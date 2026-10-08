import os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from PyQt5 import QtCore,QtGui,QtWidgets,QtTest
from smdb.RetroChannelWidget import RetroChannelWidget

class RemoteDockTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    def test_floating_redocking_and_mode_visibility_preserve_controls(self):
        tv=RetroChannelWidget();tv.resize(1000,1000)
        try:
            with patch.object(tv.standbyTone,'_syncPlayback'):
                tv.show();self.app.processEvents()
                dock=tv.controlsDock
                self.assertEqual(dock.allowedAreas(),QtCore.Qt.RightDockWidgetArea)
                self.assertFalse(dock.isFloating())
                pause=tv.pauseButton
                scales=dict(tv.sectionFontScales)
                dock.setFloating(True);self.app.processEvents()
                self.assertTrue(dock.isWindow());self.assertTrue(dock.isVisible())
                self.assertIs(dock.widget(),tv.sideScroll)
                before=tv.masterVolume
                tv.volumeUpButton.click()
                self.assertEqual(tv.masterVolume,min(100,before+5))
                tv.hide();self.app.processEvents();self.assertFalse(dock.isVisible())
                tv.show();self.app.processEvents();self.assertTrue(dock.isVisible())
                dock.setFloating(False);self.app.processEvents()
                self.assertEqual(tv.tvDockHost.dockWidgetArea(dock),QtCore.Qt.RightDockWidgetArea)
                self.assertIs(tv.pauseButton,pause)
                self.assertEqual(tv.sectionFontScales,scales)
                dock.setFloating(True)
                tv.toggleFullScreen();self.app.processEvents();self.assertTrue(dock.isVisible())
                tv.toggleFullScreen();self.app.processEvents();self.assertTrue(dock.isVisible())
                self.assertTrue(dock.isFloating())
        finally:tv.close()
    def test_explicit_button_and_titleless_surface_drag(self):
        tv=RetroChannelWidget();tv.resize(1000,1000)
        try:
            with patch.object(tv.standbyTone,'_syncPlayback'):
                tv.show();self.app.processEvents()
                dock=tv.controlsDock
                self.assertEqual(dock.titleBarWidget().height(),0)
                self.assertFalse(dock.features() & dock.DockWidgetClosable)
                self.assertEqual(tv.remoteDockButton.text(),'UNDOCK')
                tv.remoteDockButton.click();self.app.processEvents()
                self.assertTrue(dock.isFloating())
                self.assertTrue(dock.windowFlags() & QtCore.Qt.FramelessWindowHint)
                self.assertFalse(dock.mask().contains(QtCore.QPoint(0,0)))
                self.assertTrue(dock.mask().contains(dock.rect().center()))
                self.assertLess(dock.height(),tv.height())
                self.assertEqual(tv.sideScroll.verticalScrollBar().maximum(),0)
                self.assertEqual(tv.remoteDockButton.text(),'DOCK')
                tv.remoteDockButton.click();self.app.processEvents()
                self.assertFalse(dock.isFloating())
                # Drag directly from a control; release must not activate it.
                button=tv.volumeDownButton
                volume=tv.masterVolume
                start=button.rect().center();globalStart=button.mapToGlobal(start)
                QtTest.QTest.mousePress(button,QtCore.Qt.LeftButton,pos=start)
                end=globalStart+QtCore.QPoint(-140,50)
                event=QtGui.QMouseEvent(QtCore.QEvent.MouseMove,QtCore.QPointF(start),
                    QtCore.QPointF(end),QtCore.Qt.NoButton,QtCore.Qt.LeftButton,QtCore.Qt.NoModifier)
                self.app.sendEvent(button,event);self.app.processEvents()
                self.assertTrue(dock.isFloating())
                release=QtGui.QMouseEvent(QtCore.QEvent.MouseButtonRelease,QtCore.QPointF(dock.mapFromGlobal(end)),
                    QtCore.QPointF(end),QtCore.Qt.LeftButton,QtCore.Qt.NoButton,QtCore.Qt.NoModifier)
                self.app.sendEvent(dock,release);self.app.processEvents()
                self.assertEqual(tv.masterVolume,volume)
                self.assertFalse(button.isDown())
                before=dock.pos()
                surface=tv.remoteBrand;point=surface.rect().center();origin=surface.mapToGlobal(point)
                QtTest.QTest.mousePress(surface,QtCore.Qt.LeftButton,pos=point)
                event=QtGui.QMouseEvent(QtCore.QEvent.MouseMove,QtCore.QPointF(point),
                    QtCore.QPointF(origin+QtCore.QPoint(80,40)),QtCore.Qt.NoButton,QtCore.Qt.LeftButton,QtCore.Qt.NoModifier)
                self.app.sendEvent(surface,event)
                QtTest.QTest.mouseRelease(dock,QtCore.Qt.LeftButton)
                self.assertEqual(dock.pos()-before,QtCore.QPoint(80,40))
                QtTest.QTest.mouseClick(button,QtCore.Qt.LeftButton)
                self.assertEqual(tv.masterVolume,max(0,volume-5))
        finally:tv.controlsDock.hide();tv.close()

    def test_repeated_drags_keep_window_visible_and_follow_global_pointer(self):
        tv=RetroChannelWidget();tv.resize(1000,700);tv.move(180,160)
        class VisibilitySpy(QtCore.QObject):
            def __init__(self):super().__init__();self.hidden=0
            def eventFilter(self,watched,event):
                if event.type()==QtCore.QEvent.Hide:self.hidden+=1
                return False
        try:
            with patch.object(tv.standbyTone,'_syncPlayback'):
                tv.show();self.app.processEvents()
                dock=tv.controlsDock
                # A new child needs no separate event-filter registration.
                surface=QtWidgets.QLabel('Drag surface',tv.sideControls)
                surface.setGeometry(40,40,30,25);surface.show()
                spy=VisibilitySpy();dock.installEventFilter(spy)
                for attempt in range(4):
                    origin=dock.mapToGlobal(QtCore.QPoint())
                    point=surface.rect().center();start=surface.mapToGlobal(point)
                    offset=start-origin
                    QtTest.QTest.mousePress(surface,QtCore.Qt.LeftButton,pos=point)
                    target=start+QtCore.QPoint(-60,35)
                    event=QtGui.QMouseEvent(QtCore.QEvent.MouseMove,QtCore.QPointF(point),
                        QtCore.QPointF(target),QtCore.Qt.NoButton,QtCore.Qt.LeftButton,QtCore.Qt.NoModifier)
                    # Model a move delivered to the parent as the pointer leaves.
                    self.app.sendEvent(tv,event);self.app.processEvents()
                    self.assertTrue(dock.isFloating())
                    self.assertEqual(dock.pos(),target-offset)
                    release=QtGui.QMouseEvent(QtCore.QEvent.MouseButtonRelease,QtCore.QPointF(point),
                        QtCore.QPointF(target),QtCore.Qt.LeftButton,QtCore.Qt.NoButton,QtCore.Qt.NoModifier)
                    self.app.sendEvent(tv,release);self.app.processEvents()
                    self.assertIsNone(dock._press)
                    self.assertIsNot(QtWidgets.QWidget.mouseGrabber(),dock)
                    if attempt==0:spy.hidden=0  # Initial undocking changes window type.
                    else:self.assertEqual(spy.hidden,0)
                # Scrollbars must not start a window drag.
                bar=tv.sideScroll.verticalScrollBar()
                QtTest.QTest.mousePress(bar,QtCore.Qt.LeftButton)
                self.assertIsNone(dock._press)
                QtTest.QTest.mouseRelease(bar,QtCore.Qt.LeftButton)
        finally:tv.controlsDock.hide();tv.close()

    def test_corner_resize_preserves_ratio_and_opposite_corner(self):
        tv=RetroChannelWidget();tv.resize(1200,1000)
        try:
            with patch.object(tv.standbyTone,'_syncPlayback'):
                tv.show();self.app.processEvents();tv.controlsDock.setFloating(True)
                dock=tv.controlsDock
                for horizontal,vertical,direction in ((x,y,d) for x,y in ((-1,-1),(1,-1),(-1,1),(1,1)) for d in (-1,1)):
                    tv.remoteScale=0.85;tv._applyRemoteSizes();dock.move(300,100);self.app.processEvents()
                    before=dock.geometry();fonts=dict(tv.sectionFontScales)
                    point=QtCore.QPoint(16 if horizontal<0 else dock.width()-17,
                                       16 if vertical<0 else dock.height()-17)
                    start=dock.mapToGlobal(point)
                    QtTest.QTest.mousePress(dock,QtCore.Qt.LeftButton,pos=point)
                    end=start+QtCore.QPoint(15*horizontal*direction,35*vertical*direction)
                    event=QtGui.QMouseEvent(QtCore.QEvent.MouseMove,QtCore.QPointF(point),
                        QtCore.QPointF(end),QtCore.Qt.NoButton,QtCore.Qt.LeftButton,QtCore.Qt.NoModifier)
                    self.app.sendEvent(dock,event);self.app.processEvents()
                    QtTest.QTest.mouseRelease(dock,QtCore.Qt.LeftButton,pos=point)
                    after=dock.geometry()
                    self.assertGreater(direction*(after.width()-before.width()),0)
                    self.assertAlmostEqual(after.width()/after.height(),before.width()/before.height(),delta=0.002)
                    self.assertEqual(after.right() if horizontal<0 else after.left(),
                                     before.right() if horizontal<0 else before.left())
                    self.assertEqual(after.bottom() if vertical<0 else after.top(),
                                     before.bottom() if vertical<0 else before.top())
                    self.assertEqual(tv.sectionFontScales,fonts)
                    self.assertLessEqual(tv.sideControls.width(),tv.sideScroll.viewport().width())
                    self.assertFalse(dock.mask().contains(QtCore.QPoint()))
        finally:tv.controlsDock.hide();tv.close()

    def test_floating_preference_and_geometry_restore(self):
        with tempfile.TemporaryDirectory() as directory:
            parent=QtWidgets.QWidget();parent.settings=QtCore.QSettings(str(Path(directory)/'remote.ini'),QtCore.QSettings.IniFormat)
            tv=RetroChannelWidget(parent)
            restored=None
            try:
                with patch.object(tv.standbyTone,'_syncPlayback'):
                    tv._showRemote();tv.controlsDock.setFloating(True)
                    tv.controlsDock.move(240,160);tv._fitFloatingRemote();tv._saveRemoteState()
                    geometry=parent.settings.value('smtvRemoteGeometry')
                    self.assertTrue(parent.settings.value('smtvRemoteFloating',False,type=bool))
                    restored=RetroChannelWidget(parent)
                    restored._showRemote()
                    self.assertTrue(restored.controlsDock.isFloating())
                    self.assertTrue(geometry)
                    self.assertEqual(restored.controlsDock.pos(),tv.controlsDock.pos())
                    self.assertEqual(restored.controlsDock.height(),tv.controlsDock.height())
            finally:
                if restored:restored.controlsDock.hide();restored.close()
                tv.controlsDock.hide();tv.close();parent.close()
if __name__=='__main__':unittest.main()
