# 独立计算信号：真正下单示例在正文，需放入策略编辑器。
def decide(prices, period, quantity, available, has_pending):
    if has_pending or len(prices) < period:
        return "WAIT"
    mean = sum(prices[-period:]) / period
    if prices[-1] > mean and quantity == 0:
        return "BUY"
    if prices[-1] < mean and available > 0:
        return "SELL"
    return "WAIT"

print(decide([10, 11, 12], 3, 0, 0, False))
print(decide([12, 11, 10], 3, 100, 0, False))
assert decide([10, 11, 12], 3, 0, 0, False) == "BUY"
assert decide([12, 11, 10], 3, 100, 0, False) == "WAIT"

