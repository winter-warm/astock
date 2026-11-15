from pathlib import Path
from PySide6 import QtCore, QtGui

root = Path(__file__).resolve().parents[1] / "assets"
root.mkdir(exist_ok=True)
image = QtGui.QImage(256, 256, QtGui.QImage.Format.Format_ARGB32)
image.fill(QtGui.QColor("#111b29"))
painter = QtGui.QPainter(image)
painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
painter.setPen(QtGui.QPen(QtGui.QColor("#57d3b0"), 18, QtCore.Qt.PenStyle.SolidLine,
                         QtCore.Qt.PenCapStyle.RoundCap, QtCore.Qt.PenJoinStyle.RoundJoin))
painter.drawPolyline([QtCore.QPointF(45, 195), QtCore.QPointF(122, 55), QtCore.QPointF(210, 195)])
painter.setPen(QtGui.QPen(QtGui.QColor("#87b5e8"), 12, QtCore.Qt.PenStyle.SolidLine,
                         QtCore.Qt.PenCapStyle.RoundCap))
painter.drawPolyline([QtCore.QPointF(77, 171), QtCore.QPointF(112, 146), QtCore.QPointF(146, 156), QtCore.QPointF(177, 113)])
painter.end()
image.save(str(root / "astock.ico"))
image.save(str(root / "astock.png"))
