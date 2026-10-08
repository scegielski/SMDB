"""Text subtitle discovery and playback-position overlays for Qt5 video."""
import bisect
import html
import json
import os
from pathlib import Path
import re
import shutil
import sys

from PyQt5 import QtCore, QtGui, QtWidgets, sip


def mediaTool(name):
    bundled = Path(getattr(sys, '_MEIPASS', Path(__file__).parent)) / 'media-tools' / (name + '.exe')
    return str(bundled) if bundled.is_file() else shutil.which(name)


def parseSubtitles(text):
    """Read SRT/WebVTT timestamps; render all cue text as plain text."""
    stamp = r'(\d{1,2}:)?(\d{2}):(\d{2})[,.](\d{3})'
    timing = re.compile(stamp + r'\s*-->\s*' + stamp)

    def milliseconds(parts):
        hours, minutes, seconds, fraction = parts
        return ((int((hours or '0:')[:-1]) * 60 + int(minutes)) * 60 + int(seconds)) * 1000 + int(fraction)

    cues = []
    for block in re.split(r'\n\s*\n', text.replace('\r\n', '\n').replace('\r', '\n').lstrip('\ufeff')):
        lines = block.splitlines()
        for index, line in enumerate(lines):
            match = timing.search(line)
            if match:
                start, end = milliseconds(match.groups()[:4]), milliseconds(match.groups()[4:])
                content = '\n'.join(lines[index + 1:])
                content = html.unescape(re.sub(r'<[^>]*>|\{\\[^}]*\}', '', content))
                if end > start and content.strip():
                    cues.append((start, end, content.strip()))
                break
    return sorted(cues)


def readSubtitles(path):
    data = Path(path).read_bytes()
    if len(data) > 20 * 1024 * 1024:
        raise ValueError('Subtitle file is too large')
    encodings = ('utf-16',) if data.startswith((b'\xff\xfe', b'\xfe\xff')) else ('utf-8-sig', 'cp1252')
    for encoding in encodings:
        try:
            return parseSubtitles(data.decode(encoding))
        except UnicodeError:
            pass
    raise ValueError('Could not decode subtitle file')


class _CaptionLabel(QtWidgets.QLabel):
    """Paint only glyphs, with a small dark outline and no rectangle."""

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.TextAntialiasing)
        painter.setFont(self.font())
        rect = self.rect().adjusted(5, 5, -5, -5)
        flags = QtCore.Qt.AlignCenter | QtCore.Qt.TextWordWrap
        painter.setPen(QtGui.QColor('black'))
        for dx, dy in ((-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1)):
            painter.drawText(rect.translated(dx, dy), flags, self.text())
        painter.setPen(QtGui.QColor('white'))
        painter.drawText(rect, flags, self.text())


