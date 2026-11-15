from astock.strategy import Strategy

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
