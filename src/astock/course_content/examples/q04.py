class RollingMean:
    def __init__(self, period):
        if period < 1:
            raise ValueError("周期必须大于零")
        self.period = period
        self.values = []

    def update(self, price):
        self.values.append(float(price))
        self.values = self.values[-self.period:]
        if len(self.values) < self.period:
            return None
        return sum(self.values) / self.period

a = RollingMean(3)
b = RollingMean(3)
result = [a.update(p) for p in [10, 11, 12, 9]]
print(result)
assert result == [None, None, 11.0, 10.666666666666666]
assert b.values == []

