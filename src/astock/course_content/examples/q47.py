import numpy as np
gross=np.array([.01,.01,-.02,.005,-.01,.02])
turnover=np.array([1,0,0,1,0,1])
def stress(cost,gap=0):
    net=gross-turnover*cost
    net=net.copy()
    net[2]+=gap
    equity=np.r_[1.,np.cumprod(1+net)]
    drawdown=1-equity/np.maximum.accumulate(equity)
    return float(equity[-1]-1),float(drawdown.max())
base=stress(.001)
expensive=stress(.005)
gap=stress(.001,-.1)
print("基础",base,"高成本",expensive,"额外跳空",gap)
assert expensive[0]<base[0]
assert gap[1]>base[1]
assert all(np.isfinite(x) for x in base)

