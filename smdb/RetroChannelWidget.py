"""
RetroChannelWidget - a prototype "live TV" experience built from the movie collection.

Each "channel" corresponds to a genre. Channels air a continuous rotation of
movies from that genre, each airing for a fixed-length slot starting at a
random point inside the movie (trailer/sizzle-reel style), then cutting to
the next movie in the rotation. Each channel's schedule is anchored to an
absolute wall-clock epoch, so tuning away and back always resumes wherever
the broadcast "would be" had it kept playing the whole time - just like a
real TV channel keeps running whether or not you're watching. Switching
channels (up/down "clicker") and browsing the channel guide both feel
instant because the current channel plus its two neighbors are always
pre-buffered in memory, ready to display immediately. Only the channel
guide's small preview window continues to hop between random clips on the
fly while you're browsing.
"""

import math
import os
import random
import struct
import tempfile
import time
import wave

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtMultimedia import QMediaContent, QMediaPlayer, QSoundEffect
from PyQt5.QtMultimediaWidgets import QVideoWidget

PROGRAM_DURATION_MS = 60000  # how long each movie airs before the channel cuts to the next one
PREFETCH_LEAD_MS = 8000  # start buffering the next movie this far before the slot ends
MAX_START_FRACTION = 0.85  # never start a slot in the last 15% of a movie
MIN_SEEK_RUNWAY_MS = 1500  # never seek closer than this to the end of a movie


