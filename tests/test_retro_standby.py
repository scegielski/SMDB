import os
import struct
import tempfile
import unittest
import wave
from unittest.mock import Mock, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt5 import QtCore, QtWidgets
from PyQt5.QtMultimedia import QMediaPlayer, QSoundEffect

from smdb.RetroChannelWidget import ChannelClock, ChannelEngine, StandbyTone, _ensureStandbyToneFile


class FakeSoundEffect(QtCore.QObject):
    statusChanged = QtCore.pyqtSignal()
    Infinite = QSoundEffect.Infinite
    Ready = QSoundEffect.Ready

    def __init__(self, parent=None):
        super().__init__(parent)
        self.currentStatus = QSoundEffect.Loading
        self.playing = False
        self.playCalls = 0

    def setSource(self, source):
        pass

    def setLoopCount(self, count):
        pass

    def setVolume(self, volume):
        pass

    def status(self):
        return self.currentStatus

    def isPlaying(self):
        return self.playing

    def play(self):
        self.playing = True
        self.playCalls += 1

    def stop(self):
        self.playing = False

    def finishLoading(self):
        self.currentStatus = QSoundEffect.Ready
        self.statusChanged.emit()


class StandbyStartupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def makeTone(self):
        with patch('smdb.RetroChannelWidget._winsound', None), \
                patch('smdb.RetroChannelWidget.QSoundEffect', FakeSoundEffect), \
                patch('smdb.RetroChannelWidget._ensureStandbyToneFile', return_value='tone.wav'):
            return StandbyTone()

    def test_windows_tone_starts_without_qt_events_and_does_not_restart_on_poll(self):
        native = Mock(SND_FILENAME=1, SND_ASYNC=2, SND_LOOP=4, SND_NODEFAULT=8)
        with patch('smdb.RetroChannelWidget._winsound', native), \
                patch('smdb.RetroChannelWidget.QSoundEffect', FakeSoundEffect), \
                patch('smdb.RetroChannelWidget._ensureStandbyToneFile', return_value='tone.wav'):
            tone = StandbyTone()
            tone.start()
            # No processEvents / Ready signal: main-window startup is still busy.
            native.PlaySound.assert_called_once_with('tone.wav', 15)
            tone.start()
            native.PlaySound.assert_called_once()
            tone.setMuted(True)
            native.PlaySound.assert_called_with(None, 0)
            tone.setMuted(False)
            native.PlaySound.assert_called_with('tone.wav', 15)
            tone.stop()
            native.PlaySound.assert_called_with(None, 0)

    def test_start_during_loading_plays_on_ready_without_restarting_each_poll(self):
        tone = self.makeTone()
        tone.start()
        tone.start()
        self.assertEqual(tone._effect.playCalls, 0)
        tone._effect.finishLoading()
        self.assertTrue(tone._effect.playing)
        tone.start()
        self.assertEqual(tone._effect.playCalls, 1)

    def test_leaving_standby_during_loading_cancels_pending_tone(self):
        tone = self.makeTone()
        tone.start()
        tone.stop()
        tone._effect.finishLoading()
        self.assertEqual(tone._effect.playCalls, 0)

    def test_unmuting_resumes_requested_tone_immediately(self):
        tone = self.makeTone()
        tone.start()
        tone.setMuted(True)
        tone._effect.finishLoading()
        self.assertFalse(tone._effect.playing)
        tone.setMuted(False)
        self.assertTrue(tone._effect.playing)
        tone.stop()
        tone.setMuted(True)
        tone.setMuted(False)
        self.assertFalse(tone._effect.playing)

    def test_standby_lasts_until_first_playing_video_frame(self):
        engine = ChannelEngine(1, 'Action', ChannelClock([0]), lambda row: None, str)
        slot = engine.activeSlot
        realPlayer = slot.player
        slot.player = Mock()
        slot.path = 'movie.mp4'
        slot._ready = True
        try:
            slot.player.state.return_value = QMediaPlayer.PlayingState
            slot.player.mediaStatus.return_value = QMediaPlayer.LoadedMedia
            engine._onSlotReady(slot)
            self.assertTrue(engine.isShowingStandby())
            slot.player.mediaStatus.return_value = QMediaPlayer.BufferingMedia
            engine._onSlotReady(slot)
            self.assertTrue(engine.isShowingStandby())
            slot.player.mediaStatus.return_value = QMediaPlayer.BufferedMedia
            slot.player.state.return_value = QMediaPlayer.PausedState
            engine._onSlotReady(slot)
            self.assertTrue(engine.isShowingStandby())
            slot.player.state.return_value = QMediaPlayer.PlayingState
            engine._onSlotReady(slot)
            self.assertTrue(engine.isShowingStandby())
            invalidFrame = Mock()
            invalidFrame.isValid.return_value = False
            slot._onVideoFrame(invalidFrame)
            self.assertTrue(engine.isShowingStandby())
            frame = Mock()
            frame.isValid.return_value = True
            slot._onVideoFrame(frame)
            self.assertFalse(engine.isShowingStandby())
            slot.stop()
            self.assertFalse(slot._hasPlayingFrame)
        finally:
            slot.player = realPlayer
            engine.shutdown()
            engine.container.close()

    def test_show_starts_tone_before_tuning(self):
        from smdb.RetroChannelWidget import RetroChannelWidget
        tv = RetroChannelWidget()
        tv.channels = [{'genre': 'Action', 'rows': [0], 'clock': ChannelClock([0])}]
        calls = []
        with patch.object(tv.standbyTone, 'start', side_effect=lambda: calls.append('tone')), \
                patch.object(tv, '_tuneTo', side_effect=lambda _: calls.append('tune')):
            tv.show()
            self.assertEqual(calls[:2], ['tone', 'tune'])
        tv.close()

    def test_loop_boundary_has_no_fade_dip(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch('smdb.RetroChannelWidget.tempfile.gettempdir', return_value=directory):
            with wave.open(_ensureStandbyToneFile(), 'rb') as wav:
                samples = struct.unpack('<' + 'h' * wav.getnframes(), wav.readframes(wav.getnframes()))
        boundary = samples[-200:] + samples[:200]
        middle = samples[10000:10400]
        self.assertGreater(sum(x * x for x in boundary), 0.9 * sum(x * x for x in middle))


if __name__ == '__main__':
    unittest.main()
