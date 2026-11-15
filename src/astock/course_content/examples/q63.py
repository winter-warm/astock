"""人工单变量序列；CPU、小网络、固定种子，不代表真实证券收益。"""
import copy
import numpy as np
import torch
from torch import nn
import matplotlib.pyplot as plt

torch.set_num_threads(1)
torch.manual_seed(61)
rng = np.random.default_rng(61)
r = np.zeros(360, dtype=np.float32)
for t in range(1, len(r)):
    r[t] = .35*r[t-1] + rng.normal(0, 1)
times = np.arange(7, len(r)-1)
raw = np.array([r[t-7:t+1] for t in times], dtype=np.float32)[..., None]
target = r[times+1, None]
tr, va, te = slice(0, 200), slice(201, 260), slice(261, None)
mu, sd = raw[tr].mean(), raw[tr].std()
X = torch.tensor((raw-mu)/sd)
y = torch.tensor(target)
assert times[199]+1 < times[201]
assert X.ndim == 3 and X.shape[1:] == (8, 1)

def fit(model, epochs=65):
    optimizer = torch.optim.Adam(model.parameters(), lr=.01)
    best, state, curve = float("inf"), None, []
    for epoch in range(epochs):
        model.train()
        optimizer.zero_grad()
        loss = nn.functional.mse_loss(model(X[tr]), y[tr])
        loss.backward()
        nn.utils.clip_grad_norm_(model.parameters(), 1.)
        optimizer.step()
        model.eval()
        with torch.no_grad():
            val = nn.functional.mse_loss(model(X[va]), y[va]).item()
        curve.append((loss.item(), val))
        if val < best:
            best, state = val, copy.deepcopy(model.state_dict())
    model.load_state_dict(state)
    model.eval()
    with torch.no_grad():
        prediction = model(X[te])
        test_loss = nn.functional.mse_loss(prediction, y[te]).item()
    assert prediction.shape == y[te].shape and torch.isfinite(prediction).all()
    return best, test_loss, curve

class MLP(nn.Module):
    def __init__(self):
        super().__init__()
        self.net = nn.Sequential(nn.Flatten(), nn.Linear(8, 16), nn.ReLU(),
                                 nn.Dropout(.1), nn.Linear(16, 1))
    def forward(self, x):
        return self.net(x)
model = MLP()
best, test_loss, curve = fit(model)
baseline = ((y[te]-y[tr].mean())**2).mean().item()
print("最佳验证MSE", best, "测试MSE", test_loss, "训练均值基线MSE", baseline)
fig, ax = plt.subplots(figsize=(6, 3))
ax.plot(np.array(curve)[:, 0], label="train")
ax.plot(np.array(curve)[:, 1], label="validation")
ax.set(xlabel="epoch", ylabel="MSE", title="Synthetic MLP")
ax.legend()
fig.tight_layout()
plt.show()

