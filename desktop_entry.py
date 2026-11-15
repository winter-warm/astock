import multiprocessing
from astock.runtime import ensure_standard_streams

if __name__ == "__main__":
    # freeze_support dispatches frozen children before app.main is entered.
    ensure_standard_streams()
    multiprocessing.freeze_support()
    try:
        from astock.app import main
        main()
    except Exception:
        import sys
        import traceback
        from pathlib import Path
        path = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent
        try:
            (path / "startup-error.log").write_text(traceback.format_exc(), encoding="utf-8")
        except OSError:
            pass
        raise
