from PyQt5 import QtGui, QtWidgets, QtCore


class MovieCover(QtWidgets.QLabel):

    doubleClicked = QtCore.pyqtSignal()
    wheelSpun = QtCore.pyqtSignal(int)

    def __init__(self):
        super(MovieCover, self).__init__()

    def mouseDoubleClickEvent(self, a0: QtGui.QMouseEvent) -> None:
        self.doubleClicked.emit()

    def wheelEvent(self, event):
        dy = event.angleDelta().y()
        self.wheelSpun.emit(1 if dy > 0 else (-1 if dy < 0 else 0))
        event.accept()
