"""Read-only reference for the strategy API implemented by this application."""

REFERENCE = """
# AStock 策略接口

这份速查可以保持打开，供你对照编写。关闭后继续编辑当前策略。

## 最小结构与参数

```python
from astock.strategy import Strategy

PARAMETERS = {
    "period": {"label": "观察周期", "type": "int",
               "default": 20, "min": 2, "max": 200},
}

class UserStrategy(Strategy):
    def initialize(self, ctx):
        self.count = 0

    def on_bar(self, ctx, bar):
        self.count += 1
        values = ctx.history(bar.symbol, ctx.parameters["period"])
        if len(values) < ctx.parameters["period"]:
            return
        ctx.explain("观察当前价格", symbol=bar.symbol,
                    price=float(bar.close), observations=self.count)
```

这段示例只记录说明，不发委托。修改 PARAMETERS 后，在右侧“参数设置”点击“检查参数”，再核对参数值。声明须为字面量字典，最多 30 项；类型支持 int、float、str、bool，每项须含 default。

## 生命周期回调

| 方法 | 调用时机 |
| --- | --- |
| `initialize(ctx)` | 创建本次运行时初始化变量、校验参数；此时通常尚无有效行情 |
| `on_bar(ctx, bar)` | 处理 K 线；可读 `bar.symbol/time/open/high/low/close/volume/factor` |
| `on_quote(ctx, quote)` | 处理报价；可读 `quote.symbol/time/last/bid/ask` 等报价字段 |
| `on_order(ctx, order)` | 处理委托状态变化；可读 `order.id/status/filled/note` |

每次回调的 ctx 都是新建的，跨回调变量放在 self。默认每次回调限时 2 秒；不要在回调中等待用户输入或长时间下载数据。

## 上下文属性

| 属性 | 含义 |
| --- | --- |
| `ctx.parameters` | 本次运行的策略参数字典 |
| `ctx.symbols` | 本次运行的证券代码列表 |
| `ctx.cash` | 扣除冻结资金后的可用现金，float |
| `ctx.equity` | 账户总权益，float |
| `ctx.now` | 当前引擎观察时刻 |

## 行情、持仓与数量

| 调用 | 返回值与用途 |
| --- | --- |
| `ctx.history(symbol, count=100)` | 最近 1–2048 个已完成价格观察值，包含当前值；返回 float 列表，不是 OHLC 表或 DataFrame |
| `ctx.latest_time(symbol)` | 该证券最近行情的来源时刻 |
| `ctx.position(symbol)` | 字典：quantity 为持仓数量；available 为当前可卖数量；cost 为持仓总成本 |
| `ctx.has_open_orders(symbol)` | 是否有该证券尚未结束的委托 |
| `ctx.quantity_for(symbol, price, fraction=0.2)` | 按现金、权益比例及证券买入步长估算数量；不足最小买入数量时返回 0 |
| `ctx.limit_price(symbol, price)` | 按证券最小报价单位舍入价格 |

history 在 K 线模式下记录 close × factor，在报价模式下记录 last。下单时使用实际未复权的行情价格，不要直接使用复权后的 history 数值作为委托价格。available 已考虑可卖日期和卖单冻结；不能仅按 quantity 卖出。数量估算和价格舍入不保证通过资金、涨跌停及风控检查。

## 委托、撤单与解释

```python
# 以下是调用形式；须放在你自己的买卖条件内。
price = ctx.limit_price(symbol, actual_price)
quantity = ctx.quantity_for(symbol, price, fraction=0.2)
if quantity > 0 and not ctx.has_open_orders(symbol):
    ctx.order(symbol, "BUY", quantity, price, reason="写清触发依据")

ctx.cancel(order_id)
ctx.explain("判断说明", fast=1.2, slow=1.1)
```

`ctx.order(symbol, side, quantity, price, reason="")` 只排队提交限价指令，返回 None。side 为 BUY 或 SELL，quantity 为整数股/份。委托编号从 on_order 的 order.id 读取；不要把 order() 的返回值当作编号。撤单使用 ctx.cancel(order_id)。explain 的附加值须能保存为 Python 数字、文本、列表或字典。

日线信号在后续交易日开盘尝试撮合；报价委托等待后续有效报价。提交委托不代表成交，结果以委托和成交记录为准。Bar.time 为 K 线结束时刻；Quote.time 为来源时刻，received 为接收时刻，observed 为引擎处理时刻。行情和订单价格使用 Decimal，计算时注意类型转换。
"""
