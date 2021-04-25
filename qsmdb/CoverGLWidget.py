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
        self.coverXBoundary = self.aspectRatio * 2.5 * (self.cameraZoomAngle / 45.0)
        self.drag = 0.95
        self.coverObjects = list()
        self.viewMatrix = QtGui.QMatrix4x4()
        self.positionX = 0

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
        self.coverXBoundary = self.aspectRatio * 2.2 * (self.cameraZoomAngle / 45.0)
        self.setView()

    def mousePressEvent(self, a0: QtGui.QMouseEvent) -> None:
        self.lastPos = a0.pos()

    def mouseMoveEvent(self, a0: QtGui.QMouseEvent) -> None:
        dx = 0.01 * (a0.x() - self.lastPos.x())
        self.positionX += dx
        self.lastPos = a0.pos()

    def mouseReleaseEvent(self, a0: QtGui.QMouseEvent) -> None:
        pass
        #dx = a0.x() - self.lastPos.x()
        #print(f"dx = {dx}")
        #self.lastPos = a0.pos()
        #if dx <= 0:
        #    print(f"dx <= 0")
        #    self.emitVelocity(-1)
        #else:
        #    print(f"dx > 0")
        #    self.emitVelocity(1)

    def wheelEvent(self, a0: QtGui.QWheelEvent) -> None:
        pass
        #if len(self.coverObjects) <= 2:
        #    if a0.angleDelta().y() <= 0:
        #        self.coverChanged.emit(-1)
        #    else:
        #        self.coverChanged.emit(1)
        #else:
        #    if a0.angleDelta().y() <= 0:
        #        self.emitVelocity(-1)
        #    else:
        #        self.emitVelocity(1)

    def quantize(self, input, qt):
        return qt * round(input * (1/qt))

    def emitCover(self, coverFile, direction=1):
        e = 0.01 # x offset epsilon from boundaries
        cb = self.coverXBoundary
        print("\n")
        print(f"direction={direction}")
        print(f"cb = {cb}")
        x = -cb + e if direction == 1 else cb - e
        coverOffsetX = self.quantize(x - self.positionX, 0.1)
        x = self.positionX + coverOffsetX
        print(f"coverOffsetX = {coverOffsetX}")
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
        # Move the covers
        for cover in self.coverObjects:
            self.rotateByBoundary(cover)
            px = self.positionX + cover.offsetX
            cover.position = QtGui.QVector3D(px, 0.0, 0.0)

            # Remove covers at the window boundaries
            if px > self.coverXBoundary:
                self.coverObjects.remove(cover)
                self.coverChanged.emit(1)
            elif px < self.coverXBoundary * -1.0:
                self.coverObjects.remove(cover)
                self.coverChanged.emit(-1)

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