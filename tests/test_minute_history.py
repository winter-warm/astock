from datetime import datetime
from queue import Queue
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pandas as pd
import pytest

from astock.datasets import list_datasets, load_dataset
from astock.domain import CN, dec
from astock.market import download_history_worker
from astock.minute_history import normalize_minutes, source_error


def frame(times=("2026-11-12 10:00:00", "2026-11-12 10:01:00", "2026-11-13 10:00:00")):
    return pd.DataFrame([{"时间": at, "开盘": "10.01", "最高": "10.20", "最低": "10.00",
                          "收盘": "10.10", "成交量": "12345", "涨跌额": "0.01"} for at in times])


def daily():
    return pd.DataFrame([{"date": "2026-11-11", "close": "9.90"}, {"date": "2026-11-12", "close": "10.00"},
                         {"date": "2026-11-13", "close": "99"}])


def normalize(data=None, ref=None, **kwargs):
    return normalize_minutes("600000.SH", "1m", frame() if data is None else data, daily() if ref is None else ref,
                             "2026-11-12", "2026-11-13", source=kwargs.pop("source", "sina"),
                             observed=kwargs.pop("observed", datetime(2026, 11, 14, tzinfo=CN)), **kwargs)


def test_minute_reference_is_prior_session_not_prior_bar_or_future_daily_close():
    events, issues, audit = normalize()
    assert not issues
    assert [b.prev_close for b in events] == [dec("9.9"), dec("9.9"), dec("10")]
    assert [b.volume for b in events] == [12345] * 3
    assert audit["volume_unit"] == "share" and audit["time_label"] == "bar-end"
    assert len(audit["references"]) == 2
    assert all(b.close == dec("10.1") for b in events)


def test_eastmoney_has_own_volume_contract():
    events, _, audit = normalize(source="eastmoney")
    assert events[0].volume == 1234500 and audit["source_volume_unit"] == "lot-100"


def test_missing_prior_session_is_not_replaced_by_older_or_same_day_close():
    ref = daily().iloc[1:]
    events, issues, audit = normalize(ref=ref)
    assert events[0].prev_close == 0 and len(issues) == 1
    assert "上一交易日" in issues[0]
    assert audit["references"][0]["reference_day"] == "2026-11-11"


def test_weekend_reference_uses_actual_exchange_session():
    events, issues, _ = normalize_minutes("600000.SH", "1m", frame(("2026-11-09 10:00",)),
        pd.DataFrame([{"date": "2026-11-06", "close": "9.99"}]), "2026-11-09", "2026-11-09", source="sina")
    assert not issues and events[0].prev_close == dec("9.99")


def test_unfinished_and_outside_request_bars_are_excluded_without_filling_gaps():
    f = frame(("2026-11-11 15:00", "2026-11-12 10:00", "2026-11-12 10:03", "2026-11-12 10:04"))
    events, _, audit = normalize(f, observed=datetime(2026, 11, 12, 10, 3, 30, tzinfo=CN))
    assert [b.time.minute for b in events] == [0, 3]
    assert audit["unfinished_excluded"] == 1 and audit["raw_count"] == 4
    assert audit["selected_count"] == 2


def test_no_requested_coverage_has_actionable_actual_range():
    with pytest.raises(ValueError, match="实际返回.*2026-11-10"):
        normalize(frame(("2026-11-10 10:00",)))


@pytest.mark.parametrize("times", [("2026-11-12 10:00", "2026-11-12 10:00"),
                                   ("2026-11-12 10:01", "2026-11-12 10:00")])
def test_duplicate_or_out_of_order_source_is_not_silently_sorted(times):
    with pytest.raises(ValueError, match="重复或乱序"):
        normalize(frame(times))


@pytest.mark.parametrize("quantity", ["-1", "1.5", "NaN"])
def test_invalid_quantity_is_not_truncated_into_liquidity(quantity):
    f = frame()
    f.loc[0, "成交量"] = quantity
    with pytest.raises(ValueError):
        normalize(f)


def test_first_day_ex_rights_requires_reference_even_with_no_overnight_position():
    events, issues, _ = normalize(action_dates={datetime(2026, 11, 12).date()})
    assert len(events) == 3 and "除权参考价" in issues[0]


def test_provider_zero_open_is_preserved_and_flagged():
    f = frame()
    f.loc[0, "开盘"] = "0"
    events, issues, _ = normalize(f)
    assert events[0].open == 0 and "不能补造" in issues[0]


def test_disconnect_does_not_claim_unproven_ip_ban():
    error_type = type("Push2RateLimitError", (Exception,), {})
    message = source_error(error_type("IP 被临时限流"), "eastmoney")
    assert "原因尚未确认" in message and "IP" not in message and "新浪" in message


