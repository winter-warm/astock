import numpy as np
def rebalance(current,target,equity,fee_rate=.001,threshold=.05):
    current=np.asarray(current,float)
    target=np.asarray(target,float)
    if np.max(np.abs(current-target))<=threshold:
        return current,0.,0.
    traded_fraction=float(np.abs(target-current).sum())
    cost=equity*traded_fraction*fee_rate
    return target,traded_fraction,cost
weight,turn,cost=rebalance([.55,.45],[.5,.5],100000,threshold=.06)
assert turn==0 and cost==0
weight,turn,cost=rebalance([.7,.3],[.5,.5],100000,threshold=.06)
print("目标",weight,"双边成交占净值",round(turn,3),"费用",round(cost,2))
assert np.isclose(turn,.4) and np.isclose(cost,40)

