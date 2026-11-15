"""Current security directory. Never used as a historical trading-rule database."""
from __future__ import annotations

from datetime import date, datetime
import json
import os
from pathlib import Path
import re
import tempfile

from astock.domain import now_cn, symbol_code
from astock.etf_reference import LEGACY_SOURCE, SOURCE, SSE, SZSE, fetch_etfs, valid_reference
from astock.rules import NAMES, default_rule

SEGMENTS = {"sh_main": "沪市主板 A 股", "sh_star": "科创板", "sz": "深市 A 股", "etf": "场内 ETF"}
SOURCES = {
    "sh_main": "AKShare / 上交所", "sh_star": "AKShare / 上交所",
    "sz": "AKShare / 深交所", "etf": SOURCE,
}
BOARD_NAMES = {"main": "主板", "star": "科创板", "chinext": "创业板", "etf": "ETF"}


def empty_catalog():
    return {"version": 1, "segments": {}, "attempts": {}}


def _text(value):
    value = str(value).strip()
    return "" if value.lower() in {"nan", "nat", "none", "<na>", "-"} else value


def _record(symbol, name, kind, listing_date="", industry=""):
    code, exchange = symbol.split(".")
    if kind == "etf":
        allowed = (exchange == "SH" and code.startswith(("51", "52", "53", "55", "56", "58"))) or (
            exchange == "SZ" and code.startswith(("158", "159")))
        board = "etf"
    else:
        allowed = (exchange == "SH" and code.startswith(("600", "601", "603", "605", "688"))) or (
            exchange == "SZ" and code.startswith(("000", "001", "002", "003", "300", "301", "302")))
        board = "star" if code.startswith("688") else "chinext" if code.startswith(("300", "301", "302")) else "main"
    if not allowed or not name or len(name) > 120:
        raise ValueError(f"目录中出现无效的证券代码或名称：{symbol}")
    if listing_date:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", listing_date):
            raise ValueError(f"上市日期格式不正确：{symbol}")
        date.fromisoformat(listing_date)
    return {"symbol": symbol, "name": name, "kind": kind, "board": board,
            "listing_date": listing_date, "industry": industry}


def normalize_frame(segment, frame):
    """Reject a bad response as a whole; a failed refresh cannot truncate a cache."""
    if segment not in SEGMENTS:
        raise ValueError("未知证券目录分区")
    columns = {"sh_main": ("证券代码", "证券简称", "上市日期"),
               "sh_star": ("证券代码", "证券简称", "上市日期"),
               "sz": ("A股代码", "A股简称", "A股上市日期"),
               "etf": ("代码", "名称", "上市日期" if "上市日期" in frame.columns else None)}[segment]
    if any(c not in frame.columns for c in columns if c):
        raise ValueError("行情源目录字段发生变化，保留上次目录")
    if frame.empty or len(frame) >= (5000 if segment == "etf" else 10000):
        raise ValueError("目录为空或达到接口条数上限，无法确认完整性")
    records = {}
    for row in frame.to_dict("records"):
        code = _text(row[columns[0]])
        # Stock-list adapters can expose Excel numeric codes. Do not truncate
        # decimal quantities or infer arbitrary exchange codes.
        if re.fullmatch(r"\d{1,6}(?:\.0)?", code):
            code = code.removesuffix(".0").zfill(6)
        symbol = symbol_code(code)
        if segment == "sh_star" and symbol.startswith("689") and symbol.endswith(".SH"):
            continue  # SSE also includes CDRs; this directory is limited to A shares and ETFs.
        listing = _text(row[columns[2]]) if columns[2] else ""
        if re.fullmatch(r"\d{4}-\d{2}-\d{2} 00:00:00", listing):
            listing = listing[:10]
        entry = _record(symbol, _text(row[columns[1]]), "etf" if segment == "etf" else "stock",
                        listing, _text(row.get("所属行业", "")))
        if segment == "etf" and "etf_reference" in row:
            entry["etf_reference"] = valid_reference(row["etf_reference"])
            if entry["etf_reference"]["source"] != (SSE if symbol.endswith(".SH") else SZSE):
                raise ValueError("ETF 属性来源与交易所不一致")
        if (segment == "sh_main" and (not symbol.endswith(".SH") or entry["board"] != "main")
                or segment == "sh_star" and entry["board"] != "star"
                or segment == "sz" and not symbol.endswith(".SZ")):
            raise ValueError(f"证券与目录分区不一致：{symbol}")
        if symbol in records and records[symbol] != entry:
            raise ValueError(f"目录中同一证券资料冲突：{symbol}")
        records[symbol] = entry
    if not records:
        raise ValueError("目录没有适用的 A 股或场内 ETF")
    return sorted(records.values(), key=lambda x: x["symbol"])


