"""
RetroChannelWidget - a prototype "live TV" experience built from the movie collection.

Each "channel" corresponds to a genre. Channels start movies at random positions,
playing the remainder to the end before advancing to the next program.
Each channel's schedule is anchored to an
absolute wall-clock epoch, so tuning away and back always resumes wherever
the broadcast "would be" had it kept playing the whole time - just like a
real TV channel keeps running whether or not you're watching. Switching
channels (up/down "clicker") and browsing the channel guide both feel
instant because the current channel plus its two neighbors are always
pre-buffered in memory, ready to display immediately. Only the channel
guide's small preview window continues to hop between random clips on the
fly while you're browsing.
"""

import html
import math
import os
import random
import re
import struct
import sys
import tempfile
import time
import wave

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtMultimedia import QMediaContent, QMediaPlayer, QSoundEffect, QVideoProbe
from PyQt5.QtMultimediaWidgets import QVideoWidget

if sys.platform == 'win32':
    import winsound as _winsound
else:
    _winsound = None

DEFAULT_PROGRAM_DURATION_MS = 2 * 60 * 60 * 1000  # schedule estimate until media duration is known
MAX_START_FRACTION = 0.85  # leave at least the final 15% to play
PREFETCH_LEAD_MS = 8000  # start buffering the next movie this far before the slot ends
SCHEDULE_MOVIE_COUNT = 25
MIN_SEEK_RUNWAY_MS = 1500  # never seek closer than this to the end of a movie


def _ensureStandbyToneFile(native=False, gain=0.15):
    """Generate (once) a short looping sine-wave test tone, returning its WAV path."""
    filename = 'smdb_standby_tone_native_v3.wav' if native else 'smdb_standby_tone_v2.wav'
    if native and gain != 0.15:
        filename = f'smdb_standby_tone_native_v3_{round(gain * 10000)}.wav'
    path = os.path.join(tempfile.gettempdir(), filename)
    if os.path.exists(path):
        return path
    sampleRate = 44100
    freqHz = 1000.0
    durationS = 1.0
    # PlaySound has no volume control; bake in the same gain as QSoundEffect.
    amplitude = 0.25 * gain if native else 0.25
    sampleCount = int(sampleRate * durationS)
    frames = bytearray()
    for i in range(sampleCount):
        # A whole number of cycles joins seamlessly; fading each repeat makes
        # the supposedly continuous tone dip once a second.
        value = amplitude * math.sin(2 * math.pi * freqHz * i / sampleRate)
        frames += struct.pack('<h', int(value * 32767))
    with wave.open(path, 'w') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sampleRate)
        wf.writeframes(bytes(frames))
    return path


class StandbyTone(QtCore.QObject):
    """Loops a gentle test-pattern tone while a 'PLEASE STAND BY' screen is on air."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._effect = QSoundEffect(self)
        self._requested = False
        self._muted = False
        self._nativeAvailable = _winsound is not None
        self._nativePlaying = False
        self._tonePath = _ensureStandbyToneFile(native=True) if self._nativeAvailable else None
        self._volume = 0.15
        self._effect.statusChanged.connect(self._syncPlayback)
        self._effect.setLoopCount(QSoundEffect.Infinite)
        self._effect.setVolume(self._volume)
        self._effect.setSource(QtCore.QUrl.fromLocalFile(_ensureStandbyToneFile()))
        app = QtWidgets.QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self.stop)

    def start(self):
        self._requested = True
        self._syncPlayback()

    def _syncPlayback(self):
        if self._nativeAvailable:
            # Qt's loading callbacks cannot run while the main window loads the
            # catalogue. Windows owns this async loop, so startup cannot starve it.
            if self._requested and not self._muted:
                if not self._nativePlaying:
                    try:
                        _winsound.PlaySound(self._tonePath, _winsound.SND_FILENAME
                                            | _winsound.SND_ASYNC | _winsound.SND_LOOP
                                            | _winsound.SND_NODEFAULT)
                        self._nativePlaying = True
                    except RuntimeError:
                        self._nativeAvailable = False
                if self._nativeAvailable:
                    return
            else:
                if self._nativePlaying:
                    _winsound.PlaySound(None, 0)
                    self._nativePlaying = False
                return
        if not self._requested or self._muted:
            # Also cancel a pending play while the WAV is still loading.
            self._effect.stop()
        elif self._effect.status() == QSoundEffect.Ready and not self._effect.isPlaying():
            self._effect.play()

    def stop(self):
        self._requested = False
        self._syncPlayback()

    def setMuted(self, muted):
        self._muted = muted
        self._syncPlayback()

    def setVolume(self, volume):
        gain = 0.15 * max(0, min(100, volume)) / 70
        if gain == self._volume:
            return
        self._volume = gain
        self._effect.setVolume(gain)
        if self._nativeAvailable and gain > 0:
            self._tonePath = _ensureStandbyToneFile(native=True, gain=gain)
            if self._nativePlaying:
                _winsound.PlaySound(None, 0)
                self._nativePlaying = False
        self.setMuted(volume == 0)


class StandByScreen(QtWidgets.QWidget):
    """Retro test-pattern placeholder shown while a channel's clip is buffering."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: #9a9a9a;")

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        rect = self.rect()
        painter.fillRect(rect, QtGui.QColor('#9a9a9a'))

        cx, cy = rect.center().x(), rect.center().y()
        radius = min(rect.width(), rect.height()) * 0.42

        pen = QtGui.QPen(QtGui.QColor('#222222'))
        pen.setWidth(2)
        painter.setPen(pen)
        painter.drawEllipse(QtCore.QPointF(cx, cy), radius, radius)
        painter.drawEllipse(QtCore.QPointF(cx, cy), radius * 0.5, radius * 0.5)
        for i in range(12):
            angle = math.radians(i * 30)
            x = cx + radius * math.cos(angle)
            y = cy + radius * math.sin(angle)
            painter.drawLine(QtCore.QPointF(cx, cy), QtCore.QPointF(x, y))

        margin = 30
        corners = (
            (margin, margin), (rect.width() - margin, margin),
            (margin, rect.height() - margin), (rect.width() - margin, rect.height() - margin),
        )
        for dx, dy in corners:
            painter.drawEllipse(QtCore.QPointF(dx, dy), 18, 18)
            painter.drawLine(QtCore.QPointF(dx - 18, dy), QtCore.QPointF(dx + 18, dy))
            painter.drawLine(QtCore.QPointF(dx, dy - 18), QtCore.QPointF(dx, dy + 18))

        font = QtGui.QFont(self.font())
        font.setWeight(QtGui.QFont.Black)
        painter.setFont(font)
        textRect = rect.adjusted(10, 0, -10, 0)
        painter.setPen(QtGui.QColor('black'))
        painter.drawText(textRect.translated(2, 2), QtCore.Qt.AlignCenter, "PLEASE STAND BY")
        painter.setPen(QtGui.QColor('white'))
        painter.drawText(textRect, QtCore.Qt.AlignCenter, "PLEASE STAND BY")


class ClipSlot(QtCore.QObject):
    """A single QMediaPlayer/QVideoWidget pair used as a playback buffer."""

    becameReady = QtCore.pyqtSignal()
    playbackStarted = QtCore.pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.player = QMediaPlayer(None, QMediaPlayer.VideoSurface)
        self.videoWidget = QVideoWidget()
        self.videoWidget.setStyleSheet("background: black;")
        self.player.setVideoOutput(self.videoWidget)
        self.player.setVolume(0)

        self.path = None
        self.duration = 0
        self._ready = False
        self._wantsRandomSeek = False
        self._pendingSeekFraction = None
        self._pendingSeekExtraMs = 0
        self._autoplayAfterLoad = False
        self._hasPlayingFrame = False
        self._lastPlaybackPosition = None

        self.player.durationChanged.connect(self._onDurationChanged)
        self.videoProbe = QVideoProbe(self)
        self._probeSupported = self.videoProbe.setSource(self.player)
        self.videoProbe.videoFrameProbed.connect(self._onVideoFrame)
        self.player.positionChanged.connect(self._onPlaybackPosition)

    def _onVideoFrame(self, frame):
        if (frame.isValid() and self.isReady()
                and self.player.state() == QMediaPlayer.PlayingState):
            self._markPlaybackStarted()

    def _onPlaybackPosition(self, position):
        # Some platforms lack frame probes. Require actual progress, not the
        # position jump caused by the initial seek, before dismissing stand-by.
        previous = self._lastPlaybackPosition
        self._lastPlaybackPosition = position
        if (not self._probeSupported and self.isReady() and previous is not None
                and 0 < position - previous < 2000
                and self.player.state() == QMediaPlayer.PlayingState
                and self.player.mediaStatus() == QMediaPlayer.BufferedMedia):
            self._markPlaybackStarted()

    def _markPlaybackStarted(self):
        if not self._hasPlayingFrame:
            self._hasPlayingFrame = True
            self.playbackStarted.emit()

    def isReady(self):
        return self._ready and self.path is not None

    def load(self, path, autoplay=False, seekFraction=None, extraMs=0):
        """Begin loading a video file. Becomes ready once duration is known.

        If `seekFraction` is given, the slot seeks to that fraction of the
        movie's duration plus `extraMs` once loaded (used for clock-synced
        channel playback). Otherwise it falls back to a random start point
        (used by the channel guide's live preview).
        """
        self.path = path
        self.duration = 0
        self._ready = False
        self._hasPlayingFrame = False
        self._lastPlaybackPosition = None
        self._autoplayAfterLoad = autoplay
        self._pendingSeekFraction = seekFraction
        self._pendingSeekExtraMs = extraMs
        self._wantsRandomSeek = seekFraction is None
        self.player.setMedia(QMediaContent(QtCore.QUrl.fromLocalFile(path)))
        self.player.pause()

    def _onDurationChanged(self, duration):
        self.duration = duration
        if duration > 0 and (self._wantsRandomSeek or self._pendingSeekFraction is not None):
            if self._pendingSeekFraction is not None:
                self.seekTo(self._pendingSeekFraction, self._pendingSeekExtraMs)
                self._pendingSeekFraction = None
            else:
                self.seekRandom()
            self._wantsRandomSeek = False
            self._ready = True
            if self._autoplayAfterLoad:
                self.player.play()
            self.becameReady.emit()

    def seekRandom(self, runway_ms=10000):
        """Jump to a random position, leaving at least `runway_ms` of runway."""
        if self.duration > runway_ms:
            pos = random.randint(0, self.duration - runway_ms)
        elif self.duration > 1500:
            pos = random.randint(0, self.duration - 1500)
        else:
            pos = 0
        self.player.setPosition(pos)

    def seekTo(self, fraction, extraMs=0):
        """Seek to `fraction` of the movie's duration plus `extraMs`, clamped to valid range."""
        if self.duration <= 0:
            return
        maxPos = max(0, self.duration - MIN_SEEK_RUNWAY_MS)
        pos = int(fraction * self.duration) + int(extraMs)
        pos = max(0, min(pos, maxPos))
        self.player.setPosition(pos)

    def setVolume(self, volume):
        self.player.setVolume(volume)

    def play(self):
        self.player.play()

    def pause(self):
        self.player.pause()

    def stop(self):
        self._hasPlayingFrame = False
        self._lastPlaybackPosition = None
        self._ready = False
        self.path = None
        self.player.stop()
        self.player.setMedia(QMediaContent())
        self.path = None
        self.duration = 0
        self._ready = False
        self._wantsRandomSeek = False
        self._pendingSeekFraction = None


