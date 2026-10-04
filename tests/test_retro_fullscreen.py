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
        tabs = QtWidgets.QTabWidget()
        tabs.addTab(QtWidgets.QWidget(), 'Other')
        tv = RetroChannelWidget()
        tv.channels = [
            {'genre': genre, 'rows': [0, 1, 2], 'clock': ChannelClock([0, 1, 2])}
            for genre in ('Action', 'Comedy', 'Drama')
        ]
        tv._updateEmptyState()
        tabs.addTab(tv, 'Retro TV')
        tabs.setCurrentWidget(tv)
        tabs.resize(800, 600)
        tabs.show()
        self.app.processEvents()
        QtCore.QThreadPool.globalInstance().waitForDone()
        self.app.processEvents()
        engines = dict(tv.engines)
        players = {i: e.activeSlot.player for i, e in engines.items()}
        tv.toggleGuide()
        preview_engine = tv._guidePreviewHostedEngine

        try:
            with patch.object(tv, '_teardownAllEngines', wraps=tv._teardownAllEngines) as teardown, \
                    patch.object(tv, '_tuneTo', wraps=tv._tuneTo) as tune:
                for _ in range(3):
                    for fullscreen in (True, False):
                        tv.toggleFullScreen()
                        self.app.processEvents()
                        self.assertEqual(tv.isFullScreenActive, fullscreen)
                        self.assertTrue(tv.isActive)
                        self.assertTrue(tv.standbyPollTimer.isActive())
                        self.assertEqual(tv.engines, engines)
                        self.assertEqual({i: e.activeSlot.player for i, e in tv.engines.items()}, players)
                        self.assertTrue(tv.guideVisible)
                        self.assertIs(tv._guidePreviewHostedEngine, preview_engine)
                teardown.assert_not_called()
                tune.assert_not_called()
                self.assertIs(tabs.currentWidget(), tv)
                self.assertEqual(tabs.tabText(tabs.indexOf(tv)), 'Retro TV')

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


if __name__ == '__main__':
    unittest.main()
