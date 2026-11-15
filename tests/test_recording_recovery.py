import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from dataclasses import replace
from datetime import datetime, timedelta
import multiprocessing as mp
from pathlib import Path
from queue import Queue
from threading import Thread
from types import SimpleNamespace

import pytest

from astock import market, recordings
from astock.datasets import Recorder, dataset_digest, list_datasets, load_dataset
from astock.domain import CN, Quote, dec, dumps
from astock.operations_ui import OperationDialog
from astock.recordings import RecordingBusy, finalize_recording, recovery_job


def quote(index=0):
    at = datetime(2026, 11, 13, 10, tzinfo=CN) + timedelta(seconds=index)
    return Quote("600000.SH", at, at, dec(10), dec(10), dec(10), 100000, 100000,
                 100000 + index * 1000, dec(10), dec(11), dec(9))


def held_writer(root, output, stop):
    recorder = Recorder(root)
    recorder.append([quote()])
    output.put(str(recorder.directory))
    stop.wait(30)
    recorder.seal()


def test_live_writer_is_skipped_and_abrupt_exit_releases_os_lease(tmp_path):
    context = mp.get_context("spawn")
    output, stop = context.Queue(), context.Event()
    child = context.Process(target=held_writer, args=(str(tmp_path), output, stop))
    child.start()
    try:
        directory = Path(output.get(timeout=10))
        with pytest.raises(RecordingBusy):
            finalize_recording(directory, tmp_path)
        assert not list(tmp_path.glob("*.json"))
        child.terminate()
        child.join(5)
        meta = finalize_recording(directory, tmp_path)
        assert load_dataset(tmp_path, meta["id"])[1] == [quote()]
        assert meta["recording_parts"] == 1
    finally:
        if child.is_alive():
            stop.set()
            child.terminate()
        child.join(5)
        output.close()


def test_recovery_preserves_duplicates_and_original_parts_and_is_idempotent(tmp_path):
    recorder = Recorder(tmp_path)
    events = [quote(), replace(quote(), received=quote(5).received),
              replace(quote(-1), received=quote(6).received)]
    recorder.append(events[:2])
    recorder.append(events[2:])
    raw = {file.name: dataset_digest(file) for file in recorder.directory.glob("*.parquet")}
    recorder.seal()
    with pytest.raises(ValueError, match="停止"):
        recorder.append([quote(10)])
    first = finalize_recording(recorder.directory, tmp_path)
    second = finalize_recording(recorder.directory, tmp_path)
    assert first == second and len(list_datasets(tmp_path)) == 1
    assert load_dataset(tmp_path, first["id"])[1] == events
    assert raw == {file.name: dataset_digest(file) for file in recorder.directory.glob("*.parquet")}


@pytest.mark.parametrize("failure", ["metadata", "marker"])
def test_interrupted_publication_retries_without_duplicate_or_lost_data(tmp_path, monkeypatch, failure):
    recorder = Recorder(tmp_path)
    recorder.append([quote()])
    recorder.seal()
    identity = "record" + recorder.directory.name.removeprefix("recording_")
    original = Path.rename
    with monkeypatch.context() as patch:
        if failure == "metadata":
            def interrupt(path, target):
                if Path(target) == tmp_path / (identity + ".json"):
                    raise OSError("injected interruption before metadata")
                return original(path, target)
            patch.setattr(Path, "rename", interrupt)
        else:
            def interrupt(*_):
                raise OSError("injected interruption before marker")
            patch.setattr(recordings, "write_marker", interrupt)
        with pytest.raises(OSError, match="injected"):
            finalize_recording(recorder.directory, tmp_path)
    assert (tmp_path / (identity + ".parquet")).is_file()
    assert not (recorder.directory / "finalized.json").exists()
    meta = finalize_recording(recorder.directory, tmp_path)
    assert meta["id"] == identity and load_dataset(tmp_path, identity)[1] == [quote()]
    assert len(list_datasets(tmp_path)) == 1


def test_recovery_isolates_bad_directory_and_skips_writer(tmp_path):
    root = tmp_path / "datasets"
    good, broken, active = [Recorder(root) for _ in range(3)]
    for recorder in (good, broken, active):
        recorder.append([quote()])
    good.seal()
    broken.seal()
    (broken.directory / "00000000.parquet").write_bytes(b"damaged")
    try:
        result = recovery_job({"root": str(tmp_path), "stage": str(root / ".imports/job")}, lambda _: None)
        assert result["completed"] == result["errors"] == result["busy"] == 1
        assert len(list_datasets(root)) == 1
        assert (broken.directory / "00000000.parquet").read_bytes() == b"damaged"
        assert not (active.directory / "finalized.json").exists()
    finally:
        active.seal()


