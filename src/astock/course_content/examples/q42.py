# 在外部课程 Notebook 环境执行：需要 backtrader。
import backtrader as bt
import pandas as pd
frame=pd.DataFrame({"open":[10.,11.,12.,13.,14.],
                    "high":[11.,12.,13.,14.,15.],
                    "low":[9.,10.,11.,12.,13.],
                    "close":[10.5,11.5,12.5,13.5,14.5],
                    "volume":[10000]*5},
                   index=pd.date_range("2026-01-05",periods=5,freq="D"))
class Demo(bt.Strategy):
    def __init__(self):
        self.executions=[]
    def next(self):
        if len(self)==1:
            self.buy(size=10)
    def notify_order(self,order):
        if order.status==order.Completed:
            self.executions.append((order.executed.size,order.executed.price))
c=bt.Cerebro(stdstats=False,cheat_on_open=False)
c.broker.setcash(1000)
c.broker.setcommission(commission=0.0)
c.broker.set_coc(False)
c.adddata(bt.feeds.PandasData(dataname=frame))
c.addstrategy(Demo)
result=c.run(maxcpus=1)[0]
print("执行",result.executions,"期末权益",c.broker.getvalue())
assert result.executions==[(10,11.0)]
assert abs(c.broker.getvalue()-1035)<1e-8

