"""Read-only public directory probe; output is separate from user account data."""
import argparse
import json
from pathlib import Path
import time

from astock.catalog import empty_catalog, fetch_catalog, publish_catalog


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="output/catalog-probe")
    args = parser.parse_args()
    root = Path(args.output)
    started = time.monotonic()
    value = fetch_catalog(lambda value: print(value["phase"], flush=True))
    publish_catalog(root, empty_catalog(), value)
    result = {"elapsed_seconds": round(time.monotonic() - started, 2),
              "segments": {key: {"count": len(part["records"]), "source": part["source"],
                                  "retrieved_at": part["refreshed_at"], "examples": part["records"][:2]}
                           for key, part in value["segments"].items()},
              "attempts": value["attempts"], "market_session_acceptance": False}
    root.mkdir(parents=True, exist_ok=True)
    (root / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
