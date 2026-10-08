"""Composited Qt video view, allowing captions to paint over video frames."""
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtMultimediaWidgets import QGraphicsVideoItem


class VideoView(QtWidgets.QGraphicsView):
    def __init__(self, parent=None):
        super().__init__(parent)
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
