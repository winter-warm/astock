import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from copy import deepcopy
from io import BytesIO
import json
from pathlib import Path

import pandas as pd
import pytest

from astock.catalog import (empty_catalog, fetch_catalog, load_catalog, publish_catalog,
                            validate_catalog)
from astock.catalog_ui import CatalogDialog
from astock.etf_reference import (LEGACY_SOURCE, SOURCE, fetch_etfs, normalize_exchange,
                                  sse_rows, szse_export, valid_reference)
from astock.rules import default_rule

FIXTURE = json.loads((Path(__file__).parent / "fixtures/exchange-etf-reference.json").read_text(encoding="utf-8"))


def response_get(url, params, referer):
    """Small real excerpts with explicit synthetic pagination for adapter tests."""
    if "sse.com.cn" in url:
        index = 1 if "SWING_TRADE" in params else 2 if "SUBCLASS" in params else 0
        rows = FIXTURE["SH"][index]
        return json.dumps({"result": rows, "pageHelp": {"total": len(rows), "pageCount": 1,
                                                       "pageNo": 1, "data": rows}}).encode()
    key = params["TABKEY"]
    rows = FIXTURE["SZ"][("tab1", "tab3", "tab2").index(key)]
    assert params["selectJjlb"] == "ETF"
    if url.endswith("/data"):
        return json.dumps([{"metadata": {"tabkey": key, "catalogid": "1000_lf", "recordcount": len(rows),
                                         "subname": FIXTURE["source_date"]}}]).encode()
    buffer = BytesIO()
    pd.DataFrame(rows).to_excel(buffer, index=False)
    return buffer.getvalue()


def source_frame():
    return fetch_etfs(get=response_get)


def catalog():
    def fetch(segment):
        if segment != "etf":
            raise OSError("本测试只提供 ETF 分区")
        return source_frame()
    return fetch_catalog(fetch=fetch)


def test_actual_exchange_excerpts_classify_t0_t1_and_twenty_without_lof():
    records = source_frame().to_dict("records")
    values = {r["代码"]: (r["etf_reference"]["t_plus"], r["etf_reference"]["limit_rate"]) for r in records}
    assert values == {"510300.SH": (1, "0.10"), "520880.SH": (0, "0.10"),
                      "530060.SH": (1, "0.10"), "551300.SH": (0, "0.10"), "588000.SH": (1, "0.20"),
                      "158000.SZ": (0, "0.10"), "158001.SZ": (1, "0.10"),
                      "158011.SZ": (1, "0.20"), "159915.SZ": (1, "0.20")}
    for r in records:
        assert default_rule(r["代码"]).kind == "etf"


@pytest.mark.parametrize("bad", ["empty", "duplicate", "not_subset", "missing_category", "new_category", "mismatched_category", "wrong_date"])
def test_malformed_exchange_lists_never_become_default_t1(bad):
    rows = deepcopy(FIXTURE["SH"])
    if bad == "empty":
        rows[1] = []
    elif bad == "duplicate":
        rows[1].append(deepcopy(rows[1][0]))
    elif bad == "not_subset":
        rows[1][0]["FUND_CODE"] = "599999"
    elif bad == "missing_category":
        rows[0][0].pop("CATEGORY")
    elif bad == "new_category":
        rows[0][0]["CATEGORY"] = "F199"
    elif bad == "mismatched_category":
        rows[1][0]["CATEGORY"] = "F211"
    else:
        rows[1][0]["LISTING_DATE"] = "2026-11-01"
    with pytest.raises(ValueError):
        normalize_exchange("SH", *rows, observed=FIXTURE["observed"])


@pytest.mark.parametrize("change", ["empty", "truncated", "page", "data", "error"])
def test_sse_incomplete_pagination_is_rejected(change):
    payload = json.loads(response_get("https://query.sse.com.cn/", {}, ""))
    if change == "empty":
        payload["result"] = []
    elif change == "truncated":
        payload["pageHelp"]["total"] += 1
    elif change == "page":
        payload["pageHelp"]["pageCount"] = 2
    elif change == "data":
        payload["pageHelp"]["data"] = []
    else:
        payload["actionErrors"] = ["error"]
    with pytest.raises(ValueError):
        sse_rows(payload)


