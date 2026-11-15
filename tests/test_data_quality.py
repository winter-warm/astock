import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from dataclasses import replace
from datetime import date, datetime, timedelta
import json
from pathlib import Path
from queue import Queue

import pytest
from PySide6 import QtCore

from astock.broker import Broker
from astock.data_quality import expected_minutes
from astock.datasets import dataset_reader, load_dataset, write_dataset
from astock.domain import Bar, CN, CorporateAction, MatchConfig, Quote, dec, dumps, loads
from astock.engine import Run
from astock.quality_ui import QualityDialog
from astock.rules import continuous_bar, continuous_session, default_rule
from astock.trading_calendar import manifest, trading_day


def bar(at, symbol="600000.SH", period="1d", **kwargs):
    return Bar(symbol, datetime.fromisoformat(at).replace(tzinfo=CN), dec(10), dec(10), dec(10), dec(10),
               100000, period, prev_close=dec(10), **kwargs)


def inspect(root, identity):
    meta, events = dataset_reader(root, identity, inspection=True)
    list(events)
    return meta["quality"]


@pytest.mark.parametrize("day,expected", [
    ("2023-01-02", False), ("2023-01-03", True), ("2023-01-28", False), ("2023-05-03", False),
    ("2024-02-09", False), ("2024-02-18", False), ("2024-02-19", True), ("2024-09-17", False),
    ("2025-01-27", True), ("2025-01-28", False), ("2025-02-04", False), ("2025-02-05", True),
    ("2026-01-04", False), ("2026-02-23", False), ("2026-02-24", True), ("2026-02-28", False),
    ("2026-04-06", False), ("2026-06-19", False), ("2026-09-25", False), ("2026-10-08", True),
    ("2022-12-30", None), ("2027-01-04", None),
])
def test_exchange_announcements_and_makeup_weekends(day, expected):
    assert trading_day(date.fromisoformat(day)) is expected


def test_daily_holiday_and_weekend_are_not_missing_observations(tmp_path):
    meta = write_dataset(tmp_path, "春节前后", [bar("2025-01-27T15:00"), bar("2025-02-05T15:00")], verified=True)
    report = inspect(tmp_path, meta["id"])
    assert report["counts"]["expected_bars"] == 2
    assert report["counts"]["missing_bars_total"] == 0
    assert not report["details"]
    assert report["calendar"] == manifest()


def test_requested_edges_and_middle_gap_are_distinguished_and_fully_exportable(tmp_path):
    meta = write_dataset(tmp_path, "下载窗口", [bar("2026-11-10T15:00"), bar("2026-11-12T15:00")],
                         verified=True, coverage_request={"start": "2026-11-09", "end": "2026-11-13"})
    report = inspect(tmp_path, meta["id"])
    assert report["counts"]["expected_bars"] == 5 and report["counts"]["missing_bars_total"] == 3
    assert report["counts"]["missing_day"] == 3
    assert report["counts"]["before_coverage"] == report["counts"]["after_coverage"] == 1
    assert any(r["kind"] == "missing_day" and r["start"] == "2026-11-11" for r in report["details"])
    # Candidate gaps do not fabricate a suspension or silently fill OHLC.
    loaded, actual = load_dataset(tmp_path, meta["id"])
    assert len(actual) == 2 and not any(e.suspended for e in actual)
    assert loaded["quality"]["status"] == "review"


def test_each_symbol_has_its_own_coverage_against_the_shared_requested_range(tmp_path):
    meta = write_dataset(tmp_path, "多标的范围", [bar("2026-11-10T15:00"), bar("2026-11-11T15:00"),
                         bar("2026-11-11T15:00", "000001.SZ")], verified=True)
    report = inspect(tmp_path, meta["id"])
    missing = [row for row in report["details"] if row["kind"] == "missing_day"]
    assert len(missing) == 1 and missing[0]["symbol"] == "000001.SZ" and missing[0]["start"] == "2026-11-10"


def test_minute_gap_excludes_lunch_and_partial_day_edges(tmp_path):
    observations = [bar("2026-11-13T" + t, period="1m") for t in ("11:29", "11:30", "13:01", "13:03")]
    meta = write_dataset(tmp_path, "分钟缺口", observations, verified=True)
    report = inspect(tmp_path, meta["id"])
    assert report["counts"]["expected_bars"] == 5 and report["counts"]["missing_bars_total"] == 1
    assert report["details"] == [{"kind": "missing_bar", "symbol": "600000.SH",
        "start": "2026-11-13T13:02:00+08:00", "end": "2026-11-13T13:02:00+08:00", "count": 1, "unit": "根 K 线"}]


