from PySide6 import QtCore, QtWidgets

from astock.backtest_setup import BacktestSetup


def dataset(start="2026-01-01", end="2026-01-05"):
    return {"name": "教学", "symbols": ["510300.SH", "159915.SZ"], "start": start,
            "end": end, "period": "1d", "demo": True, "source": "synthetic"}


def test_presets_are_nonoverlapping_and_keep_other_settings(qtbot):
    dialog = BacktestSetup(dataset(), {"start": "2026-01-02", "end": "2026-01-04",
                                      "benchmark": "159915.SZ"}, 200000)
    qtbot.addWidget(dialog)
    assert dialog.options()["start"] == "2026-01-02"
    dialog.range_buttons["first"].click()
    assert dialog.options() == {"start": "2026-01-01", "end": "2026-01-03", "benchmark": "159915.SZ"}
    dialog.range_buttons["last"].click()
    assert dialog.options() == {"start": "2026-01-04", "end": "2026-01-05", "benchmark": "159915.SZ"}
    assert dialog.capital.value() == 200000
    dialog.range_buttons["full"].click()
    assert dialog.options()["start"] == "2026-01-01"
    assert dialog.options()["end"] == "2026-01-05"
    assert "合成教学" in dialog.coverage.text()


def test_single_day_cannot_be_split(qtbot):
    dialog = BacktestSetup(dataset("2026-01-02", "2026-01-02"), {}, 100000)
    qtbot.addWidget(dialog)
    assert not dialog.range_buttons["first"].isEnabled()
    assert not dialog.range_buttons["last"].isEnabled()
    dialog.select_range("last")
    assert dialog.options()["start"] == dialog.options()["end"] == "2026-01-02"


def test_reversed_dates_still_require_correction(qtbot):
    dialog = BacktestSetup(dataset(), {}, 100000)
    qtbot.addWidget(dialog)
    dialog.dates[0].setDate(QtCore.QDate(2026, 1, 5))
    dialog.dates[1].setDate(QtCore.QDate(2026, 1, 1))
    dialog.save()
    assert dialog.result() != QtWidgets.QDialog.DialogCode.Accepted
    assert "不能晚于" in dialog.error.text()
    dialog.range_buttons["full"].click()
    assert not dialog.error.text()
    dialog.save()
    assert dialog.result() == QtWidgets.QDialog.DialogCode.Accepted
