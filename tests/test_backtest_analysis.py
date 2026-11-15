import pytest

from astock.backtest_analysis import analyze_curve, diagnostics_html


def point(time, equity, benchmark=100):
    return {"time": time, "equity": equity, "benchmark": benchmark}


def test_intraday_drawdown_is_not_lost_when_daily_close_recovers():
    curve = [point("2026-01-05 09:30:00", 120), point("2026-01-05 10:00:00", 90),
             point("2026-01-05 15:00:00", 120), point("2026-02-02 15:00:00", 132, 110)]
    result = analyze_curve(curve, 100)
    assert result["days"] == 2
    assert result["drawdown"] == pytest.approx(.25)
    assert result["trough"] == "2026-01-05 10:00:00"
    assert result["recovery"] == "2026-01-05 15:00:00"
    assert result["monthly"][0]["return"] == pytest.approx(.2)
    assert result["monthly"][1]["return"] == pytest.approx(.1)
    assert result["monthly"][1]["excess"] == pytest.approx(0)


def test_initial_loss_and_later_deeper_drawdown_reset_recovery():
    result = analyze_curve([point("2026-01-01", 90), point("2026-01-02", 100),
                            point("2026-01-03", 80)], 100)
    assert result["drawdown"] == pytest.approx(.2)
    assert result["recovery"] is None
    assert result["worst_day"] == ("2026-01-03", pytest.approx(-.2))
    assert result["monthly"][0]["days"] == 3


def test_empty_and_zero_equity_do_not_invent_returns():
    assert analyze_curve([], 100)["monthly"] == []
    assert "运行后" in diagnostics_html([], 100)
    result = analyze_curve([point("2026-01-01", 0), point("2026-02-02", 0)], 100)
    assert result["monthly"][1]["return"] is None


def test_monthly_returns_compound_and_missing_months_are_not_filled():
    curve = [point("2026-01-29 10:00:00", 105, 102),
             point("2026-01-29 15:00:00", 110, 105),
             point("2026-03-03 15:00:00", 99, 115.5)]
    result = analyze_curve(curve, 100)
    january, march = result["monthly"]
    assert [row["month"] for row in result["monthly"]] == ["2026-01", "2026-03"]
    assert january["days"] == 1
    assert january["return"] == pytest.approx(.1)
    assert march["return"] == pytest.approx(-.1)
    assert march["benchmark"] == pytest.approx(.1)
    assert march["excess"] == pytest.approx(-.2)
    assert (1 + january["return"]) * (1 + march["return"]) - 1 == pytest.approx(-.01)
    assert "<td>-20.00</td>" in diagnostics_html(curve, 100)


def test_equal_later_drawdown_keeps_first_episode_and_its_recovery():
    curve = [point("2026-01-01", 100), point("2026-01-02", 80),
             point("2026-01-03", 100), point("2026-01-04", 80)]
    result = analyze_curve(curve, 100)
    assert result["trough"] == "2026-01-02"
    assert result["recovery"] == "2026-01-03"


def test_no_drawdown_reports_no_recovery_needed():
    curve = [point("2026-01-01", 100), point("2026-01-02", 110)]
    result = analyze_curve(curve, 100)
    assert result["drawdown"] == 0
    assert result["recovery"] is None
    assert "无回撤" in diagnostics_html(curve, 100)

