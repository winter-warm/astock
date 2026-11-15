# 可运行的事件顺序演示。真实引擎练习使用随课 strategy 文件。
events=[("bar",10),("bar",11),("bar",12)]
pending=None
position=0
trace=[]
for i,(_,price) in enumerate(events):
    if pending is not None:
        position+=pending
        trace.append((i,"fill",position))
        pending=None
    trace.append((i,"observe",price))
    if i==0:
        pending=100
        trace.append((i,"submit",pending))
print(trace)
assert trace[0]==(0,"observe",10)
assert trace[1]==(0,"submit",100)
assert trace[2]==(1,"fill",100)
assert trace[3]==(1,"observe",11)

