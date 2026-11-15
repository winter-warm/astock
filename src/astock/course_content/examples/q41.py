import numpy as np
import pandas as pd
p=pd.Series(10+np.arange(180)*.01+.6*np.sin(np.arange(180)/4))
def score(segment,period):
    target=(segment>segment.rolling(period,min_periods=period).mean()).astype(float)
    held=target.shift(1,fill_value=0)
    net=held*segment.pct_change(fill_method=None).fillna(0)-held.diff().abs().fillna(0)*.001
    return float((1+net).prod()-1)
candidates=[3,5,10]
training=p.iloc[:90].reset_index(drop=True)
validation=p.iloc[90:135].reset_index(drop=True)
testing=p.iloc[135:].reset_index(drop=True)
train_scores={n:score(training,n) for n in candidates}
chosen=max(train_scores,key=train_scores.get)
validation_result=score(validation,chosen)
test_result=score(testing,chosen)
print("训练候选",train_scores,"固定参数",chosen)
print("验证",validation_result,"最终测试",test_result)
assert chosen in candidates
assert len(training)+len(validation)+len(testing)==len(p)

