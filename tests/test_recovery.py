import multiprocessing as mp
import time
from queue import Empty

import pytest

from astock.datasets import ensure_demo, list_datasets
from astock.engine import engine_worker
from astock.storage import Store
from astock.strategy import TEMPLATES, parameter_schema


def test_queued_update_stays_at_committed_revision_until_delayed_serialization(tmp_path, monkeypatch):
    """Queue.put returns before its feeder pickles; later fills must not leak backwards."""
    import pickle
    from dataclasses import replace
    from datetime import datetime, timedelta
    from queue import Queue
    from astock import engine
    from astock.domain import CN, MatchConfig, Quote, dec, dumps
    clock = [datetime(2026, 11, 12, 10, tzinfo=CN)]
    monkeypatch.setattr(engine, 'now_cn', lambda: clock[0])
    store = Store(tmp_path)
    run = engine.Run({'mode': 'manual', 'symbols': ['600000.SH'],
                      'config': MatchConfig(slippage_ticks=0)}, tmp_path, Queue())
    try:
        quote = Quote('600000.SH', clock[0], clock[0], dec(10), dec(10), dec(10),
                      100000, 100000, 100000, dec(10), dec(11), dec(9))
        run.event(quote, live=True)
        run._apply({'commands': [{'op': 'order', 'symbol': quote.symbol,
                                 'side': 'BUY', 'quantity': 100, 'price': dec(10)}]})
        run.persist(store)
        committed = store.load_run(run.id)
        queued = run.message()  # Deliberately delay pickling until after a later event.
        clock[0] += timedelta(seconds=5)
        run.event(replace(quote, time=clock[0], received=clock[0], volume=100500), live=True)
        run.sample_equity()
        assert run.broker.trades[0].quantity == 50
        assert not store.load_run(run.id)['snapshot']['trades']
        received = pickle.loads(pickle.dumps(queued))
        for key in ('snapshot', 'result', 'manifest'):
            assert dumps(received[key]) == dumps(committed[key]), key
        assert not received['snapshot']['trades']
        assert received['snapshot']['orders'][0].filled == 0
    finally:
        store.close()


def test_corrupt_account_is_isolated_and_other_accounts_still_recover(tmp_path):
    from astock.broker import Broker
    from astock.domain import dec
    from astock.rules import default_rule
    store = Store(tmp_path)
    for name in ("healthy", "damaged"):
        b = Broker({"600000.SH": default_rule("600000.SH")})
        if name == "damaged":
            b.account.cash += dec(1)
        store.save_run(name, name, "manual", "RUNNING", {}, b.snapshot(), {})
    context = mp.get_context("spawn")
    commands, output = context.Queue(), context.Queue()
    process = context.Process(target=engine_worker, args=(commands, output, str(tmp_path)))
    process.start()
    try:
        message = output.get(timeout=12)
        assert message["type"] == "engine_ready"
        assert {r["id"]: r["status"] for r in message["runs"]} == {
            "healthy": "RECOVERED", "damaged": "RECOVERY_ERROR"}
        damaged = store.load_run("damaged")["snapshot"]
        assert damaged["account"].cash == 100001  # Preserve evidence, never invent an adjustment.
        assert "现金流水不一致" in damaged["accounting_error"]
        commands.put({"op": "start", "mode": "manual", "symbols": ["600000.SH"]})
        deadline = time.monotonic() + 8
        created = False
        while time.monotonic() < deadline:
            if output.get(timeout=2)["type"] == "run_created":
                created = True
                break
        assert created and process.is_alive()
        commands.put({"op": "shutdown"})
        process.join(8)
        assert process.exitcode == 0
    finally:
        if process.is_alive():
            process.terminate()
            process.join(3)
        store.close()


def clocked_engine(commands, output, root):
    """Give the real spawned engine a controlled market-session observation clock."""
    from datetime import datetime
    from astock import engine
    from astock.domain import CN
    class ClockedCommands:
        clock = datetime(2026, 11, 12, 10, tzinfo=CN)
        def get(self, timeout):
            request = commands.get(timeout=timeout)
            self.clock = request.pop("test_clock", self.clock)
            return request
    incoming = ClockedCommands()
    engine.now_cn = lambda: incoming.clock
    engine.engine_worker(incoming, output, root)


