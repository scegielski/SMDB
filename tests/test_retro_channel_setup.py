import os
import tempfile
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt5 import QtCore, QtWidgets
from smdb.RetroChannelWidget import RetroChannelWidget, _ChannelSetupDialog


class ChannelSetupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_selection_persists_and_can_recover_from_all_disabled(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = QtWidgets.QWidget()
            parent.settings = QtCore.QSettings(os.path.join(directory, 'settings.ini'), QtCore.QSettings.IniFormat)
            model = parent.moviesTableModel = Mock()
            model.rowCount.return_value = 10
            model.getGenres.return_value = ['Action', 'Comedy']
            model.getRuntime.return_value = '120'
            tv = RetroChannelWidget(parent)
            restored = None
            try:
                tv.refreshChannels()
                originalClock = tv.channels[0]['clock']
                tv.setExcludedChannels(['Comedy'])
                self.assertEqual([channel['genre'] for channel in tv.channels], ['Action'])
                self.assertIs(tv.channels[0]['clock'], originalClock)
                dialog = _ChannelSetupDialog(tv._availableChannels, tv._excludedGenres, tv)
                self.assertTrue(dialog.channelChecks['Action'].isChecked())
                self.assertFalse(dialog.channelChecks['Comedy'].isChecked())
                dialog.channelChecks['Action'].setChecked(False)
                with patch('smdb.RetroChannelWidget._ChannelSetupDialog', return_value=dialog), \
                        patch.object(dialog, 'exec_', return_value=QtWidgets.QDialog.Accepted):
                    tv.setupButton.click()
                self.assertEqual(tv.channels, [])
                self.assertTrue(tv.setupButton.isEnabled())
                self.assertFalse(tv.channelUpButton.isEnabled())
                self.assertEqual(len(tv._availableChannels), 2)
                restored = RetroChannelWidget(parent)
                restored.refreshChannels()
                self.assertEqual(restored.channels, [])
                restored.setExcludedChannels([])
                self.assertEqual(len(restored.channels), 2)
                self.assertTrue(restored.channelUpButton.isEnabled())
                dialog.close()
            finally:
                tv.close()
                if restored:
                    restored.close()
                parent.close()

    def test_cancel_keeps_selection_unchanged(self):
        tv = RetroChannelWidget()
        try:
            dialog = _ChannelSetupDialog([], set(), tv)
            with patch('smdb.RetroChannelWidget._ChannelSetupDialog', return_value=dialog), \
                    patch.object(dialog, 'exec_', return_value=QtWidgets.QDialog.Rejected), \
                    patch.object(tv, 'setChannelPreferences') as apply:
                tv.setupButton.click()
                apply.assert_not_called()
            dialog.close()
        finally:
            tv.close()

    def test_reprogram_repicks_only_current_filtered_channel(self):
        parent = QtWidgets.QWidget()
        model = parent.moviesTableModel = Mock()
        model.rowCount.return_value = 52
        model.getGenres.side_effect = lambda row: ['Action'] if row < 50 else ['Comedy']
        model.getMpaaRating.side_effect = lambda row: 'R' if row < 5 else 'PG'
        model.getRuntime.return_value = '120'
        tv = RetroChannelWidget(parent)
        try:
            tv.refreshChannels()
            tv.setChannelPreferences([], ['R'])
            old = tv.channels[0]['clock']
            neighborClock = tv.channels[1]['clock']
            current = Mock(container=QtWidgets.QWidget())
            neighbor = Mock(container=QtWidgets.QWidget())
            tv.engines = {0: current, 1: neighbor}
            tv.isActive = True
            with patch.object(tv, '_tuneTo') as tune, \
                    patch('smdb.RetroChannelWidget.random.sample', side_effect=lambda rows, count: list(reversed(rows))[:count]):
                tv.reprogramButton.click()
                tune.assert_called_once_with(0)
            clock = tv.channels[0]['clock']
            self.assertIsNot(clock, old)
            self.assertEqual(clock._rotation, list(range(49, 24, -1)))
            self.assertEqual(clock.rows, list(range(5, 50)))
            self.assertIs(tv.channels[1]['clock'], neighborClock)
            self.assertIs(tv.engines[1], neighbor)
            neighbor.shutdown.assert_not_called()
            current.shutdown.assert_called_once()
            tv.isActive = False
            tv.setChannelPreferences([], [])
            tv.setChannelPreferences([], ['R'])
            self.assertIs(tv.channels[0]['clock'], clock)
            tv.setExcludedChannels(['Action', 'Comedy'])
            self.assertFalse(tv.reprogramButton.isEnabled())
            tv.reprogramChannel()
        finally:
            tv.close()
            parent.close()

    def test_quality_range_filters_catalogue_scores_and_persists(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = QtWidgets.QWidget()
            parent.settings = QtCore.QSettings(os.path.join(directory, 'settings.ini'), QtCore.QSettings.IniFormat)
            model = parent.moviesTableModel = Mock()
            model.rowCount.return_value = 7
            model.getGenres.return_value = ['Action']
            model.getRuntime.return_value = '120'
            model.getMpaaRating.side_effect = lambda row: 'R' if row == 2 else 'PG'
            model.getRating.side_effect = lambda row: ['6.093', '7.667', '8.6', '3.3', '0.0', '', 'bad'][row]
            tv = RetroChannelWidget(parent)
            restored = None
            try:
                tv.refreshChannels()
                self.assertEqual(len(tv.channels[0]['rows']), 7)
                dialog = _ChannelSetupDialog(tv._availableChannels, set(), tv, tv._ratingCounts, set())
                dialog.pages.setCurrentIndex(2)
                dialog.minimumRating.setValue(6.093)
                dialog.maximumRating.setValue(7.667)
                dialog.includeUnrated.setChecked(False)
                with patch('smdb.RetroChannelWidget._ChannelSetupDialog', return_value=dialog), \
                        patch.object(dialog, 'exec_', return_value=QtWidgets.QDialog.Accepted):
                    tv.setupButton.click()
                self.assertEqual(tv.channels[0]['rows'], [0, 1])
                self.assertEqual(set(tv.channels[0]['clock']._rotation), {0, 1})
                restored = RetroChannelWidget(parent)
                restored.refreshChannels()
                self.assertEqual(restored.channels[0]['rows'], [0, 1])
                restored.setChannelPreferences([], [], (6.093, 8.6), True)
                self.assertEqual(restored.channels[0]['rows'], [0, 1, 2, 4, 5, 6])
                restored.setChannelPreferences([], ['R'], (6.093, 8.6), False)
                self.assertEqual(restored.channels[0]['rows'], [0, 1])
                restored.setChannelPreferences([], [], (9.0, 10.0), False)
                self.assertEqual(restored.channels, [])
                self.assertTrue(restored.setupButton.isEnabled())
                self.assertLessEqual(dialog.minimumRating.value(), dialog.maximumRating.value())
                dialog.minimumRating.setValue(10.0)
                self.assertEqual(dialog.minimumRating.value(), dialog.maximumRating.value())
                dialog.close()
            finally:
                tv.close()
                if restored:
                    restored.close()
                parent.close()

    def test_rating_filter_persists_and_keeps_single_movie_channels(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = QtWidgets.QWidget()
            parent.settings = QtCore.QSettings(os.path.join(directory, 'settings.ini'), QtCore.QSettings.IniFormat)
            model = parent.moviesTableModel = Mock()
            model.rowCount.return_value = 4
            model.getGenres.side_effect = lambda row: ['Action'] if row < 3 else ['Comedy']
            model.getRuntime.return_value = '120'
            model.getMpaaRating.side_effect = lambda row: ['PG', 'Rated R for violence', '', 'NR'][row]
            tv = RetroChannelWidget(parent)
            restored = None
            try:
                tv.refreshChannels()
                self.assertEqual(len(tv.channels), 2)
                dialog = _ChannelSetupDialog(tv._availableChannels, set(), tv, tv._ratingCounts, set())
                self.assertEqual(set(dialog.ratingChecks), {'PG', 'R', 'Unknown', 'Unrated'})
                dialog.pages.setCurrentIndex(1)
                dialog.selectAll(False)
                self.assertTrue(all(check.isChecked() for check in dialog.channelChecks.values()))
                dialog.ratingChecks['PG'].setChecked(True)
                with patch('smdb.RetroChannelWidget._ChannelSetupDialog', return_value=dialog), \
                        patch.object(dialog, 'exec_', return_value=QtWidgets.QDialog.Accepted):
                    tv.setupButton.click()
                self.assertEqual([(channel['genre'], channel['rows']) for channel in tv.channels], [('Action', [0])])
                self.assertEqual(tv.channels[0]['clock']._rotation, [0])
                restored = RetroChannelWidget(parent)
                restored.refreshChannels()
                self.assertEqual(restored.channels[0]['rows'], [0])
                restored.setChannelPreferences([], ['PG', 'R', 'Unknown', 'Unrated'])
                self.assertEqual(restored.channels, [])
                self.assertTrue(restored.setupButton.isEnabled())
                self.assertEqual(len(restored._availableChannels), 2)
                restored.setChannelPreferences([], [])
                self.assertEqual(len(restored.channels), 2)
                dialog.close()
            finally:
                tv.close()
                if restored:
                    restored.close()
                parent.close()


if __name__ == '__main__':
    unittest.main()