def fetch_catalog(progress=lambda _: None, fetch=None):
    """One user-requested refresh; isolate provider imports and timeouts in a worker."""
    if fetch is None:
        import akshare as ak
        from akshare.utils.context import config
        config.timeout = (5, 15)
        calls = {
            "sh_main": lambda: ak.stock_info_sh_name_code(symbol="主板A股"),
            "sh_star": lambda: ak.stock_info_sh_name_code(symbol="科创板"),
            "sz": lambda: ak.stock_info_sz_name_code(symbol="A股列表"),
            "etf": lambda: fetch_etfs(progress),
        }
        def fetch(segment):
            return calls[segment]()
    result = empty_catalog()
    for index, segment in enumerate(SEGMENTS):
        progress({"phase": "正在获取" + SEGMENTS[segment], "done": index, "total": len(SEGMENTS)})
        at = now_cn().isoformat()
        try:
            frame = fetch(segment)
            records = normalize_frame(segment, frame)
            part = {"source": SOURCES[segment], "refreshed_at": at, "records": records,
                    "excluded_count": len(frame) - len(records)}
            if segment == "etf":
                if "etf_reference" in frame.columns:
                    part["evidence"] = frame.attrs.get("evidence")
                    validate_etf_evidence(part)
                else:
                    part["source"] = LEGACY_SOURCE
            result["segments"][segment] = part
            result["attempts"][segment] = {"at": at, "error": ""}
        except Exception as error:
            result["attempts"][segment] = {"at": at, "error": str(error)[:800]}
    return result


