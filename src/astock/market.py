from __future__ import annotations

from datetime import datetime
from pathlib import Path
from queue import Empty
import ast
import re
import time
import traceback
import urllib.request

from astock.datasets import Recorder, write_dataset
from astock.domain import Bar, CN, Quote, dec, dumps, now_cn, symbol_code
from astock.rules import default_rule


def parse_tencent(content: bytes | str, received=None):
    content = content.decode("gb18030") if isinstance(content, bytes) else content
    received = received or now_cn()
    result = []
    for match in re.finditer(r'v_((?:sh|sz)\d{6})="([^"]*)"', content):
        fields = match[2].split("~")
        if len(fields) < 49 or not fields[30] or len(fields[30]) != 14:
            continue
        try:
            at = datetime.strptime(fields[30], "%Y%m%d%H%M%S").replace(tzinfo=CN)
            def num(i):
                return dec(fields[i] or 0)
            last = num(3)
            result.append(Quote(
                symbol=symbol_code(match[1]), time=at, received=received,
                last=last, bid=num(9), ask=num(19),
                bid_size=int(num(10) * 100), ask_size=int(num(20) * 100),
                volume=int(num(6) * 100), prev_close=num(4), upper=num(47), lower=num(48),
                name=fields[1], suspended=last <= 0,
            ))
        except (ValueError, ArithmeticError):
            continue
    return result


class TencentProvider:
    def quotes(self, symbols):
        if not 1 <= len(symbols) <= 20:
            raise ValueError("一次订阅 1–20 个标的")
        normalized = [symbol_code(s) for s in symbols]
        for s in normalized:
            default_rule(s)
        names = [s[-2:].lower() + s[:6] for s in normalized]
        request = urllib.request.Request("https://qt.gtimg.cn/q=" + ",".join(names),
                                         headers={"User-Agent": "AStock/0.1 (personal research)",
                                                  "Referer": "https://gu.qq.com/"})
        with urllib.request.urlopen(request, timeout=8) as response:
            payload = response.read(512 * 1024)
        result = parse_tencent(payload)
        if not result:
            raise RuntimeError("行情源未返回可解析报价")
        missing = set(normalized) - {q.symbol for q in result}
        if missing:
            raise RuntimeError("行情返回不完整：" + ", ".join(sorted(missing)))
        return result


class QmtProvider:
    """Reserved adapter contract; not represented as a connected provider in the UI."""
    def quotes(self, symbols):
        raise NotImplementedError("QMT 行情适配器尚未配置；首版使用腾讯报价")


def record_market_metrics(root, output, received, metrics):
    logfile = Path(root) / "logs" / ("market-" + received.strftime("%Y%m%d") + ".jsonl")
    try:
        logfile.parent.mkdir(parents=True, exist_ok=True)
        with logfile.open("a", encoding="utf-8") as stream:
            stream.write(dumps({"time": received, **metrics}) + "\n")
    except OSError as error:
        output.put({"type": "error", "message": f"行情运行日志保存失败：{error}"})


