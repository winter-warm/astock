"""Course assertions execute the exact resources shown to the learner."""
from pathlib import Path
from queue import Queue
import json
import re
import runpy

import pytest

from astock.datasets import ensure_demo, list_datasets
from astock.domain import MatchConfig
from astock.engine import Run
from astock.strategy import parameter_schema


ROOT = Path(__file__).resolve().parents[1] / 'src/astock/course_content'


def test_strategy_curriculum_has_complete_text_and_separate_exercises():
    entries = json.loads((ROOT / 'catalogue-strategies.json').read_text(encoding='utf-8'))
    assert [entry['id'] for entry in entries] == [f'q{n}' for n in range(29, 49)]
    for entry in entries:
        text = (ROOT / entry['body']).read_text(encoding='utf-8')
        assert len(re.findall(r'[\u4e00-\u9fff]', text)) >= 2000, entry['id']
        assert '## 练习\n' in text and '## 参考答案\n' in text
        assert entry['check']['question'] and entry['check']['answers'] and entry['check']['explanation']
        references = set(re.findall(r'\{\{code:([^}]+)\}\}', text))
        assert references == {example['id'] for example in entry['examples']}, entry['id']
        assert all((ROOT / example['file']).is_file() for example in entry['examples'])


@pytest.mark.parametrize('number', [n for n in range(29, 49) if n != 42])
def test_calculation_examples(number, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runpy.run_path(str(ROOT / 'examples' / f'q{number}.py'), run_name='__main__')


@pytest.mark.parametrize('number', [29, 30, 31, 32, 33, 38])
def test_actual_strategy_engine_execution(number, tmp_path):
    ensure_demo(tmp_path / 'datasets')
    dataset = next(row for row in list_datasets(tmp_path / 'datasets') if row['kind'] == 'bar')
    code = (ROOT / 'examples' / f'q{number}-strategy.py').read_text(encoding='utf-8')
    parameters = {name: value['default'] for name, value in parameter_schema(code).items()}
    run = Run({'name': f'课程{number}', 'mode': 'backtest', 'dataset': dataset['id'],
               'code': code, 'parameters': parameters, 'initial': 100000,
               'config': MatchConfig(), 'speed': 1000}, tmp_path, Queue())
    try:
        while run.status == 'RUNNING':
            run.step()
        assert run.status == 'COMPLETED', run.logs[-10:]
        assert run.broker.trades, f'课程{number}应在本人工样本上实际成交'
        run.broker.check_invariants()
        for trade in run.broker.trades:
            order = next(item for item in run.broker.orders if item.id == trade.order_id)
            assert trade.time > order.created
        assert run.broker.account.cash >= 0
    finally:
        if run.host:
            run.host.close()


def test_handwritten_ledger_has_no_same_day_fill_and_reconciles(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    module = runpy.run_path(str(ROOT / 'examples/q37.py'))
    rows, trades = module['backtest']([10., 11., 12., 9.], [10.5, 11.5, 11., 8.], [1, 1, 0, 0])
    assert rows[-1][3] == pytest.approx(818.2)
    assert trades[0] == (1, 'BUY', 90, 11.)
    flat, _ = module['backtest']([10.] * 4, [10.] * 4, [1, 1, 0, 0], fee_rate=0)
    assert flat[-1][3] == 1000