def validate_etf_evidence(part):
    """Bind cached attributes to the complete observations used for this refresh."""
    evidence = part.get("evidence")
    if (not isinstance(evidence, dict) or evidence.get("adapter") != "exchange-etf-reference-v1"
            or not isinstance(evidence.get("requests"), list) or len(evidence["requests"]) != 9
            or not isinstance(evidence.get("normalized_records"), list)):
        raise ValueError("ETF 当前名单缺少来源留存")
    for request in evidence["requests"]:
        if (not isinstance(request, dict) or not isinstance(request.get("params"), dict)
                or type(request.get("bytes")) is not int or not 0 < request["bytes"] <= 8_000_000
                or not isinstance(request.get("sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", request["sha256"])):
            raise ValueError("ETF 名单来源摘要不完整")
    observations = evidence["normalized_records"]
    expected = [{"代码": r["symbol"], "名称": r["name"], "上市日期": r["listing_date"],
                 "etf_reference": r.get("etf_reference")} for r in part["records"]]
    if sorted(observations, key=lambda r: r["代码"]) != sorted(expected, key=lambda r: r["代码"]):
        raise ValueError("ETF 当前属性与来源留存不一致")
    counts = {key: sum(r["symbol"].endswith(key) for r in part["records"]) for key in ("SH", "SZ")}
    if evidence.get("counts") != counts or not all(counts.values()):
        raise ValueError("ETF 沪深名单不完整")
    if any(r.get("etf_reference", {}).get("observed_at") != evidence.get("observed_at") for r in part["records"]):
        raise ValueError("ETF 名单获取时间不一致")


def validate_catalog(value):
    if not isinstance(value, dict) or value.get("version") != 1:
        raise ValueError("证券目录版本无法识别")
    if not isinstance(value.get("segments"), dict) or not isinstance(value.get("attempts"), dict):
        raise ValueError("证券目录结构不完整")
    all_symbols = set()
    for key, part in value["segments"].items():
        if (not isinstance(part, dict) or key not in SEGMENTS
                or part["source"] not in ({SOURCE, LEGACY_SOURCE} if key == "etf" else {SOURCES[key]})):
            raise ValueError("证券目录来源不正确")
        if datetime.fromisoformat(part["refreshed_at"]).tzinfo is None:
            raise ValueError("目录更新时间缺少时区")
        if not isinstance(part["records"], list) or not 1 <= len(part["records"]) < 10000:
            raise ValueError("证券目录条数异常")
        for record in part["records"]:
            if not isinstance(record, dict) or any(not isinstance(record.get(field), str) for field in (
                    "symbol", "name", "kind", "board", "listing_date", "industry")):
                raise ValueError("证券资料字段类型不正确")
            symbol = symbol_code(record["symbol"])
            if symbol != record["symbol"] or symbol in all_symbols:
                raise ValueError("证券代码重复或格式不正确")
            expected = _record(symbol, record["name"], "etf" if key == "etf" else "stock",
                               record["listing_date"], record["industry"])
            if key == "etf" and part["source"] == SOURCE:
                expected["etf_reference"] = valid_reference(record.get("etf_reference"))
                if expected["etf_reference"]["source"] != (SSE if symbol.endswith(".SH") else SZSE):
                    raise ValueError("ETF 属性来源与交易所不一致")
            if record != expected or (key == "sh_main" and (expected["board"] != "main" or not symbol.endswith(".SH"))
                    or key == "sh_star" and expected["board"] != "star"
                    or key == "sz" and not symbol.endswith(".SZ")):
                raise ValueError("证券资料与目录分区不一致")
            all_symbols.add(symbol)
        if key == "etf" and part["source"] == SOURCE:
            validate_etf_evidence(part)
    for key, attempt in value["attempts"].items():
        if not isinstance(attempt, dict) or key not in SEGMENTS or not isinstance(attempt["error"], str):
            raise ValueError("目录刷新记录不正确")
        if datetime.fromisoformat(attempt["at"]).tzinfo is None:
            raise ValueError("刷新记录缺少时区")
    return value


def load_catalog(root):
    path = Path(root) / "securities.json"
    if not path.exists():
        return empty_catalog(), "尚未下载目录；当前只显示内置常用证券，点击「更新目录」获取更多。"
    try:
        if path.stat().st_size > 12_000_000:
            raise ValueError("文件超出目录大小限制")
        return validate_catalog(json.loads(path.read_text(encoding="utf-8"))), ""
    except (ValueError, KeyError, TypeError, OSError) as error:
        return empty_catalog(), f"本机目录无法读取：{error}。当前使用内置常用证券，可重新更新。"


def publish_catalog(root, current, result):
    validate_catalog(result)
    merged = {"version": 1, "segments": {**current["segments"], **result["segments"]},
              "attempts": {**current["attempts"], **result["attempts"]}}
    validate_catalog(merged)
    if not result["segments"]:
        return merged  # Preserve the last usable file even on total provider failure.
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".securities-", suffix=".json", dir=root)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(merged, stream, ensure_ascii=False, separators=(",", ":"))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, root / "securities.json")
    finally:
        Path(temporary).unlink(missing_ok=True)
    return merged


def catalog_records(value):
    entries = {}
    for segment, part in value["segments"].items():
        for record in part["records"]:
            entries[record["symbol"]] = {**record, "source": part["source"], "refreshed_at": part["refreshed_at"],
                                          "segment": segment, "seed": False}
    # Seeds supplement only missing partitions, never resurrect a removed listing.
    for symbol, name in NAMES.items():
        rule = default_rule(symbol)
        segment = "etf" if rule.kind == "etf" else "sz" if symbol.endswith(".SZ") else "sh_main"
        if segment not in value["segments"]:
            entries[symbol] = {**_record(symbol, name, rule.kind), "source": "内置常用证券（非完整目录）",
                               "refreshed_at": "", "segment": segment, "seed": True}
    return sorted(entries.values(), key=lambda x: x["symbol"])


def add_symbols(current_text, entries):
    current = [symbol_code(s) for s in re.split(r"[,，;；\s]+", current_text) if s]
    for entry in entries:
        default_rule(entry["symbol"], entry["name"])
    merged = list(dict.fromkeys(current + [entry["symbol"] for entry in entries]))
    if len(merged) > 20:
        raise ValueError(f"加入后共有 {len(merged)} 个标的；最多同时关注 20 个，请先移除部分代码。")
    return ",".join(merged)
