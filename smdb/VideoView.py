"""Composited Qt video view, allowing captions to paint over video frames."""
import time

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtMultimediaWidgets import QGraphicsVideoItem


class VideoOsd(QtWidgets.QWidget):
    """Transparent, mouse-pass-through classic TV status display."""
    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
        self.setAttribute(QtCore.Qt.WA_NoSystemBackground)
        self.items = {}
        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self._expire)
        self.hide()

    def display(self, kind, value, seconds=3):
        self.items[kind] = (value, time.monotonic() + seconds)
        self.setGeometry(self.parentWidget().rect())
        self.show()
        self.raise_()
        self.timer.start()
        self.update()

    def _expire(self):
        now = time.monotonic()
        self.items = {kind: item for kind, item in self.items.items() if item[1] > now}
        if not self.items:
            self.timer.stop()
            self.hide()
        self.update()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        font = QtGui.QFont('Consolas')
        font.setBold(True)
        size = max(12, min(52, round(min(self.width() * .045, self.height() * .075))))
        font.setPixelSize(size)
        painter.setFont(font)
        margin = max(10, round(self.width() * .04))
        green = QtGui.QColor('#39ff14')
        def text(rect, label, align=QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter):
            painter.setPen(QtGui.QColor('black'))
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                painter.drawText(rect.translated(dx, dy), align, label)
            painter.setPen(green)
            painter.drawText(rect, align, label)
        if 'channel' in self.items:
            number, name = self.items['channel'][0]
            rect = QtCore.QRect(margin, margin, self.width() - margin * 2, size * 2)
            label = QtGui.QFontMetrics(font).elidedText(f'CH {number:02d}  {name.upper()}', QtCore.Qt.ElideRight, rect.width())
            text(rect, label)
        if 'volume' in self.items:
            volume = self.items['volume'][0]
            top = round(self.height() * .65)
            text(QtCore.QRect(margin, top, self.width() - margin * 2, size * 2),
                 'MUTE' if volume == 0 else f'VOLUME {volume}')
            barWidth = min(self.width() - 2 * margin, round(self.width() * .65))
            step = barWidth / 25
            y = top + size * 2
            for index in range(25):
                rect = QtCore.QRectF(margin + index * step, y, max(1, step * .55), size * .65)
                painter.setPen(QtGui.QPen(QtGui.QColor('black'), 2))
                painter.setBrush(green if index < round(volume / 4) else QtCore.Qt.NoBrush)
                painter.drawRect(rect)
                if index >= round(volume / 4):
                    painter.setPen(QtGui.QPen(green, 1))
                    painter.drawLine(QtCore.QPointF(rect.left(), rect.center().y()), QtCore.QPointF(rect.right(), rect.center().y()))


class VideoView(QtWidgets.QGraphicsView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.osd = VideoOsd(self.viewport())
        self.setScene(QtWidgets.QGraphicsScene(self))
        self.videoItem = QGraphicsVideoItem()
        self.videoItem.setAspectRatioMode(QtCore.Qt.KeepAspectRatio)
        self.scene().addItem(self.videoItem)
        self.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setBackgroundBrush(QtGui.QColor('black'))
        self.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop)
        self.setViewportUpdateMode(QtWidgets.QGraphicsView.FullViewportUpdate)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)

    def videoSurface(self):
        return self.videoItem.videoSurface()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        size = QtCore.QSizeF(self.viewport().size())
        self.setSceneRect(QtCore.QRectF(QtCore.QPointF(), size))
        self.videoItem.setSize(size)
        self.osd.setGeometry(self.viewport().rect())
        self.osd.raise_()
