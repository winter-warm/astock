from datetime import datetime, timedelta
from queue import Queue

import pytest

from astock.domain import Bar, CN, MatchConfig, Quote, dec
from astock.engine import Run


CALLBACKS = '''
class UserStrategy(Strategy):
    def on_order(self, ctx, order):
        ctx.explain("callback", id=order.id, status=order.status,
                    filled=order.filled, cash=ctx.cash)
'''


@pytest.fixture
def run_factory(tmp_path):
    runs = []
    def create(code=CALLBACKS, participation="1"):
        run = Run({"mode": "manual", "symbols": ["600000.SH"], "code": code,
                   "config": MatchConfig(slippage_ticks=0, participation=dec(participation))},
                  tmp_path, Queue())
        runs.append(run)
        return run
    yield create
    for run in runs:
        if run.host:
            run.stop()


def tick(seconds=0, volume=100000, day=12):
    at = datetime(2026, 11, day, 10, tzinfo=CN) + timedelta(seconds=seconds)
    return Quote("600000.SH", at, at, dec(10), dec(10), dec(10), 100000, 100000,
                 volume, dec(10), dec(11), dec(9))


def buy(run, quantity=100):
    run._apply({"commands": [{"op": "order", "symbol": "600000.SH", "side": "BUY",
                              "quantity": quantity, "price": dec(10), "reason": "test"}]})


def callbacks(run):
    return [entry["values"] for entry in run.logs if entry["message"] == "callback"]


def test_custom_cancel_delivers_one_immutable_update_and_releases_cash(run_factory):
    run = run_factory()
    run.event(tick())
    buy(run)
    run._apply({"commands": [{"op": "cancel", "order_id": "O000001"}]})
    run.cancel("O000001")  # Repeated cancellation is not another transition.
    events = callbacks(run)
    assert [x["status"] for x in events] == ["OPEN", "CANCELED"]
    assert events[-1]["cash"] == 100000
    assert run.broker.frozen_cash == 0
    journal = [value for kind, value in run.journal if kind in ("order", "order_update")]
    assert [o.status for o in journal] == ["OPEN", "CANCELED"]
    assert journal[0] is not run.broker.orders[0]


def test_partial_then_fill_callback_keeps_original_quantities(run_factory):
    run = run_factory()
    run.event(tick())
    buy(run)
    run.event(tick(5, 100050))
    run.event(tick(10, 100100))
    assert [(x["status"], x["filled"]) for x in callbacks(run)] == [
        ("OPEN", 0), ("PARTIAL", 50), ("FILLED", 100)]
    run.broker.check_invariants()


def test_daily_partial_and_expiry_both_reach_strategy(run_factory):
    run = run_factory(participation="0.1")
    at = datetime(2026, 11, 12, 15, tzinfo=CN)
    run.event(Bar("600000.SH", at, dec(10), dec(11), dec(9), dec(10), 100000, prev_close=dec(10)))
    buy(run, 200)
    run.event(Bar("600000.SH", at + timedelta(days=1), dec(10), dec(11), dec(9), dec(10),
                  500, prev_close=dec(10)))
    assert [(x["status"], x["filled"]) for x in callbacks(run)] == [
        ("OPEN", 0), ("PARTIAL", 50), ("CANCELED", 50)]
    assert run.broker.frozen_cash == 0


@pytest.mark.parametrize("operation", ["pause", "stop", "finish"])
def test_terminal_callbacks_cannot_reopen_orders(run_factory, operation):
    code = CALLBACKS + '''
        if order.status == "CANCELED":
            ctx.order(order.symbol, "BUY", 100, 10, "attempt to reopen")
'''
    run = run_factory(code)
    run.event(tick())
    buy(run)
    getattr(run, operation)()
    assert [x["status"] for x in callbacks(run)] == ["OPEN", "CANCELED"]
    assert len(run.broker.orders) == 1
    assert run.broker.frozen_cash == 0
    assert any("未执行回调" in x["message"] for x in run.logs)


def test_after_hours_expiry_still_sends_order_callback(run_factory):
    run = run_factory()
    run.event(tick())
    buy(run)
    after_hours = tick(day=13)
    after_hours.time = after_hours.time.replace(hour=16)
    after_hours.received = after_hours.time
    run.event(after_hours)
    assert callbacks(run)[-1]["status"] == "CANCELED"
    assert not run.broker.trades


def test_stale_and_no_volume_explain_waiting_without_duplicate_callbacks(run_factory):
    run = run_factory()
    run.event(tick())
    buy(run)
    run.event(tick(5, 100000))
    assert "成交量未增加" in run.broker.orders[0].note
    count = len(callbacks(run))
    run.event(tick(5, 100000))
    assert len(callbacks(run)) == count
    q = tick(10, 100100)
    run.broker.on_event(q, live_now=q.time + timedelta(seconds=30))
    run._flush_order_events(allow_orders=False)
    assert "行情已过期" in run.broker.orders[0].note
    assert run.broker.orders[0].filled == 0


def test_callback_generated_order_does_not_overtake_earlier_expiry(run_factory):
    code = CALLBACKS + '''
        if order.status == "PARTIAL":
            ctx.order(order.symbol, "BUY", 100, 10)
'''
    run = run_factory(code, participation="0.1")
    at = datetime(2026, 11, 12, 15, tzinfo=CN)
    run.event(Bar("600000.SH", at, dec(10), dec(11), dec(9), dec(10), 100000, prev_close=dec(10)))
    buy(run, 200)
    run.event(Bar("600000.SH", at + timedelta(days=1), dec(10), dec(11), dec(9), dec(10),
                  500, prev_close=dec(10)))
    assert [(x["id"], x["status"]) for x in callbacks(run)] == [
        ("O000001", "OPEN"), ("O000001", "PARTIAL"), ("O000001", "CANCELED"), ("O000002", "OPEN")]


def test_unbounded_callback_orders_stop_without_losing_journal(run_factory):
    code = '''
class UserStrategy(Strategy):
    def on_order(self, ctx, order):
        ctx.order(order.symbol, "BUY", 100, 10)
'''
    run = run_factory(code)
    run.event(tick())
    with pytest.raises(RuntimeError, match="过多连续指令"):
        buy(run)
    run.fail("callback-loop")
    assert run.host is None
    assert run.broker.frozen_cash == 0
    assert all(not o.active for o in run.broker.orders)
    assert {o.id for k, o in run.journal if k == "order"} == {o.id for o in run.broker.orders}
