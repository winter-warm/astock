from astock.strategy import Strategy

PARAMETERS = {
    "period": {"type": "int", "default": 5, "min": 2, "max": 100,
               "label": "均线周期"}
}

class UserStrategy(Strategy):
    def on_bar(self, ctx, bar):
        n = ctx.parameters["period"]
        values = ctx.history(bar.symbol, n)
        if len(values) < n or ctx.has_open_orders(bar.symbol):
            return
        mean = sum(values) / n
        position = ctx.position(bar.symbol)
        price = float(bar.close)
        ctx.explain("比较收盘与均线", close=price, mean=float(mean))
        if price > mean and position["quantity"] == 0:
            limit = ctx.limit_price(bar.symbol, price * 1.01)
            quantity = ctx.quantity_for(bar.symbol, limit, 0.2)
            if quantity:
                ctx.order(bar.symbol, "BUY", quantity, limit, "价格高于均线")
        elif price < mean and position["available"] > 0:
            limit = ctx.limit_price(bar.symbol, price * 0.99)
            ctx.order(bar.symbol, "SELL", position["available"], limit,
                      "价格低于均线")
