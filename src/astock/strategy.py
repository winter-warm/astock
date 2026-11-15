from __future__ import annotations

import ast
import multiprocessing as mp
import traceback

from astock.domain import dec, dumps, loads
from astock.rules import round_tick


class Strategy:
    def initialize(self, ctx):
        pass

    def on_quote(self, ctx, quote):
        pass

    def on_bar(self, ctx, bar):
        pass

    def on_order(self, ctx, order):
        pass


class Context:
    def __init__(self, parameters, state):
        self.parameters = parameters
        self.state = state
        self.commands = []
        self.explanations = []

    @property
    def symbols(self):
        return list(self.state["rules"])

    @property
    def cash(self):
        return float(self.state["available_cash"])

    @property
    def equity(self):
        return float(self.state["equity"])

    @property
    def now(self):
        return self.state.get("clock")

    def history(self, symbol, count=100):
        if count < 1 or count > 2048:
            raise ValueError("history 支持 1–2048 个已完成观察值")
        return list(self.state.get("history", {}).get(symbol, []))[-count:]

    def latest_time(self, symbol):
        return self.state.get("times", {}).get(symbol)

    def position(self, symbol):
        return self.state.get("positions", {}).get(symbol, {"quantity": 0, "available": 0, "cost": 0})

    def has_open_orders(self, symbol):
        return any(o.symbol == symbol and o.active for o in self.state.get("orders", []))

    def quantity_for(self, symbol, price, fraction=0.2):
        rule = self.state["rules"][symbol]
        budget = min(self.cash * .98, self.equity * fraction)
        qty = int(budget / float(price))
        if qty < rule.buy_min:
            return 0
        return rule.buy_min + (qty - rule.buy_min) // rule.buy_step * rule.buy_step

    def limit_price(self, symbol, price):
        return round_tick(price, self.state["rules"][symbol].tick)

    def order(self, symbol, side, quantity, price, reason=""):
        if len(self.commands) >= 50:
            raise ValueError("单次回调最多提交 50 条指令")
        self.commands.append({"op": "order", "symbol": symbol, "side": side,
                              "quantity": quantity, "price": dec(price), "reason": str(reason)[:2000]})

    def cancel(self, order_id):
        self.commands.append({"op": "cancel", "order_id": order_id})

    def explain(self, message, **values):
        try:
            encoded = dumps(values)
            if len(encoded.encode("utf-8")) > 65536:
                raise ValueError("单条解释信息超过 64 KiB")
            normalized = loads(encoded)
        except (ValueError, TypeError, KeyError, RecursionError) as error:
            raise ValueError("解释信息须使用可保存的数字、文本、列表或字典；NumPy/Pandas 值请先转为 Python 值："
                             + str(error)) from error
        self.explanations.append({"message": str(message)[:2000], "values": normalized})
        if len(self.explanations) > 100:
            raise ValueError("单次回调解释记录过多")


def parameter_schema(code):
    tree = ast.parse(code, filename="strategy.py")
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "PARAMETERS" for t in node.targets):
            schema = ast.literal_eval(node.value)
            if not isinstance(schema, dict) or len(schema) > 30:
                raise ValueError("PARAMETERS 必须为不超过 30 项的字典")
            for key, item in schema.items():
                if not isinstance(key, str) or not isinstance(item, dict) or "default" not in item:
                    raise ValueError("参数需包含名称和 default 字段")
                if item.get("type", "float") not in ("int", "float", "str", "bool"):
                    raise ValueError("参数类型支持 int、float、str、bool")
            return schema
    return {}


