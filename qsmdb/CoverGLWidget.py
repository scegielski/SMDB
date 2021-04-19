from PyQt5 import QtGui, QtWidgets, QtCore

def qcolor_to_glvec(qcolor):
    return QtGui.QVector3D(
        qcolor.red() / 255,
        qcolor.green() / 255,
        qcolor.blue() / 255
    )

class CoverGLObject:
    def __init__(self, textureFile):
        pass




class CoverGLWidget(QtWidgets.QOpenGLWidget):
    coverChanged = QtCore.pyqtSignal(int)

    def __init__(self):
        super(QtWidgets.QOpenGLWidget, self).__init__()
        self.coverFile = str()
        self.cameraPosition = QtGui.QVector3D(0.0, 0.0, -4.0)
        self.cameraZoomAngle = 45.0
        self.coverRotationAngle = 0
        self.coverPosition = QtGui.QVector3D(0.0, 0.0, 0.0)
        self.coverVelocity = QtGui.QVector3D(0.0, 0.0, 0.0)
        self.coverXBoundary = 1.0
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.aspectRatio = self.width() / self.height()

    def setView(self):
        self.viewMatrix = QtGui.QMatrix4x4()
        self.viewMatrix.perspective(
            self.cameraZoomAngle, # Angle
            self.aspectRatio,
            0.1, # Near clipping plane
            100.0, # Far clipping plane
        )
        self.viewMatrix.translate(self.cameraPosition)

        self.coverXBoundary = self.aspectRatio * 2.5 * (self.cameraZoomAngle / 45.0)

    def keyPressEvent(self, a0: QtGui.QKeyEvent) -> None:
        if a0.key() == QtCore.Qt.Key_Home:
            self.cameraPosition = QtGui.QVector3D(0.0, 0.0, -4.0)
            self.cameraZoomAngle = 45.0
            self.coverPosition = QtGui.QVector3D(0.0, 0.0, 0.0)
            self.coverVelocity = QtGui.QVector3D(0.0, 0.0, 0.0)
            self.coverRotationAngle = 0

    def mousePressEvent(self, a0: QtGui.QMouseEvent) -> None:
        self.lastPos = a0.pos()

    def mouseMoveEvent(self, a0: QtGui.QMouseEvent) -> None:
        dx = a0.x() - self.lastPos.x()
        self.coverVelocity.setX(self.aspectRatio * dx * 0.01)
        self.lastPos = a0.pos()

    def wheelEvent(self, a0: QtGui.QWheelEvent) -> None:
        if a0.angleDelta().y() > 0:
            self.coverVelocity.setX(self.coverVelocity.x() + 0.15 * self.aspectRatio)
        elif a0.angleDelta().y() < 0:
            self.coverVelocity.setX(self.coverVelocity.x() - 0.15 * self.aspectRatio)

    def initializeGL(self) -> None:
        super().initializeGL()
        gl_context = self.context()
        version = QtGui.QOpenGLVersionProfile()
        version.setVersion(2, 1)
        self.gl = gl_context.versionFunctions(version)

        self.gl.glEnable(self.gl.GL_DEPTH_TEST)
        self.gl.glDepthFunc(self.gl.GL_LESS)
        self.gl.glEnable(self.gl.GL_CULL_FACE)

        self.program = QtGui.QOpenGLShaderProgram()
        self.program.addShaderFromSourceFile(QtGui.QOpenGLShader.Vertex, 'qsmdb/cover_vertex_shader.glsl')
        self.program.addShaderFromSourceFile(QtGui.QOpenGLShader.Fragment, 'qsmdb/cover_fragment_shader.glsl')
        self.program.link()
        self.program.bind()
        self.program.setUniformValue('texture', 0)

        self.vertexLocation = self.program.attributeLocation('vertex')
        self.matrixLocation = self.program.uniformLocation('matrix')
        self.colorLocation = self.program.attributeLocation('color_attr')
        self.textureCoordinatesLocation = self.program.attributeLocation('texture_coordinates')

        if self.coverFile:
            self.coverTexture = QtGui.QOpenGLTexture(QtGui.QImage(self.coverFile))
        else:
            image = QtGui.QPixmap(10, 10).toImage()
            self.coverTexture = QtGui.QOpenGLTexture(image)

        self.coverTexture.setMaximumAnisotropy(16)
        self.coverTexture.setMagnificationFilter(QtGui.QOpenGLTexture.Linear)

        self.setView()

    def setTexture(self, coverFile):
        self.coverFile = coverFile
        self.coverTexture = QtGui.QOpenGLTexture(QtGui.QImage(coverFile))
        self.coverTexture.setMaximumAnisotropy(16)

    def resizeGL(self, w: int, h: int) -> None:
        self.aspectRatio = self.width() / self.height()
        self.setView()

    def drawCover(self, translation: QtGui.QVector3D, angle: float, axis: QtGui.QVector3D) -> None:

        front_vertices = [
            QtGui.QVector3D(-1.0, 1.5, 0.0),
            QtGui.QVector3D(1.0, 1.5, 0.0),
            QtGui.QVector3D(1.0, -1.5, 0.0),
            QtGui.QVector3D(-1.0, -1.5, 0.0)
        ]

        front_texture_coordinates = [
            QtGui.QVector2D(1.0, 0.0),
            QtGui.QVector2D(0.0, 0.0),
            QtGui.QVector2D(0.0, 1.0),
            QtGui.QVector2D(1.0, 1.0)
        ]

        back_texture_coordinates = [
            QtGui.QVector2D(0.0, 1.0),
            QtGui.QVector2D(1.0, 1.0),
            QtGui.QVector2D(1.0, 0.0),
            QtGui.QVector2D(0.0, 0.0)
        ]

        # Bind the texture
        self.coverTexture.bind()

        # Enable locations and texture coordinates
        self.program.enableAttributeArray(self.vertexLocation)
        self.program.enableAttributeArray(self.textureCoordinatesLocation)

        self.gl.glPushMatrix()
        self.viewMatrix.translate(translation)
        self.viewMatrix.rotate(angle, axis)

        self.program.setUniformValue(self.matrixLocation, self.viewMatrix)

        # Draw the front
        self.program.setAttributeArray(self.vertexLocation, front_vertices)
        self.program.setAttributeArray(self.textureCoordinatesLocation, front_texture_coordinates)
        self.gl.glDrawArrays(self.gl.GL_QUADS, 0, 4)

        # Draw the back
        self.program.setAttributeArray(self.vertexLocation, reversed(front_vertices))
        self.program.setAttributeArray(self.textureCoordinatesLocation, back_texture_coordinates)
        self.gl.glDrawArrays(self.gl.GL_QUADS, 0, 4)

        self.gl.glPopMatrix()

    def paintGL(self) -> None:
        self.gl.glClearColor(0.0, 0.0, 0.0, 1.0)
        self.gl.glClear(
            self.gl.GL_COLOR_BUFFER_BIT | self.gl.GL_DEPTH_BUFFER_BIT
        )
        self.program.bind()

        # Draw the cover

        px = self.coverPosition.x()
        if px > self.coverXBoundary:
            px = self.coverXBoundary * -1.0
            self.coverChanged.emit(1)
        elif px < self.coverXBoundary * -1.0:
            px = self.coverXBoundary
            self.coverChanged.emit(-1)
        self.coverPosition.setX(px + self.coverVelocity.x())

        # Rotate when in this zone
        minX = 0.1
        maxX = 0.75
        ratio = abs(px) / self.coverXBoundary
        # remap minX..maxX to 0..1
        t = min(1.0, max(0.0, (ratio - minX) / (maxX - minX)))
        # ease in
        t = t * t

        self.coverRotationAngle = t * -90.0
        if px < 0: self.coverRotationAngle *= -1.0
        axis = QtGui.QVector3D(0.0, 1.0, 0.0)

        self.drawCover(self.coverPosition, self.coverRotationAngle, axis)
        self.coverVelocity *= 0.97

        if self.coverVelocity.length() < 0.025:
            if self.coverPosition.x() > 0.01:
                self.coverVelocity.setX(self.coverVelocity.x() - 0.001 * self.aspectRatio)
            elif self.coverPosition.x() < -0.01:
                self.coverVelocity.setX(self.coverVelocity.x() + 0.001 * self.aspectRatio)
            else:
                self.coverVelocity *= 0.0

        self.program.disableAttributeArray(self.vertexLocation)
        self.program.disableAttributeArray(self.colorLocation)
        self.program.release()

        self.setView()
        self.update()
