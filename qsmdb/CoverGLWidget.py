from PyQt5 import QtGui, QtWidgets, QtCore
import math

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
        self.drag = 0.95
        self.coverObjects = list()
        self.viewMatrix = QtGui.QMatrix4x4()
        self.positionX = 0
        self.coverSpacing = 1.0
        self.coverXBoundary = self.quantize(self.aspectRatio * 2.2 * (self.cameraZoomAngle / 45.0), self.coverSpacing)
        self.vX = 0
        self.drag = 0.95

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
        self.coverXBoundary = self.quantize(self.aspectRatio * 2.2 * (self.cameraZoomAngle / 45.0), self.coverSpacing)
        self.setView()

    def mousePressEvent(self, a0: QtGui.QMouseEvent) -> None:
        self.lastPos = a0.pos()

    def mouseMoveEvent(self, a0: QtGui.QMouseEvent) -> None:
        maxDx = 0.5
        dx = max(-maxDx, min(maxDx, 0.0025 * (a0.x() - self.lastPos.x())))
        self.positionX += dx
        self.vX = dx
        self.lastPos = a0.pos()

    def wheelEvent(self, a0: QtGui.QWheelEvent) -> None:
        if a0.angleDelta().y() <= 0:
            self.vX = -0.1
        else:
            self.vX = 0.1

    def quantize(self, input, qt):
        return qt * round(input * (1/qt))

    def emitCover(self, coverFile, direction=1):
        x = -self.coverXBoundary if direction == 1 else self.coverXBoundary
        coverOffsetX = self.quantize(x - self.positionX, self.coverSpacing)

        # Don't emit if another cover is at the same offsetX
        for c in self.coverObjects:
            if abs(c.offsetX - coverOffsetX) < 0.01:
                return

        x = self.positionX + coverOffsetX
        coverPosition = QtGui.QVector3D(x, 0.0, 0.0)
        self.createCover(coverFile, coverPosition, coverOffsetX)

    def createCover(self, coverFile, position, offset):
        cover = CoverGLObject(coverFile, position, offset)
        cover.initGl()
        self.rotateByBoundary(cover)
        self.coverObjects.append(cover)

    def pushTowardsCenter(self, speedThreshold=0.025, deadZone=0.01):
        speed = self.velocity.length()
        if 0.0 < speed < speedThreshold:
            for cover in self.coverObjects:
                px = cover.position.x()
                if px > deadZone:
                    self.velocity += QtGui.QVector3D(-0.001 * self.aspectRatio, 0.0, 0.0)
                elif px < -deadZone:
                    self.velocity += QtGui.QVector3D(0.001 * self.aspectRatio, 0.0, 0.0)
                else:
                    self.velocity *= 0.0

    def rotateByBoundary(self, cover):
        # Rotate when in this zone
        minX = 0.1
        maxX = 0.75
        ratio = abs(cover.position.x()) / self.coverXBoundary
        # remap minX..maxX to 0..1
        t = min(1.0, max(0.0, (ratio - minX) / (maxX - minX)))
        # ease in
        t = t * t

        cover.rotationAngle = t * -90.0
        if cover.position.x() < 0:
            cover.rotationAngle *= -1.0

    def animate(self):
        self.positionX += self.vX
        self.vX *= self.drag

        # Move the covers
        for i, cover in enumerate(self.coverObjects):
            self.rotateByBoundary(cover)
            px = self.positionX + cover.offsetX
            cover.position = QtGui.QVector3D(px, 0.0, 0.0)

            # Remove covers at the window boundaries
            if px > self.coverXBoundary + 0.1:
                self.coverObjects.remove(cover)
                if len(self.coverObjects) == 0:
                    self.coverChanged.emit(1)
            elif px < self.coverXBoundary * -1.0 - 0.1:
                self.coverObjects.remove(cover)
                if len(self.coverObjects) == 0:
                    self.coverChanged.emit(-1)

            lastPx = cover.lastPosition.x()
            emitX = self.coverXBoundary - self.coverSpacing * 2.0
            if lastPx >= emitX and px < emitX:
                self.coverChanged.emit(-1)
            elif lastPx <= -emitX and px > -emitX:
                self.coverChanged.emit(1)

            cover.lastPosition = cover.position

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

    def paintGL(self) -> None:
        self.gl.glClearColor(0.0, 0.0, 0.0, 1.0)
        self.gl.glClear(self.gl.GL_COLOR_BUFFER_BIT | self.gl.GL_DEPTH_BUFFER_BIT)
        self.setView()
        self.animate()
        for c in self.coverObjects:
            c.draw(self.gl, self.viewMatrix)
        self.update()