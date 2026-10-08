import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtMultimedia import QMediaPlayer
from smdb.RetroChannelWidget import ComingUpScreen, ChannelClock, ChannelEngine, RetroChannelWidget


class ComingUpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_card_uses_pacific_time_cover_and_escaped_catalogue_text(self):
        screen = ComingUpScreen()
        with tempfile.TemporaryDirectory() as folder:
            cover = str(Path(folder) / 'cover.png')
            image = QtGui.QImage(100, 150, QtGui.QImage.Format_RGB32)
            image.fill(QtGui.QColor('green'))
            image.save(cover)
            utc = QtCore.QDateTime.fromString('2026-10-09T01:30:00Z', QtCore.Qt.ISODate)
            screen.setFilm(utc.toSecsSinceEpoch(), 'The Matrix (1999)', 'Neo <awakens> & follows the rabbit.', cover)
            self.assertEqual(screen.heading.text(), 'Coming up next at 6:30 pm Pacific')
            self.assertIn('The Matrix (1999)', screen.details.toPlainText())
            self.assertIn('Neo <awakens> & follows the rabbit.', screen.details.toPlainText())
            self.assertIn('<img', screen.details.toHtml())
            screen.setFilm(utc.toSecsSinceEpoch(), 'No cover', '', None)
            self.assertIn('No description available.', screen.details.toPlainText())
        screen.close()

    def test_gap_join_and_pause_keep_card_until_next_slot(self):
        with patch('smdb.RetroChannelWidget.time.monotonic', return_value=0) as now, \
                patch('smdb.RetroChannelWidget.time.time', return_value=36000), \
                patch('smdb.RetroChannelWidget.random.uniform', return_value=0):
            clock = ChannelClock([0, 1], lambda row: 61000, broadcastAligned=True)
            info = Mock(return_value={'description': 'Upcoming plot', 'cover': None})
            engine = ChannelEngine(1, 'Action', clock, lambda row: None, lambda row: f'Film {row}', infoGetter=info)
            try:
                now.return_value = 120
                with patch.object(engine, '_startResolve') as resolve:
                    engine._tuneIn()
                    resolve.assert_not_called()
                self.assertTrue(engine.isShowingComingUp())
                info.assert_called_with(clock.slotInfo(1)[0])
                self.assertIn('Upcoming plot', engine.comingUpScreen.details.toPlainText())
                engine.setPaused(True)
                now.return_value = 140
                with patch.object(engine.activeSlot, 'play') as play:
                    engine.setPaused(False)
                    play.assert_not_called()
                self.assertTrue(engine.isShowingComingUp())
                self.assertTrue(engine.advanceTimer.isActive())
                now.return_value = 920
                with patch.object(engine, '_hardCut') as cut:
                    engine._onAdvanceTimer()
                    self.assertEqual(cut.call_args.args[0], 1)
            finally:
                engine.shutdown(); engine.container.close()

    def test_natural_end_shows_card_and_silences_standby_audio(self):
        with patch('smdb.RetroChannelWidget.time.monotonic', return_value=0) as now, \
                patch('smdb.RetroChannelWidget.time.time', return_value=36000) as wall, \
                patch('smdb.RetroChannelWidget.random.uniform', return_value=0):
            tv = RetroChannelWidget()
            clock = ChannelClock([0, 1], lambda row: 61000, broadcastAligned=True)
            engine = ChannelEngine(1, 'Action', clock, lambda row: None, str)
            tv.channels = [{'clock': clock, 'genre': 'Action', 'rows': [0, 1]}]
            tv.engines = {0: engine}; tv.isActive = True
            engine.currentSlotIndex = 0; engine.currentRow = clock.slotInfo(0)[0]
            player = engine.activeSlot.player
            engine.activeSlot.player = Mock()
            engine.activeSlot.player.mediaStatus.return_value = QMediaPlayer.EndOfMedia
            try:
                now.return_value = 61; wall.return_value = 36061
                engine._onMovieStatus(engine.activeSlot, QMediaPlayer.EndOfMedia)
                self.assertTrue(engine.isShowingComingUp())
                with patch.object(tv.standbyTone, 'start') as tone, patch.object(tv.staticHiss, 'start') as hiss:
                    tv._syncStandbyTone()
                    tone.assert_not_called(); hiss.assert_not_called()
                engine.activeSlot.path = 'film.mp4'; engine.activeSlot._ready = True
                engine.activeSlot._hasPlayingFrame = True
                engine.activeSlot.player.state.return_value = QMediaPlayer.PlayingState
                engine._onSlotReady(engine.activeSlot)
                self.assertTrue(engine.isShowingComingUp())
            finally:
                engine.activeSlot.player = player
                engine.shutdown(); engine.container.close()
                tv.engines = {}; tv.close()

    def test_cyan_cursor_advances_through_gap_and_freezes_when_paused(self):
        with patch('smdb.RetroChannelWidget.time.monotonic', return_value=0) as now, \
                patch('smdb.RetroChannelWidget.time.time', return_value=36000) as wall, \
                patch('smdb.RetroChannelWidget.random.uniform', return_value=0):
            tv = RetroChannelWidget()
            clock = ChannelClock([0, 1], lambda row: 61000, broadcastAligned=True)
            clock.hasManualNavigation = True
            engine = ChannelEngine(1, 'Action', clock, lambda row: None, str)
            tv.channels = [{'clock': clock, 'genre': 'Action', 'rows': [0, 1]}]
            tv.engines = {0: engine}
            engine.currentSlotIndex = 0; engine.currentRow = clock.slotInfo(0)[0]
            engine.activeSlot.duration = 61000
            player = engine.activeSlot.player
            engine.activeSlot.player = Mock()
            engine.activeSlot.player.mediaStatus.return_value = QMediaPlayer.EndOfMedia
            try:
                now.return_value = 61; wall.return_value = 36061
                engine._onMovieStatus(engine.activeSlot, QMediaPlayer.EndOfMedia)
                tv._updatePlaybackMarker()
                self.assertEqual(tv.guideTable.playbackTime, 36061)
                now.return_value = 71
                tv._updatePlaybackMarker()
                self.assertEqual(tv.guideTable.playbackTime, 36071)
                engine.setPaused(True)
                now.return_value = 90
                tv._updatePlaybackMarker()
                self.assertEqual(tv.guideTable.playbackTime, 36071)
                clock.hasManualNavigation = False
                tv._updatePlaybackMarker()
                self.assertIsNone(tv.guideTable.playbackTime)
            finally:
                engine.activeSlot.player = player
                engine.shutdown(); engine.container.close()
                tv.engines = {}; tv.close()

    def test_cyan_cursor_when_joining_gap_without_loaded_film(self):
        with patch('smdb.RetroChannelWidget.time.monotonic', return_value=0) as now, \
                patch('smdb.RetroChannelWidget.time.time', return_value=36000), \
                patch('smdb.RetroChannelWidget.random.uniform', return_value=0):
            tv = RetroChannelWidget()
            clock = ChannelClock([0], lambda row: 61000, broadcastAligned=True)
            clock.hasManualNavigation = True
            engine = ChannelEngine(1, 'Action', clock, lambda row: None, str)
            tv.channels = [{'clock': clock, 'genre': 'Action', 'rows': [0]}]
            tv.engines = {0: engine}
            try:
                now.return_value = 120
                with patch.object(engine, '_startResolve'), patch.object(engine, '_beginPrefetch'):
                    engine._tuneIn()
                self.assertIsNone(engine.currentRow)
                tv._updatePlaybackMarker()
                self.assertEqual(tv.guideTable.playbackTime, 36120)
                now.return_value = 130
                tv._updatePlaybackMarker()
                self.assertEqual(tv.guideTable.playbackTime, 36130)
            finally:
                engine.shutdown(); engine.container.close()
                tv.engines = {}; tv.close()

    def test_remote_rew_ff_seek_gap_and_cross_both_film_boundaries(self):
        with patch('smdb.RetroChannelWidget.time.monotonic', return_value=0) as now, \
                patch('smdb.RetroChannelWidget.time.time', return_value=36000), \
                patch('smdb.RetroChannelWidget.random.uniform', return_value=0):
            tv = RetroChannelWidget()
            clock = ChannelClock([0, 1], lambda row: 61000, broadcastAligned=True)
            engine = ChannelEngine(1, 'Action', clock, lambda row: None, str)
            tv.channels = [{'clock': clock, 'genre': 'Action', 'rows': [0, 1]}]
            tv.engines = {0: engine}
            tv._updateEmptyState()
            try:
                now.return_value = 120
                with patch.object(engine, '_startResolve'), patch.object(engine, '_beginPrefetch'):
                    engine._tuneIn()
                    tv.forwardTenButton.click()
                    tv._updatePlaybackMarker()
                    self.assertEqual(tv.guideTable.playbackTime, 36130)
                    self.assertEqual(engine.advanceTimer.interval(), 770000)
                    tv.forwardTenButton.click()
                    tv.backTenButton.click()
                    tv._updatePlaybackMarker()
                    self.assertEqual(tv.guideTable.playbackTime, 36130)
                    self.assertEqual(tv._videoOsdStatus['seek'][0], (-10, 36130))
                    engine.setPaused(True)
                    tv.backTenButton.click()
                    tv._updatePlaybackMarker()
                    self.assertEqual(tv.guideTable.playbackTime, 36120)
                    self.assertFalse(engine.advanceTimer.isActive())
                    now.return_value = 130
                    tv._updatePlaybackMarker()
                    self.assertEqual(tv.guideTable.playbackTime, 36120)
                    engine.setPaused(False)
                    engine._gapMarkerTime = 36065
                    engine._gapStartedAt = clock._clockNow()
                    with patch.object(engine, '_hardCut', wraps=engine._hardCut) as cut:
                        tv.backTenButton.click()
                        cut.assert_called_once_with(0, 0.0, 55000.0)
                    tv._updatePlaybackMarker()
                    self.assertEqual(tv.guideTable.playbackTime, 36055)
                    self.assertEqual(tv._videoOsdStatus['seek'][0], (-10, 36055))
                    # Rejoin padding near the next quarter-hour boundary.
                    clock._startOverrides.clear()
                    clock.epoch = clock._clockNow() - 895
                    engine._tuneIn()
                    with patch.object(engine, '_hardCut', wraps=engine._hardCut) as cut:
                        tv.forwardTenButton.click()
                        cut.assert_called_once_with(1, 0.0, 5000.0)
                    tv._updatePlaybackMarker()
                    self.assertEqual(tv.guideTable.playbackTime, 36905)
                    self.assertEqual(tv._videoOsdStatus['seek'][0], (10, 36905))
            finally:
                engine.shutdown(); engine.container.close()
                tv.engines = {}; tv.close()

    def test_rew_crosses_film_start_and_repeats_lineup_before_first_airing(self):
        with patch('smdb.RetroChannelWidget.time.monotonic', return_value=0), \
                patch('smdb.RetroChannelWidget.time.time', return_value=36000), \
                patch('smdb.RetroChannelWidget.random.uniform', return_value=0):
            tv = RetroChannelWidget()
            clock = ChannelClock([0, 1], lambda row: 61000, broadcastAligned=True)
            original = list(clock.publishedPrograms(34000, 40000))
            engine = ChannelEngine(1, 'Action', clock, lambda row: None, str)
            tv.channels = [{'clock': clock, 'genre': 'Action', 'rows': [0, 1]}]
            tv.engines = {0: engine}; tv._updateEmptyState()
            slot = engine.activeSlot
            player = slot.player
            slot.player = Mock()
            try:
                with patch.object(engine, '_startResolve'), patch.object(engine, '_beginPrefetch'):
                    for current, expected in ((1, 36895), (0, 35995)):
                        engine.currentSlotIndex = current
                        engine.currentRow = clock.slotInfo(current)[0]
                        slot.path = 'movie.mp4'; slot._ready = True
                        slot.duration = 61000; slot._lastPlaybackPosition = 5000
                        engine._stack.setCurrentWidget(slot.videoWidget)
                        tv.backTenButton.click()
                        tv._updatePlaybackMarker()
                        self.assertEqual(tv.guideTable.playbackTime, expected)
                        self.assertTrue(engine.isShowingComingUp())
                        self.assertEqual(engine.currentSlotIndex, current - 1)
                        self.assertEqual(clock.whatsOnNow()[0], current - 1)
                        tv.backTenButton.click()
                        tv._updatePlaybackMarker()
                        self.assertEqual(tv.guideTable.playbackTime, expected - 10)
                    self.assertEqual(original, list(clock.publishedPrograms(34000, 40000)))
                    # Going forward across the repeat boundary returns to film zero.
                    with patch.object(engine, '_hardCut', wraps=engine._hardCut) as cut:
                        engine._seekFromGap(20000)
                        cut.assert_called_once_with(0, 0.0, 5000.0)
                    tv._updatePlaybackMarker()
                    self.assertEqual(tv.guideTable.playbackTime, 36005)
            finally:
                slot.player = player
                engine.shutdown(); engine.container.close()
                tv.engines = {}; tv.close()

    def test_rew_loads_previous_film_when_no_padding_separates_films(self):
        with patch('smdb.RetroChannelWidget.time.monotonic', return_value=0), \
                patch('smdb.RetroChannelWidget.time.time', return_value=36000), \
                patch('smdb.RetroChannelWidget.random.uniform', return_value=0):
            tv = RetroChannelWidget()
            clock = ChannelClock([0, 1], lambda row: 900000, broadcastAligned=True)
            engine = ChannelEngine(1, 'Action', clock, lambda row: None, str)
            tv.channels = [{'clock': clock, 'genre': 'Action', 'rows': [0, 1]}]
            tv.engines = {0: engine}; tv._updateEmptyState()
            slot = engine.activeSlot; player = slot.player; slot.player = Mock()
            try:
                engine.currentSlotIndex = 1; engine.currentRow = clock.slotInfo(1)[0]
                leaving = engine.currentRow
                slot.path = 'movie.mp4'; slot._ready = True
                slot.duration = 900000; slot._lastPlaybackPosition = 5000
                engine._stack.setCurrentWidget(slot.videoWidget)
                with patch.object(engine, '_startResolve'), patch.object(engine, '_beginPrefetch'), \
                        patch.object(engine, '_hardCut', wraps=engine._hardCut) as cut:
                    tv.backTenButton.click()
                    cut.assert_called_once_with(0, 0.0, 895000.0)
                    tv._updatePlaybackMarker()
                    self.assertEqual(tv.guideTable.playbackTime, 36895)
                    self.assertEqual(clock._resumePositions[leaving][2], 5000)
                    engine.currentRow = clock.slotInfo(0)[0]
                    slot.path = 'previous.mp4'; slot._ready = True
                    slot.duration = 900000; slot._lastPlaybackPosition = 895000
                    slot._hasPlayingFrame = True
                    slot.player.state.return_value = QMediaPlayer.PlayingState
                    slot.player.mediaStatus.return_value = QMediaPlayer.BufferedMedia
                    engine._onSlotReady(slot)
                    tv._updatePlaybackMarker()
                    self.assertEqual(tv.guideTable.playbackTime, 36895)
                    self.assertIsNone(engine._pendingTimelineSeek)
                    cut.reset_mock()
                    tv.forwardTenButton.click()
                    cut.assert_called_once_with(1, 0.0, 5000.0)
                    tv._updatePlaybackMarker()
                    self.assertEqual(tv.guideTable.playbackTime, 36905)
            finally:
                slot.player = player
                engine.shutdown(); engine.container.close()
                tv.engines = {}; tv.close()


if __name__ == '__main__':
    unittest.main()
