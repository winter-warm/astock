from PySide6 import QtCore, QtWidgets

from astock.domain import now_cn
from astock.window import MainWindow


def test_download_presets_are_relative_editable_and_do_not_start_download(qtbot, tmp_path):
    window = MainWindow(tmp_path, start_workers=False)
    qtbot.addWidget(window)
    window.show()
    errors = []

    def inspect():
        dialog = QtWidgets.QApplication.activeModalWidget()
        try:
            start = dialog.findChild(QtWidgets.QDateEdit, "historyStart")
            end = dialog.findChild(QtWidgets.QDateEdit, "historyEnd")
            now = now_cn()
            today = QtCore.QDate(now.year, now.month, now.day)
            assert end.date() == today
            assert start.date() == today.addDays(-89)
            for days in (30, 365, 90):
                dialog.findChild(QtWidgets.QPushButton, f"historyRecent{days}").click()
                assert start.date() == today.addDays(-(days - 1))
                assert end.date() == today
            symbols = dialog.findChild(QtWidgets.QLineEdit, "historySymbols")
            dialog.findChild(QtWidgets.QPushButton, "historyPresetEtf").click()
            assert symbols.text() == "510300.SH,510500.SH,159915.SZ"
            dialog.findChild(QtWidgets.QPushButton, "historyPresetStocks").click()
            assert symbols.text() == "600000.SH,000001.SZ,600036.SH"
            symbols.setText("600519.SH")
            assert symbols.text() == "600519.SH"
            start.setDate(today.addDays(-20))
            period = dialog.findChild(QtWidgets.QComboBox, "historyPeriod")
            period.setCurrentIndex(period.findData("1m"))
            assert start.date() == today.addDays(-20)
            assert window.history_process is None
        except Exception as error:
            errors.append(error)
        finally:
            dialog.reject()

    QtCore.QTimer.singleShot(50, inspect)
    window.download_dialog()
    assert not errors, errors
    assert window.history_process is None
    window.close()
