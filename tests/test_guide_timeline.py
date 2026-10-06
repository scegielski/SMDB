import os
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt5 import QtCore, QtWidgets
from PyQt5.QtMultimedia import QMediaPlayer
from smdb.RetroChannelWidget import ChannelClock, ChannelEngine, RetroChannelWidget
from smdb.GuideTimeline import GuideTimeline


class GuideTimelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_initial_random_join_uses_full_film_beginning_and_runtime(self):
        with patch('smdb.RetroChannelWidget.time.time', return_value=36420), \
                patch('smdb.RetroChannelWidget.time.monotonic', return_value=0), \
                patch('smdb.RetroChannelWidget.random.uniform', return_value=0.5):
            clock = ChannelClock([0, 1], lambda row: 120 * 60000, broadcastAligned=True)
            start, end = clock.publishedSlotTimes(0)
            self.assertEqual(start, 32400)
            self.assertEqual(end - start, 120 * 60)
            slot, row, fraction, position, remaining = clock.whatsOnNow()
            self.assertEqual(slot, 0)
            self.assertEqual(fraction, 0)
            self.assertEqual(position, (36420 - start) * 1000)
            self.assertEqual(start + position / 1000, 36420)
            self.assertEqual(remaining, (end - 36420) * 1000)
            self.assertEqual(clock.publishedSlotTimes(1)[0], end)
            clock.jumpToSlot(1)
            self.assertEqual(clock.whatsOnNow()[2], 0)

    def test_quarter_hour_starts_padding_and_repeating_blocks_are_immutable(self):
        with patch('smdb.RetroChannelWidget.time.time', return_value=36000 + 7 * 60), \
                patch('smdb.RetroChannelWidget.random.uniform', return_value=0):
            clock = ChannelClock([0, 1], lambda row: 61 * 60000)
            self.assertTrue(all(start % 900 == 0 for start in clock._scheduleStarts))
            self.assertEqual(clock._scheduleEnds[0] - clock._scheduleStarts[0], 61 * 60)
            self.assertEqual(clock._scheduleStarts[1] - clock._scheduleEnds[0], 14 * 60)
            original = list(clock.publishedPrograms(36000, 36000 + 6 * 3600))
            clock.repositionSlot(1, clock._rotation[1], 600000, 300000)
            clock.recordMedia(0, clock._rotation[0], 900000)
            self.assertEqual(original, list(clock.publishedPrograms(36000, 36000 + 6 * 3600)))
            self.assertEqual(original[2]['row'], original[0]['row'])
            self.assertEqual(original[2]['start'] % 900, 0)

    def test_hour_highlight_uses_wall_time_and_geometry_tracks_film_length(self):
        guide = GuideTimeline()
        guide.startTime = 36000
        guide.endTime = 36000 + 48 * 3600
        guide.resize(900, 300)
        guide.setRows([{'channel': 0, 'label': '01 ACTION', 'programs': [
            {'start': 36000, 'end': 37800, 'title': 'Half hour', 'playing': False},
            {'start': 37800, 'end': 41400, 'title': 'One hour', 'playing': True}]}], 0)
        guide.show()
        self.app.processEvents()
        try:
            first, second = guide.rows[0]['programs']
            self.assertEqual(guide.programRect(0, second).width(), guide.programRect(0, first).width() * 2)
            guide.setCurrentTime(36500)
            before = guide.viewport().grab().toImage()
            self.assertEqual(before.pixelColor(guide.channelWidth + 5, 3).name(), '#ffcc00')
            guide.setCurrentTime(39601)
            after = guide.viewport().grab().toImage()
            self.assertEqual(after.pixelColor(guide.channelWidth + 5, 3).name(), '#1a1aae')
            self.assertEqual(after.pixelColor(guide.channelWidth + guide.hourWidth + 5, 3).name(), '#ffcc00')
        finally:
            guide.close()

    def test_program_navigation_only_moves_highlight_in_timeline(self):
        tv = RetroChannelWidget()
        clock = ChannelClock([0, 1, 2], lambda row: 120 * 60000)
        tv.channels = [{'genre': 'Action', 'clock': clock, 'rows': [0, 1, 2]}]
        engine = Mock(currentSlotIndex=0, currentRow=clock._rotation[0])
        engine.currentTitle = 'Movie'
        engine.isShowingStandby.return_value = False
        tv.engines[0] = engine
        try:
            with patch.object(tv, '_titleForRow', side_effect=str):
                tv._refreshGuideTable()
                before = [(block['slot'], block['row'], block['start'], block['end'], block['title'])
                          for block in tv.guideTable.rows[0]['programs']]
                scroll = tv.guideTable.horizontalScrollBar().value()
                for target in (1, 0, 2):
                    clock.jumpToSlot(target)
                    engine.currentSlotIndex = target
                    engine.currentRow = clock._rotation[target]
                    tv._refreshGuideTable()
                    blocks = tv.guideTable.rows[0]['programs']
                    self.assertEqual(before, [(b['slot'], b['row'], b['start'], b['end'], b['title']) for b in blocks])
                    self.assertEqual([b['slot'] for b in blocks if b['playing']], [target])
                    self.assertEqual(tv.guideTable.horizontalScrollBar().value(), scroll)
        finally:
            tv.engines = {}
            tv.close()

    def test_natural_end_waits_for_quarter_hour_without_cutting_active_film(self):
        with patch('smdb.RetroChannelWidget.time.monotonic', return_value=0) as monotonic, \
                patch('smdb.RetroChannelWidget.time.time', return_value=36000) as wall, \
                patch('smdb.RetroChannelWidget.random.uniform', return_value=0):
            clock = ChannelClock([0, 1], lambda row: 61000, broadcastAligned=True)
            engine = ChannelEngine(1, 'Action', clock, lambda row: None, str)
            engine.currentRow = clock._rotation[0]
            engine.currentSlotIndex = 0
            realPlayer = engine.activeSlot.player
            engine.activeSlot.player = Mock()
            try:
                monotonic.return_value = 61
                wall.return_value = 36061
                engine.activeSlot.player.mediaStatus.return_value = QMediaPlayer.EndOfMedia
                with patch.object(engine, '_hardCut') as cut:
                    engine._onMovieStatus(engine.activeSlot, QMediaPlayer.EndOfMedia)
                    cut.assert_not_called()
                    self.assertEqual(engine.advanceTimer.interval(), 839000)
                    monotonic.return_value = 900
                    wall.return_value = 36900
                    engine._onAdvanceTimer()
                    self.assertEqual(cut.call_args.args[0], 1)
            finally:
                engine.activeSlot.player = realPlayer
                engine.shutdown()
                engine.container.close()

    def test_tuning_during_padding_waits_instead_of_replaying_last_frames(self):
        with patch('smdb.RetroChannelWidget.time.monotonic', return_value=0) as monotonic, \
                patch('smdb.RetroChannelWidget.time.time', return_value=36000), \
                patch('smdb.RetroChannelWidget.random.uniform', return_value=0):
            clock = ChannelClock([0], lambda row: 61000, broadcastAligned=True)
            engine = ChannelEngine(1, 'Action', clock, lambda row: None, str)
            try:
                monotonic.return_value = 120
                with patch.object(engine, '_startResolve') as resolve, patch.object(engine, '_beginPrefetch'):
                    engine._tuneIn()
                    resolve.assert_not_called()
                    self.assertIsNone(engine.currentRow)
                    self.assertTrue(engine.isShowingStandby())
                    self.assertEqual(engine.advanceTimer.interval(), 780000)
            finally:
                engine.shutdown()
                engine.container.close()

    def test_playback_cursor_tracks_actual_position_without_shifting_clock_or_blocks(self):
        tv = RetroChannelWidget()
        clock = ChannelClock([0, 1], lambda row: 120000)
        tv.channels = [{'genre': 'Action', 'clock': clock, 'rows': [0, 1]}]
        engine = Mock(currentSlotIndex=0, currentRow=clock._rotation[0], clock=clock)
        engine.activeSlot.duration = 120000
        engine.activeSlot._lastPlaybackPosition = 60000
        engine.isShowingStandby.return_value = False
        tv.engines[0] = engine
        try:
            tv.guideTable.setCurrentTime(1234567890)
            original = list(clock.publishedPrograms(clock._scheduleStarts[0], clock._scheduleStarts[0] + 86400))
            tv._updatePlaybackMarker()
            self.assertIsNone(tv.guideTable.playbackTime)
            clock.hasManualNavigation = True
            for slot, position in ((0, 60000), (1, 30000), (0, 0), (0, 90000)):
                engine.currentSlotIndex = slot
                engine.activeSlot._lastPlaybackPosition = position
                tv._updatePlaybackMarker()
                start, end = clock.publishedSlotTimes(slot)
                self.assertEqual(tv.guideTable.playbackTime,
                                 start + (end - start) * position / 120000)
                self.assertEqual(tv.guideTable.now, 1234567890)
            self.assertIn('Playback 00:01:30', tv.guideClockLabel.text())
            engine.activeSlot.player.position.assert_not_called()
            self.assertEqual(original, list(clock.publishedPrograms(clock._scheduleStarts[0], clock._scheduleStarts[0] + 86400)))
            engine.isShowingStandby.return_value = True
            tv._updatePlaybackMarker()
            self.assertIsNone(tv.guideTable.playbackTime)
        finally:
            tv.engines = {}
            tv.close()

    def test_ten_second_seek_moves_cursor_ten_seconds_from_original_random_start(self):
        tv = RetroChannelWidget()
        with patch('smdb.RetroChannelWidget.random.uniform', return_value=0.5):
            clock = ChannelClock([0], lambda row: 120000)
        tv.channels = [{'genre': 'Action', 'clock': clock, 'rows': [0]}]
        clock.hasManualNavigation = True
        engine = Mock(currentSlotIndex=0, currentRow=0)
        engine.activeSlot.duration = 120000
        engine.isShowingStandby.return_value = False
        tv.engines[0] = engine
        try:
            start = clock._scheduleStarts[0]
            tv.guideTable.setCurrentTime(start + 75)
            engine.activeSlot._lastPlaybackPosition = 75000
            tv._updatePlaybackMarker()
            self.assertEqual(tv.guideTable.playbackTime, tv.guideTable.now)
            engine.activeSlot._lastPlaybackPosition = 85000
            tv._updatePlaybackMarker()
            self.assertEqual(tv.guideTable.playbackTime, tv.guideTable.now + 10)
        finally:
            tv.engines = {}
            tv.close()

    def test_playback_cursor_is_cyan_and_wall_clock_line_stays_yellow(self):
        guide = GuideTimeline()
        guide.resize(900, 260)
        guide.startTime = 36000
        guide.endTime = 36000 + 48 * 3600
        guide.setCurrentTime(36900)
        guide.setPlaybackTime(38700)
        guide.show()
        self.app.processEvents()
        try:
            image = guide.viewport().grab().toImage()
            y = guide.headerHeight + 50
            self.assertEqual(image.pixelColor(round(guide.timeX(36900)), y).name(), '#ffcc00')
            self.assertEqual(image.pixelColor(round(guide.timeX(38700)), y).name(), '#00ffff')
            guide.setPlaybackTime(None)
            image = guide.viewport().grab().toImage()
            self.assertNotEqual(image.pixelColor(round(guide.timeX(38700)), y).name(), '#00ffff')
        finally:
            guide.close()

    def test_first_frame_queues_guide_refresh_without_querying_media_position(self):
        tv = RetroChannelWidget()
        clock = ChannelClock([0, 1], lambda row: 120000)
        tv.channels = [{'genre': 'Action', 'clock': clock, 'rows': [0, 1]}]
        tv.guideVisible = True
        clock.hasManualNavigation = True
        engine = tv._createEngine(0)
        tv.engines[0] = engine
        engine.currentSlotIndex = 1
        engine.currentRow = clock._rotation[1]
        slot = engine.activeSlot
        realPlayer = slot.player
        slot.player = Mock()
        slot.player.state.return_value = QMediaPlayer.PlayingState
        slot.player.position.side_effect = AssertionError('Media position must not be queried in a frame callback')
        slot.duration = 120000
        slot.path = 'movie.mp4'
        slot._ready = True
        slot._lastPlaybackPosition = 45000
        try:
            tv._refreshGuideTable()
            self.assertIsNone(tv.guideTable.playbackTime)
            slot._onVideoFrame(Mock(isValid=lambda: True))
            self.assertIsNone(tv.guideTable.playbackTime)  # refresh waits for the callback to return
            self.app.processEvents()
            self.assertIsNotNone(tv.guideTable.playbackTime)
            self.assertEqual([b['slot'] for b in tv.guideTable.rows[0]['programs'] if b['playing']], [1])
            slot.player.position.assert_not_called()
        finally:
            slot.player = realPlayer
            tv.close()

    def test_first_next_start_click_places_cursor_at_destination_block_and_resume_preserves_origin(self):
        tv = RetroChannelWidget()
        with patch('smdb.RetroChannelWidget.random.uniform', return_value=0.8):
            clock = ChannelClock([0, 1, 2], lambda row: 120000, broadcastAligned=True)
        tv.channels = [{'genre': 'Action', 'clock': clock, 'rows': [0, 1, 2]}]
        tv.guideVisible = True
        tv._updateEmptyState()
        engine = tv._createEngine(0)
        tv.engines[0] = engine
        engine.currentSlotIndex = 0
        engine.currentRow = clock._rotation[0]
        originals = [slot.player for slot in (engine.slotA, engine.slotB)]
        for slot in (engine.slotA, engine.slotB):
            slot.player = Mock()
            slot.player.state.return_value = QMediaPlayer.PlayingState
            slot.player.mediaStatus.return_value = QMediaPlayer.BufferedMedia
            slot.player.position.return_value = 96000
        def resolve(index, attr, callback):
            callback(clock._rowForSlot(index), 'movie.mp4')
        def load(path, autoplay=False, seekFraction=None, extraMs=0):
            slot = engine.activeSlot
            slot.path, slot.duration, slot._ready = path, 120000, True
            slot._lastPlaybackPosition = int(seekFraction * slot.duration + extraMs)
            slot.player.position.return_value = slot._lastPlaybackPosition
            slot._hasPlayingFrame = True
            engine._onSlotReady(slot)
        try:
            with patch.object(engine, '_startResolve', side_effect=resolve), \
                    patch.object(engine.activeSlot, 'load', side_effect=load), \
                    patch.object(engine, '_maybeSchedulePrefetch'):
                for target in (1, 2):
                    tv.nextBeginningButton.click()
                    self.app.processEvents()
                    start, end = clock.publishedSlotTimes(target)
                    self.assertEqual(engine.currentSlotIndex, target)
                    self.assertEqual(clock.playbackOriginForSlot(target), 0.0)
                    self.assertGreaterEqual(tv.guideTable.playbackTime, start)
                    self.assertLess(tv.guideTable.playbackTime, start + 0.01)
                    self.assertEqual([b['slot'] for b in tv.guideTable.rows[0]['programs'] if b['playing']], [target])
                    tv.forwardTenButton.click()
                    engine.activeSlot.player.position.return_value = engine.activeSlot._lastPlaybackPosition
                tv.beginningButton.click()
                self.app.processEvents()
                start, end = clock.publishedSlotTimes(1)
                self.assertEqual(clock.playbackOriginForSlot(1), 0.0)
                self.assertAlmostEqual(tv.guideTable.playbackTime, start + (end - start) * 10001 / 120000, delta=0.002)
                tv.beginningButton.click()
                self.assertEqual(tv.guideTable.playbackTime, start)
                tv.nextBeginningButton.click()
                self.assertAlmostEqual(tv.guideTable.playbackTime, start + (end - start) * 10001 / 120000, delta=0.002)
        finally:
            for slot, original in zip((engine.slotA, engine.slotB), originals):
                slot.player = original
            tv.close()

    def test_beginning_then_resume_restores_the_original_cursor_location(self):
        with patch('smdb.RetroChannelWidget.random.uniform', return_value=0.5):
            clock = ChannelClock([0], lambda row: 100000)
        engine = ChannelEngine(1, 'Action', clock, lambda row: None, str)
        engine.currentSlotIndex = engine._previousNavigationSlot = 0
        engine.currentRow = 0
        clock.rememberPosition(0, 0, 100000, 90000)
        slot = engine.activeSlot
        realPlayer = slot.player
        slot.player = Mock()
        slot.duration, slot.path, slot._ready = 100000, 'movie.mp4', True
        slot.player.position.return_value = 90000
        try:
            with patch.object(engine, '_maybeSchedulePrefetch'):
                engine.skipProgram(-1)
                self.assertEqual(clock.playbackOriginForSlot(0), 0.0)
                self.assertEqual(slot._lastPlaybackPosition, 0)
                engine.skipProgram(1)
                self.assertEqual(clock.playbackOriginForSlot(0), 0.5)
                self.assertEqual(slot._lastPlaybackPosition, 90000)
        finally:
            slot.player = realPlayer
            engine.shutdown()
            engine.container.close()


if __name__ == '__main__':
    unittest.main()
