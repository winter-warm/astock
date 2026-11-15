"""Task-oriented instructions locate controls without clicking or navigating for the user."""
import json
from pathlib import Path
from PySide6 import QtCore, QtWidgets
from astock.help_registry import help_target


def paths():
    return json.loads((Path(__file__).with_name('course_content') / 'operation_paths.json').read_text(encoding='utf-8'))


class TaskGuide(QtWidgets.QDialog):
    def __init__(self, window):
        super().__init__(window)
        self.setWindowTitle('按任务逐步操作')
        self.resize(580, 380)
        self.index = 0
        self.band = None
        self.tasks = paths()
        layout = QtWidgets.QVBoxLayout(self)
        self.selector = help_target(QtWidgets.QComboBox(), 'task_guide.TaskGuide.__init__.selector')
        for task in self.tasks:
            self.selector.addItem(task['title'])
        layout.addWidget(self.selector)
        self.text = help_target(QtWidgets.QTextBrowser(), 'task_guide.TaskGuide.__init__.text')
        layout.addWidget(self.text)
        row = QtWidgets.QHBoxLayout()
        self.previous = help_target(QtWidgets.QPushButton('上一步'), 'task_guide.TaskGuide.__init__.previous')
        self.next = help_target(QtWidgets.QPushButton('下一步（只翻页）'), 'task_guide.TaskGuide.__init__.next')
        self.exit_button = help_target(QtWidgets.QPushButton('结束引导'), 'task_guide.TaskGuide.__init__.exit_button')
        for button in (self.previous, self.next, self.exit_button):
            row.addWidget(button)
        layout.addLayout(row)
        self.selector.currentIndexChanged.connect(self.reset)
        self.previous.clicked.connect(lambda: self.advance(-1))
        self.next.clicked.connect(lambda: self.advance(1))
        self.exit_button.clicked.connect(self.close)
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.locate)
        self.timer.start(250)
        self.finished.connect(self.cleanup)
        self.render()

    def reset(self):
        self.index = 0
        self.render()

    def advance(self, change):
        self.index = max(0, min(self.index + change, len(self.tasks[self.selector.currentIndex()]['steps']) - 1))
        self.render()

    def render(self):
        steps = self.tasks[self.selector.currentIndex()]['steps']
        step = steps[self.index]
        self.text.setPlainText(f"{self.index + 1} / {len(steps)} · {step['title']}\n\n位置：{step['route']}\n\n{step['instruction']}\n\n核对：{step['expect']}\n\n请在原界面自行操作；本窗口只翻页与高亮，不执行动作。目标未出现时按位置提示打开；弹窗内可按 F1 或 Ctrl+F1 查看帮助，关闭弹窗后继续本任务。")
        self.previous.setEnabled(self.index > 0)
        self.next.setEnabled(self.index + 1 < len(steps))
        self.locate()

    def locate(self):
        self.clear_band()
        identity = self.tasks[self.selector.currentIndex()]['steps'][self.index]['target']
        candidates = [w for w in QtWidgets.QApplication.allWidgets() if w.property('helpId') == identity and w.isVisible()]
        if candidates:
            target = candidates[0]
            self.band = QtWidgets.QRubberBand(QtWidgets.QRubberBand.Shape.Rectangle, target.window())
            self.band.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            self.band.setGeometry(QtCore.QRect(target.mapTo(target.window(), QtCore.QPoint()), target.size()))
            self.band.show()

    def clear_band(self):
        if self.band:
            try:
                self.band.hide()
                self.band.deleteLater()
            except RuntimeError:
                pass
            self.band = None

    def cleanup(self, *_):
        self.timer.stop()
        self.clear_band()

    def closeEvent(self, event):
        self.cleanup()
        event.accept()
