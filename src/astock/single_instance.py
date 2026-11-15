"""Per-user launch arbitration and local activation before any data/worker startup.

QLockFile owns arbitration; QLocalServer only asks the existing window to activate.
Locks live outside the app data directory and survive in-process initialization.
"""
import hashlib
import os
from pathlib import Path
import sys

from PySide6 import QtCore, QtNetwork
from shiboken6 import isValid


def activate_legacy_window():
    """Recognize older portable AStock builds which predate the instance lock."""
    if sys.platform != 'win32':
        return False
    import ctypes
    from ctypes import wintypes
    user = ctypes.WinDLL('user32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    user.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user.IsIconic.argtypes = [wintypes.HWND]
    user.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user.SetForegroundWindow.argtypes = [wintypes.HWND]
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                                ctypes.POINTER(wintypes.DWORD)]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    found = []

    @callback_type
    def inspect(hwnd, _):
        title, kind = ctypes.create_unicode_buffer(512), ctypes.create_unicode_buffer(128)
        user.GetWindowTextW(hwnd, title, len(title))
        if title.value != 'AStock · 量化研究与仿真工作台':
            return True
        user.GetClassNameW(hwnd, kind, len(kind))
        if not kind.value.startswith('Qt') or 'QWindow' not in kind.value:
            return True
        pid = wintypes.DWORD()
        user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == os.getpid():
            return True
        handle = kernel.OpenProcess(0x1000, False, pid.value)
        if not handle:
            return True
        try:
            executable = ctypes.create_unicode_buffer(32768)
            size = wintypes.DWORD(len(executable))
            if (kernel.QueryFullProcessImageNameW(handle, 0, executable, ctypes.byref(size))
                    and Path(executable.value).name.casefold() == 'astock.exe'):
                found.append(hwnd)
        finally:
            kernel.CloseHandle(handle)
        return not found

    user.EnumWindows(inspect, 0)
    if not found:
        return False
    hwnd = found[0]
    user.ShowWindow(hwnd, 9 if user.IsIconic(hwnd) else 5)
    user.SetForegroundWindow(hwnd)
    return True


class InstanceGuard(QtCore.QObject):
    activated = QtCore.Signal()

    def __init__(self, root, *, global_scope=True, lock_directory=None):
        super().__init__()
        user = os.path.normcase(str(Path.home().resolve()))
        scope = os.path.normcase(str(Path(root).resolve()))
        scopes = (['user:' + user] if global_scope else []) + ['data:' + user + ':' + scope]
        if lock_directory is not None:
            # Isolated test namespaces must not remove/replace a real user's
            # activation endpoint even when they test a user-wide lock.
            prefix = os.path.normcase(str(Path(lock_directory).resolve())) + ':'
            scopes = [prefix + s for s in scopes]
        self.names = ['astock-' + hashlib.sha256(s.encode()).hexdigest()[:32] for s in scopes]
        self.directory = Path(lock_directory) if lock_directory else Path(QtCore.QDir.tempPath()) / 'AStock-instance'
        self.locks = []
        self.servers = []
        self.window = None
        self.pending_activation = False
        self.accepting = False
        self.check_legacy = global_scope and lock_directory is None

    def acquire(self):
        if self.check_legacy and activate_legacy_window():
            return False
        self.directory.mkdir(parents=True, exist_ok=True)
        for name in self.names:
            lock = QtCore.QLockFile(str(self.directory / (name + '.lock')))
            lock.setStaleLockTime(0)
            if not lock.tryLock(0):
                error = lock.error()
                self.close()
                if error != QtCore.QLockFile.LockError.LockFailedError:
                    raise RuntimeError('无法取得启动锁，请检查临时目录权限。')
                socket = QtNetwork.QLocalSocket()
                socket.connectToServer(name)
                socket.waitForConnected(1500)
                socket.disconnectFromServer()
                return False
            self.locks.append(lock)
        try:
            for name in self.names:
                # Safe only after owning ALL arbitration locks; never remove an
                # active server just because a connection attempt timed out.
                QtNetwork.QLocalServer.removeServer(name)
                server = QtNetwork.QLocalServer(self)
                server.setSocketOptions(QtNetwork.QLocalServer.SocketOption.UserAccessOption)
                server.newConnection.connect(self._accept_connection)
                if not server.listen(name):
                    raise RuntimeError('无法建立应用唤醒通道：' + server.errorString())
                self.servers.append(server)
            self.accepting = True
        except Exception:
            self.close()
            raise
        return True

    @QtCore.Slot()
    def _accept_connection(self):
        server = self.sender()
        if (not self.accepting or server is None or not isValid(server)
                or not any(server is current for current in self.servers)):
            return
        while server.hasPendingConnections():
            socket = server.nextPendingConnection()
            socket.disconnectFromServer()
            socket.deleteLater()
        self.pending_activation = True
        self.activated.emit()
        self.activate_window()

    def set_window(self, window):
        self.window = window
        if self.pending_activation:
            self.activate_window()

    def activate_window(self):
        window = self.window
        if window is None or not isValid(window) or getattr(window, 'closing', False):
            return
        self.pending_activation = False
        if window.isMinimized():
            window.showNormal()
        window.show()
        window.raise_()
        window.activateWindow()
        window.statusBar().showMessage('应用已在运行，已返回现有窗口。', 5000)

    def close(self):
        self.accepting = False
        self.pending_activation = False
        self.window = None
        for server in self.servers:
            server.newConnection.disconnect(self._accept_connection)
            server.blockSignals(True)
            server.close()
            server.deleteLater()
        self.servers.clear()
        for lock in reversed(self.locks):
            lock.unlock()
        self.locks.clear()
