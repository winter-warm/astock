"""Complete current exchange lists. These observations are not historical rules."""
from datetime import date, datetime
from hashlib import sha256
from io import BytesIO
import json
import re
import warnings

from astock.domain import now_cn

SSE = "https://etf.sse.com.cn/fundlist/"
SZSE = "https://fund.szse.cn/marketdata/fundslist/"
SOURCE = "上交所 / 深交所 ETF 官方列表"
LEGACY_SOURCE = "AKShare / 新浪 ETF 列表"
NOTICE = "当前名单观察值；获取时间不是生效日期，不会自动覆盖历史回测或已有账户的规则。"


def valid_reference(value):
    if (not isinstance(value, dict) or set(value) != {"t_plus", "limit_rate", "source", "observed_at", "source_date"}
            or type(value["t_plus"]) is not int or value["t_plus"] not in (0, 1)
            or value["limit_rate"] not in {"0.10", "0.20"} or value["source"] not in {SSE, SZSE}
            or not isinstance(value["observed_at"], str) or not isinstance(value["source_date"], str)
            or datetime.fromisoformat(value["observed_at"]).tzinfo is None):
        raise ValueError("ETF 当前属性格式或来源无效")
    if value["source_date"] and date.fromisoformat(value["source_date"]).isoformat() != value["source_date"]:
        raise ValueError("ETF 来源日期无效")
    return dict(value)


def get_bytes(url, params, referer):
    import requests
    with requests.get(url, params=params, headers={"User-Agent": "Mozilla/5.0", "Referer": referer},
                      timeout=(8, 15), stream=True) as response:
        response.raise_for_status()
        parts, size = [], 0
        for chunk in response.iter_content(65536):
            size += len(chunk)
            if size > 8_000_000:
                raise ValueError("ETF 来源响应超过大小限制")
            parts.append(chunk)
        return b"".join(parts)


def sse_rows(payload):
    if payload.get("actionErrors") or payload.get("fieldErrors"):
        raise ValueError("上交所 ETF 查询返回错误")
    rows, page = payload.get("result"), payload.get("pageHelp", {})
    if (not isinstance(rows, list) or type(page.get("total")) is not int
            or len(rows) != page["total"] or page.get("pageCount") != 1
            or page.get("pageNo") != 1 or page.get("data") != rows or not 1 <= len(rows) < 2000):
        raise ValueError("上交所 ETF 名单为空、被截断或分页未完整；保留原目录")
    return rows


def unique(rows, key):
    result = {}
    for row in rows:
        code = row.get(key)
        if not isinstance(code, str) or not re.fullmatch(r"\d{6}", code) or code in result:
            raise ValueError("ETF 来源包含无效或重复证券代码")
        result[code] = row
    return result


def normalize_exchange(exchange, all_rows, t0_rows, twenty_rows, *, observed, source_date=""):
    if exchange == "SH":
        key, name, listing = "FUND_CODE", "FUND_EXPANSION_ABBR", "LISTING_DATE"
        # Category codes are verified against the exchange's published category tree.
        allowed = {"F111", "F112", "F113", "F114", "F115", "F121", "F122", "F123", "F131", "F141", "F150"}
        whole = unique(all_rows, key)
        for row in all_rows + t0_rows + twenty_rows:
            category = row.get("CATEGORY")
            if not isinstance(category, str) or not category:
                raise ValueError("上交所基金分类缺失")
            if category.startswith("F1") and category not in allowed:
                raise ValueError("上交所新增 ETF 分类，需核对后更新适配器")
        for subset in (t0_rows, twenty_rows):
            for code, row in unique(subset, key).items():
                if code not in whole or any(row.get(k) != whole[code].get(k) for k in (name, listing, "CATEGORY")):
                    raise ValueError("ETF 多份名单的名称、分类或上市日期不一致，请稍后重新获取")
        # The F000 queries include LOF and REITs. Filter each complete list by its explicit category.
        all_rows, t0_rows, twenty_rows = [
            [r for r in rows if r.get("CATEGORY") in allowed] for rows in (all_rows, t0_rows, twenty_rows)]
        source = SSE
    elif exchange == "SZ":
        key, name, listing, source = "基金代码", "基金简称", "上市日期", SZSE
        if any(r.get("基金类别") != "ETF" for rows in (all_rows, t0_rows, twenty_rows) for r in rows):
            raise ValueError("深交所导出混入非 ETF，不能按代码推断基金类别")
        if any(r.get("涨跌幅限制") != "20%" for r in twenty_rows):
            raise ValueError("深交所 20% 名单字段变化")
    else:
        raise ValueError("未知 ETF 交易所")
    all_map, t0, twenty = (unique(rows, key) for rows in (all_rows, t0_rows, twenty_rows))
    if not all_map or not t0 or not twenty or not t0.keys() <= all_map.keys() or not twenty.keys() <= all_map.keys():
        raise ValueError("ETF 属性名单为空或与完整名单不一致，不能把缺失误作 T+1")
    records = []
    for code, row in all_map.items():
        for subset in (t0, twenty):
            if code in subset and (subset[code].get(name) != row.get(name) or subset[code].get(listing) != row.get(listing)):
                raise ValueError("ETF 多份名单的名称或上市日期不一致，请稍后重新获取")
        if not isinstance(row.get(name), str) or not row[name].strip():
            raise ValueError("ETF 来源缺少名称")
        day = row.get(listing, "")
        if not isinstance(day, str) or date.fromisoformat(day).isoformat() != day:
            raise ValueError("ETF 来源缺少有效上市日期")
        reference = valid_reference({"t_plus": 0 if code in t0 else 1, "limit_rate": "0.20" if code in twenty else "0.10",
                                     "source": source, "observed_at": observed, "source_date": source_date})
        records.append({"代码": code + "." + exchange, "名称": row[name].strip(), "上市日期": day,
                        "etf_reference": reference})
    return records


