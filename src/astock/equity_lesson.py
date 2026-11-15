"""Small, explicitly synthetic exercise for separating entitlement from cash."""
from datetime import datetime

from astock.datasets import list_datasets, write_dataset
from astock.domain import Bar, CN, CorporateAction, dec

CODE = '''# 教学合成行情：不是实际证券价格，也不用于评价策略收益。
PARAMETERS = {
    "quantity": {"type": "int", "default": 100, "min": 100, "max": 1000,
                 "label": "练习买入数量", "help": "按 100 的整数倍填写；观察分红与新增份额如何随持仓变化。"}
}

class UserStrategy(Strategy):
    def initialize(self, ctx):
        self.sent = False

    def on_bar(self, ctx, bar):
        # 首根已完成日线提交委托，最早下一根日线撮合。
        if not self.sent:
            self.sent = True
            ctx.explain("教学：先持有份额，再逐步观察权益登记与到账", price=bar.close)
            # 限价留出 1% 空间，使默认滑点后的下一柱开盘价仍可成交。
            limit = ctx.limit_price(bar.symbol, float(bar.close) * 1.01)
            ctx.order(bar.symbol, "BUY", ctx.parameters["quantity"], limit, "持有份额，观察分红与送转")
'''


def ensure_equity_lesson(root):
    found = next((m for m in list_datasets(root) if m["source"] == "astock-equity-lesson-v1"), None)
    if found:
        return found
    symbol = "600000.SH"
    events = []
    for day, raw_price in ((11, "10"), (12, "10"), (13, "4.5"), (16, "4.5"), (17, "4.5")):
        price = dec(raw_price)
        events.append(Bar(symbol, datetime(2026, 11, day, 15, tzinfo=CN), price, price + dec(".1"),
                          price - dec(".1"), price, 100000, prev_close=price,
                          factor=dec(1) if day <= 12 else dec(10) / dec("4.5")))
    events.append(CorporateAction(symbol, datetime(2026, 11, 13, 9, tzinfo=CN), dec(1), dec(2),
                                  "teaching-only", "2026-11-16", "2026-11-17"))
    return write_dataset(root, "教学 · 分红登记、到账与份额解锁", events, demo=True,
                         source="astock-equity-lesson-v1", verified=True,
                         notes="人工构造，非真实权益公告。100 股先产生 100 元应收及 100 股新增份额；"
                               "11 月 16 日现金到账，17 日新增份额可卖。未模拟红利税。")
