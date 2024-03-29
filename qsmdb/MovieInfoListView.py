from PyQt5 import QtWidgets, QtCore


class MovieInfoListView(QtWidgets.QListWidget):
    wheelSpun = QtCore.pyqtSignal(int)

    def wheelEvent(self, event):
        if event.modifiers() == QtCore.Qt.ControlModifier:
            self.wheelSpun.emit(event.angleDelta().y() / 120)
            event.accept()
        else:
            event.ignore()
            super().wheelEvent(event)

    def mousePressEvent(self, event):
        if event.type() == QtCore.QEvent.MouseButtonPress:
            if event.button() == QtCore.Qt.RightButton:
                self.mouseLocation = event.pos()
                return
            else:
                super().mousePressEvent(event)
