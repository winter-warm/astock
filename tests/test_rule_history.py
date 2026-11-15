import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from queue import Queue

import pytest

from astock.broker import Broker
from astock.data_jobs import publish_import
from astock.datasets import dataset_reader, load_dataset, write_dataset
from astock.domain import Bar, CN, MatchConfig, Quote, RulePeriod, dec, dumps, loads
from astock.engine import Run
from astock.rule_history import read_rule_metadata, stage_rule_revision
from astock.rules import continuous_bar, continuous_session, default_rule, rule_at, validate_rule


SYMBOL = "600000.SH"
SOURCE = "人工构造边界测试，不是真实证券状态"


def at(value):
    return datetime.fromisoformat(value).replace(tzinfo=CN)


def bar(day, symbol=SYMBOL, price=10):
    return Bar(symbol, at(day + "T15:00"), dec(price), dec(price) + dec("0.1"),
               dec(price) - dec("0.1"), dec(price), 1_000_000, prev_close=dec(10))


def history(symbol=SYMBOL, start="2026-07-01", end="2026-07-10", status="risk_warning", **kw):
    r = default_rule(symbol)
    r.history = [RulePeriod(start, end, SOURCE, status, **kw)]
    return r


def broker(rule):
    return Broker({rule.symbol: rule}, config=MatchConfig(slippage_ticks=0, participation=dec(1)))


@pytest.mark.parametrize("symbol,old,new", [(SYMBOL, ".05", ".10"), ("000001.SZ", ".05", ".10"),
                                          ("688001.SH", ".20", ".20"), ("300001.SZ", ".20", ".20")])
def test_risk_warning_changes_at_effective_date_not_consultation_date(symbol, old, new):
    r = history(symbol, start="2025-06-27")
    assert rule_at(r, "2025-06-27").limit_rate == dec(old)
    assert rule_at(r, "2026-07-03").limit_rate == dec(old)
    assert rule_at(r, "2026-07-06").limit_rate == dec(new)
    b = broker(r)
    b.on_event(replace(bar("2026-07-03", symbol), time=at("2026-07-03T10:00"), period="1m"))
    o = b.submit(symbol, "BUY", 200, dec("10.60"))
    assert (o.status == "REJECTED") == (old == ".05")
    b.cancel_all()
    b.on_event(replace(bar("2026-07-06", symbol), time=at("2026-07-06T10:00"), period="1m"))
    assert b.submit(symbol, "BUY", 200, dec("10.60")).active
    assert r.limit_rate == default_rule(symbol).limit_rate


@pytest.mark.parametrize("day,allowed", [("2026-07-03", True), ("2026-07-06", False)])
def test_sse_etf_auction_change_matches_quotes_bars_and_coverage(tmp_path, day, allowed):
    symbol = "510300.SH"
    r = default_rule(symbol)
    assert continuous_session(at(day + "T14:58"), r) is allowed
    e = replace(bar(day, symbol), period="1m")
    assert continuous_bar(e, r) is allowed
    meta = write_dataset(tmp_path, "基金收盘边界", [replace(e, time=at(day + "T14:57")), e], verified=True)
    inspected, events = dataset_reader(tmp_path, meta["id"], inspection=True)
    list(events)
    assert inspected["quality"]["counts"].get("outside_session", 0) == (0 if allowed else 1)
    b = broker(r)
    def quote(time, volume):
        t = at(day + "T" + time)
        return Quote(symbol, t, t, dec(10), dec(10), dec(10), 1000, 1000, volume,
                     dec(10), dec(11), dec(9))
    b.on_event(quote("14:56:55", 1000))
    order = b.submit(symbol, "BUY", 100, 10)
    b.on_event(quote("14:57:00", 2000))
    assert bool(order.filled) is allowed


def test_timeline_does_not_leak_future_status_into_strategy_context(tmp_path):
    r = history(end="2026-07-03", status="normal")
    r.history.append(RulePeriod("2026-07-06", "2026-07-10", SOURCE, "risk_warning"))
    meta = write_dataset(tmp_path / "datasets", "未来状态", [bar("2026-07-03"), bar("2026-07-06")],
                         rules={SYMBOL: r}, verified=True)
    run = Run({"mode": "backtest", "dataset": meta["id"], "code": ""}, tmp_path, Queue())
    assert run.context()["rules"][SYMBOL].history == []
    run.event(bar("2026-07-03"))
    current = run.context()["rules"][SYMBOL]
    assert current.history == [] and current.status == "normal"
    assert len(run.manifest["rules"][SYMBOL].history) == 2
    run.event(bar("2026-07-06"))
    assert run.context()["rules"][SYMBOL].status == "risk_warning"


