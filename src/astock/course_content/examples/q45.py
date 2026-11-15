import numpy as np
returns=np.array([[.01,.005],[-.01,.002],[.02,-.004],[-.02,.003],[.01,.001]])
vol=returns.std(axis=0,ddof=1)
equal=np.array([.5,.5])
inverse=(1/vol)/(1/vol).sum()
cov=np.cov(returns,rowvar=False,ddof=1)
def risk(weights):
    return float(np.sqrt(weights@cov@weights))
print("波动",vol,"等权",equal,"逆波动",inverse)
print("等权波动",risk(equal),"逆波动组合波动",risk(inverse))
print("相关矩阵",np.corrcoef(returns,rowvar=False))
assert np.isclose(inverse.sum(),1)
assert inverse[1]>inverse[0]
assert risk(equal)>=0

