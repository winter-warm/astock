"""Verify the captured real after-hours feed replays without synthetic fills."""
from pathlib import Path
from queue import Queue

from astock.datasets import list_datasets
from astock.domain import dumps
from astock.engine import Run
from astock.strategy import TEMPLATES, parameter_schema


if __name__ == "__main__":
    root = Path("output/live-ui-data")
    dataset = next(x for x in list_datasets(root / "datasets") if x["source"] == "tencent-recording")
    code = TEMPLATES["双均线趋势"]["code"]
    run = Run({"mode": "replay", "dataset": dataset["id"], "code": code,
               "parameters": {k: v["default"] for k, v in parameter_schema(code).items()},
               "speed": 1000}, root, Queue())
    try:
        while run.status == "RUNNING":
            run.step()
        assert run.status == "COMPLETED"
        assert run.index == dataset["count"]
        assert not run.broker.trades
        run.broker.check_invariants()
        result = {"dataset": dataset, "processed": run.index, "status": run.status,
                  "trades": len(run.broker.trades), "equity": run.broker.account.equity}
        target = Path("output/live-ui-qa/recording-replay.json")
        target.write_text(dumps(result), encoding="utf-8")
        print(target)
    finally:
        if run.host:
            run.host.close()
