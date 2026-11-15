from types import SimpleNamespace

from PySide6 import QtCore
from shiboken6 import delete, isValid

from astock.course_ui import CourseLibrary
from astock.storage import Store


def test_learning_navigation_contains_only_72_courses_and_restores_progress(qtbot, tmp_path):
    store = Store(tmp_path)
    store.set_setting('learning_library_v1', {
        '_last': 'interface-atlas',
        'q19': {'bookmark': True, 'drafts': {'q19-lab': 'print(42)'}},
    })
    reader = CourseLibrary(SimpleNamespace(root=tmp_path, store=store))
    qtbot.addWidget(reader)
    entries = [item.data(0, QtCore.Qt.ItemDataRole.UserRole) for item in reader.items]
    assert len(entries) == 72
    assert all(entry['kind'] == 'course' for entry in entries)
    assert [entry['id'] for entry in entries] == [f'q{i:02}' for i in range(1, 73)]
    assert reader.current['id'] == 'q01'
    assert reader.state['q19']['bookmark']
    reader.shutdown()
    store.close()


def test_pending_reading_position_is_canceled_when_reader_is_destroyed(qtbot, tmp_path):
    store = Store(tmp_path)
    reader = CourseLibrary(SimpleNamespace(root=tmp_path, store=store))
    body = reader.body
    # Selection queues restoration until text layout has run. Destroy immediately,
    # before entering an event loop, as initialization or closing a window can do.
    reader.tree.setCurrentItem(reader.items[18])
    reader.shutdown()
    delete(reader)
    assert not isValid(body)
    qtbot.wait(1)
    store.close()
