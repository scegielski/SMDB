"""Present native DLSS GPU textures through Qt's composited OpenGL widget."""
import ctypes
import os
from pathlib import Path
from PyQt5 import QtCore, QtGui, QtWidgets
from OpenGL import GL


class DlssGpuView(QtWidgets.QOpenGLWidget):
    def __init__(self, parent):
        super().__init__(parent)
        format = QtGui.QSurfaceFormat()
        format.setVersion(2, 1)
        format.setProfile(QtGui.QSurfaceFormat.CompatibilityProfile)
        self.setFormat(format)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
        self.helperPath = Path(__file__).parent / 'native' / 'dlss_interop.dll'
        self._helper = None
        self._surface = None
        self._texture = 0
        self._name = None
        self._size = None
        self.error = None
        self.hide()

    def supported(self):
        return os.name == 'nt' and self.helperPath.is_file()

    def initializeGL(self):
        try:
            self._helper = ctypes.CDLL(str(self.helperPath))
            self._helper.DlssInteropAvailable.restype = ctypes.c_bool
            self._helper.DlssInteropError.restype = ctypes.c_char_p
            self._helper.DlssInteropOpen.argtypes = [ctypes.c_wchar_p, ctypes.c_uint]
            self._helper.DlssInteropOpen.restype = ctypes.c_void_p
            self._helper.DlssInteropClose.argtypes = [ctypes.c_void_p]
            self._helper.DlssInteropCopy.argtypes = [ctypes.c_void_p]
            for name in ('DlssInteropLock', 'DlssInteropUnlock'):
                getattr(self._helper, name).argtypes = [ctypes.c_void_p]
                getattr(self._helper, name).restype = ctypes.c_bool
            if not self._helper.DlssInteropAvailable():
                raise RuntimeError('Desktop NVIDIA OpenGL/D3D interop is unavailable')
            self.context().aboutToBeDestroyed.connect(self._cleanup)
        except Exception as error:
            self.error = str(error)

    def present(self, name, width, height):
        self.show()
        self.makeCurrent()
        try:
            if self.error or self._helper is None:
                raise RuntimeError(self.error or 'OpenGL presentation context is unavailable')
            if name != self._name:
                if self._surface:
                    self._helper.DlssInteropClose(self._surface)
                    self._surface = None
                if self._texture:
                    GL.glDeleteTextures([self._texture])
                self._texture = int(GL.glGenTextures(1))
                GL.glBindTexture(GL.GL_TEXTURE_2D, self._texture)
                self._surface = self._helper.DlssInteropOpen(name, self._texture)
                if not self._surface:
                    raise RuntimeError(self._helper.DlssInteropError().decode(errors='replace'))
                self._name = name
            self._size = (width, height)
            self._helper.DlssInteropCopy(self._surface)
        finally:
            self.doneCurrent()
        # Complete consumption before the worker overwrites the shared texture.
        self.repaint()
        if self.error:
            raise RuntimeError(self.error)

    def paintGL(self):
        GL.glClearColor(0, 0, 0, 1)
        GL.glClear(GL.GL_COLOR_BUFFER_BIT)
        if not self._surface or not self._size:
            return
        if not self._helper.DlssInteropLock(self._surface):
            self.error = 'Could not lock the DLSS GPU texture'
            return
        try:
            ratio = self.devicePixelRatioF()
            w, h = max(1, round(self.width()*ratio)), max(1, round(self.height()*ratio))
            GL.glViewport(0, 0, w, h)
            sw, sh = self._size
            scale = min(w/sw, h/sh)
            x, y = sw*scale/w, sh*scale/h
            GL.glMatrixMode(GL.GL_PROJECTION); GL.glLoadIdentity()
            GL.glMatrixMode(GL.GL_MODELVIEW); GL.glLoadIdentity()
            GL.glEnable(GL.GL_TEXTURE_2D)
            GL.glBindTexture(GL.GL_TEXTURE_2D, self._texture)
            GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MIN_FILTER, GL.GL_LINEAR)
            GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_LINEAR)
            GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_S, GL.GL_CLAMP_TO_EDGE)
            GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_T, GL.GL_CLAMP_TO_EDGE)
            GL.glColor4f(1, 1, 1, 1)
            GL.glBegin(GL.GL_QUADS)
            for tx, ty, vx, vy in ((0,1,-x,-y),(1,1,x,-y),(1,0,x,y),(0,0,-x,y)):
                GL.glTexCoord2f(tx,ty); GL.glVertex2f(vx,vy)
            GL.glEnd()
            GL.glDisable(GL.GL_TEXTURE_2D)
            GL.glFinish()
        except Exception as error:
            self.error = str(error)
        finally:
            self._helper.DlssInteropUnlock(self._surface)

    def _cleanup(self):
        self.makeCurrent()
        if self._surface and self._helper:
            self._helper.DlssInteropClose(self._surface)
            self._surface = None
        if self._texture:
            GL.glDeleteTextures([self._texture])
            self._texture = 0
        self._name = None
        self.doneCurrent()
