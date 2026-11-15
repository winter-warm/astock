from statistics import mean, pstdev
from astock.strategy import Strategy

PARAMETERS = {
    "period": {"type": "int", "default": 10, "min": 3, "max": 200, "label": "布林窗口"},
    "width": {"type": "float", "default": 1.0, "min": .2, "max": 4., "label": "下轨标准差倍数"},
    "stop": {"type": "float", "default": .10, "min": .01, "max": .5, "label": "成本下方退出比例"},
}
class UserStrategy(Strategy):
    def on_bar(self, ctx, bar):
        p = ctx.parameters
        values = ctx.history(bar.symbol, p["period"])
        if len(values) < p["period"] or ctx.has_open_orders(bar.symbol):
            return
        center = mean(values)
        lower = center - p["width"] * pstdev(values)
        pos = ctx.position(bar.symbol)
        # 指标价与指标阈值同一口径；执行价使用未复权 bar.close。
        signal_price = values[-1]
        raw_price = float(bar.close)
        average_cost = pos["cost"] / pos["quantity"] if pos["quantity"] else 0.
        exit_signal = signal_price >= center or (
            average_cost > 0 and raw_price < average_cost * (1-p["stop"]))
        ctx.explain("布林回归判断", center=float(center), lower=float(lower),
                    indicator=float(signal_price), average_cost=float(average_cost))
        if pos["quantity"] and pos["available"] and exit_signal:
            ctx.order(bar.symbol, "SELL", pos["available"],
                      ctx.limit_price(bar.symbol, raw_price*.99), "回到均值或成本退出")
        elif not pos["quantity"] and signal_price < lower:
            limit = ctx.limit_price(bar.symbol, raw_price*1.01)
            qty = ctx.quantity_for(bar.symbol, limit, .2)
            if qty:
                ctx.order(bar.symbol, "BUY", qty, limit, "价格低于下轨")

