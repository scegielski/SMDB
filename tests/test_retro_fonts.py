import os
import tempfile
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt5 import QtCore, QtGui, QtWidgets
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
                self.assertEqual(tv.sectionFontScales, dict.fromkeys(('guide', 'info', 'controls'), 2.0))
                tv.changeSectionFontSize('guide', 1)
                tv.changeSectionFontSize('info', -2)
                tv.changeSectionFontSize('controls', 3)
                expected = {'guide': 2.25, 'info': 1.5, 'controls': 2.75}
                self.assertEqual(tv.sectionFontScales, expected)
                parent.settings.sync()
                restored = RetroChannelWidget(parent)
                restored.show()
                self.app.processEvents()
                self.assertEqual(restored.sectionFontScales, expected)
                self.assertEqual(restored.guideTable.scale, 2.25)
                self.assertEqual(restored.guideDescription.font().pixelSize(), 21)
                self.assertEqual(restored.volumeUpButton.font().pixelSize(), 38)
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
                   tv.muteButton, tv.fullScreenButton,
                   tv.nowPlayingLabel, tv.guideTable, tv.guideTable.viewport()]

        def snapshot():
            return [(QtGui.QFontInfo(widget.font()).family(), widget.font().pixelSize())
                    for widget in widgets]

        try:
            for scale in (2.0, 1.25, 3.0):
                tv.setFontScale(scale)
                self.app.processEvents()
                expected = snapshot()
                self.assertEqual(len(set(expected)), 1)
                self.assertEqual(expected[0][1], round(14 * scale))
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
