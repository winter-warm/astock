from queue import Queue

import pytest

from astock.datasets import ensure_demo, list_datasets
from astock.domain import MatchConfig, dumps
from astock.engine import Run
from astock.reports import export_report
from astock.storage import Store
from astock.strategy import StrategyHost, TEMPLATES, parameter_schema


def make_run(tmp_path, template="双均线趋势", mode="backtest"):
    ensure_demo(tmp_path / "datasets")
    ds = next(x for x in list_datasets(tmp_path / "datasets") if x["kind"] == ("bar" if mode == "backtest" else "quote"))
    code = TEMPLATES[template]["code"]
    return Run({"name": template, "mode": mode, "dataset": ds["id"], "code": code,
                "parameters": {k: v["default"] for k, v in parameter_schema(code).items()},
                "initial": 100000, "config": MatchConfig(), "speed": 1000}, tmp_path, Queue())


@pytest.mark.parametrize("template", list(TEMPLATES))
def test_all_templates_complete_with_cash_invariants(tmp_path, template):
    run = make_run(tmp_path, template)
    try:
        while run.status == "RUNNING":
            run.step()
        assert run.status == "COMPLETED"
        assert run.broker.trades
        assert run.index == len(run.events)
        run.broker.check_invariants()
        for trade in run.broker.trades:
            order = next(x for x in run.broker.orders if x.id == trade.order_id)
            assert trade.time > order.created
        assert all(len(h) <= 2048 for h in run.history.values())
    finally:
        if run.host:
            run.host.close()


def test_recording_replay_is_deterministic_and_accounts_are_isolated(tmp_path):
    states = []
    for _ in range(2):
        run = make_run(tmp_path, mode="replay")
        while run.status == "RUNNING":
            run.step()
        states.append(run.broker.snapshot())
    assert dumps(states[0]) == dumps(states[1])
    assert states[0]["account"] is not states[1]["account"]
    assert states[0]["trades"]


def test_pausing_and_single_stepping_preserve_replay_result(tmp_path):
    uninterrupted = make_run(tmp_path, mode="replay")
    while uninterrupted.status == "RUNNING":
        uninterrupted.step()
    stepped = make_run(tmp_path, mode="replay")
    pause_count = 0
    while stepped.status in ("RUNNING", "PAUSED"):
        if any(o.active for o in stepped.broker.orders):
            frozen = stepped.broker.frozen_cash
            stepped.pause()
            assert stepped.broker.frozen_cash == frozen
            pause_count += 1
        stepped.step()
    assert pause_count > 0
    assert dumps(stepped.broker.snapshot()) == dumps(uninterrupted.broker.snapshot())


def test_export_and_database_restore_manifest(tmp_path):
    store = Store(tmp_path)
    run = make_run(tmp_path)
    while run.status == "RUNNING":
        run.step()
    run.persist(store)
    record = store.load_run(run.id)
    assert record["manifest"]["code"] == TEMPLATES["双均线趋势"]["code"]
    assert record["manifest"]["dataset"]["sha256"]
    report = export_report(tmp_path, run.message())
    assert report.is_file()
    assert (report.parent / "trades.csv").read_text(encoding="utf-8-sig").startswith("成交编号")
    assert "合成" in report.read_text(encoding="utf-8")
    store.close()


def test_timeout_terminates_strategy_worker():
    code = "from astock.strategy import Strategy\nclass UserStrategy(Strategy):\n    def initialize(self, ctx):\n        while True: pass"
    host = StrategyHost(code, {}, timeout=.15)
    with pytest.raises(TimeoutError):
        host.call("initialize", {})
    assert not host.process.is_alive()


def test_pause_single_step_does_not_advance_future_history(tmp_path):
    run = make_run(tmp_path, mode="replay")
    run.status = "PAUSED"
    run.step()
    assert run.status == "PAUSED"
    assert run.index == 3
    assert all(len(v) == 1 for v in run.history.values())
    assert not run.broker.trades
    run.stop()


def test_strategy_exception_exposes_line_number_without_crashing_parent():
    code = 'from astock.strategy import Strategy\nclass UserStrategy(Strategy):\n    def initialize(self, ctx):\n        raise ValueError("测试错误")'
    host = StrategyHost(code, {})
    try:
        with pytest.raises(RuntimeError, match='strategy.py.*, line 4'):
            host.call("initialize", {})
    finally:
        host.close()


def test_order_journal_preserves_submitted_state(tmp_path):
    run = make_run(tmp_path)
    while run.status == "RUNNING":
        run.step()
    journal_orders = [o for kind, o in run.journal if kind == "order"]
    assert journal_orders
    assert all(o.filled == 0 for o in journal_orders)
    assert any(o.filled > 0 for o in run.broker.orders)
