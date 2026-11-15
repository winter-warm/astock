from __future__ import annotations

import hashlib
import math
import random
from datetime import datetime, timedelta
from pathlib import Path
import uuid

from astock.domain import Bar, CN, CorporateAction, Quote, dec, dumps, event_clock, loads
from astock.rules import default_rule, round_tick, rule_at, validate_rule
from astock.data_quality import CoverageScan
from astock.trading_calendar import trading_day


DEMO_BAR_SOURCE = "astock-synthetic-v2"
DEMO_QUOTE_SOURCE = "astock-synthetic-v1"


def dataset_digest(path: Path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_dataset(root, name, events, *, demo=False, source="import", verified=False, notes="", rules=None,
                  identity=None, coverage_request=None, provenance=None):
    import pyarrow as pa
    import pyarrow.parquet as pq

    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    events = list(events)
    if not events:
        raise ValueError("数据为空")
    quotes = any(isinstance(x, Quote) for x in events)
    if not quotes:
        events.sort(key=lambda x: (x.time, 0 if isinstance(x, CorporateAction) else 1, x.symbol))
    # Quotes preserve arrival order, including duplicates and out-of-order source
    # timestamps. Sorting/deduplicating them would change the available information.
    identity = identity or uuid.uuid4().hex[:12]
    if not identity.isalnum():
        raise ValueError("无效数据集标识")
    path = root / f"{identity}.parquet"
    rows = [{"time": e.time.isoformat(), "symbol": e.symbol, "kind": type(e).__name__, "payload": dumps(e)}
            for e in events]
    table = pa.Table.from_pylist(rows)
    temporary = path.with_suffix(".partial")
    pq.write_table(table, temporary, compression="zstd")
    temporary.replace(path)
    symbols = sorted({e.symbol for e in events})
    meta = {"id": identity, "name": name, "schema": 1, "file": path.name, "demo": demo,
            "source": source, "corporate_actions_verified": verified, "notes": notes,
            "start": min(e.time for e in events).isoformat(), "end": max(e.time for e in events).isoformat(),
            "ordering": "arrival" if quotes else "source",
            "clock": "engine-observed-or-collector-received" if quotes else "bar-close",
            "count": len(events), "symbols": symbols,
            "kind": "quote" if any(isinstance(x, Quote) for x in events) else "bar",
            "period": next((x.period for x in events if isinstance(x, Bar)), "快照"),
            "rules": rules or {s: default_rule(s) for s in symbols}, "sha256": dataset_digest(path)}
    if coverage_request:
        meta["coverage_request"] = coverage_request
    if provenance:
        meta["provenance"] = provenance
    scan = CoverageScan(meta)
    for event in events:
        scan.accept(event)
    meta["quality"] = scan.finish()
    path.with_suffix(".json").write_text(dumps(meta), encoding="utf-8")
    return meta


def list_datasets(root):
    results = []
    for path in Path(root).glob("*.json"):
        try:
            meta = loads(path.read_text(encoding="utf-8"))
            if meta.get("schema") == 1 and path.with_suffix(".parquet").is_file():
                results.append(meta)
        except (ValueError, KeyError):
            continue
    return sorted(results, key=lambda m: (not m["demo"], m["end"], m.get("source", "")), reverse=True)


def dataset_reader(root, identity, *, inspection=False):
    if not identity.isalnum():
        raise ValueError("无效数据集标识")
    path = Path(root) / f"{identity}.parquet"
    meta = loads(path.with_suffix(".json").read_text(encoding="utf-8"))
    if dataset_digest(path) != meta["sha256"]:
        raise ValueError("数据文件校验失败，文件可能被修改")
    if meta.get("id") != identity or meta.get("file") != path.name:
        raise ValueError("数据包标识与文件名不一致")
    return meta, validated_events(path, meta, inspection=inspection)


def load_dataset(root, identity):
    meta, events = dataset_reader(root, identity)
    return meta, list(events)


def validated_events(path, meta, *, inspection=False):
    import pyarrow.parquet as pq
    validator = DatasetValidator(meta, inspection=inspection)
    with pq.ParquetFile(path) as parquet:
        for batch in parquet.iter_batches(batch_size=2048, columns=["payload"]):
            for payload in batch.column("payload").to_pylist():
                event = loads(payload)
                validator.accept(event)
                yield event
    validator.finish()


def validate_dataset(meta, events):
    validator = DatasetValidator(meta)
    for e in events:
        validator.accept(e)
    validator.finish()


class DatasetValidator:
    def __init__(self, meta, *, inspection=False):
        if not inspection and not meta.get("corporate_actions_verified"):
            raise ValueError("行情已保存，但该区间暂不能回测。\n" + meta.get("notes", "权益资料未核对")
                             + "\n可重新下载不跨上述权益日期的区间，或导入含完整分红/送转明细的数据包。原数据保留。")
        if (not inspection and meta.get("kind") == "bar" and meta.get("period") != "1d"
                and meta.get("source") in {"akshare-eastmoney", "akshare-sina"}
                and any(meta.get("provenance", {}).get(s, {}).get("adapter") != "minute-bars-v2"
                        for s in meta["symbols"])):
            raise ValueError("旧版分钟下载未留存可靠昨收参考；请重新下载或导入已核对参考价的数据包。原数据仍可检查。")
        self.meta = meta
        for symbol, rule in meta["rules"].items():
            validate_rule(rule)
            if rule.symbol != symbol:
                raise ValueError("证券规则与代码不一致")
        self.inspection = inspection
        self.coverage = CoverageScan(meta, details=inspection)
        self.minimum_time = self.maximum_time = None
        self.last, self.last_factor = {}, {}
        self.last_arrival = self.last_source = None
        self.action_dates = set()
        self.actions = {}
        self.count = 0

    def accept(self, e):
        if not isinstance(e, (Quote, Bar, CorporateAction)):
            raise ValueError("数据包包含未知行情类型")
        self.count += 1
        if e.time.tzinfo is None:
            raise ValueError("行情缺少时区")
        self.minimum_time = min(self.minimum_time, e.time) if self.minimum_time else e.time
        self.maximum_time = max(self.maximum_time, e.time) if self.maximum_time else e.time
        if e.symbol not in self.meta["symbols"] or e.symbol not in self.meta["rules"]:
            raise ValueError("行情证券与数据包规则清单不一致")
        rule = rule_at(self.meta["rules"][e.symbol], e.time.astimezone(CN).date().isoformat())
        if not self.inspection and rule.status == "unknown":
            raise ValueError(rule.source or f"{e.symbol} 的证券状态未核对")
        if not self.inspection and isinstance(e, (Bar, Quote)) and rule.status == "no_limit" and (e.upper or e.lower):
            raise ValueError(f"{e.symbol} {e.time.date()} 无涨跌幅限制状态与行情上下限冲突")
        self.coverage.accept(e)
        if isinstance(e, Quote):
            if self.meta["kind"] != "quote":
                raise ValueError("K 线与快照不可混在同一数据包")
            if e.received.tzinfo is None or event_clock(e).tzinfo is None:
                raise ValueError("行情接收或引擎观察时间缺少时区")
            if self.meta.get("ordering") == "arrival":
                if self.last_arrival and event_clock(e) < self.last_arrival:
                    raise ValueError("录制接收时钟倒退，需核对原始记录；不能通过重排消除延迟")
                self.last_arrival = event_clock(e)
                # Duplicate/out-of-order provider timestamps are real inputs.
                # Broker rejects them identically in live mode and replay.
                return
        if self.last_source and e.time < self.last_source:
            raise ValueError("数据存在跨标的乱序或迟到权益事件")
        self.last_source = e.time
        if isinstance(e, CorporateAction):
            e.validate()
            if trading_day(e.time.astimezone(CN).date(), teaching=bool(self.meta.get("demo"))) is not True:
                raise ValueError("权益事件日期不是已核对的交易日，需检查日历与事件日期")
            if e.key in self.actions and self.actions[e.key] != e:
                raise ValueError("同一权益事件编号包含冲突内容")
            self.actions[e.key] = e
            self.action_dates.add((e.symbol, e.time.date()))
            return
        prior = self.last.get(e.symbol)
        if prior and e.time <= prior.time:
            raise ValueError(f"{e.symbol} 数据存在重复或乱序时间")
        if isinstance(e, Bar):
            if self.meta["kind"] != "bar":
                raise ValueError("K 线与快照不可混在同一数据包")
            if e.period != self.meta["period"] or e.period not in {"1d", "1m", "5m", "15m", "30m", "60m"}:
                raise ValueError("数据包含不支持的周期或混合周期，须拆分为独立数据包")
            if min(e.open, e.close, e.high, e.low, e.factor) <= 0 or e.volume < 0:
                raise ValueError(f"{e.symbol} {e.time} 存在缺失或无效 K 线；不能以 0 填补")
            if not e.low <= min(e.open, e.close) <= max(e.open, e.close) <= e.high:
                raise ValueError("K 线高低价范围错误")
            if e.symbol in self.last_factor and e.factor != self.last_factor[e.symbol]:
                if (e.symbol, e.time.date()) not in self.action_dates:
                    raise ValueError(f"{e.symbol} {e.time.date()} 复权因子变化但缺少对应权益事件")
            self.last_factor[e.symbol] = e.factor
        self.last[e.symbol] = e

    def finish(self):
        if not self.count:
            raise ValueError("数据为空")
        if self.count != self.meta["count"]:
            raise ValueError("数据实际条数与元数据不一致")
        if (self.minimum_time != datetime.fromisoformat(self.meta["start"])
                or self.maximum_time != datetime.fromisoformat(self.meta["end"])):
            raise ValueError("数据实际起止时间与元数据不一致")
        self.meta["quality"] = self.coverage.finish()
        if not self.inspection and not self.meta.get("demo"):
            counts = self.meta["quality"]["counts"]
            if counts.get("closed_day"):
                raise ValueError("数据包含交易所休市日 K 线，请在数据中心检查缺口与日历后修正来源")
            if counts.get("unknown_calendar_records"):
                raise ValueError("数据区间超出已核对的 2023—2026 年交易日历，不能确认交易日；请先补充日历支持")
            if counts.get("unknown_rule"):
                raise ValueError("请求范围内有交易日缺少证券状态资料；即使该日也没有行情，仍须核对后才能回测")


def _demo_bars():
    """Seeded synthetic sessions, with OHLC taken from an intraday bridge.

    The bridge is an illustration, not a fitted market model. Varying gaps,
    daily returns and clustered volatility produce different body/wick shapes
    without adding the same percentage above and below every candle.
    """
    symbols = ["510300.SH", "159915.SZ", "518880.SH"]
    generators = [random.Random(20261115 + j) for j in range(len(symbols))]
    events = []
    day = datetime(2026, 1, 5, 15, tzinfo=CN)
    previous = [dec("4"), dec("2.2"), dec("7")]
    trading_index = 0
    while trading_index < 180:
        if day.weekday() < 5:
            for j, symbol in enumerate(symbols):
                rule = default_rule(symbol)
                rng = generators[j]
                base = [4, 2.2, 7][j]
                volatility = (0.65, 1.1, 1.8, 0.85, 1.4, 0.75)[(trading_index // 18 + j) % 6]
                target = base * (1 + 0.0007 * trading_index + 0.07 * math.sin(trading_index / (11 + j * 3) + j))
                drift = 0.18 * math.log(target / float(previous[j]))
                change = max(-0.045, min(0.045, drift + rng.gauss(0, 0.0045 * volatility)))
                gap = max(-0.012, min(0.012, rng.gauss(0, 0.0018 * volatility)))
                opening = round_tick(float(previous[j]) * math.exp(gap), rule.tick)
                close = round_tick(float(previous[j]) * math.exp(change), rule.tick)
                # Interpolate endpoints with a zero-ended random bridge. Extrema
                # can occur at either endpoint, allowing short/absent wicks too.
                steps = 24
                walk = [0.0]
                for _ in range(steps):
                    walk.append(walk[-1] + rng.gauss(0, 1))
                lower = round_tick(previous[j] * (1 - rule.limit_rate), rule.tick)
                upper = round_tick(previous[j] * (1 + rule.limit_rate), rule.tick)
                path = [opening, close]
                for step in range(1, steps):
                    fraction = step / steps
                    bridge = (walk[step] - fraction * walk[-1]) * 0.005 * volatility / math.sqrt(steps)
                    value = float(opening) * math.exp(fraction * math.log(float(close / opening)) + bridge)
                    path.append(min(upper, max(lower, round_tick(value, rule.tick))))
                volume = int((2400000 + 700000 * j) * rng.uniform(0.65, 1.35)
                             * (0.7 + volatility * 0.4 + abs(change) * 35))
                events.append(Bar(symbol, day, opening, max(path), min(path), close, volume,
                                  prev_close=previous[j]))
                previous[j] = close
            trading_index += 1
        day += timedelta(days=1)
    return events


def ensure_demo(root):
    existing = list_datasets(root)
    if not any(m.get("source") == DEMO_BAR_SOURCE and m["kind"] == "bar" for m in existing):
        # Add a new version; old run manifests must keep their original file/hash.
        write_dataset(root, "合成教学 · 自然波动 ETF 日线 / 180 日（v2）", _demo_bars(),
                      demo=True, source=DEMO_BAR_SOURCE, verified=True,
                      notes="人工合成数据，不对应真实证券历史价格。固定随机种子生成开收盘、日内路径及成交量，"
                            "包含不等长上下影、跳空及不同波动阶段；仅用于教学与软件测试，不代表真实收益。")
    if any(m.get("source") == DEMO_QUOTE_SOURCE and m["kind"] == "quote" for m in existing):
        return
    symbols = ["510300.SH", "159915.SZ", "518880.SH"]
    quotes = []
    start = datetime(2026, 11, 12, 9, 30, tzinfo=CN)
    for i in range(360):
        for j, symbol in enumerate(symbols):
            r = default_rule(symbol)
            value = [4, 2.2, 7][j] * (1 + .006 * math.sin(i / (12 + j * 5)) + .00001 * i)
            price = round_tick(value, r.tick)
            at = start + timedelta(seconds=5 * i)
            prev = dec([4, 2.2, 7][j])
            quotes.append(Quote(symbol, at, at, price, price - r.tick, price + r.tick, 100000, 100000,
                                500000 + i * 20000, prev, round_tick(prev * (1 + r.limit_rate), r.tick),
                                round_tick(prev * (1 - r.limit_rate), r.tick), r.name,
                                "synthetic-teaching"))
    write_dataset(root, "合成教学 · 秒级快照 / 30 分钟", quotes, demo=True, source=DEMO_QUOTE_SOURCE,
                  verified=True, notes="人工合成的 5 秒快照，可暂停和单步；不是真实逐笔数据。")


class Recorder:
    """Each batch is committed independently; completed batches survive an abrupt exit."""
    def __init__(self, root):
        self.root = Path(root)
        self.directory = self.root / ("recording_" + uuid.uuid4().hex[:12])
        self.directory.mkdir(parents=True)
        self.parts = 0
        from astock.recordings import RecordingLease
        self.lease = RecordingLease(self.directory)
        self.closed = False

    def append(self, quotes):
        import pyarrow as pa
        import pyarrow.parquet as pq
        if self.closed:
            raise ValueError("录制已停止，不能继续写入")
        if not quotes:
            return
        table = pa.Table.from_pylist([{"payload": dumps(q)} for q in quotes])
        path = self.directory / f"{self.parts:08d}.parquet"
        pq.write_table(table, path.with_suffix(".partial"), compression="zstd")
        path.with_suffix(".partial").replace(path)
        self.parts += 1

    def finish(self):
        self.seal()
        return finalize_recording(self.directory, self.root)

    def seal(self):
        if not self.closed:
            try:
                temporary = self.directory / "sealed.partial"
                temporary.write_text(dumps({"parts": self.parts}), encoding="utf-8")
                temporary.replace(self.directory / "sealed.json")
            finally:
                self.closed = True
                self.lease.close()
        return self.directory


def finalize_recording(directory, root):
    from astock.recordings import finalize_recording as finalize
    return finalize(directory, root)