def _ensureStandbyToneFile():
    """Generate (once) a short looping sine-wave test tone, returning its WAV path."""
    path = os.path.join(tempfile.gettempdir(), 'smdb_standby_tone.wav')
    if os.path.exists(path):
        return path
    sampleRate = 44100
    freqHz = 1000.0
    durationS = 1.0
    amplitude = 0.25
    fadeSamples = 200
    sampleCount = int(sampleRate * durationS)
    frames = bytearray()
    for i in range(sampleCount):
        fade = min(1.0, i / fadeSamples, (sampleCount - i) / fadeSamples)
        value = amplitude * fade * math.sin(2 * math.pi * freqHz * i / sampleRate)
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
        self._effect.setSource(QtCore.QUrl.fromLocalFile(_ensureStandbyToneFile()))
        self._effect.setLoopCount(QSoundEffect.Infinite)
        self._muted = False
        self._volume = 0.15
        self._effect.setVolume(self._volume)

    def start(self):
        if not self._muted and not self._effect.isPlaying():
            self._effect.play()

    def stop(self):
        if self._effect.isPlaying():
            self._effect.stop()

    def setMuted(self, muted):
        self._muted = muted
        if muted:
            self._effect.stop()


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

        font = QtGui.QFont("Arial", max(14, rect.width() // 24), QtGui.QFont.Black)
        painter.setFont(font)
        textRect = rect.adjusted(10, 0, -10, 0)
        painter.setPen(QtGui.QColor('black'))
        painter.drawText(textRect.translated(2, 2), QtCore.Qt.AlignCenter, "PLEASE STAND BY")
        painter.setPen(QtGui.QColor('white'))
        painter.drawText(textRect, QtCore.Qt.AlignCenter, "PLEASE STAND BY")


class ClipSlot(QtCore.QObject):
    """A single QMediaPlayer/QVideoWidget pair used as a playback buffer."""

    becameReady = QtCore.pyqtSignal()

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

        self.player.durationChanged.connect(self._onDurationChanged)

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
    time. Movies air back-to-back in fixed-length slots, each starting at a
    random point inside the movie. Because the schedule is a pure function of
    an absolute start time (epoch), re-syncing to it (e.g. after tuning away
    and back) always resumes exactly where the broadcast "would be" had it
    kept playing the whole time - including skipping ahead across multiple
    movies if you were away longer than one slot.
    """

    def __init__(self, rows):
        self.rows = list(rows)
        self.epoch = time.monotonic()
        self._rotation = []
        self._offsetFractions = {}
        self._extendRotation()

    def _extendRotation(self):
        pool = list(self.rows)
        random.shuffle(pool)
        if self._rotation and pool and pool[0] == self._rotation[-1]:
            pool.append(pool.pop(0))
        self._rotation.extend(pool)

    def _rowForSlot(self, slotIndex):
        while slotIndex >= len(self._rotation):
            self._extendRotation()
        return self._rotation[slotIndex]

    def _offsetFractionForSlot(self, slotIndex):
        fraction = self._offsetFractions.get(slotIndex)
        if fraction is None:
            fraction = random.uniform(0.0, MAX_START_FRACTION)
            self._offsetFractions[slotIndex] = fraction
        return fraction

    def candidateRows(self, slotIndex, count=5):
        """Rows for `slotIndex` and the following slots, used as fallbacks
        when a scheduled movie has no resolvable video file."""
        return [self._rowForSlot(slotIndex + i) for i in range(count)]

    def whatsOnNow(self):
        """Return (slotIndex, row, offsetFraction, positionInSlotMs, remainingMs)."""
        elapsedMs = (time.monotonic() - self.epoch) * 1000.0
        slotIndex = int(elapsedMs // PROGRAM_DURATION_MS)
        positionInSlotMs = elapsedMs - slotIndex * PROGRAM_DURATION_MS
        row = self._rowForSlot(slotIndex)
        offsetFraction = self._offsetFractionForSlot(slotIndex)
        remainingMs = PROGRAM_DURATION_MS - positionInSlotMs
        return slotIndex, row, offsetFraction, positionInSlotMs, remainingMs

    def slotInfo(self, slotIndex):
        row = self._rowForSlot(slotIndex)
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
    showingStandby = QtCore.pyqtSignal(bool)

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
        self.showingStandby.emit(True)

        def onResolved(row, path):
            if path is None:
                return  # no playable movie found for this slot; stay on stand-by
            self.currentSlotIndex = slotIndex
            self.currentRow = row
            self.currentTitle = self.titleGetter(row)
            self.nextRow = None
            self.nextTitle = ''
            self._prefetchStarted = False
            self._prefetchedSlotIndex = None

            self.activeSlot.setVolume(self.desiredVolume)
            self.activeSlot.load(path, autoplay=True, seekFraction=offsetFraction, extraMs=positionInSlotMs)
            self.programChanged.emit()

            self._scheduleAdvance(remainingMs)
            self._maybeSchedulePrefetch(remainingMs)

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
        if slot is self.activeSlot:
            self._stack.setCurrentWidget(slot.videoWidget)
            self.showingStandby.emit(False)

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
                self._prefetchedSlotIndex = nextSlotIndex
                self.standbySlot.load(path, autoplay=False, seekFraction=offsetFraction, extraMs=0)
            else:
                self.nextRow = None
                self.nextTitle = ''
                self._prefetchedSlotIndex = None

        self._startResolve(nextSlotIndex, '_prefetchRequestId', onResolved)

    def _onAdvanceTimer(self):
        """Slot boundary reached (or we're catching up after being away): re-sync to the clock."""
        slotIndex, _, offsetFraction, positionInSlotMs, remainingMs = self.clock.whatsOnNow()
        if slotIndex == self.currentSlotIndex:
            # Timer fired a hair early due to rounding; check again shortly.
            self._scheduleAdvance(remainingMs)
            return

        if self.standbySlot.isReady() and self._prefetchedSlotIndex == slotIndex:
            self._promote(slotIndex, positionInSlotMs)
        else:
            self._hardCut(slotIndex, offsetFraction, positionInSlotMs)

        self._prefetchStarted = False
        self.prefetchTimer.stop()
        self._scheduleAdvance(remainingMs)
        self._maybeSchedulePrefetch(remainingMs)

    def _promote(self, slotIndex, positionInSlotMs):
        """Swap in the already-buffered standby slot, correcting for any scheduling drift."""
        self.activeSlot.pause()
        self.activeSlot, self.standbySlot = self.standbySlot, self.activeSlot
        if positionInSlotMs > 250:
            self.activeSlot.player.setPosition(self.activeSlot.player.position() + int(positionInSlotMs))
        self._stack.setCurrentWidget(self.activeSlot.videoWidget)
        self.activeSlot.setVolume(self.desiredVolume)
        self.activeSlot.play()
        self.standbySlot.stop()

        self.currentSlotIndex = slotIndex
        self.currentRow = self.nextRow
        self.currentTitle = self.nextTitle
        self.nextRow = None
        self.nextTitle = ''
        self._prefetchedSlotIndex = None
        self.programChanged.emit()

    def _hardCut(self, slotIndex, offsetFraction, positionInSlotMs):
        """Standby wasn't buffered in time (long gap or slow load) - load directly, showing stand-by until ready."""
        self.standbySlot.stop()
        self._stack.setCurrentWidget(self.standbyScreen)
        self.showingStandby.emit(True)

        def onResolved(row, path):
            if path is None:
                return
            self.activeSlot.setVolume(self.desiredVolume)
            self.activeSlot.load(path, autoplay=True, seekFraction=offsetFraction, extraMs=positionInSlotMs)

            self.currentSlotIndex = slotIndex
            self.currentRow = row
            self.currentTitle = self.titleGetter(row)
            self.nextRow = None
            self.nextTitle = ''
            self._prefetchedSlotIndex = None
            self.programChanged.emit()

        self._startResolve(slotIndex, '_hardCutRequestId', onResolved)


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

    MIN_MOVIES_PER_CHANNEL = 3
    NEIGHBOR_WARM_COUNT = 1  # warm this many channels on either side for instant surfing

    def __init__(self, parent=None):
        super().__init__(parent)
        self.mainWindow = parent
        self._videoPathCache = {}
        self.channels = []
        self.engines = {}
        self.currentIndex = 0
        self.isActive = False
        self.guideVisible = False
        self.guideHighlightIndex = 0
        self.guidePreviewSlot = None
        self._guidePreviewHostedEngine = None
        self.masterVolume = 70
        self.isFullScreenActive = False
        self._fsTabWidget = None
        self._fsTabIndex = None
        self._fsTabLabel = None
        self.standbyTone = StandbyTone(self)
        self._standbyConnectedEngine = None

        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        self._buildUI()

        self.bannerTimer = QtCore.QTimer(self)
        self.bannerTimer.setSingleShot(True)
        self.bannerTimer.timeout.connect(self.banner.hide)

        self.guidePreviewTimer = QtCore.QTimer(self)
        self.guidePreviewTimer.setInterval(1000)
        self.guidePreviewTimer.timeout.connect(self._onGuidePreviewTick)

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
        leftColumn.setSpacing(4)
        leftColumn.addWidget(self.overlayArea, 1)

        self.nowPlayingLabel = QtWidgets.QLabel("")
        self.nowPlayingLabel.setAlignment(QtCore.Qt.AlignCenter)
        self.nowPlayingLabel.setStyleSheet(
            "color: white; background: #111; font-size: 14px; font-weight: bold;"
            "padding: 6px; border: 1px solid #444; border-radius: 4px;"
        )
        leftColumn.addWidget(self.nowPlayingLabel)

        rootLayout.addLayout(leftColumn, 1)

        self.banner = QtWidgets.QLabel()
        self.banner.setWordWrap(True)
        self.banner.setStyleSheet(
            "color: white; background: rgba(0,0,0,175); font-size: 16px; font-weight: bold;"
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
        self.sideControls.setFixedWidth(130)
        self.sideControls.setStyleSheet(
            "background: #222; border: 2px solid #555; border-radius: 10px;"
        )
        sideLayout = QtWidgets.QVBoxLayout(self.sideControls)
        sideLayout.setSpacing(8)

        self.channelLcd = QtWidgets.QLabel("--")
        self.channelLcd.setAlignment(QtCore.Qt.AlignCenter)
        self.channelLcd.setStyleSheet(
            "background: black; color: #3fff6b; font-size: 22px; font-family: Consolas;"
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

        guideButton = QtWidgets.QPushButton("GUIDE")
        guideButton.clicked.connect(self.toggleGuide)
        self.muteButton = QtWidgets.QPushButton("Mute")
        self.muteButton.clicked.connect(self.toggleMute)
        self.fullScreenButton = QtWidgets.QPushButton("FULL")
        self.fullScreenButton.clicked.connect(self.toggleFullScreen)
        for b in (guideButton, self.muteButton, self.fullScreenButton):
            b.setStyleSheet("background: #333; color: white; border-radius: 6px; padding: 8px;")
            b.setFocusPolicy(QtCore.Qt.NoFocus)
        sideLayout.addWidget(guideButton)
        sideLayout.addWidget(self.muteButton)
        sideLayout.addWidget(self.fullScreenButton)
        sideLayout.addStretch(1)

        rootLayout.addWidget(self.sideControls)

    def _buildGuideOverlay(self):
        guide = QtWidgets.QFrame()
        guide.setStyleSheet("background: #050531; border: 3px solid #1e1e8c;")
        layout = QtWidgets.QVBoxLayout(guide)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        topLayout = QtWidgets.QHBoxLayout()
        layout.addLayout(topLayout)

        previewFrame = QtWidgets.QFrame()
        previewFrame.setFixedSize(240, 160)
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
        self.guideCaption.setStyleSheet("color: white; font-size: 26px; font-weight: bold;")
        captionLayout.addWidget(self.guideCaption)
        captionLayout.addStretch(1)

        self.guideTable = QtWidgets.QTableWidget(0, 4)
        self.guideTable.setHorizontalHeaderLabels(["CH", "CHANNEL", "NOW", "NEXT"])
        self.guideTable.horizontalHeader().setStretchLastSection(True)
        self.guideTable.verticalHeader().hide()
        self.guideTable.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.guideTable.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        self.guideTable.setFocusPolicy(QtCore.Qt.NoFocus)
        self.guideTable.setStyleSheet(
            "QTableWidget { background: #0a0a6e; color: white; gridline-color: #3333aa; font-size: 13px; }"
            "QHeaderView::section { background: #1a1aae; color: white; padding: 4px; border: 1px solid #3333aa; }"
        )
        self.guideTable.setColumnWidth(0, 50)
        self.guideTable.setColumnWidth(1, 160)
        layout.addWidget(self.guideTable, 1)

        hint = QtWidgets.QLabel("\u25B2/\u25BC Browse channels     Enter Tune     G/Esc Close Guide")
        hint.setAlignment(QtCore.Qt.AlignCenter)
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
            {'genre': genre, 'rows': rows, 'clock': ChannelClock(rows)}
            for genre, rows in sorted(genreRows.items())
            if len(rows) >= self.MIN_MOVIES_PER_CHANNEL
        ]

        self._teardownAllEngines()
        self._videoPathCache = {}
        self.channels = newChannels
        if self.channels:
            self.currentIndex = min(self.currentIndex, len(self.channels) - 1)
        else:
            self.currentIndex = 0

        self._updateEmptyState()

        if self.isActive and self.channels:
            self._tuneTo(self.currentIndex)

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

    def _updateEmptyState(self):
        hasChannels = bool(self.channels)
        self.sideControls.setEnabled(hasChannels)
        if not hasChannels:
            self.nowPlayingLabel.setText("")
            self.displayStack.setCurrentWidget(self.globalStandby)
            self._setStandbyConnection(None)

    def _setStandbyConnection(self, engine):
        """Follow whichever stand-by screen is actually visible (global or a channel's own) with the tone."""
        if self._standbyConnectedEngine is not None:
            try:
                self._standbyConnectedEngine.showingStandby.disconnect(self._onStandbyChanged)
            except TypeError:
                pass
        self._standbyConnectedEngine = engine
        if engine is not None:
            engine.showingStandby.connect(self._onStandbyChanged)
            self._onStandbyChanged(engine.isShowingStandby())
        else:
            self._onStandbyChanged(True)

    def _onStandbyChanged(self, isStandby):
        if isStandby and self.isActive:
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

        # Create/start engines for everything we need warmed.
        for idx in needed:
            if idx not in self.engines:
                engine = self._createEngine(idx)
                self.engines[idx] = engine
                self.displayStack.addWidget(engine.container)
            self.engines[idx].setDesiredVolume(self.masterVolume if idx == index else 0)
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
        self._setStandbyConnection(engine)

    def _updateChannelLabel(self):
        if not self.channels:
            self.channelLcd.setText("--")
            self.genreLabel.setText("")
            return
        chan = self.channels[self.currentIndex]
        self.channelLcd.setText(f"{self.currentIndex + 1:02d}")
        self.genreLabel.setText(chan['genre'].upper())

    def _showBanner(self, engine):
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

    def toggleMute(self):
        self.masterVolume = 0 if self.masterVolume else 70
        self.muteButton.setText("Unmute" if self.masterVolume == 0 else "Mute")
        self.standbyTone.setMuted(self.masterVolume == 0)
        engine = self.engines.get(self.currentIndex)
        if engine:
            engine.setDesiredVolume(self.masterVolume)

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
        tabWidget = self.parentWidget()
        while tabWidget is not None and not isinstance(tabWidget, QtWidgets.QTabWidget):
            tabWidget = tabWidget.parentWidget()
        if tabWidget is None:
            return
        index = tabWidget.indexOf(self)
        if index == -1:
            return
        self._fsTabWidget = tabWidget
        self._fsTabIndex = index
        self._fsTabLabel = tabWidget.tabText(index)
        tabWidget.removeTab(index)
        self.setParent(None)
        self.setWindowFlags(QtCore.Qt.Window)
        self.isFullScreenActive = True
        self.fullScreenButton.setText("EXIT FULL")
        self.showFullScreen()
        self.setFocus()

    def _exitFullScreen(self):
        if self._fsTabWidget is None:
            return
        tabWidget = self._fsTabWidget
        index = self._fsTabIndex
        label = self._fsTabLabel
        self._fsTabWidget = None
        self._fsTabIndex = None
        self._fsTabLabel = None
        self.setWindowFlags(QtCore.Qt.Widget)
        tabWidget.insertTab(index, self, label)
        tabWidget.setCurrentIndex(index)
        self.isFullScreenActive = False
        self.fullScreenButton.setText("FULL")
        self.show()
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
                nextText = engine.nextTitle
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
            for col, value in enumerate(values):
                item = QtWidgets.QTableWidgetItem(value)
                item.setFlags(QtCore.Qt.ItemIsEnabled)
                if highlighted:
                    item.setBackground(QtGui.QColor('#ffcc00'))
                    item.setForeground(QtGui.QColor('black'))
                else:
                    item.setBackground(QtGui.QColor('#0a0a6e'))
                    item.setForeground(QtGui.QColor('white'))
                table.setItem(i, col, item)

        highlightedItem = table.item(self.guideHighlightIndex, 0)
        if highlightedItem:
            table.scrollToItem(highlightedItem)

        chan = self.channels[self.guideHighlightIndex]
        self.guideCaption.setText(f"CH {self.guideHighlightIndex + 1:02d} \u2014 {chan['genre'].upper()}")

    # ------------------------------------------------------------------
    # Qt event overrides
    # ------------------------------------------------------------------
    def showEvent(self, event):
        super().showEvent(event)
        self.isActive = True
        if self.channels:
            self._tuneTo(self.currentIndex)
        else:
            self._setStandbyConnection(None)
        self.setFocus()

    def hideEvent(self, event):
        super().hideEvent(event)
        self.isActive = False
        self._setStandbyConnection(None)
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
