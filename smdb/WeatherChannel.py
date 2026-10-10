"""Native retro local-weather channel and asynchronous Open-Meteo setup."""
import html
import json
import math
import time
from pathlib import Path
from datetime import datetime, timezone, timedelta
from PyQt5 import QtCore, QtGui, QtWidgets, QtNetwork
from PyQt5.QtMultimedia import QMediaContent, QMediaPlayer, QMediaPlaylist


def condition(code):
    return {0: 'Clear', 1: 'Mostly clear', 2: 'Partly cloudy', 3: 'Overcast',
            45: 'Fog', 48: 'Freezing fog', 51: 'Light drizzle', 53: 'Drizzle',
            55: 'Heavy drizzle', 56: 'Freezing drizzle', 57: 'Freezing drizzle',
            61: 'Light rain', 63: 'Rain', 65: 'Heavy rain', 66: 'Freezing rain',
            67: 'Freezing rain', 71: 'Light snow', 73: 'Snow', 75: 'Heavy snow',
            77: 'Snow grains', 80: 'Rain showers', 81: 'Rain showers',
            82: 'Heavy showers', 85: 'Snow showers', 86: 'Snow showers',
            95: 'Thunderstorms', 96: 'Thunder / hail', 99: 'Thunder / hail'}.get(code, 'Unavailable')


def clean_config(value):
    if not isinstance(value, dict):
        return {}
    try:
        lat, lon = float(value['latitude']), float(value['longitude'])
        if not math.isfinite(lat) or not math.isfinite(lon) or not -90 <= lat <= 90 or not -180 <= lon <= 180:
            return {}
        return dict(latitude=lat, longitude=lon, label=str(value.get('label', 'Local weather')),
                    units='metric' if value.get('units') == 'metric' else 'imperial')
    except (KeyError, TypeError, ValueError):
        return {}


