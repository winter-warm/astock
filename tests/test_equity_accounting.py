from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta
from queue import Queue

import pytest

from astock.broker import Broker
from astock.datasets import load_dataset, write_dataset
from astock.domain import Bar, CN, CorporateAction, MatchConfig, Quote, dec, dumps, loads
from astock.engine import Run
from astock.reports import export_report
from astock.rules import default_rule
from astock.storage import Store


SYMBOL = "600000.SH"


def quote(day=12, second=0, price="10", volume=100000, symbol=SYMBOL):
    at = datetime(2026, 11, day, 10, tzinfo=CN) + timedelta(seconds=second)
    return Quote(symbol, at, at, dec(price), dec(price), dec(price), 100000, 100000,
                 volume, dec(price), dec(price) * dec("1.1"), dec(price) * dec(".9"))


def held_broker(quantity=100, symbols=(SYMBOL,)):
    b = Broker({s: default_rule(s) for s in symbols}, config=MatchConfig(participation=dec(1), slippage_ticks=0))
    for s in symbols:
        b.on_event(quote(symbol=s))
        b.submit(s, "BUY", quantity, 10)
    for s in symbols:
        b.on_event(quote(second=5, volume=100000 + quantity, symbol=s))
    return b


def action(**changes):
    return replace(CorporateAction(SYMBOL, datetime(2026, 11, 13, 9, tzinfo=CN), dec(1), dec(2),
                                  "annual", "2026-11-16", "2026-11-17"), **changes)


def test_entitlement_payment_and_listing_are_three_separate_account_events():
    b = held_broker()
    before_cash, before_equity = b.account.cash, b.account.equity
    b.corporate_action(action())
    assert b.account.cash == before_cash and b.account.equity == before_equity
    assert b.account.positions[SYMBOL].quantity == 200
    assert b.available_quantity(SYMBOL) == 100  # Original shares remain sellable.
    assert b.equity_entries[0].receivable_delta == 100
    assert b.submit(SYMBOL, "SELL", 100, "4.5").status == "REJECTED"  # No old-price orders.
    b.on_event(quote(day=13, price="4.5"))
    assert b.submit(SYMBOL, "SELL", 200, "4.5").status == "REJECTED"
    sell = b.submit(SYMBOL, "SELL", 100, "4.5")
    b.on_event(quote(day=13, second=5, price="4.5", volume=100100))
    assert sell.status == "FILLED" and b.available_quantity(SYMBOL) == 0
    cash, equity = b.account.cash, b.account.equity
    b.on_event(quote(day=16, price="4.5"))
    assert b.account.cash == cash + 100 and b.account.equity == equity
    assert b.account.receivables == [] and b.available_quantity(SYMBOL) == 0
    b.on_event(quote(day=16, second=5, price="4.5"))
    assert len(b.equity_entries) == 2
    b.on_event(quote(day=17, price="4.5"))
    assert b.available_quantity(SYMBOL) == 100
    b.check_invariants()


@pytest.mark.parametrize("restore_after_payment", [False, True])
def test_restore_does_not_repeat_entitlement_or_payment(restore_after_payment):
    b = held_broker()
    event = action()
    b.corporate_action(event)
    if restore_after_payment:
        b.on_event(quote(day=16, price="4.5"))
    restored = Broker.restore(loads(dumps(b.snapshot())))
    restored.corporate_action(event)
    restored.on_event(quote(day=16, price="4.5", second=5))
    restored.on_event(quote(day=17, price="4.5"))
    assert len(restored.equity_entries) == 2 and not restored.account.receivables
    assert restored.account.cash == dec("99094.99")
    assert restored.account.positions[SYMBOL].quantity == 200
    restored.check_invariants()


def test_dividend_is_still_payable_after_all_original_shares_are_sold():
    b = held_broker()
    b.corporate_action(action(share_multiplier=dec(1), share_available_date=""))
    b.on_event(quote(day=13, price=9))
    b.submit(SYMBOL, "SELL", 100, 9)
    b.on_event(quote(day=13, second=5, price=9, volume=100100))
    assert b.account.positions[SYMBOL].quantity == 0
    cash = b.account.cash
    b.on_event(quote(day=17, price=9))  # Missing payment-day quotes: first later observation settles it.
    assert b.account.cash == cash + 100
    assert b.equity_entries[-1].pay_date == "2026-11-16"
    assert b.equity_entries[-1].time.date().isoformat() == "2026-11-17"
    b.check_invariants()


def test_same_event_id_on_two_symbols_and_two_entitlements_pay_once_each():
    other = "000001.SZ"
    b = held_broker(symbols=(SYMBOL, other))
    for s in (SYMBOL, other):
        b.corporate_action(action(symbol=s, share_multiplier=dec(1), share_available_date=""))
    b.on_event(quote(day=16, price=9))
    assert len(b.applied_actions) == 2 and len(b.equity_entries) == 4
    assert sum(e.cash_delta for e in b.equity_entries) == 200
    b.check_invariants()


@pytest.mark.parametrize("change", [
    {"pay_date": "2026-11-12"}, {"pay_date": "20261116"}, {"pay_date": ""},
    {"share_available_date": ""}, {"share_available_date": "2026-11-12"},
    {"cash_per_share": dec(-1)}, {"cash_per_share": dec(11)}, {"share_multiplier": dec(0)},
    {"time": datetime(2026, 11, 13, 10, tzinfo=CN)}, {"time": datetime(2026, 11, 13, 9)},
    {"symbol": "510300.SH"},
])
def test_bad_action_is_rejected_before_any_cash_order_or_clock_change(change):
    b = held_broker()
    b.submit(SYMBOL, "BUY", 100, 10)
    before = dumps(b.snapshot())
    with pytest.raises(ValueError):
        b.corporate_action(action(**change))
    assert dumps(b.snapshot()) == before


