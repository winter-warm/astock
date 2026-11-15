"""先学训练循环：人工直线拟合，非金融预测结果。"""
import torch
from torch import nn
import matplotlib.pyplot as plt

torch.set_num_threads(1)
torch.manual_seed(61)
x = torch.linspace(-1, 1, 100).reshape(-1, 1)
y = 2*x + 1
model = nn.Linear(1, 1)
optimizer = torch.optim.SGD(model.parameters(), lr=.1)
losses = []
for epoch in range(120):
    optimizer.zero_grad()
    pred = model(x)
    loss = nn.functional.mse_loss(pred, y)
    loss.backward()
    optimizer.step()
    losses.append(loss.item())
model.eval()
with torch.no_grad():
    prediction = model(torch.tensor([[.5]]))
print("权重与偏置：", model.weight.item(), model.bias.item())
print("x=0.5 的预测：", prediction.item())
assert losses[-1] < losses[0] * .001
assert abs(prediction.item()-2) < .01
fig, ax = plt.subplots(figsize=(6, 3))
ax.plot(losses)
ax.set(xlabel="epoch", ylabel="training MSE", title="Synthetic linear fit")
fig.tight_layout()
plt.show()