@pytest.mark.parametrize("symbol,count", [("600000.SH", 237), ("510300.SH", 237), ("159915.SZ", 237)])
def test_full_day_minute_expectations_match_exchange_continuous_session(tmp_path, symbol, count):
    minutes = expected_minutes("1m", False)  # After the SSE 2026-07-06 closing-auction change.
    assert len(minutes) == count
    events = [bar(f"2026-11-13T{m//60:02}:{m%60:02}", symbol, "1m") for m in minutes]
    assert all(continuous_bar(e, default_rule(symbol)) for e in events)
    meta = write_dataset(tmp_path, "完整连续竞价分钟", events, verified=True,
                         coverage_request={"start": "2026-11-13", "end": "2026-11-13"})
    report = inspect(tmp_path, meta["id"])
    assert report["counts"]["expected_bars"] == count and report["counts"]["missing_bars_total"] == 0


def test_auction_bar_and_marked_suspension_are_explained_not_mislabeled_missing(tmp_path):
    events = [bar("2026-11-13T14:56", period="1m", suspended=True), bar("2026-11-13T14:57", period="1m"),
              bar("2026-11-13T15:00", period="1m")]
    meta = write_dataset(tmp_path, "停牌和竞价", events, verified=True)
    report = inspect(tmp_path, meta["id"])
    assert report["counts"]["suspended"] == report["counts"]["outside_session"] == 1
    assert report["counts"]["missing_bars_total"] == 0


def test_closed_day_is_visible_to_inspection_but_blocks_real_backtest(tmp_path):
    meta = write_dataset(tmp_path, "错误来源", [bar("2026-01-01T15:00")], verified=True)
    assert inspect(tmp_path, meta["id"])["counts"]["closed_day"] == 1
    with pytest.raises(ValueError, match="休市日"):
        load_dataset(tmp_path, meta["id"])


def test_calendar_unknown_range_is_not_guessed_from_weekdays(tmp_path):
    meta = write_dataset(tmp_path, "缺少日历", [bar("2027-01-04T15:00")], verified=True)
    report = inspect(tmp_path, meta["id"])
    assert report["counts"]["unknown_calendar"] == 1
    with pytest.raises(ValueError, match="交易日历"):
        load_dataset(tmp_path, meta["id"])
    assert not continuous_session(datetime(2027, 1, 4, 10, tzinfo=CN))


def test_unknown_long_requested_range_is_summarized_without_iterating_it(tmp_path):
    meta = write_dataset(tmp_path, "范围声明", [bar("2026-11-13T15:00")], verified=True,
                         coverage_request={"start": "0001-01-01", "end": "9999-12-31"})
    report = inspect(tmp_path, meta["id"])
    assert report["counts"]["unknown_calendar"] > 3_000_000
    assert len([r for r in report["details"] if r["kind"] == "unknown_calendar"]) == 2
    # Uncovered requested edges are a warning, not a reason to reject valid
    # observations wholly inside the verified calendar.
    assert len(load_dataset(tmp_path, meta["id"])[1]) == 1


def test_holiday_corporate_action_is_rejected_before_account_changes(tmp_path):
    action = CorporateAction("600000.SH", datetime(2026, 1, 1, 9, tzinfo=CN),
                             cash_per_share=dec(1), pay_date="2026-01-05")
    broker = Broker({"600000.SH": default_rule("600000.SH")})
    before = dumps(broker.snapshot())
    with pytest.raises(ValueError, match="交易日"):
        broker.corporate_action(action)
    assert dumps(broker.snapshot()) == before
    meta = write_dataset(tmp_path, "错误权益日期", [action, bar("2026-01-05T15:00")], verified=True)
    with pytest.raises(ValueError, match="交易日"):
        load_dataset(tmp_path, meta["id"])


def test_old_metadata_cannot_forge_actual_dates_or_claim_no_gaps(tmp_path):
    meta = write_dataset(tmp_path, "旧包", [bar("2026-11-10T15:00"), bar("2026-11-12T15:00")], verified=True)
    path = tmp_path / f"{meta['id']}.json"
    meta.pop("quality")
    path.write_text(dumps(meta), encoding="utf-8")
    checked, _ = load_dataset(tmp_path, meta["id"])
    assert checked["quality"]["counts"]["missing_bars_total"] == 1
    meta["end"] = "2026-11-10T15:00:00+08:00"
    path.write_text(dumps(meta), encoding="utf-8")
    with pytest.raises(ValueError, match="实际起止"):
        load_dataset(tmp_path, meta["id"])


