"""三个研究角色：离线响应由作者编写；真实调用必须显式开启。"""
import importlib.util
import json
from pathlib import Path
import re
import numpy as np
import pandas as pd


adapter = (Path(__file__).with_name("q67-api.py") if "__file__" in globals()
           else Path("examples/q67-api.py"))
spec = importlib.util.spec_from_file_location("course_model_client", adapter)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
client = module.configured_client()
mode = "real-model" if client else "offline-authored"
rng = np.random.default_rng(71)
close = pd.Series(100*np.cumprod(1+rng.normal(0, .01, 240)))
future = close.shift(-1)/close-1
trace = []

def signal_agent(round_id):
    if client:
        card = json.loads(client.ask('仅返回JSON {"operator":"momentum","lookback":5} 形式，operator只允许momentum或reversal，lookback为2到30整数。任务为人工价格研究，禁止收益承诺。'))
    else:
        card = {"operator": "momentum", "lookback": [3, 5, 10][round_id]}
    if not isinstance(card, dict) or set(card) != {"operator", "lookback"}:
        raise ValueError("假设必须且只能包含operator与lookback")
    if card.get("operator") not in {"momentum", "reversal"}:
        raise ValueError("假设算子无效")
    if type(card.get("lookback")) is not int or not 2 <= card["lookback"] <= 30:
        raise ValueError("假设窗口无效")
    return card

def code_agent(card):
    expected = f'{card["operator"]}(close, {card["lookback"]})'
    if client:
        response = json.loads(client.ask('仅返回JSON，字段expression。把假设转换为算子表达式，必须与此字符串完全一致：' + expected))
        expression = response.get("expression")
    else:
        expression = expected
    if expression != expected or not re.fullmatch(r"(momentum|reversal)\(close, [0-9]+\)", expression):
        raise ValueError("生成表达式不符合已验证假设")
    return expression

def evaluation_agent(card, section):
    score = close/close.shift(card["lookback"])-1
    if card["operator"] == "reversal":
        score = -score
    target = (score > 0).astype(float)*.5
    traded = target.diff().abs().fillna(target.abs())
    # Select the authorized interval before touching its labels or computing P&L.
    net = target.iloc[section]*future.iloc[section] - .001*traded.iloc[section]
    assert net.index.equals(close.iloc[section].index)
    return net

for round_id in range(1 if client else 3):
    card = signal_agent(round_id)
    expression = code_agent(card)
    validation_net = evaluation_agent(card, slice(100, 170))
    trace.append({"round": round_id, "hypothesis": card, "expression": expression,
                  "validation_mean": float(validation_net.mean())})
winner = max(trace, key=lambda row: row["validation_mean"])
frozen = dict(winner["hypothesis"])
holdout = evaluation_agent(frozen, slice(180, 239))
summary = {"mode": mode, "trace": trace, "frozen": frozen,
           "holdout_mean": float(holdout.mean()), "real_model_calls": client.calls if client else 0}
if client:
    validation_only = {"data_kind": "synthetic", "trace": trace, "frozen": frozen}
    summary["model_commentary_unverified"] = client.ask("用一句话指出以下人工数据验证结果的局限，不增加数值或收益承诺：" + json.dumps(validation_only, ensure_ascii=False))
    summary["real_model_calls"] = client.calls
print(json.dumps(summary, ensure_ascii=False, indent=2))
assert len(trace) == (1 if client else 3)
assert summary["real_model_calls"] <= 3
assert np.isfinite(holdout).all()
assert all("holdout" not in row for row in trace)

