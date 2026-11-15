prices = [10.0, 10.5, 9.8, 11.0]
alias = prices
snapshot = prices.copy()
alias[0] = 9.0
print("原列表", prices)
print("独立快照", snapshot)
print("最后三个价格", prices[-3:])
returns = [prices[i] / prices[i-1] - 1 for i in range(1, len(prices))]
print("逐期收益", [round(x, 4) for x in returns])
assert snapshot[0] == 10.0
assert prices[0] == 9.0

