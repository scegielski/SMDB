import os
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt5 import QtWidgets
from PyQt5.QtMultimedia import QMediaPlayer
from smdb.RetroChannelWidget import ChannelClock, ChannelEngine, RetroChannelWidget


class FullMovieScheduleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def enableControls(self, tv):
        for button in tv.sideControls.findChildren(QtWidgets.QPushButton):
            button.setEnabled(True)

    def test_schedule_uses_movie_lengths_and_rejoins_in_progress(self):
        with patch('smdb.RetroChannelWidget.time.monotonic', return_value=0) as now:
            clock = ChannelClock([0, 1], lambda row: [120000, 300000][row])
            clock._rotation = [0, 1]
            clock._offsetFractions = {0: 0.0, 1: 0.0}
            now.return_value = 61
            self.assertEqual(clock.whatsOnNow(), (0, 0, 0.0, 61000, 59000))
            now.return_value = 150
            self.assertEqual(clock.whatsOnNow(), (1, 1, 0.0, 30000, 270000))
            clock.recordMedia(1, 1, 360000)
            self.assertEqual(clock.whatsOnNow()[-1], 330000)

    def test_random_start_is_stable_and_schedule_uses_remaining_duration(self):
        with patch('smdb.RetroChannelWidget.time.monotonic', return_value=0) as now, \
                patch('smdb.RetroChannelWidget.random.uniform', return_value=0.5):
            clock = ChannelClock([0], lambda row: 120000)
            now.return_value = 10
            self.assertEqual(clock.whatsOnNow(), (0, 0, 0.5, 10000, 50000))
            self.assertEqual(clock.slotInfo(0), (0, 0.5))
            clock.recordMedia(0, 0, 180000)
            self.assertEqual(clock.whatsOnNow()[-1], 80000)
            now.return_value = 95
            clock.finishSlot(0)
            self.assertEqual(clock.whatsOnNow()[0], 1)

    def test_twenty_five_movie_lineup_repeats_and_smaller_category_uses_all(self):
        for available, expected in ((40, 25), (12, 12)):
            clock = ChannelClock(range(available), lambda row: 120000)
            first = [clock.slotInfo(i) for i in range(expected)]
            self.assertEqual(len({row for row, _ in first}), expected)
            self.assertEqual(first, [clock.slotInfo(i + expected) for i in range(expected)])

    def test_guide_schedule_lists_the_selected_channel_lineup(self):
        tv = RetroChannelWidget()
        try:
            clock = ChannelClock(range(30), lambda row: 120000)
            channel = {'genre': 'Action', 'rows': list(range(30)), 'clock': clock}
            with patch.object(tv, '_titleForRow', side_effect=lambda row: f'Movie {row}'):
                tv._refreshScheduleTable(channel)
            self.assertEqual(tv.scheduleTable.rowCount(), 25)
            self.assertNotEqual(tv.scheduleTable.item(0, 1).text(), 'NOW')
            self.assertEqual(tv.scheduleTable.item(24, 2).text(), f'Movie {clock.slotInfo(24)[0]}')
            self.assertEqual(tv.guidePages.tabText(1), 'SCHEDULE')
        finally:
            tv.close()

    def test_schedule_numbers_and_original_times_survive_navigation_and_seeks(self):
        tv = RetroChannelWidget()
        try:
            clock = ChannelClock(range(30), lambda row: 120000)
            channel = {'genre': 'Action', 'rows': list(range(30)), 'clock': clock}
            engine = Mock(currentSlotIndex=0, currentRow=clock._rotation[0])
            engine.isShowingStandby.return_value = False
            tv.engines[0] = engine
            with patch.object(tv, '_titleForRow', side_effect=lambda row: f'Movie {row}'):
                engine.currentTitle = f'Movie {clock._rotation[0]}'
                tv._refreshScheduleTable(channel)
                original = [[tv.scheduleTable.item(row, col).text() for col in range(3)] for row in range(25)]
                for target in (3, 2, 26, 0):
                    clock.repositionSlot(target, clock._rowForSlot(target), 180000, 90000)
                    engine.currentSlotIndex = target
                    engine.currentRow = clock._rowForSlot(target)
                    engine.currentTitle = f'Movie {engine.currentRow}'
                    tv._refreshScheduleTable(channel)
                    self.assertEqual(original, [[tv.scheduleTable.item(row, col).text() for col in range(3)]
                                                for row in range(25)])
                    self.assertEqual(tv.scheduleTable.item(target % 25, 2).background().color().name(), '#00ff00')
            tv.engines = {}
        finally:
            tv.engines = {}
            tv.close()

    def test_program_buttons_jump_selected_channel_and_previous_wraps(self):
        with patch('smdb.RetroChannelWidget.time.monotonic', return_value=0):
            clock = ChannelClock([0, 1, 2], lambda row: 120000)
            clock._rotation = [0, 1, 2]
            clock._offsetFractions = {0: 0.25, 1: 0.5, 2: 0.75}
            engine = ChannelEngine(1, 'Action', clock, lambda row: None, str)
            tv = RetroChannelWidget()
            neighbor = Mock()
            tv.engines = {0: engine, 1: neighbor}
            self.enableControls(tv)
            engine.currentSlotIndex = 0
            engine._tuneRequestId = 10
            engine._prefetchRequestId = 11
            try:
                with patch.object(engine, '_tuneIn') as tune:
                    tv.previousProgramButton.click()
                    self.assertEqual(clock.whatsOnNow()[:3], (2, 2, 0.75))
                    self.assertNotEqual(engine._tuneRequestId, 10)
                    self.assertNotEqual(engine._prefetchRequestId, 11)
                    tv.nextProgramButton.click()
                    self.assertEqual(clock.whatsOnNow()[:3], (3, 0, 0.25))
                    self.assertEqual(tune.call_count, 2)
                    neighbor.skipProgram.assert_not_called()
            finally:
                tv.engines.clear()
                engine.shutdown()
                engine.container.close()
                tv.close()

    def test_reversed_guide_keeps_bottom_highlight_visible_after_layout(self):
        tv = RetroChannelWidget()
        tv.channels = [{'genre': f'Genre {i}', 'rows': [i], 'clock': ChannelClock([i])}
                       for i in range(30)]
        try:
            with patch.object(tv.standbyTone, '_syncPlayback'), \
                    patch.object(tv, '_tuneTo'), patch.object(tv, '_updateGuidePreview'):
                tv.resize(1200, 700)
                tv.show()
                self.assertTrue(tv.guideVisible)
                self.app.processEvents()
                self.app.processEvents()
                self.assertEqual(tv.guideTable.rows[29]['label'], '01 GENRE 0')
                self.assertTrue(tv.guideTable.viewport().rect().contains(tv.guideTable.rowRect(29)))
                tv.guidePages.setCurrentIndex(1)
                tv.resize(1100, 650)
                tv.guidePages.setCurrentIndex(0)
                self.app.processEvents()
                self.app.processEvents()
                self.assertTrue(tv.guideTable.viewport().rect().contains(tv.guideTable.rowRect(29)))
        finally:
            tv.close()

    def test_startup_guide_waits_for_catalogue_and_opens_once(self):
        parent = QtWidgets.QWidget()
        parent.moviesTableModel = Mock()
        model = parent.moviesTableModel
        model.rowCount.return_value = 10
        model.getGenres.return_value = ['Action']
        model.getRuntime.return_value = '120'
        model.getTitle.return_value = 'Movie'
        model.getYear.return_value = '1963'
        model.getMovieData.return_value = {}
        tv = RetroChannelWidget(parent)
        try:
            with patch.object(tv.standbyTone, '_syncPlayback'), \
                    patch.object(tv, '_tuneTo'), patch.object(tv, '_updateGuidePreview'):
                parent.show()
                tv.show()
                self.assertFalse(tv.guideVisible)
                tv.refreshChannels()
                self.assertTrue(tv.guideVisible)
                self.assertEqual(tv.guidePages.currentIndex(), 0)
                tv.toggleGuide()
                tv.refreshChannels()
                self.assertFalse(tv.guideVisible)
        finally:
            tv.close()
            parent.close()

    def test_current_film_seek_buttons_adjust_position_and_schedule(self):
        with patch('smdb.RetroChannelWidget.time.monotonic', return_value=0):
            clock = ChannelClock([0], lambda row: 100000)
            clock._offsetFractions = {0: 0.5}
            engine = ChannelEngine(1, 'Action', clock, lambda row: None, str)
            engine.currentRow = 0
            engine.currentSlotIndex = 0
            slot = engine.activeSlot
            realPlayer = slot.player
            slot.player = Mock()
            slot.duration = 100000
            slot.path = 'movie.mp4'
            slot._ready = True
            position = [50000]
            slot.player.position.side_effect = lambda: position[0]
            slot.player.setPosition.side_effect = lambda value: position.__setitem__(0, value)
            tv = RetroChannelWidget()
            neighbor = Mock()
            tv.engines = {0: engine, 1: neighbor}
            self.enableControls(tv)
            try:
                with patch.object(engine, '_maybeSchedulePrefetch'):
                    tv.forwardTenButton.click()
                    self.assertEqual(position[0], 60000)
                    self.assertEqual(engine.advanceTimer.interval(), 40000)
                    tv.backTenButton.click()
                    self.assertEqual(position[0], 50000)
                    engine.seekCurrentFilm(beginning=True)
                    self.assertEqual(position[0], 0)
                    self.assertEqual(engine.advanceTimer.interval(), 100000)
                    tv.backTenButton.click()
                    self.assertEqual(position[0], 0)
                    position[0] = 95000
                    slot._onPlaybackPosition(95000)
                    tv.forwardTenButton.click()
                    self.assertEqual(position[0], 99999)
                    self.assertEqual(engine.currentRow, 0)
                    self.assertEqual(clock.slotInfo(1)[1], 0.5)
                    neighbor.seekCurrentFilm.assert_not_called()
                    slot.player.setMedia.assert_not_called()
            finally:
                tv.engines.clear()
                slot.player = realPlayer
                engine.shutdown()
                engine.container.close()
                tv.close()

    def test_next_start_opens_next_movie_at_zero_and_preserves_future_random_start(self):
        clock = ChannelClock([0, 1], lambda row: 120000)
        clock._rotation = [0, 1]
        clock._offsetFractions = {0: 0.25, 1: 0.5}
        engine = ChannelEngine(1, 'Action', clock, lambda row: None, str)
        engine.currentSlotIndex = 0
        tv = RetroChannelWidget()
        tv.engines = {0: engine}
        self.enableControls(tv)
        try:
            with patch.object(engine, '_tuneIn') as tune:
                tv.nextBeginningButton.click()
                self.assertEqual(clock.whatsOnNow()[:3], (1, 1, 0.0))
                self.assertEqual(clock.durationForSlot(1), 120000)
                self.assertEqual(clock.slotInfo(3)[1], 0.5)
                tune.assert_called_once()
        finally:
            tv.engines.clear()
            engine.shutdown()
            engine.container.close()
            tv.close()

    def test_previous_resume_then_beginning_and_forward_restores_saved_position(self):
        clock = ChannelClock([0, 1], lambda row: 100000)
        clock._rotation = [0, 1]
        clock._offsetFractions = {0: 0.25, 1: 0.5}
        clock.rememberPosition(0, 0, 100000, 42000)
        engine = ChannelEngine(1, 'Action', clock, lambda row: None, str)
        engine.currentSlotIndex = 1
        slot = engine.activeSlot
        realPlayer = slot.player
        tv = RetroChannelWidget()
        tv.engines = {0: engine}
        self.enableControls(tv)
        try:
            with patch.object(engine, '_tuneIn') as tune, patch.object(engine, '_maybeSchedulePrefetch'):
                tv.beginningButton.click()
                self.assertEqual(clock.slotInfo(0)[1], 0.42)
                self.assertEqual(engine.currentSlotIndex, 0)
                slot.player = Mock()
                position = [42000]
                slot.player.position.side_effect = lambda: position[0]
                slot.player.setPosition.side_effect = lambda value: position.__setitem__(0, value)
                slot.path = 'movie.mp4'
                slot._ready = True
                slot.duration = 100000
                engine.currentRow = 0
                tv.beginningButton.click()
                self.assertEqual(position[0], 0)
                self.assertEqual(engine.currentSlotIndex, 0)
                tv.nextBeginningButton.click()
                self.assertEqual(position[0], 42000)
                self.assertEqual(engine.currentSlotIndex, 0)
                tune.assert_called_once()
                self.assertEqual(clock.resumeInfoForSlot(2)[2], 42000)
        finally:
            tv.engines.clear()
            slot.player = realPlayer
            engine.shutdown()
            engine.container.close()
            tv.close()

    def test_estimated_boundary_never_cuts_active_movie_and_end_advances(self):
        with patch('smdb.RetroChannelWidget.time.monotonic', return_value=0) as now:
            clock = ChannelClock([0, 1], lambda row: 120000)
            clock._rotation = [0, 1]
            clock._offsetFractions = {0: 0.0, 1: 0.0}
            engine = ChannelEngine(1, 'Action', clock, lambda row: 'movie.mp4', str)
            slot = engine.activeSlot
            realPlayer = slot.player
            slot.player = Mock()
            engine.currentRow = 0
            engine.currentTitle = '0'
            engine.currentSlotIndex = 0
            slot.duration = 120000
            try:
                now.return_value = 130  # buffering outlasted the runtime estimate
                slot.player.mediaStatus.return_value = QMediaPlayer.BufferedMedia
                with patch.object(engine, '_hardCut') as cut:
                    engine._onAdvanceTimer()
                    cut.assert_not_called()
                    self.assertEqual(engine.currentRow, 0)
                    slot.player.mediaStatus.return_value = QMediaPlayer.EndOfMedia
                    engine._onMovieStatus(slot, QMediaPlayer.EndOfMedia)
                    self.assertEqual(cut.call_args.args[0], 1)
                    self.assertEqual(cut.call_args.args[1], 0.0)
                    self.assertLess(cut.call_args.args[2], 10)
                # End-of-media from the inactive buffer must not advance again.
                with patch.object(engine, '_onAdvanceTimer') as advance:
                    engine._onMovieStatus(engine.standbySlot, QMediaPlayer.EndOfMedia)
                    advance.assert_not_called()
            finally:
                slot.player = realPlayer
                engine.shutdown()
                engine.container.close()


if __name__ == '__main__':
    unittest.main()
