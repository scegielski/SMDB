"""Titleless TV remote with click-preserving surface dragging."""
from PyQt5 import QtCore, QtGui, QtWidgets


class RemoteDock(QtWidgets.QDockWidget):
    cornerResizeRequested = QtCore.pyqtSignal(QtCore.QSize)
    def __init__(self, parent):
        super().__init__('SMTV Remote', parent)
        self.setObjectName('smtvRemoteDock')
        self.setAttribute(QtCore.Qt.WA_ShowWithoutActivating)
        self.setAllowedAreas(QtCore.Qt.RightDockWidgetArea)
        self.setFeatures(self.DockWidgetMovable | self.DockWidgetFloatable)
        title = QtWidgets.QWidget(self)
        title.setFixedHeight(0)
        self.setTitleBarWidget(title)
        self.topLevelChanged.connect(self._updateShape)
        self.cornerRadius = 30
        self.resizeScale = 0.85
        self._fullscreenOverlay = False
        self._resizing = False
        self._press = None
        self._dragging = False
        self._pressedButton = None
        self._changingWindows = False
        # Observe the whole gesture, including moves delivered to another child
        # or outside the remote. This also covers dynamically created controls.
        QtWidgets.QApplication.instance().installEventFilter(self)

    def setWidget(self, widget):
        super().setWidget(widget)
        self.setMouseTracking(True)
        for child in [widget] + widget.findChildren(QtWidgets.QWidget):
            child.setMouseTracking(True)

    def _cornerAt(self, globalPoint):
        if not self.isFloating() and not self._fullscreenOverlay:
            return None
        point = self.mapFromGlobal(globalPoint)
        reach = max(24, self.cornerRadius + 4)
        horizontal = -1 if point.x() < reach else (1 if point.x() >= self.width() - reach else 0)
        vertical = -1 if point.y() < reach else (1 if point.y() >= self.height() - reach else 0)
        return (horizontal, vertical) if horizontal and vertical else None

    def _resizeToPointer(self, globalPoint):
        rect = self._resizeOrigin
        delta = globalPoint - self._press
        x = self._resizeCorner[0] * delta.x() / rect.width()
        y = self._resizeCorner[1] * delta.y() / rect.height()
        factor = 1 + (x if abs(x) > abs(y) else y)
        minimum = 0.5 / self._resizeStartScale
        maximum = 2.0 / self._resizeStartScale
        if self.screen():
            maximum = min(maximum, (self.screen().availableGeometry().height() - 40) / rect.height())
        factor = max(minimum, min(maximum, factor))
        size = QtCore.QSize(round(rect.width() * factor), round(rect.height() * factor))
        self.cornerResizeRequested.emit(size)
        left = rect.x() if self._resizeCorner[0] > 0 else rect.x() + rect.width() - self.width()
        top = rect.y() if self._resizeCorner[1] > 0 else rect.y() + rect.height() - self.height()
        self.move(left, top)

    def _updateShape(self, *_args):
        outline = QtGui.QPainterPath()
        outline.addRoundedRect(QtCore.QRectF(self.rect()), self.cornerRadius, self.cornerRadius)
        self.setMask(QtGui.QRegion(outline.toFillPolygon().toPolygon()))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._updateShape()

    def showEvent(self, event):
        super().showEvent(event)
        self._updateShape()

    def _finishDrag(self):
        dragging = self._dragging or self._resizing
        self._resizing = False
        self._press = None
        self._dragging = False
        self._pressedButton = None
        if QtWidgets.QWidget.mouseGrabber() is self:
            self.releaseMouse()
        return dragging

    def eventFilter(self, watched, event):
        kind = event.type()
        if watched is self and kind == QtCore.QEvent.Hide and not self._changingWindows:
            self._finishDrag()
        if kind == QtCore.QEvent.MouseMove and self._press is None:
            if isinstance(watched, QtWidgets.QWidget) and (watched is self or self.isAncestorOf(watched)):
                corner = self._cornerAt(event.globalPos())
                if corner:
                    cursor = QtCore.Qt.SizeFDiagCursor if corner[0] == corner[1] else QtCore.Qt.SizeBDiagCursor
                    watched.setCursor(cursor)
                    self.setCursor(cursor)
                else:
                    watched.unsetCursor()
                    self.unsetCursor()
        if kind == QtCore.QEvent.MouseButtonPress and event.button() == QtCore.Qt.LeftButton:
            if not isinstance(watched, QtWidgets.QWidget):
                return False
            if watched is not self and not self.isAncestorOf(watched):
                return False
            # Scrollbar gestures retain their normal behavior.
            if isinstance(watched, QtWidgets.QScrollBar):
                return False
            corner = self._cornerAt(event.globalPos())
            if corner and self._press is None:
                self._press = event.globalPos()
                self._resizing = True
                self._resizeCorner = corner
                self._resizeOrigin = self.geometry()
                self._resizeStartScale = self.resizeScale
                self.grabMouse()
                return True
            # Ignored presses propagate through parents; keep the original
            # target and global anchor instead of restarting the gesture.
            if self._press is None:
                self._press = event.globalPos()
                self._offset = self._press - self.mapToGlobal(QtCore.QPoint())
                self._pressedButton = watched if isinstance(watched, QtWidgets.QAbstractButton) else None
                self._dragging = False
        elif kind == QtCore.QEvent.MouseMove and self._press is not None:
            if not event.buttons() & QtCore.Qt.LeftButton:
                self._finishDrag()
                return False
            if self._resizing:
                self._resizeToPointer(event.globalPos())
                return True
            if not self._dragging:
                if (event.globalPos() - self._press).manhattanLength() < QtWidgets.QApplication.startDragDistance():
                    return False
                if self._pressedButton:
                    self._pressedButton.setDown(False)
                if not self.isFloating() and not self._fullscreenOverlay:
                    self._changingWindows = True
                    try:
                        self.setFloating(True)
                        self.show()
                    finally:
                        self._changingWindows = False
                self._dragging = True
                self.grabMouse()
            position = event.globalPos() - self._offset
            if self._fullscreenOverlay:
                position = self.parentWidget().mapFromGlobal(position)
            self.move(position)
            return True
        elif kind == QtCore.QEvent.MouseButtonRelease and event.button() == QtCore.Qt.LeftButton:
            if self._finishDrag():
                return True
        return False