def market_worker(commands, engine_commands, output, root):
    output.cancel_join_thread()
    engine_commands.cancel_join_thread()
    provider = TencentProvider()
    symbols = []
    enabled = False
    next_poll = 0.0
    failures = 0
    recorder = None
    last_receive = None
    attempts = 0
    successful = 0

    def stop_recording():
        nonlocal recorder
        current, recorder = recorder, None
        if current:
            try:
                directory = current.seal()
                output.put({"type": "recording_sealed", "directory": directory.name})
            except Exception as error:
                output.put({"type": "error", "message": f"停止录制失败（原始分块保留，可稍后恢复）：{error}"})
        output.put({"type": "recording_state", "enabled": False})

    while True:
        try:
            cmd = commands.get(timeout=max(0.05, min(0.2, next_poll - time.monotonic())))
        except Empty:
            cmd = None
        if cmd:
            op = cmd["op"]
            if op in ("stop", "shutdown"):
                enabled = False
                if recorder:
                    stop_recording()
                output.put({"type": "market_status", "status": "未连接", "failures": failures})
                if op == "shutdown":
                    return
            elif op == "connect":
                symbols = cmd["symbols"]
                enabled, next_poll, failures = True, 0.0, 0
            elif op == "record":
                if cmd["enabled"] and not recorder:
                    try:
                        recorder = Recorder(Path(root) / "datasets")
                        output.put({"type": "recording_state", "enabled": True})
                    except Exception as error:
                        output.put({"type": "error", "message": f"无法开始录制：{error}"})
                        output.put({"type": "recording_state", "enabled": False})
                elif not cmd["enabled"] and recorder:
                    stop_recording()
        if not enabled or time.monotonic() < next_poll:
            continue
        started = time.monotonic()
        attempts += 1
        try:
            quotes = provider.quotes(symbols)
            received = now_cn()
            interval = (received - last_receive).total_seconds() if last_receive else None
            last_receive = received
            successful += 1
            failures = 0
            output.put({"type": "quotes", "quotes": quotes})
            engine_commands.put({"op": "quotes", "quotes": quotes})
            ages = [(received - q.time).total_seconds() for q in quotes]
            metrics = {"type": "market_status", "status": "已连接", "interval": interval,
                       "max_age": max(ages), "latency": time.monotonic() - started,
                       "attempts": attempts, "successful": successful, "failures": 0}
            output.put(metrics)
            record_market_metrics(root, output, received, metrics)
            if recorder:
                try:
                    recorder.append(quotes)
                except Exception as error:
                    output.put({"type": "error", "message": f"录制写入失败，行情仍在接收：{error}"})
                    stop_recording()
            next_poll = started + 5
        except Exception as e:
            failures += 1
            delay = min(60, 5 * 2 ** min(failures - 1, 4))
            next_poll = time.monotonic() + delay
            metrics = {"type": "market_status", "status": f"连接失败，{delay} 秒后重试",
                       "message": str(e), "failures": failures, "attempts": attempts,
                       "successful": successful}
            output.put(metrics)
            record_market_metrics(root, output, now_cn(), metrics)


def corporate_dates(symbol):
    """Read the same public factor source used by AKShare; ETF rows can have extra columns."""
    code = symbol[-2:].lower() + symbol[:6]
    request = urllib.request.Request(f"https://finance.sina.com.cn/realstock/company/{code}/hfq.js",
                                     headers={"User-Agent": "AStock/0.1"})
    with urllib.request.urlopen(request, timeout=8) as response:
        text = response.read(1024 * 1024).decode("gb18030")
    return parse_corporate_dates(text)


def parse_corporate_dates(text):
    # 新浪在赋值行之后附带 JS 注释/回调，只解析第一行的数据字面量。
    value = ast.literal_eval(text.split("=", 1)[1].strip().splitlines()[0].rstrip(";"))
    rows = value["data"]
    if not isinstance(rows, list) or not rows:
        raise ValueError("复权因子记录为空，不能确认权益变动")
    return sorted({datetime.fromisoformat(str(row.get("d", row.get("date")))).date()
                   if isinstance(row, dict) else datetime.fromisoformat(str(row[0])).date()
                   for row in rows})


