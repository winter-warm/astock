"""Index observations can drive research but never create fictitious shares."""
from dataclasses import replace
from datetime import datetime
from queue import Queue

import pytest

from astock.broker import Broker
from astock.datasets import load_dataset, write_dataset
from astock.domain import Bar, CN, dec
from astock.engine import Run
from astock.rules import INDEX_NAMES, continuous_bar, default_rule, rules_summary, validate_rule


def bar(day, close='4000'):
    return Bar('000300.SH', datetime(2026, 11, day, 15, tzinfo=CN), dec('4000'), dec('4100'),
               dec('3900'), dec(close), 100000000, '1d', dec('4000'))


@pytest.mark.parametrize('symbol', list(INDEX_NAMES))
def test_known_indices_have_research_rules_without_confusing_stock_codes(symbol):
    rule = default_rule(symbol)
    validate_rule(rule)
    assert rule.kind == rule.board == 'index'
    assert rule.limit_rate == 0 and rule.name == INDEX_NAMES[symbol]
    assert '不支持直接买卖' in rules_summary({symbol: rule})
    assert default_rule('000001.SZ').kind == 'stock'
    assert default_rule('510300.SH').kind == 'etf'
    with pytest.raises(ValueError, match='指数代码'):
        validate_rule(replace(rule, kind='stock', t_plus=1))


@pytest.mark.parametrize('side', ['BUY', 'SELL'])
def test_index_orders_are_explicitly_rejected_without_cash_or_positions(side):
    broker = Broker({'000300.SH': default_rule('000300.SH')})
    broker.on_event(bar(12))
    order = broker.submit('000300.SH', side, 100, '4000')
    assert order.status == 'REJECTED' and '指数仅用于观察和研究' in order.note
    broker.on_event(bar(13, '4020'))
    assert not broker.trades and not broker.account.positions
    assert broker.account.cash == broker.account.initial and broker.frozen_cash == 0
    assert broker.market['000300.SH'].close == dec('4020')
    broker.check_invariants()


@pytest.mark.parametrize('period', ['1d', '60m'])
def test_index_dataset_can_run_strategy_history_and_explanations_without_trading(tmp_path, period):
    observations = [bar(11), bar(12, '4010'), bar(13, '4020')]
    if period == '60m':
        observations = [replace(item, period=period, time=datetime(2026, 11, 13, hour, minute, tzinfo=CN))
                        for item, (hour, minute) in zip(observations, [(11, 30), (14, 0), (15, 0)])]
        assert continuous_bar(observations[-1], default_rule('000300.SH'))
        assert not continuous_bar(replace(observations[-1], symbol='600000.SH'), default_rule('600000.SH'))
    meta = write_dataset(tmp_path / 'datasets', '合成测试指数', observations,
                         demo=True, source='test-index-fixture', verified=True,
                         rules={'000300.SH': default_rule('000300.SH')})
    _, points = load_dataset(tmp_path / 'datasets', meta['id'])
    assert len(points) == 3
    code = '''from astock.strategy import Strategy
class UserStrategy(Strategy):
    def on_bar(self, ctx, bar):
        history = ctx.history(bar.symbol, 2)
        if len(history) == 2:
            ctx.explain("指数观察", rising=history[-1] > history[-2])
            ctx.order(bar.symbol, "BUY", 100, float(bar.close), "不可交易指数")
'''
    run = Run({'mode': 'backtest', 'name': '指数信号测试', 'dataset': meta['id'],
               'code': code, 'parameters': {}}, tmp_path, Queue())
    try:
        while run.status == 'RUNNING':
            run.step()
        assert run.status == 'COMPLETED'
        assert len(run.history['000300.SH']) == 3
        assert len(run.broker.orders) == 2
        assert all(order.status == 'REJECTED' for order in run.broker.orders)
        assert not run.broker.trades and run.broker.account.cash == run.broker.account.initial
        assert len(run.curve) == 3
    finally:
        if run.host:
            run.host.close()
