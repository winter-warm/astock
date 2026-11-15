"""Reconcile trades and non-trade equity postings against the account snapshot."""
from collections import defaultdict

from astock.domain import CN, ZERO, dec, money


LEGACY_NOTICE = "旧版本权益流水不完整：保留账户供查看，无法验证守恒；请用原数据重新运行"


def reconcile(broker):
    if broker.legacy_equity_unverified:
        raise RuntimeError(LEGACY_NOTICE)
    account = broker.account
    cash, cost = account.initial, ZERO
    quantities = defaultdict(int)
    fees = realized = ZERO
    for trade in broker.trades:
        sign = 1 if trade.side == "BUY" else -1
        cash -= sign * trade.quantity * trade.price + trade.fee
        cost += trade.quantity * trade.price + trade.fee if sign == 1 else (
            -(trade.quantity * trade.price - trade.fee - trade.realized))
        fees += trade.fee
        realized += trade.realized
    entries = broker.equity_entries
    ids, entitlements, payments = set(), {}, set()
    pending = {}
    timeline = [(t.time, 1, t) for t in broker.trades] + [(e.time, 0, e) for e in entries]
    for timestamp, kind, entry in sorted(timeline, key=lambda item: (item[0], item[1])):
        if kind == 1:
            quantities[entry.symbol] += entry.quantity * (1 if entry.side == "BUY" else -1)
            continue
        if entry.id in ids:
            raise RuntimeError("记账校验失败：重复权益流水")
        ids.add(entry.id)
        action = broker.action_definitions.get(entry.action_key)
        if action is None or action.key != entry.action_key or action.symbol != entry.symbol:
            raise RuntimeError("记账校验失败：权益流水缺少对应事件")
        action.validate()
        if entry.pay_date != action.pay_date or entry.share_available_date != action.share_available_date:
            raise RuntimeError("记账校验失败：权益日期与事件不一致")
        if entry.kind == "entitlement":
            quantity = quantities[entry.symbol]
            expected_delta = dec(quantity) * (action.share_multiplier - 1)
            amount = money(quantity * action.cash_per_share)
            if (entry.action_key in entitlements or timestamp != action.time or entry.quantity_before != quantity
                    or entry.quantity_delta != expected_delta or entry.cash_delta != ZERO
                    or entry.receivable_delta != amount):
                raise RuntimeError("记账校验失败：权益登记与持仓/分配比例不一致")
            quantities[entry.symbol] += entry.quantity_delta
            entitlements[entry.action_key] = entry
            if amount:
                pending[entry.action_key] = {"action_key": entry.action_key, "symbol": entry.symbol,
                                             "amount": amount, "pay_date": entry.pay_date}
        elif entry.kind == "payment":
            entitlement = entitlements.get(entry.action_key)
            if (entitlement is None or entry.action_key in payments or entitlement.receivable_delta <= 0
                    or entry.quantity_before != 0 or entry.quantity_delta != 0
                    or entry.cash_delta != entitlement.receivable_delta
                    or entry.receivable_delta != -entry.cash_delta
                    or timestamp.astimezone(CN).date().isoformat() < entry.pay_date):
                raise RuntimeError("记账校验失败：分红重复到账、提前到账或金额错误")
            payments.add(entry.action_key)
            pending.pop(entry.action_key)
        else:
            raise RuntimeError("记账校验失败：未知权益流水类型")
        cash += entry.cash_delta
    if set(entitlements) != broker.applied_actions or set(entitlements) != set(broker.action_definitions):
        raise RuntimeError("记账校验失败：已处理权益事件与流水不一致")
    actual_pending = {item.get("action_key"): item for item in account.receivables}
    if len(actual_pending) != len(account.receivables) or actual_pending != pending:
        raise RuntimeError("记账校验失败：应收权益与流水不一致")
    if abs(cash - account.cash) > dec("0.001"):
        raise RuntimeError("记账校验失败：现金流水不一致")
    for symbol in set(quantities) | set(account.positions):
        pos = account.positions.get(symbol)
        if quantities[symbol] != (pos.quantity if pos else 0):
            raise RuntimeError(f"记账校验失败：{symbol} 持仓与成交/权益流水不一致")
    if fees != account.fees or abs(realized - account.realized) > dec("0.001"):
        raise RuntimeError("记账校验失败：累计费用或已实现盈亏不一致")
    if abs(cost - sum((p.cost for p in account.positions.values()), ZERO)) > dec("0.001"):
        raise RuntimeError("记账校验失败：持仓成本流水不一致")