class ChannelClock:
    """
    Tracks a single channel's continuous broadcast schedule in real (wall-clock)
    time. Movies air back-to-back using catalogue runtimes as estimates,
    corrected by media durations and actual playback completion. Re-syncing
    to an absolute start time (epoch), e.g. after tuning away
    and back) always resumes exactly where the broadcast "would be" had it
    kept playing the whole time - including skipping ahead across multiple
    movies if you were away longer than one slot.
    """

    def __init__(self, rows, durationGetter=None):
        self.rows = list(rows)
        self.epoch = time.monotonic()
        self._rotation = []
        self._offsetFractions = {}
        self._startOverrides = {}
        self._resumePositions = {}
        self._durations = {}
        self._resolvedRows = {}
        self.durationGetter = durationGetter
        self._extendRotation()

    def _extendRotation(self):
        self._rotation = random.sample(self.rows, min(SCHEDULE_MOVIE_COUNT, len(self.rows)))

    def _rowForSlot(self, slotIndex):
        return self._rotation[slotIndex % len(self._rotation)]

    def _offsetFractionForSlot(self, slotIndex):
        if slotIndex in self._startOverrides:
            return self._startOverrides[slotIndex]
        slotIndex %= len(self._rotation)
        if slotIndex not in self._offsetFractions:
            self._offsetFractions[slotIndex] = random.uniform(0.0, MAX_START_FRACTION)
        return self._offsetFractions[slotIndex]

    def durationForSlot(self, slotIndex):
        if slotIndex not in self._durations:
            row = self._resolvedRows.get(slotIndex, self._rowForSlot(slotIndex))
            duration = self.durationGetter(row) if self.durationGetter else 0
            duration = duration or DEFAULT_PROGRAM_DURATION_MS
            self._durations[slotIndex] = max(1, duration * (1 - self._offsetFractionForSlot(slotIndex)))
        return self._durations[slotIndex]

    def slotStartMs(self, slotIndex):
        return sum(self.durationForSlot(i) for i in range(slotIndex))

    def recordMedia(self, slotIndex, row, duration=0):
        self._resolvedRows[slotIndex] = row
        if duration > 0:
            self._durations[slotIndex] = max(1, duration * (1 - self._offsetFractionForSlot(slotIndex)))

    def finishSlot(self, slotIndex):
        # Playback completion is authoritative, including buffering delays and
        # inaccurate catalogue runtimes. Anchor the next movie to this moment.
        elapsed = (time.monotonic() - self.epoch) * 1000.0
        self._durations[slotIndex] = max(1, elapsed - self.slotStartMs(slotIndex) - 1)

    def jumpToSlot(self, slotIndex):
        self.epoch = time.monotonic() - (self.slotStartMs(slotIndex) + 1) / 1000.0

    def repositionSlot(self, slotIndex, row, duration, position):
        # Manual seeking affects this airing only, keeping the loop's assigned
        # random starting position for future airings.
        self._startOverrides[slotIndex] = position / duration
        self.recordMedia(slotIndex, row, duration)
        self.jumpToSlot(slotIndex)

    def startSlotAtBeginning(self, slotIndex):
        self._startOverrides[slotIndex] = 0.0
        self._durations.pop(slotIndex, None)

    def rememberPosition(self, slotIndex, row, duration, position):
        self._resumePositions[row] = (row, duration, position)

    def resumeInfoForSlot(self, slotIndex):
        row = self._resolvedRows.get(slotIndex, self._rowForSlot(slotIndex))
        return self._resumePositions.get(row)

    def resumeSlot(self, slotIndex):
        saved = self.resumeInfoForSlot(slotIndex)
        if saved is None:
            return False
        row, duration, position = saved
        self.repositionSlot(slotIndex, row, duration, position)
        return True

    def candidateRows(self, slotIndex, count=5):
        """Rows for `slotIndex` and the following slots, used as fallbacks
        when a scheduled movie has no resolvable video file."""
        return [self._resolvedRows.get(slotIndex + i, self._rowForSlot(slotIndex + i))
                for i in range(count)]

    def whatsOnNow(self):
        """Return (slotIndex, row, offsetFraction, positionInSlotMs, remainingMs)."""
        elapsedMs = (time.monotonic() - self.epoch) * 1000.0
        slotIndex = 0
        positionInSlotMs = max(0, elapsedMs)
        while positionInSlotMs >= self.durationForSlot(slotIndex):
            positionInSlotMs -= self.durationForSlot(slotIndex)
            slotIndex += 1
        row = self._resolvedRows.get(slotIndex, self._rowForSlot(slotIndex))
        offsetFraction = self._offsetFractionForSlot(slotIndex)
        remainingMs = self.durationForSlot(slotIndex) - positionInSlotMs
        return slotIndex, row, offsetFraction, positionInSlotMs, remainingMs

    def slotInfo(self, slotIndex):
        row = self._resolvedRows.get(slotIndex, self._rowForSlot(slotIndex))
        offsetFraction = self._offsetFractionForSlot(slotIndex)
        return row, offsetFraction


class _PathResolveSignals(QtCore.QObject):
    finished = QtCore.pyqtSignal(int, object, object)  # requestId, row, path


class _PathResolveTask(QtCore.QRunnable):
    """Resolves a scheduled slot's video file off the GUI thread (disk I/O can be slow)."""

    def __init__(self, requestId, candidateRows, resolver):
        super().__init__()
        self.requestId = requestId
        self.candidateRows = candidateRows
        self.resolver = resolver
        self.signals = _PathResolveSignals()

    def run(self):
        for row in self.candidateRows:
            path = self.resolver(row)
            if path:
                self.signals.finished.emit(self.requestId, row, path)
                return
        self.signals.finished.emit(self.requestId, None, None)


