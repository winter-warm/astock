"""Independent regressions for account identity at workspace boundaries."""
from dataclasses import replace
from datetime import datetime, timedelta
from queue import Queue

import pytest
from PySide6 import QtWidgets

from astock.data_jobs import DataJobs
from astock.domain import CN, MatchConfig, Quote, dec
from astock.engine import Run
from astock.window import MainWindow


@pytest.fixture
def isolated_workspace(qtbot, tmp_path, monkeypatch):
    monkeypatch.setattr(DataJobs, 'start', lambda *a, **k: 'isolated-preview')
    window = MainWindow(tmp_path, start_workers=False)
    window.engine_commands = Queue()
    window.output = Queue()
    qtbot.addWidget(window)
    window.show()
    yield window
    window.close()


def make_run(window, mode, name, *, fill=False):
    if mode == 'backtest':
        meta = next(m for m in window.datasets if m['kind'] == 'bar')
        request = {'mode': mode, 'name': name, 'dataset': meta['id'], 'autoplay': False}
    else:
        request = {'mode': mode, 'name': name, 'symbols': ['600000.SH'], 'autoplay': False,
                   'config': MatchConfig(slippage_ticks=0)}
    run = Run(request, window.root, Queue())
    if mode == 'manual':
        at = datetime(2026, 11, 12, 10, tzinfo=CN)
        quote = Quote('600000.SH', at, at, dec(10), dec(10), dec(10),
                      100000, 100000, 100000, dec(10), dec(11), dec(9))
        run.broker.on_event(quote)
        run.broker.submit(quote.symbol, 'BUY', 100, dec(10), name)
        if fill:
            later = at + timedelta(seconds=5)
            run.broker.on_event(replace(quote, time=later, received=later, volume=200000))
            assert run.broker.trades
    run.persist(window.store)
    window.states[run.id] = run.message()
    return run


def clear_commands(window):
    while not window.engine_commands.empty():
        window.engine_commands.get_nowait()


def poll_messages(window):
    # The UI intentionally processes each queue batch for at most 16 ms.
    while not window.output.empty():
        window.poll()


def test_switching_modes_restores_the_correct_control_account(isolated_workspace):
    window = isolated_workspace
    historical = make_run(window, 'backtest', '历史策略A')
    trading = make_run(window, 'manual', '模拟账户B')
    window.select_run(historical.id)
    assert window.pages.currentIndex() == 1
    assert window.active_id == historical.id
    window.select_run(trading.id)
    assert window.pages.currentIndex() == 2
    assert window.active_id == trading.id
    window.switch_workspace(1)
    assert window.active_id == historical.id
    assert window.backtest_overview.state['id'] == historical.id
    clear_commands(window)
    window.send_run('stop')
    assert window.engine_commands.get_nowait() == {'op': 'stop', 'id': historical.id}
    window.switch_workspace(2)
    assert window.active_id == trading.id
    clear_commands(window)
    window.send_run('stop')
    assert window.engine_commands.get_nowait() == {'op': 'stop', 'id': trading.id}


def test_late_foreign_mode_update_cannot_replace_backtest_results(isolated_workspace):
    window = isolated_workspace
    historical = make_run(window, 'backtest', '历史策略A')
    trading = make_run(window, 'manual', '模拟账户B')
    window.select_run(historical.id)
    before = window.result_description.text()
    window.display_run(trading.message())
    assert window.pages.currentIndex() == 1
    assert window.active_id == historical.id
    assert window.backtest_overview.state['id'] == historical.id
    assert window.result_description.text() == before


@pytest.mark.parametrize('old_update_arrives', [False, True])
def test_created_run_stays_selected_after_returning_from_editor(isolated_workspace, old_update_arrives):
    window = isolated_workspace
    old_run = make_run(window, 'backtest', '原回测A')
    created_run = make_run(window, 'backtest', '新回测B')
    window.select_run(old_run.id)
    window.dispatch_run_request({'op': 'start', 'mode': 'backtest', 'name': '新回测B'})
    window.switch_workspace(0)
    window.output.put({'type': 'run_created', 'id': created_run.id})
    window.output.put(created_run.message())
    if old_update_arrives:
        window.output.put(old_run.message())
    poll_messages(window)
    assert window.pages.currentIndex() == 0
    assert window.workspace_run_ids[1] == created_run.id
    window.switch_workspace(1)
    assert window.active_id == created_run.id
    assert window.backtest_overview.state['id'] == created_run.id


def test_step_controls_the_selected_run_when_new_run_data_differs(isolated_workspace):
    window = isolated_workspace
    historical = make_run(window, 'backtest', '已选历史账户')
    another = next(meta for meta in window.datasets if meta['kind'] == 'quote')
    window.dataset_combo.setCurrentIndex(window.dataset_combo.findData(another['id']))
    window.select_run(historical.id)
    clear_commands(window)
    window.step_run()
    assert window.engine_commands.get_nowait() == {'op': 'step', 'id': historical.id}
    assert window.engine_commands.empty()
    assert not window.start_pending


def test_created_account_mode_survives_an_unrelated_background_error(isolated_workspace):
    window = isolated_workspace
    historical = make_run(window, 'backtest', '后台旧回测')
    trading = make_run(window, 'manual', '新手动账户')
    window.select_run(historical.id)
    window.connected = True
    window.dispatch_run_request({'op': 'start', 'mode': 'manual', 'symbols': ['600000.SH']})
    window.output.put({'type': 'error', 'message': '后台旧回测的策略发生异常'})
    window.output.put({'type': 'run_created', 'id': trading.id})
    window.output.put(trading.message())
    poll_messages(window)
    assert window.pages.currentIndex() == 2
    assert window.workspace_run_ids[1] == historical.id
    assert window.workspace_run_ids[2] == trading.id
    assert window.active_id == trading.id


def test_stale_order_row_cannot_cancel_same_number_in_another_account(isolated_workspace):
    window = isolated_workspace
    first = make_run(window, 'manual', '账户A')
    second = make_run(window, 'manual', '账户B')
    assert first.broker.orders[0].id == second.broker.orders[0].id
    window.select_run(second.id)
    # Simulate a queued table selection event that belongs to the previous account.
    window.orders_table.set_records(first.broker.orders, first.id)
    window.orders_table.selectRow(0)
    clear_commands(window)
    window.cancel_selected()
    assert window.engine_commands.empty()
    window.orders_table.set_records(second.broker.orders, second.id)
    window.orders_table.selectRow(0)
    window.cancel_selected()
    assert window.engine_commands.get_nowait() == {
        'op': 'cancel', 'id': second.id, 'order_id': second.broker.orders[0].id,
    }


def test_simulated_trade_details_stay_out_of_historical_results(isolated_workspace, monkeypatch):
    window = isolated_workspace
    historical = make_run(window, 'backtest', '历史策略A')
    trading = make_run(window, 'manual', '模拟账户B', fill=True)
    window.select_run(historical.id)
    window.select_run(trading.id)
    shown = []
    monkeypatch.setattr(QtWidgets.QMessageBox, 'information', lambda *args: shown.append(args[1:]))
    window.trades_table.selectRow(0)
    window.select_trade(window.trades_table)
    assert shown
    assert window.pages.currentIndex() == 2
    assert window.active_id == trading.id
    assert window.workspace_run_ids[1] == historical.id
