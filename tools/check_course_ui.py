"""Capture the real native reader without opening trading processes."""
import os
import argparse
from pathlib import Path
from types import SimpleNamespace
from PySide6 import QtCore, QtGui, QtWidgets
from astock.course_ui import CourseLibrary
from astock.storage import Store


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--entry', default='q19')
    parser.add_argument('--output', default='output/course-ui')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1] / args.output
    root.mkdir(parents=True, exist_ok=True)
    app = QtWidgets.QApplication([])
    store = Store(root / 'data')
    page = CourseLibrary(SimpleNamespace(root=root / 'data', store=store),
                         include_manuals=not args.entry.startswith('q'))
    page.setWindowTitle('课程阅读器验证')
    page.resize(1100, 680)
    page.show()
    page.tree.setCurrentItem(next(i for i in page.items if i.data(0, QtCore.Qt.ItemDataRole.UserRole)['id'] == args.entry))

    def capture():
        if args.entry == 'interface-atlas':
            picture = page.body.document().resource(QtGui.QTextDocument.ResourceType.ImageResource,
                                                   QtCore.QUrl('images/interface/workspace-0-annotated.png'))
            assert picture is not None and not picture.isNull(), '图解资源未加载'
        page.grab().save(str(root / 'reader.png'))
        page.shutdown()
        page.close()
        store.close()
        app.quit()

    QtCore.QTimer.singleShot(1000, capture)
    app.exec()
    print(root / 'reader.png')


if __name__ == '__main__':
    os.environ.setdefault('PYTHONUTF8', '1')
    main()