def test_known_unlimited_period_can_trade_above_standard_limit_then_returns_to_limit():
    r = history(status="no_limit", end="2026-07-03")
    r.history.append(RulePeriod("2026-07-06", "2026-07-10", SOURCE))
    b = broker(r)
    b.on_event(bar("2026-07-01", price=13))
    order = b.submit(SYMBOL, "BUY", 100, 15)
    assert order.active and not b.trades
    b.on_event(bar("2026-07-02", price=14))
    assert order.filled == 100 and b.trades[0].price == 14
    b.on_event(bar("2026-07-06"))
    second = b.submit(SYMBOL, "BUY", 100, 15)
    assert second.active
    b.on_event(bar("2026-07-07"))
    assert second.status == "REJECTED"


@pytest.mark.parametrize("state", ["suspended", "unlisted", "unknown"])
def test_nontrading_period_expires_pending_daily_orders_and_rejects_new(state):
    r = history(status="normal", end="2026-07-03")
    r.history.append(RulePeriod("2026-07-06", "2026-07-10", SOURCE, state))
    b = broker(r)
    b.on_event(bar("2026-07-03"))
    order = b.submit(SYMBOL, "BUY", 100, 10)
    assert b.frozen_cash > 0
    b.on_event(bar("2026-07-06"))
    assert not b.trades and order.status == "CANCELED" and b.frozen_cash == 0
    assert b.submit(SYMBOL, "BUY", 100, 10).status == "REJECTED"


def test_etf_t0_interval_uses_current_rule_and_roundtrips_snapshot():
    symbol = "510300.SH"
    r = history(symbol, status="normal", t_plus=0)
    b = broker(r)
    start = at("2026-07-01T10:00")
    def quote(i):
        t = start + timedelta(seconds=i * 5)
        return Quote(symbol, t, t, dec(10), dec(10), dec(10), 1000, 1000, 1000 + 1000*i,
                     dec(10), dec(11), dec(9))
    b.on_event(quote(0))
    b.submit(symbol, "BUY", 100, 10)
    b.on_event(quote(1))
    assert b.available_quantity(symbol) == 100
    restored = Broker.restore(loads(dumps(b.snapshot())))
    assert restored.available_quantity(symbol) == 100 and restored.rules[symbol].history == r.history
    b.submit(symbol, "SELL", 100, 10)
    b.on_event(quote(2))
    assert b.account.positions[symbol].quantity == 0
    b.check_invariants()


def test_gap_blocks_backtest_but_still_allows_inspection(tmp_path):
    r = history(end="2026-07-03")
    meta = write_dataset(tmp_path, "规则缺口", [bar("2026-07-06")], verified=True, rules={SYMBOL: r})
    with pytest.raises(ValueError, match="缺少证券状态"):
        load_dataset(tmp_path, meta["id"])
    _, events = dataset_reader(tmp_path, meta["id"], inspection=True)
    assert len(list(events)) == 1


@pytest.mark.parametrize("periods,match", [
    ([RulePeriod("2026-07-01", "2026-07-03", SOURCE), RulePeriod("2026-07-03", "2026-07-06", SOURCE)], "交叠"),
    ([RulePeriod("2026-07-03", "2026-07-01", SOURCE)], "倒置"),
    ([RulePeriod("2026-07-01", "2026-07-03", "")], "来源"),
    ([RulePeriod("2026-7-1", "2026-07-03", SOURCE)], "YYYY"),
    ([RulePeriod("2026-07-01", "2026-07-03", SOURCE, t_plus=0)], "T\\+0"),
    ([RulePeriod("2026-07-01", "2026-07-03", SOURCE, "risk_warning", dec(".2"))], "不能另填"),
])
def test_reject_ambiguous_or_invalid_rule_intervals(periods, match):
    r = default_rule(SYMBOL)
    r.history = periods
    with pytest.raises(ValueError, match=match):
        validate_rule(r)


def test_risk_warning_daily_buy_cap_includes_fills_and_open_orders():
    r = history()
    b = Broker({SYMBOL: r}, 20_000_000,
               MatchConfig(participation=dec(1), slippage_ticks=0, max_order_value=dec(20_000_000)))
    first_bar = replace(bar("2026-07-06"), time=at("2026-07-06T10:00"), period="1m")
    b.on_event(first_bar)
    first = b.submit(SYMBOL, "BUY", 400000, 10)
    assert first.active
    assert b.submit(SYMBOL, "BUY", 100100, 10).status == "REJECTED"
    b.cancel(first.id)
    assert b.submit(SYMBOL, "BUY", 500000, 10).active
    b.on_event(replace(first_bar, time=first_bar.time + timedelta(minutes=1)))
    assert sum(t.quantity for t in b.trades) == 500000
    assert b.submit(SYMBOL, "BUY", 100, 10).status == "REJECTED"


def test_daily_intent_uses_execution_day_price_limit_without_peeking_at_future():
    b = broker(history())
    b.on_event(bar("2026-07-02"))
    old = b.submit(SYMBOL, "BUY", 100, "10.6")
    assert old.active and not b.trades
    b.on_event(bar("2026-07-03"))
    assert old.status == "REJECTED" and "成交日价格范围" in old.note
    boundary = b.submit(SYMBOL, "BUY", 100, "10.6")
    assert boundary.active and not b.trades
    b.on_event(bar("2026-07-06"))
    assert boundary.status == "FILLED" and b.trades[0].time.day == 6


