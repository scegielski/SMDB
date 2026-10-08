"""Titleless TV remote with click-preserving surface dragging."""
from PyQt5 import QtCore, QtWidgets


class RemoteDock(QtWidgets.QDockWidget):
    def __init__(self, parent):
        super().__init__('SMTV Remote', parent)
        self.setObjectName('smtvRemoteDock')
        self.setAllowedAreas(QtCore.Qt.RightDockWidgetArea)
        self.setFeatures(self.DockWidgetMovable | self.DockWidgetFloatable)
        title = QtWidgets.QWidget(self)
        title.setFixedHeight(0)
        self.setTitleBarWidget(title)
        self._press = None
        self._dragging = False
        self._pressedButton = None
        self._changingWindows = False
        # Observe the whole gesture, including moves delivered to another child
        # or outside the remote. This also covers dynamically created controls.
        QtWidgets.QApplication.instance().installEventFilter(self)

    def _finishDrag(self):
        dragging = self._dragging
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
        if kind == QtCore.QEvent.MouseButtonPress and event.button() == QtCore.Qt.LeftButton:
            if not isinstance(watched, QtWidgets.QWidget):
                return False
            if watched is not self and not self.isAncestorOf(watched):
                return False
            # Scrollbar gestures retain their normal behavior.
            if isinstance(watched, QtWidgets.QScrollBar):
                return False
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
            if not self._dragging:
                if (event.globalPos() - self._press).manhattanLength() < QtWidgets.QApplication.startDragDistance():
                    return False
                if self._pressedButton:
                    self._pressedButton.setDown(False)
                if not self.isFloating():
                    self._changingWindows = True
                    try:
                        self.setFloating(True)
                        self.show()
                    finally:
                        self._changingWindows = False
                self._dragging = True
                self.grabMouse()
            self.move(event.globalPos() - self._offset)
            return True
        elif kind == QtCore.QEvent.MouseButtonRelease and event.button() == QtCore.Qt.LeftButton:
            if self._finishDrag():
                return True
        return False
