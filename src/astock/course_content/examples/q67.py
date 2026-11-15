"""三种AI用途的离线编写样例；不是实际模型调用日志。"""
import json

requests = [
    {"task": "解释代码", "input": "close / close.shift(5) - 1",
     "response": "计算过去五个观察区间的相对价格变化；历史不足时应保留缺失。"},
    {"task": "提出假设", "input": "研究动量与费用",
     "response": "在固定验证段比较5期和20期动量，记录换手与扣费结果。"},
    {"task": "审查结论", "input": "合成数据收益为正，所以实盘会盈利",
     "response": "该结论超出证据，合成样本只能验证流程，不能证明实际盈利。"},
]
record = {"mode": "offline-authored", "real_model_calls": 0, "examples": requests}
print(json.dumps(record, ensure_ascii=False, indent=2))
assert record["real_model_calls"] == 0
assert all(row["input"] and row["response"] for row in requests)
print("人工编写的演练响应，不能标记为真实AI验收。")

