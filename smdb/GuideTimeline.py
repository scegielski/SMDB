"""A TV guide with a fixed channel column and a scrollable time axis."""
import math
import time

from PyQt5 import QtCore, QtGui, QtWidgets


class GuideTimeline(QtWidgets.QAbstractScrollArea):
    channelSelected = QtCore.pyqtSignal(int)
    timeRangeChanged = QtCore.pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows = []
        self.selectedChannel = 0
        self.now = time.time()
        self.playbackTime = None
        self._centerOnLive = False
        self.startTime = math.floor(self.now / 3600) * 3600
        self.endTime = self.startTime + 48 * 3600
        self.scale = 1.0
        self.channelScale = None
        self._channelWidthOverride = None
        self._channelDragOffset = None
        self._panOrigin = None
        self.panMode = 'drag'
        self._panLastPosition = None
        self._manualPanView = False
        self._panTimer = QtCore.QTimer(self)
        self._panTimer.setInterval(30)
        self._panTimer.timeout.connect(self._panTick)
        QtWidgets.QApplication.instance().applicationStateChanged.connect(self._applicationStateChanged)
        self.setFocusPolicy(QtCore.Qt.NoFocus)
        self.setMouseTracking(True)
        self.horizontalScrollBar().valueChanged.connect(self.viewport().update)
        self.verticalScrollBar().valueChanged.connect(self.viewport().update)
        self.setScale(1.0)

    def setScale(self, scale):
        self.scale = scale
        font = QtGui.QFont(self.font())
        font.setPixelSize(round(14 * scale))
        self.setFont(font)
        self.viewport().setFont(font)
        channelScale = self.channelScale if self.channelScale is not None else scale
        self.channelWidth = round((self._channelWidthOverride or 190) * channelScale)
        if self._channelWidthOverride is not None:
            self.channelWidth = self._boundedChannelWidth(self.channelWidth)
        self.hourWidth = round(200 * scale)
        textHeight = QtGui.QFontMetrics(font).height()
        channelFont = QtGui.QFont(font)
        channelFont.setPixelSize(round(14 * channelScale))
        rowTextHeight = max(textHeight, QtGui.QFontMetrics(channelFont).height())
        markerFont = QtGui.QFont(font)
        markerFont.setPixelSize(max(10, min(16, round(10 * scale))))
        self.labelHeight = QtGui.QFontMetrics(markerFont).height() + 4
        self.headerHeight = self.labelHeight + rowTextHeight + 6
        self.rowHeight = rowTextHeight + 6
        self.setMinimumHeight(self.headerHeight + self.rowHeight + self.horizontalScrollBar().sizeHint().height() + 12)
        self._updateRanges()
        self._ensurePlaybackVisible()
        if self._centerOnLive:
            self.showCurrentHour()
        self.viewport().update()

    def setChannelScale(self, scale):
        self.channelScale = scale
        self.setScale(self.scale)

    def captureZoomAnchor(self, point):
        """Keep the time and row beneath the pointer stationary during zoom."""
        if point.x() < self.channelWidth:
            return None
        timestamp = self.startTime + (point.x() - self.channelWidth + self.horizontalScrollBar().value()) * 3600 / self.hourWidth
        row = ((point.y() - self.headerHeight + self.verticalScrollBar().value()) / self.rowHeight
               if point.y() >= self.headerHeight else None)
        self.stopPanning()
        self._centerOnLive = False
        self._manualPanView = True
        return timestamp, QtCore.QPoint(point), row

    def restoreZoomAnchor(self, anchor):
        if anchor is None:
            return
        timestamp, point, row = anchor
        left = timestamp - (point.x() - self.channelWidth) * 3600 / self.hourWidth
        right = left + max(1, self.viewport().width() - self.channelWidth) * 3600 / self.hourWidth
        oldRange = self.startTime, self.endTime
        self.startTime = min(self.startTime, math.floor(left / 3600) * 3600)
        self.endTime = max(self.endTime, math.ceil(right / 3600) * 3600)
        self._updateRanges()
        self.horizontalScrollBar().setValue(round((timestamp - self.startTime) * self.hourWidth / 3600
                                                 - (point.x() - self.channelWidth)))
        if row is not None:
            self.verticalScrollBar().setValue(round(row * self.rowHeight + self.headerHeight - point.y()))
        if oldRange != (self.startTime, self.endTime):
            self.timeRangeChanged.emit()
        self.viewport().update()

    def setRows(self, rows, selectedChannel):
        self.rows = rows
        self.selectedChannel = selectedChannel
        self._updateRanges()
        self._ensurePlaybackVisible()
        self.viewport().update()

    def setCurrentTime(self, now):
        self.now = now
        self.viewport().update()

    def setPlaybackTime(self, timestamp):
        self.playbackTime = timestamp
        if timestamp is not None:
            self._centerOnLive = False
        self._ensurePlaybackVisible()
        self.viewport().update()

    def _ensurePlaybackVisible(self):
        if self.playbackTime is None or self._manualPanView or self._channelDragOffset is not None:
            return
        visibleWidth = self.viewport().width() - self.channelWidth
        if visibleWidth <= 0:
            return
        margin = min(80, max(8, visibleWidth // 4))
        paddingSeconds = margin * 3600 / self.hourWidth
        oldStart, oldEnd = self.startTime, self.endTime
        if self.playbackTime - paddingSeconds < self.startTime:
            self.startTime = math.floor((self.playbackTime - paddingSeconds) / 3600) * 3600
        if self.playbackTime + paddingSeconds > self.endTime:
            self.endTime = math.ceil((self.playbackTime + paddingSeconds) / 3600) * 3600
        bar = self.horizontalScrollBar()
        if (oldStart, oldEnd) != (self.startTime, self.endTime):
            oldScroll = bar.value()
            self._updateRanges()
            bar.setValue(oldScroll + round((oldStart - self.startTime) * self.hourWidth / 3600))
        position = (self.playbackTime - self.startTime) * self.hourWidth / 3600
        x = position - bar.value()
        if x < margin:
            bar.setValue(round(position - margin))
        elif x > visibleWidth - margin:
            bar.setValue(round(position - visibleWidth + margin))
        if (oldStart, oldEnd) != (self.startTime, self.endTime):
            self.timeRangeChanged.emit()

    def showCurrentHour(self):
        self.resumePlaybackFollow()
        # Center the actual live marker, allowing earlier hours on its left.
        # Resize may occur after the guide opens, so retain this initial view
        # until a manual playback cursor takes over.
        self._centerOnLive = True
        visibleWidth = self.viewport().width() - self.channelWidth
        if visibleWidth <= 0:
            return  # the hidden guide has not received its usable layout yet
        halfSeconds = visibleWidth * 1800 / self.hourWidth
        oldStart, oldEnd = self.startTime, self.endTime
        self.startTime = min(self.startTime, math.floor((self.now - halfSeconds) / 3600) * 3600)
        self.endTime = max(self.endTime, math.ceil((self.now + halfSeconds) / 3600) * 3600)
        self._updateRanges()
        self.horizontalScrollBar().setValue(round((self.now - self.startTime) * self.hourWidth / 3600 - visibleWidth / 2))
        if (oldStart, oldEnd) != (self.startTime, self.endTime):
            self.timeRangeChanged.emit()

    def _updateRanges(self):
        self.horizontalScrollBar().setRange(0, max(0, round((self.endTime - self.startTime) / 3600 * self.hourWidth)
                                                   - max(1, self.viewport().width() - self.channelWidth)))
        self.horizontalScrollBar().setPageStep(max(1, self.viewport().width() - self.channelWidth))
        self.verticalScrollBar().setRange(0, max(0, len(self.rows) * self.rowHeight
                                                 - max(1, self.viewport().height() - self.headerHeight)))
        self.verticalScrollBar().setPageStep(max(1, self.viewport().height() - self.headerHeight))

    def rowRect(self, index):
        return QtCore.QRect(0, self.headerHeight + index * self.rowHeight - self.verticalScrollBar().value(),
                            self.viewport().width(), self.rowHeight)

    def ensureChannelVisible(self, channel):
        if self.isPanning():
            return
        index = next((i for i, row in enumerate(self.rows) if row['channel'] == channel), None)
        if index is None:
            return
        height = max(1, self.viewport().height() - self.headerHeight)
        self.verticalScrollBar().setValue(index * self.rowHeight - max(0, (height - self.rowHeight) // 2))

    def timeX(self, timestamp):
        return self.channelWidth + (timestamp - self.startTime) * self.hourWidth / 3600 - self.horizontalScrollBar().value()

    def markerLabel(self, timestamp):
        return time.strftime('%I:%M:%S %p', time.localtime(timestamp))

    def programRect(self, rowIndex, program):
        row = self.rowRect(rowIndex)
        return QtCore.QRectF(self.timeX(program['start']), row.y() + 2,
                             (program['end'] - program['start']) * self.hourWidth / 3600,
                             self.rowHeight - 4)

    def paintEvent(self, event):
        painter = QtGui.QPainter(self.viewport())
        painter.setFont(self.font())
        painter.fillRect(self.viewport().rect(), QtGui.QColor('#050531'))
        width, height = self.viewport().width(), self.viewport().height()
        painter.setClipRect(self.channelWidth, self.headerHeight, max(0, width - self.channelWidth), height)
        for index, row in enumerate(self.rows):
            area = self.rowRect(index)
            if area.bottom() < self.headerHeight or area.top() > height:
                continue
            for program in row['programs']:
                rect = self.programRect(index, program)
                if rect.right() < self.channelWidth or rect.left() > width:
                    continue
                color = '#00ff00' if program['playing'] else '#0a0a6e'
                painter.fillRect(rect, QtGui.QColor(color))
                painter.setPen(QtGui.QColor('#4444aa'))
                painter.drawRect(rect)
                painter.setPen(QtGui.QColor('black' if program['playing'] else 'white'))
                textRect = rect.adjusted(6, 0, -6, 0)
                text = painter.fontMetrics().elidedText(program['title'], QtCore.Qt.ElideRight, max(0, int(textRect.width())))
                painter.drawText(textRect, QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft, text)
        painter.setClipping(False)
        # Hour headings use wall time, independently of the playing film.
        painter.setClipRect(self.channelWidth, 0, max(0, width - self.channelWidth), self.headerHeight)
        first = max(0, self.horizontalScrollBar().value() // self.hourWidth)
        hourCount = math.ceil((self.endTime - self.startTime) / 3600)
        for hour in range(first, min(hourCount, first + math.ceil(width / self.hourWidth) + 1)):
            timestamp = self.startTime + hour * 3600
            rect = QtCore.QRectF(self.timeX(timestamp), self.labelHeight, self.hourWidth,
                                 self.headerHeight - self.labelHeight)
            active = timestamp <= self.now < timestamp + 3600
            blockRect = rect.adjusted(2, 2, -2, -2)
            painter.setBrush(QtGui.QColor('#ffcc00' if active else '#123b57'))
            painter.setPen(QtGui.QPen(QtGui.QColor('#ffe06a' if active else '#4b8196'), 1))
            radius = min(10, round(5 * self.scale))
            painter.drawRoundedRect(blockRect, radius, radius)
            painter.setPen(QtGui.QColor('black' if active else 'white'))
            painter.drawText(blockRect.adjusted(6, 0, -6, 0), QtCore.Qt.AlignVCenter,
                             time.strftime('%a %I:%M %p', time.localtime(timestamp)))
        painter.setClipping(False)
        # Channel labels stay fixed while the timeline scrolls horizontally.
        channelFont = QtGui.QFont(self.font())
        channelFont.setPixelSize(round(14 * (self.channelScale if self.channelScale is not None else self.scale)))
        painter.setFont(channelFont)
        painter.fillRect(0, 0, self.channelWidth, self.headerHeight, QtGui.QColor('#1b2d42'))
        painter.setPen(QtGui.QColor('white'))
        clockLabel = time.strftime('%a %I:%M:%S %p', time.localtime(self.now))
        clockFont = QtGui.QFont(channelFont)
        available = max(1, self.channelWidth - 16)
        labelWidth = QtGui.QFontMetrics(clockFont).horizontalAdvance(clockLabel)
        if labelWidth > available:
            clockFont.setPixelSize(max(8, int(clockFont.pixelSize() * available / labelWidth)))
        painter.setFont(clockFont)
        painter.drawText(QtCore.QRect(6, 0, self.channelWidth - 16, self.headerHeight),
                         QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft, clockLabel)
        painter.setFont(channelFont)
        painter.setClipRect(0, self.headerHeight, self.channelWidth, height)
        for index, row in enumerate(self.rows):
            rect = self.rowRect(index)
            selected = row['channel'] == self.selectedChannel
            labelRect = QtCore.QRect(0, rect.y(), self.channelWidth, self.rowHeight)
            painter.fillRect(labelRect, QtGui.QColor('#ffcc00' if selected else
                                                   ('#24384c' if index % 2 else '#1b2d42')))
            painter.setPen(QtGui.QColor('#51748c'))
            painter.drawLine(labelRect.bottomLeft(), labelRect.bottomRight())
            painter.setPen(QtGui.QColor('black' if selected else 'white'))
            text = painter.fontMetrics().elidedText(row['label'], QtCore.Qt.ElideRight, self.channelWidth - 12)
            painter.drawText(labelRect.adjusted(6, 0, -6, 0), QtCore.Qt.AlignVCenter, text)
        painter.setClipping(False)
        # Keep both boundaries visible regardless of horizontal/vertical panning.
        painter.setPen(QtGui.QPen(QtGui.QColor('#6e8bbd'), 4))
        painter.drawLine(self.channelWidth - 2, 0, self.channelWidth - 2, height)
        painter.drawLine(0, self.headerHeight - 1, width, self.headerHeight - 1)
        # Compact labels sit above the hour blocks. Both pointers start at the
        # top edge of those blocks and continue through the program rows.
        painter.setClipRect(self.channelWidth, 0, max(0, width - self.channelWidth), height)
        markerFont = QtGui.QFont(self.font())
        markerFont.setPixelSize(max(10, min(16, round(10 * self.scale))))
        painter.setFont(markerFont)
        labelRects = []
        for timestamp, color in ((self.now, '#ffcc00'), (self.playbackTime, '#00ffff')):
            if timestamp is None:
                continue
            x = self.timeX(timestamp)
            if not self.channelWidth <= x <= width:
                continue
            label = self.markerLabel(timestamp)
            labelWidth = painter.fontMetrics().horizontalAdvance(label) + 8
            left = max(self.channelWidth, min(x - labelWidth / 2, width - labelWidth))
            labelRect = QtCore.QRectF(left, 0, labelWidth, self.labelHeight)
            if labelRects and labelRect.intersects(labelRects[0]):
                previous = labelRects[0]
                left = previous.right() + 4 if previous.right() + 4 + labelWidth <= width else previous.left() - labelWidth - 4
                labelRect.moveLeft(max(self.channelWidth, left))
            labelRects.append(labelRect)
            painter.setPen(QtGui.QPen(QtGui.QColor('#050531'), 4))
            painter.drawLine(QtCore.QPointF(x, self.labelHeight), QtCore.QPointF(x, height))
            painter.setPen(QtGui.QPen(QtGui.QColor(color), 2))
            painter.drawLine(QtCore.QPointF(x, self.labelHeight), QtCore.QPointF(x, height))
            painter.setBrush(QtGui.QColor(color))
            painter.setPen(QtGui.QPen(QtGui.QColor('#050531'), 1))
            painter.drawPolygon(QtGui.QPolygonF([
                QtCore.QPointF(x - 5, self.labelHeight),
                QtCore.QPointF(x + 5, self.labelHeight),
                QtCore.QPointF(x, self.labelHeight + 7)]))
            painter.fillRect(labelRect, QtGui.QColor('#050531'))
            painter.setPen(QtGui.QColor(color))
            painter.drawText(labelRect, QtCore.Qt.AlignCenter, label)
        if self.isPanning() and self.panMode == 'browser':
            painter.setClipping(False)
            origin = self.viewport().mapFromGlobal(self._panOrigin)
            painter.setPen(QtGui.QPen(QtGui.QColor('white'), 1))
            painter.setBrush(QtGui.QColor('#222'))
            painter.drawEllipse(origin, 11, 11)
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                tip = origin + QtCore.QPoint(dx * 7, dy * 7)
                painter.drawLine(origin, tip)
                painter.drawLine(tip, origin + QtCore.QPoint(dx * 4 - dy * 3, dy * 4 + dx * 3))
                painter.drawLine(tip, origin + QtCore.QPoint(dx * 4 + dy * 3, dy * 4 - dx * 3))

    def isPanning(self):
        return self._panOrigin is not None

    def stopPanning(self):
        self._panOrigin = None
        self._panLastPosition = None
        self._panTimer.stop()
        self.viewport().unsetCursor()
        self.viewport().update()

    def resumePlaybackFollow(self):
        self.stopPanning()
        self._manualPanView = False

    def setPanMode(self, mode):
        self.stopPanning()
        self.panMode = mode if mode in ('drag', 'browser') else 'drag'

    def _applicationStateChanged(self, state):
        if state != QtCore.Qt.ApplicationActive:
            self.stopPanning()

    def _panTick(self):
        if not self.isPanning() or self.panMode != 'browser':
            return
        delta = QtGui.QCursor.pos() - self._panOrigin
        def speed(distance):
            if abs(distance) <= 8:
                return 0
            return math.copysign(min(40, (abs(distance) - 8) / 8), distance)
        dx, dy = round(speed(delta.x())), round(speed(delta.y()))
        self._scrollPanBy(dx, dy)

    def _scrollPanBy(self, dx, dy):
        horizontal = self.horizontalScrollBar()
        if dx and (horizontal.value() + dx < horizontal.minimum() or
                   horizontal.value() + dx > horizontal.maximum()):
            # Continue through the repeating schedule instead of hitting the
            # initial time window's edge. Keep the current viewport stationary.
            if dx < 0:
                hours = max(1, math.ceil(-(horizontal.value() + dx) / self.hourWidth))
                self.startTime -= hours * 3600
                oldScroll = horizontal.value() + hours * self.hourWidth
            else:
                hours = max(1, math.ceil((horizontal.value() + dx - horizontal.maximum()) / self.hourWidth))
                self.endTime += hours * 3600
                oldScroll = horizontal.value()
            self._updateRanges()
            horizontal.setValue(oldScroll)
            self.timeRangeChanged.emit()
        horizontal.setValue(horizontal.value() + dx)
        vertical = self.verticalScrollBar()
        vertical.setValue(vertical.value() + dy)

    def hideEvent(self, event):
        self._channelDragOffset = None
        self.stopPanning()
        super().hideEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._channelWidthOverride is not None:
            channelScale = self.channelScale if self.channelScale is not None else self.scale
            self.channelWidth = self._boundedChannelWidth(round(self._channelWidthOverride * channelScale))
        self._updateRanges()
        if self._centerOnLive:
            self.showCurrentHour()
        else:
            self._ensurePlaybackVisible()

    def wheelEvent(self, event):
        if event.modifiers() & QtCore.Qt.ControlModifier:
            event.ignore()
            return
        # Ordinary wheel motion always scrolls channels vertically, even when
        # the horizontal timeline has a range and the channel list does not.
        pixels = event.pixelDelta().y()
        distance = pixels if pixels else event.angleDelta().y() / 120 * self.rowHeight * 3
        bar = self.verticalScrollBar()
        bar.setValue(bar.value() - round(distance))
        event.accept()

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.MiddleButton:
            if self.isPanning():
                self.stopPanning()
            else:
                self._panOrigin = event.globalPos()
                self._panLastPosition = event.globalPos()
                self._manualPanView = True
                self._centerOnLive = False
                self.viewport().setCursor(QtCore.Qt.SizeAllCursor if self.panMode == 'browser' else QtCore.Qt.ClosedHandCursor)
                QtWidgets.QToolTip.hideText()
                if self.panMode == 'browser':
                    self._panTimer.start()
                self.viewport().update()
            event.accept()
            return
        if self.isPanning():
            self.stopPanning()
            event.accept()
            return
        if event.button() != QtCore.Qt.LeftButton:
            return
        if abs(event.x() - self.channelWidth) <= 6:
            self._channelDragOffset = event.x() - self.channelWidth
            self.viewport().setCursor(QtCore.Qt.SplitHCursor)
            QtWidgets.QToolTip.hideText()
            event.accept()
            return
        index = (event.y() - self.headerHeight + self.verticalScrollBar().value()) // self.rowHeight
        if event.y() >= self.headerHeight and 0 <= index < len(self.rows):
            self.channelSelected.emit(self.rows[index]['channel'])

    def mouseMoveEvent(self, event):
        if self.isPanning():
            if self.panMode == 'drag':
                delta = self._panLastPosition - event.globalPos()
                self._panLastPosition = event.globalPos()
                self._scrollPanBy(delta.x(), delta.y())
                event.accept()
            return
        if self._channelDragOffset is not None:
            self.channelWidth = self._boundedChannelWidth(event.x() - self._channelDragOffset)
            channelScale = self.channelScale if self.channelScale is not None else self.scale
            self._channelWidthOverride = self.channelWidth / channelScale
            self._updateRanges()
            self.viewport().update()
            event.accept()
            return
        if abs(event.x() - self.channelWidth) <= 6:
            self.viewport().setCursor(QtCore.Qt.SplitHCursor)
            QtWidgets.QToolTip.hideText()
            return
        self.viewport().unsetCursor()
        index = (event.y() - self.headerHeight + self.verticalScrollBar().value()) // self.rowHeight
        if event.y() >= self.headerHeight and event.x() >= self.channelWidth and 0 <= index < len(self.rows):
            for program in self.rows[index]['programs']:
                if self.programRect(index, program).contains(event.pos()):
                    label = '{}\n{} – {}'.format(program['title'],
                        time.strftime('%a %I:%M %p', time.localtime(program['start'])),
                        time.strftime('%a %I:%M %p', time.localtime(program['end'])))
                    QtWidgets.QToolTip.showText(event.globalPos(), label, self)
                    return
        QtWidgets.QToolTip.hideText()

    def _boundedChannelWidth(self, width):
        return max(80, min(round(width), max(80, self.viewport().width() - 120)))

    def mouseReleaseEvent(self, event):
        if event.button() == QtCore.Qt.MiddleButton and self.panMode == 'drag' and self.isPanning():
            self.stopPanning()
            event.accept()
            return
        if event.button() == QtCore.Qt.LeftButton and self._channelDragOffset is not None:
            self._channelDragOffset = None
            self.viewport().unsetCursor()
            if self._centerOnLive:
                self.showCurrentHour()
            else:
                self._ensurePlaybackVisible()
            event.accept()
            return
        super().mouseReleaseEvent(event)
