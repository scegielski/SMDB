import json
import os
import tempfile
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt5 import QtWidgets
from smdb.RetroChannelWidget import RetroChannelWidget


class SchedulePersistenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_restart_preserves_paths_times_and_live_broadcast_after_row_reorder(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = QtWidgets.QWidget()
            parent.moviesFolder = directory
            model = parent.moviesTableModel = Mock()
            paths = [os.path.join(directory, str(i)) for i in range(30)]
            model.rowCount.return_value = len(paths)
            model.getPath.side_effect = lambda row: paths[row]
            model.getGenres.return_value = ['Action', 'Comedy']
            model.getRuntime.return_value = '120'
            model.getMpaaRating.return_value = 'PG'
            model.getRating.return_value = 7.0
            tv = RetroChannelWidget(parent)
            restored = None
            try:
                with patch('smdb.RetroChannelWidget.time.time', return_value=1800000000):
                    tv.refreshChannels()
                clock = tv.channels[0]['clock']
                original = [paths[row] for row in clock._rotation]
                starts, ends = list(clock._scheduleStarts), list(clock._scheduleEnds)
                fractions = dict(clock._offsetFractions)
                file = os.path.join(directory, 'smtv_schedule.json')
                with open(file, encoding='utf-8') as stream:
                    self.assertEqual(json.load(stream)['version'], 1)
                paths.reverse()
                restored = RetroChannelWidget(parent)
                later = starts[0] + clock._scheduleCycleSeconds + 30
                with patch('smdb.RetroChannelWidget.time.time', return_value=later):
                    restored.refreshChannels()
                recovered = restored.channels[0]['clock']
                self.assertEqual([paths[row] for row in recovered._rotation], original)
                self.assertEqual(recovered._scheduleStarts, starts)
                self.assertEqual(recovered._scheduleEnds, ends)
                self.assertEqual(recovered._offsetFractions, fractions)
                slot, row, fraction, position, remaining = recovered.whatsOnNow()
                self.assertEqual(slot, 25)
                self.assertAlmostEqual(position, 30000, delta=100)
                neighbor = list(restored.channels[1]['clock']._scheduleStarts)
                restored.reprogramChannel()
                replacement = list(restored.channels[0]['clock']._scheduleStarts)
                tv.close()
                tv = RetroChannelWidget(parent)
                tv.refreshChannels()
                self.assertEqual(tv.channels[0]['clock']._scheduleStarts, replacement)
                self.assertEqual(tv.channels[1]['clock']._scheduleStarts, neighbor)
            finally:
                tv.close()
                if restored is not None:
                    restored.close()
                parent.close()

    def test_filtered_lineup_persists_and_corrupt_file_recovers(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = QtWidgets.QWidget()
            parent.moviesFolder = directory
            model = parent.moviesTableModel = Mock()
            model.rowCount.return_value = 5
            model.getPath.side_effect = lambda row: os.path.join(directory, str(row))
            model.getGenres.return_value = ['Action']
            model.getRuntime.return_value = '90'
            model.getMpaaRating.side_effect = lambda row: 'R' if row < 2 else 'PG'
            model.getRating.return_value = 7
            tv = RetroChannelWidget(parent)
            restored = None
            try:
                tv.refreshChannels()
                tv.setChannelPreferences([], ['R'])
                original = tv.channels[0]['clock']
                restored = RetroChannelWidget(parent)
                restored._excludedRatings = {'R'}
                restored.refreshChannels()
                recovered = restored.channels[0]['clock']
                self.assertEqual(recovered._rotation, original._rotation)
                self.assertEqual(recovered._scheduleStarts, original._scheduleStarts)
                restored.close()
                with open(os.path.join(directory, 'smtv_schedule.json'), 'w') as stream:
                    stream.write('{broken')
                restored = RetroChannelWidget(parent)
                restored.refreshChannels()
                self.assertEqual(len(restored.channels), 1)
                with open(os.path.join(directory, 'smtv_schedule.json')) as stream:
                    self.assertEqual(json.load(stream)['version'], 1)
            finally:
                tv.close()
                if restored is not None:
                    restored.close()
                parent.close()
