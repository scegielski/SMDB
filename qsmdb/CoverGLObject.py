from PyQt5 import QtGui, QtWidgets, QtCore

class CoverGLObject:
    def __init__(self, textureFile):
        self.vertexShader = 'qsmdb/cover_vertex_shader.glsl'
        self.fragmentShader = 'qsmdb/cover_fragment_shader.glsl'
        self.coverFile = textureFile

        self.position = QtGui.QVector3D(0.0, 0.0, 0.0)
        self.velocity = QtGui.QVector3D(0.0, 0.0, 0.0)
        self.rotationAngle = 0

        self.front_vertices = [
            QtGui.QVector3D(-1.0, 1.5, 0.0),
            QtGui.QVector3D(1.0, 1.5, 0.0),
            QtGui.QVector3D(1.0, -1.5, 0.0),
            QtGui.QVector3D(-1.0, -1.5, 0.0)
        ]

        self.front_texture_coordinates = [
            QtGui.QVector2D(1.0, 0.0),
            QtGui.QVector2D(0.0, 0.0),
            QtGui.QVector2D(0.0, 1.0),
            QtGui.QVector2D(1.0, 1.0)
        ]

        self.back_texture_coordinates = [
            QtGui.QVector2D(0.0, 1.0),
            QtGui.QVector2D(1.0, 1.0),
            QtGui.QVector2D(1.0, 0.0),
            QtGui.QVector2D(0.0, 0.0)
        ]

    def init(self):
        self.program = QtGui.QOpenGLShaderProgram()
        self.program.addShaderFromSourceFile(QtGui.QOpenGLShader.Vertex, self.vertexShader)
        self.program.addShaderFromSourceFile(QtGui.QOpenGLShader.Fragment, self.fragmentShader)
        self.program.link()
        self.program.bind()
        self.program.setUniformValue('texture', 0)

        self.vertexLocation = self.program.attributeLocation('vertex')
        self.matrixLocation = self.program.uniformLocation('matrix')
        self.colorLocation = self.program.attributeLocation('color_attr')
        self.textureCoordinatesLocation = self.program.attributeLocation('texture_coordinates')

        self.coverTexture = QtGui.QOpenGLTexture(QtGui.QImage(self.coverFile))
        self.coverTexture.setMaximumAnisotropy(16)
        self.coverTexture.setMagnificationFilter(QtGui.QOpenGLTexture.Linear)

    def setTexture(self, coverFile):
        self.coverFile = coverFile
        self.coverTexture = QtGui.QOpenGLTexture(QtGui.QImage(coverFile))
        self.coverTexture.setMaximumAnisotropy(16)

    def pushTowardsCenter(self, aspectRatio : float) -> None:
        v = self.velocity
        px = self.position.x()
        if v.length() < 0.025:
            if px > 0.01:
                self.addAcceleration(QtGui.QVector3D(-0.001 * aspectRatio, 0.0, 0.0))
            elif px < -0.01:
                self.addAcceleration(QtGui.QVector3D(0.001 * aspectRatio, 0.0, 0.0))
            else:
                v *= 0.0
                self.velocity = v

    def rotateByBoundry(self, boundary):
        # Rotate when in this zone
        minX = 0.1
        maxX = 0.75
        ratio = abs(self.position.x()) / boundary
        # remap minX..maxX to 0..1
        t = min(1.0, max(0.0, (ratio - minX) / (maxX - minX)))
        # ease in
        t = t * t

        self.rotationAngle = t * -90.0
        if self.position.x() < 0:
            self.rotationAngle *= -1.0

    def animate(self, drag, aspectRatio, boundary : float) -> None:
        self.position += self.velocity
        self.pushTowardsCenter(aspectRatio)
        self.velocity *= drag
        self.rotateByBoundry(boundary)

    def reset(self):
        self.position = QtGui.QVector3D(0.0, 0.0, 0.0)
        self.velocity = QtGui.QVector3D(0.0, 0.0, 0.0)
        self.rotationAngle = 0.0

    def addAcceleration(self, acceleration : QtGui.QVector3D) -> None:
        self.velocity += acceleration

    def setVelocity(self, velocity : QtGui.QVector3D) -> None:
        self.velocity = velocity

    def getVelocity(self):
        return self.velocity

    def getPosition(self):
        return self.position

    def setPosition(self, position : QtGui.QVector3D) -> None:
        self.position = position

    def getRotationAngle(self):
        return self.rotationAngle

    def setRotationAngle(self, angle):
        self.rotationAngle = angle

    def draw(self, gl, viewMatrix : QtGui.QMatrix4x4) -> None:
        # Bind the shader programs
        self.program.bind()

        # Bind the texture
        self.coverTexture.bind()

        # Enable locations and texture coordinates
        self.program.enableAttributeArray(self.vertexLocation)
        self.program.enableAttributeArray(self.textureCoordinatesLocation)

        gl.glPushMatrix()

        # Set the object transformation
        objectMatrix = QtGui.QMatrix4x4()
        objectMatrix.translate(self.position)
        axis = QtGui.QVector3D(0.0, 1.0, 0.0)
        objectMatrix.rotate(self.rotationAngle, axis)
        viewMatrix *= objectMatrix
        self.program.setUniformValue(self.matrixLocation, viewMatrix)

        # Draw the front
        self.program.setAttributeArray(self.vertexLocation, self.front_vertices)
        self.program.setAttributeArray(self.textureCoordinatesLocation, self.front_texture_coordinates)
        gl.glDrawArrays(gl.GL_QUADS, 0, 4)

        # Draw the back
        self.program.setAttributeArray(self.vertexLocation, reversed(self.front_vertices))
        self.program.setAttributeArray(self.textureCoordinatesLocation, self.back_texture_coordinates)
        gl.glDrawArrays(gl.GL_QUADS, 0, 4)

        gl.glPopMatrix()

        self.program.disableAttributeArray(self.vertexLocation)
        self.program.disableAttributeArray(self.colorLocation)
        self.program.release()