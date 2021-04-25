from PyQt5 import QtGui, QtWidgets, QtCore

class CoverGLObject:
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

    vertexShader = 'qsmdb/cover_vertex_shader.glsl'
    fragmentShader = 'qsmdb/cover_fragment_shader.glsl'

    def __init__(self,
                 textureFile: str,
                 position: QtGui.QVector3D,
                 offsetX: float):
        self.coverFile = textureFile
        self.position = position
        self.lastPosition = position
        self.offsetX = offsetX
        self.rotationAngle = 0
        self.emit = True

    def initGl(self):
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
        self.program.setUniformValue(self.matrixLocation, viewMatrix * objectMatrix)

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