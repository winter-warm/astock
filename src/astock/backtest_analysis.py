"""Descriptive diagnostics of the observed equity curve, without annualization."""
from collections import OrderedDict
from html import escape


def analyze_curve(curve, initial):
    """Use last observation per calendar day; retain the initial-capital baseline."""
    daily = OrderedDict()
    previous = float(initial)
    previous_benchmark = float(initial)
    months = OrderedDict()
    peak = previous
    peak_day = "期初"
    worst = 0.0
    trough_day = "—"
    worst_peak_day = "—"
    recovery_day = None
    target_peak = None
    best_day = worst_day = None
    # Drawdown uses every observation, not just day-end values.
    for point in curve:
        value = float(point["equity"])
        timestamp = str(point["time"])
        daily[timestamp[:10]] = point
        day = timestamp[:19]
        if value >= peak:
            peak, peak_day = value, day
        dd = 1 - value / peak if peak > 0 else 0
        if dd > worst:
            worst, worst_peak_day, trough_day = dd, peak_day, day
            target_peak, recovery_day = peak, None
        elif target_peak is not None and recovery_day is None and value >= target_peak:
            recovery_day = day
    for day, point in daily.items():
        value, benchmark = float(point["equity"]), float(point["benchmark"])
        change = value / previous - 1 if previous > 0 else None
        if change is not None:
            if best_day is None or change > best_day[1]:
                best_day = (day, change)
            if worst_day is None or change < worst_day[1]:
                worst_day = (day, change)
        month = day[:7]
        if month not in months:
            months[month] = {"start": previous, "benchmark_start": previous_benchmark, "days": 0}
        row = months[month]
        row.update(end=value, benchmark_end=benchmark)
        row["days"] += 1
        previous, previous_benchmark = value, benchmark
    monthly = []
    for month, row in months.items():
        ret = row["end"] / row["start"] - 1 if row["start"] > 0 else None
        bench = row["benchmark_end"] / row["benchmark_start"] - 1 if row["benchmark_start"] > 0 else None
        monthly.append({"month": month, "return": ret, "benchmark": bench,
                        "excess": ret - bench if ret is not None and bench is not None else None,
                        "days": row["days"]})
    return {"days": len(daily), "monthly": monthly, "drawdown": worst,
            "peak": worst_peak_day, "trough": trough_day, "recovery": recovery_day,
            "best_day": best_day, "worst_day": worst_day}


def diagnostics_html(curve, initial):
    data = analyze_curve(curve, initial)
    if not curve:
        return "<h2>回测诊断</h2><p>运行后显示分月收益、基准差值及最大回撤区间。</p>"

    def pct(value):
        return "—" if value is None else f"{value:+.2%}"

    def percentage_points(value):
        return "—" if value is None else f"{value * 100:+.2f}"

    rows = "".join("<tr>" + "".join(f"<td>{escape(str(value))}</td>" for value in (
        row["month"], pct(row["return"]), pct(row["benchmark"]), percentage_points(row["excess"]), row["days"]
    )) + "</tr>" for row in data["monthly"])
    extremes = "；".join(f"{name}：{value[0]}（{pct(value[1])}）" for name, value in (
        ("最佳观察日", data["best_day"]), ("最差观察日", data["worst_day"])) if value)
    recovery = data["recovery"] or ("未恢复" if data["drawdown"] else "无回撤")
    return f"""<h2>回测诊断</h2><p>{data['days']} 个有数据的观察日 · {escape(extremes)}</p>
    <h3>最大回撤 {data['drawdown']:.2%}</h3>
    <p>峰值：{escape(data['peak'])}<br>谷值：{escape(data['trough'])}<br>恢复：{escape(recovery)}</p>
    <h3>分月表现</h3><table border="1" cellspacing="0" cellpadding="7">
    <tr><th>月份</th><th>策略收益</th><th>价格基准</th><th>收益差（百分点）</th><th>观察日数</th></tr>{rows}</table>
    <p>每个观察日取最后一条权益；首日以前以初始资金为基准。观察日收益相对前一个有数据日，
    缺口两侧的变化可能跨多个交易日，不能当作单日涨跌。分月收益相对上月最后观察值，
    首尾月可能不完整。收益差是两个收益率相减，不是风险调整后的 Alpha。</p>
    <p>回撤使用全部已收到的曲线点；恢复指首次重新达到该次峰值。数据缺口不填零，
    观察日数不等于完整交易日数。不对短样本或快照频率直接年化。</p>"""
