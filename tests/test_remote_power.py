import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from PyQt5 import QtWidgets
from smdb.RetroChannelWidget import RetroChannelWidget, ChannelClock


class RemotePowerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_power_stops_every_engine_and_restores_current_broadcast(self):
        tv = RetroChannelWidget()
        tv.resize(1100, 950)
        try:
            with patch.object(tv.standbyTone, '_syncPlayback'):
                tv.show()
                self.app.processEvents()
                clocks = [ChannelClock([0], lambda row: 100000), ChannelClock([1], lambda row: 100000)]
                tv.channels = [{'clock': clock, 'genre': 'Test', 'rows': [i]} for i, clock in enumerate(clocks)]
                tv.currentIndex = 1
                engines = [SimpleNamespace(shutdown=Mock(), container=QtWidgets.QWidget()) for _ in clocks]
                for index, engine in enumerate(engines):
                    tv.engines[index] = engine
                    tv.displayStack.addWidget(engine.container)
                tv.guideVisible = True
                tv.guideOverlay.show()
                tv.powerButton.click()
                self.app.processEvents()
                self.assertFalse(tv._powerOn)
                self.assertTrue(tv.powerOffScreen.isVisible())
                self.assertTrue(tv.controlsDock.isVisible())
                self.assertTrue(tv.guideOverlay.isVisible())
                self.assertTrue(tv.guidePowerOffScreen.isVisible())
                self.assertTrue(tv.channelUpButton.isEnabled())
                self.assertFalse(tv.standbyTone._requested)
                self.assertFalse(tv.pauseButton.isEnabled())
                self.assertTrue(tv.powerButton.isEnabled())
                self.assertEqual(tv.engines, {})
                for engine in engines:
                    engine.shutdown.assert_called_once()
                for clock in clocks:
                    self.assertIsNone(clock._pausedAt)
                tv._tuneTo(0)
                self.assertEqual(tv.engines, {})
                with patch.object(tv, '_tuneTo') as tune:
                    tv.powerButton.click()
                    tune.assert_called_once_with(0)
                self.assertTrue(tv._powerOn)
                self.assertFalse(tv.powerOffScreen.isVisible())
                self.assertTrue(tv.guideOverlay.isVisible())
                self.assertTrue(tv.pauseButton.isEnabled())
        finally:
            tv.channels = []
            tv.controlsDock.hide()
            tv.close()

    def test_mute_and_guide_pressed_states_follow_actions(self):
        tv=RetroChannelWidget()
        try:
            tv.muteButton.click()
            self.assertTrue(tv.muteButton.isChecked())
            self.assertEqual(tv.masterVolume,0)
            tv.volumeUpButton.click()
            self.assertFalse(tv.muteButton.isChecked())
            tv.muteButton.click();tv.muteButton.click()
            self.assertFalse(tv.muteButton.isChecked())
            tv.channels=[{'genre':'Test','clock':ChannelClock([0],lambda row:100000),'rows':[0]}]
            tv._updateEmptyState()
            with patch.object(tv,'_refreshGuideTable'),patch.object(tv,'_startGuidePreview'),patch.object(tv,'_stopGuidePreview'):
                tv.guideButton.click()
                self.assertTrue(tv.guideVisible)
                self.assertTrue(tv.guideButton.isChecked())
                tv.toggleGuide()
                self.assertFalse(tv.guideVisible)
                self.assertFalse(tv.guideButton.isChecked())
        finally:tv.channels=[];tv.close()

    def test_power_preserves_pause_and_volume(self):
        tv = RetroChannelWidget()
        try:
            tv.setVolume(35)
            tv._pausedAll = True
            tv._syncPauseButton()
            tv.powerButton.click()
            tv.togglePause()
            tv.powerButton.click()
            self.assertTrue(tv._pausedAll)
            self.assertEqual(tv.masterVolume, 35)
            self.assertEqual(tv.pauseButton.text(), 'PLAY')
            tv._pausedAll = False
            tv._syncPauseButton()
            self.assertEqual(tv.pauseButton.text(), 'PAUSE')
            self.assertEqual(tv.backTenButton.text(), 'REW')
            self.assertEqual(tv.forwardTenButton.text(), 'FF')
        finally:
            tv.close()


if __name__ == '__main__':
    unittest.main()
