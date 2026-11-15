"""受限表达式解释器：不exec模型生成的任意Python。"""
import ast
import numpy as np
import pandas as pd


def evaluate(expression, close):
    if len(expression) > 200:
        raise ValueError("表达式过长")
    tree = ast.parse(expression, mode="eval")
    node = tree.body
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
        raise ValueError("只允许算子调用")
    if node.func.id not in {"momentum", "reversal"} or node.keywords or len(node.args) != 2:
        raise ValueError("算子或参数数量无效")
    field, window = node.args
    if not isinstance(field, ast.Name) or field.id != "close":
        raise ValueError("只允许close输入")
    if not isinstance(window, ast.Constant) or type(window.value) is not int or not 2 <= window.value <= 30:
        raise ValueError("窗口无效")
    result = close / close.shift(window.value) - 1
    return -result if node.func.id == "reversal" else result

prices = pd.Series([100., 101., 102., 103., 104., 105., 106., 107.])
candidate = "momentum(close, 3)"
result = evaluate(candidate, prices)
assert np.isclose(result.iloc[3], .03)
changed = prices.copy()
changed.iloc[6:] *= 10
np.testing.assert_allclose(result.iloc[:6], evaluate(candidate, changed).iloc[:6], equal_nan=True)
for bad in ["__import__('os').system('echo bad')", "momentum(close, -1)", "close.shift(-1)", "momentum(close, True)"]:
    try:
        evaluate(bad, prices)
    except (ValueError, SyntaxError):
        pass
    else:
        raise AssertionError("非法候选未被拒绝")
print(result.to_string())
print("数值、未来不变性和非法候选拒绝：通过")

