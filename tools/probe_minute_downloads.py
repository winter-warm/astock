"""Verify all remaining minute periods against actual public stock/ETF history."""
from pathlib import Path
from queue import Queue

from astock.datasets import load_dataset
from astock.domain import dumps
from astock.market import download_history_worker


def main():
    root = Path("output/minute-periods-010").resolve()
    root.mkdir(parents=True, exist_ok=True)
    results = []
    for period in ("5m", "15m", "30m", "60m"):
        output = Queue()
        download_history_worker(output, root, ["600000.SH", "510300.SH"], period,
                                "2026-11-12", "2026-11-13", "sina")
        messages = []
        while not output.empty():
            messages.append(output.get_nowait())
        result = {"period": period, "source_is_real": True, "passed": False}
        try:
            done = next(m for m in messages if m["type"] == "history_done")
            meta, events = load_dataset(root / "datasets", done["meta"]["id"])
            result.update(passed=True, count=len(events), meta=meta)
        except Exception as error:
            result.update(error=str(error), messages=messages)
        results.append(result)
        print(period, result["passed"], result.get("count"), flush=True)
        (root / "probe.json").write_text(dumps(results), encoding="utf-8")


if __name__ == "__main__":
    main()
