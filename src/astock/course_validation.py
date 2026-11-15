"""Native tutorial smoke test, also runnable inside the frozen portable executable."""
import json
from pathlib import Path
import time
from PySide6 import QtCore, QtTest, QtWidgets
from astock.course_library import catalogue, validate
from astock.course_notebooks import export_notebooks
from astock.help_registry import help_entries


def check_strategy_entrypoints(window, report):
    """Use the actual public controls, including in the frozen application."""
    window.switch_workspace(0)
    code = window.editor.toPlainText()
    QtTest.QTest.mouseClick(window.strategy_dialog.api_button, QtCore.Qt.MouseButton.LeftButton)
    dialog = window.strategy_api_dialog
    assert dialog.isVisible() and not dialog.isModal()
    assert window.pages.currentIndex() == 0 and window.editor.toPlainText() == code
    assert 'ctx.order(symbol, side, quantity, price' in dialog.findChild(QtWidgets.QTextBrowser).toPlainText()
    QtTest.QTest.mouseClick(dialog.findChild(QtWidgets.QDialogButtonBox).button(
        QtWidgets.QDialogButtonBox.StandardButton.Close), QtCore.Qt.MouseButton.LeftButton)
    assert not dialog.isVisible()
    report['strategy_reference_keeps_editor'] = True

    window._select_demo('bar')
    window.go_backtest()
    assert not window.speed_combo.isEnabled()
    assert window.speed_combo.accessibleName() == '快照回放速度'
    assert '合成教学数据' in window.dataset_combo.currentText()
    assert 'K 线回测' in window.speed_combo.toolTip()
    window._select_demo('quote')
    window.go_backtest()
    assert window.speed_combo.isEnabled()
    report['replay_speed_label_and_bar_disabled'] = True
    original = (window.dataset_combo.currentData(), window.capital.value())
    failures = []
    opened = []

    def inspect():
        from astock.backtest_setup import BacktestSetup
        settings = QtWidgets.QApplication.activeModalWidget()
        try:
            assert isinstance(settings, BacktestSetup)
            opened.append(True)
            assert settings.selected_meta()['kind'] == 'quote'
            assert not settings.dates[0].isEnabled() and '完整录制区间' in settings.selection_note.text()
            bar = next(meta for meta in window.datasets if meta['kind'] == 'bar')
            settings.dataset.setCurrentIndex(settings.dataset.findData(bar['id']))
            assert settings.dates[0].isEnabled()
            assert settings.capital.maximum() == window.capital.maximum()
            settings.capital.setValue(settings.capital.maximum())
            QtTest.QTest.mouseClick(settings.actions.button(QtWidgets.QDialogButtonBox.StandardButton.Cancel),
                                   QtCore.Qt.MouseButton.LeftButton)
        except Exception as error:
            failures.append(repr(error))
        finally:
            if settings and settings.isVisible():
                settings.reject()

    QtCore.QTimer.singleShot(100, inspect)
    QtTest.QTest.mouseClick(window.backtest_settings_button, QtCore.Qt.MouseButton.LeftButton)
    assert opened and not failures, failures
    assert original == (window.dataset_combo.currentData(), window.capital.value())
    assert window.editor.toPlainText() == code and not window.start_pending
    report['quote_settings_opens_and_cancel_preserves_state'] = True