def szse_export(raw, metadata):
    import pandas as pd
    if not raw.startswith(b"PK"):
        raise ValueError("深交所未返回有效 Excel 导出")
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="Workbook contains no default style")
        frame = pd.read_excel(BytesIO(raw), dtype=str).fillna("")
    if len(frame) != metadata.get("recordcount") or not 1 <= len(frame) < 5000:
        raise ValueError("深交所导出条数与公开分页总数不一致；保留原目录")
    return frame.to_dict("records")


def fetch_etfs(progress=lambda _: None, get=get_bytes):
    import pandas as pd
    observed = now_cn().isoformat()
    frames, evidence = [], {"adapter": "exchange-etf-reference-v1", "observed_at": observed, "requests": [], "scope": NOTICE}
    def request(url, params, source):
        raw = get(url, params, source)
        evidence["requests"].append({"url": url, "params": params, "bytes": len(raw), "sha256": sha256(raw).hexdigest()})
        return raw
    base = {"sqlId": "COMMON_JJZWZ_JJLB_L", "isPagination": "true", "CATEGORY": "F000", "CATEGORY_ASC": 1,
            "type": "inParams", "pageHelp.pageSize": 2000, "pageHelp.pageNo": 1, "pageHelp.beginPage": 1,
            "pageHelp.endPage": 1, "pageHelp.cacheSize": 1}
    sh = []
    for index, filters in enumerate(({}, {"SWING_TRADE": "是"}, {"SUBCLASS": "09,31,15"}), 1):
        progress({"phase": f"核对上交所 ETF 名单 {index}/3", "done": index})
        sh.append(sse_rows(json.loads(request("https://query.sse.com.cn/commonQuery.do", {**base, **filters}, SSE))))
    frames.extend(normalize_exchange("SH", *sh, observed=observed))
    sz, source_dates = [], []
    for index, key in enumerate(("tab1", "tab3", "tab2"), 1):
        progress({"phase": f"核对深交所 ETF 名单 {index}/3", "done": index})
        params = {"CATALOGID": "1000_lf", "TABKEY": key, "selectJjlb": "ETF"}
        tabs = json.loads(request("https://www.szse.cn/api/report/ShowReport/data", {**params, "SHOWTYPE": "JSON", "PAGENO": 1}, SZSE))
        selected = [t for t in tabs if t.get("metadata", {}).get("tabkey") == key]
        if len(selected) != 1 or selected[0]["metadata"].get("catalogid") != "1000_lf":
            raise ValueError("深交所 ETF 分表不符合请求")
        meta = selected[0]["metadata"]
        source_dates.append(meta["subname"])
        sz.append(szse_export(request("https://www.szse.cn/api/report/ShowReport", {**params, "SHOWTYPE": "xlsx"}, SZSE), meta))
    if len(set(source_dates)) != 1 or not source_dates[0]:
        raise ValueError("深交所 ETF 名单来源日期不一致")
    frames.extend(normalize_exchange("SZ", *sz, observed=observed, source_date=source_dates[0]))
    evidence["normalized_records"] = frames
    evidence["counts"] = {"SH": sum(r["代码"].endswith("SH") for r in frames), "SZ": sum(r["代码"].endswith("SZ") for r in frames)}
    frame = pd.DataFrame(frames)
    frame.attrs["evidence"] = evidence
    return frame
