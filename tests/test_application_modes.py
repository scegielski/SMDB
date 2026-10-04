import os
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt5 import QtCore, QtWidgets
from smdb.MainWindow import MainWindow


class ApplicationModeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_mode_menu_and_video_only_fullscreen(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = QtCore.QSettings(os.path.join(directory, 'settings.ini'), QtCore.QSettings.IniFormat)
            settings.setValue('moviesTabIndex', 2)  # former TV tab
            with patch('smdb.MainWindow.QtCore.QSettings', return_value=settings), \
                    patch('smdb.RetroChannelWidget.StandbyTone._syncPlayback'):
                window = MainWindow()
                tv = window.retroChannelWidget
                try:
                    self.app.processEvents()
                    self.assertEqual(window.applicationMode, 'TV')
                    self.assertIs(window.modeStack.currentWidget(), tv)
                    self.assertTrue(window.databaseWidget.isHidden())
                    self.assertEqual([window.moviesTabWidget.tabText(i)
                                      for i in range(window.moviesTabWidget.count())],
                                     ['List', 'Cover Flow', 'Statistics'])
                    self.assertTrue(window.statusBar().isHidden())
                    self.assertFalse(window.menuBar().isHidden())
                    databaseSize = window.fontSize
                    tvSize = tv.fontScale
                    window.increaseFontAction.trigger()
                    self.assertEqual(tv.fontScale, tvSize + 0.25)
                    self.assertEqual(window.fontSize, databaseSize)
                    window.decreaseFontAction.trigger()
                    self.assertEqual(tv.fontScale, tvSize)
                    tv.setFontScale(4.0)
                    self.assertFalse(window.increaseFontAction.isEnabled())
                    tv.setFontScale(0.5)
                    self.assertFalse(window.decreaseFontAction.isEnabled())
                    tv.setFontScale(tvSize)
                    self.assertFalse(any(button.text().startswith('FONT')
                                         for button in tv.sideControls.findChildren(QtWidgets.QPushButton)))
                    tv.toggleFullScreen()
                    self.app.processEvents()
                    self.assertTrue(window.isFullScreen())
                    self.assertTrue(tv.sideScroll.isHidden())
                    self.assertTrue(tv.nowPlayingLabel.isHidden())
                    self.assertTrue(window.menuBar().isHidden())
                    self.assertEqual(tv.overlayArea.size(), tv.size())
                    window.setApplicationMode('Database')
                    self.app.processEvents()
                    self.assertFalse(window.isFullScreen())
                    self.assertFalse(tv.isFullScreenActive)
                    self.assertIs(window.modeStack.currentWidget(), window.databaseWidget)
                    self.assertFalse(window.menuBar().isHidden())
                    self.assertFalse(window.statusBar().isHidden())
                    self.assertFalse(tv.isActive)
                    window.increaseFontAction.trigger()
                    self.assertEqual(window.fontSize, databaseSize + 1)
                    self.assertEqual(tv.fontScale, tvSize)
                    window.decreaseFontAction.trigger()
                    self.assertEqual(window.fontSize, databaseSize)
                    window.modeActions['TV'].trigger()
                    self.app.processEvents()
                    self.assertIs(window.modeStack.currentWidget(), tv)
                    self.assertFalse(tv.sideScroll.isHidden())
                    self.assertEqual(settings.value('applicationMode'), 'TV')
                finally:
                    window.close()
                    self.app.processEvents()


if __name__ == '__main__':
    unittest.main()
