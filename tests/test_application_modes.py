import os
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt5 import QtCore, QtGui, QtWidgets
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
                    def wheel(widget, delta, modifiers=QtCore.Qt.NoModifier, position=None):
                        point = QtCore.QPointF(position or QtCore.QPoint(20, 20))
                        event = QtGui.QWheelEvent(point, point, QtCore.QPoint(),
                                                  QtCore.QPoint(0, delta), QtCore.Qt.NoButton,
                                                  modifiers, QtCore.Qt.NoScrollPhase, False)
                        QtWidgets.QApplication.sendEvent(widget, event)

                    # Every TV surface uses its current scale; a child scroll
                    # area must not swallow zoom or change the hidden database.
                    for target in (tv.guideDescription.viewport(), tv.guideTable.viewport(),
                                   tv.globalStandby, tv.sideScroll.viewport()):
                        section = tv.fontSectionForWidget(target, QtCore.QPoint(20, 20))
                        before = dict(tv.sectionFontScales)
                        wheel(target, 120)
                        self.assertEqual(tv.fontScale, tvSize + 0.05)
                        self.assertEqual(tv.sectionFontScales,
                                         {name: value + (0.05 if name == section else 0)
                                          for name, value in before.items()})
                        self.assertEqual(window.fontSize, databaseSize)
                        self.assertIn('205%', window.fontMenu.title())
                        window.decreaseFontAction.trigger()
                        self.assertEqual(tv.fontScale, tvSize - 0.2)
                        wheel(target, 480)
                        self.assertEqual(tv.fontScale, tvSize)
                    wheel(tv.guideTable.viewport(), 120, QtCore.Qt.NoModifier)
                    self.assertEqual(tv.fontScale, tvSize + 0.05)
                    wheel(tv.guideTable.viewport(), -120)
                    self.assertEqual(tv.fontScale, tvSize)
                    tv.guideOverlay.show()
                    self.app.processEvents()
                    tv.guideTable.horizontalScrollBar().setValue(300)
                    point = QtCore.QPoint(tv.guideTable.channelWidth + 120, tv.guideTable.headerHeight + 20)
                    stamp = tv.guideTable.startTime + (point.x() - tv.guideTable.channelWidth + 300) * 3600 / tv.guideTable.hourWidth
                    wheel(tv.guideTable.viewport(), 120, position=point)
                    self.assertEqual(tv.sectionFontScales['guide'], tvSize + 0.05)
                    self.assertEqual(tv.sectionFontScales['channels'], tvSize)
                    self.assertAlmostEqual(tv.guideTable.timeX(stamp), point.x(), delta=1)
                    wheel(tv.guideTable.viewport(), -120, position=point)
                    self.assertAlmostEqual(tv.guideTable.timeX(stamp), point.x(), delta=1)
                    window.increaseFontAction.trigger()
                    self.assertEqual(tv.fontScale, tvSize + 0.25)
                    self.assertEqual(window.fontSize, databaseSize)
                    window.decreaseFontAction.trigger()
                    self.assertEqual(tv.fontScale, tvSize)
                    self.assertEqual(tv.sectionFontScales, before)
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
                    wheel(window.moviesTableView.viewport(), 120)
                    self.assertEqual(window.fontSize, databaseSize + 1)
                    self.assertIn(str(databaseSize + 1), window.fontMenu.title())
                    self.assertEqual(tv.fontScale, tvSize)
                    window.increaseFontAction.trigger()
                    wheel(window.movieInfoListView.viewport(), -120)
                    self.assertEqual(window.fontSize, databaseSize + 1)
                    wheel(window.moviesTableView.viewport(), 120, QtCore.Qt.ControlModifier)
                    self.assertEqual(window.fontSize, databaseSize + 2)
                    window.setFontSize(databaseSize)
                    self.assertIn(str(databaseSize), window.fontMenu.title())
                    window.modeActions['TV'].trigger()
                    self.app.processEvents()
                    for target in (tv.guideTable.viewport(), tv.guideDescription.viewport(), tv.sideScroll.viewport()):
                        section = tv.fontSectionForWidget(target, QtCore.QPoint(20, 20))
                        tvScales = dict(tv.sectionFontScales)
                        wheel(target, 120, QtCore.Qt.ControlModifier)
                        self.assertEqual(tv.sectionFontScales,
                                         {name: value + (0.25 if name == section else 0)
                                          for name, value in tvScales.items()})
                        window.decreaseFontAction.trigger()
                        self.assertEqual(tv.sectionFontScales, tvScales)
                    self.assertIs(window.modeStack.currentWidget(), tv)
                    self.assertFalse(tv.sideScroll.isHidden())
                    self.assertEqual(settings.value('applicationMode'), 'TV')
                finally:
                    window.close()
                    self.app.processEvents()


if __name__ == '__main__':
    unittest.main()
