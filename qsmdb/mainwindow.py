import random

from PyQt5 import QtGui, QtWidgets, QtCore
from enum import Enum
from pathlib import Path
import imdb
from imdb import IMDb
import json
import fnmatch
import pathlib
import datetime
import collections
import webbrowser
import shutil
import os
import stat
import time
from pymediainfo import MediaInfo

# TODO List
# OpenGL cover viewer (wip)
# Multiple filters
# Play button under cover view and double click cover to play
# Save visible columns and column widths
# Font sizes and color preference
# Background color preference
# Preset layouts
# Fix status bar num visible and num selected when filtered, etc.
# Add selected and total runtime to status bar
# Use PyQt chart to show movies per year broken down by genre

# Required modules
# pyqt5, imdbpy, pymediainfo

# Commands to make stand alone executable.  Run from Console inside PyCharm

# PC
# pyinstaller --add-data ./MediaInfo.dll;. --onefile --noconsole --name SMDB run.py

# MAC
# /Users/House/Library/Python/3.9/bin/pyinstaller --onefile --noconsole --name SMDB run.py

from .utilities import *
from .moviemodel import MoviesTableModel
from .moviemodel import Columns
from .CoverGLWidget import CoverGLWidget

def handleRemoveReadonly(func, path, exc_info):
    """
    Error handler for ``shutil.rmtree``.

    If the error is due to an access error (read only file)
    it attempts to add write permission and then retries.

    If the error is for another reason it re-raises the error.

    Usage : ``shutil.rmtree(path, onerror=onerror)``
    """
    import stat
    if not os.access(path, os.W_OK):
        # Is the error an access error ?
        os.chmod(path, stat.S_IWUSR)
        func(path)
    else:
        raise

def bToGb(b):
    return b / (2**30)

def bToMb(b):
    return b / (2**20)

def readSmdbFile(fileName):
    if os.path.exists(fileName):
        try:
            with open(fileName) as f:
                return json.load(f)
        except:
            print("Could not open file: %s" % fileName)


def getMovieKey(movie, key):
    if key in movie:
        return movie[key]
    else:
        return None


def openYearImdbPage(year):
    webbrowser.open('https://www.imdb.com/search/title/?release_date=%s-01-01,%s-12-31' % (year, year), new=2)


def openPersonImdbPage(personName, db):
    personId = db.name2imdbID(personName)
    if not personId:
        results = db.search_person(personName)
        if not results:
            print('No matches for: %s' % personName)
            return
        person = results[0]
        if isinstance(person, imdb.Person.Person):
            personId = person.getID()

    if personId:
        webbrowser.open('http://imdb.com/name/nm%s' % personId, new=2)

class FilterTable(QtWidgets.QTableWidget):
    def __init__(self):
        super(FilterTable, self).__init__()
        self.mouseLocation = 0

    def mousePressEvent(self, event):
        if event.type() == QtCore.QEvent.MouseButtonPress:
            if event.button() == QtCore.Qt.RightButton:
                self.mouseLocation = event.pos()
                return
            else:
                super(FilterTable, self).mousePressEvent(event)

class FilterWidget(QtWidgets.QFrame):

    tableSelectionChangedSignal = QtCore.pyqtSignal()
    wheelSpun = QtCore.pyqtSignal(int)

    def wheelEvent(self, event):
        self.wheelSpun.emit(event.angleDelta().y() / 120)
        event.accept()

    def __init__(self, filterName="filter", filterBy=0, useMovieList=False, minCount=2, defaultSectionSize=18):
        super(FilterWidget, self).__init__()

        self.moviesSmdbData = None
        self.db = None
        self.movieList = list()
        self.useMovieList = useMovieList

        self.filterByDict = {
            'Director': 'directors',
            'Actor': 'actors',
            'Genre': 'genres',
            'Mpaa Rating': 'mpaa ratings',
            'User Tags': 'user tags',
            'Year': 'years',
            'Companies': 'companies',
            'Country': 'countries',
            'Ratings': 'ratings'
        }

        self.setFrameShape(QtWidgets.QFrame.Panel | QtWidgets.QFrame.Sunken)
        self.setLineWidth(5)
        self.setStyleSheet("background: rgb(25, 25, 25); color: white; border-radius: 10px")

        filtersVLayout = QtWidgets.QVBoxLayout()
        self.setLayout(filtersVLayout)

        filtersVLayout.addWidget(QtWidgets.QLabel(filterName))

        filterByHLayout = QtWidgets.QHBoxLayout()
        self.layout().addLayout(filterByHLayout)

        filterByLabel = QtWidgets.QLabel("Filter By")
        filterByLabel.setSizePolicy(QtWidgets.QSizePolicy.Maximum,
                                    QtWidgets.QSizePolicy.Maximum)
        filterByHLayout.addWidget(filterByLabel)

        self.filterByComboBox = QtWidgets.QComboBox()
        self.filterByComboBox.setStyleSheet("background: rgb(50, 50, 50);")
        for i in self.filterByDict.keys():
            self.filterByComboBox.addItem(i)
        self.filterByComboBox.setCurrentIndex(filterBy)
        self.filterByComboBox.activated.connect(self.populateFiltersTable)
        filterByHLayout.addWidget(self.filterByComboBox)

        minCountHLayout = QtWidgets.QHBoxLayout()
        self.layout().addLayout(minCountHLayout)
        self.filterMinCountCheckbox = QtWidgets.QCheckBox()
        self.filterMinCountCheckbox.setText("Enable Min Count")
        self.filterMinCountCheckbox.setChecked(True)
        self.filterMinCountSpinBox = QtWidgets.QSpinBox()
        self.filterMinCountCheckbox.stateChanged.connect(self.filterMinCountSpinBox.setEnabled)
        self.filterMinCountCheckbox.stateChanged.connect(self.populateFiltersTable)
        minCountHLayout.addWidget(self.filterMinCountCheckbox)

        self.filterMinCountSpinBox.setMinimum(0)
        self.filterMinCountSpinBox.setValue(minCount)
        self.filterMinCountSpinBox.valueChanged.connect(self.populateFiltersTable)
        minCountHLayout.addWidget(self.filterMinCountSpinBox)

        self.filterTable = FilterTable()
        self.filterTable.setColumnCount(2)
        self.filterTable.verticalHeader().hide()
        self.filterTable.setHorizontalHeaderLabels(['Name', 'Count'])
        self.filterTable.setColumnWidth(0, 170)
        self.filterTable.setColumnWidth(1, 60)
        self.filterTable.verticalHeader().setMinimumSectionSize(10)
        self.filterTable.verticalHeader().setDefaultSectionSize(defaultSectionSize)
        self.filterTable.setWordWrap(False)
        self.filterTable.setStyleSheet("background: black; alternate-background-color: #151515; color: white")
        self.filterTable.setAlternatingRowColors(True)
        self.filterTable.itemSelectionChanged.connect(lambda: self.tableSelectionChangedSignal.emit())
        hh = self.filterTable.horizontalHeader()
        hh.setStyleSheet("background: #303030; color: white")
        filtersVLayout.addWidget(self.filterTable)

        filtersSearchHLayout = QtWidgets.QHBoxLayout()
        filtersVLayout.addLayout(filtersSearchHLayout)

        searchText = QtWidgets.QLabel("Search")
        searchText.setSizePolicy(QtWidgets.QSizePolicy.Maximum,
                                 QtWidgets.QSizePolicy.Maximum)
        filtersSearchHLayout.addWidget(searchText)

        filterTableSearchBox = QtWidgets.QLineEdit(self)
        filterTableSearchBox.setStyleSheet("background: black; color: white; border-radius: 5px")
        filterTableSearchBox.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Maximum)
        filterTableSearchBox.setClearButtonEnabled(True)
        filtersSearchHLayout.addWidget(filterTableSearchBox)
        filterTableSearchBox.textChanged.connect(lambda: searchTableWidget(filterTableSearchBox, self.filterTable))

    def filterRightMenu(self):
        rightMenu = QtWidgets.QMenu(self.filterTable)
        selectedItem = self.filterTable.itemAt(self.filterTable.mouseLocation)
        row = selectedItem.row()
        openImdbAction = QtWidgets.QAction("Open IMDB Page", self)
        itemText = self.filterTable.item(row, 0).text()
        filterByText = self.filterByComboBox.currentText()
        if filterByText == 'Director' or filterByText == 'Actor':
            openImdbAction.triggered.connect(lambda: openPersonImdbPage(itemText, self.db))
        else:
            openImdbAction.triggered.connect(lambda: openYearImdbPage(itemText))
        rightMenu.addAction(openImdbAction)
        rightMenu.exec_(QtGui.QCursor.pos())

    def populateFiltersTable(self):
        if not self.moviesSmdbData:
            print("Error: No smbdData")
            return

        if self.useMovieList and len(self.movieList) == 0:
            return

        filterByText = self.filterByComboBox.currentText()
        filterByKey = self.filterByDict[filterByText]

        showMenuTexts = ['Director', 'Actor', 'Year']
        if filterByText in showMenuTexts:
            self.filterTable.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
            try:
                self.filterTable.customContextMenuRequested[QtCore.QPoint].disconnect()
            except Exception:
                pass
            self.filterTable.customContextMenuRequested[QtCore.QPoint].connect(
                self.filterRightMenu)
        else:
            self.filterTable.setContextMenuPolicy(QtCore.Qt.NoContextMenu)

        if filterByKey not in self.moviesSmdbData:
            print("Error: '%s' not in smdbData" % filterByKey)
            return

        self.filterTable.clear()
        self.filterTable.setHorizontalHeaderLabels(['Name', 'Count'])

        row = 0
        numActualRows = 0
        numRows = len(self.moviesSmdbData[filterByKey].keys())
        self.filterTable.setRowCount(numRows)
        self.filterTable.setSortingEnabled(False)
        for name in self.moviesSmdbData[filterByKey].keys():
            if self.useMovieList:
                movies = self.moviesSmdbData[filterByKey][name]['movies']
                count = 0
                for movie in self.movieList:
                    if movie in movies:
                        count = count + 1
            else:
                count = self.moviesSmdbData[filterByKey][name]['num movies']

            if self.filterMinCountCheckbox.isChecked() and count < self.filterMinCountSpinBox.value():
                continue

            nameItem = QtWidgets.QTableWidgetItem(name)
            self.filterTable.setItem(row, 0, nameItem)
            countItem = QtWidgets.QTableWidgetItem('%04d' % count)
            self.filterTable.setItem(row, 1, countItem)
            row += 1
            numActualRows += 1

        self.filterTable.setRowCount(numActualRows)
        if not self.useMovieList:
            self.filterTable.sortItems(1, QtCore.Qt.DescendingOrder)
        self.filterTable.setSortingEnabled(True)


class MovieCover(QtWidgets.QLabel):

    doubleClicked = QtCore.pyqtSignal()
    wheelSpun = QtCore.pyqtSignal(int)

    def __init__(self):
        super(MovieCover, self).__init__()

    def mouseDoubleClickEvent(self, a0: QtGui.QMouseEvent) -> None:
        self.doubleClicked.emit()

    def wheelEvent(self, event):
        self.wheelSpun.emit(event.angleDelta().y() / 120)
        event.accept()

class MovieTableView(QtWidgets.QTableView):
    wheelSpun = QtCore.pyqtSignal(int)

    def wheelEvent(self, event):
        if event.modifiers() == QtCore.Qt.ControlModifier:
            self.wheelSpun.emit(event.angleDelta().y() / 120)
            event.accept()
        else:
            event.ignore()
            super().wheelEvent(event)

class MovieInfoListview(QtWidgets.QListWidget):
    wheelSpun = QtCore.pyqtSignal(int)

    def wheelEvent(self, event):
        if event.modifiers() == QtCore.Qt.ControlModifier:
            self.wheelSpun.emit(event.angleDelta().y() / 120)
            event.accept()
        else:
            event.ignore()
            super().wheelEvent(event)

    def mousePressEvent(self, event):
        if event.type() == QtCore.QEvent.MouseButtonPress:
            if event.button() == QtCore.Qt.RightButton:
                self.mouseLocation = event.pos()
                return
            else:
                super().mousePressEvent(event)


def getFolderSize(startPath='.'):
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(startPath):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            # skip if it is symbolic link
            if not os.path.islink(fp):
                total_size += os.path.getsize(fp)
    return total_size


def getFolderSizes(path):
    fileAndSizes = dict()
    for f in os.listdir(path):
        fullPath = os.path.join(path, f)
        if os.path.isdir(fullPath):
            fileSize = getFolderSize(fullPath)
        else:
            fileSize = os.path.getsize(fullPath)
        fileAndSizes[f] = fileSize
    return fileAndSizes


