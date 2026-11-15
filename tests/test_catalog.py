import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from copy import deepcopy

import pandas as pd
import pytest
from PySide6 import QtCore

from astock.catalog import (add_symbols, catalog_records, empty_catalog, fetch_catalog,
                            load_catalog, normalize_frame, publish_catalog, validate_catalog)
from astock.catalog_ui import CatalogDialog
from astock.data_jobs import data_job_worker
from astock.window import MainWindow


def frame(segment):
    return pd.DataFrame({
        "sh_main": [{"证券代码": "600000", "证券简称": "浦发银行", "上市日期": "1999-11-10"}],
        "sh_star": [{"证券代码": "688001", "证券简称": "华兴源创", "上市日期": "2019-07-22"}],
        "sz": [{"A股代码": 1.0, "A股简称": "平安银行", "A股上市日期": "1991-04-03", "所属行业": "金融业"}],
        "etf": [{"代码": "sh510300", "名称": "沪深300ETF"}, {"代码": "sz159915", "名称": "创业板ETF"}],
    }[segment])


def test_all_sources_normalize_codes_listing_dates_and_do_not_invent_etf_attributes():
    result = fetch_catalog(fetch=frame)
    validate_catalog(result)
    assert len(result["segments"]) == 4
    entries = {r["symbol"]: r for r in catalog_records(result)}
    assert len(entries) == 5  # Full partitions replace the built-in subset.
    assert entries["000001.SZ"]["listing_date"] == "1991-04-03"
    assert entries["000001.SZ"]["industry"] == "金融业"
    assert entries["510300.SH"]["listing_date"] == ""
    assert "t_plus" not in entries["510300.SH"]
    assert all(not x["seed"] for x in entries.values())


@pytest.mark.parametrize("segment,bad", [
    ("sz", pd.DataFrame()),
    ("sh_main", pd.DataFrame([{"证券代码": "830799", "证券简称": "北交所", "上市日期": "2020-01-01"}])),
    ("etf", pd.DataFrame([{"代码": "sz160100", "名称": "LOF基金"}])),
    ("sh_main", pd.DataFrame([{"证券代码": "688001", "证券简称": "分区错误", "上市日期": "2020-01-01"}])),
    ("sz", pd.DataFrame([{"A股代码": "000001", "A股简称": "平安银行", "A股上市日期": "2026-02-31"}])),
    ("etf", pd.DataFrame([{"代码": "sh510300", "名称": "沪深300ETF"}, {"代码": "sh510300", "名称": "冲突"}])),
])
def test_bad_responses_reject_entire_partition(segment, bad):
    with pytest.raises(ValueError):
        normalize_frame(segment, bad)


def test_partial_refresh_keeps_old_partition_timestamp_and_replaces_success_atomically(tmp_path):
    initial = fetch_catalog(fetch=frame)
    current = publish_catalog(tmp_path, empty_catalog(), initial)
    old_sz = deepcopy(current["segments"]["sz"])
    def partial(segment):
        if segment == "sz":
            raise OSError("测试断线")
        result = frame(segment)
        if segment == "sh_main":
            result.loc[0, "证券简称"] = "新的简称"
        return result
    result = fetch_catalog(fetch=partial)
    merged = publish_catalog(tmp_path, current, result)
    stored, warning = load_catalog(tmp_path)
    assert not warning and stored == merged
    assert stored["segments"]["sz"] == old_sz
    assert stored["segments"]["sh_main"]["records"][0]["name"] == "新的简称"
    assert stored["attempts"]["sz"]["error"] == "测试断线"
    assert not list(tmp_path.glob(".securities-*"))


def test_total_failure_and_cancel_do_not_overwrite_existing_cache(tmp_path):
    current = publish_catalog(tmp_path, empty_catalog(), fetch_catalog(fetch=frame))
    before = (tmp_path / "securities.json").read_bytes()
    def fail(segment):
        raise OSError("无网络")
    result = fetch_catalog(fetch=fail)
    merged = publish_catalog(tmp_path, current, result)
    assert merged["segments"] == current["segments"]
    assert (tmp_path / "securities.json").read_bytes() == before


def test_failed_atomic_replace_preserves_old_file_and_cleans_temp(tmp_path, monkeypatch):
    current = publish_catalog(tmp_path, empty_catalog(), fetch_catalog(fetch=frame))
    before = (tmp_path / "securities.json").read_bytes()
    def fail(*args):
        raise OSError("测试磁盘写入失败")
    monkeypatch.setattr("astock.catalog.os.replace", fail)
    with pytest.raises(OSError):
        publish_catalog(tmp_path, current, fetch_catalog(fetch=frame))
    assert (tmp_path / "securities.json").read_bytes() == before
    assert not list(tmp_path.glob(".securities-*"))


def test_bad_cache_is_not_presented_as_fresh_data(tmp_path):
    (tmp_path / "securities.json").write_text('{"version":1,"segments":{"sz":{}}}', encoding="utf-8")
    value, warning = load_catalog(tmp_path)
    assert "无法读取" in warning
    assert value == empty_catalog()
    assert all(r["seed"] and not r["refreshed_at"] for r in catalog_records(value))


