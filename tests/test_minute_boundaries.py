from datetime import datetime, timedelta
from queue import Queue

import pytest

from astock.broker import Broker
from astock.domain import Bar, CN, MatchConfig, dec
from astock.engine import Run
from astock.rules import continuous_bar, default_rule


def bar(hhmm, symbol="600000.SH", period="1m"):
    hour, minute = map(int, hhmm.split(":"))
    return Bar(symbol, datetime(2026, 11, 13, hour, minute, tzinfo=CN),
               dec(10), dec(11), dec(9), dec(10), 10000, period, prev_close=dec(10))


@pytest.mark.parametrize("symbol, period, end, valid", [
    ("600000.SH", "1m", "09:30", False), ("600000.SH", "1m", "09:31", True),
    ("600000.SH", "1m", "11:30", True), ("600000.SH", "1m", "11:31", False),
    ("600000.SH", "1m", "13:00", False), ("600000.SH", "1m", "13:01", True),
    ("600000.SH", "1m", "14:57", True), ("600000.SH", "1m", "14:58", False),
    ("600000.SH", "5m", "15:00", False), ("510300.SH", "5m", "15:00", False),
    ("159915.SZ", "1m", "14:57", True), ("159915.SZ", "1m", "15:00", False),
    ("600000.SH", "60m", "11:30", True), ("600000.SH", "60m", "13:30", False),
    ("600000.SH", "5m", "11:29", False), ("600000.SH", "2m", "11:30", False),
])
def test_completed_interval_boundaries(symbol, period, end, valid):
    assert continuous_bar(bar(end, symbol, period), default_rule(symbol)) is valid


@pytest.mark.parametrize("start,end", [("11:29", "11:30"), ("14:56", "14:57"), ("11:30", "13:01")])
def test_next_completed_minute_can_fill_at_session_end_or_after_lunch(start, end):
    b = Broker({"600000.SH": default_rule("600000.SH")}, config=MatchConfig(slippage_ticks=0))
    b.on_event(bar(start))
    order = b.submit("600000.SH", "BUY", 100, 10)
    b.on_event(bar(end))
    assert order.status == "FILLED"
    assert b.trades[0].time == bar(end).time  # Completion/observation clock, not invented tick time.


def test_order_submitted_inside_a_bar_cannot_fill_at_that_bars_past_open():
    b = Broker({"600000.SH": default_rule("600000.SH")}, config=MatchConfig(slippage_ticks=0))
    b.on_event(bar("10:00"))
    b.clock += timedelta(seconds=30)
    order = b.submit("600000.SH", "BUY", 100, 10)
    b.on_event(bar("10:01"))
    assert order.filled == 0 and "晚于" in order.note
    b.on_event(bar("10:02"))
    assert order.status == "FILLED"


def test_auction_interval_cannot_fill_or_trigger_strategy_callback(tmp_path):
    run = Run({"mode": "manual", "symbols": ["600000.SH"]}, tmp_path, Queue())
    class Host:
        calls = []
        def call(self, method, *args):
            self.calls.append(method)
            return {}
    run.host = Host()
    run.event(bar("14:57"))
    order = run.broker.submit("600000.SH", "BUY", 100, 10)
    run.event(bar("14:58"))
    assert order.filled == 0 and "集合竞价" in order.note
    assert run.host.calls.count("on_bar") == 1
