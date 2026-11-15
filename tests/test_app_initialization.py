"""Exercise the actual app shutdown/reset/reopen loop against disposable data."""
import os
import subprocess
import sys
import pytest


@pytest.mark.parametrize('reset_delay', [30, 700])
def test_application_reopens_and_preserves_learning_after_initialization(tmp_path, reset_delay):
    driver = r'''
import sys
from pathlib import Path
from PySide6 import QtCore, QtWidgets
from astock import app, app_reset
from astock.window import MainWindow

root = Path(sys.argv[1])
reset_delay = int(sys.argv[2])
sys.argv = ['astock', '--data-dir', str(root), '--isolated-instance']
original = QtWidgets.QApplication.exec
cycles = []
errors = []
app_reset.confirm_initialization = lambda window: True

def execute():
    cycles.append(1)
    def exercise():
        try:
            window = next(w for w in QtWidgets.QApplication.topLevelWidgets()
                          if isinstance(w, MainWindow) and w.isVisible())
            if len(cycles) == 1:
                window.store.set_setting('learning_library_v1', {'q19': {'bookmark': True}})
                # Mirror the live reader state to ensure normal shutdown may persist it.
                window.course_library.state['q19'] = {'bookmark': True}
                window.store.save_strategy('reset-me', 'test', {})
                (root / 'delete-me.txt').write_text('test')
                window.request_initialization()
            else:
                assert len(cycles) == 2
                assert not (root / 'delete-me.txt').exists()
                assert not any(s['name'] == 'reset-me' for s in window.store.strategies())
                assert window.store.setting('learning_library_v1')['q19']['bookmark']
                assert window.store.setting('onboarding_v1', {}).get('status') != 'skipped'
                assert window.editor.isVisible()
                window.close()
        except Exception as error:
            errors.append(repr(error))
            QtWidgets.QApplication.exit(3)
    QtCore.QTimer.singleShot(reset_delay if len(cycles) == 1 else 700, exercise)
    return original()

QtWidgets.QApplication.exec = staticmethod(execute)
try:
    app.main()
except SystemExit as result:
    assert result.code == 0, (result.code, errors)
assert len(cycles) == 2, cycles
assert not errors, errors
print('INITIALIZATION_LIFECYCLE_PASSED')
'''
    result = subprocess.run([sys.executable, '-X', 'utf8', '-c', driver, str(tmp_path), str(reset_delay)],
                            capture_output=True, encoding='utf-8', timeout=90,
                            env={**os.environ, 'PYTHONUTF8': '1', 'QT_QPA_PLATFORM': 'offscreen'})
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'INITIALIZATION_LIFECYCLE_PASSED' in result.stdout
