"""Closing windows releases IPC resources even without execution workers."""
from queue import Queue
import threading

import pytest
from PySide6 import QtCore
from shiboken6 import isValid

from astock.data_jobs import DataJobs
from astock.window import MainWindow


def test_close_without_workers_does_not_create_queue_feeders(qtbot, tmp_path, monkeypatch):
    monkeypatch.setattr(DataJobs, 'start', lambda *a, **k: 'lifecycle-preview')
    window = MainWindow(tmp_path, start_workers=False)
    qtbot.addWidget(window)
    before = set(threading.enumerate())
    window.close()
    assert not [thread for thread in set(threading.enumerate()) - before
                if thread.name == 'QueueFeederThread']
    for channel in window._ipc_queues:
        with pytest.raises(ValueError, match='closed'):
            channel.put({'op': 'unused'})


def test_close_releases_existing_feeders_and_original_replaced_queues(qtbot, tmp_path, monkeypatch):
    monkeypatch.setattr(DataJobs, 'start', lambda *a, **k: 'lifecycle-preview')
    window = MainWindow(tmp_path, start_workers=False)
    qtbot.addWidget(window)
    before = set(threading.enumerate())
    for channel in window._ipc_queues:
        channel.put({'test': 'pending'})
    feeders = {thread for thread in set(threading.enumerate()) - before
               if thread.name == 'QueueFeederThread'}
    assert len(feeders) == 3
    window.engine_commands = Queue()
    window.output = Queue()
    window.close()
    qtbot.waitUntil(lambda: not any(thread.is_alive() for thread in feeders), timeout=2000)
    for channel in window._ipc_queues:
        with pytest.raises(ValueError, match='closed'):
            channel.put({'test': 'after close'})
    window.close()  # Repeated Qt teardown must remain harmless.


def test_hidden_compatibility_controls_are_destroyed_with_the_window(qtbot, tmp_path, monkeypatch):
    monkeypatch.setattr(DataJobs, 'start', lambda *a, **k: 'lifecycle-preview')
    window = MainWindow(tmp_path, start_workers=False)
    controls = (window.mode_combo, window.start_button, window.analysis_expand)
    try:
        assert all(window.isAncestorOf(control) for control in controls)
        assert all(not control.isWindow() for control in controls)
    finally:
        # This test owns destruction; qtbot must not later close an invalid wrapper.
        window.close()
        window.deleteLater()
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
    assert not isValid(window)
    assert all(not isValid(control) for control in controls)
