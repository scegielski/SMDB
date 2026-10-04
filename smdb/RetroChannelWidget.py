"""
RetroChannelWidget - a prototype "live TV" experience built from the movie collection.

Each "channel" corresponds to a genre. Channels air a continuous rotation of
1-minute movie promos, where each promo is made up of cuts of random length
(2-10 seconds) to random points inside a random movie belonging to that genre
(trailer/sizzle reel style). Switching channels (up/down "clicker") and
browsing the channel guide both feel instant because the current channel plus
its two neighbors are always pre-buffered in memory, ready to display
immediately.
"""

import math
import os
import random

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtMultimedia import QMediaContent, QMediaPlayer
from PyQt5.QtMultimediaWidgets import QVideoWidget


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
        self._autoplayAfterLoad = False

        self.player.durationChanged.connect(self._onDurationChanged)

    def isReady(self):
        return self._ready and self.path is not None

    def load(self, path, autoplay=False):
        """Begin loading a video file. Becomes ready once duration is known."""
        self.path = path
        self.duration = 0
        self._ready = False
        self._autoplayAfterLoad = autoplay
        self._wantsRandomSeek = True
        self.player.setMedia(QMediaContent(QtCore.QUrl.fromLocalFile(path)))
        self.player.pause()

    def _onDurationChanged(self, duration):
        self.duration = duration
        if duration > 0 and self._wantsRandomSeek:
            self._wantsRandomSeek = False
            self.seekRandom()
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