class ChannelEngine(QtCore.QObject):
    """
    Drives a single genre "channel": continuously plays movies from the genre
    back-to-back according to a `ChannelClock`, pre-buffering the next movie
    so cuts between programs are seamless.
    """

    programChanged = QtCore.pyqtSignal()

    def __init__(self, channelNumber, genreName, clock, resolver, titleGetter, parent=None):
        super().__init__(parent)
        self.channelNumber = channelNumber
        self.genreName = genreName
        self.clock = clock
        self.resolver = resolver
        self.titleGetter = titleGetter

        self.container = QtWidgets.QWidget()
        self._stack = QtWidgets.QStackedLayout(self.container)
        self._stack.setContentsMargins(0, 0, 0, 0)

        self.standbyScreen = StandByScreen()
        self.slotA = ClipSlot(self)
        self.slotB = ClipSlot(self)
        self._stack.addWidget(self.standbyScreen)
        self._stack.addWidget(self.slotA.videoWidget)
        self._stack.addWidget(self.slotB.videoWidget)
        self._stack.setCurrentWidget(self.standbyScreen)

        self.slotA.becameReady.connect(lambda: self._onSlotReady(self.slotA))
        self.slotB.becameReady.connect(lambda: self._onSlotReady(self.slotB))
        self.slotA.playbackStarted.connect(lambda: self._onSlotReady(self.slotA))
        self.slotB.playbackStarted.connect(lambda: self._onSlotReady(self.slotB))
        for slot in (self.slotA, self.slotB):
            slot.player.mediaStatusChanged.connect(lambda _status, s=slot: self._onSlotReady(s))
            slot.player.stateChanged.connect(lambda _state, s=slot: self._onSlotReady(s))
            slot.player.durationChanged.connect(lambda _duration, s=slot: self._onMovieDuration(s))
            slot.player.mediaStatusChanged.connect(lambda status, s=slot: self._onMovieStatus(s, status))

        self.activeSlot = self.slotA
        self.standbySlot = self.slotB

        self.desiredVolume = 0
        self.currentSlotIndex = None
        self.currentRow = None
        self.currentTitle = ''
        self.nextRow = None
        self.nextTitle = ''
        self._prefetchStarted = False
        self._prefetchedSlotIndex = None

        self._resolveSeq = 0
        self._tuneRequestId = None
        self._prefetchRequestId = None
        self._hardCutRequestId = None
        self._previousNavigationSlot = None
        self._beginningResume = None

        self.advanceTimer = QtCore.QTimer(self)
        self.advanceTimer.setSingleShot(True)
        self.advanceTimer.timeout.connect(self._onAdvanceTimer)

        self.prefetchTimer = QtCore.QTimer(self)
        self.prefetchTimer.setSingleShot(True)
        self.prefetchTimer.timeout.connect(self._beginPrefetch)

        # Occasionally the video renderer silently stalls on a frozen frame while the player
        # still reports PlayingState (a Qt Multimedia backend quirk, not something this code
        # causes) - previously the only recovery was manually toggling the guide on/off, which
        # happens to force a rebind via refreshVideoOutputs(). Do that automatically instead.
        self._watchdogLastPosition = None
        self.watchdogTimer = QtCore.QTimer(self)
        self.watchdogTimer.timeout.connect(self._checkForFrozenPlayback)
        self.watchdogTimer.start(3000)

    # -- schedule resolution --------------------------------------------------
    def _startResolve(self, slotIndex, requestAttr, onDone):
        """Resolve candidates for `slotIndex` on a worker thread; `onDone(row, path)` runs on
        the GUI thread once finished, and is skipped if a newer request has superseded it."""
        self._resolveSeq += 1
        requestId = self._resolveSeq
        setattr(self, requestAttr, requestId)
        candidateRows = self.clock.candidateRows(slotIndex, count=5)
        task = _PathResolveTask(requestId, candidateRows, self.resolver)
        task.signals.finished.connect(
            lambda rid, row, path, attr=requestAttr, cb=onDone: self._finishResolve(rid, row, path, attr, cb)
        )
        QtCore.QThreadPool.globalInstance().start(task)

    def _finishResolve(self, requestId, row, path, requestAttr, onDone):
        if getattr(self, requestAttr) != requestId:
            return  # stale: superseded by a newer tune/prefetch/cut, or the engine was shut down
        onDone(row, path)

    # -- lifecycle ----------------------------------------------------------
    def start(self):
        if self.currentRow is None:
            return self._tuneIn()
        return True

    def _tuneIn(self):
        """Sync playback to wherever the channel clock says we should be right now."""
        slotIndex, _, offsetFraction, positionInSlotMs, remainingMs = self.clock.whatsOnNow()
        self._stack.setCurrentWidget(self.standbyScreen)

        def onResolved(row, path):
            if path is None:
                return  # no playable movie found for this slot; stay on stand-by
            self.currentSlotIndex = slotIndex
            self.currentRow = row
            self.currentTitle = self.titleGetter(row)
            self.clock.recordMedia(slotIndex, row)
            self.nextRow = None
            self.nextTitle = ''
            self._prefetchStarted = False
            self._prefetchedSlotIndex = None

            self.activeSlot.setVolume(self.desiredVolume)
            self.activeSlot.load(path, autoplay=True, seekFraction=offsetFraction, extraMs=positionInSlotMs)
            self.programChanged.emit()

            self._scheduleAdvance(remainingMs)
            self._maybeSchedulePrefetch(remainingMs)
            self._onMovieDuration(self.activeSlot)

        self._startResolve(slotIndex, '_tuneRequestId', onResolved)
        return True

    def shutdown(self):
        """Fully stop and release this engine's players."""
        self.advanceTimer.stop()
        self.prefetchTimer.stop()
        self.watchdogTimer.stop()
        # Invalidate any in-flight background resolves so their results are ignored on arrival.
        self._resolveSeq += 1
        self._tuneRequestId = self._resolveSeq
        self._resolveSeq += 1
        self._prefetchRequestId = self._resolveSeq
        self._resolveSeq += 1
        self._hardCutRequestId = self._resolveSeq
        self.slotA.stop()
        self.slotB.stop()
        self.currentRow = None
        self.currentSlotIndex = None
        self._stack.setCurrentWidget(self.standbyScreen)

    def _onSlotReady(self, slot):
        # PlayingState/BufferedMedia can both precede the first video frame.
        if (slot is self.activeSlot and slot.isReady() and slot._hasPlayingFrame
                and slot.player.state() == QMediaPlayer.PlayingState):
            self._stack.setCurrentWidget(slot.videoWidget)

    def _checkForFrozenPlayback(self):
        slot = self.activeSlot
        if slot.player.state() != QMediaPlayer.PlayingState:
            self._watchdogLastPosition = None
            return
        position = slot.player.position()
        if position == self._watchdogLastPosition:
            self.refreshVideoOutputs()
        self._watchdogLastPosition = position

    def isShowingStandby(self):
        return self._stack.currentWidget() is self.standbyScreen

    def setDesiredVolume(self, volume):
        self.desiredVolume = volume
        self.activeSlot.setVolume(volume)

    def refreshVideoOutputs(self):
        """Re-bind each slot's video surface to its widget - some backends lose this binding
        when the widget is reparented (e.g. into/out of the guide preview frame)."""
        for slot in (self.slotA, self.slotB):
            slot.player.setVideoOutput(slot.videoWidget)
            slot.videoWidget.show()
            if slot.player.state() == QMediaPlayer.PlayingState:
                # Nudge the backend to actually paint a frame into the freshly (re-)bound
                # surface - some Qt Multimedia backends don't repaint on their own after the
                # video output changes mid-playback.
                slot.player.play()

    # -- scheduling -----------------------------------------------------------
    def _onMovieDuration(self, slot):
        if (slot is self.activeSlot and self.currentRow is not None
                and self.currentSlotIndex is not None and slot.duration > 0
                and slot.player.mediaStatus() != QMediaPlayer.EndOfMedia):
            self.clock.recordMedia(self.currentSlotIndex, self.currentRow, slot.duration)
            remainingMs = max(50, slot.duration - slot.player.position())
            self._scheduleAdvance(remainingMs)
            self.prefetchTimer.stop()
            self._maybeSchedulePrefetch(remainingMs)

    def _onMovieStatus(self, slot, status):
        if (slot is self.activeSlot and status == QMediaPlayer.EndOfMedia
                and self.currentSlotIndex is not None):
            self.clock.finishSlot(self.currentSlotIndex)
            self._onAdvanceTimer()

    def _scheduleAdvance(self, remainingMs):
        self.advanceTimer.start(max(50, int(remainingMs)))

    def _maybeSchedulePrefetch(self, remainingMs):
        leadMs = remainingMs - PREFETCH_LEAD_MS
        if leadMs <= 0:
            self._beginPrefetch()
        else:
            self.prefetchTimer.start(int(leadMs))

    def _beginPrefetch(self):
        if self._prefetchStarted or self.currentSlotIndex is None:
            return
        self._prefetchStarted = True
        nextSlotIndex = self.currentSlotIndex + 1
        _, offsetFraction = self.clock.slotInfo(nextSlotIndex)

        def onResolved(row, path):
            if path:
                self.nextRow = row
                self.nextTitle = self.titleGetter(row)
                self.clock.recordMedia(nextSlotIndex, row)
                self._prefetchedSlotIndex = nextSlotIndex
                self.standbySlot.load(path, autoplay=False, seekFraction=offsetFraction, extraMs=0)
            else:
                self.nextRow = None
                self.nextTitle = ''
                self._prefetchedSlotIndex = None

        self._startResolve(nextSlotIndex, '_prefetchRequestId', onResolved)

    def _onAdvanceTimer(self):
        """Slot boundary reached (or we're catching up after being away): re-sync to the clock."""
        if (self.currentRow is not None
                and self.activeSlot.player.mediaStatus() != QMediaPlayer.EndOfMedia):
            # An estimated schedule boundary must never interrupt playback.
            # Wait for EndOfMedia, even if loading or buffering ran long.
            self._scheduleAdvance(1000)
            return
        slotIndex, _, offsetFraction, positionInSlotMs, remainingMs = self.clock.whatsOnNow()
        if slotIndex == self.currentSlotIndex:
            # Timer fired a hair early due to rounding; check again shortly.
            self._scheduleAdvance(remainingMs)
            return

        self._prefetchStarted = False
        self.prefetchTimer.stop()
        if self.standbySlot.isReady() and self._prefetchedSlotIndex == slotIndex:
            self._promote(slotIndex, positionInSlotMs)
            self._scheduleAdvance(remainingMs)
            self._maybeSchedulePrefetch(remainingMs)
            self._onMovieDuration(self.activeSlot)
        else:
            self._hardCut(slotIndex, offsetFraction, positionInSlotMs)

    def _promote(self, slotIndex, positionInSlotMs):
        """Swap in the already-buffered standby slot, correcting for any scheduling drift."""
        self.activeSlot.pause()
        self.activeSlot, self.standbySlot = self.standbySlot, self.activeSlot
        if positionInSlotMs > 250:
            self.activeSlot.player.setPosition(self.activeSlot.player.position() + int(positionInSlotMs))
        self._stack.setCurrentWidget(self.activeSlot.videoWidget)
        self.activeSlot.setVolume(self.desiredVolume)
        self.currentSlotIndex = slotIndex
        self.currentRow = self.nextRow
        self.currentTitle = self.nextTitle
        self.clock.recordMedia(slotIndex, self.currentRow, self.activeSlot.duration)
        self.activeSlot.play()
        self.standbySlot.stop()
        self.nextRow = None
        self.nextTitle = ''
        self._prefetchedSlotIndex = None
        self.programChanged.emit()

    def _hardCut(self, slotIndex, offsetFraction, positionInSlotMs):
        """Standby wasn't buffered in time (long gap or slow load) - load directly, showing stand-by until ready."""
        self.standbySlot.stop()
        self.activeSlot.stop()
        self.currentRow = None
        self.currentSlotIndex = slotIndex
        self.advanceTimer.stop()
        self._stack.setCurrentWidget(self.standbyScreen)

        def onResolved(row, path):
            if path is None:
                return
            self.currentSlotIndex = slotIndex
            self.currentRow = row
            self.currentTitle = self.titleGetter(row)
            self.clock.recordMedia(slotIndex, row)
            self.nextRow = None
            self.nextTitle = ''
            self._prefetchedSlotIndex = None
            self.activeSlot.setVolume(self.desiredVolume)
            self.activeSlot.load(path, autoplay=True, seekFraction=offsetFraction, extraMs=positionInSlotMs)
            self.programChanged.emit()
            remainingMs = self.clock.durationForSlot(slotIndex) - positionInSlotMs
            self._scheduleAdvance(remainingMs)
            self._maybeSchedulePrefetch(remainingMs)
            self._onMovieDuration(self.activeSlot)

        self._startResolve(slotIndex, '_hardCutRequestId', onResolved)

    def skipProgram(self, step, beginning=False, startUnvisited=False):
        current = self.currentSlotIndex
        if current is None:
            current = self.clock.whatsOnNow()[0]
        if not beginning and current == self._previousNavigationSlot:
            if step < 0 and self._beginningResume is None:
                saved = self.clock.resumeInfoForSlot(current)
                slot = self.activeSlot
                if saved is None and self.currentRow is not None and slot.isReady() and slot.duration > 0:
                    saved = (self.currentRow, slot.duration, slot.player.position())
                if saved is not None and self.seekCurrentFilm(beginning=True):
                    self._beginningResume = saved
                return
            if step > 0 and self._beginningResume is not None:
                _row, _duration, position = self._beginningResume
                if self._seekFilmPosition(position):
                    self._beginningResume = None
                    self._previousNavigationSlot = None
                return
        target = current + step
        if target < 0:
            target = len(self.clock._rotation) - 1
        if startUnvisited and self.clock.resumeInfoForSlot(target) is None:
            beginning = True
        slot = self.activeSlot
        if self.currentRow is not None and slot.isReady() and slot.duration > 0:
            self.clock.rememberPosition(current, self.currentRow, slot.duration, slot.player.position())
        self.advanceTimer.stop()
        self.prefetchTimer.stop()
        self._resolveSeq += 1
        for attr in ('_tuneRequestId', '_prefetchRequestId', '_hardCutRequestId'):
            setattr(self, attr, self._resolveSeq)
        self.slotA.stop()
        self.slotB.stop()
        self.currentRow = None
        self.currentTitle = ''
        self.nextRow = None
        self.nextTitle = ''
        self.currentSlotIndex = target
        self._prefetchStarted = False
        self._prefetchedSlotIndex = None
        self._previousNavigationSlot = target if step < 0 and not beginning else None
        self._beginningResume = None
        if beginning:
            self.clock.startSlotAtBeginning(target)
        else:
            self.clock.resumeSlot(target)
        self.clock.jumpToSlot(target)
        self._tuneIn()

    def seekCurrentFilm(self, offsetMs=0, beginning=False):
        target = 0 if beginning else self.activeSlot.player.position() + offsetMs
        return self._seekFilmPosition(target)

    def _seekFilmPosition(self, target):
        slot = self.activeSlot
        if self.currentRow is None or self.currentSlotIndex is None or not slot.isReady() or slot.duration <= 0:
            return False
        target = max(0, min(slot.duration - 1, int(target)))
        slot.player.setPosition(target)
        self.clock.repositionSlot(self.currentSlotIndex, self.currentRow, slot.duration, target)
        self.advanceTimer.stop()
        self.prefetchTimer.stop()
        remaining = max(50, slot.duration - target)
        self._scheduleAdvance(remaining)
        self._maybeSchedulePrefetch(remaining)
        return True


