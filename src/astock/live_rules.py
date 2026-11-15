"""Date-bounded rule observations for newly configured live paper accounts."""
from copy import deepcopy
from datetime import datetime, timedelta
import hashlib
import json

from astock.catalog import load_catalog, validate_catalog
from astock.domain import CN, RulePeriod, dec, symbol_code
from astock.etf_reference import SOURCE
from astock.rules import default_rule, validate_rule
from astock.trading_calendar import trading_day

MAX_REFERENCE_AGE = timedelta(hours=6)
VERSION = "live-etf-observation-v1"


def reference_day(day):
    for _ in range(32):
        open_day = trading_day(day)
        if open_day is None:
            raise ValueError("当前日期超出已核对交易日历，无法确认 ETF 名单日期")
        if open_day:
            return day.isoformat()
        day -= timedelta(days=1)
    raise ValueError("无法确定 ETF 名单对应交易日")


def build_live_rules(symbols, catalog, at):
    if at.tzinfo is None:
        raise ValueError("在线规则时间缺少时区")
    at = at.astimezone(CN)
    day = at.date().isoformat()
    rules = {symbol_code(s): default_rule(s) for s in symbols}
    etfs = {s for s, r in rules.items() if r.kind == "etf"}
    audit = {"version": VERSION, "created_at": at.isoformat(), "valid_day": day,
             "scope": "当日实时仿真的当前观察值；不证明此前历史规则，跨日须重新核对。", "records": []}
    if not etfs:
        return rules, audit
    validate_catalog(catalog)
    part = catalog["segments"].get("etf")
    if not part or part["source"] != SOURCE:
        raise ValueError("请先更新证券目录，取得沪深交易所 ETF 当前规则资料")
    entries = {r["symbol"]: r for r in part["records"]}
    source_day = reference_day(at.date())
    for symbol in sorted(etfs):
        if symbol not in entries:
            raise ValueError(f"{symbol} 不在当前 ETF 名单中，请更新目录或核对代码")
        entry = entries[symbol]
        reference = entry["etf_reference"]
        observed = datetime.fromisoformat(reference["observed_at"]).astimezone(CN)
        if observed.date() != at.date() or not timedelta(0) <= at - observed <= MAX_REFERENCE_AGE:
            raise ValueError(f"{symbol} 的 ETF 资料不是当日近 6 小时获取，请更新目录")
        if reference["source_date"] and reference["source_date"] != source_day:
            raise ValueError(f"{symbol} 来源名单日期为 {reference['source_date']}，尚未更新到 {source_day}")
        if entry["listing_date"] > day:
            raise ValueError(f"{symbol} 尚未到上市日期")
        rule = rules[symbol]
        rule.name = entry["name"]
        rule.history = [RulePeriod(day, day, reference["source"], t_plus=reference["t_plus"],
                                   limit_rate=dec(reference["limit_rate"]))]
        rule.known_from[day] = at
        validate_rule(rule)
        audit["records"].append(deepcopy(entry))
    evidence = part["evidence"]
    audit["source_requests"] = deepcopy(evidence["requests"])
    audit["catalog_sha256"] = hashlib.sha256(json.dumps(part, ensure_ascii=False, sort_keys=True,
                                                        separators=(",", ":")).encode()).hexdigest()
    return rules, audit


def read_live_rules(root, symbols, at):
    catalog, warning = load_catalog(root)
    if warning and any(default_rule(s).kind == "etf" for s in symbols):
        raise ValueError(warning)
    return build_live_rules(symbols, catalog, at)


def prepare_live_catalog(root, symbols, progress):
    from astock.catalog import empty_catalog, normalize_frame
    from astock.domain import now_cn
    from astock.etf_reference import fetch_etfs
    try:
        _, audit = read_live_rules(root, symbols, now_cn())
        return {"catalog": None, "valid_day": audit["valid_day"]}
    except ValueError:
        progress({"phase": "获取当日 ETF 规则资料"})
    frame = fetch_etfs(progress)
    result = empty_catalog()
    at = now_cn()
    result["segments"]["etf"] = {"source": SOURCE, "refreshed_at": at.isoformat(),
                                  "records": normalize_frame("etf", frame), "excluded_count": 0,
                                  "evidence": frame.attrs["evidence"]}
    result["attempts"]["etf"] = {"at": at.isoformat(), "error": ""}
    _, audit = build_live_rules(symbols, result, at)
    return {"catalog": result, "valid_day": audit["valid_day"]}


def extend_live_rules(existing, incoming):
    """Append a new observed day without rewriting previously used intervals."""
    if set(existing) != set(incoming):
        raise ValueError("更新规则不能改变账户标的")
    merged = deepcopy(existing)
    for symbol, new in incoming.items():
        if new.kind != "etf":
            continue
        period = new.history[0]
        old = merged[symbol]
        same = next((p for p in old.history if p.start <= period.start <= p.end), None)
        if same:
            if same != period:
                raise ValueError(f"{symbol} 当日规则与已使用版本不同，不能改写已运行依据")
            continue
        if old.history and period.start <= old.history[-1].end:
            raise ValueError("不能将新观察值回填到过去日期")
        old.history.append(period)
        old.known_from[period.start] = new.known_from[period.start]
        validate_rule(old)
    return merged
