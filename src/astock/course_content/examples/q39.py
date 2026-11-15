from decimal import Decimal as D
def fill_buy(limit, next_open, visible, requested, participation, ticks, tick=D(".01")):
    available=int(visible*participation)
    price=D(str(next_open))+ticks*tick
    if price>D(str(limit)):
        return 0,None
    return min(requested,available),price
good=fill_buy(10.05,10,1000,300,.1,1)
tight=fill_buy(10,10,1000,300,.1,1)
thin=fill_buy(10.05,10,1000,300,.01,1)
print("正常",good,"限价不足",tight,"低参与",thin)
assert good==(100,D("10.01"))
assert tight==(0,None)
assert thin[0]==10

