"""Small trusted-code experiments, isolated from trading processes and accounts."""
import contextlib
import io
import multiprocessing as mp
from pathlib import Path
import time
import traceback
import uuid

from PySide6 import QtCore


class BoundedOutput(io.TextIOBase):
    def __init__(self):
        self.parts = []
        self.remaining = 256 * 1024
        self.truncated = False

    def write(self, value):
        encoded = str(value).encode('utf-8')
        if len(encoded) > self.remaining:
            self.truncated = True
        if self.remaining:
            self.parts.append(encoded[:self.remaining].decode('utf-8', errors='ignore'))
        self.remaining = max(0, self.remaining - len(encoded))
        return len(value)

    def text(self):
        return ''.join(self.parts) + ('\n[输出超过 256 KiB，已截断]' if self.truncated else '')


def lab_worker(pipe, code, directory):
    import os
    os.chdir(directory)
    output = BoundedOutput()
    from astock.course_display import LabDisplay
    display = LabDisplay()
    try:
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            namespace = {'__name__': '__main__', '__file__': str(Path(directory) / 'exercise.py'), 'lab': display}
            exec(compile(code, 'exercise.py', 'exec'), namespace)
        result = {'status': 'finished', 'output': output.text(), 'displays': display.items}
    except BaseException:
        result = {'status': 'error', 'output': output.text(), 'error': traceback.format_exc()}
    try:
        pipe.send(result)
    finally:
        pipe.close()


class CourseLab(QtCore.QObject):
    result = QtCore.Signal(object)

    def __init__(self, root, parent=None, timeout=30):
        super().__init__(parent)
        self.root, self.timeout = Path(root), timeout
        self.job = None
        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(40)
        self.timer.timeout.connect(self.poll)

    def start(self, exercise_id, code):
        self.cancel()
        token = uuid.uuid4().hex
        directory = self.root / token
        directory.mkdir(parents=True)
        (directory / 'exercise.py').write_text(code, encoding='utf-8')
        context = mp.get_context('spawn')
        reader, writer = context.Pipe(duplex=False)
        process = context.Process(target=lab_worker, args=(writer, code, str(directory)), daemon=True)
        try:
            process.start()
        except BaseException:
            reader.close()
            writer.close()
            raise
        writer.close()
        self.job = dict(token=token, exercise_id=exercise_id, reader=reader,
                        process=process, started=time.monotonic())
        self.timer.start()
        return token

    def finish(self, value):
        job, self.job = self.job, None
        self.timer.stop()
        if job:
            process = job['process']
            process.join(.1)
            if process.is_alive():
                process.terminate()
                process.join(1)
            job['reader'].close()
            self.result.emit({**value, 'token': job['token'], 'exercise_id': job['exercise_id']})

    def poll(self):
        if not self.job:
            return
        job = self.job
        if job['reader'].poll():
            try:
                self.finish(job['reader'].recv())
            except (EOFError, OSError):
                self.finish({'status': 'error', 'error': '练习进程提前退出。'})
        elif time.monotonic() - job['started'] > self.timeout:
            self.finish({'status': 'timeout', 'error': f'超过 {self.timeout} 秒，练习已停止。'})
        elif not job['process'].is_alive():
            self.finish({'status': 'error', 'error': '练习进程意外退出。'})

    def cancel(self, token=None):
        if self.job and (token is None or self.job['token'] == token):
            self.finish({'status': 'cancelled', 'output': '练习已取消。'})

    def close(self):
        self.cancel()