def strategy_worker(connection, code, parameters):
    try:
        namespace = {"Strategy": Strategy, "__name__": "user_strategy"}
        exec(compile(code, "strategy.py", "exec"), namespace)
        cls = namespace.get("UserStrategy")
        if not isinstance(cls, type) or not issubclass(cls, Strategy):
            raise ValueError("代码必须定义继承 Strategy 的 UserStrategy 类")
        strategy = cls()
        connection.send({"ok": True})
        while True:
            request = connection.recv()
            if request["method"] == "shutdown":
                return
            context = Context(parameters, request["state"])
            try:
                method = getattr(strategy, request["method"])
                if request["method"] == "initialize":
                    method(context)
                else:
                    method(context, request["event"])
                connection.send({"ok": True, "commands": context.commands,
                                 "explanations": context.explanations})
            except Exception as e:
                connection.send({"ok": False, "error": str(e), "traceback": traceback.format_exc()})
    except BaseException as e:
        try:
            connection.send({"ok": False, "error": str(e), "traceback": traceback.format_exc()})
        except (OSError, EOFError):
            pass
    finally:
        connection.close()


class StrategyHost:
    def __init__(self, code, parameters, timeout=2):
        parameter_schema(code)
        self.timeout = timeout
        ctx = mp.get_context("spawn")
        self.connection, child = ctx.Pipe()
        self.process = ctx.Process(target=strategy_worker, args=(child, code, parameters), daemon=True)
        self.process.start()
        child.close()
        try:
            self._receive(15)
        except BaseException:
            self.close()
            raise

    def _receive(self, timeout):
        if not self.connection.poll(timeout):
            self.close()
            raise TimeoutError(f"策略回调超时（{timeout} 秒），已停止策略并撤单")
        result = self.connection.recv()
        if not result.get("ok"):
            raise RuntimeError(result.get("traceback", result.get("error", "策略错误")))
        return result

    def call(self, method, state, event=None):
        self.connection.send({"method": method, "state": state, "event": event})
        return self._receive(self.timeout)

    def close(self):
        if self.process.is_alive():
            try:
                self.connection.send({"method": "shutdown"})
            except (BrokenPipeError, EOFError, OSError):
                pass
            self.process.join(.3)
            if self.process.is_alive():
                self.process.terminate()
                self.process.join(1)
        self.connection.close()


MA_CODE = '''from astock.strategy import Strategy

# 参数声明会自动生成右侧表单；周期单位取决于当前数据（K线或报价）。
PARAMETERS = {
    "fast": {"label": "快均线周期", "type": "int", "default": 5, "min": 2, "max": 200,
             "help": "最近多少个已完成观察值的平均价格。"},
    "slow": {"label": "慢均线周期", "type": "int", "default": 20, "min": 3, "max": 500,
             "help": "应大于快周期；用于判断中期方向。"},
    "allocation": {"label": "单标的目标仓位", "type": "float", "default": 0.25, "min": 0.01, "max": 0.95,
                   "help": "占账户总权益的比例，不是收益保证。"},
}

class UserStrategy(Strategy):
    def initialize(self, ctx):
        if ctx.parameters["fast"] >= ctx.parameters["slow"]:
            raise ValueError("快均线周期必须小于慢均线周期")

    def evaluate(self, ctx, symbol, price):
        p = ctx.parameters
        values = ctx.history(symbol, p["slow"])
        if len(values) < p["slow"] or ctx.has_open_orders(symbol):
            return
        fast = sum(values[-p["fast"]:]) / p["fast"]
        slow = sum(values) / p["slow"]
        pos = ctx.position(symbol)
        reason = f"快均线 {fast:.4f}，慢均线 {slow:.4f}"
        ctx.explain(reason, fast=fast, slow=slow)
        if fast > slow and pos["quantity"] == 0:
            limit = ctx.limit_price(symbol, float(price) * 1.01)
            qty = ctx.quantity_for(symbol, limit, p["allocation"])
            if qty:
                ctx.order(symbol, "BUY", qty, limit, "快线高于慢线；" + reason)
        elif fast < slow and pos["available"] > 0:
            ctx.order(symbol, "SELL", pos["available"], ctx.limit_price(symbol, float(price) * 0.99),
                      "快线低于慢线；" + reason)

    def on_bar(self, ctx, bar):
        self.evaluate(ctx, bar.symbol, bar.close)

    def on_quote(self, ctx, quote):
        self.evaluate(ctx, quote.symbol, quote.last)
'''

