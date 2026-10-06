import os
import time
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

    def test_return_to_live_restores_published_slot_and_padding_after_navigation(self):
        with patch('smdb.RetroChannelWidget.time.time', return_value=36000) as wall, \
                patch('smdb.RetroChannelWidget.time.monotonic', return_value=0), \
                patch('smdb.RetroChannelWidget.random.uniform', return_value=0):
            clock = ChannelClock([0, 1], lambda row: 61 * 60000, broadcastAligned=True)
            original = list(clock.publishedPrograms(36000, 86400))
            clock.repositionSlot(0, clock._rotation[0], 3660000, 3500000)
            clock.hasManualNavigation = True
            wall.return_value = 40500 + 300
            clock.returnToLive()
            slot, row, fraction, position, remaining = clock.whatsOnNow()
            self.assertEqual((slot, fraction, position, remaining), (1, 0, 300000, 4200000))
            self.assertFalse(clock.hasManualNavigation)
            self.assertEqual(original, list(clock.publishedPrograms(36000, 86400)))
            wall.return_value = 36000 + 62 * 60
            clock.returnToLive()
            self.assertGreater(clock.whatsOnNow()[3], clock.filmDurationForSlot(0))
            self.assertEqual(clock.whatsOnNow()[4], 13 * 60000)

    def test_now_button_restores_selected_channel_and_recenters_guide(self):
        tv = RetroChannelWidget()
        with patch('smdb.RetroChannelWidget.time.time', return_value=36000) as wall, \
                patch('smdb.RetroChannelWidget.time.monotonic', return_value=0), \
                patch('smdb.RetroChannelWidget.random.uniform', return_value=0):
            clock = ChannelClock([0, 1, 2], lambda row: 1800000, broadcastAligned=True)
            neighbor = ChannelClock([3], lambda row: 1800000, broadcastAligned=True)
            tv.channels = [{'genre': 'Action', 'clock': clock, 'rows': [0, 1, 2]},
                           {'genre': 'Adventure', 'clock': neighbor, 'rows': [3]}]
            tv.guideVisible = True
            tv._updateEmptyState()
            engine = tv._createEngine(0)
            tv.engines[0] = engine
            originalPlayer = engine.activeSlot.player
            engine.activeSlot.player = Mock()
            engine.activeSlot.player.position.return_value = 600000
            engine.activeSlot.player.state.return_value = QMediaPlayer.PlayingState
            clock.repositionSlot(0, clock._rotation[0], 1800000, 600000)
            clock.hasManualNavigation = True
            wall.return_value = 39900
            tv.guideTable.startTime = 36000
            tv.guideTable.endTime = 36000 + 48 * 3600
            tv.guideTable.horizontalScrollBar().setValue(3000)
            def loadLive(path, autoplay=False, seekFraction=None, extraMs=0):
                slot = engine.activeSlot
                slot.path, slot.duration, slot._ready = path, 1800000, True
                slot.seekTo(seekFraction, extraMs)
                slot._hasPlayingFrame = True
                engine._onSlotReady(slot)
            try:
                with patch.object(engine, '_startResolve', side_effect=lambda idx, attr, done:
                                  done(clock._rowForSlot(idx), 'movie.mp4')), \
                        patch.object(engine.activeSlot, 'load', side_effect=loadLive) as load, \
                        patch.object(engine, '_maybeSchedulePrefetch'), \
                        patch.object(engine, '_onMovieDuration'):
                    tv.nowButton.click()
                    self.assertEqual(engine.currentSlotIndex, 2)
                    self.assertEqual(load.call_args.kwargs['extraMs'], 300000)
                    self.assertEqual(load.call_args.kwargs['seekFraction'], 0)
                    self.assertFalse(clock.hasManualNavigation)
                    self.assertIsNone(tv.guideTable.playbackTime)
                    center = (tv.guideTable.channelWidth + tv.guideTable.viewport().width()) / 2
                    if tv.guideTable.viewport().width() > tv.guideTable.channelWidth:
                        self.assertAlmostEqual(tv.guideTable.timeX(wall.return_value), center, delta=0.5)
                    self.assertEqual(neighbor.epoch, 0)
                    self.assertEqual(neighbor._startOverrides, {})
                    # The backend still reports the older skipped-to position.
                    # Relative seeks must use NOW's freshly recorded live seek.
                    for button, seconds in ((tv.forwardTenButton, 10), (tv.backTenButton, -10),
                                            (tv.forwardTenButton, 10)):
                        tv.nowButton.click()
                        button.click()
                        self.assertEqual(engine.activeSlot._lastPlaybackPosition, 300000 + seconds * 1000)
                        self.assertEqual(tv.guideTable.playbackTime, wall.return_value + seconds)
                    tv.forwardTenButton.click()
                    self.assertEqual(tv.guideTable.playbackTime, wall.return_value + 20)
            finally:
                engine.activeSlot.player = originalPlayer
                tv.close()

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
            self.assertEqual(before.pixelColor(guide.channelWidth + guide.hourWidth - 15, guide.labelHeight + 5).name(), '#ffcc00')
            guide.setCurrentTime(39601)
            after = guide.viewport().grab().toImage()
            self.assertEqual(after.pixelColor(guide.channelWidth + guide.hourWidth - 15, guide.labelHeight + 5).name(), '#123b57')
            self.assertEqual(after.pixelColor(guide.channelWidth + 2 * guide.hourWidth - 15, guide.labelHeight + 5).name(), '#ffcc00')
            self.assertEqual(after.pixelColor(guide.channelWidth + 2, guide.labelHeight + 2).name(), '#050531')
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
                                 start + position / 1000)
                self.assertEqual(tv.guideTable.now, 1234567890)
            cursorTime = time.strftime('%I:%M:%S %p', time.localtime(tv.guideTable.playbackTime))
            self.assertEqual(cursorTime, tv.guideTable.markerLabel(tv.guideTable.playbackTime))
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

    def test_now_then_seeking_uses_real_seconds_when_catalogue_runtime_differs(self):
        tv = RetroChannelWidget()
        with patch('smdb.RetroChannelWidget.time.time', return_value=36000) as wall, \
                patch('smdb.RetroChannelWidget.time.monotonic', return_value=0), \
                patch('smdb.RetroChannelWidget.random.uniform', return_value=0):
            # At one hour elapsed, the previous ratio mapping put the cursor
            # four minutes 48 seconds ahead when the file is only 100 minutes.
            clock = ChannelClock([0], lambda row: 108 * 60000, broadcastAligned=True)
            published = list(clock.publishedPrograms(36000, 86400))
            tv.channels = [{'genre': 'Action', 'clock': clock, 'rows': [0]}]
            tv.guideVisible = True
            tv._updateEmptyState()
            engine = tv._createEngine(0)
            tv.engines[0] = engine
            slot, originalPlayer = engine.activeSlot, engine.activeSlot.player
            slot.player = Mock()
            slot.player.state.return_value = QMediaPlayer.PlayingState
            slot.player.position.return_value = 1800000  # deliberately stale
            def loadLive(path, autoplay=False, seekFraction=None, extraMs=0):
                slot.path, slot.duration, slot._ready = path, 100 * 60000, True
                slot.seekTo(seekFraction, extraMs)
                slot._hasPlayingFrame = True
                engine._onSlotReady(slot)
            wall.return_value = 39600
            try:
                with patch.object(engine, '_startResolve', side_effect=lambda idx, attr, done: done(0, 'movie.mp4')), \
                        patch.object(slot, 'load', side_effect=loadLive), \
                        patch.object(engine, '_maybeSchedulePrefetch'):
                    tv.nowButton.click()
                    self.assertEqual(slot._lastPlaybackPosition, 3600000)
                    self.assertIsNone(tv.guideTable.playbackTime)
                    tv.forwardTenButton.click()
                    self.assertEqual(tv.guideTable.playbackTime, 39610)
                    tv.forwardTenButton.click()
                    self.assertEqual(tv.guideTable.playbackTime, 39620)
                    tv.backTenButton.click()
                    self.assertEqual(tv.guideTable.playbackTime, 39610)
                    tv.nowButton.click()
                    tv.backTenButton.click()
                    self.assertEqual(tv.guideTable.playbackTime, 39590)
                    tv.beginningButton.click()
                    self.assertEqual(tv.guideTable.playbackTime, 36000)
                    tv.nextBeginningButton.click()
                    self.assertEqual(tv.guideTable.playbackTime, 39590)
                    # An overrun is truthful seconds beyond the estimate; it
                    # must not be compressed to fit the unchanged film block.
                    slot.duration = 120 * 60000
                    slot._onPlaybackPosition(110 * 60000)
                    tv._updatePlaybackMarker()
                    self.assertEqual(tv.guideTable.playbackTime, 36000 + 110 * 60)
                    self.assertEqual(published, list(clock.publishedPrograms(36000, 86400)))
                    self.assertEqual(tv.guideTable.now, 39600)
            finally:
                slot.player = originalPlayer
                tv.close()

    def test_horizontal_view_follows_cursor_both_directions_and_extends_time_range(self):
        guide = GuideTimeline()
        guide.resize(900, 260)
        guide.startTime, guide.endTime = 36000, 36000 + 48 * 3600
        guide.setCurrentTime(36900)
        program = {'slot': 0, 'row': 0, 'start': 36000, 'end': 39600,
                   'title': 'Fixed program', 'playing': True}
        guide.setRows([{'channel': 0, 'label': '01 ACTION', 'programs': [program]}], 0)
        guide.show()
        self.app.processEvents()
        changed = Mock()
        guide.timeRangeChanged.connect(changed)
        try:
            for timestamp in (36900, 36000 + 8 * 3600, 36000 + 9 * 3600,
                              36000 + 3600, 36000 - 4 * 3600, 36000 + 60 * 3600):
                guide.setPlaybackTime(timestamp)
                self.assertGreater(guide.timeX(timestamp), guide.channelWidth)
                self.assertLess(guide.timeX(timestamp), guide.viewport().width())
                self.assertEqual(guide.now, 36900)
                self.assertEqual((program['start'], program['end']), (36000, 39600))
            self.assertLessEqual(guide.startTime, 36000 - 4 * 3600)
            self.assertGreater(guide.endTime, 36000 + 60 * 3600)
            self.assertGreaterEqual(changed.call_count, 2)
            guide.resize(600, 260)
            self.app.processEvents()
            self.assertLess(guide.timeX(guide.playbackTime), guide.viewport().width())
            scroll = guide.horizontalScrollBar().value()
            guide.setPlaybackTime(None)
            guide.setCurrentTime(37000)
            self.assertEqual(guide.horizontalScrollBar().value(), scroll)
        finally:
            guide.close()

    def test_live_marker_starts_centered_and_stays_centered_after_layout_and_scale(self):
        guide = GuideTimeline()
        guide.startTime = 36000
        guide.endTime = 36000 + 48 * 3600
        guide.setCurrentTime(36300)
        guide.showCurrentHour()  # initial call before the visible layout settles
        guide.resize(1400, 300)
        guide.show()
        self.app.processEvents()
        try:
            for scale, width in ((1, 1400), (2, 1000), (1, 700)):
                guide.setScale(scale)
                guide.resize(width, 300)
                self.app.processEvents()
                center = (guide.channelWidth + guide.viewport().width()) / 2
                self.assertAlmostEqual(guide.timeX(guide.now), center, delta=0.5)
                self.assertLess(guide.startTime, 36000)
            guide.setPlaybackTime(36000 + 10 * 3600)
            guide.resize(600, 300)
            self.app.processEvents()
            self.assertGreater(guide.timeX(guide.playbackTime), guide.channelWidth)
            self.assertLess(guide.timeX(guide.playbackTime), guide.viewport().width())
        finally:
            guide.close()

    def test_cursor_labels_and_ticks_are_above_hour_blocks_without_old_banners(self):
        tv = RetroChannelWidget()
        guide = GuideTimeline()
        guide.startTime = 36000
        guide.endTime = 36000 + 48 * 3600
        guide.setCurrentTime(36900)
        guide.setPlaybackTime(38700)
        guide.resize(900, 260)
        guide.show()
        self.app.processEvents()
        try:
            image = guide.viewport().grab().toImage()
            for timestamp, color in ((guide.now, '#ffcc00'), (guide.playbackTime, '#00ffff')):
                x = round(guide.timeX(timestamp))
                self.assertEqual(image.pixelColor(x, guide.labelHeight + 3).name(), color)
                self.assertEqual(image.pixelColor(x, guide.headerHeight - 3).name(), color)
                # Windows' offscreen plugin does not render font glyphs; native
                # runs verify the small antialiased time labels as well.
                if self.app.platformName() != 'offscreen':
                    textPixels = (image.pixelColor(px, py)
                                  for py in range(guide.labelHeight)
                                  for px in range(guide.channelWidth, image.width()))
                    self.assertTrue(any(pixel.green() > 80 and
                                        (pixel.red() > 80 and pixel.blue() < 80 if color == '#ffcc00'
                                         else pixel.blue() > 80 and pixel.red() < 80)
                                        for pixel in textPixels))
            self.assertFalse(hasattr(tv, 'guideClockLabel'))
            self.assertFalse(any('Browse channels' in label.text()
                                 for label in tv.guideOverlay.findChildren(QtWidgets.QLabel)))
        finally:
            guide.close()
            tv.close()

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
                tv.previousProgramButton.click()
                self.app.processEvents()
                start, end = clock.publishedSlotTimes(1)
                self.assertEqual(clock.playbackOriginForSlot(1), 0.0)
                self.assertAlmostEqual(tv.guideTable.playbackTime, start + 10001 / 1000, delta=0.002)
                tv.beginningButton.click()
                self.assertEqual(tv.guideTable.playbackTime, start)
                tv.nextBeginningButton.click()
                self.assertAlmostEqual(tv.guideTable.playbackTime, start + 10001 / 1000, delta=0.002)
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