@pytest.mark.parametrize("corrupt_input", [False, True])
def test_forced_engine_kill_after_partial_fill_recovers_exact_account(tmp_path, corrupt_input):
    from datetime import datetime, timedelta
    from astock.domain import CN, MatchConfig, Quote, dec, dumps
    from astock.datasets import load_dataset
    at = datetime(2026, 11, 12, 10, tzinfo=CN)
    context = mp.get_context("spawn")
    commands, output = context.Queue(), context.Queue()
    process = context.Process(target=clocked_engine, args=(commands, output, str(tmp_path)))
    def wait_for(predicate):
        until = time.monotonic() + 12
        while time.monotonic() < until:
            try:
                message = output.get(timeout=.2)
            except Empty:
                continue
            if predicate(message):
                return message
        raise AssertionError("engine response missing")
    process.start()
    restarted = None
    store = None
    try:
        wait_for(lambda m: m["type"] == "engine_ready")
        commands.put({"op": "start", "mode": "manual", "symbols": ["600000.SH"],
                      "config": MatchConfig(slippage_ticks=0)})
        run_id = wait_for(lambda m: m["type"] == "run_created")["id"]
        q = Quote("600000.SH", at, at, dec(10), dec(10), dec(10), 100000, 100000,
                  100000, dec(10), dec(11), dec(9))
        commands.put({"op": "quotes", "quotes": [q], "test_clock": at})
        commands.put({"op": "manual_order", "id": run_id, "order": {
            "symbol": q.symbol, "side": "BUY", "quantity": 100, "price": dec(10)}})
        from dataclasses import replace
        commands.put({"op": "quotes", "test_clock": at + timedelta(seconds=5), "quotes": [
            replace(q, time=at + timedelta(seconds=5), received=at + timedelta(seconds=5), volume=100500)]})
        state = wait_for(lambda m: m["type"] == "run_update" and bool(m["snapshot"]["trades"]))
        assert state["snapshot"]["orders"][0].status == "PARTIAL"
        assert state["snapshot"]["trades"][0].quantity == 50
        assert state["frozen"] > 0
        process.terminate()  # Deliberate hard termination; no shutdown cleanup.
        process.join(5)
        assert not process.is_alive()
        store = Store(tmp_path)
        before = store.load_run(run_id)
        assert store.runs()[0]["status"] == "RUNNING"
        if corrupt_input:
            archive = before["manifest"]["input_archive"]
            path = tmp_path / archive["directory"] / archive["parts"][0]["file"]
            with path.open("ab") as stream:
                stream.write(b"invalid")
        commands2, output2 = context.Queue(), context.Queue()
        restarted = context.Process(target=engine_worker, args=(commands2, output2, str(tmp_path)))
        restarted.start()
        ready = output2.get(timeout=12)
        assert ready["type"] == "engine_ready" and ready["runs"][0]["status"] == "RECOVERED"
        after = store.load_run(run_id)
        assert dumps(after["snapshot"]["account"]) == dumps(before["snapshot"]["account"])
        assert dumps(after["snapshot"]["trades"]) == dumps(before["snapshot"]["trades"])
        assert after["snapshot"]["orders"][0].status == "CANCELED"
        assert after["snapshot"]["orders"][0].filled == 50
        if corrupt_input:
            assert after["manifest"]["input_archive"]["state"] == "error"
            assert not after["manifest"]["dataset"]
            assert store.db.execute("SELECT COUNT(*) FROM journals WHERE kind='recovery_error'").fetchone()[0] == 1
        else:
            meta, inputs = load_dataset(tmp_path / "datasets", after["manifest"]["dataset"]["id"])
            assert len(inputs) == meta["count"] == 2
            assert after["manifest"]["input_archive"]["state"] == "recovered"
        commands2.put({"op": "shutdown"})
        restarted.join(8)
        assert not restarted.is_alive()
    finally:
        for proc in (process, restarted):
            if proc and proc.is_alive():
                proc.terminate()
                proc.join(3)
        if store:
            store.close()


