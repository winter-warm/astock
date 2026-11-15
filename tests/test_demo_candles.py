"""Synthetic candle quality and non-destructive migration of teaching data."""
from collections import defaultdict
from datetime import datetime
from statistics import median

from astock.datasets import (
    DEMO_BAR_SOURCE, DEMO_QUOTE_SOURCE, ensure_demo, list_datasets, load_dataset, write_dataset,
)
from astock.domain import Bar, CN, Quote, dec, dumps


def current_bars(root):
    ensure_demo(root)
    meta = next(item for item in list_datasets(root) if item['source'] == DEMO_BAR_SOURCE)
    return load_dataset(root, meta['id'])


def test_synthetic_candles_have_valid_varied_shapes_and_session_continuity(tmp_path):
    meta, bars = current_bars(tmp_path)
    assert meta['demo'] and '合成' in meta['name'] and '不对应真实' in meta['notes']
    assert len(bars) == 540
    by_symbol = defaultdict(list)
    for bar in bars:
        assert 0 < bar.low <= min(bar.open, bar.close) <= max(bar.open, bar.close) <= bar.high
        assert bar.volume > 0
        assert max(abs(bar.high / bar.prev_close - 1), abs(bar.low / bar.prev_close - 1)) < dec('.1')
        assert all(price % dec('.001') == 0 for price in (bar.open, bar.high, bar.low, bar.close))
        by_symbol[bar.symbol].append(bar)
    for rows in by_symbol.values():
        assert len(rows) == 180
        assert all(current.prev_close == previous.close for previous, current in zip(rows, rows[1:]))
        assert sum(row.close > row.open for row in rows) > 35
        assert sum(row.close < row.open for row in rows) > 35
        assert any(row.open > row.prev_close for row in rows)
        assert any(row.open < row.prev_close for row in rows)
        assert len({row.volume for row in rows}) > 150
    ranges = [float(bar.high - bar.low) for bar in bars]
    bodies = [float(abs(bar.close - bar.open)) / span if span else 0 for bar, span in zip(bars, ranges)]
    # Avoid the previous tiny bodies surrounded by two near-identical 0.8% wicks.
    assert 0.3 < median(bodies) < 0.85
    assert sum(value < 0.2 for value in bodies) > 20
    assert sum(value > 0.8 for value in bodies) > 50
    assert any(bar.high == max(bar.open, bar.close) for bar in bars)
    assert any(bar.low == min(bar.open, bar.close) for bar in bars)
    assert sum(bar.high - max(bar.open, bar.close) != min(bar.open, bar.close) - bar.low
               for bar in bars) > len(bars) / 2


def test_demo_prices_are_reproducible_across_independent_directories(tmp_path):
    first_meta, first_bars = current_bars(tmp_path / 'first')
    second_meta, second_bars = current_bars(tmp_path / 'second')
    assert first_meta['id'] != second_meta['id']
    assert dumps(first_bars) == dumps(second_bars)
    assert first_meta['sha256'] == second_meta['sha256']


def test_new_demo_is_added_once_without_rewriting_old_manifests_or_quotes(tmp_path):
    at = datetime(2026, 9, 11, 15, tzinfo=CN)
    old_bar = Bar('510300.SH', at, dec('4'), dec('4.042'), dec('3.968'), dec('4.01'), 3000000)
    old_meta = write_dataset(tmp_path, '教学 · 三只 ETF 日线 / 180 日', [old_bar], demo=True,
                             verified=True, source='astock-synthetic-v1')
    quote = Quote('510300.SH', at, at, dec('4'), dec('3.999'), dec('4.001'), 10000, 10000,
                  3000000, dec('4'), dec('4.4'), dec('3.6'))
    quote_meta = write_dataset(tmp_path, '教学 · 秒级快照 / 30 分钟', [quote], demo=True,
                               verified=True, source=DEMO_QUOTE_SOURCE)
    old_files = {path.name: path.read_bytes() for path in tmp_path.iterdir()}
    ensure_demo(tmp_path)
    datasets = list_datasets(tmp_path)
    assert len(datasets) == 3
    assert next(meta for meta in datasets if meta['kind'] == 'bar')['source'] == DEMO_BAR_SOURCE
    assert {meta['id'] for meta in datasets if meta['kind'] == 'quote'} == {quote_meta['id']}
    assert load_dataset(tmp_path, old_meta['id'])[1] == [old_bar]
    assert all((tmp_path / name).read_bytes() == contents for name, contents in old_files.items())
    upgraded_files = {path.name: path.read_bytes() for path in tmp_path.iterdir()}
    ensure_demo(tmp_path)
    assert {path.name: path.read_bytes() for path in tmp_path.iterdir()} == upgraded_files
