"""Immutable live-input chunks, committed by reference with the account snapshot.

Parquet is durable before SQLite commits its prefix. Recovery reads only the
committed prefix: an interrupted write can leave an orphan but never replay it.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

from astock.datasets import dataset_digest, load_dataset, write_dataset
from astock.domain import dumps, event_clock, loads


class InputArchive:
    def __init__(self, root, run_id):
        self.root = Path(root)
        self.pending = []
        self.manifest = {"schema": 1, "directory": f"inputs/{run_id}", "parts": [],
                         "count": 0, "sha256": hashlib.sha256(b"").hexdigest(),
                         "state": "recording"}

    def append(self, quote):
        # Freeze at observation: later strategy or account changes cannot alter it.
        self.pending.append(dumps(quote))

    def flush(self):
        if not self.pending:
            return self.manifest
        import pyarrow as pa
        import pyarrow.parquet as pq
        directory = self.root / self.manifest["directory"]
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{len(self.manifest['parts']):08d}.parquet"
        temporary = path.with_suffix(".partial")
        with temporary.open("wb") as stream:
            pq.write_table(pa.table({"payload": self.pending}), stream, compression="zstd")
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
        part = {"file": path.name, "sha256": dataset_digest(path), "count": len(self.pending)}
        self.manifest["parts"].append(part)
        self.manifest["count"] += len(self.pending)
        self.manifest["sha256"] = prefix_digest(self.manifest["parts"])
        self.pending = []
        return self.manifest


def prefix_digest(parts):
    return hashlib.sha256(dumps(parts).encode("utf-8")).hexdigest() if parts else hashlib.sha256(b"").hexdigest()


def read_inputs(root, manifest):
    return list(iter_inputs(root, manifest))


def iter_inputs(root, manifest):
    import pyarrow.parquet as pq
    directory = Path(root) / manifest["directory"]
    directory = directory.resolve()
    if not directory.is_relative_to((Path(root) / "inputs").resolve()):
        raise ValueError("输入归档目录超出本机数据范围")
    if prefix_digest(manifest["parts"]) != manifest["sha256"]:
        raise ValueError("输入归档清单校验失败")
    count = 0
    for index, part in enumerate(manifest["parts"]):
        if part["file"] != f"{index:08d}.parquet":
            raise ValueError("输入归档片段顺序无效")
        path = directory / part["file"]
        if dataset_digest(path) != part["sha256"]:
            raise ValueError(f"输入归档片段校验失败：{part['file']}")
        rows = pq.read_table(path, columns=["payload"]).column("payload").to_pylist()
        if len(rows) != part["count"]:
            raise ValueError("输入归档片段数量不符")
        for row in rows:
            count += 1
            yield loads(row)
    if count != manifest["count"]:
        raise ValueError("输入归档总数量不符")


def finalize_inputs(root, manifest, rules, name):
    if not manifest["count"]:
        return None
    # Stable identity for this committed prefix makes recovery idempotent.
    identity = "input" + hashlib.sha256(dumps([manifest["sha256"], rules, name]).encode("utf-8")).hexdigest()[:24]
    target = Path(root) / "datasets"
    metadata = target / f"{identity}.json"
    events = read_inputs(root, manifest)
    if metadata.exists():
        meta = loads(metadata.read_text(encoding="utf-8"))
        # Even unverified cross-day data can be retained/exported; it cannot run.
        if meta.get("corporate_actions_verified"):
            load_dataset(target, identity)
        elif dataset_digest(target / f"{identity}.parquet") != meta["sha256"]:
            raise ValueError("归档数据文件校验失败")
        return meta
    single_day = len({q.time.date() for q in events} | {event_clock(q).date() for q in events}) == 1
    return write_dataset(target, f"运行留存 · {name}", events, identity=identity,
                         source="astock-live-input-v1", verified=single_day, rules=rules,
                         notes="自动保留本账户全部输入，包括重复/乱序报价、来源/接收/引擎观察时间。"
                               "回放沿用当时延迟；手动下单、暂停和撤单不自动重演，原操作另存账户流水。"
                               "跨日数据仍须补充并核对权益事件。")