class ChannelEngine(QtCore.QObject):
    """
    Drives a single genre "channel": schedules movies from the genre as
    1-minute promos (made of random 2-10 second cuts) and pre-buffers the
    next promo so program changes are seamless.
    """

    PROGRAM_DURATION_MS = 60000  # ~1 minute promo per movie
    MIN_CUT_MS = 2000
    MAX_CUT_MS = 10000
    PREFETCH_LEAD_MS = 8000

    programChanged = QtCore.pyqtSignal()

    def __init__(self, channelNumber, genreName, rows, resolver, titleGetter, parent=None):
        super().__init__(parent)
        self.channelNumber = channelNumber
        self.genreName = genreName
        self.rows = list(rows)
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
        self.upcoming = []
        self.currentRow = None
        self.currentTitle = ''
        self.nextRow = None
        self.nextTitle = ''
        self.elapsedMs = 0
        self._pendingCutMs = 0
        self._prefetchStarted = False

        self.cutTimer = QtCore.QTimer(self)
        self.cutTimer.setSingleShot(True)
        self.cutTimer.timeout.connect(self._tick)

    # -- queue management -------------------------------------------------
    def _refill(self):
        pool = list(self.rows)
        random.shuffle(pool)
        if len(pool) > 1 and pool[0] == self.currentRow:
            pool.append(pool.pop(0))
        self.upcoming = pool

    def _popNextRow(self):
        if not self.upcoming:
            self._refill()
        return self.upcoming.pop(0) if self.upcoming else None

    def _peekNextRow(self):
        if not self.upcoming:
            self._refill()
        return self.upcoming[0] if self.upcoming else None

    def _resolvePathForRow(self, row):
        """Try a handful of candidates in case some movies have no video file."""
        tries = 0
        while row is not None and tries < 5:
            path = self.resolver(row)
            if path:
                return row, path
            row = self._popNextRow()
            tries += 1
        return None, None

    # -- lifecycle ----------------------------------------------------------
    def start(self):
        if self.currentRow is None:
            row, path = self._resolvePathForRow(self._popNextRow())
            if path is None:
                return False
            self.currentRow = row
            self.currentTitle = self.titleGetter(row)
            self.activeSlot.setVolume(self.desiredVolume)
            self._stack.setCurrentWidget(self.standbyScreen)
            self.activeSlot.load(path, autoplay=True)
            nextRow = self._peekNextRow()
            self.nextRow = nextRow
            self.nextTitle = self.titleGetter(nextRow) if nextRow is not None else ''
            self.elapsedMs = 0
            self._prefetchStarted = False
            self.programChanged.emit()
        if not self.cutTimer.isActive():
            self._cutActive()
        return True

    def shutdown(self):
        """Fully stop and release this engine's players."""
        self.cutTimer.stop()
        self.slotA.stop()
        self.slotB.stop()
        self.currentRow = None
        self._stack.setCurrentWidget(self.standbyScreen)

    def _onSlotReady(self, slot):
        if slot is self.activeSlot:
            self._stack.setCurrentWidget(slot.videoWidget)

    def setDesiredVolume(self, volume):
        self.desiredVolume = volume
        self.activeSlot.setVolume(volume)

    # -- playback ticking ----------------------------------------------------
    def _tick(self):
        if self.currentRow is None:
            return
        self.elapsedMs += self._pendingCutMs

        if self.elapsedMs >= self.PROGRAM_DURATION_MS:
            if self.standbySlot.isReady():
                self._promoteStandby()
            else:
                # Next promo isn't buffered yet; keep cutting the current one.
                self._cutActive()
            return

        remaining = self.PROGRAM_DURATION_MS - self.elapsedMs
        if not self._prefetchStarted and remaining <= self.PREFETCH_LEAD_MS:
            self._beginPrefetch()

        self._cutActive()

    def _cutActive(self):
        """Cut to a new random point in the active movie; vary cut length 2-10s."""
        interval = random.randint(self.MIN_CUT_MS, self.MAX_CUT_MS)
        self._pendingCutMs = interval
        self.activeSlot.seekRandom(runway_ms=interval)
        self.cutTimer.start(interval)

    def _beginPrefetch(self):
        self._prefetchStarted = True
        row, path = self._resolvePathForRow(self.nextRow)
        self.nextRow = row
        if path:
            self.standbySlot.load(path, autoplay=False)

    def _promoteStandby(self):
        self.activeSlot.pause()
        self.activeSlot, self.standbySlot = self.standbySlot, self.activeSlot
        self._stack.setCurrentWidget(self.activeSlot.videoWidget)
        self.activeSlot.setVolume(self.desiredVolume)
        self.activeSlot.play()
        self.standbySlot.stop()

        self.currentRow = self.nextRow
        self.currentTitle = self.nextTitle
        self.elapsedMs = 0
        self._prefetchStarted = False

        nextRow = self._peekNextRow()
        self.nextRow = nextRow
        self.nextTitle = self.titleGetter(nextRow) if nextRow is not None else ''
        self.programChanged.emit()
        self._cutActive()


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
        self.masterVolume = 70
        self.isFullScreenActive = False
        self._fsTabWidget = None
        self._fsTabIndex = None
        self._fsTabLabel = None

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
            {'genre': genre, 'rows': rows}
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

    # ------------------------------------------------------------------
    # Channel engine (tuning) management
    # ------------------------------------------------------------------
    def _createEngine(self, index):
        chan = self.channels[index]
        engine = ChannelEngine(
            index + 1,
            chan['genre'],
            chan['rows'],
            resolver=self._resolveVideoPath,
            titleGetter=self._titleForRow,
            parent=self,
        )
        engine.programChanged.connect(lambda idx=index: self._onProgramChanged(idx))
        return engine

    def _teardownAllEngines(self):
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
        engine = self.engines.get(index)
        if engine:
            self.displayStack.setCurrentWidget(engine.container)
            self._showBanner(engine)
        self._updateChannelLabel()
        self._updateNowPlayingLabel(engine)
        if self.guideVisible:
            self._refreshGuideTable()

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
        if self.guideVisible:
            self.guideHighlightIndex = (self.guideHighlightIndex + 1) % len(self.channels)
            self._refreshGuideTable()
            self._updateGuidePreview()
        else:
            self._tuneTo(self.currentIndex + 1)

    def channelDown(self):
        if not self.channels:
            return
        if self.guideVisible:
            self.guideHighlightIndex = (self.guideHighlightIndex - 1) % len(self.channels)
            self._refreshGuideTable()
            self._updateGuidePreview()
        else:
            self._tuneTo(self.currentIndex - 1)

    def toggleMute(self):
        self.masterVolume = 0 if self.masterVolume else 70
        self.muteButton.setText("Unmute" if self.masterVolume == 0 else "Mute")
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
        if self.guidePreviewSlot is None:
            self.guidePreviewSlot = ClipSlot(self)
            self.guidePreviewSlot.setVolume(0)
            self.guidePreviewContainer.layout().addWidget(self.guidePreviewSlot.videoWidget)
        self._updateGuidePreview()
        self.guidePreviewTimer.start()

    def _stopGuidePreview(self):
        self.guidePreviewTimer.stop()
        if self.guidePreviewSlot:
            self.guidePreviewSlot.stop()

    def _updateGuidePreview(self):
        if not self.channels or self.guidePreviewSlot is None:
            return
        idx = self.guideHighlightIndex
        engine = self.engines.get(idx)
        if engine and engine.currentRow is not None:
            row = engine.currentRow
        else:
            row = random.choice(self.channels[idx]['rows'])
        path = self._resolveVideoPath(row)
        if path:
            self.guidePreviewSlot.load(path, autoplay=True)

    def _onGuidePreviewTick(self):
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
                rows = chan['rows']
                sample = rows[:2] if len(rows) >= 2 else (rows * 2)[:2]
                nowText = self._titleForRow(sample[0]) if sample else ''
                nextText = self._titleForRow(sample[1]) if len(sample) > 1 else ''

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
        self.setFocus()

    def hideEvent(self, event):
        super().hideEvent(event)
        self.isActive = False
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