class MyWindow(QtWidgets.QMainWindow):
    def wheelEvent(self, event):
        self.setFontSize(event.angleDelta().y() / 120)
        event.accept()

    def setFontSize(self, delta):
        if QtWidgets.QApplication.keyboardModifiers() != QtCore.Qt.ControlModifier:
            return

        if 5 >= self.fontSize <= 30:
            return

        delta = min(1, max(-1, delta))
        self.fontSize = max(6, min(29, self.fontSize + delta))
        self.setStyleSheet(f"font-size:{self.fontSize}px;")
        self.titleLabel.setStyleSheet(f"color: white; background: black; font-size: {self.fontSize * 2}px;")
        self.rowHeightWithoutCover = 18 * (self.fontSize / 12)

        self.moviesTableView.verticalHeader().setDefaultSectionSize(self.rowHeightWithoutCover)
        self.watchListTableView.verticalHeader().setDefaultSectionSize(self.rowHeightWithoutCover)
        self.backupListTableView.verticalHeader().setDefaultSectionSize(self.rowHeightWithoutCover)
        self.historyListTableView.verticalHeader().setDefaultSectionSize(self.rowHeightWithoutCover)
        self.primaryFilterWidget.filterTable.verticalHeader().setDefaultSectionSize(self.rowHeightWithoutCover)
        self.secondaryFilterWidget.filterTable.verticalHeader().setDefaultSectionSize(self.rowHeightWithoutCover)

    def __init__(self):
        super(MyWindow, self).__init__()

        self.numVisibleMovies = 0

        # Create IMDB database
        self.db = IMDb()

        # Read the movies folder from the settings
        self.settings = QtCore.QSettings("STC", "SMDB")
        self.moviesFolder = self.settings.value('movies_folder', "", type=str)
        if self.moviesFolder == "":
            self.moviesFolder = "No movies folder set.  Use the \"File->Set movies folder\" menu to set it."
        self.backupFolder = ""
        self.additionalMoviesFolders = self.settings.value('additional_movies_folders', [], type=list)

        # Movie selection history
        self.selectionHistory = list()
        self.selectionHistoryIndex = 0
        self.modifySelectionHistory = True

        # Init UI
        self.setTitleBar()
        geometry = self.settings.value('geometry',
                                       QtCore.QRect(50, 50, 1820, 900),
                                       type=QtCore.QRect)
        self.setGeometry(geometry)

        # Set default font size and foreground/background colors for item views
        self.fontSize = 12
        self.setStyleSheet(f"font-size:{self.fontSize}px;")
        self.menuBar().setStyleSheet("background: rgb(50, 50, 50); color: white; border-radius: 0px;")
        self.statusBar().setStyleSheet("background: rgb(50, 50, 50); color: white; border-radius: 0px;")

        # Default view state of UI sections
        #self.showPrimaryFilters = True
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

        # Default state of cancel button
        self.isCanceled = False

        # Main Menus
        self.initUIFileMenu()
        self.initUIViewMenu()

        # Add the central widget
        centralWidget = QtWidgets.QWidget()
        centralWidget.setStyleSheet("background: rgb(50, 50, 50); color: white; border-radius: 0px;")
        self.setCentralWidget(centralWidget)

        # Divides top h splitter and bottom progress bar
        mainVLayout = QtWidgets.QVBoxLayout(self)
        centralWidget.setLayout(mainVLayout)

        # Main H Splitter for filter, movies list, and cover/info
        self.mainHSplitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal, self)
        self.mainHSplitter.setHandleWidth(10)
        mainVLayout.addWidget(self.mainHSplitter)

        # Splitter for filters
        self.filtersVSplitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        self.filtersVSplitter.setHandleWidth(20)

        # Used to set height of rows in various tables based on whether
        # the cover column is visible
        self.rowHeightWithoutCover = 18
        self.rowHeightWithCover = 200

        # Filters
        self.primaryFilterWidget = FilterWidget("Primary Filter",
                                                defaultSectionSize=self.rowHeightWithoutCover)
        self.primaryFilterWidget.wheelSpun.connect(self.setFontSize)
        self.filtersVSplitter.addWidget(self.primaryFilterWidget)

        self.secondaryFilterWidget = FilterWidget("Secondary Filter",
                                                  filterBy=5,
                                                  useMovieList=True,
                                                  minCount=1,
                                                  defaultSectionSize=self.rowHeightWithoutCover)
        self.secondaryFilterWidget.wheelSpun.connect(self.setFontSize)
        self.filtersVSplitter.addWidget(self.secondaryFilterWidget)

        sizes = [int(x) for x in self.settings.value('filterVSplitterSizes', [200, 200], type=list)]
        self.filtersVSplitter.setSizes(sizes)

        if not self.showPrimaryFilter:
            self.primaryFilterWidget.hide()

        if not self.showSecondaryFilter:
            self.secondaryFilterWidget.hide()

        # Splitter for Movies Table and Watch List
        self.moviesWatchListBackupVSplitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        self.moviesWatchListBackupVSplitter.setHandleWidth(20)

        # Movies Table
        self.moviesTableWidget = QtWidgets.QFrame()
        self.moviesTableView = MovieTableView()
        self.moviesTableView.wheelSpun.connect(self.setFontSize)
        self.moviesTableTitleFilterBox = QtWidgets.QLineEdit()
        self.moviesTableSearchPlotsBox = QtWidgets.QLineEdit()
        self.moviesTableColumnsVisible = []
        self.moviesListHeaderActions = []
        self.initUIMoviesTable()
        self.moviesWatchListBackupVSplitter.addWidget(self.moviesTableWidget)
        if not self.showMoviesTable:
            self.moviesTableWidget.hide()

        # Watch List
        self.watchListWidget = QtWidgets.QFrame()
        self.watchListTableView = MovieTableView()
        self.watchListTableView.wheelSpun.connect(self.setFontSize)
        self.watchListColumnsVisible = []
        self.watchListHeaderActions = []
        self.initUIWatchList()
        self.moviesWatchListBackupVSplitter.addWidget(self.watchListWidget)

        # Backup List
        self.backupAnalysed = False
        self.backupListWidget = QtWidgets.QFrame()
        self.backupListTableView = MovieTableView()
        self.backupListTableView.wheelSpun.connect(self.setFontSize)
        self.spaceBarLayout = QtWidgets.QHBoxLayout()
        self.spaceUsedWidget = QtWidgets.QWidget()
        self.spaceChangedWidget = QtWidgets.QWidget()
        self.spaceAvailableWidget = QtWidgets.QWidget()
        self.spaceAvailableLabel = QtWidgets.QLabel("")
        self.spaceTotal = 0
        self.spaceUsed = 0
        self.spaceFree = 0
        self.spaceUsedPercent = 0
        self.bytesToBeCopied = 0
        self.sourceFolderSizes = dict()
        self.destFolderSizes = dict()
        self.backupListColumnsVisible = []
        self.backupListHeaderActions = []
        self.backupFolderEdit = QtWidgets.QLineEdit()

        self.initUIBackupList()
        self.moviesWatchListBackupVSplitter.addWidget(self.backupListWidget)
        if not self.showBackupList:
            self.backupListWidget.hide()

        # History List
        self.historyListWidget = QtWidgets.QFrame()
        self.historyListTableView = MovieTableView()
        self.historyListTableView.wheelSpun.connect(self.setFontSize)
        self.historyListColumnsVisible = []
        self.historyListHeaderActions = []
        self.initUIHistoryList()
        self.moviesWatchListBackupVSplitter.addWidget(self.historyListWidget)
        if not self.showHistoryList:
            self.historyListWidget.hide()

        sizes = [int(x) for x in self.settings.value('moviesWatchListBackupVSplitterSizes', [500, 200, 100, 100], type=list)]
        self.moviesWatchListBackupVSplitter.setSizes(sizes)

        # Movie section widget
        self.initUIMovieSection()

        # Add the sub-layouts to the self.mainHSplitter
        self.mainHSplitter.addWidget(self.filtersVSplitter)
        self.mainHSplitter.addWidget(self.moviesWatchListBackupVSplitter)
        self.mainHSplitter.addWidget(self.movieSectionWidget)
        self.mainHSplitter.splitterMoved.connect(self.resizeCoverFile)

        # Main horizontal sizes
        sizes = [int(x) for x in self.settings.value('mainHSplitterSizes', [270, 750, 800], type=list)]
        self.mainHSplitter.setSizes(sizes)

        # Bottom
        bottomLayout = QtWidgets.QHBoxLayout(self)
        mainVLayout.addLayout(bottomLayout)
        self.progressBar = QtWidgets.QProgressBar()
        self.progressBar.setStyleSheet("background: rgb(0, 0, 0); color: white; border-radius: 5px")
        self.progressBar.setMaximum(100)
        bottomLayout.addWidget(self.progressBar)
        cancelButton = QtWidgets.QPushButton("Cancel", self)
        cancelButton.clicked.connect(self.cancelButtonClicked)
        cancelButton.setStyleSheet("background: rgb(100, 100, 100); color: white; border-radius: 5px")
        cancelButton.setFixedSize(100, 25)
        bottomLayout.addWidget(cancelButton)

        # Show the window
        self.show()

        if not os.path.exists(self.moviesFolder):
            return

        self.moviesSmdbFile = os.path.join(self.moviesFolder, "smdb_data.json")
        self.moviesSmdbData = None
        self.moviesTableModel = None
        self.moviesTableProxyModel = None

        self.refreshMoviesList()

        self.primaryFilterWidget.moviesSmdbData = self.moviesSmdbData
        self.primaryFilterWidget.db = self.db
        self.primaryFilterWidget.populateFiltersTable()
        self.primaryFilterWidget.tableSelectionChangedSignal.connect(
            lambda: self.filterTableSelectionChanged())

        self.secondaryFilterWidget.moviesSmdbData = self.moviesSmdbData
        self.secondaryFilterWidget.db = self.db
        self.secondaryFilterWidget.populateFiltersTable()
        self.secondaryFilterWidget.tableSelectionChangedSignal.connect(
            lambda: self.filterTableSelectionChanged(mainFilter=False))

        self.watchListSmdbFile = os.path.join(self.moviesFolder, "smdb_data_watch_list.json")
        self.watchListSmdbData = None
        self.watchListTableModel = None
        self.watchListTableProxyModel = None
        self.refreshWatchList()

        self.historyListSmdbFile = os.path.join(self.moviesFolder, "smdb_data_history_list.json")
        self.historyListSmdbData = None
        self.historyListTableModel = None
        self.historyListTableProxyModel = None
        self.refreshHistoryList()

        self.backupListSmdbFile = os.path.join(self.moviesFolder, "smdb_data_backup_list.json")
        self.backupListSmdbData = None
        self.backupListTableModel = None
        self.backupListTableProxyModel = None
        self.refreshBackupList()

        self.showMoviesTableSelectionStatus()

    def closeEvent(self, a0: QtGui.QCloseEvent) -> None:
        self.settings.setValue('geometry', self.geometry())
        self.settings.setValue('mainHSplitterSizes', self.mainHSplitter.sizes())
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
        print(f"close event showWatchList = {self.showWatchList} ")
        self.settings.setValue('showWatchList', self.showWatchList)
        self.settings.setValue('showHistoryList', self.showHistoryList)
        self.settings.setValue('showBackupList', self.showBackupList)

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

        rescanAction = QtWidgets.QAction("Rescan movie folders", self)
        rescanAction.triggered.connect(lambda: self.refreshMoviesList(forceScan=True))
        fileMenu.addAction(rescanAction)

        rebuildSmdbFileAction = QtWidgets.QAction("Rebuild SMDB file", self)
        rebuildSmdbFileAction.triggered.connect(lambda: self.writeSmdbFile(self.moviesSmdbFile,
                                                                           self.moviesTableModel))
        fileMenu.addAction(rebuildSmdbFileAction)

        conformMoviesAction = QtWidgets.QAction("Conform movies in folder", self)
        conformMoviesAction.triggered.connect(self.conformMovies)
        fileMenu.addAction(conformMoviesAction)

        preferencesAction = QtWidgets.QAction("Preferences", self)
        preferencesAction.triggered.connect(self.preferences)
        fileMenu.addAction(preferencesAction)

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

        restoreDefaultWindowsAction = QtWidgets.QAction("Restore default window configuration", self)
        restoreDefaultWindowsAction.triggered.connect(self.restoreDefaultWindows)
        viewMenu.addAction(restoreDefaultWindowsAction)

    def toggleColumn(self, c, tableView, visibleList):
        visibleList[c.value] = not visibleList[c.value]
        if visibleList[c.value]:
            tableView.showColumn(c.value)
            if c.value == self.moviesTableModel.Columns.Cover.value:
                tableView.verticalHeader().setDefaultSectionSize(self.rowHeightWithCover)
                tableView.setVerticalScrollMode(QtWidgets.QAbstractItemView.ScrollPerPixel)
                tableView.verticalScrollBar().setSingleStep(10)
        else:
            tableView.hideColumn(c.value)
            if c.value == self.moviesTableModel.Columns.Cover.value:
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
            if i != self.moviesTableModel.Columns.Year.value:  # leave the year column visible
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
        for c in model.Columns:
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

    def initUIMoviesTable(self):
        self.moviesTableWidget.setFrameShape(QtWidgets.QFrame.Panel | QtWidgets.QFrame.Sunken)
        self.moviesTableWidget.setLineWidth(5)
        self.moviesTableWidget.setStyleSheet("background: rgb(25, 25, 25); color: white;  border-radius: 10px")

        moviesTableViewVLayout = QtWidgets.QVBoxLayout()
        self.moviesTableWidget.setLayout(moviesTableViewVLayout)

        moviesLabel = QtWidgets.QLabel("Movies")
        moviesTableViewVLayout.addWidget(moviesLabel)

        self.moviesTableView.setSortingEnabled(True)
        self.moviesTableView.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.moviesTableView.verticalHeader().hide()
        self.moviesTableView.setStyleSheet("background: black; alternate-background-color: #151515; color: white")
        self.moviesTableView.setAlternatingRowColors(True)
        self.moviesTableView.setShowGrid(False)
        self.moviesTableView.setVerticalScrollMode(QtWidgets.QAbstractItemView.ScrollPerItem)
        self.moviesTableView.verticalScrollBar().setSingleStep(5)

        # Right click header menu
        hh = self.moviesTableView.horizontalHeader()
        hh.setStyleSheet("background: #303030; color: white")
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

        moviesTableSearchHLayout = QtWidgets.QHBoxLayout()
        moviesTableViewVLayout.addLayout(moviesTableSearchHLayout)

        buttonsVLayout = QtWidgets.QVBoxLayout()
        moviesTableSearchHLayout.addLayout(buttonsVLayout)

        backForwardHLayout = QtWidgets.QHBoxLayout()
        buttonsVLayout.addLayout(backForwardHLayout)

        # Back button
        backButton = QtWidgets.QPushButton("Back")
        backButton.setSizePolicy(QtWidgets.QSizePolicy.Minimum,
                                 QtWidgets.QSizePolicy.Minimum)
        backButton.clicked.connect(self.moviesTableBack)
        backButton.setStyleSheet("background: rgb(50, 50, 50); color: white; border-radius: 5px;")
        backForwardHLayout.addWidget(backButton)

        # Forward button
        forwardButton = QtWidgets.QPushButton("Forward")
        forwardButton.setSizePolicy(QtWidgets.QSizePolicy.Minimum,
                                    QtWidgets.QSizePolicy.Minimum)
        forwardButton.clicked.connect(self.moviesTableForward)
        forwardButton.setStyleSheet("background: rgb(50, 50, 50); color: white; border-radius: 5px")
        backForwardHLayout.addWidget(forwardButton)

        randomAllHLayout = QtWidgets.QHBoxLayout()
        buttonsVLayout.addLayout(randomAllHLayout)

        # Pick random button
        pickRandomButton = QtWidgets.QPushButton("Random")
        pickRandomButton.setSizePolicy(QtWidgets.QSizePolicy.Minimum,
                                       QtWidgets.QSizePolicy.Minimum)
        pickRandomButton.clicked.connect(self.pickRandomMovie)
        pickRandomButton.setStyleSheet("background: rgb(50, 50, 50); color: white; border-radius: 5px")
        randomAllHLayout.addWidget(pickRandomButton)

        # Show all button
        showAllButton = QtWidgets.QPushButton("Show All")
        showAllButton.setSizePolicy(QtWidgets.QSizePolicy.Minimum,
                                    QtWidgets.QSizePolicy.Minimum)
        showAllButton.clicked.connect(self.showAllMoviesTableView)
        showAllButton.setStyleSheet("background: rgb(50, 50, 50); color: white; border-radius: 5px")
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

        self.moviesTableTitleFilterBox.setStyleSheet("background: black; color: white; border-radius: 5px")
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

        self.moviesTableSearchPlotsBox.setStyleSheet("background: black; color: white; border-radius: 5px")
        self.moviesTableSearchPlotsBox.setSizePolicy(QtWidgets.QSizePolicy.Minimum,
                                                     QtWidgets.QSizePolicy.Minimum)
        self.moviesTableSearchPlotsBox.setClearButtonEnabled(True)
        self.moviesTableSearchPlotsBox.returnPressed.connect(self.searchPlots)
        moviesTableSearchPlotsHLayout.addWidget(self.moviesTableSearchPlotsBox)

        moviesTableSearchHLayout.setStretch(0, 3)
        moviesTableSearchHLayout.setStretch(1, 10)

    def initUIWatchList(self):
        self.watchListWidget.setFrameShape(QtWidgets.QFrame.Panel | QtWidgets.QFrame.Sunken)
        self.watchListWidget.setLineWidth(5)
        self.watchListWidget.setStyleSheet("background: rgb(25, 25, 25); color: white; border-radius: 10px")

        watchListVLayout = QtWidgets.QVBoxLayout()
        self.watchListWidget.setLayout(watchListVLayout)

        watchListLabel = QtWidgets.QLabel("Watch List")
        watchListVLayout.addWidget(watchListLabel)

        self.watchListTableView.setSortingEnabled(False)
        self.watchListTableView.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.watchListTableView.verticalHeader().hide()
        self.watchListTableView.setStyleSheet("background: black; alternate-background-color: #151515; color: white")
        self.watchListTableView.setAlternatingRowColors(True)
        self.watchListTableView.horizontalHeader().setSectionsMovable(True)
        self.watchListTableView.horizontalHeader().setStyleSheet("color: black")
        self.watchListTableView.setShowGrid(False)

        # Right click header menu
        hh = self.watchListTableView.horizontalHeader()
        hh.setStyleSheet("background: #303030; color: white")
        hh.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        hh.customContextMenuRequested[QtCore.QPoint].connect(
            lambda: self.headerRightMenuShow(QtCore.QPoint,
                                             self.watchListTableView,
                                             self.watchListColumnsVisible,
                                             self.watchListTableModel))

        # Right click menu
        self.watchListTableView.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.watchListTableView.customContextMenuRequested[QtCore.QPoint].connect(self.watchListTableRightMenuShow)

        watchListVLayout.addWidget(self.watchListTableView)

        watchListButtonsHLayout = QtWidgets.QHBoxLayout()
        watchListVLayout.addLayout(watchListButtonsHLayout)

        addButton = QtWidgets.QPushButton('Add')
        addButton.clicked.connect(self.watchListAdd)
        addButton.setStyleSheet("background: rgb(50, 50, 50); color: white; border-radius: 5px")
        watchListButtonsHLayout.addWidget(addButton)

        removeButton = QtWidgets.QPushButton('Remove')
        removeButton.clicked.connect(self.watchListRemove)
        removeButton.setStyleSheet("background: rgb(50, 50, 50); color: white; border-radius: 5px")
        watchListButtonsHLayout.addWidget(removeButton)

        moveToTopButton = QtWidgets.QPushButton('Move To Top')
        moveToTopButton.clicked.connect(lambda: self.watchListMoveRow(self.MoveTo.TOP))
        moveToTopButton.setStyleSheet("background: rgb(50, 50, 50); color: white; border-radius: 5px")
        watchListButtonsHLayout.addWidget(moveToTopButton)

        moveUpButton = QtWidgets.QPushButton('Move Up')
        moveUpButton.clicked.connect(lambda: self.watchListMoveRow(self.MoveTo.UP))
        moveUpButton.setStyleSheet("background: rgb(50, 50, 50); color: white; border-radius: 5px")
        watchListButtonsHLayout.addWidget(moveUpButton)

        moveDownButton = QtWidgets.QPushButton('Move Down')
        moveDownButton.clicked.connect(lambda: self.watchListMoveRow(self.MoveTo.DOWN))
        moveDownButton.setStyleSheet("background: rgb(50, 50, 50); color: white; border-radius: 5px")
        watchListButtonsHLayout.addWidget(moveDownButton)

    def initUIHistoryList(self):
        self.historyListWidget.setFrameShape(QtWidgets.QFrame.Panel | QtWidgets.QFrame.Sunken)
        self.historyListWidget.setLineWidth(5)
        self.historyListWidget.setStyleSheet("background: rgb(25, 25, 25); color: white; border-radius: 10px")

        historyListVLayout = QtWidgets.QVBoxLayout()
        self.historyListWidget.setLayout(historyListVLayout)

        historyListLabel = QtWidgets.QLabel("History List")
        historyListVLayout.addWidget(historyListLabel)

        self.historyListTableView.setSortingEnabled(False)
        self.historyListTableView.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.historyListTableView.verticalHeader().hide()
        self.historyListTableView.setStyleSheet("background: black; alternate-background-color: #151515; color: white")
        self.historyListTableView.setAlternatingRowColors(True)
        self.historyListTableView.horizontalHeader().setSectionsMovable(True)
        self.historyListTableView.horizontalHeader().setStyleSheet("color: black")
        self.historyListTableView.setShowGrid(False)

        # Right click header menu
        hh = self.historyListTableView.horizontalHeader()
        hh.setStyleSheet("background: #303030; color: white")
        hh.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        hh.customContextMenuRequested[QtCore.QPoint].connect(
            lambda: self.headerRightMenuShow(QtCore.QPoint,
                                             self.historyListTableView,
                                             self.historyListColumnsVisible,
                                             self.historyListTableModel))

        # Right click menu
        self.historyListTableView.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.historyListTableView.customContextMenuRequested[QtCore.QPoint].connect(self.historyListTableRightMenuShow)

        historyListVLayout.addWidget(self.historyListTableView)

        historyListButtonsHLayout = QtWidgets.QHBoxLayout()
        historyListVLayout.addLayout(historyListButtonsHLayout)

        removeButton = QtWidgets.QPushButton('Remove')
        removeButton.clicked.connect(self.historyListRemove)
        removeButton.setStyleSheet("background: rgb(50, 50, 50); color: white; border-radius: 5px")
        historyListButtonsHLayout.addWidget(removeButton)

    def initUIMovieSection(self):
        self.movieSectionWidget = QtWidgets.QFrame()
        self.movieSectionWidget.setFrameShape(QtWidgets.QFrame.Panel | QtWidgets.QFrame.Sunken)
        self.movieSectionWidget.setLineWidth(5)
        self.movieSectionWidget.setStyleSheet("background: rgb(25, 25, 25); border-radius: 10px")
        if not self.showMovieSection:
            self.movieSectionWidget.hide()

        movieSectionVLayout = QtWidgets.QVBoxLayout()
        self.movieSectionWidget.setLayout(movieSectionVLayout)

        # Title
        self.titleLabel = QtWidgets.QLabel()
        self.titleLabel.setStyleSheet(f"color: white; background: black; font-size: {self.fontSize * 2}px;")
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
        self.movieInfoListView = MovieInfoListview()
        self.movieInfoListView.wheelSpun.connect(self.setFontSize)
        self.movieInfoListView.setStyleSheet("background: black; color: white;")
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
        self.summary.setStyleSheet("color:white; background-color: black;")
        self.coverSummaryVSplitter.addWidget(self.summary)
        if not self.showSummary:
            self.summary.hide()

        sizes = [int(x) for x in self.settings.value('coverSummaryVSplitterSizes', [600, 200], type=list)]
        self.coverSummaryVSplitter.setSizes(sizes)


    def initUIBackupList(self):
        self.backupListWidget.setFrameShape(QtWidgets.QFrame.Panel | QtWidgets.QFrame.Sunken)
        self.backupListWidget.setLineWidth(5)
        self.backupListWidget.setStyleSheet("background: rgb(25, 25, 25); color: white; border-radius: 10px")

        backupListVLayout = QtWidgets.QVBoxLayout()
        self.backupListWidget.setLayout(backupListVLayout)

        backupListLabel = QtWidgets.QLabel("Backup List")
        backupListVLayout.addWidget(backupListLabel)

        self.backupListTableView.setSortingEnabled(True)
        self.backupListTableView.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.backupListTableView.verticalHeader().hide()
        self.backupListTableView.setStyleSheet("background: black; alternate-background-color: #151515; color: white")
        self.backupListTableView.setAlternatingRowColors(True)
        self.backupListTableView.horizontalHeader().setSectionsMovable(True)
        self.backupListTableView.horizontalHeader().setStyleSheet("color: black")
        self.backupListTableView.setShowGrid(False)

        # Right click header menu
        hh = self.backupListTableView.horizontalHeader()
        hh.setStyleSheet("background: #303030; color: white")
        hh.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        hh.customContextMenuRequested[QtCore.QPoint].connect(
            lambda: self.headerRightMenuShow(QtCore.QPoint,
                                             self.backupListTableView,
                                             self.backupListColumnsVisible,
                                             self.backupListTableModel))

        # Right click menu
        self.backupListTableView.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.backupListTableView.customContextMenuRequested[QtCore.QPoint].connect(self.backupListTableRightMenuShow)

        backupListVLayout.addWidget(self.backupListTableView)

        backupListButtonsHLayout = QtWidgets.QHBoxLayout()
        backupListVLayout.addLayout(backupListButtonsHLayout)

        addButton = QtWidgets.QPushButton('Add')
        addButton.setStyleSheet("background: rgb(50, 50, 50);"
                                "color: white;"
                                "border-radius: 5px")
        addButton.clicked.connect(self.backupListAdd)
        backupListButtonsHLayout.addWidget(addButton)

        removeButton = QtWidgets.QPushButton('Remove')
        removeButton.setStyleSheet("background: rgb(50, 50, 50); color: white;"
                                   "border-radius: 5px")
        removeButton.clicked.connect(self.backupListRemove)
        backupListButtonsHLayout.addWidget(removeButton)

        removeNoDifferenceButton = QtWidgets.QPushButton('Remove Folders With No Difference')
        removeNoDifferenceButton.setFixedSize(300, 20)
        removeNoDifferenceButton.setStyleSheet("background: rgb(50, 50, 50);"
                                               "color: white; border-radius: 5px")
        removeNoDifferenceButton.clicked.connect(self.backupListRemoveNoDifference)
        backupListButtonsHLayout.addWidget(removeNoDifferenceButton)

        analyseButton = QtWidgets.QPushButton("Analyse")
        analyseButton.setStyleSheet("background: rgb(50, 50, 50);"
                                    "color: white;"
                                    "border-radius: 5px")
        analyseButton.clicked.connect(self.backupAnalyse)
        backupListButtonsHLayout.addWidget(analyseButton)

        backupButton = QtWidgets.QPushButton("Backup")
        backupButton.setStyleSheet("background: rgb(50, 50, 50);"
                                   "color: white;"
                                   "border-radius: 5px")
        backupButton.clicked.connect(lambda: self.backupRun(moveFiles=False))
        backupListButtonsHLayout.addWidget(backupButton)

        moveButton = QtWidgets.QPushButton("Move")
        moveButton.setStyleSheet("background: rgb(50, 50, 50);"
                                 "color: white;"
                                 "border-radius: 5px")
        moveButton.clicked.connect(lambda: self.backupRun(moveFiles=True))
        backupListButtonsHLayout.addWidget(moveButton)

        backupFolderHLayout = QtWidgets.QHBoxLayout()
        backupListVLayout.addLayout(backupFolderHLayout)

        backupFolderLabel = QtWidgets.QLabel("Destination Folder")
        backupFolderHLayout.addWidget(backupFolderLabel)

        self.backupFolderEdit.setStyleSheet("background: black; color: white; border-radius: 5px")
        self.backupFolderEdit.setReadOnly(True)
        self.backupFolderEdit.setText(self.backupFolder)
        backupFolderHLayout.addWidget(self.backupFolderEdit)

        browseButton = QtWidgets.QPushButton("Browse")
        browseButton.setStyleSheet("background: rgb(50, 50, 50);"
                                   "color: white;"
                                   "border-radius: 5px")
        browseButton.clicked.connect(self.backupBrowseFolder)
        browseButton.setFixedSize(80, 20)
        backupFolderHLayout.addWidget(browseButton)

        self.spaceAvailableLabel.setAlignment(QtCore.Qt.AlignRight)
        backupFolderHLayout.addWidget(self.spaceAvailableLabel)

        backupSpaceLayout = QtWidgets.QHBoxLayout()
        backupListVLayout.addLayout(backupSpaceLayout)

        spaceLabel = QtWidgets.QLabel("Disk Space")
        spaceLabel.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        backupSpaceLayout.addWidget(spaceLabel)

        spaceBarWidget = QtWidgets.QWidget()
        backupSpaceLayout.addWidget(spaceBarWidget)

        self.spaceBarLayout.setSpacing(0)
        self.spaceBarLayout.setContentsMargins(0, 0, 0, 0)
        spaceBarWidget.setLayout(self.spaceBarLayout)

        self.spaceUsedWidget.setStyleSheet("background: rgb(0,255,0);"
                                           "border-radius: 0px 0px 0px 0px")

        self.spaceBarLayout.addWidget(self.spaceUsedWidget)

        self.spaceChangedWidget.setStyleSheet("background: rgb(255,255,0);"
                                              "border-radius: 0px 0px 0px 0px")
        self.spaceBarLayout.addWidget(self.spaceChangedWidget)

        self.spaceAvailableWidget.setStyleSheet("background: rgb(100,100,100);"
                                                "border-radius: 0px 0px 0px 0px")
        self.spaceBarLayout.addWidget(self.spaceAvailableWidget)

        self.spaceBarLayout.setStretch(0, 0)
        self.spaceBarLayout.setStretch(1, 0)
        self.spaceBarLayout.setStretch(2, 1000)

    def initUICover(self):
        self.coverTab.setStyleSheet("background-color: black;")
        movieVLayout = QtWidgets.QVBoxLayout()
        self.coverTab.setLayout(movieVLayout)
        self.movieCover.setScaledContents(False)
        self.movieCover.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Ignored)
        self.movieCover.setStyleSheet("background-color: black;")
        self.movieCover.doubleClicked.connect(lambda: self.playMovie(self.moviesTableView, self.moviesTableProxyModel))
        self.movieCover.wheelSpun.connect(self.setFontSize)

        movieVLayout.addWidget(self.movieCover)

    def refreshTable(self,
                     smdbFile,
                     tableView,
                     columnsToShow,
                     sortColumn,
                     forceScan=False,
                     neverScan=True):

        smdbData = dict()
        if os.path.exists(smdbFile):
            smdbData = readSmdbFile(smdbFile)
        else:
            forceScan = True

        moviesFolders = [self.moviesFolder]
        moviesFolders += self.additionalMoviesFolders
        model = MoviesTableModel(smdbData,
                                 moviesFolders,
                                 forceScan,
                                 neverScan)

        # If there is no smdb file and neverScan is False (as it
        # is for the main movie list) then write a new smdb file
        if not os.path.exists(smdbFile) and not neverScan:
            smdbData = self.writeSmdbFile(smdbFile, model)

        proxyModel = QtCore.QSortFilterProxyModel()
        proxyModel.setSourceModel(model)
        tableView.setModel(proxyModel)
        proxyModel.sort(sortColumn)

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
        for col in Columns:
            tableView.setColumnWidth(col.value, model.defaultWidths[col.value])
            columnsVisible.append(True)

        for c in Columns:
            index = c.value
            columnsVisible[index] = True
            if index not in columnsToShow:
                tableView.hideColumn(index)
                columnsVisible[index] = False

        tableView.horizontalHeader().moveSection(model.Columns.Rank.value, 0)

        tableView.verticalHeader().setMinimumSectionSize(10)
        tableView.verticalHeader().setDefaultSectionSize(self.rowHeightWithoutCover)

        return smdbData, model, proxyModel, columnsVisible, smdbData

    def refreshMoviesList(self, forceScan=False):
        columnsToShow = [Columns.Year.value,
                         Columns.Title.value,
                         Columns.Rating.value,
                         Columns.MpaaRating.value,
                         Columns.Width.value,
                         Columns.Height.value,
                         Columns.Size.value]

        (self.moviesSmdbData,
         self.moviesTableModel,
         self.moviesTableProxyModel,
         self.moviesTableColumnsVisible,
         self.moviesSmdbData) = self.refreshTable(self.moviesSmdbFile,
                                                  self.moviesTableView,
                                                  columnsToShow,
                                                  Columns.Year.value,
                                                  forceScan,
                                                  neverScan=False)

        self.numVisibleMovies = self.moviesTableProxyModel.rowCount()
        self.showMoviesTableSelectionStatus()
        self.pickRandomMovie()

    def refreshWatchList(self):
        columnsToShow = [Columns.Rank.value,
                         Columns.Year.value,
                         Columns.Title.value,
                         Columns.Rating.value]

        (self.watchListSmdbData,
         self.watchListTableModel,
         self.watchListTableProxyModel,
         self.watchListColumnsVisible,
         smdbData) = self.refreshTable(self.watchListSmdbFile,
                                       self.watchListTableView,
                                       columnsToShow,
                                       Columns.Rank.value)

    def refreshHistoryList(self):
        columnsToShow = [Columns.Year.value,
                         Columns.Title.value,
                         Columns.Rating.value]

        (self.historyListSmdbData,
         self.historyListTableModel,
         self.historyListTableProxyModel,
         self.historyListColumnsVisible,
         smdbData) = self.refreshTable(self.historyListSmdbFile,
                                       self.historyListTableView,
                                       columnsToShow,
                                       Columns.Rank.value)

    def refreshBackupList(self):
        columnsToShow = [Columns.Title.value,
                         Columns.Path.value,
                         Columns.BackupStatus.value,
                         Columns.Size.value]

        (self.backupListSmdbData,
         self.backupListTableModel,
         self.backupListTableProxyModel,
         self.backupListColumnsVisible,
         smdbData) = self.refreshTable(self.backupListSmdbFile,
                                       self.backupListTableView,
                                       columnsToShow,
                                       Columns.Rank.value)

    def preferences(self):
        pass

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
                        print(f"Skipping. New name same as old name: {newFolderName}")
                        continue
                    newFolderPath = os.path.join(parentPath, newFolderName)
                    if os.path.exists(newFolderPath) or newFolderName in renamedFolders:
                        newFolderName = newFolderName + '2'
                        newFolderPath = newFolderPath + '2'
                        print(f"Duplicate folder renamed to: {newFolderName}")
                    renamedFolders.add(newFolderName)
                    print(f"Renaming folder: \"{folderPath}\"    to    \"{newFolderPath}\"")

                    with os.scandir(f.path) as childFiles:
                        for c in childFiles:
                            fileName, extension = os.path.splitext(c.name)
                            if extension == '.mp4' or extension == '.srt' or extension == '.mkv':
                                newFilePath = os.path.join(folderPath, newFolderName + extension)
                                if c.path != newFilePath:
                                    print(f"\tRenaming file: {c.path} to {newFilePath}")
                                    try:
                                        os.rename(c.path, newFilePath)
                                    except FileExistsError:
                                        print(f"Can't Rename file {c.path, newFilePath}")
                                        continue
                            elif extension == '.jpg':
                                print(f"\tRemoving file: {c.path}")
                                os.remove(c.path)
                            else:
                                print(f"\tNot touching file: {c.path}")

                    try:
                        os.rename(folderPath, newFolderPath)
                    except FileExistsError:
                        print(f"Can't Rename folder {folderPath, newFolderPath}")
                        continue
                else:
                    rejectedFolders.add(folderPath)
                    foldersRejected += 1
        for f in rejectedFolders:
            print(f"Rejected folder: {f}")
        print(f"foldersRenamed={foldersRenamed} foldersRejected={foldersRejected}")

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
            print("Saved: moviesFolder = %s" % self.moviesFolder)
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
            print("Saved: additionalMoviesFolder = %s" % additionalMoviesFolder)

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

    def backupBrowseFolder(self):
        browseDir = str(Path.home())
        if os.path.exists('%s/Desktop' % browseDir):
            browseDir = '%s/Desktop' % browseDir
        self.backupFolder =\
            QtWidgets.QFileDialog.getExistingDirectory(self,
                                                       "Select Backup Folder",
                                                       browseDir,
                                                       QtWidgets.QFileDialog.ShowDirsOnly |
                                                       QtWidgets.QFileDialog.DontResolveSymlinks)

        #if self.backupFolder == self.moviesFolder:
        #    mb = QtWidgets.QMessageBox()
        #    mb.setText("Error: Backup folder must be different from movies folder")
        #    mb.setIcon(QtWidgets.QMessageBox.Critical)
        #    mb.exec()
        #    return

        if os.path.exists(self.backupFolder):
            self.backupFolderEdit.setText(self.backupFolder)
            drive = os.path.splitdrive(self.backupFolder)[0]

            self.spaceTotal, self.spaceUsed, self.spaceFree = shutil.disk_usage(drive)
            self.spaceUsedPercent = self.spaceUsed / self.spaceTotal
            self.spaceBarLayout.setStretch(0, self.spaceUsedPercent * 1000)
            self.spaceBarLayout.setStretch(2, (1.0 - self.spaceUsedPercent) * 1000)

            self.spaceAvailableLabel.setText("%dGb  Of  %dGb  Used       %dGb Free" % \
                                             (bToGb(self.spaceUsed),
                                              bToGb(self.spaceTotal),
                                              bToGb(self.spaceFree)))

    def calculateFolderSize(self, sourceIndex, moviePath, movieFolderName):
        folderSize = '%05d Mb' % bToMb(getFolderSize(moviePath))

        jsonFile = os.path.join(moviePath, '%s.json' % movieFolderName)
        if not os.path.exists(jsonFile):
            return

        data = {}
        with open(jsonFile) as f:
            try:
                data = json.load(f)
            except UnicodeDecodeError:
                print("Error reading %s" % jsonFile)

        data["size"] = folderSize
        try:
            with open(jsonFile, "w") as f:
                json.dump(data, f, indent=4)
        except:
            print("Error writing json file: %s" % jsonFile)

        self.moviesTableModel.setSize(sourceIndex, folderSize)

    def calculateFolderSizes(self):
        numSelectedItems = len(self.moviesTableView.selectionModel().selectedRows())
        self.progressBar.setMaximum(numSelectedItems)
        progress = 0
        self.isCanceled = False
        self.moviesTableModel.aboutToChangeLayout()
        for proxyIndex in self.moviesTableView.selectionModel().selectedRows():
            QtCore.QCoreApplication.processEvents()
            if self.isCanceled:
                self.statusBar().showMessage('Cancelled')
                self.isCanceled = False
                self.progressBar.setValue(0)
                self.moviesTableModel.changedLayout()
                return

            progress += 1
            self.progressBar.setValue(progress)

            sourceIndex = self.moviesTableProxyModel.mapToSource(proxyIndex)
            movieFolderName = self.moviesTableModel.getFolderName(sourceIndex.row())
            moviePath = self.moviesTableModel.getPath(sourceIndex.row())
            if not os.path.exists(moviePath):
                continue

            self.calculateFolderSize(sourceIndex, moviePath, movieFolderName)

        self.moviesTableModel.changedLayout()
        self.progressBar.setValue(0)

    def calculateMovieDimension(self, sourceIndex, moviePath, movieFolderName):
        width, height = self.getMovieDimensions(moviePath)

        jsonFile = os.path.join(moviePath, '%s.json' % movieFolderName)
        if not os.path.exists(jsonFile):
            return

        data = {}
        with open(jsonFile) as f:
            try:
                data = json.load(f)
            except UnicodeDecodeError:
                print("Error reading %s" % jsonFile)

        data["width"] = width
        data["height"] = height

        self.moviesTableModel.setMovieData(sourceIndex.row(),
                                           data,
                                           moviePath,
                                           movieFolderName)

        try:
            with open(jsonFile, "w") as f:
                json.dump(data, f, indent=4)
        except:
            print("Error writing json file: %s" % jsonFile)
        pass

    def calculateMovieDimensions(self):
        numSelectedItems = len(self.moviesTableView.selectionModel().selectedRows())
        self.progressBar.setMaximum(numSelectedItems)
        progress = 0
        self.isCanceled = False
        self.moviesTableModel.aboutToChangeLayout()
        for proxyIndex in self.moviesTableView.selectionModel().selectedRows():
            QtCore.QCoreApplication.processEvents()
            if self.isCanceled:
                self.statusBar().showMessage('Cancelled')
                self.isCanceled = False
                self.progressBar.setValue(0)
                self.moviesTableModel.changedLayout()
                return

            progress += 1
            self.progressBar.setValue(progress)

            sourceIndex = self.moviesTableProxyModel.mapToSource(proxyIndex)
            movieFolderName = self.moviesTableModel.getFolderName(sourceIndex.row())
            moviePath = self.moviesTableModel.getPath(sourceIndex.row())
            if not os.path.exists(moviePath):
                continue

            self.calculateMovieDimension(sourceIndex, moviePath, movieFolderName)

        self.moviesTableModel.changedLayout()
        self.progressBar.setValue(0)

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
            moviePath = self.moviesTableModel.getPath(modelIndex.row())
            with os.scandir(moviePath) as files:
                for f in files:
                    if f.is_dir() and fnmatch.fnmatch(f, '*(*)'):
                        print(f"Movie: {moviePath} contains other movie: {f.name}")

        self.moviesTableModel.changedLayout()
        self.progressBar.setValue(0)

    def findDuplicates(self):
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
            title = self.moviesTableModel.getTitle(modelIndex.row())
            year = self.moviesTableModel.getYear(modelIndex.row())
            titleYear = (title, year)
            if titleYear in titleYearSet:
                self.moviesTableModel.setDuplicate(modelIndex, 'Yes')
                duplicates.add(titleYear)
            else:
                self.moviesTableModel.setDuplicate(modelIndex, 'No')
            titleYearSet.add((title, year))

        for row in range(numItems):
            modelIndex = self.moviesTableModel.index(row, 0)
            title = self.moviesTableModel.getTitle(modelIndex.row())
            year = self.moviesTableModel.getYear(modelIndex.row())
            titleYear = (title, year)
            if titleYear in duplicates:
                self.moviesTableModel.setDuplicate(modelIndex, 'Yes')

        self.moviesTableModel.changedLayout()
        self.progressBar.setValue(0)

    def backupAnalyse(self):
        if not self.backupFolder:
            mb = QtWidgets.QMessageBox()
            mb.setText("Destination folder is not set")
            mb.setIcon(QtWidgets.QMessageBox.Critical)
            mb.exec()
            return

        numItems = self.backupListTableProxyModel.rowCount()
        self.progressBar.setMaximum(numItems)
        progress = 0
        self.isCanceled = False
        self.backupListTableModel.aboutToChangeLayout()
        self.bytesToBeCopied = 0
        self.sourceFolderSizes = {}
        self.destFolderSizes = {}
        for row in range(numItems):
            QtCore.QCoreApplication.processEvents()
            if self.isCanceled:
                self.statusBar().showMessage('Cancelled')
                self.isCanceled = False
                self.progressBar.setValue(0)
                self.backupListTableModel.changedLayout()
                return

            progress += 1
            self.progressBar.setValue(progress)

            modelIndex = self.backupListTableProxyModel.index(row, 0)
            sourceIndex = self.backupListTableProxyModel.mapToSource(modelIndex)
            sourceRow = sourceIndex.row()
            title = self.backupListTableModel.getTitle(sourceRow)
            sourcePath = self.backupListTableModel.getPath(sourceRow)
            sourceFolderName = self.backupListTableModel.getFolderName(sourceRow)
            destPath = os.path.join(self.backupFolder, sourceFolderName)

            sourceFolderSize = getFolderSize(sourcePath)
            self.backupListTableModel.setSize(sourceIndex, '%05d Mb' % bToMb(sourceFolderSize))
            self.sourceFolderSizes[sourceFolderName] = sourceFolderSize

            destFolderSize = 0
            if os.path.exists(destPath):
                destFolderSize = getFolderSize(destPath)
            self.destFolderSizes[sourceFolderName] = destFolderSize

            sourceFilesAndSizes = getFolderSizes(sourcePath)
            if os.path.exists(destPath):
                destFilesAndSizes = getFolderSizes(destPath)

            if not os.path.exists(destPath):
                self.backupListTableModel.setBackupStatus(sourceIndex, "Folder Missing")
                self.bytesToBeCopied += sourceFolderSize
                continue
            else:
                self.backupListTableModel.setBackupStatus(sourceIndex, "No Difference")

            replaceFolder = False

            # Check if any of the destination files are missing or have different sizes
            for f in sourceFilesAndSizes.keys():
                # Check if the destination file exists
                fullDestPath = os.path.join(destPath, f)
                if not os.path.exists(fullDestPath):
                    self.backupListTableModel.setBackupStatus(sourceIndex, "Files Missing (Destination)")
                    replaceFolder = True
                    break

                # Check if the destination file is the same size as the source file
                if not replaceFolder:
                    if f in destFilesAndSizes:
                        destFileSize = destFilesAndSizes[f]
                    else:
                        destFileSize = os.path.getsize(fullDestPath)
                    sourceFileSize = sourceFilesAndSizes[f]
                    if sourceFileSize != destFileSize:
                        print(f'{title} file size difference.  File:{f} Source={sourceFileSize} Dest={destFileSize}')
                        self.backupListTableModel.setBackupStatus(sourceIndex, "File Size Difference")
                        replaceFolder = True
                        break

            # Check if the destination has files that the source doesn't
            if not replaceFolder:
                for f in destFilesAndSizes.keys():
                    # Check if the destination file exists
                    fullSourcePath = os.path.join(sourcePath, f)
                    if not os.path.exists(fullSourcePath):
                        print(f'missing source file {fullDestPath}')
                        self.backupListTableModel.setBackupStatus(sourceIndex, "Files Missing (Source)")
                        replaceFolder = True
                        break

            if replaceFolder:
                self.bytesToBeCopied -= destFolderSize
                self.bytesToBeCopied += sourceFolderSize

            message = "Analysing folder (%d/%d): %s" % (progress + 1,
                                                        numItems,
                                                        title)
            self.statusBar().showMessage(message)
            QtCore.QCoreApplication.processEvents()

        self.backupListTableModel.changedLayout()
        self.statusBar().showMessage("Done")
        self.progressBar.setValue(0)

        if (self.spaceUsed + self.bytesToBeCopied > self.spaceTotal):
            self.spaceUsedWidget.setStyleSheet("background: rgb(255,0,0);"
                                               "border-radius: 0px 0px 0px 0px")
            self.spaceBarLayout.setStretch(0, 1000)
            self.spaceBarLayout.setStretch(1, 0)
            self.spaceBarLayout.setStretch(2, 0)
            mb = QtWidgets.QMessageBox()
            spaceNeeded = self.spaceUsed + self.bytesToBeCopied - self.spaceTotal
            mb.setText("Error: Not enough space in backup folder: %s."
                       "   Need %.2f Gb more space" % (self.backupFolder,
                                                       bToGb(spaceNeeded)))
            mb.setIcon(QtWidgets.QMessageBox.Critical)
            mb.exec()
        else:
            self.spaceUsedWidget.setStyleSheet("background: rgb(0,255,0);"
                                               "border-radius: 0px 0px 0px 0px")
            changePercent = self.bytesToBeCopied / self.spaceTotal
            self.spaceBarLayout.setStretch(0, self.spaceUsedPercent * 1000)
            self.spaceBarLayout.setStretch(1, changePercent * 1000)
            self.spaceBarLayout.setStretch(2, (1.0 - self.spaceUsedPercent - changePercent) * 1000)

        newSize = self.spaceUsed + self.bytesToBeCopied
        self.spaceFree = self.spaceTotal - newSize
        newSpacePercent = newSize / self.spaceTotal
        self.spaceAvailableLabel.setText("%dGb  Of  %dGb  Used       %dGb Free" % \
                                         (bToGb(newSize),
                                         bToGb(self.spaceTotal),
                                         bToGb(self.spaceFree)))

        self.backupAnalysed = True

    def backupRun(self, moveFiles=False):
        if not self.backupFolder:
            mb = QtWidgets.QMessageBox()
            mb.setText("Destination folder is not set")
            mb.setIcon(QtWidgets.QMessageBox.Critical)
            mb.exec()
            return

        if not self.backupAnalysed:
            mb = QtWidgets.QMessageBox()
            mb.setText("Run analyses first by pressing Analyse button")
            mb.setIcon(QtWidgets.QMessageBox.Critical)
            mb.exec()
            return

        self.isCanceled = False
        self.backupListTableModel.aboutToChangeLayout()

        progress = 0
        lastBytesPerSecond = 0
        totalBytesCopied = 0
        totalTimeToCopy = 0
        averageBytesPerSecond = 0
        bytesRemaining = self.bytesToBeCopied
        estimatedHoursRemaining = 0
        estimatedMinutesRemaining = 0

        numItems = self.backupListTableProxyModel.rowCount()
        self.progressBar.setMaximum(numItems)
        for row in range(numItems):
            self.backupListTableView.selectRow(row)
            QtCore.QCoreApplication.processEvents()
            if self.isCanceled:
                self.statusBar().showMessage('Cancelled')
                self.isCanceled = False
                self.progressBar.setValue(0)
                self.backupListTableModel.changedLayout()
                return

            progress += 1
            self.progressBar.setValue(progress)

            modelIndex = self.backupListTableProxyModel.index(row, 0)
            sourceIndex = self.backupListTableProxyModel.mapToSource(modelIndex)
            sourceRow = sourceIndex.row()
            title = self.backupListTableModel.getTitle(sourceRow)

            try:
                sourcePath = self.backupListTableModel.getPath(sourceRow)
                sourceFolderName = self.backupListTableModel.getFolderName(sourceRow)
                sourceFolderSize = self.sourceFolderSizes[sourceFolderName]
                destFolderSize = self.destFolderSizes[sourceFolderName]
                destPath = os.path.join(self.backupFolder, sourceFolderName)

                backupStatus = self.backupListTableModel.getBackupStatus(sourceIndex.row())

                message = "Backing up" if not moveFiles else "Moving "
                message += " folder (%05d/%05d): %-50s" \
                           "   Size: %06d Mb" \
                           "   Last rate = %06d Mb/s" \
                           "   Average rate = %06d Mb/s" \
                           "   %10d Mb Remaining" \
                           "   Time remaining: %03d Hours %02d minutes" % \
                           (progress,
                            numItems,
                            title,
                            bToMb(sourceFolderSize),
                            bToMb(lastBytesPerSecond),
                            bToMb(averageBytesPerSecond),
                            bToMb(bytesRemaining),
                            estimatedHoursRemaining,
                            estimatedMinutesRemaining)

                self.statusBar().showMessage(message)
                QtCore.QCoreApplication.processEvents()

                # Time the copy
                startTime = time.perf_counter()
                bytesCopied = 0

                if backupStatus == 'File Size Difference' or \
                   backupStatus == 'Files Missing (Source)' or \
                   backupStatus == 'Files Missing (Destination)':

                    startTime = time.perf_counter()

                    # Copy/move any files that are missing or have different sizes
                    for f in os.listdir(sourcePath):

                        sourceFilePath = os.path.join(sourcePath, f)
                        if os.path.isdir(sourceFilePath):
                            sourceFileSize = getFolderSize(sourceFilePath)
                        else:
                            sourceFileSize = os.path.getsize(sourceFilePath)

                        destFilePath = os.path.join(destPath, f)

                        if not os.path.exists(destFilePath):
                            bytesCopied += sourceFileSize
                            if os.path.isdir(sourceFilePath):
                                shutil.copytree(sourceFilePath, destFilePath)
                            else:
                                shutil.copy(sourceFilePath, destFilePath)
                        else:
                            destFileSize = 0
                            if os.path.exists(destFilePath):
                                if os.path.isdir(destFilePath):
                                    destFileSize = getFolderSize(destFilePath)
                                else:
                                    destFileSize = os.path.getsize(destFilePath)

                            if sourceFileSize != destFileSize:
                                bytesCopied += sourceFileSize
                                if os.path.isdir(sourceFilePath):
                                    shutil.rmtree(destFilePath,
                                                  ignore_errors=False,
                                                  onerror=handleRemoveReadonly)

                                    shutil.copytree(sourceFilePath, destFilePath)
                                else:
                                    shutil.copy(sourceFilePath, destFilePath)

                        if moveFiles:
                            shutil.rmtree(sourceFilePath,
                                          ignore_errors=False,
                                          onerror=handleRemoveReadonly)

                    # Remove any files in the destination dir that
                    # are not in the source dir
                    for f in os.listdir(destPath):
                        destFilePath = os.path.join(destPath, f)
                        sourceFilePath = os.path.join(sourcePath, f)
                        if not os.path.exists(sourceFilePath):
                            if os.path.isdir(destFilePath):
                                shutil.rmtree(destFilePath,
                                              ignore_errors=False,
                                              onerror=handleRemoveReadonly)
                            else:
                                os.chmod(destFilePath, stat.S_IWRITE)
                                os.remove(destFilePath)

                    bytesRemaining += destFolderSize
                    bytesRemaining -= sourceFolderSize
                elif backupStatus == 'Folder Missing':
                    shutil.copytree(sourcePath, destPath)
                    bytesCopied = sourceFolderSize
                    bytesRemaining -= sourceFolderSize
                else:
                    bytesCopied = 0
                    sourceFolderSize = 0

                if sourceFolderSize != 0:
                    endTime = time.perf_counter()
                    secondsToCopy = endTime - startTime
                    lastBytesPerSecond = bytesCopied / secondsToCopy
                    totalTimeToCopy += secondsToCopy
                    totalBytesCopied += bytesCopied
                    averageBytesPerSecond = totalBytesCopied / totalTimeToCopy
                    if averageBytesPerSecond != 0:
                        estimatedSecondsRemaining = bytesRemaining // averageBytesPerSecond
                        estimatedMinutesRemaining = (estimatedSecondsRemaining // 60) % 60
                        estimatedHoursRemaining = estimatedSecondsRemaining // 3600
            except Exception as e:
                print(f"Problem copying movie: {title} - {e}")

        self.backupListTableModel.changedLayout()
        self.statusBar().showMessage("Done")
        self.progressBar.setValue(0)

    def cancelButtonClicked(self):
        self.isCanceled = True

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
            visibleRows = list()
            for row in range(numRowsProxy):
                if not self.moviesTableView.isRowHidden(row):
                    visibleRows.append(row)
            randomRow = currentRow
            while randomRow == currentRow:
                randomIndex = random.randint(0, len(visibleRows) - 1)
                randomRow = visibleRows[randomIndex]
            #self.moviesTableView.selectRow(randomRow)
            self.emitCover(randomRow, direction)
        else:
            if direction == -1:
                if currentRow == numRowsProxy - 1:
                    currentRow = 0
                else:
                    currentRow += 1
                while self.moviesTableView.isRowHidden(currentRow):
                    currentRow += 1
                    if currentRow == numRowsProxy:
                        currentRow = 0
            else:
                if currentRow == 0:
                    currentRow = numRowsProxy - 1
                else:
                    currentRow = max(0, currentRow - 1)
                while self.moviesTableView.isRowHidden(currentRow):
                    currentRow = max(0, currentRow - 1)
                    if currentRow == 0:
                        currentRow = numRowsProxy - 1

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
        title = model.getTitle(sourceRow)

        moviePath = model.getPath(sourceRow)
        folderName = model.getFolderName(sourceRow)
        year = model.getYear(sourceRow)
        jsonFile = os.path.join(moviePath, '%s.json' % folderName)
        coverFile = os.path.join(moviePath, '%s.jpg' % folderName)
        if not os.path.exists(coverFile):
            coverFilePng = os.path.join(moviePath, '%s.png' % folderName)
            if os.path.exists(coverFilePng):
                coverFile = coverFilePng

        self.titleLabel.setText('"%s" (%s)' % (title, year))
        self.showCoverFile(coverFile)

        jsonData = None
        if os.path.exists(jsonFile):
            with open(jsonFile) as f:
                try:
                    jsonData = json.load(f)
                except UnicodeDecodeError:
                    print("Error reading %s" % jsonFile)
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
        visibleRows = list()
        for row in range(numRowsProxy):
            if not self.moviesTableView.isRowHidden(row):
                visibleRows.append(row)
        if len(visibleRows) == 0:
            return
        randomIndex = random.randint(0, len(visibleRows) - 1)
        randomRow = visibleRows[randomIndex]
        self.moviesTableView.selectRow(randomRow)
        #self.emitCover(randomRow, -1)

    def showAllMoviesTableView(self):
        self.moviesTableTitleFilterBox.clear()
        self.numVisibleMovies = self.moviesTableProxyModel.rowCount()
        self.showMoviesTableSelectionStatus()
        for row in range(self.moviesTableProxyModel.rowCount()):
            self.moviesTableView.setRowHidden(row, False)
        self.moviesTableProxyModel.sort(0)

    def searchPlots(self):
        self.moviesTableTitleFilterBox.clear()

        searchText = self.moviesTableSearchPlotsBox.text()
        if len(searchText) == 0:
            return

        plotsRegex = re.compile(f'.*{searchText}.*', re.IGNORECASE)

        rowCount = self.moviesTableProxyModel.rowCount()
        visibleRowCount = 0
        for row in range(rowCount):
            proxyRow = self.moviesTableProxyModel.index(row, 0).row()
            if not self.moviesTableView.isRowHidden(proxyRow):
                visibleRowCount += 1
        self.progressBar.setMaximum(visibleRowCount)
        progress = 0

        for row in range(rowCount):
            proxyRow = self.moviesTableProxyModel.index(row, 0).row()
            sourceRow = self.getSourceRow2(proxyRow)

            if self.moviesTableView.isRowHidden(proxyRow):
                continue

            # Get Summary
            title = self.moviesTableModel.getTitle(sourceRow)
            moviePath = self.moviesTableModel.getPath(sourceRow)
            folderName = self.moviesTableModel.getFolderName(sourceRow)
            jsonFile = os.path.join(moviePath, '%s.json' % folderName)
            jsonData = None
            if os.path.exists(jsonFile):
                with open(jsonFile) as f:
                    try:
                        jsonData = json.load(f)
                    except UnicodeDecodeError:
                        print("Error reading %s" % jsonFile)

            summary = self.getPlot(jsonData)

            try:
                if not plotsRegex.match(summary) and not plotsRegex.match(title):
                    self.moviesTableView.hideRow(proxyRow)
            except TypeError:
                print(f"TypeError when searching plot for movie: {title}")
                self.moviesTableView.hideRow(proxyRow)

            progress += 1
            self.progressBar.setValue(progress)
        self.progressBar.setValue(0)

    def searchMoviesTableView(self):
        searchText = self.moviesTableTitleFilterBox.text()
        if not searchText:
            self.filterTableSelectionChanged()

        self.moviesTableProxyModel.setFilterKeyColumn(self.moviesTableModel.Columns.Title.value)
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

    def movieInfoSelectionChanged(self):
        if len(self.movieInfoListView.selectedItems()) == 0:
            return

        self.moviesTableTitleFilterBox.clear()

        movieList = []
        for item in self.movieInfoListView.selectedItems():
            smdbKey = None
            category = item.data(QtCore.Qt.UserRole)[0]
            name = str(item.data(QtCore.Qt.UserRole)[1])
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

        for row in range(self.moviesTableProxyModel.rowCount()):
            self.moviesTableView.setRowHidden(row, True)

        self.progressBar.setMaximum(len(movieList))

        progress = 0
        firstRow = -1
        self.numVisibleMovies = 0
        for row in range(self.moviesTableProxyModel.rowCount()):
            proxyModelIndex = self.moviesTableProxyModel.index(row, 0)
            sourceIndex = self.moviesTableProxyModel.mapToSource(proxyModelIndex)
            sourceRow = sourceIndex.row()
            title = self.moviesTableModel.getTitle(sourceRow)
            year = self.moviesTableModel.getYear(sourceRow)

            for (t, y) in movieList:
                if t == title and y == year:
                    self.numVisibleMovies += 1
                    if firstRow == -1:
                        firstRow = row
                    self.moviesTableView.setRowHidden(row, False)
            progress += 1
            self.progressBar.setValue(progress)

        self.progressBar.setValue(0)
        self.showMoviesTableSelectionStatus()

    def filterTableSelectionChanged(self, mainFilter=True):
        if len(self.primaryFilterWidget.filterTable.selectedItems()) == 0:
            self.showAllMoviesTableView()
            return

        filterByText = self.primaryFilterWidget.filterByComboBox.currentText()
        filterByKey = self.primaryFilterWidget.filterByDict[filterByText]

        movieList = []
        for item in self.primaryFilterWidget.filterTable.selectedItems():
            name = self.primaryFilterWidget.filterTable.item(item.row(), 0).text()
            movies = self.moviesSmdbData[filterByKey][name]['movies']
            for movie in movies:
                movieList.append(movie)

        if mainFilter:
            self.secondaryFilterWidget.movieList = movieList
            self.secondaryFilterWidget.populateFiltersTable()

        filter2ByText = self.secondaryFilterWidget.filterByComboBox.currentText()
        filter2ByKey = self.secondaryFilterWidget.filterByDict[filter2ByText]
        if filterByText != filter2ByText and len(self.secondaryFilterWidget.filterTable.selectedItems()) != 0:
            movieList2 = list()
            for movie in movieList:
                foundMovie = False
                for item in self.secondaryFilterWidget.filterTable.selectedItems():
                    name = self.secondaryFilterWidget.filterTable.item(item.row(), 0).text()
                    movies = self.moviesSmdbData[filter2ByKey][name]['movies']
                    if movie in movies:
                        foundMovie = True
                        break
                if foundMovie:
                    movieList2.append(movie)
            movieList = movieList2

        for row in range(self.moviesTableProxyModel.rowCount()):
            self.moviesTableView.setRowHidden(row, True)

        self.progressBar.setMaximum(len(movieList))

        progress = 0
        firstRow = -1
        self.numVisibleMovies = 0
        for row in range(self.moviesTableProxyModel.rowCount()):
            proxyModelIndex = self.moviesTableProxyModel.index(row, 0)
            sourceIndex = self.moviesTableProxyModel.mapToSource(proxyModelIndex)
            sourceRow = sourceIndex.row()
            title = self.moviesTableModel.getTitle(sourceRow)
            year = self.moviesTableModel.getYear(sourceRow)

            for (t, y) in movieList:
                if t == title and y == year:
                    self.numVisibleMovies += 1
                    if firstRow == -1:
                        firstRow = row
                    self.moviesTableView.setRowHidden(row, False)
            progress += 1
            self.progressBar.setValue(progress)

        self.moviesTableView.selectRow(firstRow)
        self.progressBar.setValue(0)
        self.showMoviesTableSelectionStatus()

        sortColumn = self.moviesTableProxyModel.sortColumn()
        sortOrder = self.moviesTableProxyModel.sortOrder()
        self.moviesTableProxyModel.sort(sortColumn, sortOrder)

    def resizeCoverFile(self):
        if self.movieCover:
            sz = self.movieCover.size()
            coverFile = self.movieCover.property('cover file')
            pixMap = QtGui.QPixmap(coverFile)
            self.movieCover.setPixmap(pixMap.scaled(sz.width(), sz.height(),
                                                    QtCore.Qt.KeepAspectRatio,
                                                    QtCore.Qt.SmoothTransformation))

    def resizeEvent(self, a0: QtGui.QResizeEvent) -> None:
        self.resizeCoverFile()

    def showCoverFile(self, coverFile):
        if os.path.exists(coverFile):
            pixMap = QtGui.QPixmap(coverFile)
            sz = self.movieCover.size()
            self.movieCover.setPixmap(pixMap.scaled(sz.width(), sz.height(),
                                                    QtCore.Qt.KeepAspectRatio,
                                                    QtCore.Qt.SmoothTransformation))
            self.movieCover.setProperty('cover file', coverFile)
        else:
            self.movieCover.setPixmap(QtGui.QPixmap(0, 0))

    def movieInfoAddSection(self, jsonData, jsonName, smdbName, userRoleName):
        if not jsonData:
            return
        if jsonName in jsonData and jsonData[jsonName]:
            for name in jsonData[jsonName]:
                numMovies = 0
                if name in self.moviesSmdbData[smdbName]:
                    numMovies = self.moviesSmdbData[smdbName][name]['num movies']
                item = QtWidgets.QListWidgetItem('%s (%d)' % (name, numMovies))
                item.setData(QtCore.Qt.UserRole, [userRoleName, name])
                self.movieInfoListView.addItem(item)

    def movieInfoAddHeading(self, headerName):
        item = QtWidgets.QListWidgetItem(headerName)
        item.setFlags(QtCore.Qt.ItemIsEnabled)
        item.setForeground(QtCore.Qt.gray)
        self.movieInfoListView.addItem(item)

    def movieInfoAddSpacer(self):
        spacerItem = QtWidgets.QListWidgetItem("")
        spacerItem.setFlags(QtCore.Qt.ItemIsEnabled)
        self.movieInfoListView.addItem(spacerItem)

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

        self.movieInfoListView.setCurrentRow(0)

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
            infoText += '%s<br>' % plot
        if 'synopsis' in jsonData and jsonData['synopsis']:
            infoText += '<br>Synopsis:<br>'
            if isinstance(jsonData['synopsis'], list):
                synopsis = jsonData['synopsis'][0]
            else:
                synopsis = jsonData['synopsis']
            # Remove the author of the synopsis's name
            synopsis = synopsis.split('::')[0]
            infoText += '%s<br>' % synopsis
        return infoText

    def summaryShow(self, jsonData):
        infoText = self.getSummary(jsonData)
        self.summary.setText(infoText)

    def writeMovieJson(self, movie, jsonFile):
        d = {}
        d['title'] = getMovieKey(movie, 'title')
        d['id'] = movie.getID()
        d['kind'] = getMovieKey(movie, 'kind')
        d['year'] = getMovieKey(movie, 'year')
        d['rating'] = getMovieKey(movie, 'rating')

        mpaaRating = ""
        if 'certificates' in movie:
            certificates = movie['certificates']
            for c in certificates:
                if 'United States' in c and 'TV' not in c:
                    mpaaRating = c.split(':')[1]
                    print('MPAA rating = %s' % mpaaRating)
        d['mpaa rating'] = mpaaRating

        d['countries'] = []
        countries = getMovieKey(movie, 'countries')
        if countries and isinstance(countries, list):
            for c in countries:
                d['countries'].append(c)
        d['companies'] = []
        companies = getMovieKey(movie, 'production companies')
        if companies and isinstance(companies, list):
            for c in companies:
                d['companies'].append(c['name'])
        runtimes = getMovieKey(movie, 'runtimes')
        if runtimes:
            d['runtime'] = runtimes[0]
        boxOffice = getMovieKey(movie, 'box office')
        if boxOffice:
            for k in boxOffice.keys():
                d['box office'] = boxOffice[k]
        directors = getMovieKey(movie, 'director')
        d['directors'] = []
        if directors:
            for director in directors:
                directorName = str(director['name'])
                directorId = self.db.name2imdbID(directorName)
                d['directors'].append(directorName)
        d['cast'] = []
        cast = getMovieKey(movie, 'cast')
        if cast and isinstance(cast, list):
            for c in movie['cast']:
                d['cast'].append(c['name'])
        d['genres'] = getMovieKey(movie, 'genres')
        d['plot'] = getMovieKey(movie, 'plot')
        d['plot outline'] = getMovieKey(movie, 'plot outline')
        d['synopsis'] = getMovieKey(movie, 'synopsis')
        d['summary'] = movie.summary()
        d['cover url'] = getMovieKey(movie, 'cover url')
        d['full-size cover url'] = getMovieKey(movie, 'full-size cover url')

        try:
            with open(jsonFile, "w") as f:
                json.dump(d, f, indent=4)
        except:
            print("Error writing json file: %s" % jsonFile)

    def writeSmdbFile(self, fileName, model, titlesOnly=False):
        titles = {}
        directors = {}
        actors = {}
        mpaaRatings = {}
        ratings = {}
        genres = {}
        years = {}
        companies = {}
        countries = {}
        userTags = {}

        count = model.rowCount()
        self.progressBar.setMaximum(count)
        progress = 0
        self.isCanceled = False

        # For box office $
        reMoneyValue = re.compile(r'(\d+(?:,\d+)*(?:\.\d+)?)')
        reCurrency = re.compile(r'^([A-Z][A-Z][A-Z])(.*)')

        for row in range(count):
            QtCore.QCoreApplication.processEvents()
            if self.isCanceled:
                self.statusBar().showMessage('Cancelled')
                self.isCanceled = False
                self.progressBar.setValue(0)
                return

            progress += 1
            self.progressBar.setValue(progress)

            title = model.getTitle(row)

            message = "Processing item (%d/%d): %s" % (progress + 1,
                                                       count,
                                                       title)
            self.statusBar().showMessage(message)
            QtCore.QCoreApplication.processEvents()

            rank = model.getRank(row)
            moviePath = model.getPath(row)
            if not os.path.exists(moviePath):
                print(f"path does not exist: {moviePath}")
                continue

            fname = pathlib.Path(moviePath)
            dateModified = datetime.datetime.fromtimestamp(fname.stat().st_mtime)
            dateModified = f"{dateModified.year}/{str(dateModified.month).zfill(2)}/{str(dateModified.day).zfill(2)}"
            folderName = model.getFolderName(row)
            jsonFile = os.path.join(moviePath, '%s.json' % folderName)
            if os.path.exists(jsonFile):
                with open(jsonFile) as f:
                    try:
                        jsonData = json.load(f)
                    except UnicodeDecodeError:
                        print("Error reading %s" % jsonFile)
                        continue

                if 'title' in jsonData and 'year' in jsonData:
                    jsonTitle = jsonData['title']
                    jsonYear = jsonData['year']
                    titleYear = (jsonTitle, jsonYear)

                    jsonWidth = 0
                    if 'width' in jsonData and jsonData['width']:
                        jsonWidth = jsonData['width']

                    jsonHeight = 0
                    if 'height' in jsonData and jsonData['height']:
                        jsonHeight = jsonData['height']

                    jsonSize = 0
                    if 'size' in jsonData and jsonData['size']:
                        jsonSize = jsonData['size']

                    jsonYear = None
                    if 'year' in jsonData and jsonData['year']:
                        jsonYear = jsonData['year']
                        if jsonYear not in years:
                            years[jsonYear] = {}
                            years[jsonYear]['num movies'] = 0
                            years[jsonYear]['movies'] = []
                        if titleYear not in years[jsonYear]:
                            years[jsonYear]['movies'].append(titleYear)
                            years[jsonYear]['num movies'] += 1

                    movieDirectorList = []
                    if 'directors' in jsonData and jsonData['directors']:
                        for director in jsonData['directors']:
                            if director not in directors:
                                directors[director] = {}
                                directors[director]['num movies'] = 0
                                directors[director]['movies'] = []
                            if titleYear not in directors[director]['movies']:
                                directors[director]['movies'].append(titleYear)
                                directors[director]['num movies'] += 1

                            movieDirectorList.append(director)

                    movieActorsList = []
                    if 'cast' in jsonData and jsonData['cast']:
                        for actor in jsonData['cast']:
                            if actor not in actors:
                                actors[actor] = {}
                                actors[actor]['num movies'] = 0
                                actors[actor]['movies'] = []
                            if titleYear not in actors[actor]['movies']:
                                actors[actor]['movies'].append(titleYear)
                                actors[actor]['num movies'] += 1

                            movieActorsList.append(actor)

                    jsonUserTags = None
                    if 'user tags' in jsonData and jsonData['user tags']:
                        jsonUserTags = jsonData['user tags']
                        for tag in jsonUserTags:
                            if tag not in userTags:
                                userTags[tag] = {}
                                userTags[tag]['num movies'] = 0
                                userTags[tag]['movies'] = []
                            if titleYear not in userTags[tag]['movies']:
                                userTags[tag]['movies'].append(titleYear)
                                userTags[tag]['num movies'] += 1

                    jsonGenres = None
                    if 'genres' in jsonData and jsonData['genres']:
                        jsonGenres = jsonData['genres']
                        for genre in jsonGenres:
                            if genre not in genres:
                                genres[genre] = {}
                                genres[genre]['num movies'] = 0
                                genres[genre]['movies'] = []
                            if titleYear not in genres[genre]['movies']:
                                genres[genre]['movies'].append(titleYear)
                                genres[genre]['num movies'] += 1

                    jsonCompanies = None
                    if 'companies' in jsonData and jsonData['companies']:
                        jsonCompanies = jsonData['companies']
                        for company in jsonCompanies:
                            if company not in companies:
                                companies[company] = {}
                                companies[company]['num movies'] = 0
                                companies[company]['movies'] = []
                            if titleYear not in companies[company]['movies']:
                                companies[company]['movies'].append(titleYear)
                                companies[company]['num movies'] += 1

                    jsonCountries = None
                    if 'countries' in jsonData and jsonData['countries']:
                        jsonCountries = jsonData['countries']
                        for country in jsonCountries:
                            if country not in countries:
                                countries[country] = {}
                                countries[country]['num movies'] = 0
                                countries[country]['movies'] = []
                            if titleYear not in countries[country]['movies']:
                                countries[country]['movies'].append(titleYear)
                                countries[country]['num movies'] += 1

                    jsonId = None
                    if 'id' in jsonData and jsonData['id']:
                        jsonId = jsonData['id']

                    jsonRating = None
                    if 'rating' in jsonData and jsonData['rating']:
                        jsonRating = jsonData['rating']
                        if jsonRating not in ratings:
                            ratings[jsonRating] = {}
                            ratings[jsonRating]['num movies'] = 0
                            ratings[jsonRating]['movies'] = []
                        if titleYear not in ratings[jsonRating]['movies']:
                            ratings[jsonRating]['movies'].append(titleYear)
                            ratings[jsonRating]['num movies'] += 1

                    jsonMpaaRating = None
                    if 'mpaa rating' in jsonData and jsonData['mpaa rating']:
                        jsonMpaaRating = jsonData['mpaa rating']
                        if jsonMpaaRating not in mpaaRatings:
                            mpaaRatings[jsonMpaaRating] = {}
                            mpaaRatings[jsonMpaaRating]['num movies'] = 0
                            mpaaRatings[jsonMpaaRating]['movies'] = []
                        if titleYear not in mpaaRatings[jsonMpaaRating]['movies']:
                            mpaaRatings[jsonMpaaRating]['movies'].append(titleYear)
                            mpaaRatings[jsonMpaaRating]['num movies'] += 1

                    jsonBoxOffice = None
                    if 'box office' in jsonData and jsonData['box office']:
                        jsonBoxOffice = jsonData['box office']

                        currency = 'USD'
                        if jsonBoxOffice:
                            jsonBoxOffice = jsonBoxOffice.replace(' (estimated)', '')
                            match = re.match(reCurrency, jsonBoxOffice)
                            if match:
                                currency = match.group(1)
                                jsonBoxOffice = '$%s' % match.group(2)
                            results = re.findall(reMoneyValue, jsonBoxOffice)
                            if currency == 'USD':
                                amount = '$%s' % results[0]
                            else:
                                amount = '%s' % results[0]
                        else:
                            amount = '$0'
                        jsonBoxOffice = '%-3s %15s' % (currency, amount)

                    jsonRuntime = None
                    if 'runtime' in jsonData and jsonData['runtime']:
                        jsonRuntime = jsonData['runtime']

                    titles[moviePath] = {'folder': folderName,
                                          'id': jsonId,
                                          'title': jsonTitle,
                                          'year': jsonYear,
                                          'rating': jsonRating,
                                          'mpaa rating': jsonMpaaRating,
                                          'runtime': jsonRuntime,
                                          'box office': jsonBoxOffice,
                                          'directors': movieDirectorList,
                                          'genres': jsonGenres,
                                          'user tags': jsonUserTags,
                                          'countries': jsonCountries,
                                          'companies': jsonCompanies,
                                          'actors': movieActorsList,
                                          'rank': rank,
                                          'width': jsonWidth,
                                          'height': jsonHeight,
                                          'size': jsonSize,
                                          'path': moviePath,
                                          'date': dateModified}

        self.progressBar.setValue(0)

        self.statusBar().showMessage('Sorting Data...')
        QtCore.QCoreApplication.processEvents()

        data = {'titles': collections.OrderedDict(sorted(titles.items()))}
        if not titlesOnly:
            data['years'] = collections.OrderedDict(sorted(years.items()))
            data['genres'] = collections.OrderedDict(sorted(genres.items()))
            data['directors'] = collections.OrderedDict(sorted(directors.items()))
            data['actors'] = collections.OrderedDict(sorted(actors.items()))
            data['companies'] = collections.OrderedDict(sorted(companies.items()))
            data['countries'] = collections.OrderedDict(sorted(countries.items()))
            data['user tags'] = collections.OrderedDict(sorted(userTags.items()))
            data['mpaa ratings'] = collections.OrderedDict(sorted(mpaaRatings.items()))
            data['ratings'] = collections.OrderedDict(sorted(ratings.items()))

        self.statusBar().showMessage('Writing %s' % fileName)
        QtCore.QCoreApplication.processEvents()

        with open(fileName, "w") as f:
            json.dump(data, f, indent=4)

        self.statusBar().showMessage('Done')
        QtCore.QCoreApplication.processEvents()

        return data

    def downloadMovieData(self, proxyIndex, force=False, movieId=None, doJson=True, doCover=True):
        sourceIndex = self.moviesTableProxyModel.mapToSource(proxyIndex)
        sourceRow = sourceIndex.row()
        moviePath = self.moviesTableModel.getPath(sourceRow)
        movieFolderName = self.moviesTableModel.getFolderName(sourceRow)
        jsonFile = os.path.join(moviePath, '%s.json' % movieFolderName)
        coverFile = os.path.join(moviePath, '%s.jpg' % movieFolderName)
        if not os.path.exists(coverFile):
            coverFilePng = os.path.join(moviePath, '%s.png' % movieFolderName)
            if os.path.exists(coverFilePng):
                coverFile = coverFilePng

        if force is True or not os.path.exists(jsonFile) or not os.path.exists(coverFile):
            if movieId:
                movie = self.getMovieWithId(movieId)
            else:
                movie = self.getMovie(movieFolderName)
            if not movie:
                return coverFile
            self.db.update(movie)

            # Print out all the movie keys
            #for k in movie.keys():
            #    print(k)

            if doJson:
                self.writeMovieJson(movie, jsonFile)
                self.calculateFolderSize(proxyIndex, moviePath, movieFolderName)
                self.calculateMovieDimension(proxyIndex, moviePath, movieFolderName)

            if doCover:
                coverFile = copyCoverImage(movie, coverFile)

            self.moviesTableModel.setMovieDataWithJson(sourceRow,
                                                       jsonFile,
                                                       moviePath,
                                                       movieFolderName)

        return coverFile

    def getMovieWithId(self, movieId):
        movie = self.db.get_movie(movieId)
        return movie

    def getMovie(self, folderName) -> object:
        m = re.match(r'(.*)\((.*)\)', folderName)
        title = m.group(1)

        try:
            year = int(m.group(2))
        except ValueError:
            print('Problem converting year to integer for movie: %s' % folderName)
            return None

        splitTitle = splitCamelCase(title)

        searchText = ' '.join(splitTitle)
        print('Searching for: %s' % searchText)

        try:
            results = self.db.search_movie(searchText)
        except:
            print("Error accessing imdb")
            return None

        if not results:
            print('No matches for: %s' % searchText)
            return None

        acceptableKinds = ('movie', 'short', 'tv movie', 'tv miniseries')

        movie = results[0]
        for res in results:
            if 'year' in res and 'kind' in res:
                kind = res['kind']
                if res['year'] == year and (kind in acceptableKinds):
                    movie = res
                    print('Found result: %s (%s)' % (movie['title'], movie['year']))
                    break

        return movie

    # Context Menus -----------------------------------------------------------

    def movieInfoRightMenu(self):
        rightMenu = QtWidgets.QMenu(self.movieInfoListView)
        selectedItem = self.movieInfoListView.itemAt(self.movieInfoListView.mouseLocation)
        category = selectedItem.data(QtCore.Qt.UserRole)[0]
        if category == 'director' or category == 'actor' or category == 'year':
            openImdbAction = QtWidgets.QAction("Open IMDB Page", self)
            itemText = selectedItem.text()
            if category == 'director' or category == 'actor':
                openImdbAction.triggered.connect(lambda: openPersonImdbPage(itemText, self.db))
            elif category == 'year':
                openImdbAction.triggered.connect(lambda: openYearImdbPage(itemText))
            rightMenu.addAction(openImdbAction)
            rightMenu.exec_(QtGui.QCursor.pos())

    def watchListTableRightMenuShow(self, QPos):
        rightMenu = QtWidgets.QMenu(self.moviesTableView)

        selectAllAction = QtWidgets.QAction("Select All", self)
        selectAllAction.triggered.connect(lambda: self.tableSelectAll(self.watchListTableView))
        rightMenu.addAction(selectAllAction)

        playAction = QtWidgets.QAction("Play", self)
        playAction.triggered.connect(lambda: self.playMovie(self.watchListTableView,
                                                            self.watchListTableProxyModel))
        rightMenu.addAction(playAction)

        removeFromWatchListAction = QtWidgets.QAction("Remove From Watch List", self)
        removeFromWatchListAction.triggered.connect(self.watchListRemove)
        rightMenu.addAction(removeFromWatchListAction)

        moveToTopWatchListAction = QtWidgets.QAction("Move To Top", self)
        moveToTopWatchListAction.triggered.connect(lambda: self.watchListMoveRow(self.MoveTo.TOP))
        rightMenu.addAction(moveToTopWatchListAction)

        moveUpWatchListAction = QtWidgets.QAction("Move Up", self)
        moveUpWatchListAction.triggered.connect(lambda: self.watchListMoveRow(self.MoveTo.UP))
        rightMenu.addAction(moveUpWatchListAction)

        moveDownWatchListAction = QtWidgets.QAction("Move Down", self)
        moveDownWatchListAction.triggered.connect(lambda: self.watchListMoveRow(self.MoveTo.DOWN))
        rightMenu.addAction(moveDownWatchListAction)

        modelIndex = self.watchListTableView.selectionModel().selectedRows()[0]
        self.clickedTable(modelIndex,
                          self.watchListTableModel,
                          self.watchListTableProxyModel)

        rightMenu.exec_(QtGui.QCursor.pos())

    def historyListTableRightMenuShow(self, QPos):
        rightMenu = QtWidgets.QMenu(self.moviesTableView)

        selectAllAction = QtWidgets.QAction("Select All", self)
        selectAllAction.triggered.connect(lambda: self.tableSelectAll(self.historyListTableView))
        rightMenu.addAction(selectAllAction)

        playAction = QtWidgets.QAction("Play", self)
        playAction.triggered.connect(lambda: self.playMovie(self.historyListTableView,
                                                            self.historyListTableProxyModel))
        rightMenu.addAction(playAction)

        removeFromHistoryListAction = QtWidgets.QAction("Remove From History List", self)
        removeFromHistoryListAction.triggered.connect(self.historyListRemove)
        rightMenu.addAction(removeFromHistoryListAction)

        if len(self.historyListTableView.selectionModel().selectedRows()) > 0:
            modelIndex = self.historyListTableView.selectionModel().selectedRows()[0]
            self.clickedTable(modelIndex,
                              self.historyListTableModel,
                              self.historyListTableProxyModel)

        rightMenu.exec_(QtGui.QCursor.pos())

    def openBackupSourceFolder(self):
        proxyIndex = self.backupListTableView.selectionModel().selectedRows()[0]
        sourceIndex = self.backupListTableProxyModel.mapToSource(proxyIndex)
        sourceRow = sourceIndex.row()
        moviePath = self.backupListTableModel.getPath(sourceRow)
        if os.path.exists(moviePath):
            runFile(moviePath)
        else:
            print("Folder doesn't exist")

    def openBackupDestinationFolder(self):
        if not self.backupFolder:
            return
        proxyIndex = self.backupListTableView.selectionModel().selectedRows()[0]
        sourceIndex = self.backupListTableProxyModel.mapToSource(proxyIndex)
        sourceRow = sourceIndex.row()
        movieFolder = self.backupListTableModel.getFolderName(sourceRow)
        moviePath = os.path.join(self.backupFolder, movieFolder)
        if os.path.exists(moviePath):
            runFile(moviePath)
        else:
            print("Folder doesn't exist")

    def backupListAddAllMoviesFrom(self, moviesFolder):
        self.backupListTableModel.layoutAboutToBeChanged.emit()
        numItems = self.moviesTableModel.rowCount()
        for row in range(numItems):
            path = self.moviesTableModel.getPath(row)
            if moviesFolder in path:
                self.backupListTableModel.addMovie(self.moviesSmdbData,
                                                   path)
        self.backupListTableModel.changedLayout()
        self.backupAnalysed = False

    def backupListTableRightMenuShow(self, QPos):
        rightMenu = QtWidgets.QMenu(self.moviesTableView)
        rightMenu.clear()

        selectAllAction = QtWidgets.QAction("Select All", self)
        selectAllAction.triggered.connect(lambda: self.tableSelectAll(self.backupListTableView))
        rightMenu.addAction(selectAllAction)

        movieFolders = list()
        movieFolders.extend(self.additionalMoviesFolders)
        movieFolders.append(self.moviesFolder)
        actions = list()
        for f in movieFolders:
            tmpAction = QtWidgets.QAction(f"Add all movies from {f}")
            tmpAction.triggered.connect(lambda a, folder=f: self.backupListAddAllMoviesFrom(folder))
            rightMenu.addAction(tmpAction)
            actions.append(tmpAction)

        playAction = QtWidgets.QAction("Play", self)
        playAction.triggered.connect(lambda: self.playMovie(self.backupListTableView,
                                                            self.backupListTableProxyModel))
        rightMenu.addAction(playAction)

        openSourceFolderAction = QtWidgets.QAction("Open Source Folder", self)
        openSourceFolderAction.triggered.connect(self.openBackupSourceFolder)
        rightMenu.addAction(openSourceFolderAction)

        openDestinationFolderAction = QtWidgets.QAction("Open Destination Folder", self)
        openDestinationFolderAction.triggered.connect(self.openBackupDestinationFolder)
        rightMenu.addAction(openDestinationFolderAction)

        removeFromWatchListAction = QtWidgets.QAction("Remove From Backup List", self)
        removeFromWatchListAction.triggered.connect(self.backupListRemove)
        rightMenu.addAction(removeFromWatchListAction)

        removeNoDifferenceAction = QtWidgets.QAction("Remove Entries With No Differences", self)
        removeNoDifferenceAction.triggered.connect(self.backupListRemoveNoDifference)
        rightMenu.addAction(removeNoDifferenceAction)

        removeMissingInSourceAction = QtWidgets.QAction("Remove destination folders missing in source", self)
        removeMissingInSourceAction.triggered.connect(self.backupListRemoveMissingInSource)
        rightMenu.addAction(removeMissingInSourceAction)

        moveToTopWatchListAction = QtWidgets.QAction("Move To Top", self)
        moveToTopWatchListAction.triggered.connect(lambda: self.backupListMoveRow(self.MoveTo.TOP))
        rightMenu.addAction(moveToTopWatchListAction)

        moveUpWatchListAction = QtWidgets.QAction("Move Up", self)
        moveUpWatchListAction.triggered.connect(lambda: self.backupListMoveRow(self.MoveTo.UP))
        rightMenu.addAction(moveUpWatchListAction)

        moveDownWatchListAction = QtWidgets.QAction("Move Down", self)
        moveDownWatchListAction.triggered.connect(lambda: self.backupListMoveRow(self.MoveTo.DOWN))
        rightMenu.addAction(moveDownWatchListAction)

        if self.backupListTableProxyModel.rowCount() > 0:
            if len(self.backupListTableView.selectionModel().selectedRows()) > 0:
                modelIndex = self.backupListTableView.selectionModel().selectedRows()[0]
                self.clickedTable(modelIndex,
                                  self.backupListTableModel,
                                  self.backupListTableProxyModel)

        rightMenu.exec_(QtGui.QCursor.pos())

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

        calculateSizesAction = QtWidgets.QAction("Calculate Folder Sizes", self)
        calculateSizesAction.triggered.connect(self.calculateFolderSizes)
        moviesTableRightMenu.addAction(calculateSizesAction)

        calculateDimensionsAction = QtWidgets.QAction("Calculate Movie Dimensions", self)
        calculateDimensionsAction.triggered.connect(self.calculateMovieDimensions)
        moviesTableRightMenu.addAction(calculateDimensionsAction)

        findDuplicatesAction = QtWidgets.QAction("Find Duplicates", self)
        findDuplicatesAction.triggered.connect(self.findDuplicates)
        moviesTableRightMenu.addAction(findDuplicatesAction)

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

        downloadSubtitlesAction = QtWidgets.QAction("Download Subtitles", self)
        downloadSubtitlesAction.triggered.connect(self.downloadSubtitles)
        moviesTableRightMenu.addAction(downloadSubtitlesAction)

        if self.moviesTableView.selectionModel().selectedRows():
            modelIndex = self.moviesTableView.selectionModel().selectedRows()[0]
            self.clickedTable(modelIndex,
                              self.moviesTableModel,
                              self.moviesTableProxyModel)

        moviesTableRightMenu.exec_(QtGui.QCursor.pos())

    def tableSelectAll(self, table):
        table.selectAll()
        pass

    def playMovie(self, table, proxy):
        proxyIndex = table.selectionModel().selectedRows()[0]
        sourceIndex = proxy.mapToSource(proxyIndex)
        sourceRow = sourceIndex.row()
        moviePath = proxy.sourceModel().getPath(sourceRow)
        if not os.path.exists(moviePath):
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

        if table != self.historyListTableView:
            self.historyListAdd(table, proxy)

    @staticmethod
    def getMovieDimensions(moviePath):
        if not os.path.exists(moviePath):
            return

        validExtentions = ['.mkv', '.mpg', '.mp4', '.avi', '.flv', '.wmv', '.m4v', '.divx', '.ogm']

        movieFiles = []
        for file in os.listdir(moviePath):
            extension = os.path.splitext(file)[1].lower()
            if extension in validExtentions:
                movieFiles.append(file)
        if (len(movieFiles) > 0):
            movieFile = os.path.join(moviePath, movieFiles[0])
            info = MediaInfo.parse(movieFile)
            for track in info.tracks:
                if track.track_type == 'Video':
                    return track.width, track.height
            print("No video track for movie: %s" % movieFile)
        else:
            print("No movie files in %s" % moviePath)
        return 0, 0

    def watchListAdd(self):
        self.watchListTableModel.aboutToChangeLayout()
        for modelIndex in self.moviesTableView.selectionModel().selectedRows():
            if not self.moviesTableView.isRowHidden(modelIndex.row()):
                sourceIndex = self.moviesTableProxyModel.mapToSource(modelIndex)
                sourceRow = sourceIndex.row()
                moviePath = self.moviesTableModel.getPath(sourceRow)
                self.watchListTableModel.addMovie(self.moviesSmdbData,
                                                  moviePath)

        self.watchListTableModel.changedLayout()
        self.writeSmdbFile(self.watchListSmdbFile,
                           self.watchListTableModel,
                           titlesOnly=True)

    def historyListAdd(self, table, proxy):
        self.historyListTableModel.aboutToChangeLayout()
        modelIndex = table.selectionModel().selectedRows()[0]
        if not table.isRowHidden(modelIndex.row()):
            sourceIndex = proxy.mapToSource(modelIndex)
            sourceRow = sourceIndex.row()
            moviePath = proxy.sourceModel().getPath(sourceRow)
            self.historyListTableModel.addMovie(self.moviesSmdbData,
                                                moviePath)

        self.historyListTableModel.changedLayout()
        self.writeSmdbFile(self.historyListSmdbFile,
                           self.historyListTableModel,
                           titlesOnly=True)

    def backupListAdd(self):
        self.backupListTableModel.layoutAboutToBeChanged.emit()
        for modelIndex in self.moviesTableView.selectionModel().selectedRows():
            if not self.moviesTableView.isRowHidden(modelIndex.row()):
                sourceIndex = self.moviesTableProxyModel.mapToSource(modelIndex)
                sourceRow = sourceIndex.row()
                moviePath = self.moviesTableModel.getPath(sourceRow)
                self.backupListTableModel.addMovie(self.moviesSmdbData,
                                                   moviePath)

        self.backupListTableModel.changedLayout()
        self.backupAnalysed = False


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
                data = json.load(f)
            except UnicodeDecodeError:
                print("Error reading %s" % jsonFile)

        data["user tags"] = []

        try:
            with open(jsonFile, "w") as f:
                json.dump(data, f, indent=4)
        except:
            print("Error writing json file: %s" % jsonFile)

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
                data = json.load(f)
            except UnicodeDecodeError:
                print("Error reading %s" % jsonFile)

        if "user tags" not in data:
            data["user tags"] = []

        if userTag not in data["user tags"]:
            data["user tags"].append(userTag)

        try:
            with open(jsonFile, "w") as f:
                json.dump(data, f, indent=4)
        except:
            print("Error writing json file: %s" % jsonFile)

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

    def watchListRemove(self):
        selectedRows = self.watchListTableView.selectionModel().selectedRows()
        if len(selectedRows) == 0:
            return

        minRow = selectedRows[0].row()
        maxRow = selectedRows[-1].row()
        self.watchListTableModel.removeMovies(minRow, maxRow)
        self.watchListTableView.selectionModel().clearSelection()
        self.writeSmdbFile(self.watchListSmdbFile,
                           self.watchListTableModel,
                           titlesOnly=True)

    def historyListRemove(self):
        selectedRows = self.historyListTableView.selectionModel().selectedRows()
        if len(selectedRows) == 0:
            return

        minRow = selectedRows[0].row()
        maxRow = selectedRows[-1].row()
        self.historyListTableModel.removeMovies(minRow, maxRow)
        self.historyListTableView.selectionModel().clearSelection()
        self.writeSmdbFile(self.historyListSmdbFile,
                           self.historyListTableModel,
                           titlesOnly=True)

    def backupListRemove(self):
        selectedRows = self.backupListTableView.selectionModel().selectedRows()
        if len(selectedRows) == 0:
            return

        self.backupListTableModel.aboutToChangeLayout()
        rowsToDelete = list()
        for index in selectedRows:
            sourceIndex = self.backupListTableProxyModel.mapToSource(index)
            rowsToDelete.append(sourceIndex.row())

        for row in sorted(rowsToDelete, reverse=True):
            self.backupListTableModel.removeMovie(row)

        self.backupListTableModel.changedLayout()

    def backupListRemoveNoDifference(self):
        self.backupListTableModel.aboutToChangeLayout()
        rowsToDelete = list()
        for row in range(self.backupListTableModel.rowCount()):
            if self.backupListTableModel.getBackupStatus(row) == "No Difference":
                rowsToDelete.append(row)

        for row in sorted(rowsToDelete, reverse=True):
            self.backupListTableModel.removeMovie(row)

        self.backupListTableModel.changedLayout()

    def backupListRemoveMissingInSource(self):
        if not self.backupFolder:
            mb = QtWidgets.QMessageBox()
            mb.setText("Destination folder is not set")
            mb.setIcon(QtWidgets.QMessageBox.Critical)
            mb.exec()
            return

        sourceFolders = list()
        for row in range(self.backupListTableModel.rowCount()):
            sourceFolders.append(self.backupListTableModel.getFolderName(row))

        destPathsToDelete = list()
        with os.scandir(self.backupFolder) as files:
            for f in files:
                if f.is_dir() and fnmatch.fnmatch(f, '*(*)'):
                    destFolder = f.name
                    if destFolder not in sourceFolders:
                        destPath = os.path.join(self.backupFolder, destFolder)
                        print(f'delete: {destPath}')
                        destPathsToDelete.append(destPath)

        if len(destPathsToDelete) != 0:
            mb = QtWidgets.QMessageBox()
            mb.setText("Delete these folders that do not exist in source list?")
            mb.setInformativeText('\n'.join([p for p in destPathsToDelete]))
            mb.setStandardButtons(QMessageBox.Ok|QMessageBox.Cancel)
            mb.setDefaultButton(QMessageBox.Cancel)
            if mb.exec() == QMessageBox.Ok:
                for p in destPathsToDelete:
                    print(f"Deleting: {p}")
                    shutil.rmtree(p,
                                  ignore_errors=False,
                                  onerror=handleRemoveReadonly)

    class MoveTo(Enum):
        DOWN = 0
        UP = 1
        TOP = 2

    def backupListMoveRow(self, moveTo):
        selectedRows = self.backupListTableView.selectionModel().selectedRows()
        if len(selectedRows) == 0:
            return

        minProxyRow = selectedRows[0].row()
        maxProxyRow = selectedRows[-1].row()
        minSourceRow = self.backupListTableProxyModel.mapToSource(selectedRows[0]).row()
        maxSourceRow = self.backupListTableProxyModel.mapToSource(selectedRows[-1]).row()

        if ((moveTo == self.MoveTo.UP or moveTo == self.MoveTo.TOP) and minSourceRow == 0) or \
                (moveTo == self.MoveTo.DOWN and maxSourceRow >= (self.backupListTableModel.getDataSize() - 1)):
            return

        self.backupListTableView.selectionModel().clearSelection()

        dstRow = 0
        topRow = 0
        bottomRow = 0
        if moveTo == self.MoveTo.UP:
            dstRow = minSourceRow - 1
            topRow = minProxyRow - 1
            bottomRow = maxProxyRow - 1
        elif moveTo == self.MoveTo.DOWN:
            dstRow = minSourceRow + 1
            topRow = minProxyRow + 1
            bottomRow = maxProxyRow + 1
        elif moveTo == self.MoveTo.TOP:
            dstRow = 0
            topRow = 0
            bottomRow = maxProxyRow - minProxyRow

        self.backupListTableModel.moveRow(minSourceRow, maxSourceRow, dstRow)
        topLeft = self.backupListTableProxyModel.index(topRow, 0)
        lastColumn = self.moviesTableModel.getLastColumn()
        bottomRight = self.backupListTableProxyModel.index(bottomRow, lastColumn)

        selection = self.backupListTableView.selectionModel().selection()
        selection.select(topLeft, bottomRight)
        self.backupListTableView.selectionModel().select(selection,
                                                        QtCore.QItemSelectionModel.ClearAndSelect)

        self.writeSmdbFile(self.backupListSmdbFile,
                           self.backupListTableModel,
                           titlesOnly=True)

    def watchListMoveRow(self, moveTo):
        selectedRows = self.watchListTableView.selectionModel().selectedRows()
        if len(selectedRows) == 0:
            return

        minProxyRow = selectedRows[0].row()
        maxProxyRow = selectedRows[-1].row()
        minSourceRow = self.watchListTableProxyModel.mapToSource(selectedRows[0]).row()
        maxSourceRow = self.watchListTableProxyModel.mapToSource(selectedRows[-1]).row()

        if ((moveTo == self.MoveTo.UP or moveTo == self.MoveTo.TOP) and minSourceRow == 0) or \
           (moveTo == self.MoveTo.DOWN and maxSourceRow >= (self.watchListTableModel.getDataSize() - 1)):
            return

        self.watchListTableView.selectionModel().clearSelection()

        dstRow = 0
        topRow = 0
        bottomRow = 0
        if moveTo == self.MoveTo.UP:
            dstRow = minSourceRow - 1
            topRow = minProxyRow - 1
            bottomRow = maxProxyRow - 1
        elif moveTo == self.MoveTo.DOWN:
            dstRow = minSourceRow + 1
            topRow = minProxyRow + 1
            bottomRow = maxProxyRow + 1
        elif moveTo == self.MoveTo.TOP:
            dstRow = 0
            topRow = 0
            bottomRow = maxProxyRow - minProxyRow

        self.watchListTableModel.moveRow(minSourceRow, maxSourceRow, dstRow)
        topLeft = self.watchListTableProxyModel.index(topRow, 0)
        lastColumn = self.moviesTableModel.getLastColumn()
        bottomRight = self.watchListTableProxyModel.index(bottomRow, lastColumn)

        selection = self.watchListTableView.selectionModel().selection()
        selection.select(topLeft, bottomRight)
        self.watchListTableView.selectionModel().select(selection,
                                                        QtCore.QItemSelectionModel.ClearAndSelect)

        self.writeSmdbFile(self.watchListSmdbFile,
                           self.watchListTableModel,
                           titlesOnly=True)

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
        if os.path.exists(moviePath):
            runFile(moviePath)
        else:
            print("Folder doesn't exist")

    def openMovieJson(self):
        sourceRow = self.getSelectedRow()
        moviePath = self.moviesTableModel.getPath(sourceRow)
        folderName = self.moviesTableModel.getFolderName(sourceRow)
        jsonFile = os.path.join(moviePath, '%s.json' % folderName)
        if os.path.exists(jsonFile):
            runFile(jsonFile)
        else:
            print("jsonFile: %s doesn't exist" % jsonFile)

    def openMovieImdbPage(self):
        sourceRow = self.getSelectedRow()
        movieId = self.moviesTableModel.getId(sourceRow)
        if 'http://' in movieId or 'https://' in movieId:
            webbrowser.open(movieId, new=2)
        else:
            webbrowser.open('http://imdb.com/title/tt%s' % movieId, new=2)

    def downloadSubtitles(self):
        sourceRow = self.getSelectedRow()
        movieId = self.moviesTableModel.getId(sourceRow)
        webbrowser.open(f'https://yifysubtitles.org/movie-imdb/tt{movieId}')

    def searchForOtherVersions(self):
        response = QtWidgets.QMessageBox.question(
            self,
            "WARNING!!",
            "Do not proceed unless connected to a VPN.  Proceed?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)

        if response == QtWidgets.QMessageBox.No:
            return

        sourceRow = self.getSelectedRow()
        title = self.moviesTableModel.getTitle(sourceRow)
        titlePlus = '+'.join(title.split())
        titleMinus = '-'.join(title.split())
        year = self.moviesTableModel.getYear(sourceRow)
        urlPirateBay = f"https://thepiratebay.org/search.php?q={titlePlus}+%28{year}%29&all=on&search=Pirate+Search&page=0&orderby="
        url1337x = f"https://1337x.to/search/{titlePlus}+{year}/1/"
        urlRarBG = f"http://rarbg.to/torrents.php?search={titlePlus}+%28{year}%29"
        usrlLimeTorrents = f"https://www.limetorrents.info/search/all/{titleMinus}-%20{year}%20/"
        urlYts = f"https://yts.mx/movies/{titleMinus.lower()}-{year}"
        urls = [urlPirateBay, url1337x, urlRarBG, usrlLimeTorrents, urlYts]
        for u in urls:
            webbrowser.open(u, new=2)

    def overrideID(self):
        movieId, ok = QtWidgets.QInputDialog.getText(self,
                                                     "Override ID",
                                                     "Enter new ID",
                                                     QtWidgets.QLineEdit.Normal,
                                                     "")
        if movieId and ok:
            if 'tt' in movieId:
                movieId = movieId.replace('tt', '')
            modelIndex = self.moviesTableView.selectionModel().selectedRows()[0]
            self.downloadMovieData(modelIndex, True, movieId)

    def downloadDataMenu(self, force=False, doJson=True, doCover=True):
        numSelectedItems = len(self.moviesTableView.selectionModel().selectedRows())
        self.progressBar.setMaximum(numSelectedItems)
        progress = 0
        self.isCanceled = False
        for proxyIndex in self.moviesTableView.selectionModel().selectedRows():
            QtCore.QCoreApplication.processEvents()
            if self.isCanceled:
                self.statusBar().showMessage('Cancelled')
                self.isCanceled = False
                self.progressBar.setValue(0)
                return

            progress += 1
            self.progressBar.setValue(progress)

            sourceRow = self.getSourceRow(proxyIndex)
            title = self.moviesTableModel.getTitle(sourceRow)
            message = "Downloading data (%d/%d): %s" % (progress + 1,
                                                        numSelectedItems,
                                                        title)
            self.statusBar().showMessage(message)
            QtCore.QCoreApplication.processEvents()

            movieFolderName = self.moviesTableModel.getFolderName(sourceRow)
            moviePath = self.moviesTableModel.getPath(sourceRow)
            if not os.path.exists(moviePath):
                continue

            self.downloadMovieData(proxyIndex, force, doJson=doJson, doCover=doCover)
            self.moviesTableView.selectRow(proxyIndex.row())
            self.clickedTable(proxyIndex,
                              self.moviesTableModel,
                              self.moviesTableProxyModel)

        self.progressBar.setValue(0)

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