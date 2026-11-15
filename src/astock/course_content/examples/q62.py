"""构造人工序列窗口并通过 Dataset/DataLoader 批量读取。"""
import numpy as np
import torch
from torch.utils.data import TensorDataset, DataLoader

rng = np.random.default_rng(62)
series = rng.normal(size=60).astype(np.float32)
lookback = 8
def make_windows(values):
    times = np.arange(lookback-1, len(values)-1)
    X = np.array([values[t-lookback+1:t+1] for t in times])[..., None]
    y = values[times+1, None]
    return times, X, y
times, X, y = make_windows(series)
train_mask = times+1 < 40
test_mask = times >= 40
mean, scale = X[train_mask].mean(), X[train_mask].std()
dataset = TensorDataset(torch.tensor((X[train_mask]-mean)/scale), torch.tensor(y[train_mask]))
loader = DataLoader(dataset, batch_size=8, shuffle=False, num_workers=0)
batch_x, batch_y = next(iter(loader))
print("全部形状：", X.shape, y.shape, "首批：", tuple(batch_x.shape), tuple(batch_y.shape))
assert batch_x.shape == (8, lookback, 1)
assert times[train_mask].max()+1 < times[test_mask].min()
changed = series.copy()
changed[40:] = 999
t2, x2, y2 = make_windows(changed)
np.testing.assert_array_equal(X[train_mask], x2[train_mask])
np.testing.assert_array_equal(y[train_mask], y2[train_mask])
print("未来数据改变不污染训练样本：通过")

