"""Composited Qt video view, allowing captions to paint over video frames."""
import time
from .DlssGpu import DlssGpuView

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtMultimediaWidgets import QGraphicsVideoItem
from PyQt5.QtMultimedia import QAbstractVideoSurface, QVideoFrame, QAbstractVideoBuffer


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

    def updateValue(self, kind, value):
        if kind in self.items:
            self.items[kind] = (value, self.items[kind][1])
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
        lines = []
        if 'channel' in self.items:
            number, name = self.items['channel'][0]
            lines.append((f'CH {number:02d}  {name.upper()}', QtCore.Qt.AlignLeft))
        if 'seek' in self.items:
            seconds, timestamp = self.items['seek'][0]
            lines.extend(((f'{seconds:+d} SEC', QtCore.Qt.AlignHCenter),
                          (time.strftime('%I:%M:%S %p', time.localtime(timestamp)), QtCore.Qt.AlignHCenter)))
        for kind, (value, _expiry) in self.items.items():
            if kind not in ('channel', 'seek', 'subtitleOffset', 'volume'):
                lines.append((str(value), QtCore.Qt.AlignHCenter))
        if 'subtitleOffset' in self.items:
            lines.append((f'SUBTITLES {self.items["subtitleOffset"][0]:+d} SEC', QtCore.Qt.AlignHCenter))
        volume = self.items.get('volume')
        if volume:
            lines.append(('MUTE' if volume[0] == 0 else f'VOLUME {volume[0]}', QtCore.Qt.AlignLeft))
        # Keep the message stack at the bottom, above any visible captions.
        bottom = self.height() - margin
        for label in self.parentWidget().findChildren(QtWidgets.QLabel):
            if label.property('videoCaption') and label.isVisible() and label.text():
                bottom = min(bottom, label.y() - 8)
        units = len(lines) * 1.4 + (0.85 if volume else 0)
        size = min(size, max(12, int(min(bottom, self.height() * .48) / max(1, units))))
        font.setPixelSize(size)
        painter.setFont(font)
        rowHeight = round(size * 1.4)
        y = max(margin, bottom - len(lines) * rowHeight - (round(size * .85) if volume else 0))
        for label, alignment in lines:
            rect = QtCore.QRect(margin, y, self.width() - margin * 2, rowHeight)
            label = QtGui.QFontMetrics(font).elidedText(label, QtCore.Qt.ElideRight, rect.width())
            text(rect, label, alignment | QtCore.Qt.AlignVCenter)
            y += rowHeight
        if volume:
            barWidth = min(self.width() - 2 * margin, round(self.width() * .65))
            step = barWidth / 25
            for index in range(25):
                rect = QtCore.QRectF(margin + index * step, y, max(1, step * .55), size * .65)
                painter.setPen(QtGui.QPen(QtGui.QColor('black'), 2))
                painter.setBrush(green if index < round(volume[0] / 4) else QtCore.Qt.NoBrush)
                painter.drawRect(rect)
                if index >= round(volume[0] / 4):
                    painter.setPen(QtGui.QPen(green, 1))
                    painter.drawLine(QtCore.QPointF(rect.left(), rect.center().y()), QtCore.QPointF(rect.right(), rect.center().y()))


class _FrameSurface(QAbstractVideoSurface):
    """Forward Qt playback normally, with CPU RGB frames available to DLSS."""
    def __init__(self, view, original):
        super().__init__(view)
        self.view = view
        self.original = original
        self.lastFrame = None

    def supportedPixelFormats(self, handleType=QAbstractVideoBuffer.NoHandle):
        if handleType != QAbstractVideoBuffer.NoHandle:
            return []
        return [QVideoFrame.Format_RGB32, QVideoFrame.Format_ARGB32]

    def start(self, format):
        self.view.resetDlssFrame()
        self.lastFrame = None
        return self.original.start(format) and super().start(format)

    def stop(self):
        self.lastFrame = None
        self.view.resetDlssFrame()
        self.original.stop()
        super().stop()

    def present(self, frame):
        result = (frame.isValid() if self.view.dlssEnabled and self.view._gpuView.isVisible()
                  else self.original.present(frame))
        self.lastFrame = QVideoFrame(frame)
        self.submitFrame()
        return result

    def submitFrame(self):
        if self.lastFrame is None or self.view._dlssProcessor is None:
            return
        warmOnly = not self.view.dlssEnabled
        if warmOnly and (not self.view._dlssPrewarm or not self.view._dlssProcessor.needsWarm(
                self.lastFrame.width(), self.lastFrame.height())):
            return
        if not warmOnly and self.view._dlssProcessor._busy:
            self.view._dlssProcessor.deferFrame(self.view)
            return
        frame = QVideoFrame(self.lastFrame)
        if not frame.map(QAbstractVideoBuffer.ReadOnly):
            return
        try:
            format = QVideoFrame.imageFormatFromPixelFormat(frame.pixelFormat())
            if format == QtGui.QImage.Format_Invalid:
                return
            bits = frame.bits(); bits.setsize(frame.mappedBytes())
            image = QtGui.QImage(bits, frame.width(), frame.height(), frame.bytesPerLine(), format).copy()
            self.view._dlssProcessor.submit(self.view, image, frame.startTime(), warmOnly)
        finally:
            frame.unmap()