BREAKOUT_CODE = '''from astock.strategy import Strategy

PARAMETERS = {
    "lookback": {"label": "突破回看周期", "type": "int", "default": 15, "min": 3, "max": 300,
                 "help": "使用当前观察值之前的窗口，避免把当前价格计入突破阈值。"},
    "allocation": {"label": "单标的目标仓位", "type": "float", "default": 0.25, "min": 0.01, "max": 0.95,
                   "help": "每个标的最多使用的权益比例。"},
}

class UserStrategy(Strategy):
    def evaluate(self, ctx, symbol, price):
        n = ctx.parameters["lookback"]
        values = ctx.history(symbol, n + 1)
        if len(values) <= n or ctx.has_open_orders(symbol):
            return
        high, low = max(values[:-1]), min(values[:-1])
        current = values[-1]
        pos = ctx.position(symbol)
        reason = f"价格 {current:.4f}；前 {n} 个观察值区间 [{low:.4f}, {high:.4f}]"
        ctx.explain(reason, upper=high, lower=low)
        if current > high and not pos["quantity"]:
            limit = ctx.limit_price(symbol, float(price) * 1.01)
            qty = ctx.quantity_for(symbol, limit, ctx.parameters["allocation"])
            if qty:
                ctx.order(symbol, "BUY", qty, limit, "向上突破；" + reason)
        elif current < low and pos["available"]:
            ctx.order(symbol, "SELL", pos["available"], ctx.limit_price(symbol, float(price) * .99),
                      "向下突破；" + reason)

    def on_bar(self, ctx, bar):
        self.evaluate(ctx, bar.symbol, bar.close)

    def on_quote(self, ctx, quote):
        self.evaluate(ctx, quote.symbol, quote.last)
'''

ROTATION_CODE = '''from astock.strategy import Strategy

PARAMETERS = {
    "lookback": {"label": "动量回看周期", "type": "int", "default": 20, "min": 3, "max": 300,
                 "help": "比较各 ETF 最近 N 个观察值的涨幅。所有标的时间对齐后再判断。"},
    "allocation": {"label": "目标仓位", "type": "float", "default": 0.8, "min": 0.05, "max": 0.95,
                   "help": "持有动量最高且动量为正的 ETF；先卖出，成交后再使用释放资金。"},
}

class UserStrategy(Strategy):
    def evaluate(self, ctx, event):
        n = ctx.parameters["lookback"]
        histories = {s: ctx.history(s, n + 1) for s in ctx.symbols}
        if any(len(v) <= n for v in histories.values()):
            return
        if any(ctx.latest_time(s) != event.time for s in ctx.symbols):
            return
        if any(ctx.has_open_orders(s) for s in ctx.symbols):
            return
        scores = {s: v[-1] / v[0] - 1 for s, v in histories.items()}
        best = max(scores, key=scores.get)
        target = best if scores[best] > 0 else None
        ctx.explain("ETF 动量排序", **scores)
        selling = False
        for symbol in ctx.symbols:
            pos = ctx.position(symbol)
            if symbol != target and pos["quantity"]:
                selling = True
                if pos["available"]:
                    ctx.order(symbol, "SELL", pos["available"],
                              ctx.limit_price(symbol, histories[symbol][-1] * .99),
                              f"轮出 {symbol}；动量 {scores[symbol]:.2%}")
        if target and not selling and not ctx.position(target)["quantity"]:
            price = ctx.limit_price(target, histories[target][-1] * 1.01)
            qty = ctx.quantity_for(target, price, ctx.parameters["allocation"])
            if qty:
                ctx.order(target, "BUY", qty, price, f"轮入 {target}；动量 {scores[target]:.2%}")

    def on_bar(self, ctx, bar):
        self.evaluate(ctx, bar)

    def on_quote(self, ctx, quote):
        self.evaluate(ctx, quote)
'''

TEMPLATES = {
    "双均线趋势": {"code": MA_CODE, "description": "观察快慢均线，学习信号、仓位与 T+1。"},
    "区间突破": {"code": BREAKOUT_CODE, "description": "以过去窗口为阈值，学习突破和未来数据偏差。"},
    "ETF 动量轮动": {"code": ROTATION_CODE, "description": "对齐多标的时间，比较动量并切换持仓。"},
}
