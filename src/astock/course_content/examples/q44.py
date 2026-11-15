closes=[10.,11.,12.,11.5,10.5,9.]
next_opens=[10.,11.,12.,11.5,8.,9.]
highest=closes[0]
signals=[]
for i,close in enumerate(closes):
    highest=max(highest,close)
    trailing=highest*.9
    signals.append(close<trailing)
print("收盘退出信号",signals)
signal_day=next(i for i,v in enumerate(signals) if v)
execution_day=signal_day+1
print("信号日",signal_day,"下一开盘",next_opens[execution_day])
assert signal_day==4 and execution_day==5
# 另外演示：若跳空当天才首次有机会执行，9.5 的止损线不能保证9.5成交。
stop_level=9.5
gap_open=8.
print("止损线",stop_level,"跳空开盘",gap_open,"价格差",stop_level-gap_open)
assert gap_open<stop_level

