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
            self.assertEqual(tv.scheduleTable.item(0, 1).text(), 'NOW')
            self.assertEqual(tv.scheduleTable.item(24, 2).text(), f'Movie {clock.slotInfo(24)[0]}')
            self.assertEqual(tv.guidePages.tabText(1), 'SCHEDULE')
        finally:
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
