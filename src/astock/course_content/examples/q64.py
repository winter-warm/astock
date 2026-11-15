"""人工单变量序列；CPU、小网络、固定种子，不代表真实证券收益。"""
import copy
import numpy as np
import torch
from torch import nn

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

class SequenceModel(nn.Module):
    def __init__(self):
        super().__init__()
        self.lstm = nn.LSTM(input_size=1, hidden_size=8, batch_first=True)
        self.head = nn.Linear(8, 1)
    def forward(self, x):
        output, (hidden, cell) = self.lstm(x)
        assert output.shape[:2] == x.shape[:2]
        return self.head(hidden[-1])
model = SequenceModel()
best, test_loss, curve = fit(model)
print("LSTM验证MSE", best, "测试MSE", test_loss)
print("参数量", sum(p.numel() for p in model.parameters()))
model.eval()
with torch.no_grad():
    alone = model(X[te][:1])
    batch = model(X[te][:3])[:1]
torch.testing.assert_close(alone, batch, rtol=1e-5, atol=1e-6)
print("独立窗口预测不依赖同批其他样本：通过")

