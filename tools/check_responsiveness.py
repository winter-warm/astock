"""Native UI acceptance: large preview + eight real strategy processes + all-row table access."""
from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import datetime, timedelta
import json
import multiprocessing as mp
from pathlib import Path
import statistics
import sys
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default="output/responsiveness")
    parser.add_argument("--rows", type=int, default=100000)
    args = parser.parse_args()
    out = Path(args.output_dir).resolve()
    root = out / "data"
    from astock.datasets import list_datasets, write_dataset
    from astock.domain import CN, Quote, Trade, dec
    from astock.strategy import TEMPLATES, parameter_schema
    at = datetime(2026, 11, 12, 10, tzinfo=CN)
    quote = Quote("600000.SH", at, at, dec(10), dec(10), dec(10), 100000, 100000,
                  100000, dec(10), dec(11), dec(9), source="synthetic-stress")
    existing = next((m for m in list_datasets(root / "datasets") if m.get("source") == "synthetic-stress"), None)
    meta = existing or write_dataset(root / "datasets", "教学压力测试 · 大文件", (
        replace(quote, time=at + timedelta(seconds=i), received=at + timedelta(seconds=i), volume=100000+i*100)
        for i in range(args.rows)), demo=True, source="synthetic-stress", verified=True)
    from PySide6 import QtCore, QtGui, QtTest, QtWidgets
    from astock.window import MainWindow
    app = QtWidgets.QApplication([])
    app.setFont(QtGui.QFont("Microsoft YaHei UI", 9))
    window = MainWindow(root)
    window.fit_initial_layout(1280, 760)
    window.show()
    started = time.perf_counter()
    beats, key_delays, render_times = [], [], []
    last = started
    stages = set()
    target_ids = set()
    code = TEMPLATES["双均线趋势"]["code"]
    bar = next(m for m in window.datasets if m["demo"] and m["kind"] == "bar")
    original_display = window.display_run
    def measured_display(state):
        begin = time.perf_counter()
        original_display(state)
        render_times.append((time.perf_counter() - begin) * 1000)
    window.display_run = measured_display
    def tick():
        nonlocal last
        current = time.perf_counter()
        beats.append((current-last)*1000)
        last = current
        elapsed = current - started
        if elapsed > .5 and "start" not in stages:
            stages.add("start")
            window.dataset_combo.setCurrentIndex(window.dataset_combo.findData(meta["id"]))
            for index in range(8):
                window.engine_commands.put({"op": "start", "mode": "backtest", "name": f"并发验收 {index+1}",
                    "dataset": bar["id"], "code": code, "parameters": {
                        k: v["default"] for k, v in parameter_schema(code).items()}, "speed": 1000})
        if elapsed > 1 and len(key_delays) < 8:
            begin = time.perf_counter()
            window.editor.moveCursor(QtGui.QTextCursor.MoveOperation.End)
            QtTest.QTest.keyClick(window.editor, QtCore.Qt.Key.Key_Return)
            QtTest.QTest.keyClicks(window.editor, "# responsive")
            key_delays.append((time.perf_counter() - begin) * 1000)
        for key, state in window.states.items():
            if state["name"].startswith("并发验收"):
                target_ids.add(key)
        complete = (len(target_ids) == 8 and all(window.states[k]["status"] == "COMPLETED" for k in target_ids)
                    and window.preview_token is None and len(window.preview_chart.points) == 1000)
        if (complete or elapsed > 90) and "finished" not in stages:
            stages.add("finished")
            # This is a view-only stress fixture, never an account or performance result.
            trades = [Trade(f"V{i:06d}", "display-only", "600000.SH", "BUY", 100, dec(10), dec(5), at,
                            f"界面压力数据 {i}") for i in range(50000)]
            begin = time.perf_counter()
            window.trades_table.set_records(trades, "view-only-stress")
            window.trades_table.selectRow(len(trades)-1)
            final_access = window.trades_table.current_record().id
            table_ms = (time.perf_counter()-begin)*1000
            report = {"completed": complete, "source_rows": meta["count"], "preview_rows": len(window.preview_chart.points),
                "real_strategy_runs": len(target_ids), "completed_runs": sum(window.states[k]["status"] == "COMPLETED" for k in target_ids),
                "trades_per_run": [window.states[k]["result"]["statistics"]["trades"] for k in sorted(target_ids)],
                "timer_samples": len(beats), "max_timer_gap_ms": max(beats),
                "p99_timer_gap_ms": statistics.quantiles(beats, n=100)[98],
                "max_key_dispatch_ms": max(key_delays, default=0), "max_account_render_ms": max(render_times, default=0),
                "view_only_trade_rows": len(trades), "last_trade_access": final_access, "table_replace_ms": table_ms,
                "elapsed_seconds": elapsed, "device_pixel_ratio": window.devicePixelRatioF()}
            report["responsive"] = complete and max(beats) < 500 and max(key_delays) < 200 and table_ms < 200
            (out / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            if window.active_id in window.states:
                original_display(window.states[window.active_id])
            window.switch_workspace(0)
            window.grab().save(str(out / "desktop.png"))
            print(json.dumps(report, ensure_ascii=False), flush=True)
            window.close()
            app.exit(0 if report["responsive"] else 2)
    timer = QtCore.QTimer()
    timer.timeout.connect(tick)
    timer.start(16)
    sys.exit(app.exec())


if __name__ == "__main__":
    mp.freeze_support()
    main()
