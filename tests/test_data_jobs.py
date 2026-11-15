import os
from pathlib import Path
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from dataclasses import replace
from datetime import datetime, timedelta
import time

import pytest
from PySide6 import QtCore

from astock.data_jobs import DataJobs, preview_dataset, publish_import
from astock.datasets import load_dataset, write_dataset
from astock.domain import CN, Bar, CorporateAction, Quote, dec
from astock.window import MainWindow


@pytest.fixture(scope="module")
def data_package(tmp_path_factory):
    root = tmp_path_factory.mktemp("large-data")
    at = datetime(2026, 11, 12, 10, tzinfo=CN)
    base = Quote("600000.SH", at, at, dec(10), dec(10), dec(10), 100000, 100000,
                 100000, dec(10), dec(11), dec(9))
    meta = write_dataset(root, "教学压力数据", [replace(base, time=at + timedelta(seconds=i),
                         received=at + timedelta(seconds=i), volume=100000+i*100) for i in range(12000)],
                         demo=True, source="synthetic-test", verified=True)
    return root, meta


def test_streaming_preview_validates_all_rows_and_limits_only_the_chart(data_package):
    root, meta = data_package
    progress = []
    result = preview_dataset(root, meta["id"], progress.append)
    assert result["meta"]["count"] == 12000
    assert len(result["points"]) == 1000
    assert result["points"][-1]["volume"] == 100000 + 11999 * 100
    assert progress[-1]["done"] >= 10000


def test_late_action_cannot_validate_an_earlier_factor_change(tmp_path):
    at = datetime(2026, 11, 12, 10, tzinfo=CN)
    old = Bar("600000.SH", at, dec(10), dec(11), dec(9), dec(10), 1000, period="1m")
    adjusted = replace(old, time=at + timedelta(days=1), factor=dec(2))
    action = CorporateAction(old.symbol, adjusted.time + timedelta(minutes=1), share_multiplier=dec(2))
    meta = write_dataset(tmp_path, "late action", [old, adjusted, action], verified=True)
    with pytest.raises(ValueError, match="权益"):
        load_dataset(tmp_path, meta["id"])


def test_background_import_keeps_ui_events_flowing_and_publishes_only_on_success(qtbot, tmp_path, data_package):
    source, meta = data_package
    root = tmp_path / "datasets"
    root.mkdir()
    jobs = DataJobs(root)
    messages, beats = [], []
    jobs.message.connect(messages.append)
    timer = QtCore.QTimer()
    timer.timeout.connect(lambda: beats.append(time.perf_counter()))
    timer.start(10)
    try:
        token = jobs.start("import", source=str(source / (meta["id"] + ".json")))
        qtbot.waitUntil(lambda: any(m["type"] in ("finished", "error") for m in messages), timeout=15000)
        result = next(m for m in messages if m["type"] == "finished")
        assert result["token"] == token
        assert len(beats) >= 5
        assert not (root / (meta["id"] + ".json")).exists()
        # The consumer can receive a queued completion after the worker exits.
        # Finalization must not race the janitor deleting successful staging.
        qtbot.waitUntil(lambda: not jobs.retired, timeout=5000)
        assert (Path(result["request"]["stage"]) / (meta["id"] + ".parquet")).exists()
        publish_import(root, result["request"], result["result"])
        loaded, records = load_dataset(root, meta["id"])
        assert loaded["sha256"] == meta["sha256"] and len(records) == 12000
        with pytest.raises(ValueError, match="已存在"):
            publish_import(root, result["request"], result["result"])
        assert load_dataset(root, meta["id"])[0]["sha256"] == meta["sha256"]
    finally:
        timer.stop()
        jobs.close()


def test_import_cancel_and_corrupt_package_never_publish_partial_dataset(qtbot, tmp_path, data_package):
    source, meta = data_package
    root = tmp_path / "datasets"
    root.mkdir()
    jobs = DataJobs(root)
    messages = []
    jobs.message.connect(messages.append)
    try:
        jobs.start("import", source=str(source / (meta["id"] + ".json")))
        process = jobs.active["import"]["process"]
        assert process.is_alive()
        jobs.cancel("import")
        qtbot.waitUntil(lambda: not jobs.retired, timeout=5000)
        assert not list(root.glob("*.json")) and not list(root.glob("*.parquet"))
        assert not list((root / ".imports").glob("*"))
        bad_source = tmp_path / "bad"
        bad_source.mkdir()
        (bad_source / (meta["id"] + ".json")).write_bytes((source / (meta["id"] + ".json")).read_bytes())
        (bad_source / (meta["id"] + ".parquet")).write_bytes(b"not parquet")
        jobs.start("import", source=str(bad_source / (meta["id"] + ".json")))
        qtbot.waitUntil(lambda: any(m["type"] == "error" for m in messages), timeout=10000)
        assert "校验" in messages[-1]["message"]
        assert not list(root.glob("*.json"))
    finally:
        jobs.close()


