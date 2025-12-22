# TODO List
# OpenGL cover viewer (wip)
# color preference
# Preset layouts
# Fix status bar num visible and num selected when filtered, etc.
# Add selected and total runtime to status bar
# Use PyQt chart to show movies per year broken down by genre

# Required modules
# pip install pyqt5
# pip install imdbpy
# pip install ujson
# pip install pymediainfo

# Commands to make stand alone executable.  Run from Console inside PyCharm

# PC
# pyinstaller --add-data ./smdb/MediaInfo.dll;. --onefile --noconsole --name SMDB smdb/__main__.py

# MAC
# /Users/House/Library/Python/3.9/bin/pyinstaller --onefile --noconsole --name SMDB smdb/__main__.py


from PyQt5 import QtGui, QtWidgets, QtCore
from enum import Enum
from pathlib import Path
import json
import ujson
import fnmatch
import pathlib
import datetime
import collections
import shutil
import os
import random
import requests
import stat
import time
import sys
from pymediainfo import MediaInfo
import re
from pprint import pprint
import urllib.parse
import urllib.request
import zipfile
import io

from .utilities import *
from . import __version__
from .MoviesTableModel import MoviesTableModel, Columns, defaultColumnWidths
from .MovieCover import MovieCover
from .FilterWidget import FilterWidget
from .MovieInfoListView import MovieInfoListView
from .MovieTableView import MovieTableView
from .BackupWidget import BackupWidget
from .HistoryWidget import HistoryWidget
from .WatchListWidget import WatchListWidget
from .MovieData import MovieData
from .MovieFilterProxyModel import MovieFilterProxyModel
from .LightingControlsWidget import LightingControlsWidget


def _default_collections_folder():
    candidates = []
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(sys.executable)
        candidates.append(os.path.join(exe_dir, 'collections'))
        candidates.append(os.path.join(exe_dir, '_internal', 'collections'))
        meipass = getattr(sys, '_MEIPASS', None)
        if meipass:
            candidates.append(os.path.join(meipass, 'collections'))
    here = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.abspath(os.path.join(here, os.pardir))
    candidates.append(os.path.join(repo_root, 'smdb', 'collections'))
    candidates.append(os.path.join(repo_root, 'collections'))
    candidates.append(os.path.join(os.getcwd(), 'collections'))
    candidates.append('collections')
    candidates.append('./collections')
    for p in candidates:
        if os.path.isdir(p):
            return p
    return './collections'


class OperationCanceledError(Exception):
    """Raised when a long-running task is canceled by the user."""
    pass