def test_missing_part_or_reversed_received_clock_is_not_published(tmp_path):
    for invalid in ("missing", "clock"):
        recorder = Recorder(tmp_path)
        recorder.append([quote()])
        recorder.append([quote(-1) if invalid == "clock" else quote(5)])
        recorder.seal()
        if invalid == "missing":
            (recorder.directory / "00000000.parquet").unlink()
        with pytest.raises(ValueError, match="缺号|倒退"):
            finalize_recording(recorder.directory, tmp_path)
    assert not list_datasets(tmp_path)


def test_unknown_same_name_file_is_preserved_and_cross_day_requires_equity_check(tmp_path):
    recorder = Recorder(tmp_path)
    recorder.append([quote(), quote(86400)])
    recorder.seal()
    identity = "record" + recorder.directory.name.removeprefix("recording_")
    target = tmp_path / (identity + ".parquet")
    target.write_bytes(b"unrelated original")
    with pytest.raises(ValueError, match="不同"):
        finalize_recording(recorder.directory, tmp_path)
    assert target.read_bytes() == b"unrelated original"
    target.unlink()
    meta = finalize_recording(recorder.directory, tmp_path)
    assert not meta["corporate_actions_verified"]
    with pytest.raises(ValueError, match="权益"):
        load_dataset(tmp_path, meta["id"])


def test_cancel_after_a_completed_directory_retains_it_and_raw_unfinished_parts(qtbot, tmp_path):
    first, second = Recorder(tmp_path / "datasets"), Recorder(tmp_path / "datasets")
    first.append([quote()])
    second.append([replace(quote(index), time=quote().time) for index in range(12000)])
    first.seal()
    second.seal()
    completed = finalize_recording(first.directory, first.root)
    raw = dataset_digest(second.directory / "00000000.parquet")
    dialog = OperationDialog(tmp_path, "recover")
    qtbot.addWidget(dialog)
    job = dialog.jobs.active["recover"]
    dialog.cancel()
    dialog.close()
    assert not job["process"].is_alive()
    assert not Path(job["request"]["stage"]).exists()
    assert load_dataset(first.root, completed["id"])[1] == [quote()]
    assert dataset_digest(second.directory / "00000000.parquet") == raw
    resumed = finalize_recording(second.directory, second.root)
    assert resumed["count"] == 12000 and len(list_datasets(first.root)) == 2


def test_market_stop_recording_never_merges_parts_and_collector_continues(tmp_path, monkeypatch):
    class LocalQueue(Queue):
        def cancel_join_thread(self):
            pass
    clock = [0.0]
    class Provider:
        def quotes(self, symbols):
            return [quote(int(clock[0]))]
    def forbidden(*_):
        raise AssertionError("collector must not merge recordings")
    monkeypatch.setattr(market, "TencentProvider", Provider)
    monkeypatch.setattr(market, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    monkeypatch.setattr(Recorder, "finish", forbidden)
    commands, engine, output = LocalQueue(), LocalQueue(), LocalQueue()
    worker = Thread(target=market.market_worker, args=(commands, engine, output, tmp_path), daemon=True)
    worker.start()
    def until(kind):
        for _ in range(30):
            message = output.get(timeout=2)
            if message["type"] == kind:
                return message
        raise AssertionError(kind)
    try:
        commands.put({"op": "record", "enabled": True})
        assert until("recording_state")["enabled"]
        commands.put({"op": "connect", "symbols": ["600000.SH"]})
        assert engine.get(timeout=3)["quotes"] == [quote()]
        commands.put({"op": "record", "enabled": False})
        directory = tmp_path / "datasets" / until("recording_sealed")["directory"]
        assert (directory / "sealed.json").exists() and not list_datasets(tmp_path / "datasets")
        clock[0] = 5
        commands.put({"op": "wake"})
        assert engine.get(timeout=3)["quotes"] == [quote(5)]
        assert finalize_recording(directory, directory.parent)["count"] == 1
    finally:
        commands.put({"op": "shutdown"})
        worker.join(3)
        assert not worker.is_alive()


def test_empty_recording_and_invalid_path_do_not_create_fake_dataset(tmp_path):
    recorder = Recorder(tmp_path)
    recorder.seal()
    assert finalize_recording(recorder.directory, tmp_path) is None
    assert not list_datasets(tmp_path)
    with pytest.raises(ValueError, match="目录"):
        finalize_recording(recorder.directory, tmp_path / "elsewhere")
    # Old releases' finalized markers remain readable.
    complete = Recorder(tmp_path)
    complete.append([quote()])
    meta = complete.finish()
    (complete.directory / "finalized.json").write_text(dumps({"dataset": meta["id"]}), encoding="utf-8")
    assert finalize_recording(complete.directory, tmp_path)["id"] == meta["id"]
