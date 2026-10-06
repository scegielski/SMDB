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


if __name__ == '__main__':
    unittest.main()
