from copy import deepcopy
from dataclasses import replace
from datetime import datetime
import json
from pathlib import Path
import time

import pytest

from astock.datasets import write_dataset
from astock.domain import Bar, CN, dec
from astock.historical_status import normalize_status, read_result
from astock.rule_history import read_rule_metadata, stage_rule_revision
from astock.rules import default_rule, rule_at

SYMBOL = "600654.SH"


def observed():
    return json.loads((Path(__file__).parent / "fixtures/baostock-status-600654.json").read_text(encoding="utf-8"))


def normalized(**changes):
    source = observed()
    args = dict(rule=default_rule(SYMBOL), start="2024-06-20", end="2024-06-28",
                basic=source["basic"], rows=source["days"])
    args.update(changes)
    return normalize_status(**args)


def test_observed_st_suspension_removal_agrees_with_company_announcement():
    result = normalized()
    r = default_rule(SYMBOL)
    r.history = result["periods"]
    assert [(p.start, p.end, p.status) for p in r.history] == [
        ("2024-06-20", "2024-06-24", "risk_warning"),
        ("2024-06-25", "2024-06-25", "suspended"),
        ("2024-06-26", "2024-06-28", "normal"),
    ]
    assert rule_at(r, "2024-06-24").limit_rate == dec(".05")
    assert rule_at(r, "2024-06-26").limit_rate == dec(".10")
    assert rule_at(r, "2024-06-19").status == "unknown"
    assert rule_at(r, "2024-07-01").status == "unknown"
    assert rule_at(r, "2024-06-24").history == []


def test_current_name_and_listing_status_do_not_rewrite_past_state():
    source = observed()
    source["basic"][0].update(code_name="当前已不是ST的名称", status="0")
    assert normalized(basic=source["basic"])["periods"] == normalized()["periods"]


def test_missing_middle_session_becomes_unknown_and_is_never_forward_filled():
    source = observed()
    source["days"] = [r for r in source["days"] if r["date"] != "2024-06-21"]
    result = normalized(rows=source["days"])
    assert result["audit"]["missing_dates"] == ["2024-06-21"]
    assert result["periods"][0].end == "2024-06-20"
    assert result["periods"][1].status == "unknown"
    assert result["periods"][2].start == "2024-06-24"


def test_empty_response_does_not_certify_normal_trading():
    result = normalized(rows=[])
    assert len(result["audit"]["missing_dates"]) == 7
    assert all(p.status == "unknown" for p in result["periods"])


@pytest.mark.parametrize("change", ["duplicate", "unordered", "wrong_code", "missing_flag", "bad_flag", "outside"])
def test_invalid_response_fails_whole_request(change):
    rows = observed()["days"]
    if change == "duplicate":
        rows.insert(1, deepcopy(rows[0]))
    elif change == "unordered":
        rows.reverse()
    elif change == "wrong_code":
        rows[0]["code"] = "sz.000001"
    elif change == "missing_flag":
        del rows[0]["isST"]
    elif change == "bad_flag":
        rows[0]["isST"] = ""
    else:
        rows[-1]["date"] = "2024-07-01"
    with pytest.raises(ValueError):
        normalized(rows=rows)


def test_ipo_five_sessions_skip_national_holiday_and_do_not_count_calendar_days():
    source = observed()
    source["basic"][0]["ipoDate"] = "2024-09-30"
    days = ["2024-09-30", "2024-10-08", "2024-10-09", "2024-10-10", "2024-10-11", "2024-10-14"]
    rows = [dict(date=day, code="sh.600654", tradestatus="1", isST="0") for day in days]
    result = normalized(start="2024-09-27", end="2024-10-14", basic=source["basic"], rows=rows)
    assert [(p.start, p.end, p.status) for p in result["periods"]] == [
        ("2024-09-27", "2024-09-27", "unlisted"),
        ("2024-09-30", "2024-10-11", "no_limit"),
        ("2024-10-14", "2024-10-14", "normal"),
    ]


def test_delisting_is_dated_not_current_status_inferred():
    source = observed()
    source["basic"][0]["outDate"] = "2024-06-26"
    result = normalized(basic=source["basic"], rows=source["days"][:4])
    assert result["periods"][-1].status == "unlisted" and result["periods"][-1].start == "2024-06-26"
    with pytest.raises(ValueError, match="冲突"):
        normalized(basic=source["basic"])


