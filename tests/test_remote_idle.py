import unittest
from unittest.mock import patch
from PyQt5 import QtCore, QtGui, QtWidgets
from smdb.RetroChannelWidget import RetroChannelWidget


class RemoteIdleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.tv = RetroChannelWidget()
        self.tv.resize(1100, 900)
        self.tv.show()
        self.app.processEvents()
        self.tv.remoteIdleTimer.stop()
        self.point = QtGui.QCursor.pos()
        self.tv._remoteMousePosition = self.point

    def tearDown(self):
        if self.tv.isFullScreenActive:
            self.tv._exitFullScreen()
        self.tv.close()
        self.tv.deleteLater()
        self.app.processEvents()

    def tick(self, now, moved=False):
        point = self.point + QtCore.QPoint(10, 0) if moved else self.point
        with patch('smdb.RetroChannelWidget.time.monotonic', return_value=now), patch.object(QtGui.QCursor, 'pos', return_value=point):
            self.tv._pollRemoteActivity()

    def test_five_seconds_then_mouse_restores_docked_and_floating(self):
        for floating in (False, True):
            self.tv.controlsDock.setFloating(floating)
            self.tv.controlsDock.show()
            self.tv._remoteMousePosition = self.point
            self.tv._remoteLastActivity = 100
            self.tick(104.9)
            self.assertTrue(self.tv.controlsDock.isVisible())
            self.tick(105)
            self.assertTrue(self.tv.controlsDock.isHidden())
            self.tick(106, moved=True)
            self.assertTrue(self.tv.controlsDock.isVisible())
            self.assertEqual(self.tv.controlsDock.isFloating(), floating)

    def test_drag_and_dialog_protect_remote_and_mode_exit_stops_timer(self):
        self.tv._remoteLastActivity = 100
        self.tv.controlsDock._press = self.point
        self.tick(106)
        self.assertTrue(self.tv.controlsDock.isVisible())
        self.tv.controlsDock._press = None
        dialog = QtWidgets.QDialog(self.tv)
        with patch.object(QtWidgets.QApplication, 'activeModalWidget', return_value=dialog):
            self.tick(112)
        self.assertTrue(self.tv.controlsDock.isVisible())
        self.tick(117)
        self.assertTrue(self.tv.controlsDock.isHidden())
        self.tv.hide()
        self.assertFalse(self.tv.remoteIdleTimer.isActive())
        self.tick(118, moved=True)
        self.assertTrue(self.tv.controlsDock.isHidden())

    def test_fullscreen_remote_overlays_video_and_restores_dock(self):
        self.tv._enterFullScreen()
        self.app.processEvents()
        self.assertTrue(self.tv.controlsDock.isVisible())
        self.assertTrue(self.tv.controlsDock._fullscreenOverlay)
        self.tv._remoteLastActivity = 95
        self.tick(100)
        self.assertTrue(self.tv.controlsDock.isHidden())
        self.tick(101, moved=True)
        self.assertTrue(self.tv.controlsDock.isVisible())
        self.assertTrue(self.tv.controlsDock._fullscreenOverlay)
        self.assertTrue(self.tv.nowPlayingLabel.isHidden())
        self.point = self.point + QtCore.QPoint(10, 0)
        self.tick(106)
        self.assertTrue(self.tv.controlsDock.isHidden())
        self.tv._exitFullScreen()
        self.app.processEvents()
        self.assertFalse(self.tv.controlsDock.isFloating())

    def test_fullscreen_remote_shares_video_window_and_is_top_child(self):
        self.tv._enterFullScreen()
        self.app.processEvents()
        dock = self.tv.controlsDock
        self.assertIs(dock.window(), self.tv.window())
        self.assertFalse(dock.isWindow())
        self.assertTrue(dock._fullscreenOverlay)
        self.assertTrue(self.tv.rect().contains(dock.geometry()))
        self.tv.overlayArea.raise_()
        self.tv._raiseFullscreenRemote()
        point = dock.mapTo(self.tv, dock.rect().center())
        child = self.tv.childAt(point)
        self.assertTrue(child is dock or dock.isAncestorOf(child))
        self.tv._exitFullScreen()
        self.assertFalse(dock._fullscreenOverlay)
        self.assertFalse(dock.isFloating())

    def test_video_mouse_events_restore_remote_without_global_cursor_change(self):
        from smdb.VideoView import VideoView
        video = VideoView(self.tv)
        video.resize(300, 200)
        video.show()
        self.tv._enterFullScreen()
        self.app.processEvents()
        self.tv._remoteLastActivity = 100
        self.tick(105)
        self.assertTrue(self.tv.controlsDock.isHidden())
        with patch.object(QtGui.QCursor, 'pos', return_value=self.point):
            event = QtGui.QMouseEvent(QtCore.QEvent.MouseMove, QtCore.QPointF(80, 70),
                                     QtCore.Qt.NoButton, QtCore.Qt.NoButton, QtCore.Qt.NoModifier)
            QtWidgets.QApplication.sendEvent(video.viewport(), event)
        self.assertTrue(video.viewport().hasMouseTracking())
        self.assertTrue(self.tv.controlsDock.isVisible())
        self.assertIs(self.tv.controlsDock.window(), self.tv.window())

    def test_fullscreen_overlay_drag_keeps_remote_in_video_window(self):
        from PyQt5 import QtTest
        self.tv._enterFullScreen()
        self.app.processEvents()
        dock = self.tv.controlsDock
        start = QtCore.QPoint(20, dock.height() // 2)
        origin = dock.pos()
        globalStart = dock.mapToGlobal(start)
        QtTest.QTest.mousePress(dock, QtCore.Qt.LeftButton, pos=start)
        delta = QtCore.QPoint(-60, 30)
        event = QtGui.QMouseEvent(QtCore.QEvent.MouseMove, QtCore.QPointF(start + delta),
                                 QtCore.QPointF(globalStart + delta), QtCore.Qt.NoButton,
                                 QtCore.Qt.LeftButton, QtCore.Qt.NoModifier)
        QtWidgets.QApplication.sendEvent(dock, event)
        QtTest.QTest.mouseRelease(dock, QtCore.Qt.LeftButton, pos=start + delta)
        self.assertEqual(dock.pos(), origin + delta)
        self.assertIs(dock.window(), self.tv.window())
        self.assertFalse(dock.isFloating())
