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
                    patch.object(tv, 'setExcludedChannels') as apply:
                tv.setupButton.click()
                apply.assert_not_called()
            dialog.close()
        finally:
            tv.close()


if __name__ == '__main__':
    unittest.main()