def download_history_worker(output, root, symbols, period, start, end, minute_source="sina"):
    try:
        symbols = list(dict.fromkeys(symbol_code(s) for s in symbols))
        if not 1 <= len(symbols) <= 20 or start > end:
            raise ValueError("请选择 1–20 个证券并检查起止日期")
        import akshare as ak
        from akshare.utils.context import config
        config.timeout = (5, 10)
        all_events = []
        issues = []
        provenance = {}
        rules = {s: default_rule(s) for s in symbols}
        for index, symbol in enumerate(symbols):
            output.put({"type": "history_progress", "message": f"下载 {symbol}（{index + 1}/{len(symbols)}）"})
            r = rules[symbol]
            if period != "1d":
                from astock.minute_history import fetch_minutes
                events, problems, audit = fetch_minutes(ak, symbol, r, period, start, end, minute_source, corporate_dates)
                for b in events:
                    if b.prev_close > 0 and max(abs(b.high / b.prev_close - 1), abs(b.low / b.prev_close - 1)) > r.limit_rate + dec("0.01"):
                        problems.append(f"{symbol} {b.time.date()} 超出标准涨跌幅，须核对证券状态和除权参考价")
                all_events.extend(events)
                issues.extend(dict.fromkeys(problems))
                provenance[symbol] = audit
                continue
            volume_multiplier = 100
            if period == "1d":
                # AKShare 1.20 的腾讯适配器已将 volume 统一为股，不能再次乘100。
                frame = ak.stock_zh_a_hist_tx(symbol=symbol[-2:].lower() + symbol[:6],
                                              start_date=start.replace("-", ""),
                                              end_date=end.replace("-", ""), adjust="")
                frame = frame.rename(columns={"date": "日期", "open": "开盘", "high": "最高",
                                               "low": "最低", "close": "收盘", "volume": "成交量"})
                volume_multiplier = 1
            if frame.empty:
                raise ValueError(f"{symbol} 在所选范围没有数据")
            first_time = str(frame.iloc[0].get("日期", frame.iloc[0].get("时间", "")))[:10]
            last_time = str(frame.iloc[-1].get("日期", frame.iloc[-1].get("时间", "")))[:10]
            if first_time != last_time:
                try:
                    changed = [d for d in corporate_dates(symbol)
                               if first_time < d.isoformat() <= last_time]
                    if changed:
                        issues.append(f"{symbol} 区间内发生权益变动（{', '.join(map(str, changed))}）；请导入包含分红/送转明细的数据包")
                except Exception as e:
                    issues.append(f"{symbol} 无法核对权益因子：{e}")
            previous = None
            for _, row in frame.iterrows():
                raw_date = str(row.get("日期", row.get("时间", "")))
                at = datetime.fromisoformat(raw_date).replace(tzinfo=CN)
                if period == "1d":
                    at = at.replace(hour=15, minute=0, second=0)
                close = dec(row["收盘"])
                prev_close = close - dec(row["涨跌额"]) if "涨跌额" in row else (previous or close)
                if previous is not None and period == "1d" and abs(prev_close - previous) > r.tick * 2:
                    issues.append(f"{symbol} {at.date()} 昨收基准变化，可能发生除权/分红，需补充权益事件")
                bar = Bar(symbol, at, dec(row["开盘"]), dec(row["最高"]), dec(row["最低"]), close,
                          int(dec(row["成交量"]) * volume_multiplier), period, prev_close)
                if min(bar.open, bar.low, bar.high, bar.close) <= 0:
                    issues.append(f"{symbol} {at} K 线字段缺失，不能执行回测")
                all_events.append(bar)
                previous = close
            # 免费历史不含可靠的 ST/上市初期状态序列，异常波动会触发审查而非套用默认规则。
            for b in (e for e in all_events if e.symbol == symbol):
                if b.prev_close > 0 and abs(b.close / b.prev_close - 1) > r.limit_rate + dec("0.01"):
                    issues.append(f"{symbol} {b.time.date()} 超出默认涨跌幅规则，需核对证券历史状态")
        source = "akshare-tencent" if period == "1d" else "akshare-" + minute_source
        notes = f"来源 {source}；跨日权益事件对照新浪因子日期；成交量统一为股/份；仅保留实际返回范围。"
        if period != "1d":
            notes += "\n分钟柱按结束时刻保存，使用前一交易日日线收盘参考；不补齐缺口，也不生成秒级历史。"
            notes += "\n已排除尚未结束的柱；包含集合竞价的柱保留展示，但不参与连续竞价撮合。"
        notes += "\n" + "\n".join(issues[:30]) if issues else "\n区间内未检出权益事件；使用标准证券规则，不含完整历史ST/上市状态。"
        name = symbols[0] + (f" 等 {len(symbols)} 个标的" if len(symbols) > 1 else "")
        meta = write_dataset(Path(root) / "datasets", f"历史 · {name} / {period}", all_events,
                             source=source, verified=not issues, notes=notes, rules=rules,
                             coverage_request={"start": start, "end": end}, provenance=provenance)
        output.put({"type": "history_done", "meta": meta})
    except Exception as e:
        from astock.minute_history import source_error
        detail = source_error(e, minute_source) if period != "1d" else str(e)
        output.put({"type": "error", "message": f"历史数据下载失败：{detail}", "traceback": traceback.format_exc()})
