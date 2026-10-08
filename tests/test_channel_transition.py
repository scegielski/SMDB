import unittest
from unittest.mock import Mock, patch
from PyQt5 import QtCore, QtWidgets
from PyQt5.QtMultimedia import QSoundEffect, QMediaPlayer
from smdb.RetroChannelWidget import ChannelClick, StaticHiss, StandByScreen, RetroChannelWidget, ChannelEngine, ChannelClock


class FakeClick(QtCore.QObject):
    statusChanged = QtCore.pyqtSignal()
    Ready = QSoundEffect.Ready
    Infinite = QSoundEffect.Infinite
    def __init__(self, parent=None):
        super().__init__(parent)
        self.currentStatus = QSoundEffect.Loading
        self.playing = False
        self.play = Mock(side_effect=lambda: setattr(self, 'playing', True))
        self.stop = Mock(side_effect=lambda: setattr(self, 'playing', False))
        self.setVolume = Mock()
        self.setLoopCount = Mock()
    def setSource(self, source): pass
    def status(self): return self.currentStatus
    def isPlaying(self): return self.playing


class ChannelTransitionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_static_animates_then_returns_to_color_bars_at_one_second(self):
        screen = StandByScreen()
        screen.resize(640, 360)
        try:
            with patch('smdb.RetroChannelWidget.time.monotonic', return_value=100):
                screen.startStatic()
                first = screen.grab().toImage()
                screen._animate()
                second = screen.grab().toImage()
                self.assertTrue(screen.isShowingStatic())
                self.assertEqual(screen._staticFrame.size(), screen.size())
                self.assertNotEqual(first, second)
                color = first.pixelColor(10, 10)
                self.assertEqual(color.red(), color.green())
                self.assertEqual(color.green(), color.blue())
            with patch('smdb.RetroChannelWidget.time.monotonic', return_value=101):
                screen._animate()
                self.assertFalse(screen.isShowingStatic())
                self.assertEqual(screen.grab().toImage().pixelColor(10, 10).name(), '#ebebeb')
                self.assertEqual(screen._leaderPosition()[0], 5)
        finally:
            screen.close()

    def test_click_waits_for_audio_ready_and_mute_cancels_pending_sound(self):
        native = Mock()
        with patch('smdb.RetroChannelWidget.QSoundEffect', FakeClick), \
                patch('smdb.RetroChannelWidget._winsound', native):
            click = ChannelClick()
            click.play(70)
            click._effect.play.assert_not_called()
            click._effect.setLoopCount.assert_called_once_with(1)
            click._effect.currentStatus = QSoundEffect.Ready
            click._effect.statusChanged.emit()
            click._effect.play.assert_called_once()
            click._effect.setVolume.assert_called_with(.35)
            native.PlaySound.assert_not_called()
            click._effect.currentStatus = QSoundEffect.Loading
            click.play(70)
            click.setVolume(0)
            click._effect.currentStatus = QSoundEffect.Ready
            click._effect.statusChanged.emit()
            self.assertEqual(click._effect.play.call_count, 1)
            click.play(100)
            self.assertEqual(click._effect.play.call_count, 2)

    def test_only_changed_channels_click_and_show_static(self):
        tv = RetroChannelWidget()
        engines = [Mock(container=QtWidgets.QWidget(), currentTitle='', standbyScreen=StandByScreen()) for _ in range(2)]
        tv.channels = [{'genre': 'Action'}, {'genre': 'Comedy'}]
        tv.engines = dict(enumerate(engines))
        for engine in engines:
            tv.displayStack.addWidget(engine.container)
        engines[0].isShowingStandby.return_value = False
        engines[1].isShowingStandby.return_value = True
        try:
            with patch.object(tv.channelClick, 'play') as click, \
                    patch.object(tv, '_showBanner'), patch.object(tv, '_showVideoOsd'), \
                    patch.object(tv, '_syncStandbyTone'), \
                    patch('smdb.RetroChannelWidget.time.monotonic', return_value=100):
                tv._tuneTo(1)
                click.assert_called_once_with(70)
                self.assertIsNotNone(tv._tuningOverlay)
                deadline = tv._tuningStaticDeadline
                tv._tuneTo(1)
                click.assert_called_once_with(70)
                self.assertEqual(tv._tuningStaticDeadline, deadline)
                tv._tuneTo(0)
                self.assertEqual(click.call_count, 2)
                self.assertIs(tv.displayStack.currentWidget(), engines[0].container)
                self.assertIsNotNone(tv._tuningOverlay)
        finally:
            tv.channels = []
            tv.close()
            for engine in engines:
                engine.standbyScreen.close()

    def test_first_frame_replaces_static_before_deadline(self):
        engine = ChannelEngine(1, 'Action', ChannelClock([0]), resolver=lambda row: None, titleGetter=str)
        slot = engine.activeSlot
        realPlayer = slot.player
        try:
            with patch.object(engine, '_startResolve'), \
                    patch('smdb.RetroChannelWidget.time.monotonic', return_value=100):
                engine._tuneIn()
                self.assertTrue(engine.standbyScreen.isShowingStatic())
                self.assertTrue(engine.isShowingStandby())
                slot.player = Mock()
                slot.player.state.return_value = QMediaPlayer.PlayingState
                slot._hasPlayingFrame = True
                with patch.object(slot, 'isReady', return_value=True):
                    engine._onSlotReady(slot)
                self.assertFalse(engine.isShowingStandby())
                self.assertIs(engine._stack.currentWidget(), slot.videoWidget)
        finally:
            slot.player = realPlayer
            engine.shutdown()
            engine.container.close()

    def test_hiss_loops_without_restarting_and_stops_or_mutes(self):
        with patch('smdb.RetroChannelWidget.QSoundEffect', FakeClick):
            hiss = StaticHiss()
            hiss.start(70)
            hiss._effect.play.assert_not_called()
            hiss._effect.setLoopCount.assert_called_once_with(QSoundEffect.Infinite)
            hiss._effect.currentStatus = QSoundEffect.Ready
            hiss._effect.statusChanged.emit()
            hiss._effect.play.assert_called_once()
            hiss.start(70)
            hiss._effect.play.assert_called_once()
            hiss.setVolume(0)
            self.assertFalse(hiss._effect.isPlaying())
            hiss.setVolume(70)
            self.assertEqual(hiss._effect.play.call_count, 2)
            hiss.stop()
            hiss._effect.statusChanged.emit()
            self.assertEqual(hiss._effect.play.call_count, 2)
            self.assertFalse(hiss._effect.isPlaying())

    def test_static_is_presented_before_engine_creation_and_clears_at_deadline(self):
        tv = RetroChannelWidget()
        tv.channels = [{'genre': 'Action'}, {'genre': 'Comedy'}]
        tv.resize(1000, 800)
        def make(index):
            self.assertIsNotNone(tv._tuningOverlay)
            self.assertEqual(tv._tuningChannel, 1)
            engine = Mock(container=QtWidgets.QWidget(), currentTitle='', standbyScreen=StandByScreen())
            engine.isShowingStandby.return_value = True
            return engine
        try:
            with patch.object(tv, '_createEngine', side_effect=make), \
                    patch.object(tv, '_showBanner'), patch.object(tv, '_showVideoOsd'), \
                    patch.object(tv, '_syncStandbyTone'), \
                    patch.object(tv.staticHiss, 'start') as hiss, \
                    patch.object(tv.staticHiss, 'stop') as stop, \
                    patch('smdb.RetroChannelWidget.time.monotonic', return_value=100):
                tv._tuneTo(1)
                hiss.assert_called_with(70)
                tv._pollTuningStatic()
                self.assertIsNotNone(tv._tuningOverlay)
                with patch('smdb.RetroChannelWidget.time.monotonic', return_value=101):
                    tv._pollTuningStatic()
                self.assertIsNone(tv._tuningOverlay)
                stop.assert_called()
                self.assertFalse(tv.engines[1].standbyScreen.isShowingStatic())
        finally:
            tv.channels = []
            tv.close()
