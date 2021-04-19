from PyQt5 import QtGui, QtWidgets, QtCore

from .CoverGLObject import CoverGLObject


class CoverGLWidget(QtWidgets.QOpenGLWidget):
    coverChanged = QtCore.pyqtSignal(int)

    def __init__(self):
        super(QtWidgets.QOpenGLWidget, self).__init__()
        self.coverFile = str()
        self.cameraPosition = QtGui.QVector3D(0.0, 0.0, -4.0)
        self.cameraZoomAngle = 45.0
        self.coverVelocity = QtGui.QVector3D(0.0, 0.0, 0.0)
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.aspectRatio = self.width() / self.height()
        self.coverXBoundary = self.aspectRatio * 2.5 * (self.cameraZoomAngle / 45.0)
        self.drag = 0.97
        self.coverObjects = list()
        self.coverObjects.append(CoverGLObject(self.coverFile))
        self.viewMatrix = QtGui.QMatrix4x4()

    def setView(self):
        self.viewMatrix.setToIdentity()
        self.viewMatrix.perspective(
            self.cameraZoomAngle,  # Angle
            self.aspectRatio,
            0.1,  # Near clipping plane
            100.0,  # Far clipping plane
        )
        self.viewMatrix.translate(self.cameraPosition)

    def resizeGL(self, w: int, h: int) -> None:
        self.aspectRatio = self.width() / self.height()
        self.coverXBoundary = self.aspectRatio * 2.5 * (self.cameraZoomAngle / 45.0)
        self.setView()

    def keyPressEvent(self, a0: QtGui.QKeyEvent) -> None:
        if a0.key() == QtCore.Qt.Key_Home:
            self.cameraPosition = QtGui.QVector3D(0.0, 0.0, -4.0)
            self.cameraZoomAngle = 45.0
            for c in self.coverObjects:
                c.reset()

    def mousePressEvent(self, a0: QtGui.QMouseEvent) -> None:
        self.lastPos = a0.pos()

    def mouseMoveEvent(self, a0: QtGui.QMouseEvent) -> None:
        dx = a0.x() - self.lastPos.x()
        for c in self.coverObjects:
            c.setVelocity(QtGui.QVector3D(self.aspectRatio * dx * 0.01, 0.0, 0.0))
        self.lastPos = a0.pos()

    def wheelEvent(self, a0: QtGui.QWheelEvent) -> None:
        acceleration = QtGui.QVector3D()
        if a0.angleDelta().y() > 0:
            acceleration.setX(0.15 * self.aspectRatio)
        elif a0.angleDelta().y() < 0:
            acceleration.setX(-0.15 * self.aspectRatio)
        for c in self.coverObjects:
            c.addAcceleration(acceleration)

    def initializeGL(self) -> None:
        super().initializeGL()
        gl_context = self.context()
        version = QtGui.QOpenGLVersionProfile()
        version.setVersion(2, 1)
        self.gl = gl_context.versionFunctions(version)

        self.gl.glEnable(self.gl.GL_DEPTH_TEST)
        self.gl.glDepthFunc(self.gl.GL_LESS)
        self.gl.glEnable(self.gl.GL_CULL_FACE)

        for c in self.coverObjects:
            c.initGl()

        self.setView()

    def setTexture(self, coverFile):
        for c in self.coverObjects:
            c.setTexture(coverFile)

    def animate(self):
        for c in self.coverObjects:
            px = c.getPosition().x()
            if px > self.coverXBoundary:
                px = self.coverXBoundary * -1.0
                self.coverChanged.emit(1)
            elif px < self.coverXBoundary * -1.0:
                px = self.coverXBoundary
                self.coverChanged.emit(-1)
            c.setPosition(QtGui.QVector3D(px, 0.0, 0.0))
            c.animate(self.drag,
                      self.aspectRatio,
                      self.coverXBoundary)

    def paintGL(self) -> None:
        self.gl.glClearColor(0.0, 0.0, 0.0, 1.0)
        self.gl.glClear(self.gl.GL_COLOR_BUFFER_BIT | self.gl.GL_DEPTH_BUFFER_BIT)
        self.setView()
        self.animate()
        for c in self.coverObjects:
            c.draw(self.gl, self.viewMatrix)
        self.update()