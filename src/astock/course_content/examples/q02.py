# 收盘后产生信号；下一根开盘成交。人工构造。
closes = [10, 11, 9, 12]
opens = [10, 10.5, 8, 13]
pending = False
fills = []
for day in range(len(closes)):
    if pending:
        fills.append((day, opens[day]))
        pending = False
    if day == 1:
        pending = True
print("实际成交：", fills)
assert fills == [(2, 8)]

