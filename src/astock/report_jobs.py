"""Read coherent saved states without moving large snapshots through the GUI."""
import hashlib
import json
import math
from pathlib import Path
import sqlite3

from astock.domain import loads, now_cn
from astock.reports import export_report


def connect_readonly(root):
    uri = (Path(root) / "workbench.sqlite3").resolve().as_uri() + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True, timeout=5)
    connection.execute("PRAGMA query_only=ON")
    return connection


def report_job(request, progress):
    progress({"phase": "读取已保存的账户快照", "done": 0})
    connection = connect_readonly(request["root"])
    try:
        row = connection.execute("SELECT id,name,mode,status,manifest,snapshot,result FROM runs WHERE id=?",
                                 (request["identity"],)).fetchone()
    finally:
        connection.close()
    if not row:
        raise ValueError("运行记录尚未保存或不存在，请稍后重试")
    if not row[0].isalnum():
        raise ValueError("运行编号无效")
    state = dict(zip(("id", "name", "mode", "status"), row[:4]))
    state.update(dict(zip(("manifest", "snapshot", "result"), map(loads, row[4:]))))
    digest = hashlib.sha256("\n".join(row[4:]).encode("utf-8")).hexdigest()
    state["report_snapshot"] = {"read_at": now_cn(), "sha256": digest,
                                "observed_until": state["snapshot"].get("clock"),
                                "basis": "后台开始读取时已经保存的完整账户快照；不暂停运行"}
    progress({"phase": "快照已固定，正在生成报告", "done": 0, "snapshot_sha256": digest})
    path = export_report(request["root"], state, directory=Path(request["stage"]), progress=progress)
    return {"id": state["id"], "name": state["name"], "status": state["status"], "file": path.name,
            "snapshot": state["report_snapshot"], "trades": len(state["snapshot"]["trades"])}


def publish_report(root, request, result):
    if result["id"] != request["identity"] or not result["id"].isalnum() or result["file"] != "report.html":
        raise ValueError("报告与请求的运行编号不一致")
    stage = Path(request["stage"])
    if not stage.name.isalnum() or not all((stage / name).is_file() for name in ("report.html", "run.json", "trades.csv", "equity.csv")):
        raise ValueError("报告文件尚未生成完整")
    destination = Path(root) / "reports" / result["id"] / stage.name
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage.rename(destination)  # One directory rename publishes the complete set; prior exports remain intact.
    return destination / "report.html"


def comparison_job(request, progress):
    connection = connect_readonly(request["root"])
    rows = []
    at = now_cn()
    try:
        connection.execute("BEGIN")
        total = connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
        # Extract only the needed fields in the worker. In particular, do not
        # parse every account's positions/orders or send curves to the UI.
        cursor = connection.execute("""SELECT id,name,mode,status,created,
            CASE WHEN json_valid(result) THEN json_extract(result,'$.statistics') END,
            CASE WHEN json_valid(manifest) THEN json_extract(manifest,'$.dataset.name') END,
            CASE WHEN json_valid(manifest) THEN json_extract(manifest,'$.dataset.sha256') END,
            CASE WHEN json_valid(manifest) THEN json_extract(manifest,'$.config') END,
            CASE WHEN json_valid(manifest) THEN json_extract(manifest,'$.calendar.sha256') END,
            CASE WHEN json_valid(manifest) THEN json_extract(manifest,'$.input_archive.sha256') END,
            CASE WHEN json_valid(manifest) THEN json_extract(manifest,'$.rules') END,
            CASE WHEN json_valid(manifest) THEN json_extract(manifest,'$.engine') END,
            CASE WHEN json_valid(snapshot) THEN json_extract(snapshot,'$.account.initial') END,
            CASE WHEN json_valid(snapshot) THEN json_extract(snapshot,'$.clock') END,
            CASE WHEN json_valid(manifest) THEN json_extract(manifest,'$.dataset.demo') END,
            CASE WHEN json_valid(manifest) THEN json_extract(manifest,'$.dataset.source') END,
            CASE WHEN json_valid(manifest) THEN json_extract(manifest,'$.dataset.asset_class') END
            FROM runs ORDER BY created DESC,id""")
        for index, record in enumerate(cursor, 1):
            (identity, name, mode, status, created, statistics, dataset, data_hash, config, calendar,
             inputs, rules, engine, initial, clock, demo, source, asset_class) = record
            from astock.data_identity import display_name
            data_name = display_name({'name': dataset, 'demo': bool(demo), 'source': source or '',
                                      'asset_class': asset_class}) if dataset else (
                                          '真实行情 · 本地虚拟账户' if mode in ('live', 'manual') else '数据来源未记录')
            item = {"id": identity, "name": name, "mode": mode, "status": status, "created": created,
                    "dataset": data_name, "error": "", "statistics": {}}
            try:
                stats = json.loads(statistics or "null")
                if not isinstance(stats, dict) or not all(k in stats for k in ("return", "max_drawdown", "fees", "trades")):
                    raise ValueError("缺少统计结果")
                item["statistics"] = {key: float(stats[key]) for key in ("return", "max_drawdown", "fees")}
                item["statistics"]["trades"] = int(stats["trades"])
                if not all(math.isfinite(value) for value in item["statistics"].values()):
                    raise ValueError("统计结果包含无效数值")
                if config is None or rules is None or initial is None:
                    raise ValueError("缺少撮合依据")
                basis = [inputs or data_hash or identity, mode, json.loads(config), json.loads(rules),
                         calendar, engine, initial, clock]
                normalized = json.dumps(basis, sort_keys=True, separators=(",", ":"))
                item["basis"] = hashlib.sha256(normalized.encode()).hexdigest()
            except (ValueError, TypeError, KeyError, OverflowError) as error:
                item["error"] = "记录无法完整读取：" + str(error)
                item["basis"] = "unknown-" + identity
            rows.append(item)
            if index % 50 == 0 or index == total:
                progress({"phase": "读取运行摘要", "done": index, "total": total})
    finally:
        connection.close()
    return {"rows": rows, "read_at": at, "basis_groups": len({row["basis"] for row in rows}),
            "errors": sum(bool(row["error"]) for row in rows)}
