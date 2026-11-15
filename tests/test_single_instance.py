import os
import subprocess
import sys

from astock.single_instance import InstanceGuard


def test_default_launches_share_user_lock_and_data_lock(qtbot, tmp_path):
    first = InstanceGuard(tmp_path / 'one', lock_directory=tmp_path / 'locks')
    second = InstanceGuard(tmp_path / 'two', lock_directory=tmp_path / 'locks')
    explicit_same = InstanceGuard(tmp_path / 'one', global_scope=False, lock_directory=tmp_path / 'locks')
    explicit_other = InstanceGuard(tmp_path / 'three', global_scope=False, lock_directory=tmp_path / 'locks')
    try:
        assert first.acquire()
        assert not second.acquire()
        assert not explicit_same.acquire()
        assert explicit_other.acquire()
        first.close()
        assert second.acquire()
    finally:
        for guard in (first, second, explicit_same, explicit_other):
            guard.close()


HOLDER = r'''
import sys
from pathlib import Path
from PySide6 import QtCore, QtWidgets
from astock.single_instance import InstanceGuard
app = QtWidgets.QApplication([])
guard = InstanceGuard(Path(sys.argv[1]), global_scope=False)
guard.activated.connect(lambda: Path(sys.argv[2]).write_text('activated'))
assert guard.acquire()
print('READY', flush=True)
QtCore.QTimer.singleShot(30000, app.quit)
app.exec()
guard.close()
'''


def test_second_process_activates_existing_and_never_constructs_window(qtbot, tmp_path):
    root = tmp_path / 'data-not-created'
    activation = tmp_path / 'activation.txt'
    env = {**os.environ, 'QT_QPA_PLATFORM': 'offscreen', 'PYTHONUTF8': '1'}
    process = subprocess.Popen([sys.executable, '-X', 'utf8', '-c', HOLDER, str(root), str(activation)],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
    try:
        assert process.stdout.readline().strip() == 'READY'
        duplicate = r'''
import sys
from astock import app, window
def forbidden(*args, **kwargs):
    raise AssertionError('duplicate reached window/data/worker construction')
window.MainWindow = forbidden
sys.argv = ['astock', '--data-dir', sys.argv[1], '--isolated-instance']
app.main()
'''
        result = subprocess.run([sys.executable, '-X', 'utf8', '-c', duplicate, str(root)],
                                capture_output=True, text=True, env=env, timeout=15)
        assert result.returncode == 0, result.stderr
        qtbot.waitUntil(activation.exists, timeout=5000)
        assert not root.exists()
        process.kill()
        process.wait(timeout=5)
        # A crash must not permanently prevent restart, even with a lock file
        # and a stale local-server endpoint left by the terminated process.
        replacement = InstanceGuard(root, global_scope=False)
        try:
            assert replacement.acquire()
        finally:
            replacement.close()
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        process.stdout.close()
        process.stderr.close()


def test_activation_during_reset_waits_for_new_window(qtbot, tmp_path):
    from PySide6 import QtWidgets
    guard = InstanceGuard(tmp_path, global_scope=False)
    old = QtWidgets.QMainWindow()
    new = QtWidgets.QMainWindow()
    qtbot.addWidget(old)
    qtbot.addWidget(new)
    old.closing = True
    guard.set_window(old)
    guard.pending_activation = True
    guard.activate_window()
    assert guard.pending_activation and not old.isVisible()
    guard.set_window(new)
    assert new.isVisible() and not guard.pending_activation


def test_running_legacy_portable_is_activated_before_creating_locks(qtbot, tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr('astock.single_instance.activate_legacy_window', lambda: calls.append(True) or True)
    guard = InstanceGuard(tmp_path / 'unused')
    guard.directory = tmp_path / 'locks-not-created'
    assert not guard.acquire()
    assert calls == [True]
    assert not guard.directory.exists()
    assert not guard.locks and not guard.servers


def test_launcher_data_argument_still_checks_user_wide_instance(tmp_path):
    driver = r'''
import sys
from astock import app, single_instance
class Guard:
    def __init__(self, root, *, global_scope):
        assert global_scope, 'normal shortcuts with --data-dir must use the user lock'
    def acquire(self):
        print('NORMAL_LAUNCH_CHECKED')
        return False
single_instance.InstanceGuard = Guard
sys.argv = ['astock', '--data-dir', sys.argv[1]]
app.main()
'''
    result = subprocess.run([sys.executable, '-X', 'utf8', '-c', driver, str(tmp_path / 'unused')],
                            capture_output=True, text=True, timeout=15,
                            env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen', 'PYTHONUTF8': '1'})
    assert result.returncode == 0, result.stderr
    assert 'NORMAL_LAUNCH_CHECKED' in result.stdout
    assert not (tmp_path / 'unused').exists()
