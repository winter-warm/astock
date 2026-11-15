from types import SimpleNamespace
import subprocess
import sys

from astock.course_library import catalogue, resource, validate, article
from astock.course_lab import CourseLab, BoundedOutput
from astock.course_ui import CourseLibrary
from astock.storage import Store
from astock.control_help import ControlTour
from PySide6 import QtCore, QtWidgets


def test_published_resources_and_in_app_examples_execute(tmp_path):
    assert validate() == []
    for entry in catalogue():
        if entry.get('status') != 'published':
            continue
        assert '{{code:' not in article(entry)
        for example in entry.get('examples', []):
            if example.get('environment') == 'notebook':
                continue  # Mandatory external-kernel verification is check_course_notebooks.py --release.
            result = subprocess.run([sys.executable, '-X', 'utf8', str(resource(example['file']))], cwd=tmp_path,
                                    capture_output=True, timeout=30, encoding='utf-8', errors='replace')
            assert result.returncode == 0, result.stderr


def test_incomplete_catalogue_cannot_pass_release():
    drafts = [e for e in catalogue() if e.get('status') != 'published']
    if drafts:
        assert any('未完成正文' in error for error in validate(require_complete=True))


def test_bounded_output_does_not_accumulate_after_truncation():
    output = BoundedOutput()
    output.write('中' * 100000)
    count = len(output.parts)
    for _ in range(10000):
        output.write('more')
    assert len(output.parts) == count
    assert '已截断' in output.text()


def test_worker_success_error_timeout_cancel_and_utf8(qtbot, tmp_path):
    runner = CourseLab(tmp_path, timeout=10)
    with qtbot.waitSignal(runner.result, timeout=20000) as result:
        runner.start('example', "print('中文输出')")
    assert result.args[0]['status'] == 'finished'
    assert '中文输出' in result.args[0]['output']
    with qtbot.waitSignal(runner.result, timeout=20000) as result:
        runner.start('example', "raise ValueError('教学错误')")
    assert result.args[0]['status'] == 'error'
    assert 'exercise.py' in result.args[0]['error']
    runner.timeout = .1
    with qtbot.waitSignal(runner.result, timeout=5000) as result:
        runner.start('loop', 'while True: pass')
    assert result.args[0]['status'] == 'timeout'
    runner.timeout = 10
    with qtbot.waitSignal(runner.result, timeout=5000) as result:
        token = runner.start('loop', 'while True: pass')
        runner.cancel(token)
    assert result.args[0]['status'] == 'cancelled'
    assert runner.job is None
    runner.close()


def test_reader_retains_drafts_and_does_not_complete_drafts(qtbot, tmp_path):
    store = Store(tmp_path)
    store.set_setting('lessons_completed', [0, 2])
    window = SimpleNamespace(root=tmp_path, store=store)
    reader = CourseLibrary(window)
    qtbot.addWidget(reader)
    reader.show()
    first = next(i for i in reader.items if i.data(0, 256)['id'] == 'q01')
    reader.tree.setCurrentItem(first)
    reader.code.setPlainText("print('我的草稿')")
    reader.mark_read()
    reader.tree.setCurrentItem(reader.items[-1])
    reader.tree.setCurrentItem(first)
    assert reader.code.toPlainText() == "print('我的草稿')"
    assert store.setting('lessons_completed') == [0, 2]
    draft = next((i for i in reader.items if i.data(0, 256).get('status') != 'published'), None)
    if draft:
        reader.tree.setCurrentItem(draft)
        reader.mark_read()
        assert 'read_digest' not in reader.state.get(reader.current['id'], {})
    reader.shutdown()
    reader.close()
    store.close()


def test_explanation_never_activates_control_and_escape_cleans_overlay(qtbot):
    window = QtWidgets.QWidget()
    layout = QtWidgets.QVBoxLayout(window)
    window.start_button = QtWidgets.QPushButton('开始运行')
    layout.addWidget(window.start_button)
    activated = []
    window.start_button.clicked.connect(lambda: activated.append(True))
    qtbot.addWidget(window)
    window.show()
    tour = ControlTour(window)
    tour.show()
    qtbot.waitUntil(tour.isVisible)
    assert tour.band is not None
    band = tour.band
    tour.advance(1)
    assert activated == []
    qtbot.keyClick(tour, QtCore.Qt.Key.Key_Escape)
    assert not tour.isVisible()
    try:
        assert not band.isVisible()
    except RuntimeError:
        pass  # Deferred deletion may already have completed.
    assert activated == []
