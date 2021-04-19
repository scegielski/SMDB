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
        self.coverXBoundary = 1.0
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.aspectRatio = self.width() / self.height()

    def setView(self):
        self.viewMatrix = QtGui.QMatrix4x4()
        self.viewMatrix.perspective(
            self.cameraZoomAngle,  # Angle
            self.aspectRatio,
            0.1,  # Near clipping plane
            100.0,  # Far clipping plane
        )
        self.viewMatrix.translate(self.cameraPosition)

        self.coverXBoundary = self.aspectRatio * 2.5 * (self.cameraZoomAngle / 45.0)

    def keyPressEvent(self, a0: QtGui.QKeyEvent) -> None:
        if a0.key() == QtCore.Qt.Key_Home:
            self.cameraPosition = QtGui.QVector3D(0.0, 0.0, -4.0)
            self.cameraZoomAngle = 45.0
            self.coverObject.setPosition(QtGui.QVector3D(0.0, 0.0, 0.0))
            self.coverObject.setVelocity(QtGui.QVector3D(0.0, 0.0, 0.0))
            self.coverObject.setRotationAngle(0)

    def mousePressEvent(self, a0: QtGui.QMouseEvent) -> None:
        self.lastPos = a0.pos()

    def mouseMoveEvent(self, a0: QtGui.QMouseEvent) -> None:
        dx = a0.x() - self.lastPos.x()
        coverVelocity = self.coverObject.getVelocity()
        coverVelocity.setX(self.aspectRatio * dx * 0.01)
        self.coverObject.setVelocity(coverVelocity)
        self.lastPos = a0.pos()

    def wheelEvent(self, a0: QtGui.QWheelEvent) -> None:
        coverVelocity = self.coverObject.getVelocity()
        if a0.angleDelta().y() > 0:
            coverVelocity.setX(coverVelocity.x() + 0.15 * self.aspectRatio)
        elif a0.angleDelta().y() < 0:
            coverVelocity.setX(coverVelocity.x() - 0.15 * self.aspectRatio)
        self.coverObject.setVelocity(coverVelocity)

    def initializeGL(self) -> None:
        super().initializeGL()
        gl_context = self.context()
        version = QtGui.QOpenGLVersionProfile()
        version.setVersion(2, 1)
        self.gl = gl_context.versionFunctions(version)

        self.gl.glEnable(self.gl.GL_DEPTH_TEST)
        self.gl.glDepthFunc(self.gl.GL_LESS)
        self.gl.glEnable(self.gl.GL_CULL_FACE)

        self.coverObject = CoverGLObject(self.coverFile)
        self.coverObject.init()

        self.setView()

    def setTexture(self, coverFile):
        self.coverObject.setTexture(coverFile)

    def resizeGL(self, w: int, h: int) -> None:
        self.aspectRatio = self.width() / self.height()
        self.setView()

    def paintGL(self) -> None:
        self.gl.glClearColor(0.0, 0.0, 0.0, 1.0)
        self.gl.glClear(
            self.gl.GL_COLOR_BUFFER_BIT | self.gl.GL_DEPTH_BUFFER_BIT
        )

        coverVelocity = self.coverObject.getVelocity()
        px = self.coverObject.getPosition().x()
        if px > self.coverXBoundary:
            px = self.coverXBoundary * -1.0
            self.coverChanged.emit(1)
        elif px < self.coverXBoundary * -1.0:
            px = self.coverXBoundary
            self.coverChanged.emit(-1)
        coverPosition = QtGui.QVector3D(px + coverVelocity.x(), 0.0, 0.0)
        self.coverObject.setPosition(coverPosition)

        # Rotate when in this zone
        minX = 0.1
        maxX = 0.75
        ratio = abs(px) / self.coverXBoundary
        # remap minX..maxX to 0..1
        t = min(1.0, max(0.0, (ratio - minX) / (maxX - minX)))
        # ease in
        t = t * t

        coverRotationAngle = t * -90.0
        if px < 0:
            coverRotationAngle *= -1.0

        self.coverObject.setRotationAngle(coverRotationAngle)

        coverVelocity *= 0.97

        if coverVelocity.length() < 0.025:
            if px > 0.01:
                coverVelocity.setX(coverVelocity.x() - 0.001 * self.aspectRatio)
            elif px < -0.01:
                coverVelocity.setX(coverVelocity.x() + 0.001 * self.aspectRatio)
            else:
                coverVelocity *= 0.0

        self.coverObject.setVelocity(coverVelocity)

        # Draw the cover
        self.coverObject.draw(self.gl, self.viewMatrix)

        self.setView()
        self.update()
