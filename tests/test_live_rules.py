from copy import deepcopy
from datetime import datetime, timedelta

import pytest

from astock.broker import Broker
from astock.domain import CN, MatchConfig, Quote, dec
from astock.live_rules import build_live_rules
from astock.rules import default_rule, rule_at
from test_etf_reference import catalog

AT = datetime(2026, 11, 13, 10, tzinfo=CN)


def dated_catalog():
    """Actual field samples, with synthetic observation times for boundary tests."""
    value = catalog()
    part = value["segments"]["etf"]
    stamp = (AT - timedelta(minutes=10)).isoformat()
    part["refreshed_at"] = stamp
    part["evidence"]["observed_at"] = stamp
    for row in part["records"] + part["evidence"]["normalized_records"]:
        row["etf_reference"]["observed_at"] = stamp
    return value


def test_observation_applies_only_today_and_preserves_original_rules_and_evidence():
    value = dated_catalog()
    original = deepcopy(value)
    rules, audit = build_live_rules(["158000", "158011", "600000"], value, AT)
    assert rule_at(rules["158000.SZ"], "2026-11-13").t_plus == 0
    assert rule_at(rules["158011.SZ"], "2026-11-13").limit_rate == dec(".20")
    assert rule_at(rules["158000.SZ"], "2026-11-12").status == "unknown"
    assert rule_at(rules["158000.SZ"], "2026-11-16").status == "unknown"
    assert default_rule("158000").t_plus == 1
    assert not rules["600000.SH"].history
    assert value == original and len(audit["source_requests"]) == 9
    value["segments"]["etf"]["records"][0]["name"] = "later edit"
    assert audit["records"][0]["name"] != "later edit"


@pytest.mark.parametrize("offset", [timedelta(hours=7), timedelta(days=1), -timedelta(seconds=1)])
def test_stale_cross_day_and_future_observations_are_rejected(offset):
    value = dated_catalog()
    observed = datetime.fromisoformat(value["segments"]["etf"]["evidence"]["observed_at"])
    with pytest.raises(ValueError, match="近 6 小时"):
        build_live_rules(["158000"], value, observed + offset)


def test_current_day_source_date_required_and_weekends_use_last_session():
    value = dated_catalog()
    part = value["segments"]["etf"]
    saturday = AT + timedelta(days=1)
    stamp = saturday.isoformat()
    part["evidence"]["observed_at"] = stamp
    for row in part["records"] + part["evidence"]["normalized_records"]:
        row["etf_reference"]["observed_at"] = stamp
    assert build_live_rules(["158000"], value, saturday)[1]["valid_day"] == "2026-11-14"
    monday = AT + timedelta(days=3)
    stamp = monday.isoformat()
    part["evidence"]["observed_at"] = stamp
    for row in part["records"] + part["evidence"]["normalized_records"]:
        row["etf_reference"]["observed_at"] = stamp
    with pytest.raises(ValueError, match="尚未更新到 2026-11-16"):
        build_live_rules(["158000"], value, monday)


def test_fresh_t0_rule_allows_intraday_sell_and_next_day_blocks_orders():
    rules, _ = build_live_rules(["158000"], dated_catalog(), AT)
    broker = Broker(rules, config=MatchConfig(participation=dec(1), slippage_ticks=0))
    def quote(seconds):
        at = AT + timedelta(seconds=seconds)
        return Quote("158000.SZ", at, at, dec(10), dec(10), dec(10), 100000, 100000,
                     100000 + seconds * 100, dec(10), dec(11), dec(9))
    broker.on_event(quote(0))
    buy = broker.submit("158000.SZ", "BUY", 100, 10)
    broker.on_event(quote(5))
    assert buy.status == "FILLED" and broker.available_quantity("158000.SZ") == 100
    sell = broker.submit("158000.SZ", "SELL", 100, 10)
    broker.on_event(quote(10))
    assert sell.status == "FILLED"
    broker.on_event(quote(3 * 86400))
    refused = broker.submit("158000.SZ", "BUY", 100, 10)
    assert refused.status == "REJECTED"
    broker.check_invariants()


def test_stock_only_does_not_require_etf_catalog_and_missing_etf_is_not_guessed():
    empty = {"version": 1, "segments": {}, "attempts": {}}
    assert build_live_rules(["600000"], empty, AT)[0]["600000.SH"].t_plus == 1
    with pytest.raises(ValueError, match="更新证券目录"):
        build_live_rules(["158000"], empty, AT)
    with pytest.raises(ValueError, match="不在当前 ETF 名单"):
        build_live_rules(["158999"], dated_catalog(), AT)
