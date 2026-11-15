from queue import Queue

import pytest
from PySide6 import QtCore, QtWidgets

from astock.data_identity import display_name, origin_label
from astock.data_jobs import DataJobs
from astock.datasets import DEMO_BAR_SOURCE
from astock.ui_components import PriceChart
from astock.window import MainWindow


@pytest.fixture
def window(qtbot, tmp_path, monkeypatch):
    monkeypatch.setattr(DataJobs, 'start', lambda *args, **kwargs: 'identity-preview')
    window = MainWindow(tmp_path, start_workers=False)
    window.engine_commands = Queue()
    qtbot.addWidget(window)
    window.show()
    return window


@pytest.mark.parametrize(('meta', 'expected'), [
    ({'demo': True, 'source': 'import'}, '合成教学数据'),
    ({'source': 'astock-synthetic-v1'}, '合成教学数据'),
    ({'source': 'akshare-tencent-cninfo'}, '真实历史数据'),
    ({'source': 'akshare-sina-index', 'asset_class': 'index'}, '真实历史数据 · 指数（研究用）'),
    ({'source': 'tencent-recording'}, '真实行情录制'),
    ({'demo': False, 'source': 'import'}, '导入数据 · 真实性待核对'),
    ({'demo': False}, '导入数据 · 真实性待核对'),
])
def test_data_origin_is_explicit_without_claiming_unknown_imports_are_real(meta, expected):
    assert origin_label(meta) == expected
    assert display_name(dict(meta, name='样本')).startswith(expected + '｜')


@pytest.mark.parametrize(('mode', 'status', 'next_kind', 'enabled', 'send'), [
    ('backtest', 'RUNNING', 'quote', False, False),
    ('backtest', 'PAUSED', 'bar', False, False),
    ('replay', 'RUNNING', 'bar', True, True),
    ('replay', 'PAUSED', 'quote', True, True),
    ('backtest', 'COMPLETED', 'quote', True, False),
    ('replay', 'COMPLETED', 'bar', False, False),
    (None, None, 'bar', False, False),
    (None, None, 'quote', True, False),
])
def test_replay_speed_controls_current_run_or_next_preset(window, mode, status, next_kind, enabled, send):
    window._select_demo(next_kind)
    window.go_backtest()
    window.backtest_controls_toggle.setChecked(True)
    if mode:
        window.active_id = 'current'
        window.states['current'] = {'mode': mode, 'status': status, 'speed': 5}
    window.refresh_execution_controls()
    assert window.speed_combo.isEnabled() is enabled
    assert window.speed_combo.accessibleName() == '快照回放速度'
    assert any(label.text() == '快照回放速度' and label.isVisible()
               for label in window.run_toolbar.findChildren(QtWidgets.QLabel))
    while not window.engine_commands.empty():
        window.engine_commands.get_nowait()
    window.speed_combo.setCurrentIndex(window.speed_combo.findData(100))
    if send:
        assert window.engine_commands.get_nowait() == {'op': 'speed', 'id': 'current', 'value': 100}
    assert window.engine_commands.empty()
    if not enabled and mode == 'backtest':
        assert 'K 线回测' in window.speed_combo.toolTip()
        window.send_run('speed', value=20)
        assert window.engine_commands.empty()


def test_new_teaching_selection_uses_v2_and_explicit_name(window):
    window._select_demo('bar')
    meta = next(m for m in window.datasets if m['id'] == window.dataset_combo.currentData())
    assert meta['source'] == DEMO_BAR_SOURCE
    assert '合成教学数据' in window.dataset_combo.currentText()
    assert '合成教学数据' in window.preview_chart.heading.text()
    assert 'astock-synthetic-v2' in window.dataset_combo.currentData(QtCore.Qt.ItemDataRole.ToolTipRole)


def test_chart_identity_is_from_its_run_not_from_next_dataset(qtbot):
    chart = PriceChart()
    qtbot.addWidget(chart)
    chart.set_data([], symbol='600036.SH', meta={'demo': False, 'source': 'akshare-tencent'})
    assert '真实历史数据' in chart.heading.text()
    chart.set_data([], symbol='510300.SH', meta={'demo': True, 'source': DEMO_BAR_SOURCE})
    assert '合成教学数据' in chart.heading.text()
