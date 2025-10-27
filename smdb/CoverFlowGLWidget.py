from PyQt5.QtWidgets import QOpenGLWidget
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QImage
from OpenGL.GL import *
from OpenGL.GLU import *
import numpy as np

class CoverFlowGLWidget(QOpenGLWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.cover_image = None
        self.texture_id = None
        self.y_rotation = 0.0
        self.last_mouse_x = None
        self.aspect_ratio = 1.0

    def set_cover_image(self, image_path):
        self.cover_image = QImage(image_path)
        self.texture_id = None  # Force recreation of texture for new image
        if not self.cover_image.isNull():
            self.aspect_ratio = self.cover_image.width() / self.cover_image.height()
        self.update()

    def initializeGL(self):
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_TEXTURE_2D)
        glClearColor(0.0, 0.0, 0.0, 1.0)  # Pure black background
        self.texture_id = None

    def resizeGL(self, w, h):
        glViewport(0, 0, w, h)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        # Use a moderate FOV and set near/far for a good fit
        gluPerspective(30.0, w / h if h != 0 else 1, 0.1, 10.0)
        glMatrixMode(GL_MODELVIEW)

    def paintGL(self):
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glLoadIdentity()
        # Camera distance so quad fits window
        # Calculate scale so both width and height fit
        widget_w = self.width()
        widget_h = self.height()
        if widget_h == 0:
            widget_h = 1
        window_aspect = widget_w / widget_h
        cover_aspect = self.aspect_ratio
        # Find scale so both dimensions fit
        max_quad_h = 1.0
        max_quad_w = window_aspect
        quad_h = max_quad_h
        quad_w = cover_aspect * quad_h
        if quad_w > max_quad_w:
            quad_w = max_quad_w
            quad_h = quad_w / cover_aspect
        # Set camera z so quad fits (based on FOV)
        # FOV is 30 deg, so tan(15) = quad_h/2 / z => z = quad_h/2 / tan(15deg)
        import math
        fov_y = 30.0
        z = (quad_h / 2) / math.tan(math.radians(fov_y / 2))
        glTranslatef(0.0, 0.0, -z)
        glRotatef(self.y_rotation, 0.0, 1.0, 0.0)
        if self.cover_image and not self.cover_image.isNull():
            if self.texture_id is None:
                self.texture_id = self.createTextureFromQImage(self.cover_image)
            glBindTexture(GL_TEXTURE_2D, self.texture_id)
            glBegin(GL_QUADS)
            glTexCoord2f(0.0, 1.0)
            glVertex3f(-quad_w/2, -quad_h/2, 0.0)
            glTexCoord2f(1.0, 1.0)
            glVertex3f(quad_w/2, -quad_h/2, 0.0)
            glTexCoord2f(1.0, 0.0)
            glVertex3f(quad_w/2, quad_h/2, 0.0)
            glTexCoord2f(0.0, 0.0)
            glVertex3f(-quad_w/2, quad_h/2, 0.0)
            glEnd()

    def createTextureFromQImage(self, qimage):
        qimage = qimage.convertToFormat(QImage.Format_RGBA8888)
        width = qimage.width()
        height = qimage.height()
        ptr = qimage.bits()
        ptr.setsize(qimage.byteCount())
        data = np.array(ptr, dtype=np.uint8).reshape((height, width, 4))
        texture_id = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D, texture_id)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, width, height, 0, GL_RGBA, GL_UNSIGNED_BYTE, data)
        return texture_id

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.last_mouse_x = event.x()

    def mouseMoveEvent(self, event):
        if self.last_mouse_x is not None:
            dx = event.x() - self.last_mouse_x
            self.y_rotation += dx * 0.5
            self.last_mouse_x = event.x()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.last_mouse_x = None
