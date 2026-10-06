"""A TV guide with a fixed channel column and a scrollable time axis."""
import math
import time

from PyQt5 import QtCore, QtGui, QtWidgets


class GuideTimeline(QtWidgets.QAbstractScrollArea):
    channelSelected = QtCore.pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows = []
        self.selectedChannel = 0
        self.now = time.time()
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
        self.headerHeight = round(30 * scale)
        self.rowHeight = round(34 * scale)
        self.setMinimumHeight(self.headerHeight + self.rowHeight + self.horizontalScrollBar().sizeHint().height() + 12)
        self._updateRanges()
        self.viewport().update()

    def setRows(self, rows, selectedChannel):
        self.rows = rows
        self.selectedChannel = selectedChannel
        self._updateRanges()
        self.viewport().update()

    def setCurrentTime(self, now):
        self.now = now
        self.viewport().update()

    def showCurrentHour(self):
        # Only opening the guide recenters time. Program skips preserve the view.
        hour = math.floor(self.now / 3600) * 3600
        if hour < self.startTime or hour >= self.endTime:
            self.startTime = hour
            self.endTime = hour + 48 * 3600
        self._updateRanges()
        self.horizontalScrollBar().setValue(round((hour - self.startTime) * self.hourWidth / 3600))

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
        for hour in range(first, min(48, first + math.ceil(width / self.hourWidth) + 1)):
            timestamp = self.startTime + hour * 3600
            rect = QtCore.QRectF(self.timeX(timestamp), 0, self.hourWidth, self.headerHeight)
            active = timestamp <= self.now < timestamp + 3600
            painter.fillRect(rect, QtGui.QColor('#ffcc00' if active else '#1a1aae'))
            painter.setPen(QtGui.QColor('black' if active else 'white'))
            painter.drawText(rect.adjusted(6, 0, 0, 0), QtCore.Qt.AlignVCenter,
                             time.strftime('%a %H:%M', time.localtime(timestamp)))
            painter.setPen(QtGui.QColor('#4444aa'))
            painter.drawRect(rect)
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
        # A thin time marker also shows where we are within the current hour.
        x = self.timeX(self.now)
        if self.channelWidth <= x <= width:
            painter.setPen(QtGui.QPen(QtGui.QColor('#ffcc00'), 2))
            painter.drawLine(QtCore.QPointF(x, self.headerHeight), QtCore.QPointF(x, height))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._updateRanges()

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
                        time.strftime('%a %H:%M', time.localtime(program['start'])),
                        time.strftime('%a %H:%M', time.localtime(program['end'])))
                    QtWidgets.QToolTip.showText(event.globalPos(), label, self)
                    return
        QtWidgets.QToolTip.hideText()
