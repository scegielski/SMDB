from PyQt5.QtWidgets import QOpenGLWidget
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QImage
from OpenGL.GL import *
from OpenGL.GLU import *
import numpy as np

class CoverFlowGLWidget(QOpenGLWidget):
    def _init_anim_queue(self):
        self._anim_queue = []

    def _store_prev_cover(self):
        self._prev_cover_image = self.cover_image
        self._prev_texture_id = self.texture_id

    def animate_cover_transition(self, direction):
        self._store_prev_cover()
        self._anim_direction = direction
        self._anim_progress = 0.0
        self._animating = True
        self._anim_timer = self.startTimer(16)  # ~60 FPS
        self.update()

    def timerEvent(self, event):
        if getattr(self, '_animating', False):
            self._anim_progress += 0.027
            if self._anim_progress >= 1.0:
                self._anim_progress = 1.0
                self._animating = False
                self.killTimer(self._anim_timer)
                self._prev_cover_image = None
                self._prev_texture_id = None
                self._process_anim_queue()  # Start next animation if queued
            self.update()
    wheelMovieChange = pyqtSignal(int)  # +1 for next, -1 for previous
    def wheelEvent(self, event):
        # Accumulate wheel delta and queue events for consistent animation speed
        if not hasattr(self, '_wheel_accum'):
            self._wheel_accum = 0
        self._wheel_accum += event.angleDelta().y()
        while self._wheel_accum >= 120:
            self._anim_queue.append(-1)
            self._wheel_accum -= 120
        while self._wheel_accum <= -120:
            self._anim_queue.append(1)
            self._wheel_accum += 120
        self._process_anim_queue()

    def _process_anim_queue(self):
        if getattr(self, '_animating', False):
            return  # Wait for current animation to finish
        if self._anim_queue:
            direction = self._anim_queue.pop(0)
            self.animate_cover_transition(direction)
            self.wheelMovieChange.emit(direction)
    def __init__(self, parent=None):
        super().__init__(parent)
        # Enable sample buffers for anti-aliasing
        fmt = self.format()
        fmt.setSamples(8)
        self.setFormat(fmt)
        self.cover_image = None
        self.texture_id = None
        self.y_rotation = 0.0
        self.last_mouse_x = None
        self.aspect_ratio = 1.0
        self._init_anim_queue()

    def set_cover_image(self, image_path):
        self.cover_image = QImage(image_path)
        self.texture_id = None  # Force recreation of texture for new image
        if not self.cover_image.isNull():
            self.aspect_ratio = self.cover_image.width() / self.cover_image.height()
        self.update()

    def initializeGL(self):
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_TEXTURE_2D)
        glEnable(GL_MULTISAMPLE)
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
        widget_w = self.width()
        widget_h = self.height()
        if widget_h == 0:
            widget_h = 1
        window_aspect = widget_w / widget_h
        cover_aspect = self.aspect_ratio
        max_quad_h = 1.0
        max_quad_w = window_aspect
        quad_h = max_quad_h
        quad_w = cover_aspect * quad_h
        if quad_w > max_quad_w:
            quad_w = max_quad_w
            quad_h = quad_w / cover_aspect
        import math
        fov_y = 30.0
        z = (quad_h / 2) / math.tan(math.radians(fov_y / 2))
        # Animation: dual covers
        if getattr(self, '_animating', False) and self._prev_cover_image is not None:
            progress = self._anim_progress
            smooth_progress = progress * progress * (3 - 2 * progress)
            direction = getattr(self, '_anim_direction', 1)
            # Outgoing cover offset
            if direction == 1:
                prev_y_offset = -(smooth_progress) * 2.0  # move up (outgoing goes up)
                curr_y_offset = (1.0 - smooth_progress) * 2.0  # move up from below (incoming comes up)
            else:
                prev_y_offset = smooth_progress * 2.0  # move down (outgoing goes down)
                curr_y_offset = -(1.0 - smooth_progress) * 2.0  # move down from above (incoming comes down)
            # Draw previous cover
            glPushMatrix()
            glTranslatef(0.0, prev_y_offset, -z)
            glRotatef(self.y_rotation, 0.0, 1.0, 0.0)
            if self._prev_texture_id is None and self._prev_cover_image and not self._prev_cover_image.isNull():
                self._prev_texture_id = self.createTextureFromQImage(self._prev_cover_image)
            if self._prev_texture_id:
                glBindTexture(GL_TEXTURE_2D, self._prev_texture_id)
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
            glPopMatrix()
            # Draw current cover
            glPushMatrix()
            glTranslatef(0.0, curr_y_offset, -z)
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
            glPopMatrix()
        else:
            # Normal render (single cover)
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