def test_etf_not_labeled_stock_or_given_inferred_t0():
    with pytest.raises(ValueError, match="ETF"):
        normalized(rule=default_rule("510300.SH"))


def test_pagination_failure_after_some_rows_is_not_partial_success():
    class Broken:
        fields = ["date"]
        error_code, error_msg, count = "0", "中断", 0
        def next(self):
            self.count += 1
            if self.count == 1:
                return True
            self.error_code = "10002007"
            return False
        def get_row_data(self):
            return ["2024-06-20"]
    with pytest.raises(RuntimeError, match="分页中断"):
        read_result(Broken())


def revision(tmp_path):
    events = [Bar(SYMBOL, datetime(2024, 6, day, 15, tzinfo=CN), dec(10), dec(10), dec(10), dec(10),
                  10000, prev_close=dec(10)) for day in (20, 21, 24, 25, 26, 27, 28)]
    original = write_dataset(tmp_path / "datasets", "合成价格用于状态修订测试", events, verified=True)
    meta, digest = read_rule_metadata(tmp_path / "datasets", original["id"])
    result = normalized()
    meta["rules"][SYMBOL].history = result["periods"]
    return original, {"root": str(tmp_path / "datasets"), "identity": original["id"],
                      "stage": str(tmp_path / "staged"), "metadata_sha256": digest,
                      "rules": meta["rules"], "rule_evidence": {SYMBOL: result["audit"]}}


def test_raw_state_evidence_is_persisted_and_manual_edits_are_distinguished(tmp_path):
    original, request = revision(tmp_path)
    path = tmp_path / "datasets" / (original["id"] + ".json")
    before = path.read_bytes()
    result = stage_rule_revision(request, lambda _: None)
    assert result["meta"]["rule_evidence"][SYMBOL]["applied_without_edits"]
    assert path.read_bytes() == before
    request["stage"] = str(tmp_path / "staged2")
    periods = request["rules"][SYMBOL].history
    periods[0] = replace(periods[0], source="独立核对公告")
    result = stage_rule_revision(request, lambda _: None)
    assert not result["meta"]["rule_evidence"][SYMBOL]["applied_without_edits"]
    assert result["meta"]["rule_evidence"][SYMBOL]["rows"] == observed()["days"]


def test_modified_raw_evidence_fails_before_publishing(tmp_path):
    _, request = revision(tmp_path)
    request["rule_evidence"][SYMBOL]["rows"][0]["isST"] = "0"
    with pytest.raises(ValueError, match="校验失败"):
        stage_rule_revision(request, lambda _: None)
    assert not (tmp_path / "staged").exists()


def test_known_suspension_explains_missing_price_without_creating_a_bar(tmp_path):
    from astock.datasets import dataset_reader
    events = [Bar(SYMBOL, datetime(2024, 6, day, 15, tzinfo=CN), dec(10), dec(10), dec(10), dec(10),
                  10000, prev_close=dec(10)) for day in (24, 26)]
    original = write_dataset(tmp_path / "datasets", "合成价格，停牌日无记录", events, verified=True)
    meta, digest = read_rule_metadata(tmp_path / "datasets", original["id"])
    result = normalized(start="2024-06-24", end="2024-06-26", rows=observed()["days"][2:5])
    meta["rules"][SYMBOL].history = result["periods"]
    request = {"root": str(tmp_path / "datasets"), "identity": original["id"],
               "stage": str(tmp_path / "staged"), "metadata_sha256": digest,
               "rules": meta["rules"], "rule_evidence": {SYMBOL: result["audit"]}}
    revised = stage_rule_revision(request, lambda _: None)["meta"]
    assert revised["quality"]["counts"]["state_suspended"] == 1
    assert revised["quality"]["counts"]["missing_bars_total"] == 0
    _, rows = dataset_reader(tmp_path / "staged", revised["id"])
    assert len(list(rows)) == 2
    inspected, old = dataset_reader(tmp_path / "datasets", original["id"], inspection=True)
    list(old)
    assert inspected["quality"]["counts"]["missing_bars_total"] == 1