def start_course_smoke(application, window, screenshot=None):
    output = Path(screenshot).parent if screenshot else window.root / 'reports' / 'course-smoke'
    output.mkdir(parents=True, exist_ok=True)
    report = {'passed': False, 'errors': [], 'lesson_count': 0}
    started = time.monotonic()
    state = {'phase': 'start', 'result': None}
    timer = QtCore.QTimer(window)
    timer.setInterval(100)

    def finish(error=None):
        if state['phase'] == 'done':
            return
        state['phase'] = 'done'
        timer.stop()
        if error:
            report['errors'].append(str(error))
        report['passed'] = not report['errors']
        report['elapsed_seconds'] = time.monotonic() - started
        (output / 'course-result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        if screenshot:
            window.grab().save(screenshot)
        QtCore.QTimer.singleShot(10, lambda: (window.close(), application.exit(0 if report['passed'] else 2)))

    def poll():
        try:
            if time.monotonic() - started > 50:
                finish('课程便携验收超时')
                return
            reader = window.course_library
            if state['phase'] == 'start':
                state['phase'] = 'checking-entrypoints'
                check_strategy_entrypoints(window, report)
                errors = validate(require_complete=True)
                if errors:
                    finish('; '.join(errors))
                    return
                report['lesson_count'] = sum(e['kind'] == 'course' for e in catalogue())
                report['help_controls'] = len(help_entries())
                window.open_course_library()
                reader.tree.setCurrentItem(next(i for i in reader.items if i.data(0, QtCore.Qt.ItemDataRole.UserRole)['id'] == 'q07'))
                reader.bookmark.click()
                reader.check_input.setText(str(reader.current['check']['answers'][0]))
                reader.check_button.click()
                assert reader.state['q07'].get('check_digest')
                reader.code.setPlainText("import numpy as np\nimport pandas as pd\nx=np.array([10.,11.,12.])\nprint('便携练习', x.mean())\nlab.table(pd.DataFrame({'price':x}), title='表格')\nlab.lines({'price':x}, title='图表')\nassert x.mean()==11\n")
                reader.runner.result.connect(lambda value: state.update(result=value))
                reader.run_button.click()
                state['phase'] = 'running'
            elif state['phase'] == 'running' and state['result']:
                result = state['result']
                assert result['status'] == 'finished', result
                assert '便携练习 11.0' in result['output']
                assert reader.displays.count() == 2
                report['lab_status'] = result['status']
                report['display_tabs'] = reader.displays.count()
                target = export_notebooks(output / 'notebooks')
                report['notebooks'] = len(list(target.glob('q*.ipynb')))
                assert report['notebooks'] == 72
                assert (target / 'uv.lock').is_file()
                window.help_controller.pick()
                QtTest.QTest.mouseClick(reader.run_button, QtCore.Qt.MouseButton.LeftButton)
                assert reader.runner.job is None, '点选解释不应重跑代码'
                assert window.help_controller.dialog.isVisible()
                window.help_controller.dialog.close()
                for kind in ('quality', 'report', 'compare', 'recover'):
                    dialog = window.open_instruction_preview(kind)
                    assert dialog.token is None and not dialog.retry.isEnabled()
                    dialog.close()
                window.open_task_guide()
                window.task_guide.advance(1)
                window.task_guide.close()
                from astock.onboarding import open_onboarding, STEPS, STATE_KEY
                tour = open_onboarding(window, first_run=True)
                assert tour is not None
                for _ in STEPS:
                    tour.advance(1)
                assert window.store.setting(STATE_KEY)['status'] == 'completed'
                assert open_onboarding(window, first_run=True) is None
                tour = open_onboarding(window)
                assert tour.isVisible()
                tour.close()
                assert window.editor.isVisible()
                assert len(reader.entries) == 72
                report['first_run_and_replay'] = True
                from astock.storage import Store
                from astock.app_reset import initialize_closed_data
                reset_root = output / 'initialization-fixture'
                fixture = Store(reset_root)
                fixture.set_setting('learning_library_v1', {'q19': {'bookmark': True}})
                fixture.save_strategy('to-reset', 'example', {})
                fixture.close()
                reset = initialize_closed_data(reset_root)
                fixture = Store(reset_root)
                assert not fixture.strategies()
                assert fixture.setting('learning_library_v1')['q19']['bookmark']
                fixture.close()
                assert not reset['backup_created']
                report['initialization_preserves_learning_without_backup'] = True
                report['preview_no_jobs'] = True
                report['point_help_no_action'] = True
                report['external_python_required_for_app'] = False
                finish()
        except Exception:
            import traceback
            finish(traceback.format_exc())
    timer.timeout.connect(poll)
    timer.start()
    return timer
