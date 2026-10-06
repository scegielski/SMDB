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
        self.channelWidth = round(190 * scale)
        self.hourWidth = round(200 * scale)
        textHeight = QtGui.QFontMetrics(font).height()
        markerFont = QtGui.QFont(font)
        markerFont.setPixelSize(max(10, min(16, round(10 * scale))))
        self.labelHeight = QtGui.QFontMetrics(markerFont).height() + 4
        self.headerHeight = self.labelHeight + textHeight + 6
        self.rowHeight = textHeight + 6
        self.setMinimumHeight(self.headerHeight + self.rowHeight + self.horizontalScrollBar().sizeHint().height() + 12)
        self._updateRanges()
        self._ensurePlaybackVisible()
        if self._centerOnLive:
            self.showCurrentHour()
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
        if self.playbackTime is None:
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
        painter.fillRect(0, 0, self.channelWidth, self.headerHeight, QtGui.QColor('#1a1aae'))
        painter.setPen(QtGui.QColor('white'))
        painter.drawText(QtCore.QRect(6, 0, self.channelWidth - 12, self.headerHeight), QtCore.Qt.AlignVCenter, 'CHANNEL')
        painter.setClipRect(0, self.headerHeight, self.channelWidth, height)
        for index, row in enumerate(self.rows):
            rect = self.rowRect(index)
            selected = row['channel'] == self.selectedChannel
            labelRect = QtCore.QRect(0, rect.y(), self.channelWidth, self.rowHeight)
            painter.fillRect(labelRect, QtGui.QColor('#ffcc00' if selected else '#0a0a6e'))
            painter.setPen(QtGui.QColor('black' if selected else 'white'))
            text = painter.fontMetrics().elidedText(row['label'], QtCore.Qt.ElideRight, self.channelWidth - 12)
            painter.drawText(labelRect.adjusted(6, 0, -6, 0), QtCore.Qt.AlignVCenter, text)
        painter.setClipping(False)
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

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._updateRanges()
        if self._centerOnLive:
            self.showCurrentHour()
        else:
            self._ensurePlaybackVisible()

    def mousePressEvent(self, event):
        index = (event.y() - self.headerHeight + self.verticalScrollBar().value()) // self.rowHeight
        if event.y() >= self.headerHeight and 0 <= index < len(self.rows):
            self.channelSelected.emit(self.rows[index]['channel'])

    def mouseMoveEvent(self, event):
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