class _GuideTopBar(QtWidgets.QWidget):
    """Guide header row whose preview frame scales (3:2) with the row's height."""

    def resizeEvent(self, event):
        super().resizeEvent(event)
        h = max(60, self.height() - 4)
        self.previewFrame.setFixedSize(int(h * 1.5), h)


class _OverlayArea(QtWidgets.QWidget):
    """Keeps a base widget filling the area, with floating overlay children on top."""

    def __init__(self, base, parent=None):
        super().__init__(parent)
        self._overlays = []
        layout = QtWidgets.QStackedLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(base)

    def addOverlay(self, widget):
        widget.setParent(self)
        self._overlays.append(widget)
        widget.raise_()
        self._layoutOverlay(widget)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        for w in self._overlays:
            self._layoutOverlay(w)

    def _layoutOverlay(self, widget):
        anchor = getattr(widget, '_overlayAnchor', 'fill')
        rect = self.rect()
        if anchor == 'fill':
            widget.setGeometry(rect)
        elif anchor == 'bottom':
            h = widget.sizeHint().height() + 10
            widget.setGeometry(20, max(0, rect.height() - h - 20), rect.width() - 40, h)
        elif anchor == 'center':
            w = min(rect.width() - 80, 760)
            h = min(rect.height() - 80, 560)
            widget.setGeometry((rect.width() - w) // 2, (rect.height() - h) // 2, w, h)


class RetroChannelWidget(QtWidgets.QWidget):
    """
    Prototype "Retro TV" tab: genre channels with a clicker (channel up/down)
    and a teletext-style channel guide, all built from the movie collection.
    """

    MIN_MOVIES_PER_CHANNEL = 10
    NEIGHBOR_WARM_COUNT = 1  # warm this many channels on either side for instant surfing
    DEFAULT_FONT_SCALE = 2.0
    RETRO_FONT_FAMILIES = (
        'VT323', 'PxPlus IBM VGA8', 'Perfect DOS VGA 437',
        'Lucida Console', 'Courier New', 'Liberation Mono', 'DejaVu Sans Mono',
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self.mainWindow = parent
        self._videoPathCache = {}
        self._descriptionCache = {}
        self.channels = []
        self.engines = {}
        self.currentIndex = 0
        self.isActive = False
        self.guideVisible = False
        self._showGuideOnStart = True
        self.guideHighlightIndex = 0
        self.guidePreviewSlot = None
        self._guidePreviewHostedEngine = None
        self.masterVolume = 70
        self._lastVolume = 70
        self.isFullScreenActive = False
        self._fullScreenTransition = False
        self._fsWindow = None
        self.standbyTone = StandbyTone(self)

        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        font = QtGui.QFont(self.font())
        installed = {family.casefold(): family for family in QtGui.QFontDatabase().families()}
        family = next(
            (installed[name.casefold()] for name in self.RETRO_FONT_FAMILIES if name.casefold() in installed),
            QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.FixedFont).family(),
        )
        font.setFamily(family)
        font.setStyleHint(QtGui.QFont.TypeWriter)
        font.setFixedPitch(True)
        font.setPixelSize(14)
        self.setFont(font)
        # Qt style sheets with font-size can override ordinary QFont inheritance.
        self.setStyleSheet(f'QWidget {{ font-family: "{family}"; }}')
        self._buildUI()
        self._baseFont = QtGui.QFont(font)
        self._fontStyles = [
            (widget, widget.styleSheet())
            for widget in self.findChildren(QtWidgets.QWidget)
            if re.search(r'font-size:\s*\d+px', widget.styleSheet())
        ]
        self.setFontScale(self.DEFAULT_FONT_SCALE)

        self.bannerTimer = QtCore.QTimer(self)
        self.bannerTimer.setSingleShot(True)
        self.bannerTimer.timeout.connect(self.banner.hide)

        self.guidePreviewTimer = QtCore.QTimer(self)
        self.guidePreviewTimer.setInterval(1000)
        self.guidePreviewTimer.timeout.connect(self._onGuidePreviewTick)

        # Standby tone/screen is a continuous fallback, not an event triggered once: every tick
        # we just ask "is the current channel's stand-by screen actually on screen right now?"
        # and make the tone match - no connect/disconnect ordering or missed-signal windows to
        # get wrong (a past event-driven version of this was unreliable around engine
        # creation/teardown races).
        self.standbyPollTimer = QtCore.QTimer(self)
        self.standbyPollTimer.setInterval(150)
        self.standbyPollTimer.timeout.connect(self._syncStandbyTone)

        self._updateEmptyState()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _buildUI(self):
        rootLayout = QtWidgets.QHBoxLayout(self)
        rootLayout.setContentsMargins(4, 4, 4, 4)
        rootLayout.setSpacing(6)

        self.displayStack = QtWidgets.QStackedWidget()
        self.displayStack.setStyleSheet("background: black;")
        self.globalStandby = StandByScreen()
        self.displayStack.addWidget(self.globalStandby)
        self.overlayArea = _OverlayArea(self.displayStack)

        leftColumn = QtWidgets.QVBoxLayout()
        self.leftColumn = leftColumn
        leftColumn.setSpacing(4)
        leftColumn.addWidget(self.overlayArea, 1)

        self.nowPlayingLabel = QtWidgets.QLabel("")
        self.nowPlayingLabel.setAlignment(QtCore.Qt.AlignCenter)
        self.nowPlayingLabel.setWordWrap(True)
        self.nowPlayingLabel.setStyleSheet(
            "color: white; background: #111; font-size: 14px; font-weight: bold;"
            "padding: 6px; border: 1px solid #444; border-radius: 4px;"
        )
        leftColumn.addWidget(self.nowPlayingLabel)

        rootLayout.addLayout(leftColumn, 1)

        self.banner = QtWidgets.QLabel()
        self.banner.setWordWrap(True)
        self.banner.setStyleSheet(
            "color: white; background: rgba(0,0,0,175); font-size: 14px; font-weight: bold;"
            "padding: 10px; border-radius: 6px;"
        )
        self.banner._overlayAnchor = 'bottom'
        self.overlayArea.addOverlay(self.banner)
        self.banner.hide()

        self.guideOverlay = self._buildGuideOverlay()
        self.guideOverlay._overlayAnchor = 'fill'
        self.overlayArea.addOverlay(self.guideOverlay)
        self.guideOverlay.hide()

        # -- side "clicker" panel --
        self.sideControls = QtWidgets.QFrame()
        self.sideControls.setStyleSheet(
            "background: #222; border: 2px solid #555; border-radius: 10px;"
        )
        sideLayout = QtWidgets.QVBoxLayout(self.sideControls)
        sideLayout.setSpacing(8)

        self.channelLcd = QtWidgets.QLabel("--")
        self.channelLcd.setAlignment(QtCore.Qt.AlignCenter)
        self.channelLcd.setStyleSheet(
            "background: black; color: #3fff6b; font-size: 22px;"
            "border: 2px inset #555; padding: 6px;"
        )
        sideLayout.addWidget(self.channelLcd)

        self.genreLabel = QtWidgets.QLabel("")
        self.genreLabel.setAlignment(QtCore.Qt.AlignCenter)
        self.genreLabel.setWordWrap(True)
        self.genreLabel.setStyleSheet("color: #ccc; font-size: 11px;")
        sideLayout.addWidget(self.genreLabel)

        upButton = QtWidgets.QPushButton("CH \u25B2")
        upButton.clicked.connect(self.channelUp)
        downButton = QtWidgets.QPushButton("CH \u25BC")
        downButton.clicked.connect(self.channelDown)
        for b in (upButton, downButton):
            b.setStyleSheet(
                "background: #444; color: white; font-weight: bold; font-size: 14px;"
                "border-radius: 6px; padding: 10px;"
            )
            b.setFocusPolicy(QtCore.Qt.NoFocus)
        sideLayout.addWidget(upButton)
        sideLayout.addWidget(downButton)

        self.nextProgramButton = QtWidgets.QPushButton('NEXT ▶')
        self.previousProgramButton = QtWidgets.QPushButton('PREV ◀')
        for button, step, name in ((self.nextProgramButton, 1, 'Next program'),
                                   (self.previousProgramButton, -1, 'Previous program')):
            button.setStyleSheet(upButton.styleSheet())
            button.setFocusPolicy(QtCore.Qt.NoFocus)
            button.setAccessibleName(name)
            button.setToolTip(name + ' on this channel')
            button.clicked.connect(lambda _checked=False, direction=step: self.skipProgram(direction))
            sideLayout.addWidget(button)

        self.backTenButton = QtWidgets.QPushButton('◀')
        self.forwardTenButton = QtWidgets.QPushButton('▶')
        self.beginningButton = QtWidgets.QPushButton('|◀')
        for button, offset, beginning, name in (
                (self.backTenButton, -10000, False, 'Back ten seconds'),
                (self.forwardTenButton, 10000, False, 'Forward ten seconds')):
            button.setStyleSheet(upButton.styleSheet())
            button.setFocusPolicy(QtCore.Qt.NoFocus)
            button.setAccessibleName(name)
            button.setToolTip(name)
            button.clicked.connect(lambda _checked=False, delta=offset, start=beginning:
                                   self.seekCurrentFilm(delta, start))

        self.beginningButton.setStyleSheet(upButton.styleSheet())
        self.beginningButton.setFocusPolicy(QtCore.Qt.NoFocus)
        self.beginningButton.setAccessibleName('Previous film, then beginning')
        self.beginningButton.setToolTip('Resume previous film; press again for its beginning')
        self.beginningButton.clicked.connect(lambda: self.skipProgram(-1))

        self.nextBeginningButton = QtWidgets.QPushButton('▶|')
        self.nextBeginningButton.setStyleSheet(upButton.styleSheet())
        self.nextBeginningButton.setFocusPolicy(QtCore.Qt.NoFocus)
        self.nextBeginningButton.setAccessibleName('Next film or restore resume position')
        self.nextBeginningButton.setToolTip('Restore saved position, or open the next film from its beginning')
        self.nextBeginningButton.clicked.connect(lambda: self.skipProgram(1, startUnvisited=True))
        filmControls = QtWidgets.QGridLayout()
        filmControls.addWidget(self.backTenButton, 0, 0)
        filmControls.addWidget(self.forwardTenButton, 0, 1)
        filmControls.addWidget(self.beginningButton, 1, 0)
        filmControls.addWidget(self.nextBeginningButton, 1, 1)
        sideLayout.addLayout(filmControls)

        guideButton = QtWidgets.QPushButton("GUIDE")
        guideButton.clicked.connect(self.toggleGuide)
        self.muteButton = QtWidgets.QPushButton("Mute")
        self.muteButton.clicked.connect(self.toggleMute)
        self.fullScreenButton = QtWidgets.QPushButton("FULL")
        self.fullScreenButton.clicked.connect(self.toggleFullScreen)
        for b in (guideButton, self.muteButton, self.fullScreenButton):
            b.setStyleSheet("background: #333; color: white; font-size: 14px; border-radius: 6px; padding: 8px;")
            b.setFocusPolicy(QtCore.Qt.NoFocus)
        sideLayout.addWidget(guideButton)

        self.volumeLabel = QtWidgets.QLabel(f"VOLUME {self.masterVolume}%")
        self.volumeLabel.setAlignment(QtCore.Qt.AlignCenter)
        self.volumeLabel.setStyleSheet("color: #ccc; font-size: 11px;")
        sideLayout.addWidget(self.volumeLabel)
        volumeButtons = QtWidgets.QVBoxLayout()
        self.volumeDownButton = QtWidgets.QPushButton("VOL ▼")
        self.volumeUpButton = QtWidgets.QPushButton("VOL ▲")
        self.volumeDownButton.setAccessibleName("Volume down")
        self.volumeUpButton.setAccessibleName("Volume up")
        for button, step in ((self.volumeUpButton, 5), (self.volumeDownButton, -5)):
            button.setStyleSheet(
                "QPushButton { background: #444; color: white; font-weight: bold; font-size: 14px;"
                "border-radius: 6px; padding: 10px; }"
                "QPushButton:disabled { color: #777; background: #292929; }"
            )
            button.setFocusPolicy(QtCore.Qt.NoFocus)
            button.setAutoRepeat(True)
            button.clicked.connect(lambda _checked=False, delta=step: self.setVolume(self.masterVolume + delta))
            volumeButtons.addWidget(button)
        sideLayout.addLayout(volumeButtons)
        sideLayout.addWidget(self.muteButton)
        sideLayout.addWidget(self.fullScreenButton)

        self.fontSizeLabel = QtWidgets.QLabel("FONT SIZE")
        self.fontSizeLabel.setAlignment(QtCore.Qt.AlignCenter)
        self.fontSizeLabel.setStyleSheet("color: #ccc; font-size: 11px;")
        sideLayout.addWidget(self.fontSizeLabel)
        self.fontUpButton = QtWidgets.QPushButton("FONT ▲")
        self.fontDownButton = QtWidgets.QPushButton("FONT ▼")
        self.fontUpButton.setAccessibleName("Increase TV font size")
        self.fontDownButton.setAccessibleName("Decrease TV font size")
        for button, step in ((self.fontUpButton, 0.25), (self.fontDownButton, -0.25)):
            button.setStyleSheet(self.volumeUpButton.styleSheet())
            button.setFocusPolicy(QtCore.Qt.NoFocus)
            button.setAutoRepeat(True)
            button.clicked.connect(lambda _checked=False, delta=step: self.setFontScale(self.fontScale + delta))
            sideLayout.addWidget(button)
        sideLayout.addStretch(1)

        # Large text must remain usable in shorter windows.
        self.sideScroll = QtWidgets.QScrollArea()
        self.sideScroll.setWidgetResizable(True)
        self.sideScroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.sideScroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.sideScroll.setWidget(self.sideControls)
        rootLayout.addWidget(self.sideScroll)

    def setFontScale(self, scale):
        """Scale from the original fonts so repeated adjustments never compound."""
        self.fontScale = max(0.5, min(4.0, scale))
        font = QtGui.QFont(self._baseFont)
        if font.pixelSize() > 0:
            font.setPixelSize(round(font.pixelSize() * self.fontScale))
        else:
            font.setPointSizeF(font.pointSizeF() * self.fontScale)
        self.setFont(font)
        self.setStyleSheet(
            f'QWidget {{ font-family: "{font.family()}"; font-size: {font.pixelSize()}px; }}'
        )
        for widget, style in self._fontStyles:
            widget.setStyleSheet(re.sub(
                r'font-size:\s*(\d+)px;',
                lambda match: f'font-size: {round(int(match[1]) * self.fontScale)}px; '
                              f'font-family: "{font.family()}";',
                style,
            ))
        self.fontSizeLabel.setText(f"FONT SIZE {round(self.fontScale * 100)}%")
        self.fontUpButton.setEnabled(self.fontScale < 4.0)
        self.fontDownButton.setEnabled(self.fontScale > 0.5)
        self.sideScroll.setFixedWidth(max(130, self.sideControls.sizeHint().width() + 24))
        self.guideTable.setColumnWidth(0, round(50 * self.fontScale))
        self.guideTable.setColumnWidth(1, round(160 * self.fontScale))
        self._sizeGuideColumns()
        self.guideTable.resizeRowsToContents()
        self.overlayArea._layoutOverlay(self.banner)

    def _onGuideColumnResized(self, column, oldWidth, newWidth):
        if column in (2, 3) and not self._sizingGuideColumns:
            self._manualGuideColumns.add(column)

    def _sizeGuideColumns(self):
        self._sizingGuideColumns = True
        try:
            for column in (2, 3):
                if column not in self._manualGuideColumns:
                    self.guideTable.resizeColumnToContents(column)
        finally:
            self._sizingGuideColumns = False

    def _buildGuideOverlay(self):
        guide = QtWidgets.QFrame()
        guide.setStyleSheet("background: #050531; border: 3px solid #1e1e8c;")
        layout = QtWidgets.QVBoxLayout(guide)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        topWidget = _GuideTopBar()
        topLayout = QtWidgets.QHBoxLayout(topWidget)
        topLayout.setContentsMargins(0, 0, 0, 0)

        previewFrame = QtWidgets.QFrame()
        previewFrame.setFixedSize(240, 160)
        topWidget.previewFrame = previewFrame
        previewFrame.setStyleSheet("background: black; border: 2px solid #4444aa;")
        previewLayout = QtWidgets.QVBoxLayout(previewFrame)
        previewLayout.setContentsMargins(0, 0, 0, 0)
        self.guidePreviewContainer = previewFrame
        topLayout.addWidget(previewFrame)

        captionLayout = QtWidgets.QVBoxLayout()
        topLayout.addLayout(captionLayout, 1)

        asLabel = QtWidgets.QLabel("NOW SHOWING")
        asLabel.setStyleSheet("color: #ffcc00; font-size: 14px; font-weight: bold;")
        captionLayout.addWidget(asLabel)

        self.guideCaption = QtWidgets.QLabel("")
        self.guideCaption.setWordWrap(True)
        self.guideCaption.setStyleSheet("color: white; font-size: 22px; font-weight: bold;")
        captionLayout.addWidget(self.guideCaption)

        self.guideDescription = QtWidgets.QTextEdit()
        self.guideDescription.setReadOnly(True)
        self.guideDescription.setFocusPolicy(QtCore.Qt.NoFocus)
        self.guideDescription.setStyleSheet(
            "QTextEdit { background: transparent; color: #ccccff; font-size: 14px; border: none; }"
        )
        captionLayout.addWidget(self.guideDescription, 1)

        self.guideTable = QtWidgets.QTableWidget(0, 4)
        self.guideTable.setHorizontalHeaderLabels(["CH", "CHANNEL", "NOW", "NEXT"])
        self.guideTable.setWordWrap(False)
        self.guideTable.setTextElideMode(QtCore.Qt.ElideNone)
        self.guideTable.setHorizontalScrollMode(QtWidgets.QAbstractItemView.ScrollPerPixel)
        header = self.guideTable.horizontalHeader()
        header.setStretchLastSection(False)
        header.setResizeContentsPrecision(-1)
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.Interactive)
        header.setSectionResizeMode(3, QtWidgets.QHeaderView.Interactive)
        self._manualGuideColumns = set()
        self._sizingGuideColumns = False
        header.sectionResized.connect(self._onGuideColumnResized)
        self.guideTable.verticalHeader().hide()
        self.guideTable.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.guideTable.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        self.guideTable.setFocusPolicy(QtCore.Qt.NoFocus)
        self.guideTable.setStyleSheet(
            "QTableWidget { background: #0a0a6e; color: white; gridline-color: #3333aa; font-size: 14px; }"
            "QHeaderView::section { background: #1a1aae; color: white; font-size: 14px; padding: 4px; border: 1px solid #3333aa; }"
        )
        self.guideTable.setColumnWidth(0, 50)
        self.guideTable.setColumnWidth(1, 160)
        self.guideTable.viewport().installEventFilter(self)

        self.scheduleTable = QtWidgets.QTableWidget(0, 3)
        self.scheduleTable.setHorizontalHeaderLabels(['#', 'START (EST.)', 'MOVIE'])
        self.scheduleTable.setWordWrap(False)
        self.scheduleTable.setTextElideMode(QtCore.Qt.ElideNone)
        self.scheduleTable.setHorizontalScrollMode(QtWidgets.QAbstractItemView.ScrollPerPixel)
        self.scheduleTable.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.scheduleTable.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        self.scheduleTable.setFocusPolicy(QtCore.Qt.NoFocus)
        self.scheduleTable.verticalHeader().hide()
        self.scheduleTable.setStyleSheet(self.guideTable.styleSheet())
        self.scheduleTable.horizontalHeader().setStretchLastSection(False)
        self.scheduleTable.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Interactive)
        self.guidePages = QtWidgets.QTabWidget()
        self.guidePages.addTab(self.guideTable, 'CHANNELS')
        self.guidePages.addTab(self.scheduleTable, 'SCHEDULE')
        self.guidePages.currentChanged.connect(
            lambda _index: QtCore.QTimer.singleShot(0, self._scrollGuideToHighlight))

        splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(10)
        splitter.setStyleSheet("QSplitter::handle { background: #4444aa; border: none; margin: 3px 0; }")
        topWidget.setMinimumHeight(80)
        self.guidePages.setMinimumHeight(80)
        splitter.addWidget(topWidget)
        splitter.addWidget(self.guidePages)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([600, 300])
        layout.addWidget(splitter, 1)

        hint = QtWidgets.QLabel("\u25B2/\u25BC Browse channels     Enter Tune     G/Esc Close Guide")
        hint.setAlignment(QtCore.Qt.AlignCenter)
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #8888cc; font-size: 11px;")
        layout.addWidget(hint)

        return guide

    # ------------------------------------------------------------------
    # Channel / data building
    # ------------------------------------------------------------------
    def refreshChannels(self):
        """(Re)build the channel list (one per genre) from the movies table model."""
        model = getattr(self.mainWindow, 'moviesTableModel', None)
        if model is None:
            return

        genreRows = {}
        for row in range(model.rowCount()):
            try:
                genres = model.getGenres(row)
            except Exception:
                genres = []
            for genre in genres:
                genreRows.setdefault(genre, []).append(row)

        newChannels = [
            {'genre': genre, 'rows': rows, 'clock': ChannelClock(rows, self._durationForRow)}
            for genre, rows in sorted(genreRows.items())
            if len(rows) >= self.MIN_MOVIES_PER_CHANNEL
        ]

        self._teardownAllEngines()
        self._videoPathCache = {}
        self._descriptionCache = {}
        self.channels = newChannels
        if self.channels:
            self.currentIndex = min(self.currentIndex, len(self.channels) - 1)
        else:
            self.currentIndex = 0

        self._updateEmptyState()

        if self.isActive and self.channels:
            self._tuneTo(self.currentIndex)
            self._openStartupGuide()

    def _durationForRow(self, row):
        model = getattr(self.mainWindow, 'moviesTableModel', None)
        try:
            minutes = float(str(model.getRuntime(row)).split()[0])
            return int(minutes * 60000) if minutes > 0 else 0
        except (AttributeError, IndexError, TypeError, ValueError):
            return 0

    def _resolveVideoPath(self, row):
        if row in self._videoPathCache:
            return self._videoPathCache[row]
        path = None
        if self.mainWindow and hasattr(self.mainWindow, 'resolveMovieVideoFile'):
            try:
                path = self.mainWindow.resolveMovieVideoFile(row)
            except Exception:
                path = None
        self._videoPathCache[row] = path
        return path

    def _titleForRow(self, row):
        model = getattr(self.mainWindow, 'moviesTableModel', None)
        if model is None or row is None:
            return ''
        try:
            title = model.getTitle(row)
            year = model.getYear(row)
            return f"{title} ({year})" if year else title
        except Exception:
            return ''

    def _descriptionForRow(self, row):
        """Plot text for a movie row (cached - the data lives in a per-movie JSON file)."""
        if row in self._descriptionCache:
            return self._descriptionCache[row]
        text = ''
        model = getattr(self.mainWindow, 'moviesTableModel', None)
        try:
            data = model.getMovieData(row) if model is not None else None
        except Exception:
            data = None
        if data:
            plot = data.get('plot') or data.get('synopsis') or data.get('summary') or ''
            if isinstance(plot, list):
                plot = ' '.join(str(p) for p in plot if p)
            text = str(plot).strip()
        self._descriptionCache[row] = text
        return text

    def _updateEmptyState(self):
        hasChannels = bool(self.channels)
        self.sideControls.setEnabled(hasChannels)
        if not hasChannels:
            self.nowPlayingLabel.setText("")
            self.displayStack.setCurrentWidget(self.globalStandby)

    def _syncStandbyTone(self):
        """Continuous fallback: match the tone to whatever stand-by state is actually on
        screen right now for the tuned-in channel, instead of reacting to one-shot events."""
        if not self.isActive:
            self.standbyTone.stop()
            return
        engine = self.engines.get(self.currentIndex) if self.channels else None
        isStandby = engine.isShowingStandby() if engine is not None else True
        if isStandby:
            self.standbyTone.start()
        else:
            self.standbyTone.stop()

    # ------------------------------------------------------------------
    # Channel engine (tuning) management
    # ------------------------------------------------------------------
    def _createEngine(self, index):
        chan = self.channels[index]
        engine = ChannelEngine(
            index + 1,
            chan['genre'],
            chan['clock'],
            resolver=self._resolveVideoPath,
            titleGetter=self._titleForRow,
            parent=self,
        )
        engine.programChanged.connect(lambda idx=index: self._onProgramChanged(idx))
        engine._stack.currentChanged.connect(lambda _index: self._syncStandbyTone())
        engine._stack.currentChanged.connect(
            lambda _index: self._refreshGuideTable() if self.guideVisible else None)
        return engine

    def _teardownAllEngines(self):
        self._releasePreviewHost()
        for engine in list(self.engines.values()):
            engine.shutdown()
            self.displayStack.removeWidget(engine.container)
            engine.container.setParent(None)
        self.engines = {}
        self.displayStack.setCurrentWidget(self.globalStandby)

    def _tuneTo(self, index):
        if not self.channels:
            return
        index = index % len(self.channels)
        self._releasePreviewHost()

        needed = {index}
        if len(self.channels) > 1:
            for offset in range(1, self.NEIGHBOR_WARM_COUNT + 1):
                needed.add((index - offset) % len(self.channels))
                needed.add((index + offset) % len(self.channels))

        # Drop engines we no longer need to keep memory/CPU bounded.
        for idx in list(self.engines.keys()):
            if idx not in needed:
                engine = self.engines.pop(idx)
                engine.shutdown()
                self.displayStack.removeWidget(engine.container)
                engine.container.setParent(None)

        # Wire up the current channel's engine and get it tuning/buffering immediately.
        if index not in self.engines:
            engine = self._createEngine(index)
            self.engines[index] = engine
            self.displayStack.addWidget(engine.container)
        self.engines[index].setDesiredVolume(self.masterVolume)
        self.engines[index].start()

        # Create/start everything else we need warmed (muted neighbors).
        for idx in needed:
            if idx == index:
                continue
            if idx not in self.engines:
                engine = self._createEngine(idx)
                self.engines[idx] = engine
                self.displayStack.addWidget(engine.container)
            self.engines[idx].setDesiredVolume(0)
            self.engines[idx].start()

        self.currentIndex = index
        self.guideHighlightIndex = index
        engine = self.engines.get(index)
        if engine:
            self.displayStack.setCurrentWidget(engine.container)
            self._showBanner(engine)
        self._updateChannelLabel()
        self._updateNowPlayingLabel(engine)
        if self.guideVisible:
            self._refreshGuideTable()
            self._updateGuidePreview()
        self._syncStandbyTone()

    def _updateChannelLabel(self):
        if not self.channels:
            self.channelLcd.setText("--")
            self.genreLabel.setText("")
            return
        chan = self.channels[self.currentIndex]
        self.channelLcd.setText(f"{self.currentIndex + 1:02d}")
        self.genreLabel.setText(chan['genre'].upper())

    def _showBanner(self, engine):
        if self.isFullScreenActive:
            return
        text = f"CH {engine.channelNumber:02d}  {engine.genreName.upper()}\n{engine.currentTitle}"
        self.banner.setText(text)
        self.banner.show()
        self.banner.raise_()
        self.overlayArea._layoutOverlay(self.banner)
        self.bannerTimer.start(3500)

    def _updateNowPlayingLabel(self, engine):
        self.nowPlayingLabel.setText(engine.currentTitle if engine and engine.currentTitle else "")

    def _onProgramChanged(self, idx):
        engine = self.engines.get(idx)
        if engine is None:
            return
        if idx == self.currentIndex:
            self._showBanner(engine)
            self._updateNowPlayingLabel(engine)
        if self.guideVisible:
            self._refreshGuideTable()

    # ------------------------------------------------------------------
    # Clicker (channel up/down) + guide
    # ------------------------------------------------------------------
    def channelUp(self):
        if not self.channels:
            return
        self._tuneTo(self.currentIndex + 1)

    def channelDown(self):
        if not self.channels:
            return
        self._tuneTo(self.currentIndex - 1)

    def skipProgram(self, step, beginning=False, startUnvisited=False):
        engine = self.engines.get(self.currentIndex)
        if engine is None:
            return
        engine.skipProgram(step, beginning, startUnvisited)
        self._updateNowPlayingLabel(engine)
        if self.guideVisible:
            self._refreshGuideTable()
        self._syncStandbyTone()

    def seekCurrentFilm(self, offsetMs=0, beginning=False):
        engine = self.engines.get(self.currentIndex)
        if engine and engine.seekCurrentFilm(offsetMs, beginning) and self.guideVisible:
            self._refreshGuideTable()

    def toggleMute(self):
        self.setVolume(0 if self.masterVolume else self._lastVolume)

    def setVolume(self, volume):
        self.masterVolume = max(0, min(100, int(volume)))
        if self.masterVolume:
            self._lastVolume = self.masterVolume
        self.volumeUpButton.setEnabled(self.masterVolume < 100)
        self.volumeDownButton.setEnabled(self.masterVolume > 0)
        self.volumeLabel.setText(f"VOLUME {self.masterVolume}%")
        self.muteButton.setText("Unmute" if self.masterVolume == 0 else "Mute")
        self.standbyTone.setVolume(self.masterVolume)
        engine = self.engines.get(self.currentIndex)
        if engine:
            engine.setDesiredVolume(self.masterVolume)

    def _openStartupGuide(self):
        if self._showGuideOnStart and self.channels:
            self._showGuideOnStart = False
            self.guidePages.setCurrentIndex(0)
            if not self.guideVisible:
                self.toggleGuide()

    def toggleGuide(self):
        if not self.channels:
            return
        self.guideVisible = not self.guideVisible
        self.guideOverlay.setVisible(self.guideVisible)
        if self.guideVisible:
            self.guideHighlightIndex = self.currentIndex
            self._refreshGuideTable()
            self._startGuidePreview()
        else:
            self._stopGuidePreview()
        self.setFocus()

    def toggleFullScreen(self):
        if self.isFullScreenActive:
            self._exitFullScreen()
        else:
            self._enterFullScreen()

    def _enterFullScreen(self):
        host = self.window()
        self._fsWindow = host
        self._fsWindowState = host.windowState()
        self._fsGuideVisible = self.guideVisible
        self._fsMargins = self.layout().contentsMargins()
        self._fsSpacing = self.layout().spacing()
        self._fsLeftSpacing = self.leftColumn.spacing()
        self._fsChrome = [(widget, not widget.isHidden())
                          for widget in (self.sideScroll, self.nowPlayingLabel)]
        if isinstance(host, QtWidgets.QMainWindow):
            self._fsChrome += [(widget, not widget.isHidden())
                               for widget in (host.menuBar(), host.statusBar())]
        self._fullScreenTransition = True
        try:
            self.isFullScreenActive = True
            if self.guideVisible:
                self.toggleGuide()
            self.banner.hide()
            for widget, _visible in self._fsChrome:
                widget.hide()
            self.layout().setContentsMargins(0, 0, 0, 0)
            self.layout().setSpacing(0)
            self.leftColumn.setSpacing(0)
            self.fullScreenButton.setText("EXIT FULL")
            host.showFullScreen()
        finally:
            self._fullScreenTransition = False
        self.setFocus()

    def _exitFullScreen(self):
        if self._fsWindow is None:
            return
        host = self._fsWindow
        self._fsWindow = None
        self._fullScreenTransition = True
        try:
            self.isFullScreenActive = False
            self.layout().setContentsMargins(self._fsMargins)
            self.layout().setSpacing(self._fsSpacing)
            self.leftColumn.setSpacing(self._fsLeftSpacing)
            for widget, visible in self._fsChrome:
                widget.setVisible(visible)
            self.fullScreenButton.setText("FULL")
            host.setWindowState(self._fsWindowState)
            host.show()
            if self.guideVisible != self._fsGuideVisible:
                self.toggleGuide()
        finally:
            self._fullScreenTransition = False
        self.setFocus()

    def _startGuidePreview(self):
        self._updateGuidePreview()
        # Note: periodic random-reseek ("cutting") is disabled for now - see _onGuidePreviewTick -
        # so self.guidePreviewTimer is intentionally not started here.

    def _stopGuidePreview(self):
        self.guidePreviewTimer.stop()
        self._releasePreviewHost()
        if self.guidePreviewSlot:
            self.guidePreviewSlot.stop()

    def _setPreviewContent(self, widget):
        """Show exactly `widget` in the guide's small preview frame, parking anything else."""
        layout = self.guidePreviewContainer.layout()
        for i in reversed(range(layout.count())):
            item = layout.takeAt(i)
            other = item.widget()
            if other is not None and other is not widget:
                other.setParent(None)
        if layout.indexOf(widget) == -1:
            layout.addWidget(widget)
        widget.show()

    def _releasePreviewHost(self):
        """Return a live engine's video widget (parked in the guide preview) to the main display."""
        engine = self._guidePreviewHostedEngine
        self._guidePreviewHostedEngine = None
        if engine is None:
            return
        self.guidePreviewContainer.layout().removeWidget(engine.container)
        if self.displayStack.indexOf(engine.container) == -1:
            self.displayStack.addWidget(engine.container)
        if engine is self.engines.get(self.currentIndex):
            self.displayStack.setCurrentWidget(engine.container)
        engine.container.show()

    def _updateGuidePreview(self):
        if not self.channels:
            return
        idx = self.guideHighlightIndex
        engine = self.engines.get(idx)

        if engine is not None:
            # Same rendering target as the main view - just reparented into the small frame
            # and scaled down, so there's no reload/seek/interruption of any kind.
            if self.guidePreviewSlot:
                self.guidePreviewSlot.stop()
            if self._guidePreviewHostedEngine is not None and self._guidePreviewHostedEngine is not engine:
                self._releasePreviewHost()
            if self.displayStack.indexOf(engine.container) != -1:
                self.displayStack.removeWidget(engine.container)
            self._setPreviewContent(engine.container)
            self._guidePreviewHostedEngine = engine
            return

        # No live engine for this channel (outside the warmed neighbor range) - fall back to a
        # throwaway preview clip.
        if self._guidePreviewHostedEngine is not None:
            self._releasePreviewHost()
        if self.guidePreviewSlot is None:
            self.guidePreviewSlot = ClipSlot(self)
            self.guidePreviewSlot.setVolume(0)
        self._setPreviewContent(self.guidePreviewSlot.videoWidget)
        row = random.choice(self.channels[idx]['rows'])
        path = self._resolveVideoPath(row)
        if path:
            self.guidePreviewSlot.load(path, autoplay=True)

    def _onGuidePreviewTick(self):
        # Kept for future use (periodic random-reseek "cutting" effect); not currently invoked.
        if self.guidePreviewSlot and self.guidePreviewSlot.isReady():
            self.guidePreviewSlot.seekRandom()


    def _refreshGuideTable(self):
        table = self.guideTable
        table.setRowCount(len(self.channels))
        for i, chan in enumerate(self.channels):
            engine = self.engines.get(i)
            if engine and engine.currentRow is not None:
                nowText = engine.currentTitle
                nextRow, _ = chan['clock'].slotInfo(engine.currentSlotIndex + 1)
                nextText = engine.nextTitle or self._titleForRow(nextRow)
            else:
                # No live engine warmed for this channel - preview "now"/"next" straight from
                # its schedule clock, the same source tuning in will actually use, so the guide
                # never promises content that switching to the channel won't deliver.
                slotIndex, row, _, _, _ = chan['clock'].whatsOnNow()
                nextRow, _ = chan['clock'].slotInfo(slotIndex + 1)
                nowText = self._titleForRow(row)
                nextText = self._titleForRow(nextRow)

            values = [f"{i + 1:02d}", chan['genre'].upper(), nowText, nextText]
            highlighted = (i == self.guideHighlightIndex)
            playing = (i == self.currentIndex and engine is not None
                       and engine.currentRow is not None and not engine.isShowingStandby())
            for col, value in enumerate(values):
                item = QtWidgets.QTableWidgetItem(value)
                item.setFlags(QtCore.Qt.ItemIsEnabled)
                if playing and col == 2:
                    item.setBackground(QtGui.QColor('#00ff00'))
                    item.setForeground(QtGui.QColor('black'))
                elif highlighted:
                    item.setBackground(QtGui.QColor('#ffcc00'))
                    item.setForeground(QtGui.QColor('black'))
                else:
                    item.setBackground(QtGui.QColor('#0a0a6e'))
                    item.setForeground(QtGui.QColor('white'))
                table.setItem(len(self.channels) - 1 - i, col, item)

        self._sizeGuideColumns()
        table.resizeRowsToContents()
        self._scrollGuideToHighlight()
        QtCore.QTimer.singleShot(0, self._scrollGuideToHighlight)

        chan = self.channels[self.guideHighlightIndex]
        self.guideCaption.setText(f"CH {self.guideHighlightIndex + 1:02d} \u2014 {chan['genre'].upper()}")

        self._refreshScheduleTable(chan)

        engine = self.engines.get(self.guideHighlightIndex)
        if engine and engine.currentRow is not None:
            nowRow = engine.currentRow
        else:
            nowRow = chan['clock'].whatsOnNow()[1]
        description = self._descriptionForRow(nowRow) or "No description available."
        self.guideDescription.setHtml(
            f"<p style='color:#ffcc00;font-weight:bold;'>{html.escape(self._titleForRow(nowRow))}</p>"
            f"<p>{html.escape(description)}</p>"
        )

    def _scrollGuideToHighlight(self):
        if not self.guideVisible or not self.guideTable.isVisible():
            return
        item = self.guideTable.item(len(self.channels) - 1 - self.guideHighlightIndex, 0)
        if item is not None:
            horizontal = self.guideTable.horizontalScrollBar().value()
            self.guideTable.scrollToItem(item, QtWidgets.QAbstractItemView.PositionAtCenter)
            self.guideTable.horizontalScrollBar().setValue(horizontal)

    def eventFilter(self, watched, event):
        if (watched is self.guideTable.viewport()
                and event.type() in (QtCore.QEvent.Show, QtCore.QEvent.Resize)):
            QtCore.QTimer.singleShot(0, self._scrollGuideToHighlight)
        return super().eventFilter(watched, event)

    def _refreshScheduleTable(self, channel):
        clock = channel['clock']
        engine = self.engines.get(self.guideHighlightIndex)
        current = (engine.currentSlotIndex if engine and engine.currentRow is not None
                   else clock.whatsOnNow()[0])
        count = len(clock._rotation)
        self.scheduleTable.setRowCount(count)
        epochWall = time.time() - (time.monotonic() - clock.epoch)
        startMs = clock.slotStartMs(current)
        for index in range(count):
            slot = current + index
            row, _ = clock.slotInfo(slot)
            start = 'NOW' if index == 0 else time.strftime('%a %H:%M', time.localtime(epochWall + startMs / 1000))
            title = engine.currentTitle if index == 0 and engine and engine.currentRow is not None else self._titleForRow(row)
            for column, value in enumerate((str(index + 1), start, title)):
                item = QtWidgets.QTableWidgetItem(value)
                item.setFlags(QtCore.Qt.ItemIsEnabled)
                if index == 0:
                    playing = (self.guideHighlightIndex == self.currentIndex and engine is not None
                               and engine.currentRow is not None and not engine.isShowingStandby())
                    item.setBackground(QtGui.QColor('#00ff00' if playing else '#ffcc00'))
                    item.setForeground(QtGui.QColor('black'))
                self.scheduleTable.setItem(index, column, item)
            startMs += clock.durationForSlot(slot)
        self.scheduleTable.resizeColumnsToContents()
        self.scheduleTable.resizeRowsToContents()

    # ------------------------------------------------------------------
    # Qt event overrides
    # ------------------------------------------------------------------
    def showEvent(self, event):
        super().showEvent(event)
        if self._fullScreenTransition:
            return
        self.isActive = True
        self._showGuideOnStart = True
        # Start before engine creation or any catalogue/tuning work can block Qt.
        self.standbyTone.start()
        self.standbyPollTimer.start()
        if self.channels:
            self._tuneTo(self.currentIndex)
            self._openStartupGuide()
        else:
            self._syncStandbyTone()
        self.setFocus()

    def hideEvent(self, event):
        super().hideEvent(event)
        if self._fullScreenTransition:
            return
        self.isActive = False
        self.standbyPollTimer.stop()
        self.standbyTone.stop()
        self._teardownAllEngines()
        self._stopGuidePreview()
        if self.guideVisible:
            self.guideVisible = False
            self.guideOverlay.hide()

    def keyPressEvent(self, event):
        key = event.key()
        if key in (QtCore.Qt.Key_Up, QtCore.Qt.Key_PageUp):
            self.channelUp()
        elif key in (QtCore.Qt.Key_Down, QtCore.Qt.Key_PageDown):
            self.channelDown()
        elif key == QtCore.Qt.Key_G:
            self.toggleGuide()
        elif key == QtCore.Qt.Key_M:
            self.toggleMute()
        elif key in (QtCore.Qt.Key_F, QtCore.Qt.Key_F11):
            self.toggleFullScreen()
        elif key in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
            if self.guideVisible:
                self._tuneTo(self.guideHighlightIndex)
                self.toggleGuide()
        elif key == QtCore.Qt.Key_Escape and self.guideVisible:
            self.toggleGuide()
        elif key == QtCore.Qt.Key_Escape and self.isFullScreenActive:
            self.toggleFullScreen()
        else:
            super().keyPressEvent(event)