def test_day_missing_both_price_and_state_still_blocks_backtest(tmp_path):
    from astock.datasets import load_dataset
    r = default_rule(SYMBOL)
    r.history = normalized(rows=[row for row in observed()["days"] if row["date"] != "2024-06-21"])["periods"]
    events = [Bar(SYMBOL, datetime(2024, 6, day, 15, tzinfo=CN), dec(10), dec(10), dec(10), dec(10),
                  10000, prev_close=dec(10)) for day in (20, 24)]
    meta = write_dataset(tmp_path, "合成行情和状态双缺失", events, verified=True, rules={SYMBOL: r})
    with pytest.raises(ValueError, match="即使该日也没有行情"):
        load_dataset(tmp_path, meta["id"])


def test_preview_cancel_preserves_manual_input_and_apply_is_not_save(qtbot, tmp_path):
    from PySide6 import QtWidgets
    from astock.rule_history_ui import RuleHistoryDialog
    original, _ = revision(tmp_path)
    dialog = RuleHistoryDialog(tmp_path, original["id"])
    qtbot.addWidget(dialog)
    dialog.show()
    dialog.add_period()
    dialog.grid.item(0, 6).setText("我的手工来源")
    dialog.show_status_preview(normalized())
    dialog.preview.reject()
    assert dialog.grid.item(0, 6).text() == "我的手工来源"
    assert not dialog.evidence and not dialog.saved_id
    dialog.show_status_preview(normalized())
    dialog.preview.findChild(QtWidgets.QPushButton, "applyStockStatus").click()
    assert dialog.grid.rowCount() == 3 and not dialog.saved_id
    assert dialog.collect()[SYMBOL].history == normalized()["periods"]
    assert dialog.evidence[SYMBOL]["rows"] == observed()["days"]
    dialog.reject()


def test_status_fetch_timeout_terminates_worker_and_reports_actionable_error(qtbot, tmp_path):
    from astock.data_jobs import DataJobs
    jobs = DataJobs(tmp_path)
    messages = []
    jobs.message.connect(messages.append)
    process = jobs.context.Process(target=time.sleep, args=(60,), daemon=True)
    output = jobs.context.Queue()
    process.start()
    jobs.active["rule_fetch"] = {"kind": "rule_fetch", "token": "deadline-test", "process": process,
                                 "output": output, "request": {"stage": str(tmp_path / "stage")},
                                 "deadline": time.monotonic() - 1}
    try:
        jobs.poll()
        qtbot.waitUntil(lambda: not process.is_alive(), timeout=3000)
        assert messages[0]["type"] == "error" and "45 秒" in messages[0]["message"]
        assert not jobs.active and not (tmp_path / "stage").exists()
    finally:
        jobs.close()


def test_status_socket_reports_eof_instead_of_sdk_receive_loop(monkeypatch):
    import socket
    from astock.historical_status import StatusSocket
    monkeypatch.setattr(socket.socket, "recv", lambda *args, **kwargs: b"")
    with StatusSocket() as connection:
        with pytest.raises(ConnectionError, match="关闭了连接"):
            connection.recv(8192)
        assert connection.peer_closed


def test_status_transport_failure_restores_sdk_and_global_socket_settings(monkeypatch):
    import socket
    import baostock as bs
    import baostock.util.socketutil as transport
    from types import SimpleNamespace
    from astock.historical_status import fetch_status
    old_transport, old_timeout = transport.socket, socket.getdefaulttimeout()
    monkeypatch.setattr(socket.socket, "recv", lambda *args, **kwargs: b"")
    sockets = []
    def login():
        connection = transport.socket.socket()
        sockets.append(connection)
        try:
            connection.recv(8192)
        except ConnectionError:
            return SimpleNamespace(error_code="10002007", error_msg="网络接收错误")
    monkeypatch.setattr(bs, "login", login)
    monkeypatch.setattr(bs, "logout", lambda: None)
    with pytest.raises(RuntimeError, match="资料服务已关闭连接"):
        fetch_status({"rule": default_rule(SYMBOL), "start": "2024-06-20", "end": "2024-06-28"})
    assert transport.socket is old_transport and socket.getdefaulttimeout() == old_timeout
    assert sockets[0].fileno() == -1
