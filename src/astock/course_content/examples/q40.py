import pandas as pd
p=pd.Series([10.,11.,10.,12.,11.,13.,12.,14.])
def causal(x):
    return x>x.rolling(3,min_periods=3).mean()

def cheating(x):
    return x.shift(-1)>x
changed=p.copy()
changed.iloc[5:]=[1.,100.,1.]
assert causal(p).iloc[:5].equals(causal(changed).iloc[:5])
assert not cheating(p).iloc[:5].equals(cheating(changed).iloc[:5])
print("因果信号",causal(p).tolist())
print("偷看明天",cheating(p).tolist())
print("过去信号未来扰动测试：因果规则通过，作弊规则失败。")
survivor_returns=pd.Series({"存活A":.2,"存活B":.1,"退市C":-.9})
print("只看存活",survivor_returns.iloc[:2].mean(),"完整小样本",survivor_returns.mean())
assert survivor_returns.mean()<survivor_returns.iloc[:2].mean()