class VideoView(QtWidgets.QGraphicsView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        self._gpuView = DlssGpuView(self.viewport())
        self.osd = VideoOsd(self.viewport())
        self.setScene(QtWidgets.QGraphicsScene(self))
        self.videoItem = QGraphicsVideoItem()
        self.videoItem.setAspectRatioMode(QtCore.Qt.KeepAspectRatio)
        self.scene().addItem(self.videoItem)
        self.dlssEnabled = False
        self._dlssPrewarm = False
        self._dlssGeneration = 0
        self._dlssProcessor = None
        self._enhancedItem = QtWidgets.QGraphicsPixmapItem()
        self._enhancedItem.setTransformationMode(QtCore.Qt.SmoothTransformation)
        self._enhancedItem.setZValue(1)
        self.scene().addItem(self._enhancedItem)
        self._enhancedItem.hide()
        self._frameSurface = _FrameSurface(self, self.videoItem.videoSurface())
        self.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setBackgroundBrush(QtGui.QColor('black'))
        self.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop)
        # Interpolate decoded video frames when scaling the graphics item.
        self.setRenderHint(QtGui.QPainter.SmoothPixmapTransform, True)
        self.setViewportUpdateMode(QtWidgets.QGraphicsView.FullViewportUpdate)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)

    def videoSurface(self):
        return self._frameSurface

    def setDlssEnabled(self, enabled, processor=None, prewarm=False):
        if enabled == self.dlssEnabled and prewarm == self._dlssPrewarm:
            return
        self.dlssEnabled = enabled
        self._dlssPrewarm = prewarm
        self._dlssProcessor = processor
        self.resetDlssFrame()
        if not enabled and self._frameSurface.lastFrame is not None:
            self._frameSurface.original.present(self._frameSurface.lastFrame)
        if enabled or prewarm:
            self._frameSurface.submitFrame()

    def resetDlssFrame(self):
        self._dlssGeneration += 1
        self._enhancedItem.hide()
        wasGpuVisible = self._gpuView.isVisible()
        self._gpuView.hide()
        if wasGpuVisible and self._frameSurface.lastFrame is not None:
            self._frameSurface.original.present(self._frameSurface.lastFrame)

    def showDlssGpuFrame(self, name, width, height):
        self._gpuView.setGeometry(self.viewport().rect())
        self._gpuView.present(name, width, height)
        for widget in self.viewport().findChildren(QtWidgets.QWidget, options=QtCore.Qt.FindDirectChildrenOnly):
            if widget is not self._gpuView:
                widget.raise_()

    def showDlssFrame(self, image):
        self._enhancedItem.setPixmap(QtGui.QPixmap.fromImage(image))
        self._fitDlssFrame()
        self._enhancedItem.show()

    def _fitDlssFrame(self):
        size = self._enhancedItem.pixmap().size()
        if size.isEmpty():
            return
        bounds = self.viewport().size()
        scale = min(bounds.width() / size.width(), bounds.height() / size.height())
        self._enhancedItem.setScale(scale)
        self._enhancedItem.setPos((bounds.width() - size.width() * scale) / 2,
                                 (bounds.height() - size.height() * scale) / 2)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fitDlssFrame()
        self._gpuView.setGeometry(self.viewport().rect())
        size = QtCore.QSizeF(self.viewport().size())
        self.setSceneRect(QtCore.QRectF(QtCore.QPointF(), size))
        self.videoItem.setSize(size)
        self.osd.setGeometry(self.viewport().rect())
        self.osd.raise_()
