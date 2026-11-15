"""Stream committed recording parts under an OS lease; publish metadata last."""
import hashlib
import os
from pathlib import Path
import uuid

from astock.domain import CN, Quote, dumps, event_clock, loads


class RecordingBusy(ValueError):
    pass


class RecordingLease:
    def __init__(self, directory):
        self.file = (Path(directory) / "writer.lock").open("a+b")
        try:
            self.file.seek(0, 2)
            if self.file.tell() == 0:
                self.file.write(b"0")
                self.file.flush()
            self.file.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            self.file.close()
            raise RecordingBusy("正在录制或由另一任务整理，已跳过；停止录制后可重试") from error

    def close(self):
        if not self.file.closed:
            try:
                self.file.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(self.file.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(self.file.fileno(), fcntl.LOCK_UN)
            finally:
                self.file.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def write_marker(directory, identity):
    temporary = directory / "finalized.partial"
    temporary.write_text(dumps({"dataset": identity}), encoding="utf-8")
    temporary.replace(directory / "finalized.json")


def finalize_recording(directory, root, *, stage=None, progress=lambda _: None):
    from astock.datasets import DatasetValidator, dataset_digest
    from astock.rules import default_rule
    import pyarrow as pa
    import pyarrow.parquet as pq

    root, directory = Path(root).resolve(), Path(directory).resolve()
    suffix = directory.name.removeprefix("recording_")
    if directory.parent != root or not directory.name.startswith("recording_") or not suffix.isalnum():
        raise ValueError("录制目录必须位于当前数据中心")
    own_stage = stage is None
    stage = Path(stage) if stage else root / ".imports" / uuid.uuid4().hex
    identity = "record" + suffix
    try:
        with RecordingLease(directory):
            marker = directory / "finalized.json"
            if marker.exists():
                prior = loads(marker.read_text(encoding="utf-8"))["dataset"]
                if prior is None:
                    return None
                if not isinstance(prior, str) or not prior.isalnum():
                    raise ValueError("录制完成标记无效")
                meta = loads((root / f"{prior}.json").read_text(encoding="utf-8"))
                if meta["id"] != prior or dataset_digest(root / f"{prior}.parquet") != meta["sha256"]:
                    raise ValueError("已整理数据校验失败，原始分块仍保留")
                return meta
            parts = sorted(directory.glob("*.parquet"))
            if [part.name for part in parts] != [f"{i:08d}.parquet" for i in range(len(parts))]:
                raise ValueError("录制分块缺号，不能把不完整区间静默拼接")
            sealed = directory / "sealed.json"
            if sealed.exists() and loads(sealed.read_text(encoding="utf-8"))["parts"] != len(parts):
                raise ValueError("录制分块数量与停止时的记录不一致")
            if not parts:
                write_marker(directory, None)
                return None
            stage.mkdir(parents=True, exist_ok=True)
            hashes, attributes = [], []
            for index, part in enumerate(parts, 1):
                stamp = part.stat()
                attributes.append((part.name, stamp.st_size, stamp.st_mtime_ns))
                hashes.append((part.name, dataset_digest(part)))
                if index % 100 == 0:
                    progress({"phase": "核对原始录制分块", "done": index, "total": len(parts)})
            fingerprint = hashlib.sha256(dumps(hashes).encode("utf-8")).hexdigest()
            metadata = root / f"{identity}.json"
            target = root / f"{identity}.parquet"
            if metadata.exists():
                meta = loads(metadata.read_text(encoding="utf-8"))
                if (meta.get("recording_sha256") != fingerprint or meta.get("id") != identity
                        or dataset_digest(target) != meta["sha256"]):
                    raise ValueError("同名数据与原始录制不一致，已保留两者供核对")
                write_marker(directory, identity)
                return meta
            meta = {"id": identity, "name": "录制", "schema": 1, "file": target.name, "demo": False,
                    "source": "tencent-recording", "corporate_actions_verified": False,
                    "notes": "真实报价快照；保留接收顺序、重复和乱序；不包含完整逐笔成交。跨日须核对权益事件。",
                    "ordering": "arrival", "clock": "engine-observed-or-collector-received", "count": 0,
                    "symbols": [], "kind": "quote", "period": "快照", "rules": {},
                    "recording_sha256": fingerprint, "recording_parts": len(parts), "recording_directory": directory.name}
            validator = DatasetValidator(meta, inspection=True)
            schema = pa.schema([(key, pa.string()) for key in ("time", "symbol", "kind", "payload")])
            staged = stage / target.name
            first_day = None
            single_day = True
            with pq.ParquetWriter(staged, schema, compression="zstd") as writer:
                for part in parts:
                    with pq.ParquetFile(part) as source:
                        for batch in source.iter_batches(batch_size=2048, columns=["payload"]):
                            rows = []
                            for payload in batch.column("payload").to_pylist():
                                event = loads(payload)
                                if not isinstance(event, Quote):
                                    raise ValueError("录制分块包含非快照记录")
                                if event.symbol not in meta["rules"]:
                                    meta["symbols"].append(event.symbol)
                                    meta["rules"][event.symbol] = default_rule(event.symbol)
                                validator.accept(event)
                                days = {event.time.astimezone(CN).date(), event_clock(event).astimezone(CN).date()}
                                first_day = first_day or event.time.astimezone(CN).date()
                                single_day = single_day and days == {first_day}
                                rows.append({"time": event.time.isoformat(), "symbol": event.symbol,
                                             "kind": "Quote", "payload": payload})
                            writer.write_table(pa.Table.from_pylist(rows, schema=schema))
                            progress({"phase": f"整理 {directory.name}", "done": validator.count})
            if not validator.count:
                raise ValueError("录制分块没有有效记录")
            meta.update({"count": validator.count, "start": validator.minimum_time.isoformat(),
                         "end": validator.maximum_time.isoformat(), "sha256": dataset_digest(staged),
                         "corporate_actions_verified": single_day,
                         "name": "录制 · " + validator.minimum_time.astimezone(CN).strftime("%m-%d %H:%M")})
            meta["symbols"].sort()
            validator.finish()
            current = [(part.name, part.stat().st_size, part.stat().st_mtime_ns)
                       for part in sorted(directory.glob("*.parquet"))]
            if attributes != current:
                raise ValueError("整理期间原始分块发生变化，稍后重试")
            (stage / metadata.name).write_text(dumps(meta), encoding="utf-8")
            # Recover a process killed between the two renames only when bytes
            # match exactly. Never replace an unrelated dataset or delete raw parts.
            if target.exists():
                if dataset_digest(target) != meta["sha256"]:
                    raise ValueError("未完成发布的同名数据内容不同，已保留供核对")
                staged.unlink()
            else:
                staged.rename(target)
            (stage / metadata.name).rename(metadata)
            write_marker(directory, identity)
            return meta
    finally:
        if own_stage and stage.is_dir():
            for name in (identity + ".parquet", identity + ".json"):
                (stage / name).unlink(missing_ok=True)
            stage.rmdir()


def recovery_job(request, progress):
    root = Path(request["root"]) / "datasets"
    identity = request.get("identity")
    if identity:
        if not identity.startswith("recording_") or not identity.removeprefix("recording_").isalnum():
            raise ValueError("无效录制编号")
        directories = [root / identity]
    else:
        directories = sorted(path for path in root.glob("recording_*")
                             if path.is_dir() and not (path / "finalized.json").exists())
    rows = []
    for index, directory in enumerate(directories, 1):
        try:
            meta = finalize_recording(directory, root, stage=request["stage"], progress=progress)
            row = {"directory": directory.name, "status": "已完成" if meta else "空录制",
                   "dataset": meta["id"] if meta else "", "count": meta["count"] if meta else 0, "message": "原始分块保留"}
        except RecordingBusy as error:
            row = {"directory": directory.name, "status": "正在使用", "dataset": "", "count": 0, "message": str(error)}
        except Exception as error:
            row = {"directory": directory.name, "status": "需要处理", "dataset": "", "count": 0, "message": str(error)}
        rows.append(row)
        progress({"phase": "整理录制目录", "done": index, "total": len(directories)})
    return {"rows": rows, "completed": sum(row["status"] == "已完成" for row in rows),
            "errors": sum(row["status"] == "需要处理" for row in rows),
            "busy": sum(row["status"] == "正在使用" for row in rows)}