def test_engine_process_restart_restores_account_but_does_not_replay_orders(tmp_path):
    ensure_demo(tmp_path / "datasets")
    ds = next(m for m in list_datasets(tmp_path / "datasets") if m["kind"] == "quote")
    context = mp.get_context("spawn")
    commands, output = context.Queue(), context.Queue()
    process = context.Process(target=engine_worker, args=(commands, output, str(tmp_path)))
    process.start()
    code = TEMPLATES["双均线趋势"]["code"]
    commands.put({"op": "start", "mode": "replay", "name": "恢复测试", "dataset": ds["id"],
                  "code": code, "parameters": {k: v["default"] for k, v in parameter_schema(code).items()},
                  "initial": 100000, "speed": 1000, "autoplay": False})
    run_id = None
    deadline = time.monotonic() + 15
    try:
        while time.monotonic() < deadline:
            try:
                msg = output.get(timeout=.5)
            except Empty:
                continue
            if msg["type"] == "run_created":
                run_id = msg["id"]
                break
        assert run_id
        commands.put({"op": "step", "id": run_id})
        commands.put({"op": "shutdown"})
        process.join(8)
        assert not process.is_alive()
    finally:
        if process.is_alive():
            process.terminate()
            process.join(2)
    store = Store(tmp_path)
    saved = store.load_run(run_id)
    cash = saved["snapshot"]["account"].cash
    assert saved["result"]["index"] == 3
    commands2, output2 = context.Queue(), context.Queue()
    process2 = context.Process(target=engine_worker, args=(commands2, output2, str(tmp_path)))
    process2.start()
    output2.get(timeout=8)
    commands2.put({"op": "shutdown"})
    process2.join(8)
    try:
        assert not process2.is_alive()
        assert store.runs()[0]["status"] == "RECOVERED"
        assert store.load_run(run_id)["snapshot"]["account"].cash == cash
        assert all(not o.active for o in store.load_run(run_id)["snapshot"]["orders"])
    finally:
        store.close()
        if process2.is_alive():
            process2.terminate()
            process2.join(2)


@pytest.mark.parametrize("body, expected", [
    ('raise RuntimeError("single-step-failure")', "single-step-failure"),
    ('ctx.explain("bad-log", payload=object())', "解释信息须使用"),
])
def test_single_step_strategy_error_stops_account_and_engine_remains_usable(tmp_path, body, expected):
    ensure_demo(tmp_path / "datasets")
    ds = next(m for m in list_datasets(tmp_path / "datasets") if m["kind"] == "quote")
    context = mp.get_context("spawn")
    commands, output = context.Queue(), context.Queue()
    process = context.Process(target=engine_worker, args=(commands, output, str(tmp_path)))
    process.start()
    def wait_for(predicate):
        until = time.monotonic() + 12
        while time.monotonic() < until:
            try:
                msg = output.get(timeout=.2)
            except Empty:
                continue
            if predicate(msg):
                return msg
        raise AssertionError("engine did not produce the expected message")
    code = f'''
class UserStrategy(Strategy):
    def on_quote(self, ctx, quote):
        {body}
'''
    try:
        wait_for(lambda m: m["type"] == "engine_ready")
        commands.put({"op": "start", "mode": "replay", "dataset": ds["id"],
                      "code": code, "autoplay": False})
        created = wait_for(lambda m: m["type"] == "run_created")
        commands.put({"op": "step", "id": created["id"]})
        state = wait_for(lambda m: m["type"] == "run_update" and m["status"] == "ERROR")
        assert state["result"]["index"] == 0
        assert not state["snapshot"]["trades"]
        assert all(not o.active for o in state["snapshot"]["orders"])
        assert any(expected in x["message"] for x in state["result"]["logs"])
        commands.put({"op": "start", "mode": "manual", "symbols": ["600000.SH"]})
        another = wait_for(lambda m: m["type"] == "run_created")
        assert another["id"] != created["id"]
        assert process.is_alive()
        commands.put({"op": "shutdown"})
        process.join(8)
        assert not process.is_alive()
        with_store = Store(tmp_path)
        try:
            status = next(r["status"] for r in with_store.runs() if r["id"] == created["id"])
            assert status == "ERROR"
        finally:
            with_store.close()
    finally:
        if process.is_alive():
            process.terminate()
            process.join(2)
