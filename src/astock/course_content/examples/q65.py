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

class TinyAttention(nn.Module):
    def __init__(self):
        super().__init__()
        self.input = nn.Linear(1, 8)
        self.position = nn.Parameter(torch.zeros(1, 8, 8))
        layer = nn.TransformerEncoderLayer(d_model=8, nhead=2, dim_feedforward=16,
                                          dropout=0., batch_first=True)
        self.encoder = nn.TransformerEncoder(layer, num_layers=1, enable_nested_tensor=False)
        self.head = nn.Linear(8, 1)
    def encode(self, x):
        length = x.shape[1]
        mask = torch.triu(torch.ones(length, length, dtype=torch.bool), diagonal=1)
        return self.encoder(self.input(x) + self.position[:, :length], mask=mask)
    def forward(self, x):
        return self.head(self.encode(x)[:, -1])
model = TinyAttention()
best, test_loss, curve = fit(model, epochs=45)
print("Attention验证MSE", best, "测试MSE", test_loss)
model.eval()
with torch.no_grad():
    original = X[te][:2].clone()
    changed = original.clone()
    changed[:, -1] += 100
    early_original = model.encode(original)[:, :-1]
    early_changed = model.encode(changed)[:, :-1]
torch.testing.assert_close(early_original, early_changed, rtol=1e-4, atol=1e-5)
print("因果掩码：改变最后位置不影响更早位置输出")

