import os
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt5 import QtCore, QtWidgets

from smdb.RetroChannelWidget import ChannelClock, RetroChannelWidget


class FullScreenLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_fullscreen_preserves_engines_and_guide_but_tab_exit_stops_them(self):
        tabs = QtWidgets.QStackedWidget()
        tabs.addWidget(QtWidgets.QWidget())
        tv = RetroChannelWidget()
        tv.channels = [
            {'genre': genre, 'rows': [0, 1, 2], 'clock': ChannelClock([0, 1, 2])}
            for genre in ('Action', 'Comedy', 'Drama')
        ]
        tv._updateEmptyState()
        tabs.addWidget(tv)
        tabs.setCurrentWidget(tv)
        tabs.resize(800, 600)
        tabs.show()
        self.app.processEvents()
        QtCore.QThreadPool.globalInstance().waitForDone()
        self.app.processEvents()
        engines = dict(tv.engines)
        players = {i: e.activeSlot.player for i, e in engines.items()}
        if not tv.guideVisible:
            tv.toggleGuide()
        preview_engine = tv._guidePreviewHostedEngine

        try:
            with patch.object(tv, '_teardownAllEngines', wraps=tv._teardownAllEngines) as teardown, \
                    patch.object(tv, '_tuneTo', wraps=tv._tuneTo) as tune:
                for guide_visible in (True, False, True):
                    if tv.guideVisible != guide_visible:
                        tv.toggleGuide()
                    preview_engine = tv._guidePreviewHostedEngine
                    for fullscreen in (True, False):
                        tv.toggleFullScreen()
                        self.app.processEvents()
                        self.assertEqual(tv.isFullScreenActive, fullscreen)
                        self.assertTrue(tv.isActive)
                        self.assertTrue(tv.standbyPollTimer.isActive())
                        self.assertEqual(tv.engines, engines)
                        self.assertEqual({i: e.activeSlot.player for i, e in tv.engines.items()}, players)
                        self.assertEqual(tv.guideVisible, guide_visible)
                        self.assertFalse(tv.sideScroll.isHidden())
                        self.assertTrue(tv.controlsDock.isVisible())
                        self.assertTrue(tv.nowPlayingLabel.isHidden())
                        self.assertIs(tv._guidePreviewHostedEngine, preview_engine)
                teardown.assert_not_called()
                tune.assert_not_called()
                self.assertIs(tabs.currentWidget(), tv)
                self.assertIs(tv.parentWidget(), tabs)

                tabs.setCurrentIndex(0)
                self.app.processEvents()
                teardown.assert_called_once()
                self.assertFalse(tv.isActive)
                self.assertFalse(tv.standbyPollTimer.isActive())
                self.assertFalse(tv.guideVisible)
                self.assertEqual(tv.engines, {})
        finally:
            if tv.isFullScreenActive:
                tv.toggleFullScreen()
            tabs.close()
            QtCore.QThreadPool.globalInstance().waitForDone()
            self.app.processEvents()

    def test_fullscreen_hides_menu_and_status_but_keeps_guide_changes_on_exit(self):
        host = QtWidgets.QMainWindow()
        tv = RetroChannelWidget()
        host.setCentralWidget(tv)
        host.menuBar().addMenu('View')
        host.statusBar().showMessage('Ready')
        host.resize(1100, 900)
        try:
            with patch.object(tv.standbyTone, '_syncPlayback'):
                host.show()
                self.app.processEvents()
                tv.channels = [{'genre': 'Action', 'rows': [0], 'clock': ChannelClock([0])}]
                tv.toggleGuide()
                margins = tv.layout().contentsMargins()
                spacing = tv.layout().spacing()
                tv._enterFullScreen()
                self.app.processEvents()
                self.assertTrue(tv.guideVisible)
                self.assertTrue(tv.guideOverlay.isVisible())
                self.assertTrue(tv.guideButton.isChecked())
                self.assertFalse(host.menuBar().isVisible())
                self.assertFalse(host.statusBar().isVisible())
                self.assertFalse(tv.nowPlayingLabel.isVisible())
                self.assertEqual(tv.layout().contentsMargins(), margins)
                self.assertEqual(tv.layout().spacing(), spacing)
                tv.toggleGuide()
                self.assertFalse(tv.guideVisible)
                tv._exitFullScreen()
                self.app.processEvents()
                self.assertFalse(tv.guideVisible)
                self.assertFalse(tv.guideButton.isChecked())
                self.assertFalse(tv.guideOverlay.isVisible())
                self.assertTrue(host.menuBar().isVisible())
                self.assertFalse(host.statusBar().isVisible())
                self.assertFalse(tv.nowPlayingLabel.isVisible())
                tv._enterFullScreen()
                self.assertFalse(tv.guideVisible)
                tv.toggleGuide()
                tv._exitFullScreen()
                self.assertTrue(tv.guideVisible)
                self.assertTrue(tv.guideButton.isChecked())
        finally:
            if tv.isFullScreenActive:
                tv._exitFullScreen()
            host.close()


if __name__ == '__main__':
    unittest.main()
