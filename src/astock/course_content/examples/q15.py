import numpy as np
a = np.array([-.02, -.01, 0., .01, .02])
b = 2 * a + .003
c = -a
corr = np.corrcoef(np.vstack([a, b, c]))
print("相关矩阵\n", corr)
np.testing.assert_allclose(corr[0, 1], 1)
np.testing.assert_allclose(corr[0, 2], -1)
cov = np.cov(a, b, ddof=1)[0, 1]
manual = cov / (a.std(ddof=1) * b.std(ddof=1))
np.testing.assert_allclose(manual, 1)
# 零线性相关仍可能有确定的非线性关系。
x = np.array([-2., -1., 0., 1., 2.])
y = x ** 2
np.testing.assert_allclose(np.corrcoef(x, y)[0, 1], 0, atol=1e-14)
print("x 与 x² 的线性相关", np.corrcoef(x, y)[0, 1])

