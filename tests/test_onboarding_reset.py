import sqlite3

import pytest
from PySide6 import QtCore, QtWidgets

from astock.app_reset import LEARNING_KEYS, confirm_initialization, initialize_closed_data
from astock.onboarding import STATE_KEY, STEPS, open_onboarding
from astock.storage import Store


def populated_root(root):
    store = Store(root)
    for key in LEARNING_KEYS:
        store.set_setting(key, {'read': 'q07', 'draft': '我的练习', 'bookmark': True})
    store.set_setting(STATE_KEY, {'status': 'completed'})
    store.set_setting('theme', 'light')
    store.save_strategy('自己的策略', 'print(1)', {})
    store.save_run('old', '旧账户', 'backtest', 'STOPPED', {}, {}, {}, [('action', {'x': 1})])
    (root / 'datasets' / 'prices.txt').write_text('行情', encoding='utf-8')
    (root / 'reports' / 'report.txt').write_text('运行报告', encoding='utf-8')
    study = root / 'learning' / 'notebooks'
    study.mkdir(parents=True)
    (study / 'q07.ipynb').write_text('自己的笔记', encoding='utf-8')
    store.close()


def test_full_initialization_keeps_learning_without_backups(tmp_path):
    root = tmp_path / 'data'
    populated_root(root)
    result = initialize_closed_data(root)
    assert result['backup_created'] is False
    assert list(tmp_path.iterdir()) == [root]
    assert {p.name for p in root.iterdir()} == {'workbench.sqlite3', 'learning'}
    assert (root / 'learning/notebooks/q07.ipynb').read_text(encoding='utf-8') == '自己的笔记'
    fresh = Store(root)
    for key in LEARNING_KEYS:
        assert fresh.setting(key) == {'read': 'q07', 'draft': '我的练习', 'bookmark': True}
    assert fresh.setting('theme') is None
    assert fresh.setting(STATE_KEY) is None
    assert fresh.strategies() == [] and fresh.runs() == []
    assert fresh.db.execute('SELECT count(*) FROM journals').fetchone()[0] == 0
    fresh.close()


def test_reset_refuses_live_writer_before_deleting_files(tmp_path):
    root = tmp_path / 'data'
    populated_root(root)
    writer = sqlite3.connect(root / 'workbench.sqlite3')
    try:
        writer.execute('BEGIN IMMEDIATE')
        with pytest.raises(sqlite3.OperationalError):
            initialize_closed_data(root)
        assert (root / 'datasets/prices.txt').is_file()
    finally:
        writer.close()


@pytest.mark.parametrize('marker', ['pyproject.toml', 'portable.flag', 'AStock.exe'])
def test_reset_refuses_program_source_directories(tmp_path, marker):
    root = tmp_path / 'data'
    populated_root(root)
    (root / marker).write_text('keep', encoding='utf-8')
    with pytest.raises(ValueError, match='程序或源码'):
        initialize_closed_data(root)
    assert (root / 'datasets/prices.txt').is_file()


def test_reset_refuses_non_astock_database(tmp_path):
    root = tmp_path / 'data'
    root.mkdir()
    connection = sqlite3.connect(root / 'workbench.sqlite3')
    connection.execute('CREATE TABLE unrelated(x)')
    connection.close()
    (root / 'keep.txt').write_text('keep', encoding='utf-8')
    with pytest.raises(ValueError, match='不属于 AStock'):
        initialize_closed_data(root)
    assert (root / 'keep.txt').read_text(encoding='utf-8') == 'keep'


def test_reset_failure_reports_partial_deletion_and_preserves_progress(tmp_path, monkeypatch):
    root = tmp_path / 'data'
    populated_root(root)

    def refuse(path, directory):
        raise PermissionError('文件仍被占用')

    monkeypatch.setattr('astock.app_reset._remove_inside', refuse)
    with pytest.raises(RuntimeError, match='部分非学习文件可能已删除'):
        initialize_closed_data(root)
    store = Store(root)
    assert store.setting(LEARNING_KEYS[0])['draft'] == '我的练习'
    assert len(store.strategies()) == 1
    store.close()


