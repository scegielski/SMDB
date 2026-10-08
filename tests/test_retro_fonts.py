import os
import tempfile
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt5 import QtCore, QtGui, QtTest, QtWidgets
from smdb.RetroChannelWidget import RetroChannelWidget


class RetroFontTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_section_sizes_restore_independently(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = QtWidgets.QWidget()
            parent.settings = QtCore.QSettings(os.path.join(directory, 'fonts.ini'), QtCore.QSettings.IniFormat)
            tv = RetroChannelWidget(parent)
            restored = None
            try:
                self.assertEqual(tv.sectionFontScales, dict.fromkeys(('guide', 'info', 'controls', 'channels'), 2.0))
                tv.changeSectionFontSize('guide', 1)
                tv.changeSectionFontSize('info', -2)
                tv.changeSectionFontSize('controls', 3)
                tv.changeSectionFontSize('channels', -3)
                expected = {'guide': 2.25, 'info': 1.5, 'controls': 2.75, 'channels': 1.25}
                self.assertEqual(tv.sectionFontScales, expected)
                parent.settings.sync()
                restored = RetroChannelWidget(parent)
                restored.show()
                self.app.processEvents()
                self.assertEqual(restored.sectionFontScales, expected)
                self.assertEqual(restored.guideTable.scale, 2.25)
                self.assertEqual(restored.guideTable.channelScale, 1.25)
                self.assertEqual(restored.guideTable.channelWidth, round(190 * 1.25))
                self.assertEqual(restored.guideDescription.font().pixelSize(), 21)
                self.assertEqual(restored.volumeUpButton.font().pixelSize(), round(14 * 2.75 * restored.remoteScale))
                for _ in range(2):
                    restored.toggleFullScreen()
                    self.app.processEvents()
                self.assertEqual(restored.sectionFontScales, expected)
                self.assertEqual(restored.guideDescription.font().pixelSize(), 21)
            finally:
                tv.close()
                if restored is not None:
                    restored.close()
                parent.close()

    def test_video_info_splitter_drag_survives_layout_changes(self):
        tv = RetroChannelWidget()
        tv.resize(1300, 850)
        tv.show()
        tv.guideOverlay.show()
        self.app.processEvents()
        try:
            splitter = tv.guideInfoSplitter
            self.assertEqual(splitter.orientation(), QtCore.Qt.Horizontal)
            before = splitter.sizes()
            handle = splitter.handle(1)
            anchor = handle.rect().center()
            globalTarget = handle.mapToGlobal(anchor) + QtCore.QPoint(-100, 0)
            QtTest.QTest.mousePress(handle, QtCore.Qt.LeftButton, pos=anchor)
            event = QtGui.QMouseEvent(QtCore.QEvent.MouseMove,
                                      QtCore.QPointF(handle.mapFromGlobal(globalTarget)),
                                      QtCore.QPointF(globalTarget), QtCore.Qt.NoButton,
                                      QtCore.Qt.LeftButton, QtCore.Qt.NoModifier)
            QtWidgets.QApplication.sendEvent(handle, event)
            QtTest.QTest.mouseRelease(handle, QtCore.Qt.LeftButton,
                                     pos=handle.mapFromGlobal(globalTarget))
            self.app.processEvents()
            after = splitter.sizes()
            self.assertLess(after[0], before[0] - 60)
            self.assertGreater(after[1], before[1] + 60)
            tv.resize(1300, 950)
            tv.changeSectionFontSize('info', 1)
            self.app.processEvents()
            resized = splitter.sizes()
            self.assertAlmostEqual(resized[0] / sum(resized), after[0] / sum(after), delta=0.015)
            self.assertGreater(tv.infoPane.width(), 120)
        finally:
            tv.close()
            self.app.processEvents()

    def test_fonts_ignore_parent_styles_and_survive_fullscreen(self):
        window = QtWidgets.QWidget()
        window.setStyleSheet('font-family: "Times New Roman"; font-size: 12px;')
        layout = QtWidgets.QVBoxLayout(window)
        tabs = QtWidgets.QTabWidget()
        layout.addWidget(tabs)
        tv = RetroChannelWidget(window)
        tv.setVolume(0)
        tabs.addTab(tv, 'Retro TV')
        window.resize(1000, 800)
        window.show()
        self.app.processEvents()
        widgets = [tv, tv.volumeUpButton, tv.volumeDownButton,
                   tv.fullScreenButton,
                   tv.nowPlayingLabel, tv.guideTable, tv.guideTable.viewport()]

        def snapshot():
            return [(QtGui.QFontInfo(widget.font()).family(), widget.font().pixelSize())
                    for widget in widgets]

        try:
            for scale in (2.0, 1.25, 3.0):
                tv.setFontScale(scale)
                self.app.processEvents()
                self.assertLessEqual(tv.sideControls.width(), tv.sideScroll.viewport().width())
                expected = snapshot()
                self.assertEqual(len(set(family for family,size in expected)), 1)
                for widget,(_,size) in zip(widgets,expected):
                    factor=tv.remoteScale if tv.sideControls.isAncestorOf(widget) else 1.0
                    self.assertEqual(size, round(14 * scale * factor))
                self.assertEqual(tv.muteButton.font().pixelSize(), round(11 * scale * tv.remoteScale))
                for _ in range(2):
                    tv.toggleFullScreen()
                    self.app.processEvents()
                    self.assertEqual(snapshot(), expected)
                    tv.toggleFullScreen()
                    self.app.processEvents()
                    self.assertEqual(snapshot(), expected)
                window.setStyleSheet('font-family: Arial; font-size: 26px;')
                self.app.processEvents()
                self.assertEqual(snapshot(), expected)
        finally:
            if tv.isFullScreenActive:
                tv.toggleFullScreen()
            window.close()
            self.app.processEvents()


if __name__ == '__main__':
    unittest.main()
