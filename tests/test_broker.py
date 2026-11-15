from datetime import datetime, timedelta

import pytest

from astock.broker import Broker
from astock.domain import Bar, CN, CorporateAction, MatchConfig, Quote, dec
from astock.rules import default_rule


def quote(symbol="600000.SH", seconds=0, volume=100000, price="10", day=12):
    at = datetime(2026, 11, day, 10, tzinfo=CN) + timedelta(seconds=seconds)
    return Quote(symbol, at, at, dec(price), dec(price), dec(price), 100000, 100000, volume,
                 dec(10), dec(11), dec(9))


def broker(symbol="600000.SH", participation="1"):
    return Broker({symbol: default_rule(symbol)}, config=MatchConfig(
        participation=dec(participation), slippage_ticks=0))


def test_no_same_quote_fill_and_duplicate_does_not_fill():
    b = broker()
    q = quote()
    b.on_event(q)
    o = b.submit(q.symbol, "BUY", 100, 10)
    assert b.frozen_cash == dec("1005.01")
    assert not b.on_event(q)
    assert not b.trades
    b.on_event(quote(seconds=5, volume=100100))
    assert o.status == "FILLED"
    assert b.account.cash == dec("98994.99")
    assert b.frozen_cash == 0
    b.on_event(quote(seconds=5, volume=100200))
    assert len(b.trades) == 1


def test_minimum_commission_is_per_order_not_per_partial_fill():
    b = broker(participation="0.1")
    b.on_event(quote())
    order = b.submit("600000.SH", "BUY", 200, 10)
    b.on_event(quote(seconds=5, volume=100500))
    assert order.filled == 50
    assert order.status == "PARTIAL"
    b.on_event(quote(seconds=10, volume=102000))
    assert order.filled == 200
    assert order.commission == dec(5)
    assert sum(t.fee for t in b.trades) == dec("5.02")
    b.check_invariants()


def test_t_plus_one_and_next_day():
    b = broker()
    b.on_event(quote())
    b.submit("600000.SH", "BUY", 100, 10)
    b.on_event(quote(seconds=5, volume=100100))
    assert b.available_quantity("600000.SH") == 0
    o = b.submit("600000.SH", "SELL", 100, 10)
    assert o.status == "REJECTED"
    b.on_event(quote(day=13))
    assert b.available_quantity("600000.SH") == 100
    sell = b.submit("600000.SH", "SELL", 100, 10)
    b.on_event(quote(day=13, seconds=5, volume=100100))
    assert sell.status == "FILLED"
    assert b.account.positions["600000.SH"].quantity == 0
    assert b.account.equity == b.account.initial - b.account.fees


def test_t_zero_etf_and_cancel_reservations():
    b = broker("518880.SH")
    b.on_event(quote("518880.SH"))
    order = b.submit("518880.SH", "BUY", 200, 10)
    b.on_event(quote("518880.SH", seconds=5, volume=100200))
    assert order.status == "FILLED"
    assert b.available_quantity("518880.SH") == 200
    s1 = b.submit("518880.SH", "SELL", 100, 10)
    assert b.available_quantity("518880.SH") == 100
    b.cancel(s1.id)
    assert b.available_quantity("518880.SH") == 200


def test_stale_quotes_and_reconnect_gap_cannot_spend_accumulated_volume():
    b = broker()
    b.on_event(quote())
    order = b.submit("600000.SH", "BUY", 100, 10)
    q = quote(seconds=5, volume=200000)
    b.on_event(q, live_now=q.time + timedelta(seconds=30))
    assert not b.trades
    b.on_event(quote(seconds=60, volume=300000))
    assert not b.trades
    b.on_event(quote(seconds=65, volume=300100))
    assert order.status == "FILLED"


def test_shared_liquidity_cannot_be_reused_between_orders():
    b = broker()
    b.on_event(quote())
    one = b.submit("600000.SH", "BUY", 100, 10)
    two = b.submit("600000.SH", "BUY", 100, 10)
    b.on_event(quote(seconds=5, volume=100120))
    assert one.filled + two.filled == 120


def test_invalid_sizes_ticks_money_and_session():
    b = broker()
    b.on_event(quote())
    for qty, price in ((1, 10), (100, "10.001"), (10000, 10), (100, 12)):
        assert b.submit("600000.SH", "BUY", qty, price).status == "REJECTED"
    q = quote(seconds=3 * 3600 + 30 * 60)
    q.time = q.time.replace(hour=12)
    b.on_event(q)
    assert b.submit("600000.SH", "BUY", 100, 10).status == "REJECTED"


