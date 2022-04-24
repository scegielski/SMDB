from PyQt5 import QtWidgets, QtCore


class MovieTableView(QtWidgets.QTableView):
    wheelSpun = QtCore.pyqtSignal(int)

    def wheelEvent(self, event):
        if event.modifiers() == QtCore.Qt.ControlModifier:
            self.wheelSpun.emit(event.angleDelta().y() / 120)
            event.accept()
        else:
            event.ignore()
            super().wheelEvent(event)
