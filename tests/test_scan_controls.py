import unittest
from unittest.mock import Mock, patch
from PyQt5 import QtCore, QtWidgets, QtTest
from smdb.RetroChannelWidget import RetroChannelWidget, _ScanButton


class ScanControlsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_quick_click_skips_but_hold_does_not_click_on_release(self):
        button = _ScanButton('FF')
        button.resize(120, 50)
        button.show()
        click, start, stop = Mock(), Mock(), Mock()
        button.clicked.connect(click)
        button.scanStarted.connect(start)
        button.scanFinished.connect(stop)
        QtTest.QTest.mouseClick(button, QtCore.Qt.LeftButton)
        self.assertEqual(click.call_count, 1)
        QtTest.QTest.mousePress(button, QtCore.Qt.LeftButton)
        QtTest.QTest.qWait(450)
        start.assert_called_once()
        QtTest.QTest.mouseRelease(button, QtCore.Qt.LeftButton)
        stop.assert_called_once()
        self.assertEqual(click.call_count, 1)
        button.close()

    def test_scan_uses_exact_three_times_elapsed_and_restores_pause(self):
        tv = RetroChannelWidget()
        engine = Mock()
        engine.currentSlotIndex = 0
        engine.currentRow = 0
        engine._pendingTimelineSeek = None
        engine._paused = False
        engine.activeSlot._lastPlaybackPosition = 10000
        engine.activeSlot.isReady.return_value = True
        engine.isShowingComingUp.return_value = False
        engine.clock.publishedSlotTimes.return_value = (1000, 1100)
        tv.engines = {0: engine}
        tv.currentIndex = 0
        tv.guideVisible = False
        button = tv.forwardTenButton
        button.setDown(True)
        try:
            with patch('smdb.RetroChannelWidget.time.monotonic', return_value=20) as now:
                tv._startScan(button, 1)
                engine.setPaused.assert_called_with(True)
                now.return_value = 22
                tv._scanStep()
                engine._seekFilmPosition.assert_called_with(16000)
                engine.activeSlot.isReady.return_value = False
                calls = engine._seekFilmPosition.call_count
                now.return_value = 22.5
                tv._scanStep()
                self.assertEqual(engine._seekFilmPosition.call_count, calls)
                engine._seekScheduledTime.assert_not_called()
                engine.activeSlot.isReady.return_value = True
                now.return_value = 23
                tv._stopScan()
                engine._seekFilmPosition.assert_called_with(19000)
                engine.setPaused.assert_called_with(False)
                self.assertEqual(button.text(), 'FF')
                engine._paused = True
                tv._startScan(tv.backTenButton, -1)
                tv.backTenButton.setDown(True)
                now.return_value = 25
                tv._scanStep()
                engine._seekFilmPosition.assert_called_with(4000)
                now.return_value = 30
                tv._scanStep()
                engine._seekScheduledTime.assert_called_with(989)
                engine.isShowingComingUp.return_value = True
                now.return_value = 31
                tv._scanStep()
                engine._seekScheduledTime.assert_called_with(986)
                tv._stopScan()
                engine.setPaused.assert_called_with(True)
        finally:
            tv._scanState = None
            tv._scanTimer.stop()
            tv.engines = {}
            tv.close()


if __name__ == '__main__':
    unittest.main()
