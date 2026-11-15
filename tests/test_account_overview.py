from datetime import datetime, timedelta

from astock.broker import Broker
from astock.domain import CN, MatchConfig, Quote, dec, dumps
from astock.rules import default_rule
from astock.window import MainWindow


def account(initial):
    b = Broker({"600000.SH": default_rule("600000.SH")}, initial, MatchConfig(slippage_ticks=0))
    at = datetime(2026, 11, 12, 10, tzinfo=CN)
    q = Quote("600000.SH", at, at, dec(10), dec(10), dec(10), 100000, 100000, 100000,
              dec(10), dec(11), dec(9))
    b.on_event(q)
    b.submit(q.symbol, "BUY", 100, 10, "账户测试")
    return b


def test_switch_accounts_is_read_only_and_persists(qtbot, tmp_path):
    w = MainWindow(tmp_path, start_workers=False)
    qtbot.addWidget(w)
    a, b = account(100000), account(200000)
    for key, broker in (("a", a), ("b", b)):
        w.store.save_run(key, "同名策略", "manual", "PAUSED", {}, broker.snapshot(), {"logs": []})
    original = dumps(w.store.load_run("a"))
    home = w.home_accounts
    home.refresh()
    home.selector.setCurrentIndex(home.selector.findData("a"))
    assert home.values["总资产"].text() == "100,000.00"
    assert home.values["冻结资金"].text() == f"{a.frozen_cash:,.2f}"
    assert home.operations.rowCount() == 1
    assert home.operations.item(0, 6).text() == a.orders[0].note
    home.selector.setCurrentIndex(home.selector.findData("b"))
    assert home.values["总资产"].text() == "200,000.00"
    assert w.active_id is None
    assert w.engine_commands.empty()
    assert dumps(w.store.load_run("a")) == original
    assert a.orders[0].active
    w.close()
    reopened = MainWindow(tmp_path, start_workers=False)
    qtbot.addWidget(reopened)
    assert reopened.home_accounts.selector.currentData() == "b"
    reopened.close()


def test_live_selected_account_updates_without_following_active_account(qtbot, tmp_path):
    w = MainWindow(tmp_path, start_workers=False)
    qtbot.addWidget(w)
    b = account(100000)
    at = b.clock + timedelta(seconds=5)
    b.on_event(Quote("600000.SH", at, at, dec(10), dec(10), dec(10), 100000, 100000, 200000,
                     dec(10), dec(11), dec(9)))
    w.states["held"] = {"id": "held", "name": "持仓账户", "mode": "manual", "status": "PAUSED",
                        "snapshot": b.snapshot(), "result": {"logs": []}}
    home = w.home_accounts
    home.refresh()
    assert home.positions.rowCount() == 1
    assert home.positions.item(0, 2).text() == "0"  # T+1, not total quantity
    assert home.operations.rowCount() == 2
    w.active_id = "unrelated"
    b.account.cash += dec(10)
    home.refresh()
    assert home.selector.currentData() == "held"
    assert home.values["总资产"].text() == f"{b.account.equity:,.2f}"
    home.open_details()
    assert w.active_id == "held"
    assert w.engine_commands.get(timeout=2) == {"op": "load", "id": "held"}
    assert w.pages.currentIndex() == 2
    w.close()


def test_missing_snapshot_clears_previous_account(qtbot, tmp_path):
    w = MainWindow(tmp_path, start_workers=False)
    qtbot.addWidget(w)
    home = w.home_accounts
    assert not home.details.isEnabled()
    w.store.save_run("a", "正常", "backtest", "COMPLETED", {}, account(100000).snapshot(), {})
    w.store.save_run("b", "无快照", "backtest", "ERROR", {}, {}, {})
    home.refresh()
    home.selector.setCurrentIndex(home.selector.findData("a"))
    assert home.operations.rowCount() == 1
    home.selector.setCurrentIndex(home.selector.findData("b"))
    assert home.values["总资产"].text() == "—"
    assert home.operations.rowCount() == 0
    assert "暂无可用快照" in home.empty.text()
    w.close()
