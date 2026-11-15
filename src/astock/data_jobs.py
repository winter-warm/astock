"""Cancelable, isolated data preparation. Only the GUI publishes completed imports."""
from __future__ import annotations

from collections import deque
import multiprocessing as mp
from pathlib import Path
from queue import Empty
import shutil
import time
import uuid

from PySide6 import QtCore

from astock.datasets import dataset_reader
from astock.domain import Bar, Quote, event_clock, loads
from astock.input_archive import iter_inputs


def chart_point(e):
    price = e.close if isinstance(e, Bar) else e.last
    return {"time": e.time, "open": float(e.open) if isinstance(e, Bar) else float(price),
            "high": float(e.high) if isinstance(e, Bar) else float(price),
            "low": float(e.low) if isinstance(e, Bar) else float(price),
            "close": float(price), "volume": e.volume}


def preview_dataset(root, identity, progress=lambda _: None):
    progress({"phase": "检查文件完整性", "done": 0})
    meta, events = dataset_reader(root, identity)
    points = deque(maxlen=1000)
    symbol = meta["symbols"][0]
    for count, e in enumerate(events, 1):
        if isinstance(e, (Bar, Quote)) and e.symbol == symbol:
            points.append(chart_point(e))
        if count % 2048 == 0:
            progress({"phase": "校验数据", "done": count, "total": meta["count"]})
    return {"meta": meta, "symbol": symbol, "points": list(points)}


def trade_context(request, progress=lambda _: None):
    progress({"phase": "从原始数据定位成交", "done": 0})
    root = Path(request["root"])
    # Prefer the committed input prefix for live runs, including cross-day
    # recordings that may be retained for inspection but blocked from backtesting.
    if request.get("archive"):
        events = iter_inputs(root, request["archive"])
    elif request.get("dataset"):
        _, events = dataset_reader(root / "datasets", request["dataset"])
    else:
        raise ValueError("该历史账户没有留存原始行情，无法准确定位这笔成交")
    before = deque(maxlen=41)
    points = []
    previous = None
    found, following = False, 0
    for count, e in enumerate(events, 1):
        if count % 4096 == 0:
            progress({"phase": "核对原始行情", "done": count})
        if not isinstance(e, (Bar, Quote)) or e.symbol != request["symbol"] or event_clock(e) > request["until"]:
            continue
        if previous and e.time <= previous:
            continue
        previous = e.time
        if not found:
            before.append(chart_point(e))
            if e.time == request["at"]:
                found = True
                points = list(before)
        elif following < 40:
            points.append(chart_point(e))
            following += 1
    if not found:
        raise ValueError("原始数据中未找到该笔成交的准确时刻，请核对该运行的数据版本")
    return {"points": points, "symbol": request["symbol"], "at": request["at"]}


def data_job_worker(output, kind, request):
    def progress(value):
        output.put({"type": "progress", **value})
    try:
        if kind == "preview":
            result = preview_dataset(request["root"], request["identity"], progress)
        elif kind == "import":
            source = Path(request["source"])
            meta = loads(source.read_text(encoding="utf-8"))
            identity = meta["id"]
            if not isinstance(identity, str) or not identity.isalnum() or source.stem != identity:
                raise ValueError("数据包文件名必须与 id 一致")
            stage = Path(request["stage"])
            stage.mkdir(parents=True)
            # Metadata is the commit marker. No final dataset is exposed until
            # the GUI accepts a successful, current job and publishes both files.
            progress({"phase": "复制至临时目录", "done": 0})
            shutil.copyfile(source.with_suffix(".parquet"), stage / f"{identity}.parquet")
            shutil.copyfile(source, stage / f"{identity}.json")
            result = preview_dataset(stage, identity, progress)
        elif kind == "trade":
            result = trade_context(request, progress)
        elif kind == "catalog":
            from astock.catalog import fetch_catalog
            result = fetch_catalog(progress)
        elif kind == "live_rules":
            from astock.live_rules import prepare_live_catalog
            result = prepare_live_catalog(request["root"], request["symbols"], progress)
        elif kind in ("report", "compare"):
            from astock.report_jobs import comparison_job, report_job
            result = (report_job if kind == "report" else comparison_job)(request, progress)
        elif kind == "recover":
            from astock.recordings import recovery_job
            result = recovery_job(request, progress)
        elif kind == "quality":
            from astock.data_quality import write_coverage_files
            progress({"phase": "核对数据哈希与记录", "done": 0})
            meta, events = dataset_reader(request["root"], request["identity"], inspection=True)
            for count, _ in enumerate(events, 1):
                if count % 2048 == 0:
                    progress({"phase": "检查交易日与分钟覆盖", "done": count, "total": meta["count"]})
            result = meta["quality"]
            progress({"phase": "生成全部缺口明细", "done": meta["count"]})
            write_coverage_files(request["stage"], result)
        elif kind == "rules":
            from astock.rule_history import stage_rule_revision
            result = stage_rule_revision(request, progress)
        elif kind == "rule_fetch":
            from astock.historical_status import fetch_status
            result = fetch_status(request, progress)
        else:
            raise ValueError("未知数据任务")
        output.put({"type": "finished", "result": result})
    except Exception as error:
        output.put({"type": "error", "message": str(error)})


