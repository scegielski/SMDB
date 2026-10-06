import os
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt5 import QtGui, QtWidgets
from smdb.RetroChannelWidget import RetroChannelWidget


class RetroFontTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

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