def test_daily_signals_fill_at_next_open_and_expire_after_attempt():
    b = broker()
    day = datetime(2026, 11, 12, 15, tzinfo=CN)
    b.on_event(Bar("600000.SH", day, dec(10), dec(11), dec(9), dec(10), 100000, prev_close=dec(10)))
    o = b.submit("600000.SH", "BUY", 100, "10.10")
    b.on_event(Bar("600000.SH", day + timedelta(days=1), dec("10.05"), dec(11), dec(10), dec("10.5"),
                   100000, prev_close=dec(10)))
    assert o.status == "FILLED"
    assert b.trades[0].price == dec("10.05")
    assert b.trades[0].time.date().isoformat() == "2026-11-13"


def test_sealed_limit_and_missing_opposite_quote_no_fill():
    b = broker()
    b.on_event(quote(price="10.99"))
    o = b.submit("600000.SH", "BUY", 100, 11)
    q = quote(seconds=5, volume=100100, price="11")
    q.ask = dec(0)
    b.on_event(q)
    assert o.filled == 0


def test_restore_keeps_cash_and_positions_but_cancels_orders():
    b = broker()
    b.on_event(quote())
    b.submit("600000.SH", "BUY", 200, 10)
    b.on_event(quote(seconds=5, volume=100100))
    from astock.domain import dumps, loads
    restored = Broker.restore(loads(dumps(b.snapshot())))
    assert restored.account.cash == b.account.cash
    assert restored.account.positions["600000.SH"].quantity == 100
    assert restored.frozen_cash == 0
    assert restored.orders[0].status == "CANCELED"


def test_dividend_receivable_and_split_do_not_create_equity():
    b = broker()
    b.on_event(quote())
    b.submit("600000.SH", "BUY", 100, 10)
    b.on_event(quote(seconds=5, volume=100100))
    before = b.account.equity
    action = CorporateAction("600000.SH", datetime(2026, 11, 13, 9, tzinfo=CN),
                             dec(1), dec(2), "split-dividend", "2026-11-16", "2026-11-16")
    b.corporate_action(action)
    assert b.account.positions["600000.SH"].quantity == 200
    assert b.account.equity == before
    assert b.account.receivables[0]["amount"] == dec(100)
    b.corporate_action(action)
    assert b.account.positions["600000.SH"].quantity == 200


def test_out_of_order_is_ignored():
    b = broker()
    b.on_event(quote(seconds=10))
    seq = b.sequence
    b.on_event(quote(seconds=5, price=9))
    assert b.sequence == seq
    assert b.market["600000.SH"].last == dec(10)


def test_nan_and_invalid_config_rejected():
    with pytest.raises(ValueError):
        dec("NaN")
    with pytest.raises(ValueError):
        Broker({"600000.SH": default_rule("600000.SH")}, config=MatchConfig(participation=dec(2)))


def test_suspended_next_day_does_not_keep_daily_signal_alive():
    b = broker()
    day = datetime(2026, 11, 12, 15, tzinfo=CN)
    b.on_event(Bar("600000.SH", day, dec(10), dec(11), dec(9), dec(10), 100000, prev_close=dec(10)))
    order = b.submit("600000.SH", "BUY", 100, 10)
    b.on_event(Bar("600000.SH", day + timedelta(days=1), dec(10), dec(10), dec(10), dec(10), 0,
                   prev_close=dec(10), suspended=True))
    assert order.status == "CANCELED"
    assert b.available_cash == b.account.initial


def test_invalid_corporate_action_is_atomic():
    b = broker()
    b.on_event(quote())
    order = b.submit("600000.SH", "BUY", 200, 10)
    b.on_event(quote(seconds=5, volume=100101))
    before_cash, before_qty, before_status, before_day = b.account.cash, 101, order.status, b.day
    with pytest.raises(ValueError, match="零碎"):
        b.corporate_action(CorporateAction("600000.SH", datetime(2026, 11, 13, 9, tzinfo=CN),
                                          dec(1), dec("1.5"), "fractional", "2026-11-16", "2026-11-16"))
    assert b.account.cash == before_cash
    assert b.account.positions["600000.SH"].quantity == before_qty
    assert order.status == before_status
    assert b.day == before_day
    assert not b.account.receivables


def test_random_partial_orders_preserve_cash_and_position_invariants():
    import random
    rng = random.Random(42)
    b = broker("518880.SH", participation="0.07")
    volume = 100000
    b.on_event(quote("518880.SH"))
    for step in range(1, 250):
        price = dec(1000 + rng.randint(-5, 5)) / 100
        volume += rng.randint(0, 4000)
        b.on_event(quote("518880.SH", seconds=step * 5, volume=volume, price=price))
        if step % 5 == 0:
            b.cancel_all()
        if rng.random() < .6:
            b.submit("518880.SH", "BUY", rng.choice([100, 200, 300]), price)
        elif b.available_quantity("518880.SH"):
            b.submit("518880.SH", "SELL", b.available_quantity("518880.SH"), price)
        b.check_invariants()
    b.cancel_all()
    assert b.frozen_cash == 0
