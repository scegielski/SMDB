import json
import os
import tempfile
import time
import wave
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
os.environ.setdefault('QT_QPA_PLATFORM', 'windows')
from PyQt5 import QtCore, QtWidgets
from smdb.WeatherChannel import WeatherService, WeatherScreen, WeatherSettingsPage, WeatherMusic, clean_config
from smdb.RetroChannelWidget import RetroChannelWidget, WeatherChannelEngine, _ChannelSetupDialog


class WeatherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_settings_search_selection_and_persistence(self):
        with tempfile.TemporaryDirectory() as folder:
            parent = QtWidgets.QWidget()
            parent.settings = QtCore.QSettings(os.path.join(folder, 'settings.ini'), QtCore.QSettings.IniFormat)
            tv = RetroChannelWidget(parent)
            dialog = _ChannelSetupDialog([], set(), tv)
            page = dialog.weatherPage
            page._results({'results': [{'name': 'Springfield', 'admin1': 'Illinois', 'country': 'United States', 'latitude': 39.78, 'longitude': -89.65},
                                       {'name': 'Springfield', 'admin1': 'Massachusetts', 'latitude': 42.1, 'longitude': -72.59}]}, '')
            page.locations.setCurrentIndex(1)
            page.units.setCurrentIndex(1)
            selected = page.configuration()
            self.assertEqual(selected['latitude'], 42.1)
            self.assertEqual(selected['units'], 'metric')
            page._results({}, 'Offline')
            self.assertEqual(page.configuration(), selected)
            with patch.object(tv.weatherService.request, 'get'), patch.object(dialog, 'exec_', return_value=QtWidgets.QDialog.Accepted), patch('smdb.RetroChannelWidget._ChannelSetupDialog', return_value=dialog):
                tv.openChannelSetup()
            parent.settings.sync()
            restored = RetroChannelWidget(parent)
            self.assertEqual(restored.weatherService.config, selected)
            dialog.close()
            tv.close()
            restored.close()
            parent.close()

    def test_missing_location_failed_refresh_and_units(self):
        service = WeatherService()
        with patch.object(service.request, 'get') as get:
            service.start()
            get.assert_not_called()
            service.configure({'latitude': 0, 'longitude': 0, 'label': 'Test', 'units': 'metric'})
            params = get.call_args.args[1]
            self.assertEqual(params['temperature_unit'], 'celsius')
            self.assertEqual(params['timezone'], 'auto')
        data = {'current': {'temperature_2m': 18, 'weather_code': 2}, 'utc_offset_seconds': 7200}
        service._received(data, '')
        self.assertIn('18°C', service.summary())
        service._received(None, 'Offline')
        self.assertIs(service.data, data)
        self.assertIn('Showing last update', service.status)
        self.assertEqual(service.local_time(0), '2:00 AM')
        self.assertEqual(clean_config({'latitude': float('nan'), 'longitude': 0}), {})
        service.refreshTimer.stop()

    def test_weather_survives_movie_filters_and_uses_live_surface(self):
        parent = QtWidgets.QWidget()
        parent.moviesTableModel = model = Mock()
        model.rowCount.return_value = 1
        model.getGenres.return_value = ['Action']
        model.getRuntime.return_value = '120'
        model.getRating.return_value = 5
        model.getMpaaRating.return_value = 'R'
        tv = RetroChannelWidget(parent)
        tv.refreshChannels()
        tv.setChannelPreferences([], ['R'], (8, 10), False)
        self.assertEqual([channel['genre'] for channel in tv.channels], ['Weather'])
        self.assertIsNone(tv._resolveVideoPath(-1))
        blocks = list(tv.channels[0]['clock'].publishedPrograms(time.time(), time.time() + 7200))
        self.assertTrue(all(block['end'] - block['start'] == 3600 for block in blocks))
        engine = tv._createEngine(0)
        tv.engines[0] = engine
        engine.start(False)
        self.assertIsInstance(engine, WeatherChannelEngine)
        self.assertFalse(engine.isShowingStandby())
        self.assertIsNone(engine.activeSlot.path)
        engine.setPaused(True)
        self.assertTrue(engine.weather.paused)
        self.assertFalse(engine.seekCurrentFilm(10000))
        tv._updateEmptyState()
        self.assertFalse(tv.forwardTenButton.isEnabled())
        tv.guideVisible = True
        tv._refreshGuideTable()
        self.assertIn('Local Weather', tv.guideDescription.toPlainText())
        tv._guidePreviewHostedEngine = engine
        tv._syncDlss()
        self.assertIsNone(tv._dlssChosen)
        tv._guidePreviewHostedEngine = None
        tv.guideVisible = False
        tv.setExcludedChannels(['Weather'])
        self.assertEqual(tv.channels, [])
        tv.close()
        parent.close()

    def test_original_music_assets_and_audio_controls(self):
        assets = Path(__file__).resolve().parents[1] / 'smdb' / 'assets' / 'weather_music'
        self.assertEqual(len(list(assets.glob('*.mid'))), 3)
        for midi in assets.glob('*.mid'):
            self.assertTrue(midi.read_bytes().startswith(b'MThd'))
            with wave.open(str(midi.with_suffix('.wav'))) as audio:
                self.assertEqual(audio.getnchannels(), 2)
                self.assertGreater(audio.getnframes() / audio.getframerate(), 30)
        music = WeatherMusic()
        self.assertEqual(music.playlist.mediaCount(), 3)
        with patch.object(music.player, 'play') as play, patch.object(music.player, 'pause') as pause, patch.object(music.player, 'stop') as stop:
            music.sync(70, active=True)
            play.assert_called_once()
            self.assertEqual(music.player.volume(), 32)
            music.sync(0, active=True)
            music.sync(70, paused=True, active=True)
            self.assertEqual(pause.call_count, 2)
            music.sync(70, active=False)
            stop.assert_called_once()
        music.stop()

    def test_weather_engine_routes_music_on_volume_pause_and_shutdown(self):
        tv = RetroChannelWidget()
        tv.refreshChannels()
        engine = tv._createEngine(0)
        with patch.object(engine.music, 'sync') as sync, patch.object(engine.music, 'stop') as stop:
            engine.setDesiredVolume(70)
            sync.assert_called_with(70, False, False)
            engine.start(False)
            sync.assert_called_with(70, False, True)
            engine.setPaused(True)
            sync.assert_called_with(70, True, True)
            engine.setDesiredVolume(0)
            sync.assert_called_with(0, True, True)
            engine.shutdown()
            stop.assert_called_once()
        tv.close()

    def test_screen_rotation_pause_and_render(self):
        service = WeatherService({'latitude': 47.6, 'longitude': -122.3, 'label': 'Seattle, Washington', 'units': 'imperial'})
        now = time.time()
        service._received({'current': {'temperature_2m': 64, 'weather_code': 2, 'apparent_temperature': 62,
                                      'relative_humidity_2m': 74, 'wind_speed_10m': 8, 'wind_direction_10m': 240},
                           'utc_offset_seconds': -25200,
                           'hourly': {'time': [now + i * 3600 for i in range(5)], 'temperature_2m': [64, 62, 60, 59, 58], 'weather_code': [2, 3, 3, 61, 61], 'precipitation_probability': [5, 10, 20, 50, 60]},
                           'daily': {'time': [now + i * 86400 for i in range(3)], 'temperature_2m_max': [66, 62, 65], 'temperature_2m_min': [52, 49, 51], 'weather_code': [2, 61, 3]}}, '')
        screen = WeatherScreen(service)
        screen.resize(960, 720)
        with patch.object(service, 'start'):
            screen.show()
            self.app.processEvents()
            for page in range(3):
                screen.page = page
                image = screen.grab().toImage()
                self.assertFalse(image.isNull())
                if page == 0 and os.environ.get('SMTV_WEATHER_SCREENSHOT'):
                    image.save(os.environ['SMTV_WEATHER_SCREENSHOT'])
            screen.paused = True
            seconds = screen.seconds
            screen._tick()
            self.assertEqual(screen.seconds, seconds)
            screen.paused = False
            screen.seconds = 9
            screen._tick()
            self.assertEqual(screen.page, 1)
        screen.close()


if __name__ == '__main__':
    unittest.main()