@pytest.mark.parametrize("release", ["cancel", "close"])
def test_successful_unpublished_result_is_cleaned_when_owner_discards_it(qtbot, tmp_path, data_package, release):
    source, meta = data_package
    root = tmp_path / "datasets"
    root.mkdir()
    jobs = DataJobs(root)
    messages = []
    jobs.message.connect(messages.append)
    try:
        jobs.start("import", source=str(source / (meta["id"] + ".json")))
        qtbot.waitUntil(lambda: any(m["type"] == "finished" for m in messages), timeout=15000)
        qtbot.waitUntil(lambda: not jobs.retired, timeout=5000)
        stage = Path(next(m for m in messages if m["type"] == "finished")["request"]["stage"])
        assert stage.is_dir()
        if release == "cancel":
            jobs.cancel("import")
        else:
            jobs.close()
        assert not stage.exists() and not list(root.glob("*.parquet"))
        assert (source / (meta["id"] + ".parquet")).exists()
    finally:
        jobs.close()


def test_preview_race_cannot_replace_newer_dataset_or_change_user_mode(qtbot, tmp_path):
    window = MainWindow(tmp_path, start_workers=False)
    qtbot.addWidget(window)
    window.show()
    old_token = window.preview_token
    old_identity = window.preview_identity
    window._select_demo("quote")
    new_identity = window.preview_identity
    assert old_identity != new_identity
    window.mode_combo.setCurrentIndex(2)  # User moves to live while preview is loading.
    window.data_job_message({"type": "error", "kind": "preview", "token": old_token, "message": "old failure"})
    assert "old failure" not in window.data_badge.text()
    qtbot.waitUntil(lambda: window.preview_token is None, timeout=10000)
    assert window.preview_identity == new_identity
    assert window.preview_chart.points
    assert window.mode_combo.currentData() == "live"


def test_closing_window_terminates_pending_data_jobs(qtbot, tmp_path, data_package):
    source, meta = data_package
    window = MainWindow(tmp_path, start_workers=False)
    qtbot.addWidget(window)
    window.start_import(source / (meta["id"] + ".json"))
    processes = [j["process"] for j in window.data_jobs.active.values()]
    window.close()
    assert all(not p.is_alive() for p in processes)
    assert not (tmp_path / "datasets" / (meta["id"] + ".json")).exists()
    assert not list((tmp_path / "datasets/.imports").glob("*"))


def test_many_trade_rows_remain_accessible_without_cell_allocation(qtbot, tmp_path):
    from astock.domain import Trade
    window = MainWindow(tmp_path, start_workers=False)
    qtbot.addWidget(window)
    window.show()
    at = datetime(2026, 11, 12, 10, tzinfo=CN)
    trades = [Trade(f"T{i:06d}", "O1", "600000.SH", "BUY", 100, dec(10), dec(5), at, f"理由 {i}")
              for i in range(50000)]
    view = window.trades_table
    started = time.perf_counter()
    view.set_records(trades, "large-run")
    assert time.perf_counter() - started < .5
    assert view.model().rowCount() == 50000
    view.selectRow(49999)
    assert view.current_record().id == "T049999"
    assert view.model().data(view.model().index(49999, 7)) == "理由 49999"
    assert len(view.record_model.cache) < 1024
    view.set_records(trades + [trades[0]], "large-run")
    assert view.current_record().id == "T049999"
    view.set_records(trades, "another-run")
    assert view.current_record() is None


def test_long_input_manifest_is_summarized_without_removing_saved_parts(qtbot, tmp_path):
    from queue import Queue
    from astock.engine import Run
    window = MainWindow(tmp_path, start_workers=False)
    qtbot.addWidget(window)
    run = Run({"mode": "manual", "symbols": ["600000.SH"]}, tmp_path, Queue())
    state = run.message()
    state["manifest"]["input_archive"]["parts"] = [
        {"file": f"{i:08d}.parquet", "sha256": "0"*64, "count": 20} for i in range(10000)]
    state["manifest"]["input_archive"]["count"] = 200000
    window.display_run(state)
    text = window.live_manifest_text.toPlainText()
    assert "200,000" in text and "part_count" in text
    assert len(text) < 5000
    assert len(state["manifest"]["input_archive"]["parts"]) == 10000
    run.stop()


def test_queued_account_updates_paint_only_latest_state(qtbot, tmp_path, monkeypatch):
    from queue import Queue
    from astock.engine import Run
    window = MainWindow(tmp_path, start_workers=False)
    qtbot.addWidget(window)
    window.output = Queue()
    run = Run({"mode": "manual", "symbols": ["600000.SH"]}, tmp_path, Queue())
    window.active_id = run.id
    painted = []
    monkeypatch.setattr(window, "display_run", lambda state: painted.append(state["revision"]))
    for revision in range(12):
        window.output.put({**run.message(), "revision": revision})
    window.poll()
    assert painted == [11]
    run.stop()


