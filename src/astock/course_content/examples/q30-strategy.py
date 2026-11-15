from astock.strategy import Strategy

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