def test_sz_export_count_non_etf_and_mixed_source_date_fail_closed():
    raw = response_get("https://www.szse.cn/ShowReport", {"TABKEY": "tab1", "selectJjlb": "ETF"}, "")
    with pytest.raises(ValueError, match="条数"):
        szse_export(raw, {"recordcount": 5})
    rows = deepcopy(FIXTURE["SZ"])
    rows[0][0]["基金类别"] = "LOF"
    with pytest.raises(ValueError, match="非 ETF"):
        normalize_exchange("SZ", *rows, observed=FIXTURE["observed"])
    def mixed_date(url, params, referer):
        raw = response_get(url, params, referer)
        if params.get("TABKEY") == "tab2" and url.endswith("/data"):
            parsed = json.loads(raw)
            parsed[0]["metadata"]["subname"] = "2026-11-12"
            return json.dumps(parsed).encode()
        return raw
    with pytest.raises(ValueError, match="日期不一致"):
        fetch_etfs(get=mixed_date)


def test_refresh_persists_reference_and_does_not_mutate_rules_or_old_cache(tmp_path):
    result = catalog()
    assert result["segments"]["etf"]["source"] == SOURCE
    before = default_rule("158000.SZ")
    stored = publish_catalog(tmp_path, empty_catalog(), result)
    reopened, warning = load_catalog(tmp_path)
    assert not warning and reopened == stored
    assert default_rule("158000.SZ") == before
    assert default_rule("158000.SZ").t_plus == 1  # Current reference is not historical evidence.
    etf = stored["segments"]["etf"]
    assert len(etf["evidence"]["requests"]) == 9
    assert len(etf["records"]) == 9
    old_bytes = (tmp_path / "securities.json").read_bytes()
    def incomplete(_):
        raise ValueError("ETF 名单未完整")
    failed = fetch_catalog(fetch=incomplete)
    publish_catalog(tmp_path, stored, failed)
    assert (tmp_path / "securities.json").read_bytes() == old_bytes


def test_legacy_cache_remains_usable_and_cannot_mislabel_reference(tmp_path):
    result = catalog()
    part = result["segments"]["etf"]
    part["source"] = LEGACY_SOURCE
    part.pop("evidence")
    for r in part["records"]:
        r.pop("etf_reference")
    publish_catalog(tmp_path, empty_catalog(), result)
    reopened, warning = load_catalog(tmp_path)
    assert not warning and reopened == result
    part["source"] = SOURCE
    with pytest.raises(ValueError):
        validate_catalog(result)


def test_attribute_tampering_and_wrong_exchange_do_not_load_as_valid(tmp_path):
    result = catalog()
    changed = deepcopy(result)
    changed["segments"]["etf"]["records"][0]["etf_reference"]["t_plus"] = 1
    with pytest.raises(ValueError, match="留存不一致"):
        validate_catalog(changed)
    changed = deepcopy(result)
    ref = changed["segments"]["etf"]["records"][0]["etf_reference"]
    ref["source"] = "https://etf.sse.com.cn/fundlist/"
    with pytest.raises(ValueError, match="交易所不一致"):
        validate_catalog(changed)
    bad = deepcopy(ref)
    bad["observed_at"] = "2026-11-14T12:00:00"
    with pytest.raises(ValueError):
        valid_reference(bad)


def test_gui_reference_default_difference_and_readonly_history_view(qtbot, tmp_path):
    publish_catalog(tmp_path, empty_catalog(), catalog())
    calls = []
    dialog = CatalogDialog(tmp_path, calls.append, reference_only=True)
    qtbot.addWidget(dialog)
    dialog.show()
    dialog.search.setText("158000")
    assert dialog.proxy.rowCount() == 1
    dialog.table.selectRow(0)
    detail = dialog.details.toPlainText()
    assert "交易所当前名单：T+0" in detail and "默认模拟设置：T+1" in detail
    assert "获取时间不是生效日期" in detail and "名单日期：2026-11-13" in detail
    assert not dialog.add_button.isVisible()
    dialog.table.doubleClicked.emit(dialog.proxy.index(0, 0))
    assert calls == []
    dialog.search.setText("158011")
    dialog.table.selectRow(0)
    assert "涨跌幅 20%" in dialog.details.toPlainText()
    dialog.close()