def mock_provider(monkeypatch):
    import akshare as ak
    from astock import market
    f = frame().rename(columns={"时间": "day", "开盘": "open", "最高": "high", "最低": "low",
                                "收盘": "close", "成交量": "volume"})
    calls = []
    def minutes(**kwargs):
        calls.append(kwargs)
        return f
    monkeypatch.setattr(ak, "stock_zh_a_minute", minutes)
    monkeypatch.setattr(ak, "stock_zh_a_hist_tx", lambda **kwargs: daily())
    monkeypatch.setattr(market, "corporate_dates", lambda symbol: [])
    return calls


def test_download_persists_adapter_provenance_and_all_symbols(tmp_path, monkeypatch):
    calls = mock_provider(monkeypatch)
    output = Queue()
    download_history_worker(output, tmp_path, ["600000.SH", "510300.SH"], "1m", "2026-11-12", "2026-11-13")
    meta = list_datasets(tmp_path / "datasets")[0]
    assert meta["source"] == "akshare-sina" and meta["corporate_actions_verified"]
    assert [c["symbol"] for c in calls] == ["sh600000", "sh510300"]
    assert all(c["adjust"] == "" for c in calls)
    assert len(meta["provenance"]) == 2 and meta["provenance"]["510300.SH"]["adapter"] == "minute-bars-v2"
    _, events = load_dataset(tmp_path / "datasets", meta["id"])
    assert len(events) == 6 and events[0].volume == 12345
    assert events[0].prev_close == dec("9.9")


def test_missing_reference_or_action_evidence_is_saved_but_blocks_run(tmp_path, monkeypatch):
    mock_provider(monkeypatch)
    from astock import market
    def failure(symbol):
        raise ConnectionError("暂时断线")
    monkeypatch.setattr(market, "corporate_dates", failure)
    download_history_worker(Queue(), tmp_path, ["510300.SH"], "1m", "2026-11-12", "2026-11-13")
    meta = list_datasets(tmp_path / "datasets")[0]
    assert not meta["corporate_actions_verified"] and "无法核对权益" in meta["notes"]
    with pytest.raises(ValueError, match="权益"):
        load_dataset(tmp_path / "datasets", meta["id"])


def test_repeated_history_symbols_are_requested_once(tmp_path, monkeypatch):
    calls = mock_provider(monkeypatch)
    download_history_worker(Queue(), tmp_path, ["sh600000", "600000.SH"], "1m", "2026-11-12", "2026-11-13")
    assert len(calls) == 1
    meta = list_datasets(tmp_path / "datasets")[0]
    assert len(load_dataset(tmp_path / "datasets", meta["id"])[1]) == 3


def test_legacy_download_cannot_silently_reuse_moving_minute_reference(tmp_path):
    from astock.datasets import dataset_reader, write_dataset
    events, _, _ = normalize()
    meta = write_dataset(tmp_path, "旧版分钟", events, source="akshare-eastmoney", verified=True)
    with pytest.raises(ValueError, match="旧版分钟下载"):
        load_dataset(tmp_path, meta["id"])
    _, rows = dataset_reader(tmp_path, meta["id"], inspection=True)
    assert len(list(rows)) == 3


def test_download_dialog_source_dates_and_wrapped_guidance_fit(qtbot, tmp_path):
    from PySide6 import QtCore, QtWidgets
    from astock.window import MainWindow
    window = MainWindow(tmp_path, start_workers=False)
    qtbot.addWidget(window)
    window.show()
    errors = []
    def inspect():
        dialog = QtWidgets.QApplication.activeModalWidget()
        try:
            period = dialog.findChild(QtWidgets.QComboBox, "historyPeriod")
            period.setCurrentIndex(period.findData("1m"))
            source = dialog.findChild(QtWidgets.QComboBox, "historySource")
            assert source.currentData() == "sina" and source.findData("eastmoney") >= 0
            hint = dialog.findChild(QtWidgets.QLabel, "historyHint")
            size = hint.fontMetrics().boundingRect(hint.contentsRect(), QtCore.Qt.TextFlag.TextWordWrap, hint.text())
            assert hint.height() >= size.height()
            start = dialog.findChild(QtWidgets.QDateEdit, "historyStart")
            end = dialog.findChild(QtWidgets.QDateEdit, "historyEnd")
            assert start.date() == end.date().addDays(-7)
            assert period.findData("60m") >= 0
        except Exception as error:
            errors.append(error)
        finally:
            dialog.reject()
    QtCore.QTimer.singleShot(50, inspect)
    window.download_dialog()
    assert not errors, errors
    assert window.history_process is None
