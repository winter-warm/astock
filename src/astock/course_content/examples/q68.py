"""结构化假设卡；本例离线编写，没有模型调用。"""
from dataclasses import dataclass, asdict
import json

@dataclass(frozen=True)
class Hypothesis:
    name: str
    operator: str
    lookback: int
    decision: str
    target_horizon: int
    candidate_id: str

def validate(card):
    if card.operator not in {"momentum", "reversal"}:
        raise ValueError("只允许已定义算子")
    if type(card.lookback) is not int or not 2 <= card.lookback <= 30:
        raise ValueError("回看窗口须为2—30的整数")
    if card.decision != "after_completed_bar":
        raise ValueError("决策时点必须是完成K线之后")
    if type(card.target_horizon) is not int or card.target_horizon != 1:
        raise ValueError("本实验固定一步预测，不在搜索中更换标签")
    return card

card = validate(Hypothesis("五期动量", "momentum", 5, "after_completed_bar", 1, "candidate-001"))
print(json.dumps(asdict(card), ensure_ascii=False, indent=2))
try:
    validate(Hypothesis("错误未来收益", "future_return", 5, "after_completed_bar", 1, "bad"))
except ValueError as error:
    print("预期拒绝：", error)
else:
    raise AssertionError("未拒绝未知算子")
assert card.lookback == 5 and card.target_horizon == 1

