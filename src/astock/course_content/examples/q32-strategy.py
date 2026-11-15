from astock.strategy import Strategy

PARAMETERS = {
    "period": {"type": "int", "default": 3, "min": 2, "max": 100, "label": "简单平均 RSI 周期"},
    "threshold": {"type": "float", "default": 40., "min": 1., "max": 99., "label": "回升穿越阈值"},
    "trend": {"type": "int", "default": 4, "min": 2, "max": 200, "label": "趋势均线周期"},
}
def simple_rsi(values):
    changes = [b-a for a,b in zip(values, values[1:])]
    gain = sum(max(x,0) for x in changes)
    loss = sum(max(-x,0) for x in changes)
    return 100*gain/(gain+loss) if gain+loss else 50.

class UserStrategy(Strategy):
    def on_bar(self, ctx, bar):
        p = ctx.parameters
        required = max(p["period"]+2, p["trend"])
        values = ctx.history(bar.symbol, required)
        if len(values) < required or ctx.has_open_orders(bar.symbol):
            return
        old = simple_rsi(values[-p["period"]-2:-1])
        current = simple_rsi(values[-p["period"]-1:])
        trend = sum(values[-p["trend"]:])/p["trend"]
        price = values[-1]
        pos = ctx.position(bar.symbol)
        ctx.explain("RSI 回升过滤", previous=float(old), rsi=float(current), trend=float(trend))
        if pos["available"] and price < trend:
            ctx.order(bar.symbol,"SELL",pos["available"],
                      ctx.limit_price(bar.symbol,float(bar.close)*.99),"跌回趋势均线")
        elif pos["quantity"] == 0 and old < p["threshold"] <= current and price > trend:
            limit = ctx.limit_price(bar.symbol,float(bar.close)*1.01)
            quantity = ctx.quantity_for(bar.symbol,limit,.2)
            if quantity:
                ctx.order(bar.symbol,"BUY",quantity,limit,"RSI 回升且趋势过滤通过")

