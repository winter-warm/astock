from __future__ import annotations

import csv
import json
from html import escape
from pathlib import Path

from astock.domain import dumps, plain
from astock.data_identity import origin_label

EQUITY_HEADERS = ["流水", "入账时间", "证券", "事项", "现金变动", "应收变动", "份额变动", "现金到账日", "份额可卖日", "事件编号"]


def equity_row(entry):
    return [entry.id, entry.time.strftime("%Y-%m-%d %H:%M:%S"), entry.symbol,
            "权益登记" if entry.kind == "entitlement" else "分红到账", f"{entry.cash_delta:+.2f}",
            f"{entry.receivable_delta:+.2f}", f"{entry.quantity_delta:+d}",
            entry.pay_date or "—", entry.share_available_date or "—", entry.action_key]


def accounting_note(snapshot):
    if snapshot.get("accounting_error"):
        return "账户核对失败，已隔离：" + snapshot["accounting_error"]
    if snapshot.get("legacy_equity_unverified") or (
            snapshot.get("applied_actions") and "equity_ledger_version" not in snapshot):
        from astock.accounting import LEGACY_NOTICE
        return LEGACY_NOTICE
    return "分红先记应收，再按到账日转入现金；到账前不可用于买入。新增份额按可卖日解锁。"


def log_message(entry):
    def display(value):
        if isinstance(value, float):
            return f"{value:.6g}"
        if isinstance(value, (dict, list, tuple)):
            return json.dumps(plain(value), ensure_ascii=False)
        return str(value)
    values = entry.get("values") or {}
    details = "；".join(f"{key}={display(value)}" for key, value in values.items())
    return entry["message"] + ("\n    " + details if details else "")


