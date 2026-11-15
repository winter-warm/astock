from copy import deepcopy
from datetime import timedelta
from queue import Queue

from astock.datasets import write_dataset
from astock.domain import MatchConfig, Quote, dec, dumps, loads
from astock.engine import Run
from astock.live_rules import build_live_rules
from astock.rules import rule_at
from test_live_rules import AT, dated_catalog


def test_context_before_activation_does_not_expose_later_t0_or_future_time():
    rules, _ = build_live_rules(["158000"], dated_catalog(), AT + timedelta(hours=1))
    r = rules["158000.SZ"]
    before = rule_at(r, "2026-11-13", observed_at=AT)
    assert before.status == "unknown" and before.t_plus == 1
    assert not before.history and not before.known_from
    after = rule_at(r, "2026-11-13", observed_at=AT + timedelta(hours=1))
    assert after.status == "normal" and after.t_plus == 0
    assert loads(dumps(r)) == r


def test_recorded_rule_activation_does_not_trade_earlier_replay_inputs(tmp_path):
    rules, _ = build_live_rules(["158000"], dated_catalog(), AT + timedelta(hours=1))
    def quote(seconds):
        at = AT + timedelta(seconds=seconds)
        return Quote("158000.SZ", at, at, dec(10), dec(10), dec(10), 100000, 100000,
                     100000 + seconds * 100, dec(10), dec(11), dec(9), observed=at)
    events = [quote(x) for x in (0, 5, 3600, 3605)]
    meta = write_dataset(tmp_path / "datasets", "合成规则启用时刻测试", events,
                         demo=True, verified=True, rules=rules)
    code = '''
class UserStrategy(Strategy):
    def initialize(self, ctx):
        self.ordered = False
    def on_quote(self, ctx, quote):
        if not self.ordered:
            self.ordered = True
            ctx.order(quote.symbol, "BUY", 100, quote.last, "已取得规则后下单")
'''
    run = Run({"mode": "replay", "dataset": meta["id"], "code": code,
               "config": MatchConfig(participation=dec(1), slippage_ticks=0)}, tmp_path, Queue())
    try:
        run.step()
        run.step()
        assert not run.broker.orders and not run.broker.trades
        assert run.context()["rules"]["158000.SZ"].status == "unknown"
        run.step()
        assert len(run.broker.orders) == 1 and not run.broker.trades
        run.step()
        assert len(run.broker.trades) == 1
        assert run.broker.trades[0].time == AT + timedelta(seconds=3605)
        assert rules == loads(dumps(deepcopy(rules)))
    finally:
        run.stop()
