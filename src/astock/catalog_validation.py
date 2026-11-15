"""Native-window acceptance for source and frozen Windows builds."""
import json
from pathlib import Path
import time

from PySide6 import QtCore, QtTest

from astock.catalog_ui import CatalogDialog


def start_catalog_smoke(application, window, screenshot=None, refresh=False):
    output = Path(screenshot).parent if screenshot else window.root / "reports" / "catalog-check"
    output.mkdir(parents=True, exist_ok=True)
    dialog = CatalogDialog(window.root, window.add_catalog_symbols, window)
    dialog.show()
    started = time.perf_counter()
    beats, searches = [], []
    state = {"stage": "waiting", "last": started}
    timer = QtCore.QTimer(application)
    result = {}

    def finish(error=""):
        timer.stop()
        result.update({"error": error, "passed": not error, "searches": searches,
                       "device_pixel_ratio": dialog.devicePixelRatioF(),
                       "window": [dialog.width(), dialog.height()],
                       "timer_max_gap_ms": round(max(beats, default=0) * 1000, 2),
                       "records": dialog.model.rowCount(), "network_refresh_requested": refresh,
                       "segments": {key: len(part["records"]) for key, part in dialog.current["segments"].items()},
                       "attempts": dialog.current["attempts"], "watchlist": window.symbols()})
        (output / "catalog-result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        dialog.grab().save(str(screenshot or output / "catalog.png"))
        dialog.close()
        window.close()
        application.exit(2 if error else 0)

    def poll():
        now = time.perf_counter()
        beats.append(now - state["last"])
        state["last"] = now
        try:
            if now - started > 100:
                raise AssertionError("目录验收超时")
            if state["stage"] == "waiting":
                if now - started < 0.6:
                    return
                state["stage"] = "refreshing"
                if refresh:
                    dialog.refresh()
                    return
            if state["stage"] == "refreshing":
                if dialog.token:
                    return
                if refresh and (len(dialog.current["segments"]) != 4
                                or any(x["error"] for x in dialog.current["attempts"].values())):
                    raise AssertionError("真实目录更新未通过四个分区，请查看 attempts")
                window.symbol_input.setText("")
                state["stage"] = "search"
            if state["stage"] == "search":
                queries = (("浦发", "000001", "沪深300", "158000", "520880", "530060", "sh510300")
                           if refresh else ("浦发", "000001", "沪深300", "sh510300"))
                if len(searches) < len(queries):
                    query = queries[len(searches)]
                    before = time.perf_counter()
                    dialog.search.setText(query)
                    searches.append({"query": query, "count": dialog.proxy.rowCount(),
                                     "filter_ms": round((time.perf_counter() - before) * 1000, 2)})
                    assert dialog.proxy.rowCount() > 0, "证券搜索没有匹配项：" + query
                    return
                dialog.table.selectRow(0)
                QtTest.QTest.mouseClick(dialog.add_button, QtCore.Qt.MouseButton.LeftButton)
                assert window.symbols() == ["510300.SH"], "选择结果没有写入关注列表"
                QtTest.QTest.mouseClick(dialog.add_button, QtCore.Qt.MouseButton.LeftButton)
                assert window.symbols() == ["510300.SH"] and "新增 0" in dialog.status.text(), "重复添加异常"
                assert window.store.setting("watchlist") == "510300.SH", "关注列表未保存"
                if refresh:
                    part = dialog.current["segments"]["etf"]
                    assert all(r.get("etf_reference") for r in part["records"]), "ETF 当前属性缺失"
                    result["etf_reference_counts"] = part["evidence"]["counts"]
                    result["etf_t0_count"] = sum(r["etf_reference"]["t_plus"] == 0 for r in part["records"])
                    result["etf_twenty_count"] = sum(r["etf_reference"]["limit_rate"] == "0.20" for r in part["records"])
                    dialog.search.setText("158000")
                    dialog.table.selectRow(0)
                    detail = dialog.details.toPlainText()
                    assert "交易所当前名单：T+0" in detail and "默认模拟设置：T+1" in detail
                    assert "获取时间不是生效日期" in detail
                    result["etf_detail"] = detail
                available = dialog.screen().availableGeometry()
                assert dialog.frameGeometry().height() <= available.height(), "目录高度超出可用屏幕"
                for widget in (dialog.search, dialog.add_button, dialog.status):
                    rect = QtCore.QRect(widget.mapTo(dialog, QtCore.QPoint()), widget.size())
                    assert dialog.rect().contains(rect), "搜索或操作区域被裁切"
                state["stage"] = "capture"
                state["capture_after"] = now + 0.5
            elif state["stage"] == "capture" and now >= state["capture_after"]:
                finish()
        except Exception as error:
            finish(str(error))
    timer.timeout.connect(poll)
    timer.start(20)
    return timer