def test_real_source_edge_codes_do_not_reject_other_valid_listings():
    star = pd.concat([frame("sh_star"), pd.DataFrame([{
        "证券代码": "689009", "证券简称": "九号公司-WD", "上市日期": "2020-10-29"}])])
    assert [r["symbol"] for r in normalize_frame("sh_star", star)] == ["688001.SH"]
    sz = pd.concat([frame("sz"), pd.DataFrame([{
        "A股代码": "302132", "A股简称": "中航成飞", "A股上市日期": "2010-08-27", "所属行业": "制造业"}])])
    entries = normalize_frame("sz", sz)
    assert entries[-1]["board"] == "chinext"
    with pytest.raises(ValueError, match="不支持"):
        add_symbols("", [entries[-1]])  # Directory presence must not invent an engine rule.


def test_watchlist_deduplicates_and_rejects_over_limit_without_modification():
    entries = catalog_records(fetch_catalog(fetch=frame))
    assert add_symbols("SH600000，000001", entries[:1]) == "600000.SH,000001.SZ"
    current = ",".join(f"600{i:03}.SH" for i in range(20))
    with pytest.raises(ValueError, match="最多"):
        add_symbols(current, [next(e for e in entries if e["symbol"] == "159915.SZ")])


def test_worker_catalog_dispatch_uses_provider_in_isolated_worker(monkeypatch):
    from queue import Queue
    monkeypatch.setattr("astock.catalog.fetch_catalog", lambda progress: fetch_catalog(progress, frame))
    messages = Queue()
    data_job_worker(messages, "catalog", {})
    result = None
    while not messages.empty():
        result = messages.get_nowait()
    assert result["type"] == "finished" and len(result["result"]["segments"]) == 4


def test_offline_search_name_code_type_and_addition_persist_watchlist(qtbot, tmp_path):
    publish_catalog(tmp_path, empty_catalog(), fetch_catalog(fetch=frame))
    window = MainWindow(tmp_path, start_workers=False)
    qtbot.addWidget(window)
    window.symbol_input.setText("")
    dialog = CatalogDialog(tmp_path, window.add_catalog_symbols, window)
    qtbot.addWidget(dialog)
    dialog.show()
    dialog.search.setText("平安")
    assert dialog.proxy.rowCount() == 1
    dialog.table.selectRow(0)
    qtbot.mouseClick(dialog.add_button, QtCore.Qt.MouseButton.LeftButton)
    assert window.symbols() == ["000001.SZ"]
    assert window.store.setting("watchlist") == "000001.SZ"
    dialog.search.setText("sh510300")
    assert dialog.proxy.rowCount() == 1
    dialog.category.setCurrentIndex(1)
    assert dialog.proxy.rowCount() == 0 and not dialog.add_button.isEnabled()
    dialog.category.setCurrentIndex(2)
    dialog.table.selectRow(0)
    assert "保守 T+1" in dialog.details.toPlainText()
    window.connected = True
    qtbot.mouseClick(dialog.add_button, QtCore.Qt.MouseButton.LeftButton)
    assert "重新连接" in dialog.status.text()
    assert window.symbols() == ["000001.SZ", "510300.SH"]
    dialog.close()
    window.close()
    reopened = MainWindow(tmp_path, start_workers=False)
    qtbot.addWidget(reopened)
    assert reopened.symbols() == ["000001.SZ", "510300.SH"]


def test_cancel_ignores_old_results_and_closing_stops_worker(qtbot, tmp_path):
    dialog = CatalogDialog(tmp_path, lambda entries: "", None)
    qtbot.addWidget(dialog)
    dialog.show()
    dialog.token = "old"
    dialog.cancel()
    dialog.receive({"token": "old", "type": "finished", "result": fetch_catalog(fetch=frame)})
    assert not (tmp_path / "securities.json").exists()
    # A real spawn is immediately closed: no network work or completion is required.
    dialog.refresh()
    process = dialog.jobs.active["catalog"]["process"]
    dialog.close()
    assert not process.is_alive() and not dialog.jobs.active
    assert not (tmp_path / "securities.json").exists()


def test_partial_failure_and_empty_search_are_visible_without_modal_error(qtbot, tmp_path):
    dialog = CatalogDialog(tmp_path, lambda entries: "", None)
    qtbot.addWidget(dialog)
    def partial(segment):
        if segment != "etf":
            raise OSError("测试失败")
        return frame(segment)
    dialog.token = "current"
    dialog.receive({"token": "current", "type": "finished", "result": fetch_catalog(fetch=partial)})
    assert "已更新 1 个分区" in dialog.status.text() and "失败" in dialog.status.text()
    assert "深市 A 股：未下载" in dialog.sources.text()
    dialog.search.setText("没有这个证券")
    assert "没有结果" in dialog.count.text()


def test_name_search_ignores_exchange_spacing_and_full_width_letters(qtbot, tmp_path):
    def source(segment):
        value = frame(segment)
        if segment == "sz":
            value.loc[0, "A股简称"] = "万  科Ａ"
        return value
    publish_catalog(tmp_path, empty_catalog(), fetch_catalog(fetch=source))
    dialog = CatalogDialog(tmp_path, lambda entries: "", None)
    qtbot.addWidget(dialog)
    dialog.search.setText("万科A")
    assert dialog.proxy.rowCount() == 1
    dialog.table.selectRow(0)
    assert dialog.selected()[0]["name"] == "万  科Ａ"  # Preserve the original display name.