def test_conflicting_duplicate_cannot_overwrite_an_existing_entitlement():
    b = held_broker()
    event = action()
    b.corporate_action(event)
    before = dumps(b.snapshot())
    with pytest.raises(ValueError, match="内容发生变化"):
        b.corporate_action(replace(event, cash_per_share=dec(2)))
    assert dumps(b.snapshot()) == before


def test_fractional_lots_with_integral_account_entitlement_are_not_rejected():
    b = Broker({SYMBOL: default_rule(SYMBOL)}, config=MatchConfig(participation=dec(1), slippage_ticks=0))
    b.on_event(quote())
    b.submit(SYMBOL, "BUY", 100, 10)
    b.on_event(quote(second=5, volume=100033))
    b.on_event(quote(second=10, volume=100100))
    b.corporate_action(action(share_multiplier=dec("1.5")))
    assert b.account.positions[SYMBOL].quantity == 150
    assert b.available_quantity(SYMBOL) == 100
    b.check_invariants()


@pytest.mark.parametrize("damage", ["cash", "quantity", "receivable", "fee", "cost", "missing", "duplicate", "payment"])
def test_ledger_detects_corruption_even_after_corporate_actions(damage):
    b = held_broker()
    b.corporate_action(action())
    if damage == "cash":
        b.account.cash += dec(".01")
    elif damage == "quantity":
        b.account.positions[SYMBOL].lots[0].quantity += 1
    elif damage == "receivable":
        b.account.receivables[0]["amount"] += 1
    elif damage == "fee":
        b.account.fees += 1
    elif damage == "cost":
        b.account.positions[SYMBOL].cost += 1
    elif damage == "missing":
        b.equity_entries.clear()
    elif damage == "duplicate":
        b.equity_entries.append(b.equity_entries[0])
    else:
        b.on_event(quote(day=16, price="4.5"))
        b.equity_entries[-1] = replace(b.equity_entries[-1], cash_delta=dec(101))
    with pytest.raises(RuntimeError, match="记账校验失败"):
        b.check_invariants()
    with pytest.raises(RuntimeError, match="记账校验失败"):
        Broker.restore(loads(dumps(b.snapshot())))


def test_old_snapshot_with_equity_history_is_viewable_but_never_silently_reconciled():
    b = held_broker()
    b.corporate_action(action())
    old = deepcopy(b.snapshot())
    for key in ("equity_ledger_version", "equity_entries", "action_definitions", "legacy_equity_unverified"):
        old.pop(key)
    restored = Broker.restore(old)
    assert restored.legacy_equity_unverified
    assert dumps(restored.account) == dumps(b.account)
    with pytest.raises(RuntimeError, match="旧版本权益流水不完整"):
        restored.check_invariants()
    with pytest.raises(RuntimeError, match="旧版本权益流水不完整"):
        restored.on_event(quote(day=16))
    assert Broker.restore(loads(dumps(restored.snapshot()))).legacy_equity_unverified


def equity_run(tmp_path):
    def bar(day, price):
        price = dec(price)
        return Bar(SYMBOL, datetime(2026, 11, day, 15, tzinfo=CN), price, price + 1, price - 1,
                   price, 100000, prev_close=price)
    event = action()
    meta = write_dataset(tmp_path / "datasets", "分红送转教学", [bar(11, 10), bar(12, 10), event,
                          bar(13, "4.5"), bar(16, "4.5"), bar(17, "4.5")], demo=True, verified=True)
    code = '''
class UserStrategy(Strategy):
    def on_bar(self, ctx, bar):
        if bar.time.day == 11:
            ctx.order(bar.symbol, "BUY", 100, 10, "权益教学买入")
'''
    return Run({"mode": "backtest", "dataset": meta["id"], "code": code,
                "config": MatchConfig(slippage_ticks=0)}, tmp_path, Queue())


def test_real_strategy_equity_journals_roundtrip_sqlite_and_export(tmp_path):
    run = equity_run(tmp_path)
    try:
        while run.status == "RUNNING":
            run.step()
        with_store = Store(tmp_path)
        try:
            run.persist(with_store)
            record = with_store.load_run(run.id)
            recovered = Broker.restore(record["snapshot"])
            recovered.check_invariants()
            journal = with_store.db.execute("SELECT payload FROM journals WHERE kind='equity' ORDER BY id").fetchall()
            assert [loads(row[0]).kind for row in journal] == ["entitlement", "payment"]
            assert record["result"]["statistics"]["dividends_paid"] == 100
            assert recovered.account.positions[SYMBOL].quantity == 200
            path = export_report(tmp_path, run.message())
            text = path.read_text(encoding="utf-8")
            assert "权益流水" in text and "分红到账" in text and "2026-11-17" in text
            assert (path.parent / "equity.csv").read_text(encoding="utf-8-sig").count("annual") == 2
        finally:
            with_store.close()
    finally:
        if run.host:
            run.host.close()


def test_import_blocks_missing_share_availability_date_before_running(tmp_path):
    event = action(share_available_date="")
    meta = write_dataset(tmp_path, "缺少可卖日", [event, Bar(SYMBOL, event.time.replace(hour=15),
                         dec(5), dec(6), dec(4), dec(5), 1000)], verified=True)
    with pytest.raises(ValueError, match="份额可卖日期"):
        load_dataset(tmp_path, meta["id"])
