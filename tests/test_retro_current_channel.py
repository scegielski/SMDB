import os
import tempfile
import unittest
from unittest.mock import Mock, patch
from PyQt5 import QtCore, QtWidgets
from smdb.RetroChannelWidget import RetroChannelWidget


class CurrentChannelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.settingsPath = os.path.join(self.directory.name, 'settings.ini')
        self.parents = []
        self.widgets = []

    def makeTv(self, genres):
        parent = QtWidgets.QWidget()
        parent.settings = QtCore.QSettings(self.settingsPath, QtCore.QSettings.IniFormat)
        parent.moviesTableModel = Mock()
        parent.moviesTableModel.rowCount.return_value = 1 if genres else 0
        parent.moviesTableModel.getGenres.return_value = genres
        parent.moviesTableModel.getRuntime.return_value = '120'
        parent.moviesTableModel.getPath.return_value = None
        tv = RetroChannelWidget(parent)
        self.parents.append(parent)
        self.widgets.append(tv)
        tv.refreshChannels()
        return tv

    def tearDown(self):
        for tv in self.widgets:
            tv.close()
            tv.deleteLater()
        for parent in self.parents:
            parent.close()
            parent.deleteLater()
        self.app.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
        self.directory.cleanup()

    def test_power_off_selection_restores_by_name_after_numbering_changes(self):
        tv = self.makeTv(['Action', 'Comedy', 'Drama'])
        tv._powerOn = False
        tv.channelUp()
        self.assertEqual(tv.channels[tv.currentIndex]['genre'], 'Comedy')
        tv._settings.sync()
        restored = self.makeTv(['Action', 'Biography', 'Comedy', 'Drama'])
        self.assertEqual(restored.currentIndex, 2)
        self.assertEqual(restored.guideHighlightIndex, 2)
        self.assertEqual(restored.channels[restored.currentIndex]['genre'], 'Comedy')

    def test_playing_selection_saves_and_unavailable_channel_falls_back(self):
        tv = self.makeTv(['Action', 'Comedy'])
        def engine(index):
            return Mock(container=QtWidgets.QWidget(), currentTitle='')
        with patch.object(tv, '_createEngine', side_effect=engine), \
                patch.object(tv, '_showBanner'), patch.object(tv, '_showVideoOsd'), \
                patch.object(tv, '_syncStandbyTone'):
            tv.channelUp()
        self.assertEqual(tv._settings.value('smtvCurrentChannel'), 'Comedy')
        tv._settings.sync()
        restored = self.makeTv(['Action', 'Comedy'])
        restored.setExcludedChannels(['Comedy'])
        self.assertEqual(restored.channels[restored.currentIndex]['genre'], 'Action')
        restored._powerOn = False
        restored._tuneTo(restored.currentIndex)
        self.assertEqual(restored._settings.value('smtvCurrentChannel'), 'Action')

    def test_empty_initial_catalogue_keeps_preference_until_movies_load(self):
        settings = QtCore.QSettings(self.settingsPath, QtCore.QSettings.IniFormat)
        settings.setValue('smtvCurrentChannel', 'Drama')
        settings.sync()
        tv = self.makeTv([])
        tv._tuneTo(0)
        self.assertEqual(tv._settings.value('smtvCurrentChannel'), 'Drama')
        tv.mainWindow.moviesTableModel.rowCount.return_value = 1
        tv.mainWindow.moviesTableModel.getGenres.return_value = ['Action', 'Drama']
        tv.refreshChannels()
        self.assertEqual(tv.channels[tv.currentIndex]['genre'], 'Drama')
