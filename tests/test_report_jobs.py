import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import csv
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
import time

from PySide6 import QtCore
import pytest

from astock.broker import Broker
from astock.domain import CN, MatchConfig, Quote, dec, loads
from astock.engine import performance
from astock.operations_ui import OperationDialog
from astock.report_jobs import comparison_job, publish_report, report_job
from astock.rules import default_rule
from astock.storage import Store
from astock.window import MainWindow


def saved_state(root, identity="run001"):
    broker = Broker({"600000.SH": default_rule("600000.SH")}, config=MatchConfig(slippage_ticks=0))
    at = datetime(2026, 11, 13, 10, tzinfo=CN)
    for index in range(2):
        stamp = at + timedelta(seconds=index * 5)
        broker.on_event(Quote("600000.SH", stamp, stamp, dec(10), dec(10), dec(10), 100000,
                              100000, 100000 + index * 10000, dec(10), dec(11), dec(9)))
        if index == 0:
            broker.submit("600000.SH", "BUY", 100, 10, reason="测试成交 <原始理由>")
    assert len(broker.trades) == 1
    state = {"id": identity, "name": "报告测试", "mode": "replay", "status": "COMPLETED",
             "manifest": {"config": broker.config, "rules": broker.rules, "engine": "test",
                          "calendar": {"sha256": "calendar"}, "dataset": {"name": "测试数据", "sha256": "data"}},
             "snapshot": broker.snapshot(),
             "result": {"statistics": performance([], broker), "curve": [], "logs": []}}
    with_store(root, state)
    return state


def with_store(root, state):
    store = Store(root)
    try:
        store.save_run(*(state[key] for key in ("id", "name", "mode", "status", "manifest", "snapshot", "result")))
    finally:
        store.close()


def test_report_uses_one_saved_snapshot_even_if_run_changes_during_export(tmp_path):
    state = saved_state(tmp_path)
    def update(progress):
        if "snapshot_sha256" in progress:
            state["status"] = "RUNNING"
            state["result"]["statistics"]["return"] = .75
            state["snapshot"]["trades"] = []
            with_store(tmp_path, state)
    request = {"root": str(tmp_path), "identity": state["id"], "stage": str(tmp_path / "datasets/.imports/abc123")}
    result = report_job(request, update)
    report = publish_report(tmp_path, request, result)
    exported = loads(report.with_name("run.json").read_text(encoding="utf-8"))
    assert exported["status"] == "COMPLETED" and len(exported["snapshot"]["trades"]) == 1
    assert exported["result"]["statistics"]["return"] != .75
    assert len(exported["report_snapshot"]["sha256"]) == 64
    with report.with_name("trades.csv").open(encoding="utf-8-sig", newline="") as source:
        rows = list(csv.reader(source))
    assert len(rows) == 2 and rows[1][-1] == "测试成交 <原始理由>"
    assert "&lt;原始理由&gt;" in report.read_text(encoding="utf-8")
    original = report.read_bytes()
    request["stage"] = str(tmp_path / "datasets/.imports/def456")
    second = publish_report(tmp_path, request, report_job(request, lambda _: None))
    assert second != report and report.read_bytes() == original


def test_mismatched_or_incomplete_report_is_never_published(tmp_path):
    saved_state(tmp_path)
    request = {"root": str(tmp_path), "identity": "run001", "stage": str(tmp_path / "datasets/.imports/test")}
    result = report_job(request, lambda _: None)
    with pytest.raises(ValueError, match="编号"):
        publish_report(tmp_path, {**request, "identity": "another"}, result)
    (Path(request["stage"]) / "trades.csv").unlink()
    with pytest.raises(ValueError, match="完整"):
        publish_report(tmp_path, request, result)
    assert not (tmp_path / "reports/run001").exists()


def test_comparison_is_a_consistent_view_and_keeps_bad_rows_visible(tmp_path):
    state = saved_state(tmp_path)
    store = Store(tmp_path)
    try:
        for index in range(60):
            store.save_run(f"row{index}", str(index), "replay", "COMPLETED", state["manifest"],
                           state["snapshot"], state["result"])
        store.db.execute("UPDATE runs SET result='broken' WHERE id='row59'")
        store.db.commit()
        changed = False
        def update(progress):
            nonlocal changed
            if not changed:
                changed = True
                store.db.execute("UPDATE runs SET status='RUNNING'")
                store.db.commit()
        result = comparison_job({"root": str(tmp_path)}, update)
        assert len(result["rows"]) == 61 and result["errors"] == 1
        assert all(row["status"] == "COMPLETED" for row in result["rows"])
        assert len({row["basis"] for row in result["rows"] if not row["error"]}) == 1
        assert next(row for row in result["rows"] if row["id"] == "row59")["error"]
        assert all(row["status"] == "RUNNING" for row in comparison_job({"root": str(tmp_path)}, lambda _: None)["rows"])
    finally:
        store.close()