class DataJobs(QtCore.QObject):
    message = QtCore.Signal(object)
    settled = QtCore.Signal(str)

    def __init__(self, root, parent=None):
        super().__init__(parent)
        self.root = Path(root)
        self.context = mp.get_context("spawn")
        self.active, self.retired, self.ready_stages = {}, [], {}
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.poll)
        self.timer.start(40)

    def start(self, kind, **request):
        self.cancel(kind)
        token = uuid.uuid4().hex
        request = {**request, "stage": str(self.root / ".imports" / token)}
        output = self.context.Queue()
        process = self.context.Process(target=data_job_worker, args=(output, kind, request),
                                       name=f"AStockData-{kind}", daemon=True)
        job = {"kind": kind, "token": token, "request": request, "process": process, "output": output}
        if kind == "rule_fetch":
            job["deadline"] = time.monotonic() + 45
        elif kind == "live_rules":
            job["deadline"] = time.monotonic() + 90
        process.start()
        self.active[kind] = job
        return token

    def cancel(self, kind):
        for token, entry in list(self.ready_stages.items()):
            if entry["kind"] == kind:
                self.cleanup_stage(entry["stage"])
                self.ready_stages.pop(token)
        job = self.active.pop(kind, None)
        if job:
            if job["process"].is_alive():
                job["process"].terminate()
            self.retired.append(job)

    @staticmethod
    def cleanup_stage(value):
        # The worker owns only these flat staging files, never arbitrary subtrees.
        stage = Path(value)
        if stage.is_dir():
            for path in stage.iterdir():
                if path.is_file() and path.suffix in (".json", ".parquet", ".html", ".csv", ".partial"):
                    path.unlink(missing_ok=True)
            stage.rmdir()

    def cleanup(self, job, *, preserve_result=False):
        job["process"].join(0)
        job["output"].close()
        if preserve_result and job.get("result_ready"):
            self.ready_stages[job["token"]] = {"stage": job["request"]["stage"], "kind": job["kind"]}
        else:
            self.cleanup_stage(job["request"]["stage"])

    def poll(self):
        for kind, job in list(self.active.items()):
            if job.get("deadline", float("inf")) < time.monotonic():
                self.cancel(kind)
                self.message.emit({"type": "error", "kind": kind, "token": job["token"],
                                   "message": ("当日 ETF 规则获取超过 90 秒，已停止；账户未改变，可稍后重试。"
                                               if kind == "live_rules" else
                                               "历史状态获取超过 45 秒，已停止；原规则未修改，可稍后重试。")})
                continue
            terminal = False
            exhausted = False
            latest_progress = None
            for _ in range(20):
                try:
                    value = job["output"].get_nowait()
                except Empty:
                    exhausted = True
                    break
                if value["type"] == "progress":
                    latest_progress = value
                else:
                    terminal = True
                    job["result_ready"] = value["type"] == "finished"
                    self.active.pop(kind, None)
                    self.retired.append(job)
                    self.message.emit({**value, "kind": kind, "token": job["token"], "request": job["request"]})
                    break
            if latest_progress and not terminal:
                self.message.emit({**latest_progress, "kind": kind, "token": job["token"]})
            if exhausted and not terminal and not job["process"].is_alive() and job["process"].exitcode is not None:
                self.active.pop(kind, None)
                self.retired.append(job)
                self.message.emit({"type": "error", "kind": kind, "token": job["token"],
                                   "message": f"数据任务意外退出 ({job['process'].exitcode})，可重新加载"})
        for job in self.retired[:]:
            if not job["process"].is_alive():
                self.cleanup(job, preserve_result=True)
                self.retired.remove(job)
                self.settled.emit(job["kind"])
        # A finished worker does not imply that its queued GUI result has been
        # published yet. Keep nonempty successful staging until accepted,
        # superseded by another task of that kind, or the owner closes.
        for token, entry in list(self.ready_stages.items()):
            stage = Path(entry["stage"])
            if not stage.exists() or not any(stage.iterdir()):
                if stage.exists():
                    stage.rmdir()
                self.ready_stages.pop(token)

    def close(self):
        self.timer.stop()
        for kind in list(self.active):
            self.cancel(kind)
        for job in self.retired:
            job["process"].join(1)
            if not job["process"].is_alive():
                self.cleanup(job)
                self.settled.emit(job["kind"])
        self.retired = []
        for entry in self.ready_stages.values():
            self.cleanup_stage(entry["stage"])
        self.ready_stages.clear()


def publish_import(dataset_root, request, result):
    root = Path(dataset_root)
    identity = result["meta"]["id"]
    source = Path(request["source"]).resolve()
    target = root / f"{identity}.json"
    if source == target.resolve():
        return  # Already local; the background validation still ran.
    parquet = target.with_suffix(".parquet")
    if target.exists() or parquet.exists():
        raise ValueError("同一数据集已存在；请使用已有数据或重新生成不同 id 的数据包")
    stage = Path(request["stage"])
    # Same volume, native Windows rename refuses replacement; metadata last.
    (stage / parquet.name).rename(parquet)
    try:
        (stage / target.name).rename(target)
    except Exception:
        parquet.unlink(missing_ok=True)
        raise