def test_mixed_bar_periods_are_rejected_instead_of_using_first_period(tmp_path):
    meta = write_dataset(tmp_path, "混合周期", [bar("2026-11-12T15:00"), bar("2026-11-13T10:01", period="1m")], verified=True)
    with pytest.raises(ValueError, match="混合周期"):
        load_dataset(tmp_path, meta["id"])


def test_holiday_quotes_do_not_fill_or_advance_account_but_teaching_calendar_is_explicit():
    symbol = "600000.SH"
    rule = default_rule(symbol)
    config = MatchConfig(slippage_ticks=0, max_position_ratio=dec(1))
    before = datetime(2025, 12, 31, 10, tzinfo=CN)
    q = Quote(symbol, before, before, dec(10), dec(10), dec(10), 10000, 10000, 10000, dec(10), dec(11), dec(9))
    broker = Broker({symbol: rule}, config=config)
    broker.on_event(q)
    order = broker.submit(symbol, "BUY", 100, 10)
    closed = before + timedelta(days=1)
    broker.on_event(replace(q, time=closed, received=closed, volume=100000))
    assert not order.filled and "休市" in order.note and broker.clock == before
    teaching = Broker({symbol: rule}, config=config, teaching_calendar=True)
    teaching.on_event(bar("2026-01-01T15:00"))
    order = teaching.submit(symbol, "BUY", 100, 10)
    teaching.on_event(bar("2026-01-02T15:00"))
    assert order.filled == 100
    assert Broker.restore(loads(dumps(teaching.snapshot()))).teaching_calendar is True


def test_run_keeps_quality_and_calendar_version_in_report_and_manifest(tmp_path):
    from astock.reports import export_report
    meta = write_dataset(tmp_path / "datasets", "留存缺口", [bar("2026-11-10T15:00"), bar("2026-11-12T15:00")], verified=True)
    run = Run({"mode": "backtest", "dataset": meta["id"], "code": ""}, tmp_path, Queue())
    assert run.manifest["calendar"] == manifest()
    assert run.manifest["dataset"]["quality"]["counts"]["missing_bars_total"] == 1
    assert any("缺少 1 根" in log["message"] for log in run.logs)
    while run.status == "RUNNING":
        run.step()
    # Use the real Run state shape used by report export.
    state = run.message()
    path = export_report(tmp_path, state)
    assert "数据覆盖与日历" in path.read_text(encoding="utf-8")
    assert manifest()["sha256"] in path.read_text(encoding="utf-8")


def test_quality_window_reads_unverified_data_without_mutating_it_and_publishes_full_report(qtbot, tmp_path):
    root = tmp_path / "datasets"
    meta = write_dataset(root, "<原始>待核对", [bar("2026-11-10T15:00"), bar("2026-11-12T15:00")], verified=False)
    before = {p.name: p.read_bytes() for p in root.iterdir()}
    dialog = QualityDialog(tmp_path, meta["id"])
    qtbot.addWidget(dialog)
    dialog.show()
    beats = []
    timer = QtCore.QTimer()
    timer.timeout.connect(lambda: beats.append(1))
    timer.start(10)
    qtbot.waitUntil(lambda: dialog.token is None, timeout=15000)
    timer.stop()
    assert dialog.report and dialog.report["status"] == "blocked_actions", dialog.summary.text()
    assert len(beats) > 5 and dialog.open_button.isEnabled()
    assert dialog.table.model().rowCount() == len(dialog.report["details"])
    dialog.table.selectRow(0)
    assert "停牌" in dialog.detail.text()
    saved = json.loads(Path(dialog.report_path).with_suffix(".json").read_text(encoding="utf-8"))
    assert saved == dialog.report and saved["details_complete"]
    assert "&lt;原始&gt;" in Path(dialog.report_path).read_text(encoding="utf-8")
    assert all((root / name).read_bytes() == content for name, content in before.items())
    dialog.close()
    assert not dialog.jobs.active


def test_cancel_quality_drops_stale_completion_and_never_publishes(qtbot, tmp_path):
    meta = write_dataset(tmp_path / "datasets", "取消", [bar("2026-11-13T15:00")], verified=True)
    dialog = QualityDialog(tmp_path, meta["id"])
    qtbot.addWidget(dialog)
    token = dialog.token
    process = dialog.jobs.active["quality"]["process"]
    dialog.cancel()
    dialog.receive({"token": token, "type": "finished", "result": {}})
    qtbot.waitUntil(lambda: not dialog.jobs.retired, timeout=5000)
    assert not process.is_alive() and not list((tmp_path / "reports").rglob("*.html"))
    assert "已取消" in dialog.summary.text()