@pytest.mark.parametrize("field", ["cash", "rules", "engine", "clock", "data", "config"])
def test_comparison_separates_materially_different_assumptions(tmp_path, field):
    first = saved_state(tmp_path)
    second = deepcopy(first)
    second["id"] = "run002"
    if field == "cash":
        second["snapshot"]["account"].initial = dec(200000)
    elif field == "clock":
        second["snapshot"]["clock"] += timedelta(seconds=5)
    elif field == "rules":
        second["manifest"]["rules"] = {}
    elif field == "engine":
        second["manifest"]["engine"] = "another"
    elif field == "data":
        second["manifest"]["dataset"]["sha256"] = "changed"
    else:
        second["manifest"]["config"].slippage_ticks = 2
    with_store(tmp_path, second)
    assert comparison_job({"root": str(tmp_path)}, lambda _: None)["basis_groups"] == 2


def test_background_export_does_not_follow_account_switch_and_close_stops_workers(qtbot, tmp_path):
    state = saved_state(tmp_path)
    window = MainWindow(tmp_path, start_workers=False)
    qtbot.addWidget(window)
    window.states[state["id"]], window.active_id = state, state["id"]
    window.export_current()
    assert window.pages.currentIndex() == 4
    window.home_accounts.selector.setCurrentIndex(window.home_accounts.selector.findData(state['id']))
    window.home_accounts.report_button.click()
    dialog = window.operations[("report", state["id"])]
    qtbot.addWidget(dialog)
    window.active_id = "someotheraccount"
    beats = []
    timer = QtCore.QTimer()
    timer.timeout.connect(lambda: beats.append(time.perf_counter()))
    timer.start(10)
    try:
        qtbot.waitUntil(lambda: dialog.token is None, timeout=15000)
        assert dialog.report_path and dialog.result["id"] == state["id"]
        assert len(beats) >= 5 and not dialog.isModal()
        previous = dialog.report_path.read_bytes()
        dialog.start()
        job = dialog.jobs.active["report"]
        token = dialog.token
        dialog.cancel()
        dialog.receive({"type": "finished", "token": token, "result": {"id": "bad"}})
        window.close()
        assert not job["process"].is_alive()
        assert not Path(job["request"]["stage"]).exists()
        assert list((tmp_path / "reports" / state["id"]).rglob("report.html"))[0].read_bytes() == previous
    finally:
        timer.stop()


def test_comparison_refresh_close_and_large_table_remain_usable(qtbot, tmp_path):
    saved_state(tmp_path)
    dialog = OperationDialog(tmp_path, "compare")
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitUntil(lambda: dialog.token is None, timeout=15000)
    assert dialog.table.model().rowCount() == 1
    # Display pressure fixture only; these are not 50,000 real account runs.
    row = dialog.result["rows"][0]
    dialog.table.set_records([{**row, "id": f"view{i}"} for i in range(50000)], "fixture")
    assert dialog.table.model().rowCount() == 50000
    dialog.table.selectRow(49999)
    assert len(dialog.table.model().cache) < 1024 and dialog.open_button.isEnabled()
    with qtbot.waitSignal(dialog.view_run) as signal:
        dialog.open_result()
    assert signal.args == ["view49999"]
    dialog.start()
    job = dialog.jobs.active["compare"]
    dialog.reject()  # Escape and Close both clean up the child process.
    assert not job["process"].is_alive()


def test_unreadable_database_is_an_inline_error_not_a_modal_block(qtbot, tmp_path):
    dialog = OperationDialog(tmp_path, "compare")
    qtbot.addWidget(dialog)
    qtbot.waitUntil(lambda: dialog.token is None, timeout=15000)
    assert "失败" in dialog.summary.text()
    assert dialog.retry.isEnabled() and not dialog.open_button.isEnabled()


def test_large_report_exports_every_fixture_row_without_blocking_ui(qtbot, tmp_path):
    state = saved_state(tmp_path)
    # Explicit export stress fixture, not simulated trading or ledger evidence.
    state["name"] = "合成报告压力数据 / 50,000 行"
    trade = state["snapshot"]["trades"][0]
    state["snapshot"]["trades"] = [replace(trade, id=f"fixture{i}") for i in range(50000)]
    state["result"]["statistics"]["trades"] = 50000
    with_store(tmp_path, state)
    dialog = OperationDialog(tmp_path, "report", state["id"], state["name"])
    qtbot.addWidget(dialog)
    beats = [time.perf_counter()]
    timer = QtCore.QTimer()
    timer.timeout.connect(lambda: beats.append(time.perf_counter()))
    timer.start(10)
    try:
        qtbot.waitUntil(lambda: dialog.token is None, timeout=30000)
        assert dialog.report_path and dialog.result["trades"] == 50000
        assert len(beats) > 10
        assert max(b - a for a, b in zip(beats, beats[1:])) < 1
        with dialog.report_path.with_name("trades.csv").open(encoding="utf-8-sig", newline="") as source:
            assert sum(1 for _ in csv.reader(source)) == 50001
        assert "fixture49999" in dialog.report_path.with_name("run.json").read_text(encoding="utf-8")
    finally:
        timer.stop()