class TourWindow(QtWidgets.QMainWindow):
    """A real widget surface with only navigation; no business action methods."""
    def __init__(self, root):
        super().__init__()
        self.root = root
        self.store = Store(root)
        self.closing = False
        self.navigation = []
        body = QtWidgets.QWidget()
        self.setCentralWidget(body)
        layout = QtWidgets.QVBoxLayout(body)
        self.nav_group = QtWidgets.QButtonGroup(self)
        for index in range(6):
            button = QtWidgets.QPushButton(str(index))
            self.nav_group.addButton(button, index)
            layout.addWidget(button)
        for name in ('new_strategy_button', 'template_button', 'save_strategy_button', 'start_button'):
            button = QtWidgets.QPushButton(name)
            setattr(self, name, button)
            layout.addWidget(button)
        self.editor = QtWidgets.QPlainTextEdit('未保存的策略')
        layout.addWidget(self.editor)
        self.editor_settings = QtWidgets.QTabWidget()
        self.editor_settings.addTab(QtWidgets.QWidget(), '参数')
        layout.addWidget(self.editor_settings)
        self.resize(950, 650)

    def switch_workspace(self, index):
        self.navigation.append(index)


@pytest.fixture
def tour_window(qtbot, tmp_path):
    window = TourWindow(tmp_path / 'data')
    qtbot.addWidget(window)
    window.show()
    yield window
    window.closing = True
    if hasattr(window, 'onboarding_dialog'):
        window.onboarding_dialog.close()
    window.store.close()


def test_first_launch_skip_replay_and_completion_keep_draft(tour_window):
    window = tour_window
    tour = open_onboarding(window, first_run=True)
    assert tour.isVisible() and tour.index == 0
    tour.close()
    assert window.store.setting(STATE_KEY)['status'] == 'skipped'
    assert open_onboarding(window, first_run=True) is None
    tour = open_onboarding(window)
    for index in range(len(STEPS)):
        assert tour.index == index
        assert window.editor.toPlainText() == '未保存的策略'
        assert window.store.strategies() == []
        tour.advance(1)
    assert window.store.setting(STATE_KEY)['status'] == 'completed'
    assert window.navigation[-1] == 0
    assert not tour.timer.isActive()
    assert tour.band is None
    assert open_onboarding(window, first_run=True) is None


def test_reset_confirmation_defaults_to_cancel_and_makes_no_changes(tour_window):
    window = tour_window
    seen = []

    def dismiss():
        dialog = QtWidgets.QApplication.activeModalWidget()
        assert isinstance(dialog, QtWidgets.QMessageBox)
        assert dialog.defaultButton().text() == '取消'
        assert '不创建备份' in dialog.informativeText()
        assert '保留' in dialog.informativeText()
        seen.append(dialog.windowTitle())
        dialog.reject()

    QtCore.QTimer.singleShot(10, dismiss)
    assert not confirm_initialization(window)
    assert seen == ['初始化应用']
    assert window.store.db.execute('SELECT count(*) FROM settings').fetchone()[0] == 0


def test_escape_dismissal_is_remembered(tour_window, qtbot):
    tour = open_onboarding(tour_window, first_run=True)
    qtbot.keyClick(tour, QtCore.Qt.Key.Key_Escape)
    assert not tour.isVisible()
    assert not tour.timer.isActive()
    assert tour_window.store.setting(STATE_KEY)['status'] == 'skipped'
    assert open_onboarding(tour_window, first_run=True) is None


def test_real_window_reset_shutdown_and_fresh_window_preserve_course_state(qtbot, tmp_path, monkeypatch):
    from astock.data_jobs import DataJobs
    from astock.window import MainWindow

    # The contract under test is window persistence/shutdown, not dataset workers.
    monkeypatch.setattr(DataJobs, 'start', lambda *args, **kwargs: 'isolated-preview')
    root = tmp_path / 'data'
    w = MainWindow(root, start_workers=False)
    qtbot.addWidget(w)
    w.show()
    w.course_library.state['q07'] = {'position': 32, 'bookmark': True, 'drafts': {'q07': '练习'}}
    w.course_library.persist()
    w.store.save_strategy('待清除', 'old', {})
    w.store.set_setting(STATE_KEY, {'status': 'completed'})
    monkeypatch.setattr('astock.app_reset.confirm_initialization', lambda window: True)
    w.request_initialization()
    assert w.reset_requested and w.closing
    assert not w.isVisible()
    with pytest.raises(sqlite3.ProgrammingError):
        w.store.db.execute('SELECT 1')

    initialize_closed_data(root)
    fresh = MainWindow(root, start_workers=False)
    qtbot.addWidget(fresh)
    fresh.show()
    assert fresh.course_library.state['q07'] == {'position': 32, 'bookmark': True, 'drafts': {'q07': '练习'}}
    assert fresh.store.strategies() == []
    assert fresh.store.runs() == []
    tour = open_onboarding(fresh, first_run=True)
    assert tour is not None
    tour.close()
    fresh.close()
