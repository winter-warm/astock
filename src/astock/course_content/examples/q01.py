# 人工价格，用于检验规则，不是实际行情。
prices = [10, 10.2, 10.4, 10.1, 9.8, 10.3]
signals = []
for i in range(3, len(prices)):
    previous_mean = sum(prices[i-3:i]) / 3
    signal = prices[i] > previous_mean
    signals.append((i, round(previous_mean, 4), signal))
print(signals)
assert signals == [(3, 10.2, False), (4, 10.2333, False), (5, 10.1, True)]

