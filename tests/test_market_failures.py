from datetime import datetime
from queue import Queue

import pandas as pd

from astock.datasets import list_datasets, load_dataset
from astock.domain import CN, dec
from astock.market import download_history_worker, parse_corporate_dates, parse_tencent


def test_history_normalization_uses_provider_units_and_checks_action_dates(tmp_path, monkeypatch):
    import akshare as ak
    from astock import market
    frame = pd.DataFrame([
        {"date": "2026-11-12", "open": 10, "high": 10.2, "low": 9.9, "close": 10.1, "volume": 123400},
        {"date": "2026-11-13", "open": 10.1, "high": 10.3, "low": 10, "close": 10.2, "volume": 234500},
    ])
    monkeypatch.setattr(ak, "stock_zh_a_hist_tx", lambda **kwargs: frame)
    monkeypatch.setattr(market, "corporate_dates", lambda symbol: [datetime(2026, 7, 1).date()])
    q = Queue()
    download_history_worker(q, tmp_path, ["600000.SH"], "1d", "2026-11-12", "2026-11-13")
    meta = list_datasets(tmp_path / "datasets")[0]
    assert meta["corporate_actions_verified"]
    _, events = load_dataset(tmp_path / "datasets", meta["id"])
    assert events[0].volume == 123400
    assert events[0].time == datetime(2026, 11, 12, 15, tzinfo=CN)
    assert events[1].prev_close == dec("10.1")


def test_unavailable_corporate_evidence_is_preserved_as_blocked_data(tmp_path, monkeypatch):
    import akshare as ak
    from astock import market
    frame = pd.DataFrame([
        {"date": "2026-11-12", "open": 4, "high": 4.1, "low": 3.9, "close": 4, "volume": 10000},
        {"date": "2026-11-13", "open": 4, "high": 4.1, "low": 3.9, "close": 4, "volume": 10000},
    ])
    monkeypatch.setattr(ak, "stock_zh_a_hist_tx", lambda **kwargs: frame)
    def fail(symbol):
        raise ConnectionError("unavailable")
    monkeypatch.setattr(market, "corporate_dates", fail)
    download_history_worker(Queue(), tmp_path, ["510300.SH"], "1d", "2026-11-12", "2026-11-13")
    meta = list_datasets(tmp_path / "datasets")[0]
    assert not meta["corporate_actions_verified"]
    assert "无法核对" in meta["notes"]


def test_malformed_and_nonfinite_public_quotes_are_not_accepted():
    assert parse_tencent(b"bad gateway") == []
    fields = ["0"] * 88
    fields[3] = "NaN"
    fields[30] = "20261113100000"
    assert parse_tencent('v_sh600000="' + "~".join(fields) + '";') == []


def test_sina_factor_rows_support_etf_extra_columns_and_js_footer():
    text = 'var data={"data":[["2026-01-21","1.1","0.02","0"],["2025-01-20","1","0","0"]]};\n2026providerFooter();'
    dates = parse_corporate_dates(text)
    assert [str(d) for d in dates] == ["2025-01-20", "2026-01-21"]
    actual_shape = 'var sh600000hfq={"total":2,"data":[{"d":"2026-07-16","f":"17.39"},{"d":"2025-07-16","f":"16.60"}]};\n/*source footer*/'
    assert [str(d) for d in parse_corporate_dates(actual_shape)] == ["2025-07-16", "2026-07-16"]


def test_collector_retries_with_backoff_recovers_and_records_failures(tmp_path, monkeypatch):
    from queue import Empty
    from threading import Thread
    from types import SimpleNamespace
    import time
    from astock import market
    from astock.domain import Quote, loads, now_cn
    class LocalQueue(Queue):
        def cancel_join_thread(self):
            pass
    clock = [0.0]
    class Provider:
        calls = 0
        def quotes(self, symbols):
            self.calls += 1
            if self.calls < 3:
                raise ConnectionError(f"injected-failure-{self.calls}")
            at = now_cn()
            return [Quote(symbols[0], at, at, dec(10))]
    provider = Provider()
    monkeypatch.setattr(market, "TencentProvider", lambda: provider)
    monkeypatch.setattr(market, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    commands, engine, output = LocalQueue(), LocalQueue(), LocalQueue()
    worker = Thread(target=market.market_worker, args=(commands, engine, output, tmp_path), daemon=True)
    worker.start()
    def status_message():
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            try:
                message = output.get(timeout=.2)
            except Empty:
                continue
            if message["type"] == "market_status":
                return message
        raise AssertionError("market worker did not publish its state")
    try:
        commands.put({"op": "connect", "symbols": ["600000.SH"]})
        assert "5 秒" in status_message()["status"]
        clock[0] = 5
        commands.put({"op": "wake"})
        assert "10 秒" in status_message()["status"]
        clock[0] = 15
        commands.put({"op": "wake"})
        recovered = status_message()
        assert recovered["status"] == "已连接"
        assert recovered["attempts"] == 3 and recovered["successful"] == 1
        assert recovered["failures"] == 0
        assert engine.get(timeout=1)["quotes"][0].symbol == "600000.SH"
        commands.put({"op": "shutdown"})
        worker.join(3)
        assert not worker.is_alive()
        log = next((tmp_path / "logs").glob("market-*.jsonl"))
        entries = [loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
        assert [entry["successful"] for entry in entries] == [0, 0, 1]
        assert "injected-failure-1" in entries[0]["message"]
    finally:
        commands.put({"op": "shutdown"})
        worker.join(3)
