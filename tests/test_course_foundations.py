"""Validate the exact foundation lesson resources, calculations and trading example."""
import json
from pathlib import Path
from queue import Queue
import re
import runpy

import numpy as np
import pandas as pd
import pytest

from astock.course_display import LabDisplay
from astock.datasets import ensure_demo, list_datasets
from astock.domain import MatchConfig
from astock.engine import Run
from astock.strategy import parameter_schema


ROOT = Path(__file__).resolve().parents[1] / "src/astock/course_content"


def test_foundation_curriculum_contract():
    entries = json.loads((ROOT / "catalogue-foundations.json").read_text(encoding="utf8"))
    assert [entry["id"] for entry in entries] == [f"q{number:02}" for number in range(1, 29)]
    for number, entry in enumerate(entries, 1):
        assert entry["kind"] == "course" and entry["status"] == "published"
        body = (ROOT / entry["body"]).read_text(encoding="utf8")
        assert len(re.findall(r"[\u4e00-\u9fff]", body)) >= (650 if number <= 6 else 2000), entry["id"]
        assert "## 练习\n" in body and "## 参考答案\n" in body
        assert "## 练习与解析" not in body
        assert "https://" in body, entry["id"]
        assert not re.search(r"```(?:python|py)\b", body), "Executable code must come from its source file"
        ids = {example["id"] for example in entry["examples"]}
        assert set(re.findall(r"\{\{code:([^}]+)\}\}", body)) == ids
        for example in entry["examples"]:
            assert (ROOT / example["file"]).is_file()
            assert example["environment"] in {"lab", "strategy", "notebook"}
            assert example["label"]
        check = entry["check"]
        assert check["question"] and check["explanation"] and check["answers"]
        assert all(isinstance(answer, str) and answer.strip() for answer in check["answers"])


@pytest.mark.parametrize("number", range(1, 29))
def test_all_foundation_examples_run_offline(number, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runpy.run_path(str(ROOT / "examples" / f"q{number:02}.py"), run_name="__main__")


@pytest.mark.parametrize("number", range(19, 29))
def test_indicator_outputs_use_serializable_lab_displays(number, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    display = LabDisplay()
    runpy.run_path(str(ROOT / "examples" / f"q{number:02}.py"), init_globals={"lab": display})
    assert any(item["kind"] == "table" for item in display.items)
    assert any(item["kind"] in {"lines", "bars"} for item in display.items)
    json.dumps(display.items, ensure_ascii=False, allow_nan=False)


def test_rsi_scaling_and_direction_invariants():
    namespace = runpy.run_path(str(ROOT / "examples/q23.py"))
    calculate = namespace["rsi_wilder"]
    prices = np.array([10., 11., 10., 12., 11., 13.])
    np.testing.assert_allclose(calculate(prices), calculate(2 * prices), equal_nan=True)
    unchanged = calculate([10, 11, 10, 12, 12])
    np.testing.assert_allclose(unchanged[3:], [75, 75])
    assert calculate([10, 11, 10, 12, 13])[-1] > 75
    assert calculate([10, 11, 10, 12, 11])[-1] < 75
    assert np.isnan(calculate([10, 11, 12])).all()
    with pytest.raises(ValueError):
        calculate(prices, period=0)


def test_rolling_features_do_not_depend_on_future_rows():
    namespace = runpy.run_path(str(ROOT / "examples/q11.py"))
    calculate = namespace["features"]
    original = pd.Series([20., 19., 21., 25., 24., 26., 28.])
    changed = original.copy()
    changed.iloc[5:] = [1000, 1]
    pd.testing.assert_frame_equal(calculate(original).iloc[:5], calculate(changed).iloc[:5])


def test_atr_rejects_invalid_ohlc_and_handles_scale():
    namespace = runpy.run_path(str(ROOT / "examples/q26.py"))
    calculate = namespace["true_ranges"]
    high, low, close = namespace["high"], namespace["low"], namespace["close"]
    np.testing.assert_allclose(calculate(2 * high, 2 * low, 2 * close), 2 * namespace["tr"])
    invalid_low = low.copy()
    invalid_low[1] = 14  # Close remains 12.5: impossible OHLC.
    with pytest.raises(ValueError, match="low <= close <= high"):
        calculate(high, invalid_low, close)
    assert np.isnan(namespace["wilder_atr"]([2, 3], 3)).all()


def test_q06_actual_strategy_fills_and_reconciles(tmp_path):
    ensure_demo(tmp_path / "datasets")
    dataset = next(row for row in list_datasets(tmp_path / "datasets") if row["kind"] == "bar")
    code = (ROOT / "examples/q06-strategy.py").read_text(encoding="utf8")
    parameters = {name: value["default"] for name, value in parameter_schema(code).items()}
    run = Run({"name": "课程06真实引擎验证", "mode": "backtest", "dataset": dataset["id"],
               "code": code, "parameters": parameters, "initial": 100000,
               "config": MatchConfig(), "speed": 1000}, tmp_path, Queue())
    try:
        while run.status == "RUNNING":
            run.step()
        assert run.status == "COMPLETED", run.logs[-10:]
        assert run.broker.trades, "The real strategy must produce fills, not merely define a class"
        run.broker.check_invariants()
        assert run.broker.account.cash >= 0
        for trade in run.broker.trades:
            order = next(order for order in run.broker.orders if order.id == trade.order_id)
            assert trade.time > order.created
    finally:
        if run.host:
            run.host.close()
