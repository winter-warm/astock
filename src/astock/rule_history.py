"""Publish a new dataset revision with sourced security-state intervals."""
from copy import deepcopy
import hashlib
from pathlib import Path
import shutil
import uuid

from astock.datasets import dataset_digest, dataset_reader
from astock.data_quality import CoverageScan
from astock.domain import Bar, CN, Quote, dumps, loads
from astock.rules import RULE_ENGINE_VERSION, rule_at, validate_rule


def stage_rule_revision(request, progress):
    root, stage = Path(request["root"]), Path(request["stage"])
    identity = request["identity"]
    original, events = dataset_reader(root, identity, inspection=True)
    original_text = (root / f"{identity}.json").read_bytes()
    if hashlib.sha256(original_text).hexdigest() != request["metadata_sha256"]:
        raise ValueError("数据说明已在其他任务中改变，请重新打开证券规则")
    meta = deepcopy(original)
    rules = request["rules"]
    if set(rules) != set(meta["symbols"]):
        raise ValueError("规则证券清单必须与所选数据一致")
    for symbol, rule in rules.items():
        validate_rule(rule)
        if rule.symbol != symbol:
            raise ValueError("证券规则代码不一致")
        # This editor changes dated states, never the instrument's identity or base model.
        old = deepcopy(original["rules"][symbol])
        old.history = rule.history
        if old != rule:
            raise ValueError("规则修订只允许修改日期区间；基础证券类型须通过数据包导入提供")
    meta["rules"] = rules
    evidence = deepcopy(request.get("rule_evidence", original.get("rule_evidence", {})))
    for symbol, audit in evidence.items():
        if symbol not in rules:
            raise ValueError("状态资料证券与数据不一致")
        from astock.historical_status import digest, normalize_status
        if audit.get("adapter") != "stock-status-baostock-v1":
            raise ValueError("无法识别状态资料版本")
        if digest(audit["basic"]) != audit["basic_sha256"] or digest(audit["rows"]) != audit["rows_sha256"]:
            raise ValueError("状态原始资料校验失败，请重新获取")
        proposed = normalize_status(rules[symbol], audit["request"]["start"], audit["request"]["end"],
                                    audit["basic"], audit["rows"])["periods"]
        if proposed != audit["proposed_periods"]:
            raise ValueError("状态区间与原始资料不一致，请重新获取")
        audit["applied_without_edits"] = rules[symbol].history == proposed
    if evidence:
        meta["rule_evidence"] = evidence
    progress({"phase": "核对规则日期与原始行情", "done": 0})
    coverage = CoverageScan(meta)
    for count, event in enumerate(events, 1):
        coverage.accept(event)
        r = rule_at(rules[event.symbol], event.time.astimezone(CN).date().isoformat())
        if rules[event.symbol].history and r.status == "unknown":
            raise ValueError(r.source or "证券状态日期有缺口")
        if isinstance(event, (Bar, Quote)) and r.status == "no_limit" and (event.upper or event.lower):
            raise ValueError(f"{event.symbol} {event.time.date()} 无涨跌幅限制状态与行情上下限冲突")
        if count % 2048 == 0:
            progress({"phase": "核对规则日期与原始行情", "done": count, "total": meta["count"]})
    meta["id"] = uuid.uuid4().hex[:12]
    meta["file"] = meta["id"] + ".parquet"
    meta["name"] = original["name"] + " · 规则修订"
    meta["rule_engine"] = RULE_ENGINE_VERSION
    meta["parent_dataset"] = {"id": identity, "sha256": original["sha256"],
                              "metadata_sha256": request["metadata_sha256"]}
    meta["quality"] = coverage.finish()
    stage.mkdir(parents=True)
    progress({"phase": "保存独立数据版本，保留原始数据", "done": meta["count"]})
    target = stage / meta["file"]
    shutil.copyfile(root / f"{identity}.parquet", target)
    if dataset_digest(target) != original["sha256"]:
        raise ValueError("原始数据在复制期间改变，请重新核对")
    # Avoid revising metadata that changed while the worker was scanning.
    if (root / f"{identity}.json").read_bytes() != original_text:
        raise ValueError("原数据说明在检查期间改变，请重试")
    target.with_suffix(".json").write_text(dumps(meta), encoding="utf-8")
    return {"meta": meta}


def read_rule_metadata(root, identity):
    if not identity.isalnum():
        raise ValueError("无效数据集标识")
    path = Path(root) / f"{identity}.json"
    raw = path.read_bytes()
    meta = loads(raw.decode("utf-8"))
    if meta["id"] != identity:
        raise ValueError("数据说明与编号不一致")
    return meta, hashlib.sha256(raw).hexdigest()