def test_explicit_unlimited_quotes_keep_price_cage_and_next_quote_fill():
    b = broker(history(status="no_limit"))
    t = at("2026-07-01T10:00")
    q = Quote(SYMBOL, t, t, dec(15), dec(15), dec(15), 1000, 1000, 1000, dec(10))
    b.on_event(q)
    assert b.submit(SYMBOL, "BUY", 100, 16).status == "REJECTED"
    order = b.submit(SYMBOL, "BUY", 100, 15)
    assert order.active and not b.trades
    b.on_event(replace(q, time=t+timedelta(seconds=5), received=t+timedelta(seconds=5), volume=2000))
    assert order.filled == 100


def test_missing_limits_do_not_fill_a_preexisting_quote_order():
    b = broker(default_rule(SYMBOL))
    t = at("2026-07-01T10:00")
    q = Quote(SYMBOL, t, t, dec(10), dec(10), dec(10), 1000, 1000, 1000, dec(10), dec(11), dec(9))
    b.on_event(q)
    order = b.submit(SYMBOL, "BUY", 100, 10)
    b.on_event(replace(q, time=t+timedelta(seconds=5), received=t+timedelta(seconds=5), volume=2000, upper=dec(0)))
    assert not order.filled and "缺少当日涨跌停" in order.note


def test_china_date_drives_rule_and_t1_even_with_foreign_timezone():
    r = history(status="normal")
    b = broker(r)
    pacific = timezone(timedelta(hours=-8))
    first = replace(bar("2026-07-03"), time=at("2026-07-03T10:00").astimezone(pacific), period="1m")
    b.on_event(first)
    b.submit(SYMBOL, "BUY", 100, 10)
    b.on_event(replace(first, time=first.time + timedelta(minutes=1)))
    assert b.day == "2026-07-03" and b.account.positions[SYMBOL].lots[0].acquired == b.day
    assert b.available_quantity(SYMBOL) == 0


def revision_request(tmp_path, *, verified=True):
    root = tmp_path / "datasets"
    original = write_dataset(root, "待补资料", [bar("2026-07-03"), bar("2026-07-06")], verified=verified)
    meta, digest = read_rule_metadata(root, original["id"])
    rules = deepcopy(meta["rules"])
    rules[SYMBOL] = history()
    return original, {"root": str(root), "stage": str(tmp_path / "stage"), "identity": meta["id"],
                      "source": str(root / (meta["id"] + ".json")), "metadata_sha256": digest, "rules": rules}


def test_revision_preserves_original_and_unverified_rights_flag(tmp_path):
    original, request = revision_request(tmp_path, verified=False)
    from pathlib import Path
    path = Path(request["source"])
    before = path.read_bytes()
    result = stage_rule_revision(request, lambda _: None)
    publish_import(path.parent, request, result)
    assert path.read_bytes() == before
    assert result["meta"]["id"] != original["id"] and result["meta"]["sha256"] == original["sha256"]
    assert not result["meta"]["corporate_actions_verified"]
    assert result["meta"]["parent_dataset"]["metadata_sha256"] == request["metadata_sha256"]
    with pytest.raises(ValueError, match="权益"):
        load_dataset(path.parent, result["meta"]["id"])


def test_revision_rejects_missing_dates_or_concurrent_metadata_change(tmp_path):
    _, request = revision_request(tmp_path)
    request["rules"][SYMBOL] = history(end="2026-07-03")
    with pytest.raises(ValueError, match="缺少证券状态"):
        stage_rule_revision(request, lambda _: None)
    request["metadata_sha256"] = "changed"
    with pytest.raises(ValueError, match="其他任务"):
        stage_rule_revision(request, lambda _: None)


def test_graphical_editor_validates_source_then_saves_independent_revision(qtbot, tmp_path):
    from astock.rule_history_ui import RuleHistoryDialog
    original, _ = revision_request(tmp_path)
    dialog = RuleHistoryDialog(tmp_path, original["id"])
    qtbot.addWidget(dialog)
    dialog.show()
    dialog.add_button.click()
    dialog.save_button.click()
    assert "来源" in dialog.note.text() and dialog.token is None
    dialog.grid.item(0, 6).setText(SOURCE)
    status = dialog.grid.cellWidget(0, 3)
    status.setCurrentIndex(status.findData("risk_warning"))
    dialog.save_button.click()
    qtbot.waitUntil(lambda: bool(dialog.saved_id), timeout=15000)
    meta, _ = load_dataset(tmp_path / "datasets", dialog.saved_id)
    assert meta["rules"][SYMBOL].history[0].status == "risk_warning"
    assert (tmp_path / "datasets" / (original["id"] + ".json")).exists()