def test_narrow_quote_preview_has_readable_axis_and_no_artificial_zero(qtbot):
    from PySide6 import QtGui
    from astock.ui_components import PriceChart
    chart = PriceChart()
    qtbot.addWidget(chart)
    chart.resize(300, 260)
    chart.volume.setMaximumHeight(48)
    chart.show()
    at = datetime(2026, 11, 12, 10, tzinfo=CN)
    chart.set_data([{"time": at + timedelta(seconds=i), "open": 10, "close": 10,
                     "low": 10, "high": 10, "volume": 100000+i*100} for i in range(1000)], quote=True)
    qtbot.wait(100)
    chart.grab()
    assert chart.plot.viewRange()[1][0] > 8
    canvas = QtGui.QImage(400, 300, QtGui.QImage.Format.Format_ARGB32)
    painter = QtGui.QPainter(canvas)
    try:
        _, _, texts = chart.axis.generateDrawSpecs(painter)
        assert texts
        for left, right in zip(texts, texts[1:]):
            assert not left[0].intersects(right[0])
        _, _, values = chart.volume.getAxis("left").generateDrawSpecs(painter)
        assert len(values) <= 1
    finally:
        painter.end()


def test_old_trade_loads_exact_history_and_survives_account_refresh(qtbot, tmp_path, data_package):
    from queue import Queue
    import shutil
    from astock.domain import Trade
    from astock.engine import Run
    source, meta = data_package
    window = MainWindow(tmp_path, start_workers=False)
    qtbot.addWidget(window)
    window.show()
    for extension in (".json", ".parquet"):
        shutil.copyfile(source / (meta["id"] + extension), tmp_path / "datasets" / (meta["id"] + extension))
    run = Run({"mode": "replay", "dataset": meta["id"], "autoplay": False}, tmp_path, Queue())
    state = run.message()
    at = datetime(2026, 11, 12, 10, tzinfo=CN)
    # View fixture: a persisted trade older than the engine's recent-price cache.
    trade = Trade("T000001", "O1", "600000.SH", "BUY", 100, dec(10), dec(5), at + timedelta(seconds=5), "早期成交")
    state["snapshot"]["trades"] = [trade]
    state["snapshot"]["clock"] = at + timedelta(seconds=11999)
    latest = preview_dataset(source, meta["id"])["points"]
    state["result"]["prices"] = {"600000.SH": latest}
    window.active_id = run.id
    window.states[run.id] = state
    window.display_run(state)
    window.trades_table.selectRow(0)
    assert window.trade_token is not None
    qtbot.waitUntil(lambda: window.trade_token is None, timeout=10000)
    assert any(p["time"] == trade.time for p in window.result_chart.points)
    assert window.result_chart.points[-1]["time"] < latest[0]["time"]
    assert window.result_chart.cursor.isVisible()
    window.display_run(state)
    assert window.result_chart.points[-1]["time"] < latest[0]["time"]
    window.clear_trade_context()
    assert window.result_chart.points == latest
    assert not window.result_chart.cursor.isVisible()
    run.stop()


def test_trade_context_honors_observation_cutoff_and_missing_time(data_package):
    from astock.data_jobs import trade_context
    source, meta = data_package
    at = datetime(2026, 11, 12, 10, tzinfo=CN)
    # dataset_reader expects root/datasets, use the existing package's parent layout.
    request = {"root": source.parent, "dataset": meta["id"], "symbol": "600000.SH",
               "at": at + timedelta(seconds=100), "until": at + timedelta(seconds=105)}
    from unittest.mock import patch
    from astock.datasets import dataset_reader
    with patch("astock.data_jobs.dataset_reader", lambda _, identity: dataset_reader(source, identity)):
        context = trade_context(request)
        assert context["points"][-1]["time"] == request["until"]
        with pytest.raises(ValueError, match="准确时刻"):
            trade_context({**request, "at": at + timedelta(microseconds=1)})


def test_date_ticks_point_at_actual_candles(qtbot):
    from astock.ui_components import PriceChart
    chart = PriceChart()
    qtbot.addWidget(chart)
    chart.axis.times = [datetime(2026, 11, day, 15, tzinfo=CN) for day in (11, 12, 13, 16, 17)]
    ticks = chart.axis.tickValues(-.5, 4.5, 800)[0][1]
    assert ticks == [0, 1, 2, 3, 4]
    assert chart.axis.tickStrings(ticks, 1, 1) == ["11/11", "11/12", "11/13", "11/16", "11/17"]


def test_etf_candles_preserve_subyuan_price_range(qtbot):
    from astock.ui_components import PriceChart
    chart = PriceChart()
    qtbot.addWidget(chart)
    chart.resize(650, 350)
    chart.show()
    at = datetime(2026, 11, 12, 15, tzinfo=CN)
    chart.set_data([{"time": at + timedelta(days=i), "open": 4.21, "close": 4.22,
                     "low": 4.205, "high": 4.225, "volume": 10000} for i in range(5)])
    qtbot.wait(100)
    low, high = chart.plot.viewRange()[1]
    assert low <= 4.205 and high >= 4.225
    assert high - low < .1
