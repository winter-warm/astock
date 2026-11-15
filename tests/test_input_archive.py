from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta
from queue import Queue

import pytest

from astock import engine
from astock.datasets import Recorder, load_dataset, write_dataset
from astock.domain import CN, MatchConfig, Quote, dec, dumps, event_clock, loads
from astock.engine import Run
from astock.input_archive import InputArchive, read_inputs
from astock.storage import Store


AT = datetime(2026, 11, 12, 10, tzinfo=CN)
CODE = '''
class UserStrategy(Strategy):
    def initialize(self, ctx):
        self.seen = set()
    def on_quote(self, ctx, quote):
        ctx.explain("observed", symbol=quote.symbol, source_time=quote.time, clock=ctx.now)
        if quote.symbol not in self.seen:
            self.seen.add(quote.symbol)
            ctx.order(quote.symbol, "BUY", 100, quote.last, "first fresh observation")
'''


def quote(seconds, received=None, volume=100000, symbol="600000.SH"):
    return Quote(symbol, AT + timedelta(seconds=seconds), AT + timedelta(seconds=received or seconds),
                 dec(10), dec(10), dec(10), 100000, 100000, volume, dec(10), dec(11), dec(9))


def test_live_inputs_replay_original_latency_duplicates_and_arrival_order(tmp_path, monkeypatch):
    store = Store(tmp_path)
    request = {"mode": "live", "name": "输入一致性", "symbols": ["600000.SH", "000001.SZ"],
               "code": CODE, "config": MatchConfig(slippage_ticks=0)}
    run = Run(request, tmp_path, Queue())
    inputs = [(quote(0, 1), 2), (quote(5, 6, 100500), 25),  # Queue delay, not just collector delay.
              (quote(30, 31, 103000), 32), (quote(35, 36, 103500), 37),
              (quote(35, 37, 999999), 38), (quote(34, 38, 999999), 39),
              (quote(32, 39, 100000, "000001.SZ"), 40),
              (quote(40, 41, 104000), 42), (quote(43, 44, 101000, "000001.SZ"), 45)]
    try:
        for q, observed in inputs:
            monkeypatch.setattr(engine, "now_cn", lambda at=observed: AT + timedelta(seconds=at))
            run.event(q, live=True)
            run.sample_equity()
            run.persist(store)
        assert [t.quantity for t in run.broker.trades] == [50, 50, 100]
        assert run.broker.trades[0].time == AT + timedelta(seconds=35)
        run.stop()
        run.persist(store)
        saved = store.load_run(run.id)
        archive = saved["manifest"]["input_archive"]
        assert archive["count"] == len(inputs) and archive["state"] == "closed"
        meta, data = load_dataset(tmp_path / "datasets", saved["manifest"]["dataset"]["id"])
        assert meta["ordering"] == "arrival"
        assert data[1].received == AT + timedelta(seconds=6)
        assert data[1].observed == AT + timedelta(seconds=25)
        assert data[4].time == data[3].time and data[5].time < data[4].time
        replay = Run({**request, "mode": "replay", "dataset": meta["id"]}, tmp_path, Queue())
        while replay.status == "RUNNING":
            replay.step()
        assert dumps(replay.broker.snapshot()) == dumps(run.broker.snapshot())
        assert replay.curve == run.curve
        assert replay.history == run.history
        assert len([x for x in replay.logs if x["message"] == "observed"]) == 6
    finally:
        run.stop()
        store.close()


def test_recorder_preserves_duplicate_inputs_and_blocks_received_clock_regression(tmp_path):
    recording = Recorder(tmp_path)
    recording.append([quote(0), quote(0, 5), quote(-1, 6)])
    meta = recording.finish()
    _, data = load_dataset(tmp_path, meta["id"])
    assert len(data) == 3 and data[-1].time < data[0].time
    meta = write_dataset(tmp_path, "bad-clock", [quote(5), quote(6, 4)], verified=True)
    with pytest.raises(ValueError, match="接收时钟倒退"):
        load_dataset(tmp_path, meta["id"])


def test_committed_archive_prefix_ignores_orphan_and_detects_tampering(tmp_path):
    archive = InputArchive(tmp_path, "test")
    archive.append(replace(quote(0), observed=AT))
    saved = deepcopy(archive.flush())
    archive.append(replace(quote(5), observed=AT + timedelta(seconds=5)))
    archive.flush()  # Simulate a crash before the second prefix reached SQLite.
    assert len(read_inputs(tmp_path, saved)) == 1
    assert len(read_inputs(tmp_path, archive.manifest)) == 2
    path = tmp_path / saved["directory"] / saved["parts"][0]["file"]
    with path.open("ab") as stream:
        stream.write(b"tampering")
    with pytest.raises(ValueError, match="片段校验"):
        read_inputs(tmp_path, saved)


def test_capture_write_failure_stops_account_and_preserves_input_in_sqlite(tmp_path, monkeypatch):
    run = Run({"mode": "manual", "symbols": ["600000.SH"]}, tmp_path, Queue())
    monkeypatch.setattr(engine, "now_cn", lambda: AT)
    run.event(quote(0), live=True)
    def fail():
        raise OSError("disk full")
    monkeypatch.setattr(run.input_archive, "flush", fail)
    store = Store(tmp_path)
    try:
        run.persist(store)
        saved = store.load_run(run.id)
        assert store.runs()[0]["status"] == "ERROR"
        assert saved["manifest"]["input_archive"]["state"] == "error"
        payload = store.db.execute("SELECT payload FROM journals WHERE kind='unarchived_input'").fetchone()[0]
        assert event_clock(loads(payload)) == AT
        assert "disk full" in saved["result"]["logs"][-1]["message"]
    finally:
        store.close()


def test_multi_day_automatic_archive_is_retained_but_cannot_bypass_action_check(tmp_path, monkeypatch):
    run = Run({"mode": "manual", "symbols": ["600000.SH"]}, tmp_path, Queue())
    for day in (0, 1):
        at = AT + timedelta(days=day)
        monkeypatch.setattr(engine, "now_cn", lambda at=at: at)
        run.event(replace(quote(0), time=at, received=at), live=True)
    store = Store(tmp_path)
    try:
        run.stop()
        run.persist(store)
        meta = run.manifest["dataset"]
        assert meta["count"] == 2
        assert not meta["corporate_actions_verified"]
        with pytest.raises(ValueError, match="权益"):
            load_dataset(tmp_path / "datasets", meta["id"])
    finally:
        store.close()
