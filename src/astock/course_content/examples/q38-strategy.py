from astock.strategy import Strategy

class UserStrategy(Strategy):
    def initialize(self, ctx):
        self.sent = set()

    def on_bar(self, ctx, bar):
        if bar.symbol not in self.sent:
            self.sent.add(bar.symbol)
            price = ctx.limit_price(bar.symbol, float(bar.close)*1.05)
            qty = ctx.quantity_for(bar.symbol, price, .1)
            if qty:
                ctx.explain("第一个已完成行情提交，等待之后行情", symbol=bar.symbol)
                ctx.order(bar.symbol, "BUY", qty, price, "事件顺序教学")

    def on_order(self, ctx, order):
        ctx.explain("订单回报，仅记录不产生新指令", order_id=order.id,
                    status=order.status, filled=order.filled, note=order.note)

