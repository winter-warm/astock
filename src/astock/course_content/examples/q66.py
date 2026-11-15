"""人工单变量序列；CPU、小网络、固定种子，不代表真实证券收益。"""
import copy
import numpy as np
import torch
from torch import nn
from sklearn.linear_model import Ridge

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
        self.net = nn.Sequential(nn.Flatten(), nn.Linear(8, 16), nn.ReLU(), nn.Linear(16, 1))
    def forward(self, x):
        return self.net(x)
class LSTM(nn.Module):
    def __init__(self):
        super().__init__()
        self.net = nn.LSTM(1, 8, batch_first=True)
        self.head = nn.Linear(8, 1)
    def forward(self, x):
        _, (hidden, _) = self.net(x)
        return self.head(hidden[-1])
class Attention(nn.Module):
    def __init__(self):
        super().__init__()
        self.input = nn.Linear(1, 8)
        self.position = nn.Parameter(torch.zeros(1, 8, 8))
        layer = nn.TransformerEncoderLayer(8, 2, 16, dropout=0., batch_first=True)
        self.net = nn.TransformerEncoder(layer, 1, enable_nested_tensor=False)
        self.head = nn.Linear(8, 1)
    def forward(self, x):
        mask = torch.triu(torch.ones(8, 8, dtype=torch.bool), diagonal=1)
        h = self.net(self.input(x)+self.position, mask=mask)
        return self.head(h[:, -1])
results = {}
ridge = Ridge(alpha=10.).fit(X[tr].numpy().reshape(-1, 8), y[tr].numpy().ravel())
for name, cls in [("MLP", MLP), ("LSTM", LSTM), ("Attention", Attention)]:
    torch.manual_seed(66)
    model = cls()
    val, test_error, _ = fit(model, epochs=45)
    results[name] = {"validation": val, "test": test_error, "parameters": sum(p.numel() for p in model.parameters())}
for name, prediction_val, prediction_test in [
    ("Ridge", ridge.predict(X[va].numpy().reshape(-1, 8)), ridge.predict(X[te].numpy().reshape(-1, 8))),
    ("Constant", np.full(len(y[va]), y[tr].mean().item()), np.full(len(y[te]), y[tr].mean().item()))]:
    results[name] = {"validation": float(np.mean((prediction_val-y[va].numpy().ravel())**2)),
                     "test": float(np.mean((prediction_test-y[te].numpy().ravel())**2)), "parameters": 9 if name == "Ridge" else 1}
winner = min(results, key=lambda name: results[name]["validation"])
for name, row in results.items():
    print(name, row)
print("仅按验证选择：", winner, "冻结测试误差：", results[winner]["test"])
assert len(results) == 5
assert all(np.isfinite(row["test"]) for row in results.values())

