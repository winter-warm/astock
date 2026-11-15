import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from copy import deepcopy
from datetime import timedelta
from queue import Queue

import pytest

from astock.broker import Broker
from astock.catalog import empty_catalog, publish_catalog
from astock.domain import MatchConfig, Quote, dec
from astock.engine import Run
from astock.live_rules import extend_live_rules, prepare_live_catalog
from astock.storage import Store
from astock.window import MainWindow
from test_live_rules import AT, dated_catalog


def publish_day(root, at):
    value = dated_catalog()
    part = value["segments"]["etf"]
    part["evidence"]["observed_at"] = at.isoformat()
    for row in part["records"] + part["evidence"]["normalized_records"]:
        ref = row["etf_reference"]
        ref["observed_at"] = at.isoformat()
        if row.get("symbol", row.get("代码", "")).endswith(".SZ"):
            ref["source_date"] = at.date().isoformat()
    return publish_catalog(root, empty_catalog(), value)


def test_live_account_cross_day_cancels_then_updates_without_resetting_positions(tmp_path, monkeypatch):
    clock = [AT]
    monkeypatch.setattr("astock.engine.now_cn", lambda: clock[0])
    publish_day(tmp_path, AT)
    run = Run({"mode": "manual", "symbols": ["158000.SZ"],
               "config": MatchConfig(participation=dec(1), slippage_ticks=0)}, tmp_path, Queue())
    def event(seconds):
        clock[0] = AT + timedelta(seconds=seconds)
        q = Quote("158000.SZ", clock[0], clock[0], dec(10), dec(10), dec(10), 100000, 100000,
                  100000 + seconds * 100, dec(10), dec(11), dec(9))
        run.event(q, live=True)
    event(0)
    run.broker.submit("158000.SZ", "BUY", 100, 10)
    event(5)
    assert run.broker.available_quantity("158000.SZ") == 100
    pending = run.broker.submit("158000.SZ", "BUY", 100, 9)
    cash = run.broker.account.cash
    assert run.broker.frozen_cash > 0
    old_rule = deepcopy(run.broker.rules["158000.SZ"])
    event(3 * 86400)
    assert run.status == "PAUSED" and pending.status == "CANCELED"
    assert run.broker.frozen_cash == 0 and run.broker.account.cash == cash
    with pytest.raises(ValueError, match="跨日"):
        run.require_current_live_rules()
    with pytest.raises(ValueError):
        run.refresh_live_rules()  # Old catalog cannot be stretched into the new day.
    assert run.broker.rules["158000.SZ"] == old_rule
    publish_day(tmp_path, clock[0])
    run.refresh_live_rules()
    assert run.status == "PAUSED"
    assert run.broker.account.positions["158000.SZ"].quantity == 100
    assert run.broker.rules["158000.SZ"].history[0] == old_rule.history[0]
    assert [p.start for p in run.broker.rules["158000.SZ"].history] == ["2026-11-13", "2026-11-16"]
    assert len(run.manifest["live_rule_observations"]) == 2
    run.require_current_live_rules()
    store = Store(tmp_path)
    run.persist(store)
    saved = store.load_run(run.id)
    restored = Broker.restore(saved["snapshot"])
    assert restored.account.cash == cash and restored.account.positions["158000.SZ"].quantity == 100
    assert len(saved["manifest"]["live_rule_observations"]) == 2
    store.close()
    run.stop()


def test_same_day_change_cannot_rewrite_previously_used_rule(tmp_path, monkeypatch):
    monkeypatch.setattr("astock.engine.now_cn", lambda: AT)
    publish_day(tmp_path, AT)
    run = Run({"mode": "manual", "symbols": ["158000.SZ"]}, tmp_path, Queue())
    old = deepcopy(run.broker.rules)
    changed = deepcopy(old)
    from dataclasses import replace
    changed["158000.SZ"].history[0] = replace(changed["158000.SZ"].history[0], t_plus=1)
    with pytest.raises(ValueError, match="不能改写"):
        extend_live_rules(old, changed)
    assert run.broker.rules == old
    run.stop()


def test_fresh_cache_avoids_network_and_failed_rules_leave_no_account_directory(tmp_path, monkeypatch):
    monkeypatch.setattr("astock.domain.now_cn", lambda: AT)
    monkeypatch.setattr("astock.engine.now_cn", lambda: AT)
    def unexpected(*args, **kwargs):
        raise AssertionError("Fresh catalog should not refresh")
    monkeypatch.setattr("astock.etf_reference.fetch_etfs", unexpected)
    with pytest.raises(ValueError):
        Run({"mode": "manual", "symbols": ["158000.SZ"]}, tmp_path, Queue())
    assert not list(tmp_path.iterdir())
    publish_day(tmp_path, AT)
    assert prepare_live_catalog(tmp_path, ["158000.SZ"], lambda _: None)["catalog"] is None


def test_ui_cancel_and_late_reply_cannot_create_or_modify_account(qtbot, tmp_path, monkeypatch):
    window = MainWindow(tmp_path, start_workers=False)
    qtbot.addWidget(window)
    window.engine_commands = Queue()
    monkeypatch.setattr(window.data_jobs, "start", lambda *a, **k: "prepare-1")
    window.start_run(mode="manual")
    assert window.start_pending and window.engine_commands.empty()
    assert not window.symbol_input.isEnabled()
    window.cancel_live_rule_preparation()
    window.live_rule_message({"token": "prepare-1", "type": "finished",
                              "result": {"catalog": None, "valid_day": "2026-11-13"}})
    assert not window.start_pending and window.engine_commands.empty()
    assert window.symbol_input.isEnabled()
    window.close()


def test_ui_preparation_error_and_selected_account_change_keep_target(qtbot, tmp_path, monkeypatch):
    window = MainWindow(tmp_path, start_workers=False)
    qtbot.addWidget(window)
    window.engine_commands = Queue()
    monkeypatch.setattr(window.data_jobs, "start", lambda *a, **k: "prepare-2")
    window.start_run(mode="manual")
    window.live_rule_message({"token": "prepare-2", "type": "error", "message": "公开名单尚未更新"})
    assert "尚未更新" in window.live_rule_status.text() and window.engine_commands.empty()
    window.states["old"] = {"mode": "manual", "status": "PAUSED", "manifest": {"rules": {"158000.SZ": None}}}
    window.active_id = "old"
    window.refresh_active_live_rules()
    window.active_id = "another"
    window.live_rule_message({"token": "prepare-2", "type": "finished",
                              "result": {"catalog": None, "valid_day": "2026-11-13"}})
    assert window.engine_commands.get_nowait()["id"] == "old"
    window.close()