def export_report(root, state, *, directory=None, progress=lambda _: None):
    directory = Path(directory) if directory is not None else Path(root) / "reports" / state["id"]
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "run.json").write_text(dumps(state), encoding="utf-8")
    progress({"phase": "写入完整运行快照", "done": 0})
    trades = state["snapshot"]["trades"]
    equity = state["snapshot"].get("equity_entries", [])
    with (directory / "equity.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(EQUITY_HEADERS)
        for entry in equity:
            # Keep numeric deltas numeric; guard user-supplied action identifiers.
            row = equity_row(entry)
            if row[-1].startswith(("=", "+", "-", "@")):
                row[-1] = "'" + row[-1]
            writer.writerow(row)
    with (directory / "trades.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["成交编号", "订单编号", "时间", "代码", "方向", "数量", "价格", "费用", "已实现盈亏", "原因"])
        for index, t in enumerate(trades, 1):
            reason = t.reason
            if reason.startswith(("=", "+", "-", "@")):
                reason = "'" + reason
            writer.writerow([t.id, t.order_id, t.time.isoformat(), t.symbol, t.side, t.quantity,
                             t.price, t.fee, t.realized, reason])
            if index % 2000 == 0:
                progress({"phase": "导出成交明细", "done": index, "total": len(trades)})
    progress({"phase": "生成图表与 HTML 报告", "done": len(trades), "total": len(trades)})
    result = state["result"]
    stats = result["statistics"]
    curve = result["curve"]
    svg = ""
    if curve:
        values = [p["equity"] for p in curve] + [p["benchmark"] for p in curve]
        low, high = min(values), max(values)
        span = high - low or 1
        for key, color in (("benchmark", "#8fa5cb"), ("equity", "#53d1ae")):
            points = " ".join(f"{20 + i * 920 / max(1, len(curve)-1):.1f},{260 - (p[key]-low)/span*230:.1f}"
                              for i, p in enumerate(curve))
            svg += f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="2"/>'
    rows = "".join("<tr>" + "".join(f"<td>{escape(str(x))}</td>" for x in (
        t.time.strftime("%Y-%m-%d %H:%M:%S"), t.symbol, t.side, t.quantity, t.price, t.fee, t.reason
    )) + "</tr>" for t in trades)
    log_rows = "".join(f"<tr><td>{entry['time']:%Y-%m-%d %H:%M:%S}</td>"
                       f"<td style='white-space:pre-wrap'>{escape(log_message(entry))}</td></tr>"
                       for entry in result["logs"])
    equity_rows = "".join("<tr>" + "".join(f"<td>{escape(str(value))}</td>" for value in equity_row(entry)) + "</tr>"
                          for entry in equity)
    equity_headers = "".join(f"<th>{title}</th>" for title in EQUITY_HEADERS)
    manifest = state["manifest"]
    dataset = manifest.get("dataset") or {}
    from astock.data_quality import coverage_text
    quality_note = coverage_text(dataset.get("quality")) if dataset else "在线采集以实际行情时间及连接状态为准。"
    archive = manifest.get("input_archive")
    from astock.backtest_analysis import diagnostics_html
    diagnostics = diagnostics_html(curve, state["snapshot"]["account"].initial)
    input_note = (f"自动留存 {archive['count']:,} 条输入；状态 {archive['state']}；"
                  f"输入版本 {archive['sha256']}。回放使用当时的接收/处理延迟；"
                  "手动操作另存流水，不随数据集自动重演。") if archive else ""
    report = f"""<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>AStock 运行报告</title>
    <style>body{{background:#0e1521;color:#e5ebf5;font:15px 'Microsoft YaHei',sans-serif;max-width:1100px;margin:40px auto;padding:0 24px}}
    h1{{color:#53d1ae}}.cards{{display:flex;gap:30px;background:#182334;padding:24px;border-radius:10px}}
    table{{border-collapse:collapse;width:100%;font-size:12px}}td,th{{border-bottom:1px solid #304057;padding:10px;text-align:left}}
    pre{{white-space:pre-wrap;background:#182334;padding:20px}}.muted{{color:#a2b1c8}}</style>
    <h1>AStock / {escape(state['name'])}</h1><p class="muted">虚拟账户 · {escape(state['mode'])} · {escape(state['status'])}</p>
    <p class="muted">{escape(state.get('report_snapshot', {}).get('basis', '完整运行快照'))}；观察截至：{escape(str(state.get('snapshot', {}).get('clock') or '尚无行情'))}</p>
    <div class="cards"><div>总收益<br><b>{stats['return']:.2%}</b></div><div>最大回撤<br><b>{stats['max_drawdown']:.2%}</b></div>
    <div>总权益<br><b>{stats['equity']:,.2f}</b></div><div>累计费用<br><b>{stats['fees']:,.2f}</b></div></div>
    <h2>策略权益与价格基准</h2><svg viewBox="0 0 960 280" width="100%">{svg}</svg>
    <p>绿色：策略权益；蓝色：所选证券 {escape(str(manifest.get('benchmark_symbol', '默认标的')))} 的价格基准，不含分红再投资。样本内结果不代表未来收益。</p>
    {diagnostics}
    <h2>运行依据</h2><p>数据：{escape(dataset.get('name', '在线行情'))}；来源：{escape(dataset.get('source', 'tencent'))}；
    数据性质：{escape(origin_label(dataset))}。</p><p>{escape(input_note)}</p><p>{escape(manifest.get('model', ''))}</p>
    <h2>数据覆盖与日历</h2><p>{escape(quality_note)}</p><p>{escape(dataset.get('quality', {}).get('note', ''))}</p>
    <pre>{escape(dumps(manifest.get('calendar', {'说明': '旧版本未保存交易日历依据'})))}</pre>
    <pre>{escape(dumps({'parameters': manifest.get('parameters'), 'config': manifest.get('config'),
                       'code_sha256': manifest.get('code_sha256'), 'dataset_sha256': dataset.get('sha256')}))}</pre>
    <h2>成交明细</h2><table><tr><th>时间</th><th>代码</th><th>方向</th><th>数量</th><th>价格</th><th>费用</th><th>原因</th></tr>{rows}</table>
    <h2>权益流水</h2><p>{escape(accounting_note(state['snapshot']))}</p>
    <table><tr>{equity_headers}</tr>{equity_rows}</table>
    <h2>策略判断与订单回报</h2><p>显示最近 {len(result['logs'])} 条记录，含自定义解释指标；完整流水保存在本机数据库。</p>
    <table><tr><th>时间</th><th>说明与指标</th></tr>{log_rows}</table>
    <h2>策略源码</h2><pre>{escape(manifest.get('code', '手动练习账户'))}</pre></html>"""
    path = directory / "report.html"
    path.write_text(report, encoding="utf-8")
    return path