class JsonRequest(QtCore.QObject):
    """One cancellable, bounded request; errors never block the GUI or remove old data."""
    finished = QtCore.pyqtSignal(object, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.manager = QtNetwork.QNetworkAccessManager(self)
        self.reply = None
        self.timeout = QtCore.QTimer(self)
        self.timeout.setSingleShot(True)
        self.timeout.timeout.connect(self._abort)

    def cancel(self):
        self.timeout.stop()
        old, self.reply = self.reply, None
        if old:
            old.abort()

    def _abort(self):
        if self.reply:
            self.reply.abort()

    def get(self, endpoint, params):
        self.cancel()
        url = QtCore.QUrl(endpoint)
        query = QtCore.QUrlQuery()
        for key, value in params.items():
            query.addQueryItem(key, str(value))
        url.setQuery(query)
        request = QtNetwork.QNetworkRequest(url)
        request.setAttribute(QtNetwork.QNetworkRequest.RedirectPolicyAttribute,
                             QtNetwork.QNetworkRequest.NoLessSafeRedirectPolicy)
        reply = self.manager.get(request)
        self.reply = reply
        reply.finished.connect(lambda: self._finish(reply))
        self.timeout.start(15000)

    def _finish(self, reply):
        if reply is not self.reply:
            reply.deleteLater()
            return
        self.reply = None
        self.timeout.stop()
        data, error = None, ''
        if reply.error():
            error = 'Unable to connect. Check your connection and try again.'
        else:
            try:
                data = json.loads(bytes(reply.readAll()).decode('utf-8'))
                if not isinstance(data, dict) or data.get('error'):
                    raise ValueError()
            except (ValueError, UnicodeError):
                error = 'Weather service returned an invalid response.'
        reply.deleteLater()
        self.finished.emit(data, error)


class WeatherService(QtCore.QObject):
    updated = QtCore.pyqtSignal()

    def __init__(self, config=None, parent=None):
        super().__init__(parent)
        self.config = clean_config(config)
        self.data = None
        self.receivedAt = 0
        self.status = 'Choose a location in SETUP → Weather.'
        self.request = JsonRequest(self)
        self.request.finished.connect(self._received)
        self.refreshTimer = QtCore.QTimer(self)
        self.refreshTimer.setInterval(10 * 60 * 1000)
        self.refreshTimer.timeout.connect(self.refresh)

    def configure(self, config):
        config = clean_config(config)
        if config == self.config:
            return
        self.request.cancel()
        self.config, self.data, self.receivedAt = config, None, 0
        self.refresh()

    def start(self):
        self.refreshTimer.start()
        if not self.receivedAt or time.time() - self.receivedAt > 600:
            self.refresh()

    def refresh(self):
        if not self.config:
            self.status = 'Choose a location in SETUP → Weather.'
            self.updated.emit()
            return
        if self.request.reply:
            return
        metric = self.config['units'] == 'metric'
        self.status = 'Updating local weather…'
        self.updated.emit()
        self.request.get('https://api.open-meteo.com/v1/forecast', {
            'latitude': self.config['latitude'], 'longitude': self.config['longitude'],
            'current': 'temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m,wind_direction_10m',
            'hourly': 'temperature_2m,weather_code,precipitation_probability',
            'daily': 'weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max',
            'timezone': 'auto', 'forecast_days': 3, 'timeformat': 'unixtime',
            'temperature_unit': 'celsius' if metric else 'fahrenheit',
            'wind_speed_unit': 'kmh' if metric else 'mph'})

    def _received(self, data, error):
        if not error and (not isinstance(data, dict) or not isinstance(data.get('current'), dict)
                          or not isinstance(data['current'].get('temperature_2m'), (int, float))):
            error = 'Weather readings are unavailable. Retrying in ten minutes.'
        if error:
            self.status = ('Showing last update. ' if self.data else '') + error
        else:
            self.data = data
            self.receivedAt = time.time()
            self.status = 'Updated ' + self.local_time(self.receivedAt, '%I:%M %p')
        self.updated.emit()

    def local_time(self, stamp, fmt='%I:%M %p'):
        offset = (self.data or {}).get('utc_offset_seconds', 0)
        return datetime.fromtimestamp(stamp, timezone(timedelta(seconds=offset))).strftime(fmt).lstrip('0')

    def summary(self):
        current = (self.data or {}).get('current', {})
        title = html.escape(self.config.get('label', 'Local Weather'))
        text = f'<h2 style="color:#ffda59">{title}</h2><p>{html.escape(self.status)}</p>'
        if current:
            unit = '°C' if self.config.get('units') == 'metric' else '°F'
            text += f'<p style="color:#65ffb2">{current["temperature_2m"]:g}{unit} — {condition(current.get("weather_code"))}</p>'
        return text + '<p>Current conditions • Hourly forecast • Three-day outlook</p><p>Weather data: Open-Meteo<br>Location search: GeoNames</p>'


class WeatherSettingsPage(QtWidgets.QWidget):
    def __init__(self, config=None, parent=None):
        super().__init__(parent)
        self.saved = clean_config(config)
        self.searchRequest = JsonRequest(self)
        self.searchRequest.finished.connect(self._results)
        form = QtWidgets.QFormLayout(self)
        self.query = QtWidgets.QLineEdit()
        self.query.setPlaceholderText('City, state / country or postal code')
        self.searchButton = QtWidgets.QPushButton('Search')
        row = QtWidgets.QHBoxLayout()
        row.addWidget(self.query)
        row.addWidget(self.searchButton)
        form.addRow('Location', row)
        self.locations = QtWidgets.QComboBox()
        if self.saved:
            self.locations.addItem(self.saved['label'], self.saved)
        form.addRow('Choose result', self.locations)
        self.units = QtWidgets.QComboBox()
        self.units.addItem('Fahrenheit / mph', 'imperial')
        self.units.addItem('Celsius / km/h', 'metric')
        self.units.setCurrentIndex(max(0, self.units.findData(self.saved.get('units', 'imperial'))))
        form.addRow('Units', self.units)
        self.message = QtWidgets.QLabel('Search, choose your location, then press OK. Settings are saved between launches.')
        self.message.setWordWrap(True)
        form.addRow(self.message)
        credit = QtWidgets.QLabel('Weather: Open-Meteo • Location search: GeoNames')
        form.addRow(credit)
        self.searchButton.clicked.connect(self.search)
        self.query.returnPressed.connect(self.search)

    def search(self):
        if len(self.query.text().strip()) < 2:
            self.message.setText('Enter a city or postal code.')
            return
        self.searchButton.setEnabled(False)
        self.message.setText('Searching…')
        self.searchRequest.get('https://geocoding-api.open-meteo.com/v1/search',
                               {'name': self.query.text().strip(), 'count': 10, 'language': 'en'})

    def _results(self, data, error):
        self.searchButton.setEnabled(True)
        results = (data or {}).get('results', [])
        if error or not results:
            self.message.setText(error or 'No locations found. Try a city and state or country.')
            return  # Preserve the previous selection after a failed search.
        self.locations.clear()
        for place in results:
            label = ', '.join(str(place[k]) for k in ('name', 'admin1', 'country') if place.get(k))
            config = clean_config(dict(latitude=place.get('latitude'), longitude=place.get('longitude'), label=label))
            if config:
                self.locations.addItem(label, config)
        self.message.setText('Choose your location from the results, then press OK.')

    def configuration(self):
        value = dict(self.locations.currentData() or {})
        value['units'] = self.units.currentData()
        return clean_config(value)


class WeatherScreen(QtWidgets.QWidget):
    """A scalable 4:3 cable-weather card, independent of application font controls."""
    def __init__(self, service, parent=None):
        super().__init__(parent)
        self.service = service
        self.page = 0
        self.paused = False
        self.seconds = 0
        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._tick)
        self.service.updated.connect(self.update)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
        if parent:
            parent.installEventFilter(self)
            self.setGeometry(parent.rect())

    def eventFilter(self, watched, event):
        if event.type() == QtCore.QEvent.Resize:
            self.setGeometry(watched.rect())
        return False

    def showEvent(self, event):
        self.timer.start()
        self.service.start()
        super().showEvent(event)

    def hideEvent(self, event):
        self.timer.stop()
        super().hideEvent(event)

    def _tick(self):
        if not self.paused:
            self.seconds += 1
            self.page = (self.seconds // 10) % 3
        self.update()

    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        p.fillRect(self.rect(), QtGui.QColor('black'))
        scale = min(self.width() / 640, self.height() / 480)
        p.translate((self.width() - 640 * scale) / 2, (self.height() - 480 * scale) / 2)
        p.scale(scale, scale)
        gradient = QtGui.QLinearGradient(0, 0, 0, 480)
        gradient.setColorAt(0, QtGui.QColor('#17367f'))
        gradient.setColorAt(1, QtGui.QColor('#070a37'))
        p.fillRect(QtCore.QRectF(0, 0, 640, 480), gradient)
        p.fillRect(QtCore.QRectF(0, 0, 640, 30), QtGui.QColor('#10162e'))
        def text(x, y, w, h, label, size=22, color='#ffffff', align=QtCore.Qt.AlignLeft):
            font = QtGui.QFont('Consolas')
            font.setPixelSize(size)
            font.setBold(True)
            p.setFont(font)
            rect = QtCore.QRectF(x, y, w, h)
            p.setPen(QtGui.QColor('#030525'))
            p.drawText(rect.translated(2, 2), align | QtCore.Qt.AlignVCenter, str(label))
            p.setPen(QtGui.QColor(color))
            label = QtGui.QFontMetrics(font).elidedText(str(label), QtCore.Qt.ElideRight, int(w))
            p.drawText(rect, align | QtCore.Qt.AlignVCenter, label)
        text(26, 0, 380, 30, 'SMTV  •  LOCAL WEATHER', 18, '#d9c080')
        service, data = self.service, self.service.data or {}
        text(420, 0, 195, 30, service.local_time(time.time()) if data else '', 18, '#d9c080', QtCore.Qt.AlignRight)
        titles = ('Current Conditions', 'Hourly Forecast', 'Extended Forecast')
        text(26, 43, 588, 50, titles[self.page], 34, '#ffda59')
        text(26, 96, 588, 30, service.config.get('label', 'Your Local Forecast'), 20, '#8dd9ff')
        p.setPen(QtGui.QPen(QtGui.QColor('#d9ad49'), 3))
        p.drawLine(26, 135, 614, 135)
        unit = '°C' if service.config.get('units') == 'metric' else '°F'
        if not data:
            text(30, 195, 580, 48, 'LOCAL WEATHER', 32, '#ffda59', QtCore.Qt.AlignHCenter)
            text(30, 252, 580, 40, 'SETUP → Weather' if not service.config else 'Retrieving forecast…', 26, align=QtCore.Qt.AlignHCenter)
            text(30, 320, 580, 35, service.status, 15, '#8dd9ff', QtCore.Qt.AlignHCenter)
        elif self.page == 0:
            current = data['current']
            text(36, 157, 280, 100, f'{current["temperature_2m"]:g}{unit}', 70, '#ffda59')
            text(36, 253, 565, 42, condition(current.get('weather_code')), 30)
            windUnit = 'km/h' if service.config['units'] == 'metric' else 'mph'
            direction = current.get('wind_direction_10m')
            compass = ('N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW')[int((direction or 0) / 45 + .5) % 8]
            for y, label in ((306, f'Feels like  {current.get("apparent_temperature", "—")}{unit}'),
                             (342, f'Humidity    {current.get("relative_humidity_2m", "—")}%'),
                             (378, f'Wind        {compass} {current.get("wind_speed_10m", "—")} {windUnit}')):
                text(36, y, 568, 30, label, 22)
            self._icon(p, 405, 165, current.get('weather_code'))
        elif self.page == 1:
            hours = data.get('hourly', {})
            indexes = [i for i, stamp in enumerate(hours.get('time', [])) if stamp >= time.time() - 3600][:5]
            text(32, 145, 580, 30, 'TIME        TEMP   RAIN   CONDITIONS', 17, '#ffda59')
            for row, i in enumerate(indexes):
                def item(key):
                    values = hours.get(key, [])
                    return values[i] if i < len(values) and values[i] is not None else '—'
                y = 186 + row * 43
                text(32, y, 135, 38, service.local_time(hours['time'][i]), 21)
                text(176, y, 96, 38, f'{item("temperature_2m")}{unit}', 21, '#ffda59')
                text(280, y, 80, 38, f'{item("precipitation_probability")}%', 21)
                text(365, y, 250, 38, condition(item('weather_code')), 18)
        else:
            daily = data.get('daily', {})
            for i, stamp in enumerate(daily.get('time', [])[:3]):
                x = 28 + i * 200
                text(x, 158, 186, 32, service.local_time(stamp, '%a').upper(), 27, '#ffda59', QtCore.Qt.AlignHCenter)
                codes = daily.get('weather_code', [])
                code = codes[i] if i < len(codes) else None
                self._icon(p, x + 44, 204, code, .68)
                text(x, 288, 186, 42, condition(code), 17, align=QtCore.Qt.AlignHCenter)
                for key, y, label in (('temperature_2m_max', 340, 'HI'), ('temperature_2m_min', 378, 'LO')):
                    values = daily.get(key, [])
                    value = values[i] if i < len(values) and values[i] is not None else '—'
                    text(x, y, 186, 32, f'{label} {value}{unit}', 26, '#ffda59' if label == 'HI' else '#8dd9ff', QtCore.Qt.AlignHCenter)
        p.fillRect(QtCore.QRectF(0, 431, 640, 49), QtGui.QColor('#10162e'))
        text(26, 434, 588, 23, service.status, 14, '#e6ce90')
        text(26, 457, 588, 20, 'Open-Meteo / GeoNames      SMTV WEATHER', 13, '#adb9dd')
        p.setPen(QtGui.QColor(0, 0, 0, 22))
        for y in range(0, 480, 3):
            p.drawLine(0, y, 640, y)

    @staticmethod
    def _icon(p, x, y, code, scale=1):
        p.save()
        p.translate(x, y)
        p.scale(scale, scale)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        if code in (0, 1, 2):
            p.setPen(QtGui.QPen(QtGui.QColor('#ffd762'), 5))
            p.setBrush(QtGui.QColor('#ffd762'))
            p.drawEllipse(QtCore.QRectF(27, 20, 48, 48))
            for angle in range(0, 360, 45):
                a = math.radians(angle)
                p.drawLine(QtCore.QPointF(51 + 32 * math.cos(a), 44 + 32 * math.sin(a)),
                           QtCore.QPointF(51 + 43 * math.cos(a), 44 + 43 * math.sin(a)))
        if code != 0:
            p.setPen(QtCore.Qt.NoPen)
            p.setBrush(QtGui.QColor('#d6e4f4'))
            for rect in ((14, 42, 60, 40), (40, 27, 58, 52), (70, 45, 50, 37)):
                p.drawEllipse(QtCore.QRectF(*rect))
            p.drawRoundedRect(QtCore.QRectF(28, 60, 81, 23), 10, 10)
            if isinstance(code, int) and code >= 51:
                p.setPen(QtGui.QPen(QtGui.QColor('#75bdff'), 4))
                for xx in (34, 62, 90):
                    p.drawLine(xx, 91, xx - 7, 108)
        p.restore()


class WeatherMusic(QtCore.QObject):
    """Original MIDI lounge cues rendered to PCM for portable playback."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.player = QMediaPlayer(self)
        self.playlist = QMediaPlaylist(self)
        for path in sorted((Path(__file__).resolve().parent / 'assets' / 'weather_music').glob('*.wav')):
            self.playlist.addMedia(QMediaContent(QtCore.QUrl.fromLocalFile(str(path))))
        self.playlist.setPlaybackMode(QMediaPlaylist.Loop)
        self.player.setPlaylist(self.playlist)
        self.player.setVolume(0)

    def sync(self, volume, paused=False, active=False):
        self.player.setVolume(round(max(0, min(100, volume)) * .45))
        if not active:
            self.player.stop()
        elif paused or volume <= 0:
            self.player.pause()
        elif self.playlist.mediaCount():
            self.player.play()

    def stop(self):
        self.player.stop()
