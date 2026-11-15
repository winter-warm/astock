"""The proposed strategy, the displayed result, and archive selection have distinct identities."""
from queue import Queue

import pytest
from PySide6 import QtWidgets

from astock.data_jobs import DataJobs
from astock.engine import Run
from astock.strategy import TEMPLATES
from astock.window import MainWindow


@pytest.fixture
def workspace(qtbot, tmp_path, monkeypatch):
    monkeypatch.setattr(DataJobs, 'start', lambda *a, **k: 'identity-preview')
    window = MainWindow(tmp_path, start_workers=False)
    window.engine_commands = Queue()
    qtbot.addWidget(window)
    window.show()
    yield window
    window.close()


def historical(window, name):
    run = Run({'mode': 'backtest', 'name': name, 'dataset': window.dataset_combo.currentData(),
               'autoplay': False}, window.root, Queue())
    run.persist(window.store)
    window.states[run.id] = run.message()
    return run


def drain(window):
    while not window.engine_commands.empty():
        window.engine_commands.get_nowait()


def test_parameter_check_is_in_parameter_tab_and_not_strategy_toolbar(workspace):
    window = workspace
    check = window.check_parameters_button
    window.editor_settings.setCurrentIndex(1)
    assert check.isVisible()
    assert window.editor_settings.currentWidget().isAncestorOf(check)
    assert not any(toolbar.isAncestorOf(check)
                   for toolbar in window.strategy_dialog.findChildren(QtWidgets.QToolBar))
    window.editor_settings.setCurrentIndex(0)
    assert not check.isVisible()


def test_editor_backtest_carries_unsaved_source_and_params_without_relabelling_old_result(workspace):
    window = workspace
    old = historical(window, '旧策略A')
    window.select_run(old.id)
    old_description = window.result_description.text()
    window.switch_workspace(0)
    window.load_template('区间突破')
    window.editor.appendPlainText('# 尚未保存的新草稿')
    window.parameters['lookback'].setValue(12)
    code = window.editor.toPlainText()
    drain(window)
    window.strategy_dialog.backtest_button.click()
    assert window.pages.currentIndex() == 1
    assert '区间突破' in window.backtest_strategy_label.text()
    assert '当前编辑草稿' in window.backtest_strategy_label.text()
    assert '尚未运行此配置' in window.backtest_strategy_label.text()
    assert 'lookback=12' in window.backtest_strategy_label.text()
    assert window.result_description.text() == old_description
    assert window.backtest_overview.state['id'] == old.id
    assert window.engine_commands.empty()
    window.backtest_start_button.click()
    request = window.engine_commands.get_nowait()
    assert (request['op'], request['mode'], request['name']) == ('start', 'backtest', '区间突破')
    assert request['code'] == code and request['parameters']['lookback'] == 12
    assert window.store.load_run(old.id)['manifest']['name'] == '旧策略A'


def test_manual_strategy_choice_loads_saved_parameters_without_starting(workspace, monkeypatch):
    window = workspace
    params = dict(window.parameter_values(), fast=9)
    window.store.save_strategy('我的均线', TEMPLATES['双均线趋势']['code'], params)
    window.editor.appendPlainText('# 当前工作需保留')
    monkeypatch.setattr(QtWidgets.QInputDialog, 'getItem', lambda *a, **k: ('已保存 · 我的均线', True))
    drain(window)
    window.choose_backtest_strategy()
    assert window.pages.currentIndex() == 1
    assert window.current_template == '我的均线'
    assert window.parameters['fast'].value() == 9
    assert '我的均线' in window.backtest_strategy_label.text()
    assert any('# 当前工作需保留' in item['code'] for item in window.store.strategies())
    assert window.engine_commands.empty()


def test_execution_controls_are_separate_and_report_export_uses_archive_selection(workspace, monkeypatch):
    window = workspace
    first = historical(window, '历史A')
    second = historical(window, '历史B')
    window.select_run(first.id)
    assert window.backtest_start_button.isVisible()
    assert not window.run_toolbar.isVisible()
    window.backtest_controls_toggle.setChecked(True)
    assert window.run_toolbar.isVisible()
    assert not window.start_button.isVisible()
    window.switch_workspace(2)
    assert not window.run_toolbar.isVisible()
    assert window.trading_control_bar.isVisible()
    assert window.active_id is None
    window.select_run(first.id)
    window.export_current()
    assert window.pages.currentIndex() == 4
    window.home_accounts.selector.setCurrentIndex(window.home_accounts.selector.findData(second.id))
    assert window.active_id == first.id
    calls = []
    monkeypatch.setattr(window, 'show_operation', lambda *a: calls.append(a))
    window.home_accounts.report_button.click()
    assert calls == [('report', second.id, '历史B')]
    drain(window)
    window.send_run('stop')
    assert window.engine_commands.empty()


def test_quote_data_has_an_explicit_replay_start_without_live_controls(workspace):
    window = workspace
    window._select_demo('quote')
    window.go_backtest()
    assert window.backtest_start_button.text() == '开始回放'
    assert window.backtest_settings_button.isEnabled()
    drain(window)
    window.backtest_start_button.click()
    request = window.engine_commands.get_nowait()
    assert request['mode'] == 'replay'
    assert window.pages.currentIndex() == 1

