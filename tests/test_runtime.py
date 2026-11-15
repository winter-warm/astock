import io
import multiprocessing
from pathlib import Path
import runpy
import sys
from types import SimpleNamespace

from astock.runtime import ensure_standard_streams


def test_windowless_provider_progress_and_print_do_not_fail(monkeypatch):
    from akshare.utils.tqdm import get_tqdm
    with monkeypatch.context() as patch:
        patch.setattr(sys, "stdout", None)
        patch.setattr(sys, "stderr", None)
        ensure_standard_streams()
        stdout, stderr = sys.stdout, sys.stderr
        try:
            print("中文行情进度")
            assert list(get_tqdm()(range(3), leave=False)) == [0, 1, 2]
            ensure_standard_streams()
            assert sys.stdout is stdout and sys.stderr is stderr
        finally:
            stdout.close()
            stderr.close()


def test_existing_console_or_capture_streams_are_preserved(monkeypatch):
    stdout, stderr = io.StringIO(), io.StringIO()
    monkeypatch.setattr(sys, "stdout", stdout)
    monkeypatch.setattr(sys, "stderr", stderr)
    ensure_standard_streams()
    print("正常输出")
    sys.stderr.write("正常错误")
    assert stdout.getvalue() == "正常输出\n" and stderr.getvalue() == "正常错误"


def test_frozen_worker_dispatch_has_streams_before_freeze_support(monkeypatch):
    calls = []
    def dispatch():
        assert sys.stdout is not None and sys.stderr is not None
        sys.stderr.write("工作进程进度")
        calls.append("worker_dispatch")
    with monkeypatch.context() as patch:
        patch.setattr(sys, "stdout", None)
        patch.setattr(sys, "stderr", None)
        patch.setattr(multiprocessing, "freeze_support", dispatch)
        patch.setitem(sys.modules, "astock.app", SimpleNamespace(main=lambda: calls.append("gui")))
        try:
            runpy.run_path(str(Path(__file__).parents[1] / "desktop_entry.py"), run_name="__main__")
            assert calls == ["worker_dispatch", "gui"]
        finally:
            for stream in (sys.stdout, sys.stderr):
                if stream is not None:
                    stream.close()
