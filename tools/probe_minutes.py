"""Bounded, read-only minute-source check. A rejected endpoint remains a failed check."""
from pathlib import Path
from queue import Queue

from astock.domain import dumps
from astock.market import download_history_worker


def main():
    from akshare.utils.context import config
    config.timeout = (5, 10)
    root = Path("output/minute-check-016").resolve()
    root.mkdir(parents=True, exist_ok=True)
    results = []
    for symbol in ("600000.SH", "510300.SH"):
        output = Queue()
        download_history_worker(output, root, [symbol], "1m", "2026-11-09", "2026-11-13")
        messages = []
        while not output.empty():
            message = output.get_nowait()
            messages.append(message)
            print(symbol, message.get("type"), message.get("message", ""), flush=True)
        results.append({"symbol": symbol, "messages": messages,
                        "passed": any(m["type"] == "history_done" and m["meta"]["corporate_actions_verified"] for m in messages)})
    (root / "probe.json").write_text(dumps(results), encoding="utf-8")


if __name__ == "__main__":
    main()
