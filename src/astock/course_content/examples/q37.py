def backtest(opens, closes, targets, initial=1000., fee_rate=.001):
    cash, qty, pending = initial, 0, None
    rows, trades = [], []
    for i,(opening,closing) in enumerate(zip(opens,closes)):
        if pending == 0 and qty:
            cash += qty*opening*(1-fee_rate)
            trades.append((i,"SELL",qty,opening))
            qty=0
        elif pending == 1 and qty==0:
            qty=int(cash/(opening*(1+fee_rate)))
            cash-=qty*opening*(1+fee_rate)
            if qty:
                trades.append((i,"BUY",qty,opening))
        pending=targets[i]
        equity=cash+qty*closing
        assert cash >= -1e-8
        rows.append((i,cash,qty,equity))
    return rows,trades

rows,trades=backtest([10.,11.,12.,9.],[10.5,11.5,11.,8.],[1,1,0,0])
print("成交",trades)
print("逐日账本",rows)
assert trades[0][0]==1 and trades[0][3]==11
assert trades[1][0]==3 and trades[1][1]=="SELL"
assert abs(rows[0][3]-1000)<1e-8

