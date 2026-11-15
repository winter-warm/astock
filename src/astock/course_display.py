"""Small, serializable lab displays; no Qt objects are created by exercise code."""
import math
from itertools import islice


class LabDisplay:
    def __init__(self):
        self.items = []

    def add(self, item):
        if len(self.items) >= 16:
            raise ValueError('一次练习最多展示 16 个表格或图表。')
        self.items.append(item)

    def table(self, data, *, title='数据表', headers=None):
        if hasattr(data, 'columns') and hasattr(data, 'head'):
            headers = [str(v)[:100] for v in data.columns[:20]]
            rows = data.iloc[:200, :20].astype(object).values.tolist()
            truncated = len(data) > 200 or len(data.columns) > 20
        else:
            rows = list(islice(iter(data), 201))
            raw_rows = [list(islice(iter(row), 21)) for row in rows[:200]]
            truncated = len(rows) > 200 or any(len(row) > 20 for row in raw_rows)
            rows = [row[:20] for row in raw_rows]
            headers = headers or [str(i + 1) for i in range(max((len(r) for r in rows), default=0))]
        self.add({'kind': 'table', 'title': str(title)[:200], 'headers': [str(v)[:100] for v in headers[:20]],
                  'rows': [[str(v)[:1000] for v in row] for row in rows], 'truncated': truncated})

    def lines(self, series, *, title='曲线', bars=False):
        if not isinstance(series, dict) or not 1 <= len(series) <= 16:
            raise ValueError('图表需要名称到数值序列的字典，最多 16 条序列。')
        normalized = {}
        truncated = False
        for name, values in series.items():
            if len(values) > 5000:
                truncated = True
            result = []
            for value in values[:5000]:
                number = float(value) if value is not None else float('nan')
                result.append(number if math.isfinite(number) else None)
            normalized[str(name)[:100]] = result
        self.add({'kind': 'bars' if bars else 'lines', 'title': str(title)[:200],
                  'series': normalized, 'truncated': truncated})