class SubtitleController(QtCore.QObject):
    tracksChanged = QtCore.pyqtSignal()
    error = QtCore.pyqtSignal(str)

    def __init__(self, video, parent=None):
        super().__init__(parent)
        self.video = video
        # Captions are ordinary children of the composited video viewport.
        self.canvas = video.viewport() if hasattr(video, 'viewport') else video
        self.label = _CaptionLabel(self.canvas)
        self.label.setTextFormat(QtCore.Qt.PlainText)
        self.label.setAlignment(QtCore.Qt.AlignCenter)
        self.label.setWordWrap(True)
        self.label.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
        self.label.setStyleSheet('QLabel { color: white; background: transparent; border: none; padding: 5px; font-family: Arial; }')
        self.label.hide()
        self.enabled = False
        self._layouting = False
        self.path = None
        self.tracks = []
        self.selected = None
        self.position = 0
        self.cues = []
        self.starts = []
        self.ends = []
        self._jobs = []
        self._generation = 0
        self._probed = False
        self._pendingJobs = 0
        self.lastError = ''
        self.error.connect(self._recordError)
        self.canvas.installEventFilter(self)

    def _recordError(self, message):
        self.lastError = message
        self.tracksChanged.emit()

    def eventFilter(self, watched, event):
        if sip.isdeleted(self.video) or sip.isdeleted(self.label):
            return False
        if event.type() in (QtCore.QEvent.Resize, QtCore.QEvent.Show):
            self._layout()
        return False

    def _layout(self):
        if (sip.isdeleted(self.video) or sip.isdeleted(self.label)
                or self._layouting or not self.enabled or not self.label.text()):
            return
        self._layouting = True
        font = QtGui.QFont('Arial')
        font.setPixelSize(max(15, min(36, round(self.canvas.width() / 32))))
        self.label.setStyleSheet('QLabel { color: white; background: transparent; border: none; padding: 5px; font-family: Arial; font-size: ' + str(font.pixelSize()) + 'px; }')
        self.label.setFont(font)
        width = max(1, round(self.canvas.width() * .9))
        height = min(max(1, self.canvas.height() // 2), self.label.heightForWidth(width) + 10)
        self.label.setGeometry((self.canvas.width() - width) // 2,
                              max(0, self.canvas.height() - height - round(self.canvas.height() * .06)), width, height)
        self.label.raise_()
        self._layouting = False

    def load(self, path):
        self.clear()
        self.path = path
        if path:
            movie = Path(path)
            try:
                self.tracks = [{'id': str(p), 'label': p.name, 'path': str(p)}
                               for p in sorted(movie.parent.iterdir())
                               if p.is_file() and p.suffix.lower() in ('.srt', '.vtt')
                               and (p.stem.casefold() == movie.stem.casefold()
                                    or p.stem.casefold().startswith(movie.stem.casefold() + '.'))]
            except OSError:
                pass
            if self.tracks:
                self.select(self.tracks[0]['id'])
            if self.enabled:
                self.probe()
        self.tracksChanged.emit()

    def clear(self):
        self._generation += 1
        for job in list(self._jobs):
            job.kill()
            job.waitForFinished(1000)
        self._jobs = []
        self.path = None
        self.tracks = []
        self.selected = None
        self.cues, self.starts, self.ends = [], [], []
        self.position = 0
        self._probed = False
        self._pendingJobs = 0
        self.lastError = ''
        if not sip.isdeleted(self.label):
            self.label.clear()
            self.label.hide()

    def setEnabled(self, enabled):
        self.enabled = enabled
        if enabled:
            self.probe()
        self.updatePosition(self.position)

    def _run(self, tool, arguments, callback):
        executable = mediaTool(tool)
        if not executable:
            self.error.emit('Embedded subtitles need FFmpeg and FFprobe. External SRT/VTT files are still available.')
            return
        job = QtCore.QProcess(self)
        generation = self._generation
        self._jobs.append(job)
        self._pendingJobs += 1
        self.tracksChanged.emit()

        def finished(code, status):
            if job in self._jobs:
                self._jobs.remove(job)
            if generation == self._generation:
                self._pendingJobs = max(0, self._pendingJobs - 1)
                if code == 0 and status == QtCore.QProcess.NormalExit:
                    callback(bytes(job.readAllStandardOutput()))
                else:
                    self.error.emit('Could not read subtitles from this movie.')
                self.tracksChanged.emit()
            job.deleteLater()

        job.finished.connect(finished)
        job.errorOccurred.connect(lambda error: self.error.emit('Could not start the subtitle reader.')
                                  if error == QtCore.QProcess.FailedToStart and generation == self._generation else None)
        job.start(executable, arguments)

    def probe(self):
        if self._probed or not self.path:
            return
        self._probed = True
        self._run('ffprobe', ['-v', 'error', '-select_streams', 's', '-show_streams', '-of', 'json', self.path], self._probeFinished)

    def _probeFinished(self, data):
        try:
            streams = json.loads(data).get('streams', [])
        except (ValueError, UnicodeError):
            self.error.emit('Could not read embedded subtitle tracks.')
            return
        textCodecs = {'subrip', 'ass', 'ssa', 'webvtt', 'mov_text', 'text', 'ttml'}
        for stream in streams:
            tags = stream.get('tags', {})
            codec = stream.get('codec_name', '')
            label = 'Embedded: ' + tags.get('title', tags.get('language', 'Track ' + str(stream['index'])))
            supported = codec in textCodecs
            self.tracks.append({'id': 'embedded:' + str(stream['index']), 'label': label + ('' if supported else ' (image subtitles unsupported)'),
                                'stream': stream['index'], 'supported': supported})
        if self.selected is None and self.enabled:
            first = next((track for track in self.tracks if track.get('supported', True)), None)
            if first:
                self.select(first['id'])
        self.tracksChanged.emit()

    def select(self, identifier):
        track = next((track for track in self.tracks if track['id'] == identifier), None)
        if not track or not track.get('supported', True):
            return
        self.selected = identifier
        self.cues, self.starts, self.ends = [], [], []
        self.label.hide()
        if 'path' in track:
            try:
                self._setCues(readSubtitles(track['path']))
            except (OSError, ValueError) as error:
                self.error.emit(str(error))
        else:
            selected = identifier
            self._run('ffmpeg', ['-v', 'error', '-i', self.path, '-map', '0:' + str(track['stream']), '-f', 'srt', 'pipe:1'],
                      lambda data: self._setCues(parseSubtitles(data.decode('utf-8', errors='replace')))
                      if self.selected == selected else None)
        self.tracksChanged.emit()

    def addFile(self, path):
        if not any(track['id'] == path for track in self.tracks):
            self.tracks.append({'id': path, 'path': path, 'label': Path(path).name})
        self.select(path)

    def _setCues(self, cues):
        self.cues = cues
        self.starts = [cue[0] for cue in cues]
        maximum = 0
        self.ends = []
        for _, end, _ in cues:
            maximum = max(maximum, end)
            self.ends.append(maximum)
        self.updatePosition(self.position)
        self.tracksChanged.emit()

    def updatePosition(self, position):
        if sip.isdeleted(self.video) or sip.isdeleted(self.label):
            return
        self.position = position
        texts = []
        if self.enabled:
            index = bisect.bisect_right(self.starts, position) - 1
            while index >= 0 and self.ends[index] > position:
                start, end, text = self.cues[index]
                if start <= position < end:
                    texts.insert(0, text)
                index -= 1
        self.label.setText('\n'.join(texts))
        self._layout()
        self.label.setVisible(bool(texts))
