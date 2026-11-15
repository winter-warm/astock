"""Enumerate native controls in real windows; capture routes and annotated screenshots."""
import argparse
import json
from pathlib import Path
import sys

from PySide6 import QtCore, QtGui, QtTest, QtWidgets
from astock.help_registry import help_entries, resolve_target, runtime_details
from astock.tutorial_release import snapshot
from astock.window import MainWindow


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default='output/course-interface')
    parser.add_argument('--theme', default='dark', choices=['dark', 'light'])
    parser.add_argument('--width', type=int, default=1280)
    parser.add_argument('--height', type=int, default=760)
    args = parser.parse_args()
    project = Path(__file__).resolve().parents[1]
    output = (project / args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    app = QtWidgets.QApplication([])
    window = MainWindow(output / 'data', start_workers=False)
    window.theme_name = args.theme
    window.apply_theme()
    window.resize(args.width, args.height)
    window.show()
    report = dict(passed=False, surfaces=[], uncovered=[], missing_targets=[], registered=len(help_entries()),
                  theme=args.theme, scale=window.devicePixelRatioF(), window=[args.width, args.height])
    observed = set()
    kinds = (QtWidgets.QAbstractButton, QtWidgets.QComboBox, QtWidgets.QLineEdit, QtWidgets.QAbstractSpinBox,
             QtWidgets.QAbstractItemView, QtWidgets.QPlainTextEdit, QtWidgets.QTextBrowser, QtWidgets.QTabWidget)

    def capture(surface, name):
        app.processEvents()
        rows, missing = [], []
        for action in surface.findChildren(QtGui.QAction):
            if action.property('helpId'):
                observed.add(action.property('helpId'))
        for widget in surface.findChildren(QtWidgets.QWidget):
            identity = widget.property('helpId')
            if identity:
                observed.add(identity)
                if identity not in help_entries():
                    report['missing_targets'].append(identity)
            if not widget.isVisible() or not isinstance(widget, kinds):
                continue
            target, entry = resolve_target(widget)
            # Qt internals inherit their field's explanation. Scrollbar/header are presentation controls.
            if isinstance(widget, (QtWidgets.QHeaderView, QtWidgets.QScrollBar)):
                continue
            if target is None:
                missing.append({'class': type(widget).__name__, 'name': widget.objectName(),
                                'text': widget.text() if hasattr(widget, 'text') else ''})
                continue
            if target is not widget:
                continue
            point = widget.mapTo(surface, QtCore.QPoint())
            rows.append({'id': identity, 'title': entry.get('title', entry.get('label', '')),
                         'class': type(widget).__name__, 'enabled': widget.isEnabled(),
                         'detail': runtime_details(widget), 'rect': [point.x(), point.y(), widget.width(), widget.height()]})
        picture = surface.grab()
        picture.save(str(output / (name + '.png')))
        painter = QtGui.QPainter(picture)
        painter.setPen(QtGui.QPen(QtGui.QColor('#ffbf33'), 2))
        painter.setFont(QtGui.QFont('Microsoft YaHei', 9))
        for index, row in enumerate(rows, 1):
            x, y, width, height = row['rect']
            painter.drawRect(x, y, width, height)
            painter.drawText(x + 3, y + 13, str(index))
        painter.end()
        picture.save(str(output / (name + '-annotated.png')))
        report['surfaces'].append({'name': name, 'window_title': surface.windowTitle(),
                                   'actual_size': [surface.width(), surface.height()], 'controls': rows})
        report['uncovered'].extend({'surface': name, **value} for value in missing)

    def modal(action, name):
        def inspect_modal():
            surface = app.activeModalWidget()
            if surface is None:
                report['missing_targets'].append(name + ': modal not opened')
                return
            capture(surface, name)
            surface.reject()
        QtCore.QTimer.singleShot(120, inspect_modal)
        action()

    try:
        # These real objects remain as internal compatibility handles, are deliberately
        # absent from page layouts, and must never reappear as duplicate controls.
        report['hidden_compatibility_targets'] = []
        for attribute in ('mode_combo', 'start_button', 'analysis_expand'):
            widget = getattr(window, attribute)
            identity = widget.property('helpId')
            assert identity in help_entries() and not widget.isVisible(), attribute
            observed.add(identity)
            report['hidden_compatibility_targets'].append(identity)
        for index in range(window.pages.count()):
            window.switch_workspace(index)
            capture(window, 'workspace-' + str(index))
        window.switch_workspace(5)
        for index in range(window.data_market_tabs.count()):
            window.data_market_tabs.setCurrentIndex(index)
            capture(window, 'data-tab-' + str(index))
        window.data_market_tabs.setCurrentIndex(0)
        window.switch_workspace(1)
        modal(window.choose_backtest_strategy, 'backtest-strategy-selection')
        window.backtest_controls_toggle.setChecked(True)
        capture(window, 'backtest-run-controls')
        window.backtest_controls_toggle.setChecked(False)
        for index in range(window.result_tabs.count()):
            window.result_tabs.setCurrentIndex(index)
            capture(window, 'backtest-tab-' + str(index))
        window.result_tabs.setCurrentWidget(window.activity_tabs.parentWidget())
        for index in range(window.activity_tabs.count()):
            window.activity_tabs.setCurrentIndex(index)
            capture(window, 'activity-tab-' + str(index))
        window.switch_workspace(2)
        for index in range(window.live_tabs.count()):
            window.live_tabs.setCurrentIndex(index)
            capture(window, 'trading-tab-' + str(index))
        for index in range(window.bottom_tabs.count()):
            window.bottom_tabs.setCurrentIndex(index)
            capture(window, 'execution-tab-' + str(index))
        window.switch_workspace(4)
        for index in range(window.home_accounts.tabs.count()):
            window.home_accounts.tabs.setCurrentIndex(index)
            capture(window, 'archive-tab-' + str(index))
        window.open_course_library()
        reader = window.course_library
        assert len(reader.entries) == 72 and all(e['kind'] == 'course' for e in reader.entries)
        assert not window.learning_sections.tabBar().isVisible(), '旧教程分区不应继续显示'
        for identity in ('q01', 'q19', 'q29', 'q61', 'q67'):
            item = next(i for i in reader.items if i.data(0, QtCore.Qt.ItemDataRole.UserRole)['id'] == identity)
            reader.tree.setCurrentItem(item)
            capture(window, 'course-' + identity)
        reader.render_displays([{'kind': 'table', 'headers': ['序号', '值'], 'rows': [['0', '10']], 'title': '合成表'},
                                {'kind': 'lines', 'series': {'合成价格': [10, 11, 10.5]}, 'title': '合成图'}])
        capture(window, 'course-output')
        window.open_strategy_editor()
        old_code = window.editor.toPlainText()
        window.editor.setPlainText("PARAMETERS = {'a': {'type': 'int', 'default': 2}, 'b': {'type': 'float', 'default': 0.5}, 'c': {'type': 'bool', 'default': True}, 'd': {'type': 'str', 'default': 'demo'}}\n")
        window.rebuild_parameters()
        capture(window.strategy_dialog, 'strategy-editor')
        for index in range(window.editor_settings.count()):
            window.editor_settings.setCurrentIndex(index)
            capture(window.strategy_dialog, 'editor-settings-' + str(index))
        window.editor.setPlainText(old_code)
        window.rebuild_parameters()
        # Editing is an inline primary workspace; leaving it must not hide its page.
        window.switch_workspace(0)
        def close_menu():
            menu = app.activePopupWidget()
            if menu:
                capture(menu, 'model-context-menu')
                menu.close()
        QtCore.QTimer.singleShot(100, close_menu)
        window.open_strategy_library()
        app.processEvents()
        capture(window.strategy_library_dialog, 'strategy-library')
        window.model_browser.context_menu(QtCore.QPoint(10, 10))
        modal(window.model_browser.new_model, 'new-model-name')
        window.strategy_library_dialog.close()
        modal(lambda: window.error('教学验收提示：这是合成错误，用于说明错误窗口，不会发起交易。'), 'error-dialog')
        modal(window.open_data_center, 'data-center')
        modal(window.download_dialog, 'download')
        from astock.catalog_ui import CatalogDialog
        dialog = CatalogDialog(window.root, lambda codes: None, window)
        dialog.show()
        capture(dialog, 'catalog')
        dialog.close()
        window.switch_workspace(0)
        QtTest.QTest.mouseClick(window.strategy_dialog.api_button, QtCore.Qt.MouseButton.LeftButton)
        capture(window.strategy_api_dialog, 'strategy-api')
        assert window.pages.currentIndex() == 0
        window.strategy_api_dialog.close()
        window.switch_workspace(1)
        modal(lambda: QtTest.QTest.mouseClick(window.backtest_settings_button,
                                             QtCore.Qt.MouseButton.LeftButton), 'backtest-settings')
        from astock.rule_history_ui import RuleHistoryDialog
        dialog = RuleHistoryDialog(window.root, window.dataset_combo.currentData(), window)
        dialog.add_period()
        dialog.show()
        capture(dialog, 'rules')
        from astock.domain import RulePeriod
        symbol = dialog.symbols.currentText()
        dialog.show_status_preview({'symbol': symbol, 'periods': [RulePeriod('2024-01-01', '2024-01-02', 'normal')],
                                    'audit': {'request': {'start': '2024-01-01', 'end': '2024-01-02'},
                                              'rows': [], 'basic': [{'ipoDate': '2000-01-01'}], 'missing_dates': []}})
        capture(dialog.preview, 'rules-source-preview-synthetic')
        dialog.preview.close()
        dialog.close()
        for kind in ('quality', 'report', 'compare', 'recover'):
            dialog = window.open_instruction_preview(kind)
            dialog._instruction_tour.close()
            capture(dialog, 'preview-' + kind)
            assert dialog.jobs is not None and dialog.token is None
            dialog.close()
        window.switch_workspace(2)
        modal(window.trading_tasks.new_task, 'new-trading-task')
        window.help_controller.explain(window.start_button)
        capture(window.help_controller.dialog, 'help-dialog')
        window.help_controller.dialog.close()
        window.explain_current_page()
        capture(window.control_tour, 'control-tour')
        window.control_tour.close()
        window.open_task_guide()
        capture(window.task_guide, 'task-guide')
        window.task_guide.close()
        from astock.onboarding import open_onboarding, STEPS
        before_tutorial = (window.editor.toPlainText(), window.store.strategies(), set(window.states))
        tour = open_onboarding(window)
        capture(tour, 'first-run-tutorial')
        report['tutorial_steps'] = []
        for index, step in enumerate(STEPS):
            tour.index = index
            tour.render()
            app.processEvents()
            assert tour.target is not None and tour.target.isVisible(), step
            assert tour.band.isVisible(), step
            available = tour.screen().availableGeometry()
            for button in (tour.chapter, tour.previous, tour.next, tour.skip):
                assert button.isVisible() and available.contains(button.mapToGlobal(button.rect().center())), step
            report['tutorial_steps'].append({'chapter': step[0], 'target': step[2], 'title': step[3],
                                              'visible': True, 'card_size': [tour.width(), tour.height()]})
            if index == 0 or step[0] != STEPS[index - 1][0]:
                chapter_number = tour.chapter.currentIndex()
                capture(tour, f'tutorial-chapter-{chapter_number}')
                capture(window, f'tutorial-target-{chapter_number}')
        tour.close()
        assert (window.editor.toPlainText(), window.store.strategies(), set(window.states)) == before_tutorial
        from astock.app_reset import confirm_initialization
        before_reset = set(window.root.rglob('*'))
        modal(lambda: confirm_initialization(window), 'initialize-confirmation')
        assert set(window.root.rglob('*')) == before_reset, '取消初始化不能改动数据'
        report['observed_ids'] = sorted(observed)
        report['missing_targets'].extend(sorted(set(help_entries()) - observed))
        report['passed'] = not report['uncovered'] and not report['missing_targets']
    except Exception:
        import traceback
        report['error'] = traceback.format_exc()
    finally:
        window.close()
        app.processEvents()
    report['snapshot_digest'] = snapshot(project)['digest']
    (output / 'interface-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: report.get(k) for k in ('passed', 'error', 'uncovered', 'missing_targets')}, ensure_ascii=False))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