class MainWindow(QtWidgets.QMainWindow):
    def coverFlowWheelNavigate(self, direction):
        # direction: +1 for next, -1 for previous
        view = self.moviesTableView
        model = view.model()
        proxy = getattr(self, 'moviesTableProxyModel', None)
        if proxy:
            model = proxy
        sel_model = view.selectionModel()
        selected = sel_model.selectedRows()
        if not selected:
            # If nothing selected, select first row in proxy model
            if model.rowCount() > 0:
                view.selectRow(0)
            return
        
        current_row = selected[0].row()
        
        # Find next/previous row in proxy model (clamp at boundaries, no wrapping)
        next_row = current_row
        search_direction = 1 if direction > 0 else -1
        found = False
        for step in range(1, model.rowCount()):
            candidate = current_row + (step * search_direction)
            # Clamp to boundaries instead of wrapping
            if candidate >= model.rowCount() or candidate < 0:
                break  # Reached the end, stop searching
            
            # Proxy model handles filtering, so all rows in the proxy are valid
            next_row = candidate
            found = True
            break
        
        if not found or next_row == current_row:
            # At boundary - stop momentum and reset offset in cover flow widget
            if hasattr(self, 'coverFlowWidget'):
                self.coverFlowWidget.drag_offset = 0.0
                self.coverFlowWidget.drag_velocity = 0.0
                if hasattr(self.coverFlowWidget, 'is_momentum_scrolling'):
                    self.coverFlowWidget.is_momentum_scrolling = False
            return  # At boundary
        
        if next_row != current_row:
            # Get source index for the new row
            modelIndex = model.index(next_row, 0)
            if proxy:
                sourceIndex = proxy.mapToSource(modelIndex)
                sourceRow = sourceIndex.row()
                sourceModel = self.moviesTableModel
            else:
                sourceRow = next_row
                sourceModel = model
            
            # Update cover flow widget immediately to start animation
            # Pass proxy model and proxy row to respect filters
            if hasattr(self, 'coverFlowWidget'):
                self.coverFlowWidget.setModelAndIndex(model, next_row, proxy, view)
            
            # Check if user is actively dragging
            is_dragging = (hasattr(self.coverFlowWidget, 'last_mouse_x') and self.coverFlowWidget.last_mouse_x is not None) or \
                         (hasattr(self.coverFlowWidget, 'is_momentum_scrolling') and self.coverFlowWidget.is_momentum_scrolling)
            
            if is_dragging:
                # During dragging, update views immediately without blocking
                view.selectRow(next_row)
                self.clickedTable(modelIndex, sourceModel, model if proxy else None)
            else:
                # Block selection change handling and store pending info
                self._block_selection_change = True
                self._pending_selection_row = next_row
                self._pending_model_index = modelIndex
                self._pending_source_model = sourceModel
                self._pending_proxy_model = model if proxy else None
                
                # Update the selection (but tableSelectionChanged will be blocked)
                view.selectRow(next_row)
    
    def onCoverFlowAnimationComplete(self, index):
        """Called when the cover flow scroll animation completes"""
        # Unblock selection changes
        self._block_selection_change = False
        # Trigger the delayed selection handling
        if hasattr(self, '_pending_model_index'):
            # Manually trigger what would have happened in tableSelectionChanged
            self.clickedTable(self._pending_model_index, 
                            self._pending_source_model, 
                            self._pending_proxy_model)
            
            # Clean up pending attributes (only if they exist)
            if hasattr(self, '_pending_selection_row'):
                delattr(self, '_pending_selection_row')
            if hasattr(self, '_pending_model_index'):
                delattr(self, '_pending_model_index')
            if hasattr(self, '_pending_source_model'):
                delattr(self, '_pending_source_model')
            if hasattr(self, '_pending_proxy_model'):
                delattr(self, '_pending_proxy_model')

    def __init__(self):
        super(MainWindow, self).__init__()
        start_time = time.perf_counter()

        self.numVisibleMovies = 0
        
        # Initialize log panel text widget reference (will be created later in UI setup)
        self.logTextWidget = None
        
        # Store current plot search regex for highlighting
        self.plotSearchRegex = None
        
        # Store current plot search regex for highlighting
        self.plotSearchRegex = None

        # Define API keys here and use throughout the class
        self.openSubtitlesApiKey = "9iBc6gQ0mlsC9hdapJs6IR2JfmT6F3f1"

        # Movie data helper (downloads, JSON writes, cover downloads)
        self.movieData = MovieData(self)

        # Read the movies folder from the settings
        self.settings = QtCore.QSettings("STC", "SMDB")
        self.moviesFolder = self.settings.value('movies_folder', "", type=str)
        if self.moviesFolder == "":
            self.moviesFolder = "No movies folder set.  Use the \"File->Set movies folder\" menu to set it."
        self.backupFolder = ""
        self.additionalMoviesFolders = self.settings.value('additional_movies_folders', [], type=list)

        # Collections for filter by menu
        self.collections = []
        self.collectionsFolder = self.settings.value('collections_folder', "", type=str)
        if self.collectionsFolder == "":
            self.collectionsFolder = _default_collections_folder()
        self.refreshCollectionsList()


        # Movie selection history
        self.selectionHistory = list()
        self.selectionHistoryIndex = 0
        self.modifySelectionHistory = True

        # Init UI
        self.setTitleBar()
        self.setGeometry(self.settings.value('geometry',
                                             QtCore.QRect(50, 50, 1820, 900),
                                             type=QtCore.QRect))

        self.defaultFontSize = 12
        self.fontSize = self.settings.value('fontSize', self.defaultFontSize, type=int)
        self._debugZoom = False  # set True to log Ctrl+wheel handling
        self.bgColorA = 'rgb(50, 50, 50)'
        self.bgColorB = 'rgb(25, 25, 25)'
        self.bgColorC = 'rgb(0, 0, 0)'
        self.bgColorD = 'rgb(15, 15, 15)'
        self.bgColorE = QtGui.QColor(75, 75, 75)
        self.fgColor = 'rgb(255, 255, 255)'
        self.borderRadiusA = 0
        self.borderRadiusB = 5
        self.borderRadiusC = 10

        self.setStyleSheet(f"font-size:{self.fontSize}px;"
                           f"background: {self.bgColorA};"
                           f"color: {self.fgColor};")

        self.menuBar().setStyleSheet(f"background: {self.bgColorA};"
                                     f"color: {self.fgColor};")

        self.statusBar().setStyleSheet(f"background: {self.bgColorA};"
                                       f"color: {self.fgColor};")

        # Default view state of UI sections
        self.showPrimaryFilter = self.settings.value('showPrimaryFilter', True, type=bool)
        self.showSecondaryFilter = self.settings.value('showSecondaryFilter', True, type=bool)
        self.showMoviesTable = self.settings.value('showMoviesTable', True, type=bool)
        self.showCover = self.settings.value('showCover', True, type=bool)
        self.showMovieInfo = self.settings.value('showMovieInfo', True, type=bool)
        self.showMovieSection = self.settings.value('showMovieSection', True, type=bool)
        self.showSummary = self.settings.value('showSummary', True, type=bool)
        self.showWatchList = self.settings.value('showWatchList', False, type=bool)
        self.showBackupList = self.settings.value('showBackupList', False, type=bool)
        self.showHistoryList = self.settings.value('showHistoryList', False, type=bool)
        self.showLog = self.settings.value('showLog', True, type=bool)
        self.showLightingControls = self.settings.value('showLightingControls', False, type=bool)

        # Default state of cancel button
        self.isCanceled = False

        # Main Menus
        self.initUIFileMenu()
        self.initUIViewMenu()

        # Add the central widget
        centralWidget = QtWidgets.QWidget()
        centralWidget.setStyleSheet(f"background: {self.bgColorB};"
                                    f"border-radius: 0px;")
        self.setCentralWidget(centralWidget)

        # Divides top h splitter and bottom progress bar
        # Do not parent layouts to QMainWindow; set on central widget instead
        mainVLayout = QtWidgets.QVBoxLayout()
        centralWidget.setLayout(mainVLayout)

        # Create a vertical splitter to separate main content from log panel
        self.mainContentLogSplitter = QtWidgets.QSplitter(QtCore.Qt.Vertical, self)
        self.mainContentLogSplitter.setHandleWidth(10)
        mainVLayout.addWidget(self.mainContentLogSplitter)

        # Main H Splitter for filter, movies list, and cover/info
        self.mainHSplitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal, self)
        self.mainHSplitter.setHandleWidth(10)
        self.mainContentLogSplitter.addWidget(self.mainHSplitter)

        # Splitter for filters
        self.filtersVSplitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        self.filtersVSplitter.setHandleWidth(20)

        # Used to set height of rows in various tables based on whether
        # the cover column is visible
        self.rowHeightWithoutCover = 18
        self.rowHeightWithCover = 200

        # Primary Filter
        self.primaryFilterColumn0WidthDefault = 170
        self.primaryFilterColumn1WidthDefault = 60
        self.primaryFilterWidget =\
            FilterWidget("Primary Filter",
                         defaultSectionSize=self.rowHeightWithoutCover,
                         column0Width=self.settings.value("primaryFilterColumn0Width",
                                                          self.primaryFilterColumn0WidthDefault,
                                                          type=int),
                         column1Width=self.settings.value("primaryFilterColumn1Width",
                                                          self.primaryFilterColumn1WidthDefault,
                                                          type=int),
                         bgColorA=self.bgColorA,
                         bgColorB=self.bgColorB,
                         bgColorC=self.bgColorC,
                         bgColorD=self.bgColorD,
                         fgColor=self.fgColor)
        self.primaryFilterWidget.wheelSpun.connect(self.changeFontSize)
        self.filtersVSplitter.addWidget(self.primaryFilterWidget)
        if not self.showPrimaryFilter:
            self.primaryFilterWidget.hide()

        # Secondary Filter
        self.secondaryFilterColumn0WidthDefault = 170
        self.secondaryFilterColumn1WidthDefault = 60
        self.secondaryFilterWidget =\
            FilterWidget("Secondary Filter",
                         filterBy=5,
                         useMovieList=True,
                         minCount=1,
                         defaultSectionSize=self.rowHeightWithoutCover,
                         column0Width=self.settings.value("secondaryFilterColumn0Width",
                                                          self.secondaryFilterColumn0WidthDefault,
                                                          type=int),
                         column1Width=self.settings.value("secondaryFilterColumn1Width",
                                                          self.secondaryFilterColumn1WidthDefault,
                                                          type=int),
                         bgColorA=self.bgColorA,
                         bgColorB=self.bgColorB,
                         bgColorC=self.bgColorC,
                         bgColorD=self.bgColorD,
                         fgColor=self.fgColor)
        self.secondaryFilterWidget.wheelSpun.connect(self.changeFontSize)
        self.filtersVSplitter.addWidget(self.secondaryFilterWidget)
        if not self.showSecondaryFilter:
            self.secondaryFilterWidget.hide()

        sizes = [int(x) for x in self.settings.value('filterVSplitterSizes', [200, 200], type=list)]
        self.filtersVSplitter.setSizes(sizes)

        # Splitter for Movies Table and Watch List
        self.moviesWatchListBackupVSplitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        self.moviesWatchListBackupVSplitter.setHandleWidth(20)

        # Movies Table
        # TabView for Movies List and Cover Flow
        self.moviesTabWidget = QtWidgets.QTabWidget()
        # Movies List Tab
        self.moviesTableWidget = QtWidgets.QFrame()
        self.moviesTableView = MovieTableView()
        self.moviesTabWidget.addTab(self.moviesTableWidget, "List")
        # Cover Flow Tab (OpenGL)
        from .CoverFlowGLWidget import CoverFlowGLWidget
        self.coverFlowWidget = CoverFlowGLWidget()
        self.coverFlowWidget.wheelMovieChange.connect(self.coverFlowWheelNavigate)
        self.coverFlowWidget.scrollAnimationComplete.connect(self.onCoverFlowAnimationComplete)
        self.moviesTabWidget.addTab(self.coverFlowWidget, "Cover Flow")
        
        # Restore saved tab index (0=List, 1=Cover Flow)
        savedTabIndex = self.settings.value('moviesTabIndex', 0, type=int)
        self.moviesTabWidget.setCurrentIndex(savedTabIndex)
        
        self.moviesTableDefaultColumns = [Columns.Year.value,
                                          Columns.Title.value,
                                          Columns.Rating.value,
                                          Columns.MpaaRating.value,
                                          Columns.Width.value,
                                          Columns.Height.value,
                                          Columns.Size.value]
        try:
            self.moviesTableColumns = self.settings.value('moviesTableColumns',
                                                          self.moviesTableDefaultColumns,
                                                          type=list)
            self.moviesTableColumns = [int(m) for m in self.moviesTableColumns]
        except TypeError:
            self.moviesTableColumns = self.moviesTableDefaultColumns

        try:
            self.moviesTableColumnWidths = self.settings.value('moviesTableColumnWidths',
                                                               defaultColumnWidths,
                                                               type=list)
            self.moviesTableColumnWidths = [int(m) for m in self.moviesTableColumnWidths]
        except TypeError:
            self.moviesTableColumnWidths = defaultColumnWidths

        self.moviesTableView.wheelSpun.connect(self.changeFontSize)
        self.moviesTableTitleFilterBox = QtWidgets.QLineEdit()
        self.moviesTableSearchPlotsBox = QtWidgets.QLineEdit()
        self.moviesTableColumnsVisible = []
        self.moviesListHeaderActions = []
        self.initUIMoviesTable()
        
        # Create container for tab widget and navigation controls
        self.moviesTabContainer = QtWidgets.QFrame()
        self.moviesTabContainer.setFrameShape(QtWidgets.QFrame.Panel | QtWidgets.QFrame.Sunken)
        self.moviesTabContainer.setLineWidth(5)
        self.moviesTabContainer.setStyleSheet(f"background: {self.bgColorB};"
                                              f"border-radius: 10px;")
        moviesTabContainerLayout = QtWidgets.QVBoxLayout()
        self.moviesTabContainer.setLayout(moviesTabContainerLayout)
        
        # Add tabview to container
        moviesTabContainerLayout.addWidget(self.moviesTabWidget)
        
        # Add navigation controls below the tabs
        self.initUINavigationControls(moviesTabContainerLayout)
        
        # Add container instead of direct tab widget
        self.moviesWatchListBackupVSplitter.addWidget(self.moviesTabContainer)
        if not self.showMoviesTable:
            self.moviesTableWidget.hide()

        # Watch List
        # Initialize early for WatchListWidget
        if not hasattr(self, 'moviesSmdbData'):
            self.moviesSmdbData = None
        watchListSmdbFile = os.path.join(self.moviesFolder, "smdb_data_watch_list.json")
        self.watchListWidget = WatchListWidget(
            parent=self,
            settings=self.settings,
            bgColorA=self.bgColorA,
            bgColorB=self.bgColorB,
            bgColorC=self.bgColorC,
            bgColorD=self.bgColorD,
            moviesSmdbData=self.moviesSmdbData,
            watchListSmdbFile=watchListSmdbFile,
            outputCallback=self.output
        )
        self.moviesWatchListBackupVSplitter.addWidget(self.watchListWidget)
        if not self.showWatchList:
            self.watchListWidget.hide()

        # Backup List
        # Initialize early for BackupWidget
        if not hasattr(self, 'moviesSmdbData'):
            self.moviesSmdbData = None
        if not hasattr(self, 'backupListSmdbFile'):
            self.backupListSmdbFile = os.path.join(self.moviesFolder, "smdb_data_backup_list.json")
            
        self.backupListWidget = BackupWidget(
            self,
            self.settings,
            self.bgColorA,
            self.bgColorB,
            self.bgColorC,
            self.bgColorD,
            self.moviesSmdbData,
            self.backupListSmdbFile,
            self.output
        )
        
        # Initialize references for backward compatibility
        self.backupAnalysed = self.backupListWidget.analysed
        self.backupFolder = self.backupListWidget.folder
        self.backupListTableView = self.backupListWidget.listTableView
        self.backupListColumns = self.backupListWidget.listColumns
        self.backupListColumnWidths = self.backupListWidget.listColumnWidths
        self.backupListColumnsVisible = self.backupListWidget.listColumnsVisible
        self.backupListHeaderActions = self.backupListWidget.listHeaderActions
        self.backupFolderEdit = self.backupListWidget.folderEdit
        
        # Connect wheel spin event
        self.backupListTableView.wheelSpun.connect(self.changeFontSize)

        self.moviesWatchListBackupVSplitter.addWidget(self.backupListWidget)
        if not self.showBackupList:
            self.backupListWidget.hide()

        # History List
        historyListSmdbFile = os.path.join(self.moviesFolder, "smdb_data_history_list.json")
        self.historyListWidget = HistoryWidget(
            parent=self,
            settings=self.settings,
            bgColorA=self.bgColorA,
            bgColorB=self.bgColorB,
            bgColorC=self.bgColorC,
            bgColorD=self.bgColorD,
            moviesSmdbData=self.moviesSmdbData,
            historyListSmdbFile=historyListSmdbFile,
            outputCallback=self.output
        )
        self.moviesWatchListBackupVSplitter.addWidget(self.historyListWidget)
        if not self.showHistoryList:
            self.historyListWidget.hide()

        sizes = [int(x) for x in self.settings.value('moviesWatchListBackupVSplitterSizes', [500, 200, 100, 100], type=list)]
        self.moviesWatchListBackupVSplitter.setSizes(sizes)

        # Movie section widget
        self.initUIMovieSection()

        # Lighting Controls Widget
        self.lightingControlsWidget = LightingControlsWidget(
            parent=self,
            bgColorA=self.bgColorA,
            bgColorB=self.bgColorB,
            bgColorC=self.bgColorC,
            fgColor=self.fgColor
        )
        # Connect signal to refresh the cover flow widget when controls change
        self.lightingControlsWidget.controlsChanged.connect(self.onLightingControlsChanged)

        # Wrap lighting controls in a frame
        self.lightingControlsFrame = QtWidgets.QFrame()
        self.lightingControlsFrame.setFrameShape(QtWidgets.QFrame.Panel | QtWidgets.QFrame.Sunken)
        self.lightingControlsFrame.setLineWidth(5)
        self.lightingControlsFrame.setStyleSheet(f"background: {self.bgColorB};"
                                                  f"border-radius: 10px;")
        lightingControlsLayout = QtWidgets.QVBoxLayout()
        self.lightingControlsFrame.setLayout(lightingControlsLayout)
        lightingControlsLayout.addWidget(self.lightingControlsWidget)
        if not self.showLightingControls:
            self.lightingControlsFrame.hide()

        # Add the sub-layouts to the self.mainHSplitter
        self.mainHSplitter.addWidget(self.filtersVSplitter)
        self.mainHSplitter.addWidget(self.moviesWatchListBackupVSplitter)
        self.mainHSplitter.addWidget(self.lightingControlsFrame)  # Lighting controls before movie section
        self.mainHSplitter.addWidget(self.movieSectionWidget)
        self.mainHSplitter.splitterMoved.connect(self.resizeCoverFile)

        # Main horizontal sizes (added fourth panel for lighting controls, positioned before movie section)
        sizes = [int(x) for x in self.settings.value('mainHSplitterSizes', [270, 750, 300, 800], type=list)]
        self.mainHSplitter.setSizes(sizes)

        # Log Panel
        self.logWidget = QtWidgets.QFrame()
        self.logWidget.setFrameShape(QtWidgets.QFrame.Panel | QtWidgets.QFrame.Sunken)
        self.logWidget.setLineWidth(5)
        self.logWidget.setStyleSheet(f"background: {self.bgColorB};"
                                     f"border-radius: 10px;")
        logVLayout = QtWidgets.QVBoxLayout()
        self.logWidget.setLayout(logVLayout)
        
        logLabel = QtWidgets.QLabel("Log")
        logVLayout.addWidget(logLabel)
        
        self.logTextWidget = QtWidgets.QTextEdit()
        self.logTextWidget.setReadOnly(True)
        self.logTextWidget.setStyleSheet(f"background: {self.bgColorC};"
                                        f"color: {self.fgColor};"
                                        f"font-size: {self.fontSize}px;")
        self.logTextWidget.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.logTextWidget.customContextMenuRequested.connect(self.showLogContextMenu)
        logVLayout.addWidget(self.logTextWidget)
        
        # Set the global output function so all modules can use it
        set_output_function(self.output)
        
        self.mainContentLogSplitter.addWidget(self.logWidget)
        if not self.showLog:
            self.logWidget.hide()
        
        # Set sizes for content/log splitter (main content gets most space, log gets smaller portion)
        contentLogSizes = [int(x) for x in self.settings.value('mainContentLogSplitterSizes', [700, 150], type=list)]
        self.mainContentLogSplitter.setSizes(contentLogSizes)

        self.output(f"Welcome to SMDB v{__version__}")
        
        # Bottom
        # Create bottom layout without parenting to QMainWindow
        bottomLayout = QtWidgets.QHBoxLayout()
        mainVLayout.addLayout(bottomLayout)
        self.progressBar = QtWidgets.QProgressBar()
        self.progressBar.setStyleSheet(f"background: {self.bgColorC};"
                                       f"border-radius: 5px")
        self.progressBar.setMaximum(100)
        bottomLayout.addWidget(self.progressBar)
        cancelButton = QtWidgets.QPushButton("Cancel", self)
        cancelButton.clicked.connect(self.cancelButtonClicked)
        cancelButton.setStyleSheet(f"background: rgb(100, 100, 100);"
                                   f"border-radius: 5px")
        cancelButton.setFixedSize(100, 25)
        bottomLayout.addWidget(cancelButton)

        self.setFontSize(self.fontSize)

        # Show the window
        self.show()

        self.moviesSmdbFile = os.path.join(self.moviesFolder, "smdb_data.json")
        self.moviesSmdbData = None
        self.moviesTableModel = None
        self.moviesTableProxyModel = None

        self.refreshMoviesList(writeToLog=True)

        # Update BackupWidget's moviesSmdbData reference after it's loaded
        if hasattr(self, 'backupListWidget'):
            self.backupListWidget.moviesSmdbData = self.moviesSmdbData

        self.primaryFilterWidget.moviesSmdbData = self.moviesSmdbData
        self.primaryFilterWidget.populateFiltersTable()
        self.primaryFilterWidget.tableSelectionChangedSignal.connect(
            lambda: self.filterTableSelectionChanged())

        self.secondaryFilterWidget.moviesSmdbData = self.moviesSmdbData
        self.secondaryFilterWidget.populateFiltersTable()
        self.secondaryFilterWidget.tableSelectionChangedSignal.connect(
            lambda: self.filterTableSelectionChanged(mainFilter=False))

        self.watchListSmdbFile = os.path.join(self.moviesFolder, "smdb_data_watch_list.json")
        self.watchListSmdbData = None
        self.watchListTableModel = None
        self.watchListTableProxyModel = None
        self.refreshWatchList()

        # Refresh history list data
        self.refreshHistoryList()

        # backupListSmdbFile already initialized before BackupWidget creation
        # Just refresh the backup list data
        self.backupListSmdbData = None
        self.backupListTableModel = None
        self.backupListTableProxyModel = None
        self.refreshBackupList()

        self.showMoviesTableSelectionStatus()

        # Startup messages at end of initialization
        elapsed = time.perf_counter() - start_time
        self.output(f"Time to startup: {elapsed:.3f}s")


    def clearMovie(self):
        self.summary.clear()
        self.titleLabel.clear()
        self.showCoverFile(None)
        self.movieInfoListView.clear()

    def output(self, *args, **kwargs):
        """Output function that replaces print() - outputs to both console and log panel"""
        sep = kwargs.pop('sep', ' ')
        end = kwargs.pop('end', '\n')
        file = kwargs.pop('file', sys.stdout)
        flush = kwargs.pop('flush', False)

        message_body = sep.join(str(arg) for arg in args)
        timestamp = datetime.datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
        full_message = f"{timestamp} {message_body}" if message_body else timestamp

        print(full_message, end=end, file=file, flush=flush)

        # Also append to log panel if it exists
        if self.logTextWidget is not None:
            message = full_message
            if end == '\n':
                message += '\n'
            scrollbar = self.logTextWidget.verticalScrollBar()
            prev_value = scrollbar.value()
            at_bottom = prev_value >= scrollbar.maximum()
            cursor = self.logTextWidget.textCursor()
            cursor.movePosition(QtGui.QTextCursor.End)
            cursor.insertText(message)
            if at_bottom:
                scrollbar.setValue(scrollbar.maximum())
            else:
                scrollbar.setValue(min(prev_value, scrollbar.maximum()))
            # Process events so log updates in real-time during loops
            QtCore.QCoreApplication.processEvents()

    def wheelEvent(self, event):
        dy = event.angleDelta().y()
        self.changeFontSize(1 if dy > 0 else (-1 if dy < 0 else 0))
        event.accept()

    def changeFontSize(self, delta):
        # Require Ctrl to be held (allow other modifiers too)
        mods = QtWidgets.QApplication.keyboardModifiers()
        if not (mods & QtCore.Qt.ControlModifier):
            if self._debugZoom:
                self.output(f"zoom: ignored (no Ctrl). mods={int(mods)} raw={delta}")
            return

        # Normalize to step of -1, 0, or +1
        raw = delta
        delta = -1 if delta < 0 else (1 if delta > 0 else 0)

        if self._debugZoom:
            self.output(f"zoom: mods={int(mods)} raw={raw} norm={delta} font={self.fontSize}")

        # Avoid redundant updates at bounds
        if (self.fontSize <= 6 and delta < 0) or (self.fontSize >= 29 and delta > 0):
            if self._debugZoom:
                self.output("zoom: at bound, no change")
            return

        self.setFontSize(self.fontSize + delta)
        if self._debugZoom:
            self.output(f"zoom: new font={self.fontSize}")

    def setFontSize(self, fontSize):
        self.fontSize = max(6, min(29, fontSize))
        self.setStyleSheet(f"font-size:{self.fontSize}px;"
                           f"background: {self.bgColorA};"
                           f"color: {self.fgColor};")
        self.titleLabel.setStyleSheet(f"background: {self.bgColorC};"
                                      f"font-size: {self.fontSize * 2}px;")
        self.rowHeightWithoutCover = max(1, int(round(18 * self.fontSize / 12)))

        if len(self.moviesTableColumnsVisible) > 0 and self.moviesTableColumnsVisible[Columns.Cover.value]:
            self.moviesTableView.verticalHeader().setDefaultSectionSize(self.rowHeightWithCover)
        else:
            self.moviesTableView.verticalHeader().setDefaultSectionSize(self.rowHeightWithoutCover)

        if len(self.watchListWidget.listColumnsVisible) > 0 and self.watchListWidget.listColumnsVisible[Columns.Cover.value]:
            self.watchListWidget.listTableView.verticalHeader().setDefaultSectionSize(self.rowHeightWithCover)
        else:
            self.watchListWidget.listTableView.verticalHeader().setDefaultSectionSize(self.rowHeightWithoutCover)

        if len(self.backupListColumnsVisible) > 0 and self.backupListColumnsVisible[Columns.Cover.value]:
            self.backupListTableView.verticalHeader().setDefaultSectionSize(self.rowHeightWithCover)
        else:
            self.backupListTableView.verticalHeader().setDefaultSectionSize(self.rowHeightWithoutCover)

        if len(self.historyListWidget.listColumnsVisible) > 0 and self.historyListWidget.listColumnsVisible[Columns.Cover.value]:
            self.historyListWidget.listTableView.verticalHeader().setDefaultSectionSize(self.rowHeightWithCover)
        else:
            self.historyListWidget.listTableView.verticalHeader().setDefaultSectionSize(self.rowHeightWithoutCover)

        self.primaryFilterWidget.filterTable.verticalHeader().setDefaultSectionSize(self.rowHeightWithoutCover)
        self.secondaryFilterWidget.filterTable.verticalHeader().setDefaultSectionSize(self.rowHeightWithoutCover)
        
        # Update log panel font size if it exists
        if self.logTextWidget is not None:
            self.logTextWidget.setStyleSheet(f"background: {self.bgColorC};"
                                             f"color: {self.fgColor};"
                                             f"font-size: {self.fontSize}px;")


    def clearSettings(self):
        self.settings.clear()

    def closeEvent(self, a0: QtGui.QCloseEvent) -> None:
        self.settings.setValue('geometry', self.geometry())
        self.settings.setValue('moviesTabIndex', self.moviesTabWidget.currentIndex())
        self.settings.setValue('mainHSplitterSizes', self.mainHSplitter.sizes())
        self.settings.setValue('mainContentLogSplitterSizes', self.mainContentLogSplitter.sizes())
        self.settings.setValue('coverInfoHSplitterSizes', self.coverInfoHSplitter.sizes())
        self.settings.setValue('coverSummaryVSplitterSizes', self.coverSummaryVSplitter.sizes())
        self.settings.setValue('moviesWatchListBackupVSplitterSizes', self.moviesWatchListBackupVSplitter.sizes())
        self.settings.setValue('filterVSplitterSizes', self.filtersVSplitter.sizes())
        self.settings.setValue('showPrimaryFilter', self.showPrimaryFilter)
        self.settings.setValue('showSecondaryFilter', self.showSecondaryFilter)
        self.settings.setValue('showMoviesTable', self.showMoviesTable)
        self.settings.setValue('showCover', self.showCover)
        self.settings.setValue('showMovieInfo', self.showMovieInfo)
        self.settings.setValue('showMovieSection', self.showMovieSection)
        self.settings.setValue('showSummary', self.showSummary)
        self.settings.setValue('showWatchList', self.showWatchList)
        self.settings.setValue('showHistoryList', self.showHistoryList)
        self.settings.setValue('showBackupList', self.showBackupList)
        self.settings.setValue('showLog', self.showLog)
        self.settings.setValue('showLightingControls', self.showLightingControls)
        self.settings.setValue('fontSize', self.fontSize)
        
        # Save API keys if they have been set
        if self.movieData.tmdbApiKey:
            self.settings.setValue('tmdbApiKey', self.movieData.tmdbApiKey)
        if self.movieData.omdbApiKey:
            self.settings.setValue('omdbApiKey', self.movieData.omdbApiKey)

        self.saveTableColumns('moviesTable', self.moviesTableView, self.moviesTableColumnsVisible)
        self.saveTableColumns('watchListTable', self.watchListWidget.listTableView, self.watchListWidget.listColumnsVisible)
        self.saveTableColumns('historyListTable', self.historyListWidget.listTableView, self.historyListWidget.listColumnsVisible)
        self.saveTableColumns('backupListTable', self.backupListTableView, self.backupListColumnsVisible)

        self.settings.setValue('primaryFilterColumn0Width', self.primaryFilterWidget.filterTable.columnWidth(0))
        self.settings.setValue('primaryFilterColumn1Width', self.primaryFilterWidget.filterTable.columnWidth(1))
        self.settings.setValue('secondaryFilterColumn0Width', self.secondaryFilterWidget.filterTable.columnWidth(0))
        self.settings.setValue('secondaryFilterColumn1Width', self.secondaryFilterWidget.filterTable.columnWidth(1))

    def saveTableColumns(self, saveName, tableView, columnsVisible):
        visibleColumns = list()
        for i, c in enumerate(columnsVisible):
            if c:
                visibleColumns.append(i)
        self.settings.setValue(f'{saveName}Columns', visibleColumns)

        columnWidths = list()
        for i in range(len(defaultColumnWidths)):
            width = tableView.columnWidth(i)
            if width == 0:
                width = defaultColumnWidths[i]
            columnWidths.append(width)
        self.settings.setValue(f'{saveName}ColumnWidths', columnWidths)

    def initUIFileMenu(self):
        menuBar = self.menuBar()
        fileMenu = menuBar.addMenu('File')

        setMovieFolderAction = QtWidgets.QAction("Set primary movies folder", self)
        setMovieFolderAction.triggered.connect(self.setPrimaryMoviesFolder)
        fileMenu.addAction(setMovieFolderAction)

        clearPrimaryMoviesFolderAction = QtWidgets.QAction("Clear primary movies folder", self)
        clearPrimaryMoviesFolderAction.triggered.connect(self.clearPrimaryMoviesFolder)
        fileMenu.addAction(clearPrimaryMoviesFolderAction)

        addAdditionalMoviesFolderAction = QtWidgets.QAction("Add additional movies folder", self)
        addAdditionalMoviesFolderAction.triggered.connect(self.browseAdditionalMoviesFolder)
        fileMenu.addAction(addAdditionalMoviesFolderAction)

        clearAdditionalMoviesFolderAction = QtWidgets.QAction("Clear additional movies folders", self)
        clearAdditionalMoviesFolderAction.triggered.connect(self.clearAdditionalMoviesFolders)
        fileMenu.addAction(clearAdditionalMoviesFolderAction)

        rescanAction = QtWidgets.QAction("Rescan all movie folders", self)
        rescanAction.triggered.connect(lambda: self.refreshMoviesList(forceScan=True))
        fileMenu.addAction(rescanAction)

        rescanNewAction = QtWidgets.QAction("Rescan new movie folders", self)
        rescanNewAction.triggered.connect(self.rescanModifiedSince)
        fileMenu.addAction(rescanNewAction)

        rebuildSmdbFileAction = QtWidgets.QAction("Rebuild SMDB file", self)
        rebuildSmdbFileAction.triggered.connect(self.rebuildSmdbFileAndReload)

        setCollectionsFolderAction = QtWidgets.QAction("Set collections folder", self)
        setCollectionsFolderAction.triggered.connect(self.setCollectionsFolder)
        fileMenu.addAction(setCollectionsFolderAction)

        fileMenu.addAction(rebuildSmdbFileAction)

        conformMoviesAction = QtWidgets.QAction("Conform movies in folder", self)
        conformMoviesAction.triggered.connect(self.conformMovies)
        fileMenu.addAction(conformMoviesAction)

        preferencesAction = QtWidgets.QAction("Preferences", self)
        preferencesAction.triggered.connect(self.preferences)
        fileMenu.addAction(preferencesAction)

        clearSettingsAction = QtWidgets.QAction("Clear Settings", self)
        clearSettingsAction.triggered.connect(self.clearSettings)
        fileMenu.addAction(clearSettingsAction)

        quitAction = QtWidgets.QAction("Quit", self)
        quitAction.triggered.connect(QtCore.QCoreApplication.quit)
        fileMenu.addAction(quitAction)

    def initUIViewMenu(self):
        menuBar = self.menuBar()
        viewMenu = menuBar.addMenu('View')

        showPrimaryFilterAction = QtWidgets.QAction("Show Primary Filter", self)
        showPrimaryFilterAction.setCheckable(True)
        showPrimaryFilterAction.setChecked(self.showPrimaryFilter)
        showPrimaryFilterAction.triggered.connect(self.showPrimaryFilterMenu)
        viewMenu.addAction(showPrimaryFilterAction)

        showSecondaryFilterAction = QtWidgets.QAction("Show Secondary Filter", self)
        showSecondaryFilterAction.setCheckable(True)
        showSecondaryFilterAction.setChecked(self.showSecondaryFilter)
        showSecondaryFilterAction.triggered.connect(self.showSecondaryFilterMenu)
        viewMenu.addAction(showSecondaryFilterAction)

        showMoviesTableAction = QtWidgets.QAction("Show Movies", self)
        showMoviesTableAction.setCheckable(True)
        showMoviesTableAction.setChecked(self.showMoviesTable)
        showMoviesTableAction.triggered.connect(self.showMoviesTableMenu)
        viewMenu.addAction(showMoviesTableAction)

        showWatchListAction = QtWidgets.QAction("Show Watch List", self)
        showWatchListAction.setCheckable(True)
        showWatchListAction.setChecked(self.showWatchList)
        showWatchListAction.triggered.connect(self.showWatchListMenu)
        viewMenu.addAction(showWatchListAction)

        showHistoryListAction = QtWidgets.QAction("Show History List", self)
        showHistoryListAction.setCheckable(True)
        showHistoryListAction.setChecked(self.showHistoryList)
        showHistoryListAction.triggered.connect(self.showHistoryListMenu)
        viewMenu.addAction(showHistoryListAction)

        showBackupListAction = QtWidgets.QAction("Show Backup List", self)
        showBackupListAction.setCheckable(True)
        showBackupListAction.setChecked(self.showBackupList)
        showBackupListAction.triggered.connect(self.showBackupListMenu)
        viewMenu.addAction(showBackupListAction)

        showMovieSectionAction = QtWidgets.QAction("Show Movie Section", self)
        showMovieSectionAction.setCheckable(True)
        showMovieSectionAction.setChecked(self.showMovieSection)
        showMovieSectionAction.triggered.connect(self.showMovieSectionMenu)
        viewMenu.addAction(showMovieSectionAction)

        showCoverAction = QtWidgets.QAction("Show Cover", self)
        showCoverAction.setCheckable(True)
        showCoverAction.setChecked(self.showCover)
        showCoverAction.triggered.connect(self.showCoverMenu)
        viewMenu.addAction(showCoverAction)

        showMovieInfoAction = QtWidgets.QAction("Show Movie Info", self)
        showMovieInfoAction.setCheckable(True)
        showMovieInfoAction.setChecked(self.showMovieInfo)
        showMovieInfoAction.triggered.connect(self.showMovieInfoMenu)
        viewMenu.addAction(showMovieInfoAction)

        showSummaryAction = QtWidgets.QAction("Show Summary", self)
        showSummaryAction.setCheckable(True)
        showSummaryAction.setChecked(self.showSummary)
        showSummaryAction.triggered.connect(self.showSummaryMenu)
        viewMenu.addAction(showSummaryAction)

        showLogAction = QtWidgets.QAction("Show Log", self)
        showLogAction.setCheckable(True)
        showLogAction.setChecked(self.showLog)
        showLogAction.triggered.connect(self.showLogMenu)
        viewMenu.addAction(showLogAction)

        showLightingControlsAction = QtWidgets.QAction("Show Lighting Controls", self)
        showLightingControlsAction.setCheckable(True)
        showLightingControlsAction.setChecked(self.showLightingControls)
        showLightingControlsAction.triggered.connect(self.showLightingControlsMenu)
        viewMenu.addAction(showLightingControlsAction)

        restoreDefaultWindowsAction = QtWidgets.QAction("Restore default window configuration", self)
        restoreDefaultWindowsAction.triggered.connect(self.restoreDefaultWindows)
        viewMenu.addAction(restoreDefaultWindowsAction)

    def toggleColumn(self, c, tableView, visibleList):
        visibleList[c.value] = not visibleList[c.value]
        if visibleList[c.value]:
            tableView.showColumn(c.value)
            if c.value == Columns.Cover.value:
                tableView.verticalHeader().setDefaultSectionSize(self.rowHeightWithCover)
                tableView.setVerticalScrollMode(QtWidgets.QAbstractItemView.ScrollPerPixel)
                tableView.verticalScrollBar().setSingleStep(10)
        else:
            tableView.hideColumn(c.value)
            if c.value == Columns.Cover.value:
                tableView.verticalHeader().setDefaultSectionSize(self.rowHeightWithoutCover)
                tableView.setVerticalScrollMode(QtWidgets.QAbstractItemView.ScrollPerItem)
                tableView.verticalScrollBar().setSingleStep(5)

    def showAllColumns(self, tableView, visibleList):
        tableView.verticalHeader().setDefaultSectionSize(self.rowHeightWithCover)
        tableView.setVerticalScrollMode(QtWidgets.QAbstractItemView.ScrollPerPixel)
        tableView.verticalScrollBar().setSingleStep(10)
        for i, c in enumerate(visibleList):
            visibleList[i] = True
            tableView.showColumn(i)

    def hideAllColumns(self, tableView, visibleList):
        tableView.verticalHeader().setDefaultSectionSize(self.rowHeightWithoutCover)
        tableView.setVerticalScrollMode(QtWidgets.QAbstractItemView.ScrollPerItem)
        tableView.verticalScrollBar().setSingleStep(5)
        for i, c in enumerate(visibleList):
            if i != Columns.Year.value:  # leave the year column visible
                visibleList[i] = False
                tableView.hideColumn(i)

    def headerRightMenuShow(self, QPos, tableView, visibleColumnsList, model):
        menu = QtWidgets.QMenu(tableView.horizontalHeader())

        showAllAction = QtWidgets.QAction("Show All")
        showAllAction.triggered.connect(lambda a,
                                               tv=tableView,
                                               vcl=visibleColumnsList:
                                        self.showAllColumns(tv, vcl))
        menu.addAction(showAllAction)

        hideAllAction = QtWidgets.QAction("Hide All")
        hideAllAction.triggered.connect(lambda a,
                                               tv=tableView,
                                               vcl=visibleColumnsList:
                                        self.hideAllColumns(tv, vcl))
        menu.addAction(hideAllAction)

        headers = model.getHeaders()

        actionsList = []
        for c in Columns:
            header = headers[c.value]
            action = QtWidgets.QAction(header)
            action.setCheckable(True)
            action.setChecked(visibleColumnsList[c.value])
            action.triggered.connect(lambda a,
                                            column=c,
                                            tv=tableView,
                                            vcl=visibleColumnsList:
                                     self.toggleColumn(column, tv, vcl))
            menu.addAction(action)
            actionsList.append(action)

        menu.exec_(QtGui.QCursor.pos())

    def initUINavigationControls(self, parentLayout):
        """Initialize navigation controls shared between List and Cover Flow tabs"""
        moviesTableSearchHLayout = QtWidgets.QHBoxLayout()
        parentLayout.addLayout(moviesTableSearchHLayout)

        buttonsVLayout = QtWidgets.QVBoxLayout()
        moviesTableSearchHLayout.addLayout(buttonsVLayout)

        backForwardHLayout = QtWidgets.QHBoxLayout()
        buttonsVLayout.addLayout(backForwardHLayout)

        # Back button
        backButton = QtWidgets.QPushButton("Back")
        backButton.setSizePolicy(QtWidgets.QSizePolicy.Minimum,
                                 QtWidgets.QSizePolicy.Minimum)
        backButton.clicked.connect(self.moviesTableBack)
        backButton.setStyleSheet(f"background: {self.bgColorA};"
                                 f"border-radius: 5px;")
        backForwardHLayout.addWidget(backButton)

        # Forward button
        forwardButton = QtWidgets.QPushButton("Forward")
        forwardButton.setSizePolicy(QtWidgets.QSizePolicy.Minimum,
                                    QtWidgets.QSizePolicy.Minimum)
        forwardButton.clicked.connect(self.moviesTableForward)
        forwardButton.setStyleSheet(f"background: {self.bgColorA};"
                                    f"border-radius: 5px;")
        backForwardHLayout.addWidget(forwardButton)

        randomAllHLayout = QtWidgets.QHBoxLayout()
        buttonsVLayout.addLayout(randomAllHLayout)

        # Pick random button
        pickRandomButton = QtWidgets.QPushButton("Random")
        pickRandomButton.setSizePolicy(QtWidgets.QSizePolicy.Minimum,
                                       QtWidgets.QSizePolicy.Minimum)
        pickRandomButton.clicked.connect(self.pickRandomMovie)
        pickRandomButton.setStyleSheet(f"background: {self.bgColorA};"
                                       f"border-radius: 5px;")
        randomAllHLayout.addWidget(pickRandomButton)

        # Show all button
        showAllButton = QtWidgets.QPushButton("Show All")
        showAllButton.setSizePolicy(QtWidgets.QSizePolicy.Minimum,
                                    QtWidgets.QSizePolicy.Minimum)
        showAllButton.clicked.connect(self.showAllMoviesTableView)
        showAllButton.setStyleSheet(f"background: {self.bgColorA};"
                                    f"border-radius: 5px;")
        randomAllHLayout.addWidget(showAllButton)

        moviesTableSearchVLayout = QtWidgets.QVBoxLayout()
        moviesTableSearchHLayout.addLayout(moviesTableSearchVLayout)

        moviesTableFilterHLayout = QtWidgets.QHBoxLayout()
        moviesTableSearchVLayout.addLayout(moviesTableFilterHLayout)

        # Filter box
        titleFilterText = QtWidgets.QLabel("Filter Titles")
        titleFilterText.setSizePolicy(QtWidgets.QSizePolicy.Maximum,
                                      QtWidgets.QSizePolicy.Maximum)
        moviesTableFilterHLayout.addWidget(titleFilterText)

        self.moviesTableTitleFilterBox.setStyleSheet(f"background: {self.bgColorC};"
                                                     f"border-radius: 5px;")
        self.moviesTableTitleFilterBox.setSizePolicy(QtWidgets.QSizePolicy.Minimum,
                                                     QtWidgets.QSizePolicy.Minimum)
        self.moviesTableTitleFilterBox.setClearButtonEnabled(True)
        self.moviesTableTitleFilterBox.textChanged.connect(self.searchMoviesTableView)
        moviesTableFilterHLayout.addWidget(self.moviesTableTitleFilterBox)

        # Search plots
        moviesTableSearchPlotsHLayout = QtWidgets.QHBoxLayout()
        moviesTableSearchVLayout.addLayout(moviesTableSearchPlotsHLayout)

        searchPlotsText = QtWidgets.QLabel("Search Plots")
        searchPlotsText.setSizePolicy(QtWidgets.QSizePolicy.Maximum,
                                      QtWidgets.QSizePolicy.Maximum)
        moviesTableSearchPlotsHLayout.addWidget(searchPlotsText)

        self.moviesTableSearchPlotsBox.setStyleSheet(f"background: {self.bgColorC};"
                                                     f"border-radius: 5px;")
        self.moviesTableSearchPlotsBox.setSizePolicy(QtWidgets.QSizePolicy.Minimum,
                                                     QtWidgets.QSizePolicy.Minimum)
        self.moviesTableSearchPlotsBox.setClearButtonEnabled(True)
        self.moviesTableSearchPlotsBox.returnPressed.connect(self.searchPlots)
        moviesTableSearchPlotsHLayout.addWidget(self.moviesTableSearchPlotsBox)

        moviesTableSearchHLayout.setStretch(0, 3)
        moviesTableSearchHLayout.setStretch(1, 10)

    def initUIMoviesTable(self):
        self.moviesTableWidget.setFrameShape(QtWidgets.QFrame.Panel | QtWidgets.QFrame.Sunken)
        self.moviesTableWidget.setLineWidth(5)
        self.moviesTableWidget.setStyleSheet(f"background: {self.bgColorB};"
                                             f"border-radius: 10px;")

        moviesTableViewVLayout = QtWidgets.QVBoxLayout()
        self.moviesTableWidget.setLayout(moviesTableViewVLayout)

        moviesLabel = QtWidgets.QLabel("Movies")
        moviesTableViewVLayout.addWidget(moviesLabel)

        self.moviesTableView.setSortingEnabled(True)
        self.moviesTableView.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.moviesTableView.verticalHeader().hide()
        self.moviesTableView.setStyleSheet(f"background: {self.bgColorC};"
                                           f"alternate-background-color: {self.bgColorD};")
        self.moviesTableView.setAlternatingRowColors(True)
        self.moviesTableView.setShowGrid(False)

        # Right click header menu
        hh = self.moviesTableView.horizontalHeader()
        hh.setStyleSheet(f"background: {self.bgColorB};"
                         f"border-radius: 0px;")
        hh.setSectionsMovable(True)
        hh.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        hh.customContextMenuRequested[QtCore.QPoint].connect(
            lambda: self.headerRightMenuShow(QtCore.QPoint,
                                             self.moviesTableView,
                                             self.moviesTableColumnsVisible,
                                             self.moviesTableModel))

        # Right click menu
        self.moviesTableView.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.moviesTableView.customContextMenuRequested[QtCore.QPoint].connect(self.moviesTableRightMenuShow)
        moviesTableViewVLayout.addWidget(self.moviesTableView)

    def initUIMovieSection(self):
        self.movieSectionWidget = QtWidgets.QFrame()
        self.movieSectionWidget.setFrameShape(QtWidgets.QFrame.Panel | QtWidgets.QFrame.Sunken)
        self.movieSectionWidget.setLineWidth(5)
        self.movieSectionWidget.setStyleSheet(f"background: {self.bgColorB};"
                                              f"border-radius: 10px;")
        if not self.showMovieSection:
            self.movieSectionWidget.hide()

        movieSectionVLayout = QtWidgets.QVBoxLayout()
        self.movieSectionWidget.setLayout(movieSectionVLayout)

        # Title
        self.titleLabel = QtWidgets.QLabel()
        self.titleLabel.setStyleSheet(f"background: {self.bgColorC};"
                                      f"font-size: {self.fontSize * 2}px;")
        self.titleLabel.setWordWrap(True)
        self.titleLabel.setAlignment(QtCore.Qt.AlignHCenter | QtCore.Qt.AlignTop)
        #self.titleLabel.setSizePolicy(QtWidgets.QSizePolicy.MinimumExpanding, QtWidgets.QSizePolicy.Fixed)
        movieSectionVLayout.addWidget(self.titleLabel)

        # Cover and Summary V Splitter
        self.coverSummaryVSplitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        movieSectionVLayout.addWidget(self.coverSummaryVSplitter)
        self.coverSummaryVSplitter.setHandleWidth(20)
        self.coverSummaryVSplitter.splitterMoved.connect(self.resizeCoverFile)

        # Cover and Movie Info H Splitter
        self.coverInfoHSplitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)

        self.coverSummaryVSplitter.addWidget(self.coverInfoHSplitter)

        # Movie Info
        self.movieInfoWidget = QtWidgets.QWidget()
        self.coverInfoHSplitter.addWidget(self.movieInfoWidget)
        self.coverInfoHSplitter.splitterMoved.connect(self.resizeCoverFile)
        movieInfoVLayout = QtWidgets.QVBoxLayout()
        self.movieInfoWidget.setLayout(movieInfoVLayout)
        self.movieInfoListView = MovieInfoListView()
        self.movieInfoListView.wheelSpun.connect(self.changeFontSize)
        self.movieInfoListView.setStyleSheet(f"background: {self.bgColorC};")
        self.movieInfoListView.itemSelectionChanged.connect(self.movieInfoSelectionChanged)
        self.movieInfoListView.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.movieInfoListView.customContextMenuRequested[QtCore.QPoint].connect(self.movieInfoRightMenu)
        movieInfoVLayout.addWidget(self.movieInfoListView)
        if not self.showMovieInfo:
            self.movieInfoWidget.hide()

        # Cover / GL Tabs
        self.coverTabWidget = QtWidgets.QTabWidget()
        self.coverInfoHSplitter.addWidget(self.coverTabWidget)

        # Cover
        self.coverTab = QtWidgets.QWidget()
        self.movieCover = MovieCover()
        self.initUICover()
        if not self.showCover:
            self.coverTab.hide()
        self.coverTabWidget.addTab(self.coverTab, "Cover")

        # Cover GL
        #coverGLTab = QtWidgets.QWidget()
        #coverGLTab.setLayout(QtWidgets.QVBoxLayout())
        #self.coverRowHistory = list()

        #self.randomizeCheckbox = QtWidgets.QCheckBox("Randomize")
        #coverGLTab.layout().addWidget(self.randomizeCheckbox)

        #self.openGlWidget = CoverGLWidget()
        #self.openGlWidget.emitCoverSignal.connect(self.coverChanged)
        #self.openGlWidget.showRowSignal.connect(self.showRow)
        #coverGLTab.layout().addWidget(self.openGlWidget)
        #self.coverTabWidget.addTab(coverGLTab, "Cover GL")

        sizes = [int(x) for x in self.settings.value('coverInfoHSplitterSizes', [200, 600], type=list)]
        self.coverInfoHSplitter.setSizes(sizes)

        # Summary
        self.summary = QtWidgets.QTextBrowser()
        self.summary.setStyleSheet(f"background-color: {self.bgColorC};")
        self.coverSummaryVSplitter.addWidget(self.summary)
        if not self.showSummary:
            self.summary.hide()

        sizes = [int(x) for x in self.settings.value('coverSummaryVSplitterSizes', [600, 200], type=list)]
        self.coverSummaryVSplitter.setSizes(sizes)

    def initUICover(self):
        self.coverTab.setStyleSheet(f"background-color: {self.bgColorC};")
        movieVLayout = QtWidgets.QVBoxLayout()
        self.coverTab.setLayout(movieVLayout)
        self.movieCover.setScaledContents(False)
        self.movieCover.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Ignored)
        self.movieCover.setStyleSheet(f"background-color: {self.bgColorC};")
        self.movieCover.doubleClicked.connect(lambda: self.playMovie(self.moviesTableView, self.moviesTableProxyModel))
        self.movieCover.wheelSpun.connect(self.changeFontSize)

        movieVLayout.addWidget(self.movieCover)

    def refreshTable(self,
                     smdbFile,
                     tableView,
                     columnsToShow,
                     columnWidths,
                     sortColumn,
                     forceScan=False,
                     neverScan=True,
                     modifiedSince=None,
                     sortAscending=True,
                     writeToLog=False,
                     proxyModelClass=None):

        smdbData = dict()
        read_time = None
        # Support binary MessagePack file beside JSON for faster IO
        mpk_path = os.path.splitext(smdbFile)[0] + ".mpk"
        if os.path.exists(smdbFile) or os.path.exists(mpk_path):
            t0 = time.perf_counter()
            smdbData = readSmdbFile(smdbFile)
            read_time = time.perf_counter() - t0
            # Ensure new fields exist for backward compatibility with older SMDB files
            if smdbData:
                smdbData.setdefault('writers', {})
                smdbData.setdefault('producers', {})
                smdbData.setdefault('composers', {})
            # Capture and log read time for the main movies SMDB at startup
            try:
                if smdbFile == self.moviesSmdbFile and not getattr(self, "_readMoviesSmdbLogged", False):
                    self._lastMoviesSmdbReadSeconds = read_time
                    if writeToLog:
                        try:
                            fmt = get_last_smdb_read_format()
                        except Exception:
                            fmt = None
                        fmt_text = f" ({fmt})" if fmt else ""
                        self.output(f"Read SMDB{fmt_text} in {read_time:.3f}s")
                    self._readMoviesSmdbLogged = True
            except Exception:
                pass
        else:
            forceScan = False

        moviesFolders = [self.moviesFolder]
        moviesFolders += self.additionalMoviesFolders
        start_time = time.monotonic()

        def format_eta(seconds):
            seconds = max(0, int(round(seconds)))
            hours, remainder = divmod(seconds, 3600)
            minutes, secs = divmod(remainder, 60)
            if hours:
                return f"{hours:d}:{minutes:02d}:{secs:02d}"
            return f"{minutes:02d}:{secs:02d}"

        def progress_callback(current, total):
            QtCore.QCoreApplication.processEvents()
            if self.isCanceled:
                raise OperationCanceledError()
            original_total = total
            safe_total = max(original_total, 1)
            current_value = min(current, safe_total)
            self.progressBar.setMaximum(safe_total)
            self.progressBar.setValue(current_value)
            display_total = original_total if original_total else 0
            display_current = min(current, display_total) if display_total else 0
            elapsed = time.monotonic() - start_time
            eta_seconds = None
            if original_total and original_total > 0:
                processed = min(current + 1, original_total)
                if processed > 0:
                    remaining = max(original_total - processed, 0)
                    if remaining == 0:
                        eta_seconds = 0
                    elif elapsed > 0:
                        eta_seconds = remaining * (elapsed / processed)
            if eta_seconds is None:
                eta_text = "estimating..."
            else:
                eta_text = f"{format_eta(eta_seconds)} remaining"
            self.statusBar().showMessage(f"{display_current}/{display_total} ({eta_text})")

        t0 = time.perf_counter()
        model = MoviesTableModel(smdbData,
                                 moviesFolders,
                                 forceScan,
                                 neverScan,
                                 progress_callback if (forceScan or modifiedSince is not None) else None,
                                 modifiedSince=modifiedSince)
        if writeToLog:
            create_model_time = time.perf_counter() - t0
            self.output(f"Created MoviesTableModel in {create_model_time:.3f}s")


        # If there is no smdb file and neverScan is False (as it
        # is for the main movie list) then write a new smdb file
        if not os.path.exists(smdbFile) and not neverScan:
            smdbData = self.writeSmdbFile(smdbFile,
                                          model,
                                          titlesOnly=False)

        # Use custom proxy model class if provided, otherwise use default
        if proxyModelClass is not None:
            proxyModel = proxyModelClass()
        else:
            # Use custom MovieFilterProxyModel for the main movies table
            if tableView == self.moviesTableView:
                proxyModel = MovieFilterProxyModel()
            else:
                proxyModel = QtCore.QSortFilterProxyModel()
        proxyModel.setSourceModel(model)
        tableView.setModel(proxyModel)


        tableView.selectionModel().selectionChanged.connect(
            lambda: self.tableSelectionChanged(tableView,
                                               model,
                                               proxyModel))

        # Not sure why this is needed but if we don't
        # disconnect before reconnecting then multiple
        # movies play when a movie is double clicked.
        # Also not sure why an exception is needed but
        # it might be when no connection exists already.
        try:
            tableView.doubleClicked.disconnect()
        except TypeError:
            pass

        tableView.doubleClicked.connect(
            lambda: self.playMovie(tableView,
                                   proxyModel))

        proxyModel.setDynamicSortFilter(False)
        tableView.setWordWrap(False)

        columnsVisible = []
        for c in Columns:
            index = c.value
            if isinstance(columnWidths, (list, tuple)) and index < len(columnWidths):
                tableView.setColumnWidth(index, int(columnWidths[index]))
            else:
                tableView.setColumnWidth(index, defaultColumnWidths[index])
            if index not in columnsToShow:
                tableView.hideColumn(index)
                columnsVisible.append(False)
            else:
                tableView.showColumn(index)
                columnsVisible.append(True)

        # TODO this is only for the watchlist
        tableView.horizontalHeader().moveSection(Columns.Rank.value, 0)

        tableView.verticalHeader().setMinimumSectionSize(10)
        if Columns.Cover.value in columnsToShow:
            tableView.verticalHeader().setDefaultSectionSize(self.rowHeightWithCover)
            tableView.setVerticalScrollMode(QtWidgets.QAbstractItemView.ScrollPerPixel)
            tableView.verticalScrollBar().setSingleStep(10)
        else:
            tableView.verticalHeader().setDefaultSectionSize(self.rowHeightWithoutCover)
            tableView.setVerticalScrollMode(QtWidgets.QAbstractItemView.ScrollPerItem)
            tableView.verticalScrollBar().setSingleStep(5)

        refresh_table_remaining_time = time.perf_counter() - t0
        return smdbData, model, proxyModel, columnsVisible, smdbData

    def refreshMoviesList(self, forceScan=False, writeToLog=False, modifiedSince=None):
        if forceScan or (modifiedSince is not None):
            self.isCanceled = False
            self.progressBar.setValue(0)
            rescan_start = time.monotonic()
        else:
            rescan_start = None

        try:
            (self.moviesSmdbData,
             self.moviesTableModel,
             self.moviesTableProxyModel,
             self.moviesTableColumnsVisible,
             self.moviesSmdbData) = self.refreshTable(self.moviesSmdbFile,
                                                      self.moviesTableView,
                                                      self.moviesTableColumns,
                                                      self.moviesTableColumnWidths,
                                                      Columns.Year.value,
                                                      forceScan,
                                                      neverScan=True,
                                                      modifiedSince=modifiedSince,
                                                      writeToLog=writeToLog)
        except OperationCanceledError:
            self.statusBar().showMessage("Cancelled")
            self.output("Cancelled")
            self.progressBar.setValue(0)
            self.isCanceled = False
            return

        if forceScan or (modifiedSince is not None):
            self.progressBar.setValue(0)
            total_seconds = time.monotonic() - rescan_start if rescan_start is not None else 0
            duration = max(0, int(round(total_seconds)))
            minutes, secs = divmod(duration, 60)
            hours, minutes = divmod(minutes, 60)
            if hours:
                duration_text = f"{hours:d}:{minutes:02d}:{secs:02d}"
            else:
                duration_text = f"{minutes:02d}:{secs:02d}"
            self.output(f"Rescan completed in {duration_text}")
        self.isCanceled = False

        self.numVisibleMovies = self.moviesTableProxyModel.rowCount()
        self.showMoviesTableSelectionStatus()
        self.pickRandomMovie()

    def refreshWatchList(self):
        """Delegate to WatchListWidget."""
        result = self.watchListWidget.refresh()
        # Update references
        if result:
            (self.watchListSmdbData,
             self.watchListTableModel,
             self.watchListTableProxyModel,
             self.watchListColumnsVisible,
             smdbData) = result

    def refreshHistoryList(self):
        """Delegate to HistoryWidget."""
        result = self.historyListWidget.refresh()
        # Update references
        if result:
            (self.historyListSmdbData,
             self.historyListTableModel,
             self.historyListTableProxyModel,
             self.historyListColumnsVisible,
             smdbData) = result

    def refreshBackupList(self):
        """Delegate to BackupWidget."""
        result = self.backupListWidget.refresh()
        # Update references
        if result:
            (self.backupListSmdbData,
             self.backupListTableModel,
             self.backupListTableProxyModel,
             self.backupListColumnsVisible,
             smdbData) = result
        return result

    def preferences(self):
        pass

    def rescanModifiedSince(self):
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Select cutoff date")
        layout = QtWidgets.QVBoxLayout(dialog)
        calendar = QtWidgets.QCalendarWidget(dialog)
        calendar.setGridVisible(True)
        layout.addWidget(calendar)
        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel,
            parent=dialog
        )
        layout.addWidget(buttons)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            qdate = calendar.selectedDate()
            selected_dt = datetime.datetime(qdate.year(), qdate.month(), qdate.day())
            self.refreshMoviesList(modifiedSince=selected_dt, writeToLog=True)

    def restoreDefaultWindows(self):
        self.setGeometry(QtCore.QRect(50, 50, 1820, 900))
        self.mainHSplitter.setSizes([270, 750, 800])
        self.coverInfoHSplitter.setSizes([200, 600])
        self.coverSummaryVSplitter.setSizes([600, 200])
        self.moviesWatchListBackupVSplitter.setSizes([500, 200, 100, 100])
        self.showPrimaryFilter = True
        self.showSecondaryFilter = True
        self.primaryFilterWidget.show()
        self.secondaryFilterWidget.show()
        self.showMoviesTable = True
        self.moviesTableWidget.show()
        self.showWatchList = False
        self.watchListWidget.hide()
        self.showBackupList = False
        self.backupListWidget.hide()
        self.showMovieSection = True
        self.movieSectionWidget.show()
        self.showMovieInfo = True
        self.movieInfoWidget.show()
        self.showCover = True
        self.coverTab.show()
        self.showSummary = True
        self.summary.show()
        self.moviesTableColumns = self.moviesTableDefaultColumns
        self.moviesTableColumnWidths = defaultColumnWidths
        self.refreshMoviesList()
        self.watchListWidget.listColumns = self.watchListWidget.listDefaultColumns
        self.watchListWidget.listColumnWidths = defaultColumnWidths
        self.refreshWatchList()
        self.historyListWidget.listColumns = self.historyListWidget.listDefaultColumns
        self.historyListWidget.listColumnWidths = defaultColumnWidths
        self.refreshHistoryList()
        self.backupListWidget.listColumns = self.backupListWidget.listDefaultColumns
        self.backupListWidget.listColumnWidths = defaultColumnWidths
        self.refreshBackupList()
        self.setFontSize(self.defaultFontSize)
        self.primaryFilterWidget.filterTable.setColumnWidth(0, self.primaryFilterColumn0WidthDefault)
        self.primaryFilterWidget.filterTable.setColumnWidth(1, self.primaryFilterColumn1WidthDefault)
        self.secondaryFilterWidget.filterTable.setColumnWidth(0, self.secondaryFilterColumn0WidthDefault)
        self.secondaryFilterWidget.filterTable.setColumnWidth(1, self.secondaryFilterColumn1WidthDefault)

    def conformMovies(self):
        browseDir = str(Path.home())
        if os.path.exists('E:/MoviesToOrganize'):
            browseDir = 'E:/MoviesToOrganize'
        elif os.path.exists('%s/Desktop' % browseDir):
            browseDir = '%s/Desktop' % browseDir
        else:
            return
        moviesFolder = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            "Select Movies Directory",
            browseDir,
            QtWidgets.QFileDialog.ShowDirsOnly |
            QtWidgets.QFileDialog.DontResolveSymlinks)
        if not os.path.exists(moviesFolder):
            return

        foldersRenamed = 0
        foldersRejected = 0
        renamedFolders = set()
        rejectedFolders = set()
        with os.scandir(moviesFolder) as files:
            for f in files:
                folderName = f.name
                folderPath = f.path
                parentPath = os.path.dirname(f.path)
                if f.is_dir() and (fnmatch.fnmatch(f, '*(*)') or fnmatch.fnmatch(f, '*(*)*')):
                    foldersRenamed += 1
                    tokens = folderName.split()
                    if len(tokens) == 1:
                        rejectedFolders.add(folderPath)
                        foldersRejected += 1
                        continue
                    newFolderName = ''
                    end = False
                    for t in tokens:
                        if end:
                            break
                        if t[0] == '(' and t[-1] == ')' and len(t) == 6:
                            end = True
                        else:
                            t = t.lower().capitalize()
                            t = t.replace(',', '')
                            t = t.replace('\'', '')
                            t = t.replace('.', '')

                        newFolderName += t

                    if newFolderName == folderName:
                        self.output(f"Skipping. New name same as old name: {newFolderName}")
                        continue
                    newFolderPath = os.path.join(parentPath, newFolderName)
                    if os.path.exists(newFolderPath) or newFolderName in renamedFolders:
                        newFolderName = newFolderName + '2'
                        newFolderPath = newFolderPath + '2'
                        self.output(f"Duplicate folder renamed to: {newFolderName}")
                    renamedFolders.add(newFolderName)
                    self.output(f"Renaming folder: \"{folderPath}\"    to    \"{newFolderPath}\"")

                    with os.scandir(f.path) as childFiles:
                        for c in childFiles:
                            fileName, extension = os.path.splitext(c.name)
                            if extension == '.mp4' or extension == '.srt' or extension == '.mkv':
                                newFilePath = os.path.join(folderPath, newFolderName + extension)
                                if c.path != newFilePath:
                                    self.output(f"\tRenaming file: {c.path} to {newFilePath}")
                                    try:
                                        os.rename(c.path, newFilePath)
                                    except FileExistsError:
                                        self.output(f"Can't Rename file {c.path, newFilePath}")
                                        continue
                            elif extension == '.jpg':
                                try:
                                    self.output(f"\tRemoving file: {c.path}")
                                    os.remove(c.path)
                                except:
                                    self.output(f"\tCould not remove file: {c.path}")
                            else:
                                self.output(f"\tNot touching file: {c.path}")

                    try:
                        os.rename(folderPath, newFolderPath)
                    except FileExistsError:
                        self.output(f"Can't Rename folder {folderPath, newFolderPath}")
                        continue
                else:
                    rejectedFolders.add(folderPath)
                    foldersRejected += 1
        for f in rejectedFolders:
            self.output(f"Rejected folder: {f}")
        self.output(f"foldersRenamed={foldersRenamed} foldersRejected={foldersRejected}")

    def setTitleBar(self):
        additionalMoviesFoldersString = ""
        if self.additionalMoviesFolders:
            if len(self.additionalMoviesFolders) == 1:
                additionalMoviesFoldersString += '%s' % self.additionalMoviesFolders[0]
            else:
                for af in self.additionalMoviesFolders:
                    additionalMoviesFoldersString += '%s, ' % af
            self.setWindowTitle("SMDB - Primary Movies Folder: %s  Additional Movies Folders: (%s)"
                                % (self.moviesFolder, additionalMoviesFoldersString))
        else:
            self.setWindowTitle("SMDB - Primary Movies Folder = %s" % (self.moviesFolder))

    def setCollectionsFolder(self):
        browseDir = str(Path.home())
        if os.path.exists('%s/Desktop' % browseDir):
            browseDir = '%s/Desktop' % browseDir
        collectionsFolder = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            "Select Collections Directory",
            browseDir,
            QtWidgets.QFileDialog.ShowDirsOnly |
            QtWidgets.QFileDialog.DontResolveSymlinks)
        if os.path.exists(collectionsFolder):
            self.collectionsFolder = collectionsFolder
            self.settings.setValue('collections_folder', self.collectionsFolder)
            self.setTitleBar()
            self.output("Saved: collectionsFolder = %s" % self.collectionsFolder)
            self.refreshCollectionsList()

    def refreshCollectionsList(self):
        if os.path.exists(self.collectionsFolder):
            self.collections = [f"{self.collectionsFolder}/{c}" for c in os.listdir(self.collectionsFolder) if c.endswith('.txt')]

    def setPrimaryMoviesFolder(self):
        browseDir = str(Path.home())
        if os.path.exists('%s/Desktop' % browseDir):
            browseDir = '%s/Desktop' % browseDir
        moviesFolder = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            "Select Movies Directory",
            browseDir,
            QtWidgets.QFileDialog.ShowDirsOnly |
            QtWidgets.QFileDialog.DontResolveSymlinks)
        if os.path.exists(moviesFolder):
            self.moviesFolder = moviesFolder
            self.settings.setValue('movies_folder', self.moviesFolder)
            self.setTitleBar()
            self.output("Saved: moviesFolder = %s" % self.moviesFolder)
            self.moviesSmdbFile = os.path.join(self.moviesFolder, "smdb_data.json")
            readSmdbFile(self.moviesSmdbFile)
            self.refreshMoviesList()

    def browseAdditionalMoviesFolder(self):
        browseDir = str(Path.home())
        if os.path.exists('%s/Desktop' % browseDir):
            browseDir = '%s/Desktop' % browseDir
        additionalMoviesFolder = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            "Select Movies Directory",
            browseDir,
            QtWidgets.QFileDialog.ShowDirsOnly |
            QtWidgets.QFileDialog.DontResolveSymlinks)
        if os.path.exists(additionalMoviesFolder):
            self.additionalMoviesFolders.append(additionalMoviesFolder)
            self.setTitleBar()
            self.settings.setValue('additional_movies_folders', self.additionalMoviesFolders)
            self.output("Saved: additionalMoviesFolder = %s" % additionalMoviesFolder)

    def clearAdditionalMoviesFolders(self):
        self.additionalMoviesFolders = []
        self.settings.remove('additional_movies_folders')
        self.setTitleBar()

    def clearPrimaryMoviesFolder(self):
        self.moviesFolder = ""
        self.settings.remove('movies_folder')
        self.moviesFolder = "No movies folder set.  Use the \"File->Set movies folder\" menu to set it."
        self.setTitleBar()
        self.refreshMoviesList()



    def findMovieInMovie(self):
        numItems = self.moviesTableModel.rowCount()
        self.progressBar.setMaximum(numItems)
        progress = 0
        self.isCanceled = False

        self.moviesTableModel.aboutToChangeLayout()
        titleYearSet = set()
        duplicates = set()
        for row in range(numItems):
            QtCore.QCoreApplication.processEvents()
            if self.isCanceled:
                self.statusBar().showMessage('Cancelled')
                self.isCanceled = False
                self.progressBar.setValue(0)
                self.movieTableModel.changedLayout()
                return

            progress += 1
            self.progressBar.setValue(progress)

            modelIndex = self.moviesTableModel.index(row, 0)
            movieFolderName = self.moviesTableModel.getFolderName(modelIndex.row())
            moviePath = self.moviesTableModel.getPath(modelIndex.row())
            moviePath = self.findMovie(moviePath, movieFolderName)
            if not moviePath or not os.path.exists(moviePath):
                continue
            with os.scandir(moviePath) as files:
                for f in files:
                    if f.is_dir() and fnmatch.fnmatch(f, '*(*)'):
                        self.output(f"Movie: {moviePath} contains other movie: {f.name}")

        self.moviesTableModel.changedLayout()
        self.progressBar.setValue(0)

    def markAsKnownDuplicate(self):
        """Mark selected movie(s) as known duplicates"""
        selectedRows = self.moviesTableView.selectionModel().selectedRows()
        if not selectedRows:
            return
        
        for proxyIndex in selectedRows:
            sourceIndex = self.moviesTableProxyModel.mapToSource(proxyIndex)
            sourceRow = sourceIndex.row()
            moviePath = self.moviesTableModel.getPath(sourceRow)
            folderName = self.moviesTableModel.getFolderName(sourceRow)
            
            moviePath = self.findMovie(moviePath, folderName)
            if not moviePath:
                continue
            
            jsonFile = os.path.join(moviePath, f'{folderName}.json')
            if os.path.exists(jsonFile):
                try:
                    with open(jsonFile, 'r', encoding='utf-8') as f:
                        jsonData = ujson.load(f)
                    
                    jsonData['known duplicate'] = True
                    
                    with open(jsonFile, 'w', encoding='utf-8') as f:
                        ujson.dump(jsonData, f, indent=4)
                    
                    self.output(f"Marked as known duplicate: {folderName}")
                except Exception as e:
                    self.output(f"Error marking {folderName} as known duplicate: {str(e)}")
        
        self.output(f"Marked {len(selectedRows)} movie(s) as known duplicate(s)")
    
    def unmarkAsKnownDuplicate(self):
        """Unmark selected movie(s) as known duplicates"""
        selectedRows = self.moviesTableView.selectionModel().selectedRows()
        if not selectedRows:
            return
        
        for proxyIndex in selectedRows:
            sourceIndex = self.moviesTableProxyModel.mapToSource(proxyIndex)
            sourceRow = sourceIndex.row()
            moviePath = self.moviesTableModel.getPath(sourceRow)
            folderName = self.moviesTableModel.getFolderName(sourceRow)
            
            moviePath = self.findMovie(moviePath, folderName)
            if not moviePath:
                continue
            
            jsonFile = os.path.join(moviePath, f'{folderName}.json')
            if os.path.exists(jsonFile):
                try:
                    with open(jsonFile, 'r', encoding='utf-8') as f:
                        jsonData = ujson.load(f)
                    
                    if 'known duplicate' in jsonData:
                        del jsonData['known duplicate']
                    
                    with open(jsonFile, 'w', encoding='utf-8') as f:
                        ujson.dump(jsonData, f, indent=4)
                    
                    self.output(f"Unmarked as known duplicate: {folderName}")
                except Exception as e:
                    self.output(f"Error unmarking {folderName} as known duplicate: {str(e)}")
        
        self.output(f"Unmarked {len(selectedRows)} movie(s) as known duplicate(s)")

    def findDuplicates(self):
        import time
        startTime = time.time()
        
        numItems = self.moviesTableModel.rowCount()
        self.progressBar.setMaximum(numItems)
        progress = 0
        self.isCanceled = False

        self.moviesTableModel.aboutToChangeLayout()
        titleYearSet = set()
        duplicates = set()
        # Track all instances of each title/year with their row, path, and size
        titleYearInstances = collections.defaultdict(list)
        
        for row in range(numItems):
            if row % 10 == 0:  # Reduce processEvents calls
                QtCore.QCoreApplication.processEvents()
            if self.isCanceled:
                self.statusBar().showMessage('Cancelled')
                self.isCanceled = False
                self.progressBar.setValue(0)
                self.moviesTableModel.changedLayout()
                return

            progress += 1
            
            # Update progress bar and status less frequently
            if progress % 50 == 0 or progress == numItems:
                self.progressBar.setValue(progress)
                elapsedTime = time.time() - startTime
                itemsPerSecond = progress / elapsedTime if elapsedTime > 0 else 0
                remainingItems = numItems - progress
                eta = remainingItems / itemsPerSecond if itemsPerSecond > 0 else 0
                self.statusBar().showMessage(f'Finding duplicates: {progress}/{numItems} - ETA: {int(eta)}s')

            modelIndex = self.moviesTableModel.index(row, 0)
            title = self.moviesTableModel.getTitle(modelIndex.row())
            year = self.moviesTableModel.getYear(modelIndex.row())
            folderName = self.moviesTableModel.getFolderName(modelIndex.row())
            moviePath = self.moviesTableModel.getPath(modelIndex.row())
            
            # Find the actual movie path
            moviePath = self.findMovie(moviePath, folderName)
            
            # Check if this is a known duplicate
            isKnownDuplicate = False
            if moviePath and os.path.exists(moviePath):
                jsonFile = os.path.join(moviePath, f"{folderName}.json")
                if os.path.exists(jsonFile):
                    try:
                        with open(jsonFile, 'r', encoding='utf-8') as f:
                            jsonData = ujson.load(f)
                            isKnownDuplicate = jsonData.get('known duplicate', False)
                    except Exception:
                        pass
            
            # Convert year to int for consistent comparison
            try:
                year_int = int(year) if year else 0
            except (ValueError, TypeError):
                year_int = 0
            
            titleYear = (title.lower(), year_int)
            
            # Store instance information
            titleYearInstances[titleYear].append({
                'row': row,
                'path': moviePath,
                'folderName': folderName,
                'knownDuplicate': isKnownDuplicate
            })
            
            # Only mark as duplicate if not a known duplicate
            if titleYear in titleYearSet:
                if not isKnownDuplicate:
                    self.moviesTableModel.setDuplicate(modelIndex, 'Yes')
                    duplicates.add(titleYear)
                else:
                    self.moviesTableModel.setDuplicate(modelIndex, 'No')
            else:
                self.moviesTableModel.setDuplicate(modelIndex, 'No')
            titleYearSet.add(titleYear)

        for row in range(numItems):
            modelIndex = self.moviesTableModel.index(row, 0)
            title = self.moviesTableModel.getTitle(modelIndex.row())
            year = self.moviesTableModel.getYear(modelIndex.row())
            folderName = self.moviesTableModel.getFolderName(modelIndex.row())
            moviePath = self.moviesTableModel.getPath(modelIndex.row())
            
            # Find the actual movie path and check known duplicate status
            moviePath = self.findMovie(moviePath, folderName)
            isKnownDuplicate = False
            if moviePath and os.path.exists(moviePath):
                jsonFile = os.path.join(moviePath, f"{folderName}.json")
                if os.path.exists(jsonFile):
                    try:
                        with open(jsonFile, 'r', encoding='utf-8') as f:
                            jsonData = ujson.load(f)
                            isKnownDuplicate = jsonData.get('known duplicate', False)
                    except Exception:
                        pass
            
            # Convert year to int for consistent comparison
            try:
                year_int = int(year) if year else 0
            except (ValueError, TypeError):
                year_int = 0
            
            titleYear = (title.lower(), year_int)
            if titleYear in duplicates and not isKnownDuplicate:
                self.moviesTableModel.setDuplicate(modelIndex, 'Yes')

        self.moviesTableModel.changedLayout()
        
        # Filter to show only duplicates using the proxy model
        self.statusBar().showMessage('Filtering duplicates...')
        QtCore.QCoreApplication.processEvents()
        
        self.output(f"Total duplicate titleYear pairs found: {len(duplicates)}")
        self.output(f"Total titleYear instances tracked: {len(titleYearInstances)}")
        
        # Debug: show some examples
        duplicate_count = 0
        for titleYear, instances in titleYearInstances.items():
            if len(instances) >= 2:
                duplicate_count += 1
                if duplicate_count <= 3:  # Show first 3 examples
                    self.output(f"Duplicate: {titleYear[0]} ({titleYear[1]}) - {len(instances)} instances")
        
        # Build list of ALL instances of duplicate movies for the filter
        # This ensures both/all copies show up in the filtered view
        duplicate_movies = []
        for titleYear, instances in titleYearInstances.items():
            # Count non-known-duplicate instances
            non_known_instances = [inst for inst in instances if not inst.get('knownDuplicate', False)]
            
            # Only consider it a duplicate if there are 2+ non-known-duplicate copies
            if len(non_known_instances) >= 2:
                # Add all non-known-duplicate instances to the filter
                for instance in non_known_instances:
                    row = instance['row']
                    title = self.moviesTableModel.getTitle(row)
                    year = self.moviesTableModel.getYear(row)
                    try:
                        year_int = int(year) if year else 0
                    except (ValueError, TypeError):
                        year_int = 0
                    duplicate_movies.append((title, year_int))
        
        self.output(f"Found {len(duplicate_movies)} movie instances to show as duplicates")
        
        # Apply the filter using the proxy model
        self.moviesTableProxyModel.setMovieListFilter(duplicate_movies, mode='include')
        self.numVisibleMovies = self.moviesTableProxyModel.rowCount()
        self.output(f"Proxy model row count after filter: {self.numVisibleMovies}")
        self.showMoviesTableSelectionStatus()
        
        # Sort by Title after filtering duplicates
        self.statusBar().showMessage('Sorting duplicates by title...')
        QtCore.QCoreApplication.processEvents()
        self.moviesTableView.sortByColumn(Columns.Title.value, QtCore.Qt.AscendingOrder)
        
        # Scroll to the top of the table
        self.moviesTableView.scrollToTop()
        
        self.statusBar().showMessage('Duplicate search complete')
        self.progressBar.setValue(0)
        
        # Count known duplicates for later reporting
        knownDuplicateCount = sum(1 for instances in titleYearInstances.values() 
                                  for inst in instances if inst.get('knownDuplicate', False))
        
        # Now check for exact duplicates (same or very similar file sizes)
        exactDuplicateFolders = []
        sizeTolerance = 5 * 1024 * 1024  # 5 MB tolerance
        
        # Build ordered list of movie folders for priority determination
        orderedMovieFolders = []
        if self.moviesFolder and self.moviesFolder != "No movies folder set.  Use the \"File->Set movies folder\" menu to set it.":
            orderedMovieFolders.append(self.moviesFolder)
        if self.additionalMoviesFolders:
            orderedMovieFolders.extend(self.additionalMoviesFolders)
        
        def getFolderPriority(path):
            """Return priority index based on folder hierarchy (lower is better)"""
            if not path:
                return 999  # Invalid paths get lowest priority
            # Normalize paths for comparison (convert backslashes to forward slashes, handle case)
            normalized_path = os.path.normpath(path).replace('\\', '/').lower()
            
            # Find the best (longest) matching folder to avoid E:/Movies matching E:/Movies2
            best_match_idx = 999
            best_match_len = 0
            
            for idx, folder in enumerate(orderedMovieFolders):
                normalized_folder = os.path.normpath(folder).replace('\\', '/').lower()
                # Check if path starts with this folder, ensuring proper boundary
                # (either exact match or followed by a path separator)
                if (normalized_path == normalized_folder or 
                    normalized_path.startswith(normalized_folder + '/')):
                    # Use the longest matching folder (most specific)
                    if len(normalized_folder) > best_match_len:
                        best_match_idx = idx
                        best_match_len = len(normalized_folder)
            
            if best_match_idx != 999:
                return best_match_idx
            else:
                return 999  # Not in any known folder
        
        self.output(f"Primary movies folder: {self.moviesFolder}")
        if self.additionalMoviesFolders:
            for idx, folder in enumerate(self.additionalMoviesFolders):
                self.output(f"Additional movies folder {idx+1}: {folder}")
        
        self.output("Checking for exact duplicates (same file size)...")
        duplicateMessages = []
        for titleYear, instances in titleYearInstances.items():
            if len(instances) < 2:
                continue  # Skip if not a duplicate
            
            # Calculate sizes for all instances and check if they're known duplicates
            for instance in instances:
                if instance['path'] and os.path.exists(instance['path']):
                    instance['size'] = getFolderSize(instance['path'])
                    instance['priority'] = getFolderPriority(instance['path'])
                    
                    # Check if this is a known duplicate
                    jsonFile = os.path.join(instance['path'], f"{instance['folderName']}.json")
                    instance['knownDuplicate'] = False
                    if os.path.exists(jsonFile):
                        try:
                            with open(jsonFile, 'r', encoding='utf-8') as f:
                                jsonData = ujson.load(f)
                                instance['knownDuplicate'] = jsonData.get('known duplicate', False)
                        except Exception:
                            pass
                else:
                    instance['size'] = None
                    instance['priority'] = 999
                    instance['knownDuplicate'] = False
            
            # Filter out instances with no valid path/size
            validInstances = [inst for inst in instances if inst['size'] is not None]
            
            if len(validInstances) < 2:
                continue
            
            # Remove duplicate paths (same movie appearing multiple times due to indexing)
            seenPaths = set()
            uniqueInstances = []
            for inst in validInstances:
                if inst['path'] not in seenPaths:
                    seenPaths.add(inst['path'])
                    uniqueInstances.append(inst)
            
            validInstances = uniqueInstances
            
            if len(validInstances) < 2:
                continue
            
            # Sort by priority (primary folder first, then additional folders in order)
            validInstances.sort(key=lambda x: x['priority'])
            
            # Keep the first instance (highest priority) as the original
            original = validInstances[0]
            for duplicate in validInstances[1:]:
                # Skip if this duplicate is marked as a known duplicate
                if duplicate['knownDuplicate']:
                    continue
                    
                sizeDiff = abs(original['size'] - duplicate['size'])
                if sizeDiff <= sizeTolerance:
                    # This is an exact duplicate - format as one line
                    duplicateMsg = (f"Keep: {original['path']} | Delete: {duplicate['path']} | "
                                  f"Diff: {sizeDiff / (1024*1024):.2f} MB")
                    duplicateMessages.append(duplicateMsg)
                    
                    exactDuplicateFolders.append({
                        'path': duplicate['path'],
                        'row': duplicate['row'],
                        'title': titleYear[0],
                        'year': titleYear[1],
                        'size': duplicate['size'],
                        'originalSize': original['size'],
                        'sizeDiff': sizeDiff
                    })
        
        # Prompt user to delete exact duplicates if any were found
        if len(exactDuplicateFolders) > 0:
            totalSize = sum(dup['size'] for dup in exactDuplicateFolders)
            sizeGB = totalSize / (1024 * 1024 * 1024)
            
            # Create a custom dialog with scrollable list
            dialog = QtWidgets.QDialog(self)
            dialog.setWindowTitle('Delete Exact Duplicates')
            dialog.resize(900, 500)
            
            layout = QtWidgets.QVBoxLayout()
            
            # Header label
            headerLabel = QtWidgets.QLabel(
                f"Found {len(exactDuplicateFolders)} exact duplicate(s) "
                f"(same or very similar file size).\n"
                f"Total size to be freed: {sizeGB:.2f} GB\n"
            )
            layout.addWidget(headerLabel)
            
            # Scrollable text area with the list
            textEdit = QtWidgets.QPlainTextEdit()
            textEdit.setReadOnly(True)
            textEdit.setPlainText('\n'.join(duplicateMessages))
            textEdit.setStyleSheet("background-color: black; color: white;")
            layout.addWidget(textEdit)
            
            # Question label
            questionLabel = QtWidgets.QLabel("Delete these duplicate folders and keep the originals?")
            layout.addWidget(questionLabel)
            
            # Buttons
            buttonBox = QtWidgets.QDialogButtonBox(
                QtWidgets.QDialogButtonBox.Yes | QtWidgets.QDialogButtonBox.No
            )
            buttonBox.accepted.connect(dialog.accept)
            buttonBox.rejected.connect(dialog.reject)
            layout.addWidget(buttonBox)
            
            dialog.setLayout(layout)
            ret = dialog.exec_()
            
            if ret == QtWidgets.QDialog.Accepted:
                foldersToDelete = [dup['path'] for dup in exactDuplicateFolders]
                rowsToDelete = [dup['row'] for dup in exactDuplicateFolders]
                
                # Delete folders first
                for folder in foldersToDelete:
                    self.output(f'Deleting exact duplicate folder: {folder}')
                    try:
                        shutil.rmtree(folder,
                                    ignore_errors=False,
                                    onerror=handleRemoveReadonly)
                        self.output(f'Successfully deleted: {folder}')
                    except Exception as e:
                        self.output(f'Error deleting {folder}: {str(e)}')
                
                # Remove rows from model (delete from highest to lowest to avoid index shifting)
                self.moviesTableModel.aboutToChangeLayout()
                rowsToDelete.sort(reverse=True)
                for row in rowsToDelete:
                    self.moviesTableModel.removeMovie(row)
                self.moviesTableModel.changedLayout()
                
                self.output(f"Deleted {len(foldersToDelete)} exact duplicate folder(s) and removed their rows from the list")
                QtWidgets.QMessageBox.information(
                    self,
                    'Deletion Complete',
                    f'Successfully deleted {len(foldersToDelete)} exact duplicate folder(s).\n'
                    f'Freed approximately {sizeGB:.2f} GB of space.\n'
                    f'Removed {len(rowsToDelete)} row(s) from the list.\n\n'
                    f'Run "Find Duplicates" again to check for more duplicates.'
                )
            else:
                self.output("User cancelled deletion of exact duplicates")
        else:
            self.output("No exact duplicates found")
        
        # Count remaining duplicates that need attention (non-exact duplicates)
        remainingDuplicates = len(duplicates)
        if knownDuplicateCount > 0:
            # Subtract known duplicates from total
            remainingDuplicates = sum(1 for titleYear in duplicates 
                                     if not any(inst.get('knownDuplicate', False) 
                                               for inst in titleYearInstances.get(titleYear, [])))
        
        # Report summary
        if knownDuplicateCount > 0:
            self.output(f"Skipped {knownDuplicateCount} known duplicate(s)")
        
        if remainingDuplicates > 0:
            self.output(f"{remainingDuplicates} duplicate title(s) remaining that need attention")
        else:
            self.output("No remaining duplicates found")

    def cancelButtonClicked(self):
        self.isCanceled = True
        self.statusBar().showMessage('Cancelling...')

    def showMoviesTableSelectionStatus(self):
        numSelected = len(self.moviesTableView.selectionModel().selectedRows())
        self.statusBar().showMessage('%s/%s' % (numSelected, self.numVisibleMovies))

    def showRow(self, row):
        self.moviesTableView.selectRow(row)

    def coverChanged(self, direction):
        #if (len(self.moviesTableView.selectionModel().selectedRows()) > 0):
        #    currentRow = self.moviesTableView.selectionModel().selectedRows()[0].row()
        #else:
        #    currentRow = 0

        if len(self.coverRowHistory) > 0:
            currentRow = self.coverRowHistory[-1]
        else:
            currentRow = 0

        numRowsProxy = self.moviesTableProxyModel.rowCount()
        if self.randomizeCheckbox.isChecked():
            # All rows in proxy model are visible
            if numRowsProxy == 0:
                return
            randomRow = currentRow
            while randomRow == currentRow and numRowsProxy > 1:
                randomRow = random.randint(0, numRowsProxy - 1)
            #self.moviesTableView.selectRow(randomRow)
            self.emitCover(randomRow, direction)
        else:
            if direction == -1:
                if currentRow == numRowsProxy - 1:
                    currentRow = 0
                else:
                    currentRow += 1
            else:
                if currentRow == 0:
                    currentRow = numRowsProxy - 1
                else:
                    currentRow = max(0, currentRow - 1)

            #self.moviesTableView.selectRow(currentRow)
            self.emitCover(currentRow, direction)

    def emitCover(self, row, direction):
        self.coverRowHistory.append(row)
        #modelIndex = self.moviesTableView.selectionModel().selectedRows()[0]
        modelIndex = self.moviesTableProxyModel.index(row, 0)
        sourceIndex = self.moviesTableProxyModel.mapToSource(modelIndex)
        sourceRow = sourceIndex.row()
        moviePath = self.moviesTableModel.getPath(sourceRow)
        folderName = self.moviesTableModel.getFolderName(sourceRow)
        coverFile = os.path.join(moviePath, '%s.jpg' % folderName)
        if not os.path.exists(coverFile):
            coverFilePng = os.path.join(moviePath, '%s.png' % folderName)
            if os.path.exists(coverFilePng):
                coverFile = coverFilePng
        self.openGlWidget.emitCover(row, coverFile, direction)

    def tableSelectionChanged(self, table, model, proxyModel):
        # Block selection changes if cover flow is animating
        if hasattr(self, '_block_selection_change') and self._block_selection_change:
            return
            
        if self.modifySelectionHistory:
            selectedRows = [r.row() for r in self.moviesTableView.selectionModel().selectedRows()]
            if len(selectedRows) != 0:
                # Delete everything after the selectionHistoryIndex
                del self.selectionHistory[self.selectionHistoryIndex + 1:len(self.selectionHistory)]
                self.selectionHistory.append(selectedRows)
                self.selectionHistoryIndex = len(self.selectionHistory) - 1

        self.showMoviesTableSelectionStatus()
        numSelected = len(table.selectionModel().selectedRows())
        if numSelected == 1:
            modelIndex = table.selectionModel().selectedRows()[0]
            self.clickedTable(modelIndex,
                              model,
                              proxyModel)

    def clickedTable(self, modelIndex, model, proxyModel):
        sourceIndex = proxyModel.mapToSource(modelIndex)
        sourceRow = sourceIndex.row()
        
        # Store for CoverFlowGLWidget
        self.currentModel = model
        self.currentSourceRow = sourceRow
        
        title = model.getTitle(sourceRow)

        moviePath = model.getPath(sourceRow)
        folderName = model.getFolderName(sourceRow)
        # Use findMovie to get the actual path
        moviePath = self.findMovie(moviePath, folderName)
        if not moviePath:
            self.clearMovie()
            return
        year = model.getYear(sourceRow)
        jsonFile = os.path.join(moviePath, '%s.json' % folderName)
        coverFile = os.path.join(moviePath, '%s.jpg' % folderName)
        if not os.path.exists(coverFile):
            coverFilePng = os.path.join(moviePath, '%s.png' % folderName)
            if os.path.exists(coverFilePng):
                coverFile = coverFilePng

        self.titleLabel.setText('"%s" (%s)' % (title, year))
        
        # Load cover image once and share it
        coverImage = None
        if coverFile and os.path.exists(coverFile):
            coverImage = QtGui.QImage(coverFile)
        
        self.showCoverFile(coverFile, coverImage)

        # Update Cover Flow tab with selected movie cover
        if hasattr(self, 'coverFlowWidget'):
            # Set the model and current index - this will trigger animation if needed
            # Use proxy model if available to respect filters
            proxy_row = modelIndex.row()
            self.coverFlowWidget.setModelAndIndex(proxyModel, proxy_row, proxyModel, self.moviesTableView)
            # Only update the cover image if not animating
            if not getattr(self.coverFlowWidget, '_scrolling', False):
                if coverImage and not coverImage.isNull():
                    self.coverFlowWidget.set_cover_image_from_qimage(coverImage)
            else:
                # Store for later update when animation completes
                self.coverFlowWidget._pending_cover_qimage = coverImage

        jsonData = None
        if os.path.exists(jsonFile):
            with open(jsonFile) as f:
                try:
                    jsonData = ujson.load(f)
                except UnicodeDecodeError:
                    self.output("Error reading %s" % jsonFile)
        else:
            self.summary.clear()

        self.summaryShow(jsonData)
        self.movieInfoRefresh(jsonData)

    def moviesTableBack(self):
        if self.selectionHistoryIndex != 0:
            self.moviesTableView.clearSelection()
            self.selectionHistoryIndex -= 1
            selectedRows = self.selectionHistory[self.selectionHistoryIndex]
            self.modifySelectionHistory = False
            indexes = [self.moviesTableProxyModel.index(r, 0) for r in selectedRows]
            mode = QtCore.QItemSelectionModel.Select | QtCore.QItemSelectionModel.Rows
            self.moviesTableView.selectRow(selectedRows[0])
            [self.moviesTableView.selectionModel().select(i, mode) for i in indexes]
            self.modifySelectionHistory = True

    def moviesTableForward(self):
        if self.selectionHistoryIndex != (len(self.selectionHistory) - 1):
            self.moviesTableView.clearSelection()
            self.selectionHistoryIndex += 1
            selectedRows = self.selectionHistory[self.selectionHistoryIndex]
            self.modifySelectionHistory = False
            indexes = [self.moviesTableProxyModel.index(r, 0) for r in selectedRows]
            mode = QtCore.QItemSelectionModel.Select | QtCore.QItemSelectionModel.Rows
            self.moviesTableView.selectRow(selectedRows[0])
            [self.moviesTableView.selectionModel().select(i, mode) for i in indexes]
            self.modifySelectionHistory = True

    def pickRandomMovie(self):
        numRowsProxy = self.moviesTableProxyModel.rowCount()
        if numRowsProxy == 0:
            return
        randomRow = random.randint(0, numRowsProxy - 1)
        self.moviesTableView.selectRow(randomRow)

    def showAllMoviesTableView(self):
        self.moviesTableTitleFilterBox.clear()
        # Clear the movie list filter to show all movies
        self.moviesTableProxyModel.clearMovieListFilter()
        self.numVisibleMovies = self.moviesTableProxyModel.rowCount()
        self.showMoviesTableSelectionStatus()
        self.moviesTableProxyModel.sort(0)
        
        # Update to first row and trigger cover flow update
        if self.moviesTableProxyModel.rowCount() > 0:
            # Clear selection first to ensure selection change is triggered
            self.moviesTableView.clearSelection()
            # Select first row which will trigger tableSelectionChanged -> clickedTable
            self.moviesTableView.selectRow(0)
            # Also directly update cover flow to ensure it updates
            modelIndex = self.moviesTableProxyModel.index(0, 0)
            self.clickedTable(modelIndex, self.moviesTableModel, self.moviesTableProxyModel)

    def searchPlots(self):
        self.moviesTableTitleFilterBox.clear()

        searchText = self.moviesTableSearchPlotsBox.text()
        if len(searchText) == 0:
            return

        # Initialize for fallback
        searchTextLower = searchText.lower()
        search_regex = None
        
        # Parse quoted phrases and regular words
        import shlex
        
        # Split by | first to handle OR groups
        or_groups = searchText.split('|')
        all_group_patterns = []
        
        for group in or_groups:
            group = group.strip()
            if not group:
                continue
                
            try:
                # shlex.split handles quoted strings properly
                tokens = shlex.split(group)
            except ValueError:
                # If shlex fails (mismatched quotes), fall back to simple split
                tokens = group.split()
            
            # Check if we have wildcards in this group
            has_wildcards = any('*' in t or '?' in t or '[' in t for t in tokens)
            
            if has_wildcards:
                # If any token has wildcards, treat the whole group as a wildcard pattern
                import fnmatch
                regex_pattern = fnmatch.translate(group)
                regex_pattern = regex_pattern.replace(r'\Z', '')
                if regex_pattern.startswith('(?:'):
                    regex_pattern = regex_pattern[4:]
                all_group_patterns.append(regex_pattern)
            elif len(tokens) > 0:
                # Build regex pattern from tokens
                # Each token becomes a word-boundary-wrapped pattern
                patterns = []
                for token in tokens:
                    # Escape special regex characters and add word boundaries
                    escaped = re.escape(token)
                    patterns.append(r'\b' + escaped + r'\b')
                
                # For AND logic, we need to check each pattern separately
                # Store as tuple to handle differently than OR groups
                all_group_patterns.append(('AND', patterns))
        
        # Combine all OR groups with | regex operator
        # Handle AND groups separately based on whether we have multiple OR groups
        if len(all_group_patterns) == 0:
            search_regex = None
        elif len(all_group_patterns) == 1:
            # Single group - could be AND or simple pattern
            item = all_group_patterns[0]
            if isinstance(item, tuple) and item[0] == 'AND':
                # Single AND group - compile each pattern separately
                _, patterns = item
                search_regex = []
                for pattern in patterns:
                    try:
                        search_regex.append(re.compile(pattern, re.IGNORECASE))
                    except re.error:
                        pass
                if not search_regex:
                    search_regex = None
            else:
                # Single simple pattern (wildcard)
                try:
                    search_regex = re.compile(item, re.IGNORECASE)
                except re.error:
                    search_regex = None
        else:
            # Multiple OR groups - need to combine with | operator
            # For OR logic, we can't use list of regexes, need single regex with |
            # Convert AND groups to match-all patterns using lookaheads would freeze
            # So we need to check AND groups separately
            
            # Check if all groups are AND groups
            all_and = all(isinstance(p, tuple) and p[0] == 'AND' for p in all_group_patterns)
            
            if all_and:
                # All OR groups contain AND logic - need special handling
                # Store as list of lists for OR of ANDs
                search_regex = []
                for item in all_group_patterns:
                    _, patterns = item
                    group_regexes = []
                    for pattern in patterns:
                        try:
                            group_regexes.append(re.compile(pattern, re.IGNORECASE))
                        except re.error:
                            pass
                    if group_regexes:
                        search_regex.append(group_regexes)
                if not search_regex:
                    search_regex = None
            else:
                # Mix of AND and simple patterns - convert to single regex with |
                or_patterns = []
                for item in all_group_patterns:
                    if isinstance(item, tuple) and item[0] == 'AND':
                        _, patterns = item
                        # Join with .* for sequential matching
                        or_patterns.append('.*'.join(patterns))
                    else:
                        or_patterns.append(item)
                
                # Wrap each group in non-capturing group and join with |
                regex_pattern = '|'.join([f'(?:{p})' for p in or_patterns])
                try:
                    search_regex = re.compile(regex_pattern, re.IGNORECASE)
                except re.error:
                    search_regex = None

        # Store the search regex for highlighting in summary display (before search starts)
        self.plotSearchRegex = search_regex

        # Get row count from SOURCE model (not proxy) to search all movies
        rowCount = self.moviesTableModel.rowCount()
        self.progressBar.setMaximum(rowCount)
        self.isCanceled = False

        # Build list of movies that match the plot search
        matching_movies = []
        
        # Clear the table immediately by showing empty results
        self.moviesTableProxyModel.setMovieListFilter([], mode='include')
        self.numVisibleMovies = 0
        QtCore.QCoreApplication.processEvents()
        
        # Batch UI updates for better performance (update display every N matches)
        update_interval = 5  # Update display every 5 matches
        progress_update_interval = max(1, rowCount // 100)
        
        # Track timing for ETA
        import time
        start_time = time.time()
        
        # Search through all movies in the SOURCE model
        for sourceRow in range(rowCount):
            # Process events to allow UI updates and cancellation
            if sourceRow % 10 == 0:  # Process events every 10 rows for responsiveness
                QtCore.QCoreApplication.processEvents()
            
            # Check if operation was cancelled
            if self.isCanceled:
                self.statusBar().showMessage('Cancelled')
                self.isCanceled = False
                self.progressBar.setValue(0)
                self.output("Plot search cancelled")
                return

            # Get movie data
            title = self.moviesTableModel.getTitle(sourceRow)
            
            # Get plot and synopsis from cached smdb data (much faster than loading JSON files)
            moviePath = self.moviesTableModel.getPath(sourceRow)
            plot = None
            synopsis = None
            
            if self.moviesSmdbData and 'titles' in self.moviesSmdbData:
                if moviePath in self.moviesSmdbData['titles']:
                    plot = self.moviesSmdbData['titles'][moviePath].get('plot')
                    synopsis = self.moviesSmdbData['titles'][moviePath].get('synopsis')
            
            # Search both plot and synopsis
            text_matches = False
            # Combine title, plot and synopsis for searching
            search_text = ' '.join(filter(None, [title, plot, synopsis]))
            
            if search_text:
                if search_regex:
                    if isinstance(search_regex, list):
                        if len(search_regex) > 0 and isinstance(search_regex[0], list):
                            # OR of ANDs - at least one AND group must have all patterns match
                            text_matches = any(
                                all(regex.search(search_text) for regex in and_group)
                                for and_group in search_regex
                            )
                        else:
                            # Single AND group - all patterns must match
                            text_matches = all(regex.search(search_text) for regex in search_regex)
                    else:
                        # Single regex pattern (OR logic or simple pattern)
                        text_matches = search_regex.search(search_text) is not None
                else:
                    text_matches = searchTextLower in search_text.lower()
            
            if text_matches:
                year = self.moviesTableModel.getYear(sourceRow)
                try:
                    year_int = int(year) if year else 0
                except (ValueError, TypeError):
                    year_int = 0
                matching_movies.append((title, year_int))
                
                # Update display with new matches periodically
                if len(matching_movies) % update_interval == 0:
                    self.moviesTableProxyModel.setMovieListFilter(matching_movies, mode='include')
                    self.numVisibleMovies = self.moviesTableProxyModel.rowCount()
                    QtCore.QCoreApplication.processEvents()
            
            # Update progress bar and status less frequently
            if sourceRow % progress_update_interval == 0:
                self.progressBar.setValue(sourceRow)
                # Calculate and display ETA
                elapsed = time.time() - start_time
                if sourceRow > 0:
                    avg_time_per_item = elapsed / sourceRow
                    remaining_items = rowCount - sourceRow
                    eta_seconds = avg_time_per_item * remaining_items
                    
                    if eta_seconds < 60:
                        eta_str = f"{int(eta_seconds)}s"
                    else:
                        eta_minutes = int(eta_seconds // 60)
                        eta_secs = int(eta_seconds % 60)
                        eta_str = f"{eta_minutes}m {eta_secs}s"
                    
                    self.statusBar().showMessage(f'Plot search: {len(matching_movies)} matches | {sourceRow}/{rowCount} | ETA: {eta_str}')
                else:
                    self.statusBar().showMessage(f'Plot search: {len(matching_movies)} matches | {sourceRow}/{rowCount}')
        
        # Final update to show all matches
        self.moviesTableProxyModel.setMovieListFilter(matching_movies, mode='include')
        self.numVisibleMovies = self.moviesTableProxyModel.rowCount()
        self.showMoviesTableSelectionStatus()
        
        self.progressBar.setValue(0)
        self.statusBar().showMessage(f'Plot search completed: {len(matching_movies)} matches found')
        self.output(f"Plot search completed: {len(matching_movies)} movies found")

    def searchMoviesTableView(self):
        searchText = self.moviesTableTitleFilterBox.text()
        if not searchText:
            self.filterTableSelectionChanged()

        self.moviesTableProxyModel.setFilterKeyColumn(Columns.Title.value)
        self.moviesTableProxyModel.setFilterRegExp(
            QtCore.QRegExp(searchText,
                           QtCore.Qt.CaseInsensitive,
                           QtCore.QRegExp.FixedString))

    def showPrimaryFilterMenu(self):
        if self.primaryFilterWidget:
            self.showPrimaryFilter = not self.showPrimaryFilter
            if not self.showPrimaryFilter:
                self.primaryFilterWidget.hide()
            else:
                self.primaryFilterWidget.show()

    def showSecondaryFilterMenu(self):
        if self.secondaryFilterWidget:
            self.showSecondaryFilter = not self.showSecondaryFilter
            if not self.showSecondaryFilter:
                self.secondaryFilterWidget.hide()
            else:
                self.secondaryFilterWidget.show()

    def showMoviesTableMenu(self):
        if self.moviesTableWidget:
            self.showMoviesTable = not self.showMoviesTable
            if not self.showMoviesTable:
                self.moviesTableWidget.hide()
            else:
                self.moviesTableWidget.show()

    def showWatchListMenu(self):
        if self.watchListWidget:
            self.showWatchList = not self.showWatchList
            if not self.showWatchList:
                self.watchListWidget.hide()
            else:
                self.watchListWidget.show()

    def showHistoryListMenu(self):
        if self.historyListWidget:
            self.showHistoryList = not self.showHistoryList
            if not self.showHistoryList:
                self.historyListWidget.hide()
            else:
                self.historyListWidget.show()

    def showBackupListMenu(self):
        if self.backupListWidget:
            self.showBackupList = not self.showBackupList
            if not self.showBackupList:
                self.backupListWidget.hide()
            else:
                self.backupListWidget.show()

    def showMovieSectionMenu(self):
        if self.movieSectionWidget:
            self.showMovieSection = not self.showMovieSection
            if not self.showMovieSection:
                self.movieSectionWidget.hide()
            else:
                self.movieSectionWidget.show()

    def showCoverMenu(self):
        if self.coverTabWidget:
            self.showCover = not self.showCover
            if not self.showCover:
                self.coverTabWidget.hide()
            else:
                self.coverTabWidget.show()

    def showMovieInfoMenu(self):
        if self.movieInfoWidget:
            self.showMovieInfo = not self.showMovieInfo
            if not self.showMovieInfo:
                self.movieInfoWidget.hide()
            else:
                self.movieInfoWidget.show()

    def showSummaryMenu(self):
        if self.summary:
            self.showSummary = not self.showSummary
            if not self.showSummary:
                self.summary.hide()
            else:
                self.summary.show()

    def showLogMenu(self):
        if self.logWidget:
            self.showLog = not self.showLog
            if not self.showLog:
                self.logWidget.hide()
            else:
                self.logWidget.show()

    def showLightingControlsMenu(self):
        if self.lightingControlsFrame:
            self.showLightingControls = not self.showLightingControls
            if not self.showLightingControls:
                self.lightingControlsFrame.hide()
            else:
                self.lightingControlsFrame.show()

    def onLightingControlsChanged(self):
        """Called when lighting controls are changed - refresh the cover flow widget."""
        # Trigger a redraw of the OpenGL cover flow widget
        if hasattr(self, 'coverFlowWidget'):
            # Force a full repaint to pick up new lighting values
            self.coverFlowWidget.update()
            self.coverFlowWidget.repaint()

    def showLogContextMenu(self, position):
        if not self.logTextWidget:
            return
        menu = self.logTextWidget.createStandardContextMenu()
        menu.addSeparator()
        select_all_action = menu.addAction("Select All")
        clear_action = menu.addAction("Clear Log")
        selected_action = menu.exec_(self.logTextWidget.mapToGlobal(position))
        if selected_action == select_all_action:
            self.logTextWidget.selectAll()
        elif selected_action == clear_action:
            self.logTextWidget.clear()

    def movieInfoSelectionChanged(self):
        selected_items = self.movieInfoListView.selectedItems()
        if len(selected_items) == 0:
            return

        for item in selected_items:
            data = item.data(QtCore.Qt.UserRole)
            if data and len(data) >= 3 and data[0] == 'similar_movie':
                title = data[1]
                year = data[2]
                self.selectMovieByTitleYear(title, year)
                return

        self.moviesTableTitleFilterBox.clear()

        movieList = []
        for item in selected_items:
            smdbKey = None
            data = item.data(QtCore.Qt.UserRole)
            if not data or len(data) < 2:
                continue
            category = data[0]
            if category == 'similar_movie':
                continue
            name = str(data[1])
            if category:
                if category == 'actor':
                    smdbKey = 'actors'
                elif category == 'director':
                    smdbKey = 'directors'
                elif category == 'company':
                    smdbKey = 'companies'
                elif category == 'country':
                    smdbKey = 'countries'
                elif category == 'genre':
                    smdbKey = 'genres'
                elif category == 'year':
                    smdbKey = 'years'
                else:
                    continue

            if name in self.moviesSmdbData[smdbKey]:
                movies = self.moviesSmdbData[smdbKey][name]['movies']
                for movie in movies:
                    movieList.append(movie)

        # Apply the filter using the proxy model
        self.moviesTableProxyModel.setMovieListFilter(movieList, mode='include')
        self.numVisibleMovies = self.moviesTableProxyModel.rowCount()
        self.showMoviesTableSelectionStatus()

    def selectMovieByTitleYear(self, title, year=None, resetFilters=True):
        if not title or not self.moviesTableProxyModel or not self.moviesTableModel:
            return False

        title_normalized = title.strip().lower()
        year_str = str(year).strip() if year else None

        match_row = None
        match_proxy_index = None

        for row in range(self.moviesTableProxyModel.rowCount()):
            proxy_index = self.moviesTableProxyModel.index(row, Columns.Title.value)
            if not proxy_index.isValid():
                continue
            source_index = self.moviesTableProxyModel.mapToSource(proxy_index)
            source_row = source_index.row()
            row_title = self.moviesTableModel.getTitle(source_row)
            if not row_title or row_title.strip().lower() != title_normalized:
                continue
            row_year = self.moviesTableModel.getYear(source_row)
            if year_str and str(row_year) != year_str:
                continue
            match_row = row
            match_proxy_index = proxy_index
            break

        # If not found and resetFilters is True, clear filters and try again
        if match_row is None and resetFilters:
            self.showAllMoviesTableView()
            return self.selectMovieByTitleYear(title, year, resetFilters=False)

        if match_row is None:
            return False

        if match_proxy_index is None or not match_proxy_index.isValid():
            match_proxy_index = self.moviesTableProxyModel.index(match_row, 0)

        self.moviesTableView.clearSelection()
        self.moviesTableView.selectRow(match_row)
        self.moviesTableView.scrollTo(match_proxy_index, QtWidgets.QAbstractItemView.PositionAtCenter)
        return True

    def filterTableSelectionChanged(self, mainFilter=True):
        if len(self.primaryFilterWidget.filterTable.selectedItems()) == 0:
            self.showAllMoviesTableView()
            return

        filterByText = self.primaryFilterWidget.filterByComboBox.currentText()
        filterByKey = self.primaryFilterWidget.filterByDict[filterByText]

        movieList = []
        for item in self.primaryFilterWidget.filterTable.selectedItems():
            name = self.primaryFilterWidget.filterTable.item(item.row(), 0).text()
            # Convert string back to appropriate type for dictionary lookup
            lookup_key = name
            if filterByKey == 'ratings':
                lookup_key = float(name)
            elif filterByKey == 'years':
                lookup_key = int(name)
            movies = self.moviesSmdbData[filterByKey][lookup_key]['movies']
            for movie in movies:
                movieList.append(movie)

        if mainFilter:
            self.secondaryFilterWidget.movieList = movieList
            self.secondaryFilterWidget.populateFiltersTable()

        filter2ByText = self.secondaryFilterWidget.filterByComboBox.currentText()
        filter2ByKey = self.secondaryFilterWidget.filterByDict[filter2ByText]
        if len(self.secondaryFilterWidget.filterTable.selectedItems()) != 0:
            movieList2 = list()
            for movie in movieList:
                foundMovie = False
                for item in self.secondaryFilterWidget.filterTable.selectedItems():
                    name = self.secondaryFilterWidget.filterTable.item(item.row(), 0).text()
                    # Convert string back to appropriate type for dictionary lookup
                    lookup_key = name
                    if filter2ByKey == 'ratings':
                        lookup_key = float(name)
                    elif filter2ByKey == 'years':
                        lookup_key = int(name)
                    movies = self.moviesSmdbData[filter2ByKey][lookup_key]['movies']
                    if movie in movies:
                        foundMovie = True
                        break
                if foundMovie:
                    movieList2.append(movie)
            movieList = movieList2

        # Apply the filter using the proxy model
        self.moviesTableProxyModel.setMovieListFilter(movieList, mode='include')
        self.numVisibleMovies = self.moviesTableProxyModel.rowCount()
        
        # Select first visible row if any
        if self.moviesTableProxyModel.rowCount() > 0:
            self.moviesTableView.selectRow(0)
        
        self.showMoviesTableSelectionStatus()

        sortColumn = self.moviesTableProxyModel.sortColumn()
        sortOrder = self.moviesTableProxyModel.sortOrder()
        self.moviesTableProxyModel.sort(sortColumn, sortOrder)

    def resizeCoverFile(self):
        if self.movieCover:
            sz = self.movieCover.size()
            coverFile = self.movieCover.property('cover file')
            if coverFile and isinstance(coverFile, str) and os.path.exists(coverFile):
                pm = QtGui.QPixmap(coverFile)
                if not pm.isNull():
                    self.movieCover.setPixmap(pm.scaled(sz.width(), sz.height(),
                                                        QtCore.Qt.KeepAspectRatio,
                                                        QtCore.Qt.SmoothTransformation))
                    return
            # If no valid cover, clear pixmap to avoid scaling null pixmap
            self.movieCover.setPixmap(QtGui.QPixmap())

    def resizeEvent(self, a0: QtGui.QResizeEvent) -> None:
        self.resizeCoverFile()

    def showCoverFile(self, coverFile, coverImage=None):
        if coverFile and os.path.exists(coverFile):
            # Use provided QImage if available, otherwise load it
            if coverImage is None:
                coverImage = QtGui.QImage(coverFile)
            
            if not coverImage.isNull():
                # Convert QImage to QPixmap for display
                pm = QtGui.QPixmap.fromImage(coverImage)
                sz = self.movieCover.size()
                self.movieCover.setPixmap(pm.scaled(sz.width(), sz.height(),
                                                    QtCore.Qt.KeepAspectRatio,
                                                    QtCore.Qt.SmoothTransformation))
                self.movieCover.setProperty('cover file', coverFile)
                return
        else:
            self.movieCover.setPixmap(QtGui.QPixmap())

    def movieInfoAddSection(self, jsonData, jsonName, smdbName, userRoleName):
        if not jsonData:
            return
        if jsonName in jsonData and jsonData[jsonName]:
            for name in jsonData[jsonName]:
                numMovies = 0
                # Check if smdbName exists in moviesSmdbData (for backward compatibility)
                if smdbName in self.moviesSmdbData and name in self.moviesSmdbData[smdbName]:
                    numMovies = self.moviesSmdbData[smdbName][name]['num movies']
                item = QtWidgets.QListWidgetItem('%s (%d)' % (name, numMovies))
                item.setData(QtCore.Qt.UserRole, [userRoleName, name])
                self.movieInfoListView.addItem(item)

    def movieInfoAddHeading(self, headerName):
        item = QtWidgets.QListWidgetItem(headerName)
        item.setFlags(QtCore.Qt.ItemIsEnabled)
        item.setForeground(self.bgColorE)
        self.movieInfoListView.addItem(item)

    def movieInfoAddSpacer(self):
        spacerItem = QtWidgets.QListWidgetItem("")
        spacerItem.setFlags(QtCore.Qt.ItemIsEnabled)
        self.movieInfoListView.addItem(spacerItem)

    def parseSimilarMovieEntry(self, entry):
        text = str(entry).strip()
        title = text
        year = None
        match = re.match(r'^(.*?)[ ]?\((\d{4})\)$', text)
        if match:
            title = match.group(1).strip()
            year = match.group(2).strip()
        return text, title, year

    def movieInfoRefresh(self, jsonData):
        if not jsonData:
            return
        self.movieInfoListView.clear()

        self.movieInfoAddHeading("Year:")
        if 'year' in jsonData and jsonData['year']:
            year = jsonData['year']
            yearItem = QtWidgets.QListWidgetItem('%s' % year)
            yearItem.setData(QtCore.Qt.UserRole, ['year', year])
            self.movieInfoListView.addItem(yearItem)

        self.movieInfoAddSpacer()

        self.movieInfoAddHeading("Rating:")
        if 'rating' in jsonData and jsonData['rating']:
            rating = jsonData['rating']
            ratingItem = QtWidgets.QListWidgetItem('%s' % rating)
            ratingItem.setFlags(QtCore.Qt.ItemIsEnabled)
            self.movieInfoListView.addItem(ratingItem)

        self.movieInfoAddSpacer()

        self.movieInfoAddHeading("Box Office:")
        if 'box office' in jsonData and jsonData['box office']:
            boxOffice = jsonData['box office']
            boxOfficeItem = QtWidgets.QListWidgetItem('%s' % boxOffice)
            boxOfficeItem.setFlags(QtCore.Qt.ItemIsEnabled)
            self.movieInfoListView.addItem(boxOfficeItem)

        self.movieInfoAddSpacer()

        self.movieInfoAddHeading("Runtime:")
        if 'runtime' in jsonData and jsonData['runtime']:
            runtime = jsonData['runtime']
            runtimeItem = QtWidgets.QListWidgetItem('%s minutes' % runtime)
            runtimeItem.setFlags(QtCore.Qt.ItemIsEnabled)
            self.movieInfoListView.addItem(runtimeItem)

        self.movieInfoAddSpacer()

        #self.movieInfoAddHeading("Director:")
        #if 'directors' in jsonData and jsonData['directors']:
        #    directorName = jsonData['director'][0]
        #    numMovies = 0
        #    if directorName in self.moviesSmdbData['directors']:
        #        numMovies = self.moviesSmdbData['directors'][directorName]['num movies']
        #    directorItem = QtWidgets.QListWidgetItem('%s(%d)' % (directorName, numMovies))
        #    directorItem.setData(QtCore.Qt.UserRole, ['director', directorName])
        #    self.movieInfoListView.addItem(directorItem)

        self.movieInfoAddHeading("Directors:")
        self.movieInfoAddSection(jsonData, 'directors', 'directors', 'director')
        self.movieInfoAddSpacer()
        self.movieInfoAddHeading("Companies:")
        self.movieInfoAddSection(jsonData, 'companies', 'companies', 'company')
        self.movieInfoAddSpacer()
        self.movieInfoAddHeading("Countries:")
        self.movieInfoAddSection(jsonData, 'countries', 'countries', 'country')
        self.movieInfoAddSpacer()
        self.movieInfoAddHeading("Genres:")
        self.movieInfoAddSection(jsonData, 'genres', 'genres', 'genre')
        self.movieInfoAddSpacer()
        self.movieInfoAddHeading("Cast:")
        self.movieInfoAddSection(jsonData, 'cast', 'actors', 'actor')

        # Add Writers section if available
        if 'writers' in jsonData and jsonData['writers']:
            self.movieInfoAddSpacer()
            self.movieInfoAddHeading("Writers:")
            self.movieInfoAddSection(jsonData, 'writers', 'writers', 'writer')

        # Add Producers section if available
        if 'producers' in jsonData and jsonData['producers']:
            self.movieInfoAddSpacer()
            self.movieInfoAddHeading("Producers:")
            self.movieInfoAddSection(jsonData, 'producers', 'producers', 'producer')

        # Add Composers section if available
        if 'composers' in jsonData and jsonData['composers']:
            self.movieInfoAddSpacer()
            self.movieInfoAddHeading("Composers:")
            self.movieInfoAddSection(jsonData, 'composers', 'composers', 'composer')

        similar_movies = jsonData.get('similar movies') or []
        if isinstance(similar_movies, list) and similar_movies:
            self.movieInfoAddSpacer()
            self.movieInfoAddHeading("Similar Movies:")
            for entry in similar_movies:
                display_text, title_value, year_value = self.parseSimilarMovieEntry(entry)
                item = QtWidgets.QListWidgetItem(display_text)
                item.setFlags(QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable)
                item.setData(QtCore.Qt.UserRole, ['similar_movie', title_value, year_value])
                self.movieInfoListView.addItem(item)

        self.movieInfoListView.setCurrentRow(0)

    def highlightSearchTerms(self, text, search_regex):
        """Highlight search terms in text using HTML.
        
        Args:
            text: The text to highlight terms in
            search_regex: Either a compiled regex, or a list of regexes (AND), or list of lists (OR of ANDs)
            
        Returns:
            Text with HTML highlighting applied
        """
        if not text or not search_regex:
            return text
        
        # Collect all regex patterns to highlight
        patterns_to_highlight = []
        
        if isinstance(search_regex, list):
            if len(search_regex) > 0 and isinstance(search_regex[0], list):
                # OR of ANDs - flatten all patterns
                for and_group in search_regex:
                    patterns_to_highlight.extend(and_group)
            else:
                # Single AND group
                patterns_to_highlight = search_regex
        else:
            # Single regex pattern - could be OR pattern with | operator
            # In this case, we want to highlight all matches from the combined pattern
            patterns_to_highlight = [search_regex]
        
        # Find all matches with their positions
        matches = []
        for pattern in patterns_to_highlight:
            for match in pattern.finditer(text):
                # Don't add empty matches
                if match.group():
                    matches.append((match.start(), match.end(), match.group()))
        
        if not matches:
            return text
        
        # Sort by position and merge overlapping matches
        matches.sort()
        merged_matches = []
        for start, end, matched_text in matches:
            if merged_matches and start < merged_matches[-1][1]:
                # Overlapping - extend the previous match
                prev_start, prev_end, prev_text = merged_matches[-1]
                merged_matches[-1] = (prev_start, max(end, prev_end), text[prev_start:max(end, prev_end)])
            else:
                merged_matches.append((start, end, matched_text))
        
        # Build highlighted text from end to start to preserve positions
        # Need to HTML-escape the text first, then apply highlights
        import html
        result_parts = []
        last_pos = 0
        
        for start, end, matched_text in merged_matches:
            # Add non-highlighted text (escaped)
            if start > last_pos:
                result_parts.append(html.escape(text[last_pos:start]))
            # Add highlighted text (escaped)
            result_parts.append(f'<span style="background-color: yellow; color: black;">{html.escape(matched_text)}</span>')
            last_pos = end
        
        # Add remaining text
        if last_pos < len(text):
            result_parts.append(html.escape(text[last_pos:]))
        
        return ''.join(result_parts)

    def getPlot(self, jsonData):
        if not jsonData:
            return

        infoText = ''
        if 'plot' in jsonData and jsonData['plot']:
            infoText += '<br>Plot:<br>'
            if isinstance(jsonData['plot'], list):
                plot = jsonData['plot'][0]
            else:
                plot = jsonData['plot']
            # Remove the author of the plot's name
            plot = plot.split('::')[0]
            infoText += '%s<br>' % plot
        return infoText

    def getSummary(self, jsonData):
        if not jsonData:
            return

        infoText = ''
        if 'plot' in jsonData and jsonData['plot']:
            infoText += '<br>Plot:<br>'
            if isinstance(jsonData['plot'], list):
                plot = jsonData['plot'][0]
            else:
                plot = jsonData['plot']
            # Remove the author of the plot's name
            plot = plot.split('::')[0]
            
            # Highlight search terms if we have a plot search active
            if self.plotSearchRegex:
                plot = self.highlightSearchTerms(plot, self.plotSearchRegex)
            
            infoText += '%s<br>' % plot
            
        if 'synopsis' in jsonData and jsonData['synopsis']:
            infoText += '<br>Synopsis:<br>'
            if isinstance(jsonData['synopsis'], list):
                synopsis = jsonData['synopsis'][0]
            else:
                synopsis = jsonData['synopsis']
            # Remove the author of the synopsis's name
            synopsis = synopsis.split('::')[0]
            
            # Highlight search terms if we have a plot search active
            if self.plotSearchRegex:
                synopsis = self.highlightSearchTerms(synopsis, self.plotSearchRegex)
            
            infoText += '%s<br>' % synopsis
            
        return infoText

    def summaryShow(self, jsonData):
        infoText = self.getSummary(jsonData)
        self.summary.setText(infoText)

    def rebuildSmdbFileAndReload(self):
        """Rebuild SMDB file and reload the movie list"""
        self.writeSmdbFile(self.moviesSmdbFile, self.moviesTableModel, titlesOnly=False)
        self.statusBar().showMessage('Reloading movies...')
        QtCore.QCoreApplication.processEvents()
        self.refreshMoviesList()
        self.statusBar().showMessage('Rebuild complete')

    def writeSmdbFile(self, fileName, model, titlesOnly=False):
        titles = {}
        directors = {}
        actors = {}
        writers = {}
        producers = {}
        composers = {}
        mpaaRatings = {}
        ratings = {}
        genres = {}
        years = {}
        companies = {}
        countries = {}
        userTags = {}

        # Small helpers to index aggregate dicts efficiently
        # Use dict-as-set for O(1) membership and to preserve insertion order
        def add_to_index(index_dict, key, title_year):
            if key is None:
                return
            entry = index_dict.get(key)
            if entry is None:
                entry = {'num movies': 0, 'movies': {}}
                index_dict[key] = entry
            movies = entry.get('movies')
            if isinstance(movies, list):
                # Backward compatibility if a list slips in
                if title_year not in movies:
                    movies.append(title_year)
                    entry['num movies'] += 1
            else:
                # dict-as-set path
                if title_year not in movies:
                    movies[title_year] = None
                    entry['num movies'] += 1

        def normalize_index_for_json(index_dict):
            for _, entry in index_dict.items():
                movies = entry.get('movies')
                if isinstance(movies, dict):
                    entry['movies'] = list(movies.keys())
                    entry['num movies'] = len(entry['movies'])

        count = model.rowCount()
        self.progressBar.setMaximum(count)
        progress = 0
        self.isCanceled = False

        # For box office $
        reMoneyValue = re.compile(r'(\d+(?:,\d+)*(?:\.\d+)?)')
        reCurrency = re.compile(r'^([A-Z][A-Z][A-Z])(.*)')

        # Throttle UI updates to reduce overhead while keeping responsiveness
        import time
        ui_update_interval = 0.1  # seconds
        loop_start_time = time.perf_counter()
        ui_last_update = loop_start_time

        for row in range(count):
            # advance progress and throttle UI updates
            progress += 1
            now = time.perf_counter()
            if (now - ui_last_update) >= ui_update_interval or row == (count - 1):
                # Show percentage, throughput, and ETA in status
                elapsed = now - loop_start_time
                avg_per_item = (elapsed / progress) if progress else 0.0
                remaining = max(0, count - progress)
                eta_seconds = remaining * avg_per_item
                eta_h = int(eta_seconds // 3600)
                eta_m = int((eta_seconds % 3600) // 60)
                eta_s = int(eta_seconds % 60)
                if eta_h > 0:
                    eta_str = f"{eta_h}:{eta_m:02d}:{eta_s:02d}"
                else:
                    eta_str = f"{eta_m:02d}:{eta_s:02d}"
                pct = (progress / count * 100.0) if count else 0.0
                ips = (progress / elapsed) if elapsed > 0 else 0.0
                message = "Processing (%d/%d, %4.1f%%, %4.1f it/s): ETA %s" % (progress, count, pct, ips, eta_str)
                self.progressBar.setValue(progress)
                self.statusBar().showMessage(message)
                QtCore.QCoreApplication.processEvents()
                ui_last_update = now

                if self.isCanceled:
                    self.statusBar().showMessage('Cancelled')
                    self.isCanceled = False
                    self.progressBar.setValue(0)
                    return

            dateWatched = model.getDateWatched(row)
            rank = model.getRank(row)
            moviePath = model.getPath(row)
            folderName = model.getFolderName(row)
            moviePath = self.findMovie(moviePath, folderName)
            if not moviePath or not os.path.exists(moviePath):
                self.output(f"path does not exist: {moviePath}")
                continue

            jsonFile = os.path.join(moviePath, '%s.json' % folderName)
            if not os.path.exists(jsonFile):
                continue

            with open(jsonFile, encoding="utf-8") as f:
                try:
                    jsonData = ujson.load(f)
                except UnicodeDecodeError:
                    self.output("Error reading %s" % jsonFile)
                    continue

            # Use 'date' from JSON if available, otherwise fall back to file modification time
            if 'date' in jsonData:
                # Date from JSON is already in YYYY-MM-DD format, convert to YYYY/MM/DD
                jsonDate = jsonData.get('date')
                dateModified = jsonDate.replace('-', '/')
            else:
                dateModified = datetime.datetime.fromtimestamp(pathlib.Path(moviePath).stat().st_mtime)
                dateModified = f"{dateModified.year}/{str(dateModified.month).zfill(2)}/{str(dateModified.day).zfill(2)}"

            if 'title' in jsonData and 'year' in jsonData:
                jsonTitle = jsonData.get('title')

                jsonWidth = jsonData.get('width') or 0
                jsonHeight = jsonData.get('height') or 0
                jsonChannels = jsonData.get('channels') or 0
                jsonSize = jsonData.get('size') or 0

                # Parse numeric year for indexing
                jsonYearInt = 0
                if jsonData.get('year'):
                    try:
                        jsonYearInt = int(jsonData.get('year'))
                    except ValueError:
                        try:
                            jy = str(jsonData.get('year')).split('â€“')[0]
                            jsonYearInt = int(jy)
                        except Exception:
                            jsonYearInt = 0
                
                # Use integer year in tuple to match stored format
                titleYearTuple = (jsonTitle, jsonYearInt)

                # Indexing block
                if not titlesOnly and jsonYearInt:
                    add_to_index(years, jsonYearInt, titleYearTuple)

                # Directors
                movieDirectorList = []
                jsonDirectors = jsonData.get('directors') or []
                for director in jsonDirectors:
                    movieDirectorList.append(director)
                    if not titlesOnly:
                        add_to_index(directors, director, titleYearTuple)

                # Actors
                movieActorsList = []
                jsonCast = jsonData.get('cast') or []
                for actor in jsonCast:
                    movieActorsList.append(actor)
                    if not titlesOnly:
                        add_to_index(actors, actor, titleYearTuple)

                # Writers
                movieWritersList = []
                jsonWriters = jsonData.get('writers') or []
                for writer in jsonWriters:
                    movieWritersList.append(writer)
                    if not titlesOnly:
                        add_to_index(writers, writer, titleYearTuple)

                # Producers
                movieProducersList = []
                jsonProducers = jsonData.get('producers') or []
                for producer in jsonProducers:
                    movieProducersList.append(producer)
                    if not titlesOnly:
                        add_to_index(producers, producer, titleYearTuple)

                # Composers
                movieComposersList = []
                jsonComposers = jsonData.get('composers') or []
                for composer in jsonComposers:
                    movieComposersList.append(composer)
                    if not titlesOnly:
                        add_to_index(composers, composer, titleYearTuple)

                # User tags
                jsonUserTags = jsonData.get('user tags') or []
                if not titlesOnly:
                    for tag in jsonUserTags:
                        add_to_index(userTags, tag, titleYearTuple)

                # Genres
                jsonGenres = jsonData.get('genres') or []
                if not titlesOnly:
                    for genre in jsonGenres:
                        add_to_index(genres, genre, titleYearTuple)

                # Companies
                jsonCompanies = jsonData.get('companies') or []
                if not titlesOnly:
                    for company in jsonCompanies:
                        add_to_index(companies, company, titleYearTuple)

                # Countries
                jsonCountries = jsonData.get('countries') or []
                if not titlesOnly:
                    for country in jsonCountries:
                        add_to_index(countries, country, titleYearTuple)

                # IDs and ratings
                jsonId = jsonData.get('id') or None

                jsonRating = None
                if jsonData.get('rating'):
                    try:
                        jsonRating = float(jsonData.get('rating'))
                    except ValueError:
                        jsonRating = 0.0
                    if not titlesOnly:
                        add_to_index(ratings, jsonRating, titleYearTuple)

                jsonMpaaRating = None
                if jsonData.get('mpaa rating'):
                    jsonMpaaRating = jsonData.get('mpaa rating')
                    if not titlesOnly:
                        add_to_index(mpaaRatings, jsonMpaaRating, titleYearTuple)

                # Box office formatting and other fields
                jsonBoxOffice = None
                if jsonData.get('box office'):
                    jsonBoxOffice = jsonData.get('box office')
                    try:
                        currency = 'USD'
                        if jsonBoxOffice:
                            jsonBoxOffice = jsonBoxOffice.replace(' (estimated)', '')
                            match = re.match(reCurrency, jsonBoxOffice)
                            if match:
                                currency = match.group(1)
                                jsonBoxOffice = '$%s' % match.group(2)
                            results = re.findall(reMoneyValue, jsonBoxOffice)
                            if results:
                                amount = ('$' + results[0]) if currency == 'USD' else results[0]
                            else:
                                amount = '$0'
                        else:
                            amount = '$0'
                        jsonBoxOffice = '%-3s %15s' % (currency, amount)
                    except Exception:
                        pass

                jsonRuntime = jsonData.get('runtime') or None

                jsonSimilarMovies = jsonData.get('similar movies') or []
                if not isinstance(jsonSimilarMovies, list):
                    jsonSimilarMovies = [jsonSimilarMovies] if jsonSimilarMovies else []

                # Known duplicate status
                knownDuplicate = jsonData.get('known duplicate', False)

                # Extract plot for caching in smdb file
                jsonPlot = None
                if jsonData.get('plot'):
                    plot_data = jsonData.get('plot')
                    if isinstance(plot_data, list):
                        jsonPlot = plot_data[0] if plot_data else None
                    else:
                        jsonPlot = plot_data
                    # Remove the author of the plot's name
                    if jsonPlot:
                        jsonPlot = jsonPlot.split('::')[0]

                # Extract synopsis for caching in smdb file
                jsonSynopsis = None
                if jsonData.get('synopsis'):
                    synopsis_data = jsonData.get('synopsis')
                    if isinstance(synopsis_data, list):
                        jsonSynopsis = synopsis_data[0] if synopsis_data else None
                    else:
                        jsonSynopsis = synopsis_data
                    # Remove the author of the synopsis's name
                    if jsonSynopsis:
                        jsonSynopsis = jsonSynopsis.split('::')[0]

                # Subtitles exist status comes from current model value if present
                try:
                    if len(model._data[row]) > Columns.SubtitlesExist.value:
                        subtitlesExist = model._data[row][Columns.SubtitlesExist.value] or "unknown"
                    else:
                        subtitlesExist = "unknown"
                except Exception:
                    subtitlesExist = "unknown"

                # Build title entry
                titles[moviePath] = {
                    'folder': folderName,
                    'id': jsonId,
                    'title': jsonTitle,
                    'year': jsonYearInt,
                    'rating': jsonRating,
                    'mpaa rating': jsonMpaaRating,
                    'runtime': jsonRuntime,
                    'box office': jsonBoxOffice,
                    'directors': movieDirectorList,
                    'genres': jsonGenres or None,
                    'user tags': jsonUserTags or None,
                    'countries': jsonCountries or None,
                    'companies': jsonCompanies or None,
                    'actors': movieActorsList,
                    'writers': movieWritersList,
                    'producers': movieProducersList,
                    'composers': movieComposersList,
                    'rank': rank,
                    'width': jsonWidth,
                    'height': jsonHeight,
                    'channels': jsonChannels,
                    'size': jsonSize,
                    'path': moviePath,
                    'date': dateModified,
                    'subtitles exist': subtitlesExist,
                    'date watched': dateWatched,
                    'similar movies': jsonSimilarMovies,
                    'known duplicate': knownDuplicate,
                    'plot': jsonPlot,
                    'synopsis': jsonSynopsis
                }

        self.progressBar.setValue(0)

        self.statusBar().showMessage('Sorting Data...')
        QtCore.QCoreApplication.processEvents()
        
        # Count how many movies have plots and synopsis for logging
        plot_count = sum(1 for t in titles.values() if t.get('plot'))
        synopsis_count = sum(1 for t in titles.values() if t.get('synopsis'))
        self.output(f"Collected {plot_count} plots and {synopsis_count} synopses out of {len(titles)} movies")

        # Normalize indexes (convert dict-as-set to lists) before serializing
        data = {'titles': collections.OrderedDict(sorted(titles.items()))}
        if not titlesOnly:
            normalize_index_for_json(years)
            normalize_index_for_json(genres)
            normalize_index_for_json(directors)
            normalize_index_for_json(actors)
            normalize_index_for_json(writers)
            normalize_index_for_json(producers)
            normalize_index_for_json(composers)
            normalize_index_for_json(companies)
            normalize_index_for_json(countries)
            normalize_index_for_json(userTags)
            normalize_index_for_json(mpaaRatings)
            normalize_index_for_json(ratings)
            data['years'] = collections.OrderedDict(sorted(years.items()))
            data['genres'] = collections.OrderedDict(sorted(genres.items()))
            data['directors'] = collections.OrderedDict(sorted(directors.items()))
            data['actors'] = collections.OrderedDict(sorted(actors.items()))
            data['writers'] = collections.OrderedDict(sorted(writers.items()))
            data['producers'] = collections.OrderedDict(sorted(producers.items()))
            data['composers'] = collections.OrderedDict(sorted(composers.items()))
            data['companies'] = collections.OrderedDict(sorted(companies.items()))
            data['countries'] = collections.OrderedDict(sorted(countries.items()))
            data['user tags'] = collections.OrderedDict(sorted(userTags.items()))
            data['mpaa ratings'] = collections.OrderedDict(sorted(mpaaRatings.items()))
            data['ratings'] = collections.OrderedDict(sorted(ratings.items()))

        # Try to write fast binary format (.mpk) if msgpack is available
        # Otherwise fall back to JSON (human-readable, backward-compatible)
        try:
            import msgpack  # optional dependency
        except Exception:
            msgpack = None
        
        if msgpack:
            try:
                base, ext = os.path.splitext(fileName)
                mpk_path = f"{base}.mpk" if ext.lower() != ".mpk" else fileName
                self.statusBar().showMessage('Writing %s' % mpk_path)
                QtCore.QCoreApplication.processEvents()
                with open(mpk_path, "wb") as bf:
                    msgpack.pack(data, bf, use_bin_type=True)
                
                # Get file size for logging
                mpk_size_mb = os.path.getsize(mpk_path) / (1024 * 1024)
                self.output(f"Wrote {mpk_path} ({mpk_size_mb:.2f} MB)")
                
                # Also write JSON for human readability and backup
                self.statusBar().showMessage('Writing %s' % fileName)
                QtCore.QCoreApplication.processEvents()
                with open(fileName, "w", encoding="utf-8") as f:
                    ujson.dump(data, f, indent=4)
                
                json_size_mb = os.path.getsize(fileName) / (1024 * 1024)
                self.output(f"Wrote {fileName} ({json_size_mb:.2f} MB)")
                
            except Exception as e:
                # Fall back to JSON if msgpack write fails
                self.output(f"Warning: failed to write MessagePack SMDB: {e}, falling back to JSON")
                self.statusBar().showMessage('Writing %s' % fileName)
                QtCore.QCoreApplication.processEvents()
                with open(fileName, "w", encoding="utf-8") as f:
                    ujson.dump(data, f, indent=4)
        else:
            # Write JSON when msgpack is not available
            self.statusBar().showMessage('Writing %s' % fileName)
            QtCore.QCoreApplication.processEvents()
            with open(fileName, "w", encoding="utf-8") as f:
                ujson.dump(data, f, indent=4)

        self.statusBar().showMessage('Done')
        QtCore.QCoreApplication.processEvents()

        return data

    # Context Menus -----------------------------------------------------------

    def movieInfoRightMenu(self):
        rightMenu = QtWidgets.QMenu(self.movieInfoListView)
        selectedItem = self.movieInfoListView.itemAt(self.movieInfoListView.mouseLocation)
        category = selectedItem.data(QtCore.Qt.UserRole)[0]
        if category == 'director' or category == 'actor' or category == 'year':
            openImdbAction = QtWidgets.QAction("Open IMDB Page", self)
            itemText = selectedItem.text()
            if category == 'director' or category == 'actor':
                openImdbAction.triggered.connect(lambda: openPersonImdbPage(itemText))
            elif category == 'year':
                openImdbAction.triggered.connect(lambda: openYearImdbPage(itemText))
            rightMenu.addAction(openImdbAction)
            rightMenu.exec_(QtGui.QCursor.pos())

    def conditionTitle(self, title, insensitive_the):
        title = title.lower()
        title = insensitive_the.sub('', title)
        title = title.replace('&', 'and')
        title = title.replace("'", "")
        title = title.replace("`", "")
        title = title.replace("â€™", "")
        title = title.replace("...", "")
        title = title.replace("-", " ")
        title = title.replace("â€”", " ")
        title = title.replace("(", "")
        title = title.replace(")", "")
        title = title.encode('ascii', 'replace').decode()
        return title.strip()

    def filterCollection(self, collection_type):
        insensitive_the = re.compile(r'\bthe\b', re.IGNORECASE)
        collection = getCollection(collection_type)
        collection_mod = [(r, self.conditionTitle(t, insensitive_the), int(y)) for r, t, y in collection]
        rowCount = range(self.moviesTableProxyModel.rowCount())

        self.progressBar.setMaximum(rowCount.stop)
        progress = 0
        foundMovies = set()
        matching_movies = []

        for row in rowCount:
            proxyModelIndex = self.moviesTableProxyModel.index(row, 0)
            sourceIndex = self.moviesTableProxyModel.mapToSource(proxyModelIndex)
            sourceRow = sourceIndex.row()
            title = self.moviesTableModel.getTitle(sourceRow)
            title_conditioned = self.conditionTitle(title, insensitive_the)
            year = int(self.moviesTableModel.getYear(sourceRow))

            for item in collection_mod:
                r, t, y = item
                if t == title_conditioned and abs(y - year) < 5:  # Allow a slight difference in year
                    try:
                        year_int = int(year) if year else 0
                    except (ValueError, TypeError):
                        year_int = 0
                    matching_movies.append((title, year_int))
                    self.moviesTableModel.setRank(sourceIndex, r)
                    foundMovies.add((t, y))
                    break

            progress += 1
            self.progressBar.setValue(progress)

        # Apply the filter using the proxy model
        self.moviesTableProxyModel.setMovieListFilter(matching_movies, mode='include')
        self.numVisibleMovies = self.moviesTableProxyModel.rowCount()
        
        # Select first visible row if any
        if self.moviesTableProxyModel.rowCount() > 0:
            self.moviesTableView.selectRow(0)
        
        self.progressBar.setValue(0)
        self.showMoviesTableSelectionStatus()
        self.moviesTableModel.aboutToChangeLayout()

        # Add missing films
        for i, item in enumerate(collection_mod):
            r, t, y = item
            if (t, y) not in foundMovies:
                # Use the unmodified data
                original_item = collection[i]
                r2, t2, y2 = original_item
                data = {"title": t2, "year": y2, "rank": r2, "backup status": "Folder Missing"}
                self.moviesTableModel.addMovieData(data, "Not Found", "Not Found")

        self.moviesTableModel.changedLayout()

        name = os.path.splitext(os.path.basename(str(collection_type)))[0].lower()
        sort_column = Columns.Rank.value if name == 'criterion' else Columns.Year.value
        self.moviesTableProxyModel.sort(sort_column, QtCore.Qt.AscendingOrder)

    def moviesTableRightMenuShow(self, QPos):
        moviesTableRightMenu = QtWidgets.QMenu(self.moviesTableView)

        moviesTableRightMenu.setStyleSheet("""QMenu::separator { background: white; }""")

        playAction = QtWidgets.QAction("Play")
        playAction.triggered.connect(lambda: self.playMovie(self.moviesTableView,
                                                            self.moviesTableProxyModel))
        moviesTableRightMenu.addAction(playAction)

        openFolderAction = QtWidgets.QAction("Open Folder", self)
        openFolderAction.triggered.connect(self.openMovieFolder)
        moviesTableRightMenu.addAction(openFolderAction)

        selectAllAction = QtWidgets.QAction("Select All", self)
        selectAllAction.triggered.connect(lambda: self.tableSelectAll(self.moviesTableView))
        moviesTableRightMenu.addAction(selectAllAction)

        openJsonAction = QtWidgets.QAction("Open Json File", self)
        openJsonAction.triggered.connect(self.openMovieJson)
        moviesTableRightMenu.addAction(openJsonAction)

        removeJsonFilesAction = QtWidgets.QAction("Remove .json files", self)
        removeJsonFilesAction.triggered.connect(self.removeJsonFilesMenu)
        moviesTableRightMenu.addAction(removeJsonFilesAction)

        removeCoversAction = QtWidgets.QAction("Remove cover files", self)
        removeCoversAction.triggered.connect(self.removeCoverFilesMenu)
        moviesTableRightMenu.addAction(removeCoversAction)

        removeMovieAction = QtWidgets.QAction("Remove movie", self)
        removeMovieAction.triggered.connect(self.removeMovieMenu)
        moviesTableRightMenu.addAction(removeMovieAction)

        moviesTableRightMenu.addSeparator()

        openImdbAction = QtWidgets.QAction("Open IMDB Page", self)
        openImdbAction.triggered.connect(self.openMovieImdbPage)
        moviesTableRightMenu.addAction(openImdbAction)

        overrideImdbAction = QtWidgets.QAction("Override IMDB ID", self)
        overrideImdbAction.triggered.connect(self.overrideID)
        moviesTableRightMenu.addAction(overrideImdbAction)

        moviesTableRightMenu.addSeparator()

        addToWatchListAction = QtWidgets.QAction("Add To Watch List", self)
        addToWatchListAction.triggered.connect(self.watchListAdd)
        moviesTableRightMenu.addAction(addToWatchListAction)

        addToBackupListAction = QtWidgets.QAction("Add To Backup List", self)
        addToBackupListAction.triggered.connect(self.backupListAdd)
        moviesTableRightMenu.addAction(addToBackupListAction)

        moviesTableRightMenu.addSeparator()

        findDuplicatesAction = QtWidgets.QAction("Find Duplicates", self)
        findDuplicatesAction.triggered.connect(self.findDuplicates)
        moviesTableRightMenu.addAction(findDuplicatesAction)

        markKnownDuplicateAction = QtWidgets.QAction("Mark as Known Duplicate", self)
        markKnownDuplicateAction.triggered.connect(self.markAsKnownDuplicate)
        moviesTableRightMenu.addAction(markKnownDuplicateAction)

        unmarkKnownDuplicateAction = QtWidgets.QAction("Unmark as Known Duplicate", self)
        unmarkKnownDuplicateAction.triggered.connect(self.unmarkAsKnownDuplicate)
        moviesTableRightMenu.addAction(unmarkKnownDuplicateAction)

        findMovieInMovieAction = QtWidgets.QAction("Find Movie in Movie", self)
        findMovieInMovieAction.triggered.connect(self.findMovieInMovie)
        moviesTableRightMenu.addAction(findMovieInMovieAction)

        searchForOtherVersionsAction = QtWidgets.QAction("Search for other versions", self)
        searchForOtherVersionsAction.triggered.connect(self.searchForOtherVersions)
        moviesTableRightMenu.addAction(searchForOtherVersionsAction)

        moviesTableRightMenu.addSeparator()

        addNewUserTagAction = QtWidgets.QAction("Add New User Tag", self)
        addNewUserTagAction.triggered.connect(self.addNewUserTag)
        moviesTableRightMenu.addAction(addNewUserTagAction)

        addExistingUserTagAction = QtWidgets.QAction("Add Existing User Tag", self)
        addExistingUserTagAction.triggered.connect(self.addExistingUserTag)
        moviesTableRightMenu.addAction(addExistingUserTagAction)

        clearUserTagsAction = QtWidgets.QAction("Clear User Tags", self)
        clearUserTagsAction.triggered.connect(self.clearUserTags)
        moviesTableRightMenu.addAction(clearUserTagsAction)

        moviesTableRightMenu.addSeparator()

        downloadDataAction = QtWidgets.QAction("Download Data", self)
        downloadDataAction.triggered.connect(self.downloadDataMenu)
        moviesTableRightMenu.addAction(downloadDataAction)

        downloadMissingDataAction = QtWidgets.QAction("Download Missing Data", self)
        downloadMissingDataAction.triggered.connect(self.downloadMissingDataMenu)
        moviesTableRightMenu.addAction(downloadMissingDataAction)

        downloadDataAction = QtWidgets.QAction("Force Download Data", self)
        downloadDataAction.triggered.connect(lambda: self.downloadDataMenu(force=True))
        moviesTableRightMenu.addAction(downloadDataAction)

        downloadDataAction = QtWidgets.QAction("Force Download Json only", self)
        downloadDataAction.triggered.connect(lambda: self.downloadDataMenu(force=True,
                                                                           doJson=True,
                                                                           doCover=False))
        moviesTableRightMenu.addAction(downloadDataAction)

        downloadDataAction = QtWidgets.QAction("Force Download Cover only", self)
        downloadDataAction.triggered.connect(lambda: self.downloadDataMenu(force=True,
                                                                           doJson=False,
                                                                           doCover=True))
        moviesTableRightMenu.addAction(downloadDataAction)

        downloadSynopsisAction = QtWidgets.QAction("Download Synopsis", self)
        downloadSynopsisAction.triggered.connect(lambda: self.downloadSynopsisMenu(force=False))
        moviesTableRightMenu.addAction(downloadSynopsisAction)

        forceDownloadSynopsisAction = QtWidgets.QAction("Force Download Synopsis", self)
        forceDownloadSynopsisAction.triggered.connect(lambda: self.downloadSynopsisMenu(force=True))
        moviesTableRightMenu.addAction(forceDownloadSynopsisAction)

        moviesTableRightMenu.addSeparator()

        # OpenSubtitles download actions
        downloadOpenSubtitlesSelectAction = QtWidgets.QAction("Download Subtitles", self)
        downloadOpenSubtitlesSelectAction.triggered.connect(lambda: self.downloadSubtitles('select'))
        moviesTableRightMenu.addAction(downloadOpenSubtitlesSelectAction)

        downloadOpenSubtitlesAction = QtWidgets.QAction("Download English Subtitles", self)
        downloadOpenSubtitlesAction.triggered.connect(lambda: self.downloadSubtitles('en'))
        moviesTableRightMenu.addAction(downloadOpenSubtitlesAction)

        downloadSubtitlesAction = QtWidgets.QAction("Download Subtitles from YIFY", self)
        downloadSubtitlesAction.triggered.connect(self.downloadSubtitlesYify)
        moviesTableRightMenu.addAction(downloadSubtitlesAction)


        moviesTableRightMenu.addSeparator()

        filterBySubmenu = QtWidgets.QMenu("Filter by:")
        filterBySubmenu.setStyle(moviesTableRightMenu.style())
        moviesTableRightMenu.addMenu(filterBySubmenu)

        for c in self.collections:
            label = os.path.splitext(os.path.basename(c))[0]
            action = QtWidgets.QAction(f"Filter by {label} Collection", self)
            action.triggered.connect(lambda checked, collection=c: self.filterCollection(collection))
            filterBySubmenu.addAction(action)

        selectionModel = self.moviesTableView.selectionModel()
        if selectionModel and selectionModel.selectedRows():
            modelIndex = selectionModel.selectedRows()[0]
            self.clickedTable(modelIndex,
                              self.moviesTableModel,
                              self.moviesTableProxyModel)

        moviesTableRightMenu.exec_(QtGui.QCursor.pos())

    def tableSelectAll(self, table):
        # Select all rows in the proxy model (which are already filtered)
        table.selectAll()
        pass

    def findMovie(self, moviePath, folderName):
        """
        Find a movie folder, first checking the given path, then searching alternate folders.
        If multiple paths are found during fallback, prompts user to choose.
        
        Args:
            moviePath: The original/stored path to check first
            folderName: The folder name to search for (e.g., "MovieTitle(2020)")
        
        Returns:
            Full path to the movie folder if found, None otherwise
        """
        # First check if the original path exists
        if os.path.exists(moviePath):
            return moviePath
        
        # Build list of all folders to search
        foldersToSearch = []
        if self.moviesFolder and self.moviesFolder != "No movies folder set.  Use the \"File->Set movies folder\" menu to set it.":
            foldersToSearch.append(self.moviesFolder)
        if self.additionalMoviesFolders:
            foldersToSearch.extend(self.additionalMoviesFolders)
        
        # Search each folder for the movie and collect all matches
        foundPaths = []
        for folder in foldersToSearch:
            if not os.path.exists(folder):
                continue
            candidatePath = os.path.join(folder, folderName)
            if os.path.exists(candidatePath) and os.path.isdir(candidatePath):
                foundPaths.append(candidatePath)
        
        # Return based on number of matches found
        if len(foundPaths) == 0:
            return None
        elif len(foundPaths) == 1:
            return foundPaths[0]
        else:
            # Multiple paths found - ask user to choose
            selectedPath, ok = QtWidgets.QInputDialog.getItem(
                self,
                "Multiple Locations Found",
                f"Movie '{folderName}' found in multiple locations.\nSelect the path to open:",
                foundPaths,
                0,
                False
            )
            if ok and selectedPath:
                return selectedPath
            else:
                return None

    def playMovie(self, tableView, proxy):
        proxyIndex = tableView.selectionModel().selectedRows()[0]
        sourceIndex = proxy.mapToSource(proxyIndex)
        sourceRow = sourceIndex.row()
        moviePath = proxy.sourceModel().getPath(sourceRow)
        folderName = proxy.sourceModel().getFolderName(sourceRow)
        
        # Find the movie (checks stored path, then searches alternate folders)
        moviePath = self.findMovie(moviePath, folderName)
        if not moviePath:
            return

        validExtentions = ['.mkv', '.mpg', '.mp4', '.avi', '.flv', '.wmv', '.m4v', '.divx', '.ogm']

        movieFiles = []
        for file in os.listdir(moviePath):
            extension = os.path.splitext(file)[1].lower()
            if extension in validExtentions:
                movieFiles.append(file)
        if len(movieFiles) == 1:
            fileToPlay = os.path.join(moviePath, movieFiles[0])
            if os.path.exists(fileToPlay):
                runFile(fileToPlay)
        else:
            # If there are more than one movie like files in the
            # folder, then just open the folder so the user can
            # play the desired file.
            runFile(moviePath)

        # Record date watched
        now = datetime.datetime.now()
        dateWatched = f"{now.year}/{str(now.month).zfill(2)}/{str(now.day).zfill(2)} - " \
                      f"{str(now.hour).zfill(2)}:{str(now.minute).zfill(2)}"
        proxy.sourceModel().setDateWatched(sourceIndex, dateWatched)
        if moviePath in self.moviesSmdbData['titles']:
            self.moviesSmdbData['titles'][moviePath]['date watched'] = dateWatched

        if tableView != self.historyListWidget.listTableView:
            self.historyListAdd(tableView, proxy)

    def watchListAdd(self):
        """Delegate to WatchListWidget."""
        self.watchListWidget.listAdd()

    def historyListAdd(self, table, proxy):
        """Delegate to HistoryWidget."""
        self.historyListWidget.listAdd(table, proxy)

    def backupListAdd(self):
        """Delegate to BackupWidget."""
        self.backupListWidget.listAdd()
        # Update reference
        self.backupAnalysed = self.backupListWidget.analysed


    def addNewUserTag(self):
        userTag, ok = QtWidgets.QInputDialog.getText(self,
                                                     "User Tag",
                                                     "Enter new user tag",
                                                     QtWidgets.QLineEdit.Normal,
                                                     "")
        if userTag and ok:
            self.addUserTag(userTag)

    def addExistingUserTag(self):
        userTags = []
        if 'user tags' in self.moviesSmdbData:
            for tag in self.moviesSmdbData['user tags']:
                userTags.append(tag)
        userTag, ok = QtWidgets.QInputDialog.getItem(self,
                                                     "User Tag",
                                                     "Enter new user tag",
                                                     userTags,
                                                     0,
                                                     False)
        if userTag and ok:
            self.addUserTag(userTag)

    def clearUserTags(self):
        modelIndex = self.moviesTableView.selectionModel().selectedRows()[0]
        sourceIndex = self.moviesTableProxyModel.mapToSource(modelIndex)
        sourceRow = sourceIndex.row()
        moviePath = self.moviesTableModel.getPath(sourceRow)
        movieFolderName = self.moviesTableModel.getFolderName(sourceRow)

        jsonFile = os.path.join(moviePath, '%s.json' % movieFolderName)
        if not os.path.exists(jsonFile):
            return

        data = {}
        with open(jsonFile) as f:
            try:
                data = ujson.load(f)
            except UnicodeDecodeError:
                self.output("Error reading %s" % jsonFile)

        data["user tags"] = []

        try:
            with open(jsonFile, "w") as f:
                ujson.dump(data, f, indent=4)
        except:
            self.output("Error writing json file: %s" % jsonFile)

        self.moviesTableModel.setMovieData(sourceRow, data, moviePath, movieFolderName)

    def addUserTag(self, userTag):
        modelIndex = self.moviesTableView.selectionModel().selectedRows()[0]
        sourceIndex = self.moviesTableProxyModel.mapToSource(modelIndex)
        sourceRow = sourceIndex.row()
        moviePath = self.moviesTableModel.getPath(sourceRow)
        movieFolderName = self.moviesTableModel.getFolderName(sourceRow)

        jsonFile = os.path.join(moviePath, '%s.json' % movieFolderName)
        if not os.path.exists(jsonFile):
            return

        data = {}
        with open(jsonFile) as f:
            try:
                data = ujson.load(f)
            except UnicodeDecodeError:
                self.output("Error reading %s" % jsonFile)

        if "user tags" not in data:
            data["user tags"] = []

        if userTag not in data["user tags"]:
            data["user tags"].append(userTag)

        try:
            with open(jsonFile, "w") as f:
                ujson.dump(data, f, indent=4)
        except:
            self.output("Error writing json file: %s" % jsonFile)

        self.moviesTableModel.setMovieData(sourceRow, data, moviePath, movieFolderName)

        if 'user tags' in self.moviesSmdbData:
            if userTag in self.moviesSmdbData['user tags']:
                numMovies = self.moviesSmdbData['user tags'][userTag]['num movies']
                self.moviesSmdbData['user tags'][userTag]['num movies'] = numMovies + 1
            else:
                self.moviesSmdbData['user tags'][userTag] = {}
                self.moviesSmdbData['user tags'][userTag]['movies'] = []
                self.moviesSmdbData['user tags'][userTag]['num movies'] = 1

            title = self.moviesTableModel.getTitle(sourceRow)
            year = self.moviesTableModel.getYear(sourceRow)
            titleYear = (title, year)

            self.moviesSmdbData['user tags'][userTag]['movies'].append(titleYear)

    class MoveTo(Enum):
        DOWN = 0
        UP = 1
        TOP = 2

    def getSelectedRow(self):
        proxyIndex = self.moviesTableView.selectionModel().selectedRows()[0]
        sourceIndex = self.moviesTableProxyModel.mapToSource(proxyIndex)
        return sourceIndex.row()

    def getSourceRow(self, proxyIndex):
        return self.moviesTableProxyModel.mapToSource(proxyIndex).row()

    def getSourceRow2(self, row):
        return self.moviesTableProxyModel.mapToSource(self.moviesTableProxyModel.index(row, 0)).row()

    def getProxyRow(self, sourceRow):
        return self.moviesTableProxyModel.mapFromSource(self.moviesTableModel.index(sourceRow, 0)).row()

    def openMovieFolder(self):
        sourceRow = self.getSelectedRow()
        moviePath = self.moviesTableModel.getPath(sourceRow)
        folderName = self.moviesTableModel.getFolderName(sourceRow)
        
        # Find the movie (checks stored path, then searches alternate folders)
        moviePath = self.findMovie(moviePath, folderName)
        if not moviePath:
            self.output("Folder doesn't exist")
            return
        
        runFile(moviePath)

    def openMovieJson(self):
        sourceRow = self.getSelectedRow()
        moviePath = self.moviesTableModel.getPath(sourceRow)
        folderName = self.moviesTableModel.getFolderName(sourceRow)
        
        # Find the movie (checks stored path, then searches alternate folders)
        moviePath = self.findMovie(moviePath, folderName)
        if not moviePath:
            self.output("Folder doesn't exist")
            return
        
        jsonFile = os.path.join(moviePath, '%s.json' % folderName)
        if os.path.exists(jsonFile):
            runFile(jsonFile)
        else:
            self.output("jsonFile: %s doesn't exist" % jsonFile)

    def openMovieImdbPage(self):
        sourceRow = self.getSelectedRow()
        movieId = self.moviesTableModel.getId(sourceRow)
        if 'http://' in movieId or 'https://' in movieId:
            open_url(movieId, new=2)
        else:
            if 'tt' in movieId: movieId = movieId.replace('tt', '')
            open_url('http://imdb.com/title/tt%s' % movieId, new=2)

    def downloadSubtitlesYify(self):
        sourceRow = self.getSelectedRow()
        movieId = self.moviesTableModel.getId(sourceRow)
        if 'tt' in movieId: movieId = movieId.replace('tt', '')
        open_url(f'https://yifysubtitles.org/movie-imdb/tt{movieId}', new=2)

    def downloadSubtitles(self, language='en'):
        try:
            sourceRow = self.getSelectedRow()
        except Exception:
            return

        # Resolve IMDb ID (numeric, without 'tt')
        movieId = self.moviesTableModel.getId(sourceRow)
        if isinstance(movieId, str) and 'tt' in movieId:
            movieId = movieId.replace('tt', '')
        imdb_id = str(movieId).strip()
        if not imdb_id.isdigit():
            QtWidgets.QMessageBox.warning(self, "OpenSubtitles", "Unable to determine IMDb ID for this title.")
            return

        # Resolve movie path and a target base filename
        moviePath = self.moviesTableModel.getPath(sourceRow)
        folderName = self.moviesTableModel.getFolderName(sourceRow)
        moviePath = self.findMovie(moviePath, folderName)
        if not os.path.exists(moviePath):
            QtWidgets.QMessageBox.warning(self, "OpenSubtitles", "Movie folder does not exist on disk.")
            return

        baseName = str(folderName)
        displayTitle = f"{self.moviesTableModel.getTitle(sourceRow)} ({self.moviesTableModel.getYear(sourceRow)})"
        selecting_mode = (language == 'select')
        language_label = {
            'en': 'English', 'es': 'Spanish', 'fr': 'French', 'pt': 'Portuguese', 'de': 'German',
            'it': 'Italian', 'nl': 'Dutch', 'pl': 'Polish', 'ru': 'Russian', 'sv': 'Swedish',
            'fi': 'Finnish', 'no': 'Norwegian', 'da': 'Danish', 'hu': 'Hungarian', 'cs': 'Czech',
            'ro': 'Romanian', 'el': 'Greek', 'tr': 'Turkish', 'ar': 'Arabic', 'he': 'Hebrew',
            'fa': 'Persian', 'zh': 'Chinese', 'ja': 'Japanese', 'ko': 'Korean'
        }.get(language, language)

        # For the 'select' language flow, skip early subtitle existence check.
        # Otherwise, keep the current behavior and avoid redundant downloads.
        if not selecting_mode:
            existing_srts = [f for f in os.listdir(moviePath) if f.lower().endswith('.srt')]
            if existing_srts:
                QtWidgets.QMessageBox.information(self,
                                                  "OpenSubtitles",
                                                  f"A subtitle already exists in this folder:\n{os.path.join(moviePath, existing_srts[0])}")
                return

        # Query OpenSubtitles API
        headers = {
            'Api-Key': self.openSubtitlesApiKey,
            'Accept': 'application/json',
            'User-Agent': 'SMDB/1.0'
        }

        # If user chose to select language, fetch available languages first
        if language == 'select':
            params_select = {
                'imdb_id': imdb_id,
                'order_by': 'downloads',
                'order_direction': 'desc',
                'type': 'movie'
            }
            try:
                r_pre = requests.get("https://api.opensubtitles.com/api/v1/subtitles", params=params_select, headers=headers, timeout=20)
                if r_pre.status_code == 403:
                    newKey, ok = QtWidgets.QInputDialog.getText(self, "OpenSubtitles API Key",
                                                               "Access forbidden (403). Enter a valid OpenSubtitles API key:",
                                                               text=self.openSubtitlesApiKey)
                    if ok and newKey:
                        self.openSubtitlesApiKey = newKey
                        headers['Api-Key'] = newKey
                        r_pre = requests.get("https://api.opensubtitles.com/api/v1/subtitles", params=params_select, headers=headers, timeout=20)
                r_pre.raise_for_status()
                items_pre = (r_pre.json() or {}).get('data') or []
                # Collect available languages
                seen = set()
                langs = []  # list of (code, name)
                for it in items_pre:
                    attr = it.get('attributes', {})
                    code = attr.get('language')
                    name = attr.get('language_name') or code
                    if code and code not in seen:
                        langs.append((code, name))
                        seen.add(code)
                if not langs:
                    QtWidgets.QMessageBox.information(self, "OpenSubtitles", f"No subtitles found for {displayTitle}.")
                    return
                # Build selection list
                options = [f"{name} ({code})" for code, name in langs]
                preselect = 0
                for i, (code, _) in enumerate(langs):
                    if code == 'en':
                        preselect = i
                        break
                selected, ok = QtWidgets.QInputDialog.getItem(self,
                                                              "Select Subtitle Language",
                                                              "Available languages:",
                                                              options,
                                                              preselect,
                                                              False)
                if not ok or not selected:
                    return
                # Parse selection to language code
                sel_code = selected[selected.rfind('(')+1:selected.rfind(')')].strip()
                # Find human label
                sel_name = next((name for code, name in langs if code == sel_code), sel_code)
                language = sel_code
                language_label = sel_name
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "OpenSubtitles", f"Failed to list languages: {e}")
                return

        # For English, omit the .en and save as <base>.srt
        if language == 'en':
            targetPath = os.path.join(moviePath, f"{baseName}.srt")
        else:
            targetPath = os.path.join(moviePath, f"{baseName}.{language}.srt")

        # In 'select' mode, now that we have the chosen language, check
        # if a subtitle with the target filename already exists.
        if selecting_mode and os.path.exists(targetPath):
            QtWidgets.QMessageBox.information(self,
                                              "OpenSubtitles",
                                              f"A subtitle for the selected language already exists:\n{targetPath}")
            return

        params = {
            'imdb_id': imdb_id,
            'languages': language,
            'order_by': 'downloads',
            'order_direction': 'desc',
            'type': 'movie'
        }

        try:
            self.statusBar().showMessage("Searching OpenSubtitlesâ€¦", 5000)
            r = requests.get("https://api.opensubtitles.com/api/v1/subtitles", params=params, headers=headers, timeout=20)
            if r.status_code == 403:
                # Allow user to provide a valid API key, then retry once
                newKey, ok = QtWidgets.QInputDialog.getText(self, "OpenSubtitles API Key",
                                                           "Access forbidden (403). Enter a valid OpenSubtitles API key:",
                                                           text=self.openSubtitlesApiKey)
                if ok and newKey:
                    self.openSubtitlesApiKey = newKey
                    headers['Api-Key'] = newKey
                    r = requests.get("https://api.opensubtitles.com/api/v1/subtitles", params=params, headers=headers, timeout=20)
            r.raise_for_status()
            data = r.json()
            items = data.get('data') or []
            if not items:
                QtWidgets.QMessageBox.information(self, "OpenSubtitles", f"No subtitles found ({language_label}) for {displayTitle}.")
                return

            # Pick the first file entry
            files = items[0].get('attributes', {}).get('files', [])
            if not files:
                QtWidgets.QMessageBox.information(self, "OpenSubtitles", f"No downloadable files found for {displayTitle}.")
                return
            file_id = files[0].get('file_id')
            if not file_id:
                QtWidgets.QMessageBox.information(self, "OpenSubtitles", "Subtitle file id missing.")
                return

            # Include content type for POST
            post_headers = dict(headers)
            post_headers['Content-Type'] = 'application/json'
            dl = requests.post("https://api.opensubtitles.com/api/v1/download", json={"file_id": file_id}, headers=post_headers, timeout=20)
            if dl.status_code == 403:
                # Retry once if API key was updated by user earlier
                dl = requests.post("https://api.opensubtitles.com/api/v1/download", json={"file_id": file_id}, headers=post_headers, timeout=20)
            dl.raise_for_status()
            dl_json = dl.json()
            link = dl_json.get('link')
            if not link:
                QtWidgets.QMessageBox.warning(self, "OpenSubtitles", "Download link not provided by API.")
                return

            # Download the actual subtitle file
            resp = requests.get(link, timeout=60)
            resp.raise_for_status()

            content_type = resp.headers.get('Content-Type', '')
            saved = False
            if 'zip' in content_type.lower() or link.lower().endswith('.zip'):
                # Extract first .srt from the zip
                with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
                    # Prefer .srt, else take first file
                    srt_names = [n for n in zf.namelist() if n.lower().endswith('.srt')]
                    name_to_extract = srt_names[0] if srt_names else (zf.namelist()[0] if zf.namelist() else None)
                    if not name_to_extract:
                        QtWidgets.QMessageBox.warning(self, "OpenSubtitles", "Downloaded archive is empty.")
                        return
                    with zf.open(name_to_extract) as zf_member, open(targetPath, 'wb') as out:
                        out.write(zf_member.read())
                        saved = True
            else:
                # Assume direct subtitle content
                with open(targetPath, 'wb') as f:
                    f.write(resp.content)
                    saved = True

            if saved:
                # Inform user first that subtitle has been downloaded
                self.statusBar().showMessage(f"Subtitle saved: {targetPath}", 5000)
                QtWidgets.QMessageBox.information(self, "OpenSubtitles", f"Subtitle downloaded to:\n{targetPath}")

                # After saving, ensure there is a video file with the same base name
                base_sub = os.path.splitext(os.path.basename(targetPath))[0]
                # Omit language suffix from the base when matching video files
                base_for_video = base_sub
                try:
                    if language and language != 'en' and base_for_video.endswith(f".{language}"):
                        base_for_video = base_for_video[:-(len(language)+1)]
                except Exception:
                    pass
                video_exts = ['.mp4', '.avi', '.mkv']
                expected_exists = any(os.path.exists(os.path.join(moviePath, base_for_video + ext)) for ext in video_exts)
                if not expected_exists:
                    # Find candidate video files to optionally rename
                    candidates = [f for f in os.listdir(moviePath) if os.path.splitext(f)[1].lower() in video_exts]
                    chosen = None
                    if len(candidates) == 1:
                        ans = QtWidgets.QMessageBox.question(
                            self,
                            "Rename Video",
                            f"No video named '{base_for_video}.mp4/.avi/.mkv' found.\n"
                            f"Found '{candidates[0]}'.\n\n"
                            f"Rename it to '{base_for_video}{os.path.splitext(candidates[0])[1]}'?",
                            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                            QtWidgets.QMessageBox.Yes)
                        if ans == QtWidgets.QMessageBox.Yes:
                            chosen = candidates[0]
                    elif len(candidates) > 1:
                        chosen, ok = QtWidgets.QInputDialog.getItem(
                            self,
                            "Rename Video",
                            "Select a video file to rename to match the subtitle base name:",
                            candidates,
                            0,
                            False)
                        if not ok:
                            chosen = None

                    if chosen:
                        old_path = os.path.join(moviePath, chosen)
                        new_path = os.path.join(moviePath, base_for_video + os.path.splitext(chosen)[1])
                        if os.path.exists(new_path):
                            QtWidgets.QMessageBox.warning(self, "Rename Video", f"Cannot rename. Target already exists:\n{new_path}")
                        else:
                            try:
                                os.rename(old_path, new_path)
                                self.statusBar().showMessage(f"Renamed video to: {os.path.basename(new_path)}", 5000)
                            except Exception as e:
                                QtWidgets.QMessageBox.critical(self, "Rename Video", f"Failed to rename file:\n{e}")
        except requests.HTTPError as e:
            try:
                code = e.response.status_code if e.response is not None else None
            except Exception:
                code = None
            if code in (401, 403):
                # Offer to open OpenSubtitles web search as fallback
                open_web = QtWidgets.QMessageBox.question(self, "OpenSubtitles",
                                                          f"Access denied (HTTP {code}). Open the OpenSubtitles website instead?",
                                                          QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                                                          QtWidgets.QMessageBox.Yes)
                if open_web == QtWidgets.QMessageBox.Yes:
                    open_url(f"https://www.opensubtitles.org/en/search2/sublanguageid-eng/imdbid-{imdb_id}", new=2)
            else:
                QtWidgets.QMessageBox.critical(self, "OpenSubtitles", f"HTTP error: {e}")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "OpenSubtitles", f"Error downloading subtitles: {e}")

    def get_imdb_movie_page(self, title, year):
        # Format the search query
        query = f"{title} {year}"

        # Encode the query for use in a URL
        encoded_query = urllib.parse.quote(query)

        # Construct the IMDb search URL
        url = f"https://www.imdb.com/find?q={encoded_query}&s=tt&ttype=ft"

        return url

    def get_youtube_search_url(self, query):
        base_url = "https://www.youtube.com/results"
        encoded_query = urllib.parse.quote(query)
        return f"{base_url}?search_query={encoded_query}"

    def get_prime_video_search_url(self, query):
        base_url = "https://www.amazon.com/s"
        encoded_query = urllib.parse.quote(query)
        return f"{base_url}?k={encoded_query}&i=instant-video"

    def searchForOtherVersions(self):
        sourceRow = self.getSelectedRow()
        title = self.moviesTableModel.getTitle(sourceRow)
        titlePlus = '+'.join(title.split())
        titleMinus = '-'.join(title.split())
        year = self.moviesTableModel.getYear(sourceRow)
        urlPirateBay = f"https://thepiratebay.org/search.php?q={titlePlus}+%28{year}%29&all=on&search=Pirate+Search&page=0&orderby="
        url1337x = f"https://1337x.to/search/{titlePlus}+{year}/1/"
        usrlLimeTorrents = f"https://www.limetorrents.info/search/all/{titleMinus}-%20{year}%20/"
        urlYts = f"https://yts.mx/movies/{titleMinus.lower()}-{year}"
        urlImdb = self.get_imdb_movie_page(title, year)
        urlYt = self.get_youtube_search_url(f"{title} {year}")
        urlAmz = self.get_prime_video_search_url(f"{title} {year}")
        urls = [urlPirateBay, url1337x, usrlLimeTorrents, urlYts, urlImdb, urlYt, urlAmz]
        for u in urls:
            open_url(u, new=2)

    def overrideID(self):
        movieId, ok = QtWidgets.QInputDialog.getText(self,
                                                     "Override ID",
                                                     "Enter new ID",
                                                     QtWidgets.QLineEdit.Normal,
                                                     "")
        if movieId and ok:
            modelIndex = self.moviesTableView.selectionModel().selectedRows()[0]
            self.movieData.downloadMovieData(modelIndex, True, movieId)

    def downloadDataMenu(self, force=False, doJson=True, doCover=True):
        numSelectedItems = len(self.moviesTableView.selectionModel().selectedRows())
        self.progressBar.setMaximum(numSelectedItems)
        progress = 0
        self.isCanceled = False
        import time
        start_time = time.time()
        
        for proxyIndex in self.moviesTableView.selectionModel().selectedRows():
            QtCore.QCoreApplication.processEvents()
            if self.isCanceled:
                self.statusBar().showMessage('Cancelled')
                self.isCanceled = False
                self.progressBar.setValue(0)
                return

            progress += 1
            self.progressBar.setValue(progress)

            # Calculate ETA
            if progress > 0:
                elapsed_time = time.time() - start_time
                avg_time_per_item = elapsed_time / progress
                remaining_items = numSelectedItems - progress
                eta_seconds = avg_time_per_item * remaining_items
                
                if eta_seconds < 60:
                    eta_str = f"{int(eta_seconds)}s"
                else:
                    eta_minutes = int(eta_seconds / 60)
                    eta_secs = int(eta_seconds % 60)
                    eta_str = f"{eta_minutes}m {eta_secs}s"
                
                message = "Downloading data (%d/%d) - ETA: %s" % (progress, numSelectedItems, eta_str)
            else:
                message = "Downloading data (%d/%d)" % (progress, numSelectedItems)
            
            self.statusBar().showMessage(message)
            QtCore.QCoreApplication.processEvents()

            sourceRow = self.getSourceRow(proxyIndex)
            movieFolderName = self.moviesTableModel.getFolderName(sourceRow)
            moviePath = self.moviesTableModel.getPath(sourceRow)
            moviePath = self.findMovie(moviePath, movieFolderName)
            if not os.path.exists(moviePath):
                continue

            self.movieData.downloadMovieData(proxyIndex, force, doJson=doJson, doCover=doCover)
            self.moviesTableView.selectRow(proxyIndex.row())
            self.clickedTable(proxyIndex,
                              self.moviesTableModel,
                              self.moviesTableProxyModel)

        self.progressBar.setValue(0)

    def downloadSynopsisMenu(self, force=False):
        """Download Wikipedia synopsis for selected movies.
        
        Args:
            force: If True, download even if synopsis already exists
        """
        numSelectedItems = len(self.moviesTableView.selectionModel().selectedRows())
        self.progressBar.setMaximum(numSelectedItems)
        progress = 0
        self.isCanceled = False
        import time
        start_time = time.time()
        
        downloaded_count = 0
        skipped_count = 0
        failed_count = 0
        
        for proxyIndex in self.moviesTableView.selectionModel().selectedRows():
            QtCore.QCoreApplication.processEvents()
            if self.isCanceled:
                self.statusBar().showMessage('Cancelled')
                self.isCanceled = False
                self.progressBar.setValue(0)
                return

            progress += 1
            self.progressBar.setValue(progress)

            # Calculate ETA
            if progress > 0:
                elapsed_time = time.time() - start_time
                avg_time_per_item = elapsed_time / progress
                remaining_items = numSelectedItems - progress
                eta_seconds = avg_time_per_item * remaining_items
                
                if eta_seconds < 60:
                    eta_str = f"{int(eta_seconds)}s"
                else:
                    eta_minutes = int(eta_seconds / 60)
                    eta_secs = int(eta_seconds % 60)
                    eta_str = f"{eta_minutes}m {eta_secs}s"
                
                message = "Downloading synopsis (%d/%d) - ETA: %s" % (progress, numSelectedItems, eta_str)
            else:
                message = "Downloading synopsis (%d/%d)" % (progress, numSelectedItems)
            
            self.statusBar().showMessage(message)
            QtCore.QCoreApplication.processEvents()

            sourceRow = self.getSourceRow(proxyIndex)
            movieFolderName = self.moviesTableModel.getFolderName(sourceRow)
            moviePath = self.moviesTableModel.getPath(sourceRow)
            moviePath = self.findMovie(moviePath, movieFolderName)
            if not os.path.exists(moviePath):
                failed_count += 1
                continue

            jsonFile = os.path.join(moviePath, '%s.json' % movieFolderName)
            
            # Check if JSON file exists
            if not os.path.exists(jsonFile):
                self.output(f"No JSON file for {movieFolderName}, skipping...")
                failed_count += 1
                continue
            
            # Load existing JSON
            try:
                with open(jsonFile, 'r', encoding='utf-8') as f:
                    jsonData = ujson.load(f)
            except Exception as e:
                self.output(f"Error reading JSON for {movieFolderName}: {e}")
                failed_count += 1
                continue
            
            # Get title and year from JSON
            title = jsonData.get('title')
            year = jsonData.get('year')
            
            if not title:
                self.output(f"No title in JSON for {movieFolderName}, skipping...")
                failed_count += 1
                continue
            
            # Check if synopsis already exists
            existing_synopsis = jsonData.get('synopsis')
            existing_plot = jsonData.get('plot')
            
            # Download if: force mode, no synopsis exists, or synopsis is the same as plot
            should_download = force or not existing_synopsis or (existing_synopsis == existing_plot)
            
            if not should_download:
                self.output(f"Synopsis already exists for {movieFolderName}, skipping...")
                skipped_count += 1
                continue
            
            if existing_synopsis == existing_plot and existing_synopsis:
                self.output(f"Synopsis is same as plot for {movieFolderName}, downloading new synopsis...")
            
            # Download synopsis from Wikipedia
            self.output(f"Fetching Wikipedia synopsis for '{title}' ({year})...")
            synopsis = self.movieData._getWikipediaPlot(title, year)
            
            if synopsis:
                # Add synopsis to JSON data
                jsonData['synopsis'] = synopsis
                
                # Write updated JSON
                try:
                    with open(jsonFile, 'w', encoding='utf-8') as f:
                        ujson.dump(jsonData, f, indent=4)
                    self.output(f"Successfully added synopsis ({len(synopsis)} characters)")
                    downloaded_count += 1
                except Exception as e:
                    self.output(f"Error writing JSON for {movieFolderName}: {e}")
                    failed_count += 1
            else:
                # No Wikipedia synopsis found
                # If synopsis was same as plot, remove the duplicate synopsis
                if existing_synopsis == existing_plot and existing_synopsis:
                    self.output(f"No Wikipedia synopsis found and existing synopsis duplicates plot - removing duplicate synopsis")
                    if 'synopsis' in jsonData:
                        del jsonData['synopsis']
                        # Write updated JSON
                        try:
                            with open(jsonFile, 'w', encoding='utf-8') as f:
                                ujson.dump(jsonData, f, indent=4)
                            self.output(f"Removed duplicate synopsis from {movieFolderName}")
                            skipped_count += 1
                        except Exception as e:
                            self.output(f"Error writing JSON for {movieFolderName}: {e}")
                            failed_count += 1
                else:
                    self.output(f"No Wikipedia synopsis found for '{title}' ({year})")
                    failed_count += 1
            
            # Update the view
            self.moviesTableView.selectRow(proxyIndex.row())
            self.clickedTable(proxyIndex,
                              self.moviesTableModel,
                              self.moviesTableProxyModel)
        
        self.progressBar.setValue(0)
        
        # Show summary
        summary = f"Synopsis download complete: {downloaded_count} downloaded, {skipped_count} skipped, {failed_count} failed"
        self.statusBar().showMessage(summary)
        self.output(summary)

    def downloadMissingDataMenu(self):
        """Download missing data fields for selected movies.
        
        Checks existing JSON files to identify missing fields and downloads only those.
        Also checks for missing poster files.
        
        Full dataset fields checked:
        - title, id, year, rating, mpaa rating
        - directors, cast, writers, producers, composers
        - genres, countries, companies
        - runtime, box office, plot, synopsis
        - keywords, tagline, budget, revenue
        - cover url, poster file
        - size, width, height, channels (file info)
        """
        # Ensure API keys are available before proceeding
        if not self.movieData._ensureApiKeys():
            return
        
        numSelectedItems = len(self.moviesTableView.selectionModel().selectedRows())
        self.progressBar.setMaximum(numSelectedItems)
        progress = 0
        self.isCanceled = False
        import time
        start_time = time.time()
        
        downloaded_count = 0
        skipped_count = 0
        failed_count = 0
        
        # Track what was downloaded
        missing_fields_count = collections.defaultdict(int)
        
        for proxyIndex in self.moviesTableView.selectionModel().selectedRows():
            QtCore.QCoreApplication.processEvents()
            if self.isCanceled:
                self.statusBar().showMessage('Cancelled')
                self.isCanceled = False
                self.progressBar.setValue(0)
                return

            progress += 1
            self.progressBar.setValue(progress)

            # Calculate ETA
            if progress > 0:
                elapsed_time = time.time() - start_time
                avg_time_per_item = elapsed_time / progress
                remaining_items = numSelectedItems - progress
                eta_seconds = avg_time_per_item * remaining_items
                
                if eta_seconds < 60:
                    eta_str = f"{int(eta_seconds)}s"
                else:
                    eta_minutes = int(eta_seconds / 60)
                    eta_secs = int(eta_seconds % 60)
                    eta_str = f"{eta_minutes}m {eta_secs}s"
                
                message = "Downloading missing data (%d/%d) - ETA: %s" % (progress, numSelectedItems, eta_str)
            else:
                message = "Downloading missing data (%d/%d)" % (progress, numSelectedItems)
            
            self.statusBar().showMessage(message)
            QtCore.QCoreApplication.processEvents()

            sourceRow = self.getSourceRow(proxyIndex)
            movieFolderName = self.moviesTableModel.getFolderName(sourceRow)
            moviePath = self.moviesTableModel.getPath(sourceRow)
            moviePath = self.findMovie(moviePath, movieFolderName)
            if not os.path.exists(moviePath):
                failed_count += 1
                continue

            jsonFile = os.path.join(moviePath, '%s.json' % movieFolderName)
            coverFile = os.path.join(moviePath, '%s.jpg' % movieFolderName)
            if not os.path.exists(coverFile):
                coverFilePng = os.path.join(moviePath, '%s.png' % movieFolderName)
                if os.path.exists(coverFilePng):
                    coverFile = coverFilePng
            
            # Check if JSON file exists
            if not os.path.exists(jsonFile):
                self.output(f"No JSON file for {movieFolderName}, using regular download...")
                self.movieData.downloadMovieData(proxyIndex, force=False, doJson=True, doCover=True)
                downloaded_count += 1
                continue
            
            # Load existing JSON
            try:
                with open(jsonFile, 'r', encoding='utf-8') as f:
                    jsonData = ujson.load(f)
            except Exception as e:
                self.output(f"Error reading JSON for {movieFolderName}: {e}")
                failed_count += 1
                continue
            
            # Define expected fields from the full dataset
            expected_fields = {
                'title': 'Title',
                'id': 'IMDb ID',
                'year': 'Year',
                'rating': 'Rating',
                'mpaa rating': 'MPAA Rating',
                'directors': 'Directors',
                'cast': 'Cast',
                'writers': 'Writers',
                'producers': 'Producers',
                'composers': 'Composers',
                'genres': 'Genres',
                'countries': 'Countries',
                'companies': 'Companies',
                'runtime': 'Runtime',
                'box office': 'Box Office',
                'plot': 'Plot',
                'synopsis': 'Synopsis',
                'keywords': 'Keywords',
                'tagline': 'Tagline',
                'budget': 'Budget',
                'revenue': 'Revenue',
                'cover url': 'Cover URL',
                'size': 'File Size',
                'width': 'Video Width',
                'height': 'Video Height',
                'channels': 'Audio Channels'
            }
            
            # Check which fields are missing or empty
            missing_fields = []
            for field, display_name in expected_fields.items():
                value = jsonData.get(field)
                # Consider field missing if it doesn't exist, is None, empty string, or empty list
                if value is None or value == '' or value == [] or value == {}:
                    missing_fields.append(field)
                    missing_fields_count[display_name] += 1
            
            # Check if poster file is missing
            poster_missing = not os.path.exists(coverFile)
            if poster_missing:
                missing_fields_count['Poster File'] += 1
            
            # If nothing is missing, skip
            if not missing_fields and not poster_missing:
                self.output(f"All data present for {movieFolderName}, skipping...")
                skipped_count += 1
                continue
            
            # Log what's missing with separator line
            self.output("")  # Blank separator line
            missing_display = [expected_fields.get(f, f) for f in missing_fields]
            if poster_missing:
                missing_display.append('Poster File')
            self.output(f"Missing data for {movieFolderName}: {', '.join(missing_display)}")
            
            # Download the missing data
            try:
                title = jsonData.get('title')
                year = jsonData.get('year')
                imdbId = jsonData.get('id')
                
                if not title:
                    self.output(f"No title in JSON for {movieFolderName}, cannot download missing data")
                    failed_count += 1
                    continue
                
                # Get the IMDb ID if missing
                if not imdbId:
                    imdbId = self.movieData._resolveImdbId(title, year)
                    if not imdbId:
                        self.output(f"Could not resolve IMDb ID for {movieFolderName}")
                        failed_count += 1
                        continue
                
                # Fetch fresh data from TMDB/OMDb
                movie = self.movieData._getMovieTmdb(title, year, imdbId)
                if not movie:
                    self.output(f"TMDB lookup failed, trying OMDb for {movieFolderName}")
                    movie = self.movieData._getMovieOmdb(title, year, imdbId)
                
                if not movie:
                    self.output(f"Could not fetch movie data for {movieFolderName}")
                    failed_count += 1
                    continue
                
                # Update only missing fields in the JSON
                updated = False
                
                # Map downloaded data to JSON fields
                field_mapping = {
                    'title': lambda m: m.get('Title'),
                    'id': lambda m: m.get('ImdbID') or m.get('imdbID'),
                    'year': lambda m: m.get('Year'),
                    'rating': lambda m: m.get('ImdbRating') or m.get('imdbRating'),
                    'mpaa rating': lambda m: m.get('Rated'),
                    'runtime': lambda m: m.get('Runtime', '').split()[0] if m.get('Runtime') else None,
                    'box office': lambda m: m.get('BoxOffice'),
                    'plot': lambda m: m.get('Plot'),
                    'synopsis': lambda m: m.get('Synopsis'),
                    'tagline': lambda m: m.get('Tagline'),
                    'budget': lambda m: m.get('Budget'),
                    'revenue': lambda m: m.get('Revenue'),
                    'cover url': lambda m: m.get('Poster'),
                }
                
                # Handle list fields
                def get_list_field(data, field_name):
                    """Get a list field from movie data, handling both list and string formats."""
                    value = data.get(field_name)
                    if value is None:
                        return None
                    if isinstance(value, list):
                        return value if value else None
                    if isinstance(value, str):
                        result = [v.strip() for v in value.split(',') if v.strip()]
                        return result if result else None
                    return None
                
                list_field_mapping = {
                    'directors': lambda m: get_list_field(m, 'Directors'),
                    'cast': lambda m: get_list_field(m, 'Actors'),
                    'writers': lambda m: m.get('Writers') if isinstance(m.get('Writers'), list) else None,
                    'producers': lambda m: m.get('Producers') if isinstance(m.get('Producers'), list) else None,
                    'composers': lambda m: m.get('Composers') if isinstance(m.get('Composers'), list) else None,
                    'genres': lambda m: get_list_field(m, 'Genres'),
                    'countries': lambda m: (m.get('Countries') if isinstance(m.get('Countries'), list) 
                                          else get_list_field(m, 'Country')),
                    'companies': lambda m: m.get('ProductionCompanies') if isinstance(m.get('ProductionCompanies'), list) else None,
                    'keywords': lambda m: m.get('Keywords') if isinstance(m.get('Keywords'), list) else None,
                }
                
                # Update scalar fields
                for field, getter in field_mapping.items():
                    if field in missing_fields:
                        new_value = getter(movie)
                        if new_value is not None and new_value != '':
                            jsonData[field] = new_value
                            updated = True
                
                # Update list fields
                for field, getter in list_field_mapping.items():
                    if field in missing_fields:
                        new_value = getter(movie)
                        if new_value is not None:
                            jsonData[field] = new_value
                            updated = True
                
                # Update file info if missing
                if any(f in missing_fields for f in ['size', 'width', 'height', 'channels']):
                    self.movieData._getMovieFileInfo(moviePath, movie)
                    if 'size' in missing_fields and movie.get('size'):
                        jsonData['size'] = movie['size']
                        updated = True
                    if 'width' in missing_fields and movie.get('width'):
                        jsonData['width'] = movie['width']
                        updated = True
                    if 'height' in missing_fields and movie.get('height'):
                        jsonData['height'] = movie['height']
                        updated = True
                    if 'channels' in missing_fields and movie.get('channels'):
                        jsonData['channels'] = movie['channels']
                        updated = True
                
                # Write updated JSON if anything changed
                if updated:
                    try:
                        with open(jsonFile, 'w', encoding='utf-8') as f:
                            ujson.dump(jsonData, f, indent=4)
                        self.output(f"Updated JSON for {movieFolderName}")
                    except Exception as e:
                        self.output(f"Error writing JSON for {movieFolderName}: {e}")
                        failed_count += 1
                        continue
                
                # Download poster if missing
                if poster_missing:
                    movieCoverUrl = None
                    coverDownloaded = False
                    
                    # Try OMDB first for cover
                    omdb_data = self.movieData._getMovieOmdb(title, year, imdbId)
                    if omdb_data and omdb_data.get('Poster') and omdb_data['Poster'] != 'N/A':
                        movieCoverUrl = omdb_data['Poster']
                        try:
                            urllib.request.urlretrieve(movieCoverUrl, coverFile)
                            coverDownloaded = True
                            self.output(f"Downloaded cover from OMDb for {movieFolderName}")
                        except Exception as e:
                            self.output(f"OMDb cover download failed: {e}")
                    
                    # Fallback to TMDB if OMDB failed
                    if not coverDownloaded:
                        if 'PosterFullSize' in movie:
                            movieCoverUrl = movie['PosterFullSize']
                        elif 'Poster' in movie:
                            movieCoverUrl = movie['Poster']
                        
                        if movieCoverUrl:
                            try:
                                urllib.request.urlretrieve(movieCoverUrl, coverFile)
                                self.output(f"Downloaded cover from TMDB for {movieFolderName}")
                            except Exception as e:
                                self.output(f"TMDB cover download failed: {e}")
                        else:
                            self.output(f"No cover image available for {movieFolderName}")
                
                downloaded_count += 1
                
                # Update the view
                self.moviesTableModel.setMovieDataWithJson(sourceRow,
                                                          jsonFile,
                                                          moviePath,
                                                          movieFolderName)
                self.moviesTableView.selectRow(proxyIndex.row())
                self.clickedTable(proxyIndex,
                                  self.moviesTableModel,
                                  self.moviesTableProxyModel)
                
            except Exception as e:
                self.output(f"Error downloading missing data for {movieFolderName}: {e}")
                import traceback
                self.output(traceback.format_exc())
                failed_count += 1
        
        self.progressBar.setValue(0)
        
        # Show summary
        summary = f"Missing data download complete: {downloaded_count} updated, {skipped_count} skipped, {failed_count} failed"
        self.statusBar().showMessage(summary)
        self.output(summary)
        
        # Show detailed breakdown of what was missing
        if missing_fields_count:
            self.output("\nMissing fields breakdown:")
            for field, count in sorted(missing_fields_count.items(), key=lambda x: x[1], reverse=True):
                self.output(f"  {field}: {count} movies")

    def removeJsonFilesMenu(self):
        filesToDelete = []
        for modelIndex in self.moviesTableView.selectionModel().selectedRows():
            sourceRow = self.getSourceRow(modelIndex)
            moviePath = self.moviesTableModel.getPath(sourceRow)
            movieFolder = self.moviesTableModel.getFolderName(sourceRow)
            jsonFile = os.path.join(moviePath, '%s.json' % movieFolder)
            if os.path.exists(jsonFile):
                filesToDelete.append(os.path.join(moviePath, jsonFile))
        removeFiles(self, filesToDelete, '.json')

    def removeCoverFilesMenu(self):
        filesToDelete = []
        for modelIndex in self.moviesTableView.selectionModel().selectedRows():
            sourceRow = self.getSourceRow(modelIndex)
            moviePath = self.moviesTableModel.getPath(sourceRow)
            movieFolder = self.moviesTableModel.getFolderName(sourceRow)

            coverFile = os.path.join(moviePath, '%s.jpg' % movieFolder)
            if os.path.exists(coverFile):
                filesToDelete.append(coverFile)
            else:
                coverFile = os.path.join(moviePath, '%s.png' % movieFolder)
                if os.path.exists(coverFile):
                    filesToDelete.append(coverFile)

        removeFiles(self, filesToDelete, '.jpg')

    def removeMovieMenu(self):
        foldersToDelete = []
        for modelIndex in self.moviesTableView.selectionModel().selectedRows():
            sourceRow = self.getSourceRow(modelIndex)
            moviePath = self.moviesTableModel.getPath(sourceRow)
            foldersToDelete.append(moviePath)

        removeFolders(self, foldersToDelete)
