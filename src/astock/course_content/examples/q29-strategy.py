from astock.strategy import Strategy

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
