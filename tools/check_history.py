"""One bounded public-history probe; network errors are recorded, not hidden."""
from pathlib import Path
from queue import Queue
import sys

from astock.domain import dumps
from astock.market import download_history_worker


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    root = Path("output/history-check").resolve()
    root.mkdir(parents=True, exist_ok=True)
    output = Queue()
    download_history_worker(output, root, ["510300.SH", "600000.SH"], "1d", "2026-11-02", "2026-11-13")
    messages = []
    while not output.empty():
        message = output.get()
        messages.append(message)
        print(message.get("message", message.get("type")))
    (root / "probe.json").write_text(dumps(messages), encoding="utf-8")
    if not any(x["type"] == "history_done" and x["meta"]["corporate_actions_verified"] for x in messages):
        raise SystemExit(1)
