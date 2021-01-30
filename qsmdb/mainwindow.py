from PyQt5 import QtGui, QtWidgets
from enum import Enum
from pathlib import Path
import imdb
from imdb import IMDb
import json
import collections
import webbrowser
import shutil
import os
import stat
import time
from pymediainfo import MediaInfo

from .utilities import *
from .moviemodel import MoviesTableModel

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


def toggleColumn(c, tableView, visibleList):
    visibleList[c.value] = not visibleList[c.value]
    if visibleList[c.value]:
        tableView.showColumn(c.value)
    else:
        tableView.hideColumn(c.value)


def showAllColumns(tableView, visibleList):
    for i, c in enumerate(visibleList):
        visibleList[i] = True
        tableView.showColumn(i)


def hideAllColumns(tableView, visibleList):
    for i, c in enumerate(visibleList):
        if i != 0:  # leave the first column visible
            visibleList[i] = False
            tableView.hideColumn(i)


def openYearImdbPage(year):
    webbrowser.open('https://www.imdb.com/search/title/?release_date=%s-01-01,%s-12-31' % (year, year), new=2)


def headerRightMenuShow(QPos, tableView, visibleColumnsList, model):
    menu = QtWidgets.QMenu(tableView.horizontalHeader())

    showAllAction = QtWidgets.QAction("Show All")
    showAllAction.triggered.connect(lambda a,
                                    tv=tableView,
                                    vcl=visibleColumnsList:
                                    showAllColumns(tv, vcl))
    menu.addAction(showAllAction)

    hideAllAction = QtWidgets.QAction("Hide All")
    hideAllAction.triggered.connect(lambda a,
                                    tv=tableView,
                                    vcl=visibleColumnsList:
                                    hideAllColumns(tv, vcl))
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
                                 toggleColumn(column, tv, vcl))
        menu.addAction(action)
        actionsList.append(action)

    menu.exec_(QtGui.QCursor.pos())


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


class MovieInfoListview(QtWidgets.QListWidget):
    def __init__(self):
        super(MovieInfoListview, self).__init__()
        self.mouseLocation = 0

    def mousePressEvent(self, event):
        if event.type() == QtCore.QEvent.MouseButtonPress:
            if event.button() == QtCore.Qt.RightButton:
                self.mouseLocation = event.pos()
                return
            else:
                super(MovieInfoListview, self).mousePressEvent(event)


def getFolderSize(startPath='.'):
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(startPath):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            # skip if it is symbolic link
            if not os.path.islink(fp):
                total_size += os.path.getsize(fp)

    return total_size


class MyWindow(QtWidgets.QMainWindow):
    def __init__(self):
        print("running init")
        super(MyWindow, self).__init__()

        self.numVisibleMovies = 0

        # Create IMDB database
        self.db = IMDb()

        # Read the movies folder from the settings
        self.settings = QtCore.QSettings("STC", "SMDB")
        self.moviesFolder = self.settings.value('movies_folder', "J:/Movies", type=str)
        self.backupFolder = ""

        self.additionalMoviesFolders = self.settings.value('additional_movies_folders', [], type=list)
        for af in self.additionalMoviesFolders:
            print("Additional movies folder = %s" % af)

        # Init UI
        self.setTitleBar()
        self.setGeometry(300, 150, 1300, 700)

        # Set foreground/background colors for item views
        self.setStyleSheet("""QAbstractItemView{ background: black; color: white; }; """)

        # Default view state of UI sections
        self.showFilters = True
        self.showMoviesTable = True
        self.showCover = True
        self.showMovieInfo = True
        self.showMovieSection = True
        self.showSummary = True
        self.showWatchList = True
        self.showBackupList = False

        # Default state of cancel button
        self.isCanceled = False

        # Main Menus
        self.initUIFileMenu()
        self.initUIViewMenu()

        # Add the central widget
        centralWidget = QtWidgets.QWidget()
        centralWidget.setStyleSheet("background: rgb(50, 50, 50); color: white;")
        self.setCentralWidget(centralWidget)

        # Divides top h splitter and bottom progress bar
        mainVLayout = QtWidgets.QVBoxLayout(self)
        centralWidget.setLayout(mainVLayout)

        # Main H Splitter for criteria, movies list, and cover/info
        mainHSplitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal, self)
        mainHSplitter.setHandleWidth(10)
        mainVLayout.addWidget(mainHSplitter)

        # Filter Table
        self.filterByDict = {
            'Director': 'directors',
            'Actor': 'actors',
            'Genre': 'genres',
            'Mpaa Rating': 'mpaa ratings',
            'User Tags': 'user tags',
            'Year': 'years',
            'Companies': 'companies',
            'Country': 'countries'
        }
        self.filterWidget = QtWidgets.QFrame()
        self.filterByComboBox = QtWidgets.QComboBox()
        self.filterMinCountCheckbox = QtWidgets.QCheckBox()
        self.filterMinCountSpinBox = QtWidgets.QSpinBox()
        self.filterTable = FilterTable()
        self.initUIFilterTable()
        if not self.showFilters:
            self.filterWidget.hide()

        # Splitter for Movies Table and Watch List
        moviesWatchListBackupVSplitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        moviesWatchListBackupVSplitter.setHandleWidth(20)

        # Movies Table
        self.moviesTableWidget = QtWidgets.QFrame()
        self.moviesTableView = QtWidgets.QTableView()
        self.moviesTableSearchBox = QtWidgets.QLineEdit()
        self.moviesTableColumnsVisible = []
        self.moviesListHeaderActions = []
        self.initUIMoviesTable()
        moviesWatchListBackupVSplitter.addWidget(self.moviesTableWidget)
        if not self.showMoviesTable:
            self.moviesTableWidget.hide()

        # Watch List
        self.watchListWidget = QtWidgets.QFrame()
        self.watchListTableView = QtWidgets.QTableView()
        self.watchListColumnsVisible = []
        self.watchListHeaderActions = []
        self.initUIWatchList()
        moviesWatchListBackupVSplitter.addWidget(self.watchListWidget)
        if not self.showWatchList:
            self.watchListWidget.hide()

        # Backup List
        self.backupAnalysed = False
        self.backupListWidget = QtWidgets.QFrame()
        self.backupListTableView = QtWidgets.QTableView()
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
        self.backupFolder = ''
        self.initUIBackupList()
        moviesWatchListBackupVSplitter.addWidget(self.backupListWidget)
        if not self.showBackupList:
            self.backupListWidget.hide()

        moviesWatchListBackupVSplitter.setSizes([500, 200, 200])

        # Movie section widget
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
        self.titleLabel.setFont(QtGui.QFont('TimesNew Roman', 20))
        self.titleLabel.setStyleSheet("color: white; background: black")
        self.titleLabel.setWordWrap(True)
        self.titleLabel.setAlignment(QtCore.Qt.AlignHCenter | QtCore.Qt.AlignTop)
        self.titleLabel.setSizePolicy(QtWidgets.QSizePolicy.MinimumExpanding, QtWidgets.QSizePolicy.Fixed)
        movieSectionVLayout.addWidget(self.titleLabel)

        # Cover and Summary V Splitter
        coverSummaryVSplitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        movieSectionVLayout.addWidget(coverSummaryVSplitter)
        coverSummaryVSplitter.setHandleWidth(20)
        coverSummaryVSplitter.splitterMoved.connect(self.resizeCoverFile)

        # Cover and Movie Info H Splitter
        coverInfoHSplitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)

        coverSummaryVSplitter.addWidget(coverInfoHSplitter)

        # Movie Info
        self.movieInfoWidget = QtWidgets.QWidget()
        coverInfoHSplitter.addWidget(self.movieInfoWidget)
        coverInfoHSplitter.splitterMoved.connect(self.resizeCoverFile)
        movieInfoVLayout = QtWidgets.QVBoxLayout()
        self.movieInfoWidget.setLayout(movieInfoVLayout)
        self.movieInfoListView = MovieInfoListview()
        self.movieInfoListView.setStyleSheet("background: black")
        self.movieInfoListView.itemSelectionChanged.connect(self.movieInfoSelectionChanged)
        self.movieInfoListView.setFont(QtGui.QFont('TimesNew Roman', 10))
        self.movieInfoListView.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.movieInfoListView.customContextMenuRequested[QtCore.QPoint].connect(self.movieInfoRightMenu)
        movieInfoVLayout.addWidget(self.movieInfoListView)
        if not self.showMovieInfo:
            self.movieInfoWidget.hide()

        # Cover
        self.coverWidget = QtWidgets.QWidget()
        self.movieCover = QtWidgets.QLabel()
        self.initUICover()
        coverInfoHSplitter.addWidget(self.coverWidget)
        if not self.showCover:
            self.coverWidget.hide()

        coverInfoHSplitter.setSizes([250, 450])

        # Summary
        self.summary = QtWidgets.QTextBrowser()
        self.summary.setFont(QtGui.QFont('TimesNew Roman', 12))
        self.summary.setStyleSheet("color:white; background-color: black;")
        coverSummaryVSplitter.addWidget(self.summary)
        coverSummaryVSplitter.setSizes([600, 200])
        if not self.showSummary:
            self.summary.hide()

        # Add the sub-layouts to the mainHSplitter
        mainHSplitter.addWidget(self.filterWidget)
        mainHSplitter.addWidget(moviesWatchListBackupVSplitter)
        mainHSplitter.addWidget(self.movieSectionWidget)
        mainHSplitter.splitterMoved.connect(self.resizeCoverFile)
        mainHSplitter.setSizes([270, 430, 600])

        # Bottom
        bottomLayout = QtWidgets.QHBoxLayout(self)
        mainVLayout.addLayout(bottomLayout)
        self.progressBar = QtWidgets.QProgressBar()
        self.progressBar.setStyleSheet("background: rgb(0, 0, 0); color: white; border-radius: 5px")
        self.progressBar.setFont(QtGui.QFont('TimesNew Roman', 12))
        self.progressBar.setMaximum(100)
        bottomLayout.addWidget(self.progressBar)
        cancelButton = QtWidgets.QPushButton("Cancel", self)
        cancelButton.clicked.connect(self.cancelButtonClicked)
        cancelButton.setStyleSheet("background: rgb(100, 100, 100); color: white; border-radius: 5px")
        cancelButton.setFixedSize(100, 25)
        cancelButton.setFont(QtGui.QFont('TimesNew Roman', 12))
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

        self.populateFiltersTable()

        self.watchListSmdbFile = os.path.join(self.moviesFolder, "smdb_data_watch_list.json")
        self.watchListSmdbData = None
        self.watchListTableModel = None
        self.watchListTableProxyModel = None
        self.refreshWatchList()

        self.backupListSmdbFile = os.path.join(self.moviesFolder, "smdb_data_backup_list.json")
        self.backupListSmdbData = None
        self.backupListTableModel = None
        self.backupListTableProxyModel = None
        self.refreshBackupList()

        self.showMoviesTableSelectionStatus()

    def initUIFileMenu(self):
        menuBar = self.menuBar()
        fileMenu = menuBar.addMenu('File')

        rebuildSmdbFileAction = QtWidgets.QAction("Rebuild SMDB file", self)
        rebuildSmdbFileAction.triggered.connect(lambda: self.writeSmdbFile(self.moviesSmdbFile,
                                                                           self.moviesTableModel))
        fileMenu.addAction(rebuildSmdbFileAction)

        setMovieFolderAction = QtWidgets.QAction("Set movies folder", self)
        setMovieFolderAction.triggered.connect(self.browseMoviesFolder)
        fileMenu.addAction(setMovieFolderAction)

        addAdditionalMoviesFolderAction = QtWidgets.QAction("Add additional movies folder", self)
        addAdditionalMoviesFolderAction.triggered.connect(self.browseAdditionalMoviesFolder)
        fileMenu.addAction(addAdditionalMoviesFolderAction)

        clearAdditionalMoviesFolderAction = QtWidgets.QAction("Clear additional movies folders", self)
        clearAdditionalMoviesFolderAction.triggered.connect(self.clearAdditionalMoviesFolders)
        fileMenu.addAction(clearAdditionalMoviesFolderAction)

        refreshAction = QtWidgets.QAction("Refresh movies dir", self)
        refreshAction.triggered.connect(lambda: self.refreshMoviesList(forceScan=True))
        fileMenu.addAction(refreshAction)

        preferencesAction = QtWidgets.QAction("Preferences", self)
        preferencesAction.triggered.connect(self.preferences)
        fileMenu.addAction(preferencesAction)

        quitAction = QtWidgets.QAction("Quit", self)
        quitAction.triggered.connect(QtCore.QCoreApplication.quit)
        fileMenu.addAction(quitAction)

    def initUIViewMenu(self):
        menuBar = self.menuBar()
        viewMenu = menuBar.addMenu('View')

        showFiltersAction = QtWidgets.QAction("Show Filters", self)
        showFiltersAction.setCheckable(True)
        showFiltersAction.setChecked(self.showFilters)
        showFiltersAction.triggered.connect(self.showFiltersMenu)
        viewMenu.addAction(showFiltersAction)

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

    def initUIFilterTable(self):
        self.filterWidget.setFrameShape(QtWidgets.QFrame.Panel | QtWidgets.QFrame.Sunken)
        self.filterWidget.setLineWidth(5)
        self.filterWidget.setStyleSheet("background: rgb(25, 25, 25); color: white; border-radius: 10px")

        filtersVLayout = QtWidgets.QVBoxLayout()
        self.filterWidget.setLayout(filtersVLayout)

        filterByHLayout = QtWidgets.QHBoxLayout()
        self.filterWidget.layout().addLayout(filterByHLayout)

        filterByLabel = QtWidgets.QLabel("Filter By")
        filterByLabel.setFont(QtGui.QFont('TimesNew Roman', 12))
        filterByLabel.setSizePolicy(QtWidgets.QSizePolicy.Maximum,
                                    QtWidgets.QSizePolicy.Maximum)
        filterByHLayout.addWidget(filterByLabel)

        self.filterByComboBox.setStyleSheet("background: rgb(50, 50, 50); color: white; border-radius: 5px")
        self.filterByComboBox.setFont(QtGui.QFont('TimesNewY Roman', 12))
        for i in self.filterByDict.keys():
            self.filterByComboBox.addItem(i)
        self.filterByComboBox.setCurrentIndex(0)
        self.filterByComboBox.activated.connect(self.populateFiltersTable)
        filterByHLayout.addWidget(self.filterByComboBox)

        minCountHLayout = QtWidgets.QHBoxLayout()
        self.filterWidget.layout().addLayout(minCountHLayout)
        self.filterMinCountCheckbox.setText("Enable Min Count")
        self.filterMinCountCheckbox.setFont(QtGui.QFont('TimesNewY Roman', 12))
        self.filterMinCountCheckbox.setChecked(True)
        minCountHLayout.addWidget(self.filterMinCountCheckbox)

        self.filterMinCountSpinBox.setMinimum(0)
        self.filterMinCountSpinBox.setValue(2)
        self.filterMinCountSpinBox.setFont(QtGui.QFont('TimesNewY Roman', 12))
        self.filterMinCountSpinBox.setStyleSheet("background: black; color: white; border-radius: 5px")
        self.filterMinCountSpinBox.valueChanged.connect(self.populateFiltersTable)
        minCountHLayout.addWidget(self.filterMinCountSpinBox)

        self.filterMinCountCheckbox.stateChanged.connect(self.filterMinCountSpinBox.setEnabled)
        self.filterMinCountCheckbox.stateChanged.connect(self.populateFiltersTable)

        self.filterTable.setColumnCount(2)
        self.filterTable.verticalHeader().hide()
        self.filterTable.setHorizontalHeaderLabels(['Name', 'Count'])
        self.filterTable.setColumnWidth(0, 170)
        self.filterTable.setColumnWidth(1, 60)
        self.filterTable.verticalHeader().setMinimumSectionSize(10)
        self.filterTable.verticalHeader().setDefaultSectionSize(18)
        self.filterTable.setWordWrap(False)
        self.filterTable.setStyleSheet("background: black; alternate-background-color: #151515; color: white")
        self.filterTable.setAlternatingRowColors(True)
        self.filterTable.itemSelectionChanged.connect(self.filterTableSelectionChanged)
        hh = self.filterTable.horizontalHeader()
        hh.setStyleSheet("background: #303030; color: white")
        filtersVLayout.addWidget(self.filterTable)

        filtersSearchHLayout = QtWidgets.QHBoxLayout()
        filtersVLayout.addLayout(filtersSearchHLayout)

        searchText = QtWidgets.QLabel("Search")
        searchText.setFont(QtGui.QFont('TimesNew Roman', 12))
        searchText.setSizePolicy(QtWidgets.QSizePolicy.Maximum,
                                 QtWidgets.QSizePolicy.Maximum)
        filtersSearchHLayout.addWidget(searchText)

        filterTableSearchBox = QtWidgets.QLineEdit(self)
        filterTableSearchBox.setStyleSheet("background: black; color: white; border-radius: 5px")
        filterTableSearchBox.setFont(QtGui.QFont('TimesNew Roman', 12))
        filterTableSearchBox.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Maximum)
        filterTableSearchBox.setClearButtonEnabled(True)
        filtersSearchHLayout.addWidget(filterTableSearchBox)
        filterTableSearchBox.textChanged.connect(lambda: searchTableWidget(filterTableSearchBox, self.filterTable))

    def initUIMoviesTable(self):
        self.moviesTableWidget.setFrameShape(QtWidgets.QFrame.Panel | QtWidgets.QFrame.Sunken)
        self.moviesTableWidget.setLineWidth(5)
        self.moviesTableWidget.setStyleSheet("background: rgb(25, 25, 25); color: white;  border-radius: 10px")
        self.moviesTableView.horizontalHeader().setStyleSheet("color: black")

        moviesTableViewVLayout = QtWidgets.QVBoxLayout()
        self.moviesTableWidget.setLayout(moviesTableViewVLayout)

        moviesLabel = QtWidgets.QLabel("Movies")
        moviesLabel.setFont(QtGui.QFont('TimesNew Roman', 12))
        moviesTableViewVLayout.addWidget(moviesLabel)

        self.moviesTableView.setSortingEnabled(True)
        self.moviesTableView.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.moviesTableView.verticalHeader().hide()
        self.moviesTableView.setStyleSheet("background: black; alternate-background-color: #151515; color: white")
        self.moviesTableView.setAlternatingRowColors(True)
        self.moviesTableView.horizontalHeader().setSectionsMovable(True)
        self.moviesTableView.setShowGrid(False)

        # Right click header menu
        hh = self.moviesTableView.horizontalHeader()
        hh.setStyleSheet("background: #303030; color: white")
        hh.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        hh.customContextMenuRequested[QtCore.QPoint].connect(
            lambda: headerRightMenuShow(QtCore.QPoint,
                                        self.moviesTableView,
                                        self.moviesTableColumnsVisible,
                                        self.moviesTableModel))

        # Right click menu
        self.moviesTableView.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.moviesTableView.customContextMenuRequested[QtCore.QPoint].connect(self.moviesTableRightMenuShow)
        moviesTableViewVLayout.addWidget(self.moviesTableView)

        moviesTableSearchHLayout = QtWidgets.QHBoxLayout()
        moviesTableViewVLayout.addLayout(moviesTableSearchHLayout)

        # Show all button
        showAllButton = QtWidgets.QPushButton("Show All")
        showAllButton.setFixedSize(100, 20)
        showAllButton.setSizePolicy(QtWidgets.QSizePolicy.Fixed,
                                    QtWidgets.QSizePolicy.Maximum)
        showAllButton.clicked.connect(self.showAllMoviesTableView)
        showAllButton.setFont(QtGui.QFont('TimesNew Roman', 12))
        showAllButton.setStyleSheet("background: rgb(50, 50, 50); color: white; border-radius: 5px")
        moviesTableSearchHLayout.addWidget(showAllButton)

        # Search box
        searchText = QtWidgets.QLabel("Search")
        searchText.setFont(QtGui.QFont('TimesNew Roman', 12))
        searchText.setSizePolicy(QtWidgets.QSizePolicy.Maximum,
                                 QtWidgets.QSizePolicy.Maximum)
        moviesTableSearchHLayout.addWidget(searchText)

        self.moviesTableSearchBox.setStyleSheet("background: black; color: white; border-radius: 5px")
        self.moviesTableSearchBox.setFont(QtGui.QFont('TimesNew Roman', 12))
        self.moviesTableSearchBox.setSizePolicy(QtWidgets.QSizePolicy.Ignored,
                                                QtWidgets.QSizePolicy.Maximum)
        self.moviesTableSearchBox.setClearButtonEnabled(True)
        self.moviesTableSearchBox.textChanged.connect(self.searchMoviesTableView)
        moviesTableSearchHLayout.addWidget(self.moviesTableSearchBox)

    def initUIWatchList(self):
        self.watchListWidget.setFrameShape(QtWidgets.QFrame.Panel | QtWidgets.QFrame.Sunken)
        self.watchListWidget.setLineWidth(5)
        self.watchListWidget.setStyleSheet("background: rgb(25, 25, 25); color: white; border-radius: 10px")

        watchListVLayout = QtWidgets.QVBoxLayout()
        self.watchListWidget.setLayout(watchListVLayout)

        watchListLabel = QtWidgets.QLabel("Watch List")
        watchListLabel.setFont(QtGui.QFont('TimesNew Roman', 12))
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
            lambda: headerRightMenuShow(QtCore.QPoint,
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
        addButton.setFont(QtGui.QFont('TimesNew Roman', 12))
        addButton.setStyleSheet("background: rgb(50, 50, 50); color: white; border-radius: 5px")
        watchListButtonsHLayout.addWidget(addButton)

        removeButton = QtWidgets.QPushButton('Remove')
        removeButton.clicked.connect(self.watchListRemove)
        removeButton.setFont(QtGui.QFont('TimesNew Roman', 12))
        removeButton.setStyleSheet("background: rgb(50, 50, 50); color: white; border-radius: 5px")
        watchListButtonsHLayout.addWidget(removeButton)

        moveToTopButton = QtWidgets.QPushButton('Move To Top')
        moveToTopButton.clicked.connect(lambda: self.watchListMoveRow(self.MoveTo.TOP))
        moveToTopButton.setFont(QtGui.QFont('TimesNew Roman', 12))
        moveToTopButton.setStyleSheet("background: rgb(50, 50, 50); color: white; border-radius: 5px")
        watchListButtonsHLayout.addWidget(moveToTopButton)

        moveUpButton = QtWidgets.QPushButton('Move Up')
        moveUpButton.clicked.connect(lambda: self.watchListMoveRow(self.MoveTo.UP))
        moveUpButton.setFont(QtGui.QFont('TimesNew Roman', 12))
        moveUpButton.setStyleSheet("background: rgb(50, 50, 50); color: white; border-radius: 5px")
        watchListButtonsHLayout.addWidget(moveUpButton)

        moveDownButton = QtWidgets.QPushButton('Move Down')
        moveDownButton.clicked.connect(lambda: self.watchListMoveRow(self.MoveTo.DOWN))
        moveDownButton.setFont(QtGui.QFont('TimesNew Roman', 12))
        moveDownButton.setStyleSheet("background: rgb(50, 50, 50); color: white; border-radius: 5px")
        watchListButtonsHLayout.addWidget(moveDownButton)

    def initUIBackupList(self):
        self.backupListWidget.setFrameShape(QtWidgets.QFrame.Panel | QtWidgets.QFrame.Sunken)
        self.backupListWidget.setLineWidth(5)
        self.backupListWidget.setStyleSheet("background: rgb(25, 25, 25); color: white; border-radius: 10px")

        backupListVLayout = QtWidgets.QVBoxLayout()
        self.backupListWidget.setLayout(backupListVLayout)

        backupListLabel = QtWidgets.QLabel("Backup List")
        backupListLabel.setFont(QtGui.QFont('TimesNew Roman', 12))
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
            lambda: headerRightMenuShow(QtCore.QPoint,
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
        addButton.setFont(QtGui.QFont('TimesNew Roman', 12))
        addButton.setStyleSheet("background: rgb(50, 50, 50);"
                                "color: white;"
                                "border-radius: 5px")
        addButton.clicked.connect(self.backupListAdd)
        backupListButtonsHLayout.addWidget(addButton)

        removeButton = QtWidgets.QPushButton('Remove')
        removeButton.setFont(QtGui.QFont('TimesNew Roman', 12))
        removeButton.setStyleSheet("background: rgb(50, 50, 50); color: white;"
                                   "border-radius: 5px")
        removeButton.clicked.connect(self.backupListRemove)
        backupListButtonsHLayout.addWidget(removeButton)

        removeNoDifferenceButton = QtWidgets.QPushButton('Remove Folders With No Difference')
        removeNoDifferenceButton.setFixedSize(300, 20)
        removeNoDifferenceButton.setFont(QtGui.QFont('TimesNew Roman', 12))
        removeNoDifferenceButton.setStyleSheet("background: rgb(50, 50, 50);"
                                               "color: white; border-radius: 5px")
        removeNoDifferenceButton.clicked.connect(self.backupListRemoveNoDifference)
        backupListButtonsHLayout.addWidget(removeNoDifferenceButton)

        analyseButton = QtWidgets.QPushButton("Analyse")
        analyseButton.setFont(QtGui.QFont('TimesNew Roman', 12))
        analyseButton.setStyleSheet("background: rgb(50, 50, 50);"
                                    "color: white;"
                                    "border-radius: 5px")
        analyseButton.clicked.connect(self.backupAnalyse)
        backupListButtonsHLayout.addWidget(analyseButton)

        backupButton = QtWidgets.QPushButton("Backup")
        backupButton.setStyleSheet("background: rgb(50, 50, 50);"
                                   "color: white;"
                                   "border-radius: 5px")
        backupButton.setFont(QtGui.QFont('TimesNew Roman', 12))
        backupButton.clicked.connect(self.backupRun)
        backupListButtonsHLayout.addWidget(backupButton)

        backupFolderHLayout = QtWidgets.QHBoxLayout()
        backupListVLayout.addLayout(backupFolderHLayout)

        backupFolderLabel = QtWidgets.QLabel("Destination Folder")
        backupFolderLabel.setFont(QtGui.QFont('TimesNew Roman', 12))
        backupFolderHLayout.addWidget(backupFolderLabel)

        self.backupFolderEdit.setStyleSheet("background: black; color: white; border-radius: 5px")
        self.backupFolderEdit.setFont(QtGui.QFont('TimesNew Roman', 12))
        self.backupFolderEdit.setReadOnly(True)
        backupFolderHLayout.addWidget(self.backupFolderEdit)

        browseButton = QtWidgets.QPushButton("Browse")
        browseButton.setFont(QtGui.QFont('TimesNew Roman', 12))
        browseButton.setStyleSheet("background: rgb(50, 50, 50);"
                                   "color: white;"
                                   "border-radius: 5px")
        browseButton.clicked.connect(self.backupBrowseFolder)
        browseButton.setFixedSize(80, 20)
        backupFolderHLayout.addWidget(browseButton)

        self.spaceAvailableLabel.setAlignment(QtCore.Qt.AlignRight)
        self.spaceAvailableLabel.setFont(QtGui.QFont('TimesNew Roman', 12))
        backupFolderHLayout.addWidget(self.spaceAvailableLabel)

        backupSpaceLayout = QtWidgets.QHBoxLayout()
        backupListVLayout.addLayout(backupSpaceLayout)

        spaceLabel = QtWidgets.QLabel("Disk Space")
        spaceLabel.setFont(QtGui.QFont('TimesNew Roman', 12))
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
        self.coverWidget.setStyleSheet("background-color: black;")
        movieVLayout = QtWidgets.QVBoxLayout()
        self.coverWidget.setLayout(movieVLayout)
        self.movieCover.setScaledContents(False)
        self.movieCover.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Ignored)
        self.movieCover.setStyleSheet("background-color: black;")
        movieVLayout.addWidget(self.movieCover)

    def refreshMoviesList(self, forceScan=False):
        moviesFolders = [self.moviesFolder]
        moviesFolders += self.additionalMoviesFolders
        if os.path.exists(self.moviesSmdbFile):
            self.moviesSmdbData = readSmdbFile(self.moviesSmdbFile)
            self.moviesTableModel = MoviesTableModel(self.moviesSmdbData,
                                                     moviesFolders,
                                                     forceScan)
        else:
            self.moviesTableModel = MoviesTableModel(self.moviesSmdbData,
                                                     moviesFolders,
                                                     True)  # Force scan if no smdb file
            # Generate smdb data from movies table model and write
            # out smdb file
            self.moviesSmdbData = self.writeSmdbFile(self.moviesSmdbFile,
                                                     self.moviesTableModel)

        self.moviesTableProxyModel = QtCore.QSortFilterProxyModel()
        self.moviesTableProxyModel.setSourceModel(self.moviesTableModel)

        tableView = self.moviesTableView
        tableModel = self.moviesTableModel
        proxyModel = self.moviesTableProxyModel

        # If forScan, sort by exists otherwise year
        if forceScan:
            proxyModel.sort(tableModel.Columns.JsonExists.value)
        else:
            proxyModel.sort(tableModel.Columns.Year.value)

        tableView.setModel(proxyModel)

        try:
            tableView.doubleClicked.disconnect()
        except Exception:
            pass

        tableView.selectionModel().selectionChanged.connect(lambda: self.tableSelectionChanged(tableView, tableModel, proxyModel))
        tableView.doubleClicked.connect(lambda: self.playMovie(tableView, proxyModel))

        # Don't sort the table when the data changes
        proxyModel.setDynamicSortFilter(False)

        tableView.setWordWrap(False)

        # Set the column widths
        self.moviesTableColumnsVisible = []
        for col in tableModel.Columns:
            tableView.setColumnWidth(col.value, tableModel.defaultWidths[col])
            self.moviesTableColumnsVisible.append(True)

        columnsToShow = [tableModel.Columns.Year,
                         tableModel.Columns.Title,
                         tableModel.Columns.Rating]

        for c in tableModel.Columns:
            index = c.value
            if c not in columnsToShow:
                tableView.hideColumn(index)
                self.moviesTableColumnsVisible[index] = False

        # Make the row height smaller
        tableView.verticalHeader().setMinimumSectionSize(10)
        tableView.verticalHeader().setDefaultSectionSize(18)

        self.numVisibleMovies = proxyModel.rowCount()
        self.showMoviesTableSelectionStatus()

        tableView.selectRow(0)
        self.tableSelectionChanged(tableView, tableModel, proxyModel)

    def refreshWatchList(self):
        if os.path.exists(self.watchListSmdbFile):
            self.watchListSmdbData = readSmdbFile(self.watchListSmdbFile)
        self.watchListTableModel = MoviesTableModel(self.watchListSmdbData,
                                                    [self.moviesFolder],
                                                    False,  # force scan
                                                    True)  # don't scan the movies folder for the watch list
        self.watchListTableProxyModel = QtCore.QSortFilterProxyModel()
        self.watchListTableProxyModel.setSourceModel(self.watchListTableModel)

        tableView = self.watchListTableView
        tableModel = self.watchListTableModel
        proxyModel = self.watchListTableProxyModel

        # Sort the watch list by rankl
        proxyModel.sort(tableModel.Columns.Rank.value)

        tableView.setModel(proxyModel)
        tableView.selectionModel().selectionChanged.connect(lambda: self.tableSelectionChanged(tableView, tableModel, proxyModel))
        tableView.doubleClicked.connect(lambda: self.playMovie(tableView, proxyModel))
        proxyModel.setDynamicSortFilter(False)
        tableView.setWordWrap(False)

        self.watchListColumnsVisible = []
        for col in tableModel.Columns:
            tableView.setColumnWidth(col.value, tableModel.defaultWidths[col])
            self.watchListColumnsVisible.append(True)

        columnsToShow = [tableModel.Columns.Rank,
                         tableModel.Columns.Year,
                         tableModel.Columns.Title,
                         tableModel.Columns.Rating]

        for c in tableModel.Columns:
            index = c.value
            if c not in columnsToShow:
                tableView.hideColumn(index)
                self.moviesTableColumnsVisible[index] = False

        # Set rank as the first column
        tableView.horizontalHeader().moveSection(tableModel.Columns.Rank.value, 0)

        tableView.verticalHeader().setMinimumSectionSize(10)
        tableView.verticalHeader().setDefaultSectionSize(18)

    def refreshBackupList(self):
        self.backupListTableModel = MoviesTableModel(None,
                                                    [self.moviesFolder],
                                                    False,  # force scan
                                                    True)  # don't scan the movies folder for the watch list
        self.backupListTableProxyModel = QtCore.QSortFilterProxyModel()
        self.backupListTableProxyModel.setSourceModel(self.backupListTableModel)

        tableView = self.backupListTableView
        tableModel = self.backupListTableModel
        proxyModel = self.backupListTableProxyModel

        # Sort the watch list by rankl
        proxyModel.sort(tableModel.Columns.Rank.value)

        tableView.setModel(proxyModel)
        tableView.selectionModel().selectionChanged.connect(lambda: self.tableSelectionChanged(tableView, tableModel, proxyModel))
        tableView.doubleClicked.connect(lambda: self.playMovie(tableView, proxyModel))
        proxyModel.setDynamicSortFilter(False)
        tableView.setWordWrap(False)

        self.backupListColumnsVisible = []
        for col in tableModel.Columns:
            tableView.setColumnWidth(col.value, tableModel.defaultWidths[col])
            self.backupListColumnsVisible.append(True)

        columnsToShow = [tableModel.Columns.Title,
                         tableModel.Columns.Path,
                         tableModel.Columns.BackupStatus,
                         tableModel.Columns.Size]

        for c in tableModel.Columns:
            index = c.value
            if c not in columnsToShow:
                tableView.hideColumn(index)
                self.moviesTableColumnsVisible[index] = False

        tableView.verticalHeader().setMinimumSectionSize(10)
        tableView.verticalHeader().setDefaultSectionSize(18)

    def backupMoviesFolder(self):
        pass

    def preferences(self):
        pass

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

    def browseMoviesFolder(self):
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
        self.settings.setValue('additional_movies_folders', self.additionalMoviesFolders)
        self.setTitleBar()

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

        if self.backupFolder == self.moviesFolder:
            mb = QtWidgets.QMessageBox()
            mb.setText("Error: Backup folder must be different from movies folder")
            mb.setIcon(QtWidgets.QMessageBox.Critical)
            mb.exec()
            return

        if os.path.exists(self.backupFolder):
            self.backupFolderEdit.setText(self.backupFolder)
            drive = os.path.splitdrive(self.backupFolder)[0]

            self.spaceTotal, self.spaceUsed, self.spaceFree = shutil.disk_usage(drive)
            self.spaceTotal = self.spaceTotal
            self.spaceUsed = self.spaceUsed
            self.spaceFree = self.spaceFree
            self.spaceUsedPercent = self.spaceUsed / self.spaceTotal
            self.spaceBarLayout.setStretch(0, self.spaceUsedPercent * 1000)
            self.spaceBarLayout.setStretch(2, (1.0 - self.spaceUsedPercent) * 1000)

            self.spaceAvailableLabel.setText("%dGb  Of  %dGb  Used       %dGb Free" % \
                                             (bToGb(self.spaceUsed),
                                              bToGb(self.spaceTotal),
                                              bToGb(self.spaceFree)))

    def calculateFolderSizes(self):
        numItems = self.moviesTableModel.rowCount()
        self.progressBar.setMaximum(numItems)
        progress = 0
        self.isCanceled = False
        self.moviesTableModel.aboutToChangeLayout()
        for row in range(numItems):
            QtCore.QCoreApplication.processEvents()
            if self.isCanceled:
                self.statusBar().showMessage('Cancelled')
                self.isCanceled = False
                self.progressBar.setValue(0)
                self.moviesTableModel.changedLayout()
                return

            progress += 1
            self.progressBar.setValue(progress)

            modelIndex = self.moviesTableModel.index(row, 0)
            path = self.moviesTableModel.getPath(row)
            folderSize = getFolderSize(path)
            self.moviesTableModel.setSize(modelIndex, '%05d Mb' % bToMb(folderSize))

        self.moviesTableModel.changedLayout()
        self.progressBar.setValue(0)

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
            moviePath = self.moviesTableModel.getPath(sourceIndex.row())
            movieFolderName = self.moviesTableModel.getFolderName(sourceIndex.row())
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

            self.moviesTableModel.setMovieData(sourceIndex.row(), data, moviePath, movieFolderName)

            try:
                with open(jsonFile, "w") as f:
                    json.dump(data, f, indent=4)
            except:
                print("Error writing json file: %s" % jsonFile)

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

            sourceFilesAndSizes = dict()
            for f in os.listdir(sourcePath):
                fullPath = os.path.join(sourcePath, f)
                fileSize = os.path.getsize(fullPath)
                sourceFilesAndSizes[f] = fileSize

            destFilesAndSizes = dict()
            if os.path.exists(destPath):
                for f in os.listdir(destPath):
                    fullPath = os.path.join(destPath, f)
                    fileSize = os.path.getsize(fullPath)
                    destFilesAndSizes[f] = fileSize

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
                    destFileSize = os.path.getsize(fullDestPath)
                    sourceFileSize = sourceFilesAndSizes[f]
                    if sourceFileSize != destFileSize:
                        self.backupListTableModel.setBackupStatus(sourceIndex, "File Size Difference")
                        replaceFolder = True
                        break

            # Check if the destination has files that the source doesn't
            if not replaceFolder:
                for f in destFilesAndSizes.keys():
                    # Check if the destination file exists
                    fullSourcePath = os.path.join(sourcePath, f)
                    if not os.path.exists(fullSourcePath):
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

    def backupRun(self):
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
            sourcePath = self.backupListTableModel.getPath(sourceRow)
            sourceFolderName = self.backupListTableModel.getFolderName(sourceRow)
            sourceFolderSize = self.sourceFolderSizes[sourceFolderName]
            destFolderSize = self.destFolderSizes[sourceFolderName]
            destPath = os.path.join(self.backupFolder, sourceFolderName)

            backupStatus = self.backupListTableModel.getBackupStatus(sourceIndex.row())

            message = "Backing up folder (%05d/%05d): %-50s" \
                      "   Size: %06d Mb" \
                      "   Last rate = %06d Mb/s" \
                      "   Average rate = %06d Mb/s" \
                      "   %10d Mb Remaining" \
                      "   Time remaining: %03d Hours %02d minutes" % \
                      (progress + 1,
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

                # Copy any files that are missing or have different sizes
                for f in os.listdir(sourcePath):
                    sourceFilePath = os.path.join(sourcePath, f)
                    sourceFileSize = os.path.getsize(sourceFilePath)
                    destFilePath = os.path.join(destPath, f)
                    destFileSize = 0
                    if os.path.exists(destFilePath):
                        destFileSize = os.path.getsize(destFilePath)

                    if not os.path.exists(destFilePath):
                        bytesCopied += sourceFileSize
                        if os.path.isdir(sourceFilePath):
                            shutil.copytree(sourceFilePath, destFilePath)
                        else:
                            shutil.copy(sourceFilePath, destFilePath)
                    elif sourceFileSize != destFileSize:
                        bytesCopied += sourceFileSize
                        if not os.path.isdir(sourceFilePath):
                            shutil.copy(sourceFilePath, destFilePath)

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
                estimatedSecondsRemaining = bytesRemaining // averageBytesPerSecond
                estimatedMinutesRemaining = (estimatedSecondsRemaining // 60) % 60
                estimatedHoursRemaining = estimatedSecondsRemaining // 3600

        self.backupListTableModel.changedLayout()
        self.statusBar().showMessage("Done")
        self.progressBar.setValue(0)

    def populateFiltersTable(self):
        if not self.moviesSmdbData:
            print("Error: No smbdData")
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

        numEntries = len(self.moviesSmdbData[filterByKey].keys())
        message = "Populating list: %s with %s entries" % (filterByKey, numEntries)
        self.statusBar().showMessage(message)
        QtCore.QCoreApplication.processEvents()

        self.progressBar.setMaximum(len(self.moviesSmdbData[filterByKey].keys()))
        progress = 0

        self.filterTable.clear()
        self.filterTable.setHorizontalHeaderLabels(['Name', 'Count'])

        row = 0
        numActualRows = 0
        numRows = len(self.moviesSmdbData[filterByKey].keys())
        self.filterTable.setRowCount(numRows)
        self.filterTable.setSortingEnabled(False)
        for name in self.moviesSmdbData[filterByKey].keys():
            count = self.moviesSmdbData[filterByKey][name]['num movies']

            if self.filterMinCountCheckbox.isChecked() and count < self.filterMinCountSpinBox.value():
                continue

            nameItem = QtWidgets.QTableWidgetItem(name)
            self.filterTable.setItem(row, 0, nameItem)
            countItem = QtWidgets.QTableWidgetItem('%04d' % count)
            self.filterTable.setItem(row, 1, countItem)
            row += 1
            progress += 1
            numActualRows += 1
            self.progressBar.setValue(progress)

        self.filterTable.setRowCount(numActualRows)
        self.filterTable.sortItems(1, QtCore.Qt.DescendingOrder)
        self.filterTable.setSortingEnabled(True)

        self.progressBar.setValue(0)

    def cancelButtonClicked(self):
        self.isCanceled = True

    def showMoviesTableSelectionStatus(self):
        numSelected = len(self.moviesTableView.selectionModel().selectedRows())
        self.statusBar().showMessage('%s/%s' % (numSelected, self.numVisibleMovies))

    def tableSelectionChanged(self, table, model, proxyModel):
        self.showMoviesTableSelectionStatus()
        numSelected = len(table.selectionModel().selectedRows())
        if numSelected == 1:
            modelIndex = table.selectionModel().selectedRows()[0]
            self.clickedMovieTable(modelIndex,
                                   model,
                                   proxyModel)

    def clickedMovieTable(self, modelIndex, model, proxyModel):
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

    def showAllMoviesTableView(self):
        self.moviesTableSearchBox.clear()
        self.numVisibleMovies = self.moviesTableProxyModel.rowCount()
        self.showMoviesTableSelectionStatus()
        for row in range(self.moviesTableProxyModel.rowCount()):
            self.moviesTableView.setRowHidden(row, False)
        self.moviesTableProxyModel.sort(0)

    def searchMoviesTableView(self):
        searchText = self.moviesTableSearchBox.text()
        self.moviesTableProxyModel.setFilterKeyColumn(1)
        self.moviesTableProxyModel.setFilterRegExp(
            QtCore.QRegExp(searchText,
                           QtCore.Qt.CaseInsensitive,
                           QtCore.QRegExp.FixedString))
        if not searchText:
            self.filterTableSelectionChanged()

    def showFiltersMenu(self):
        if self.filterWidget:
            self.showFilters = not self.showFilters
            if not self.showFilters:
                self.filterWidget.hide()
            else:
                self.filterWidget.show()

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
        if self.coverWidget:
            self.showCover = not self.showCover
            if not self.showCover:
                self.coverWidget.hide()
            else:
                self.coverWidget.show()

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

        self.moviesTableSearchBox.clear()

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

    def filterTableSelectionChanged(self):
        if len(self.filterTable.selectedItems()) == 0:
            self.showAllMoviesTableView()
            return

        filterByText = self.filterByComboBox.currentText()
        filterByKey = self.filterByDict[filterByText]

        movieList = []
        for item in self.filterTable.selectedItems():
            name = self.filterTable.item(item.row(), 0).text()
            movies = self.moviesSmdbData[filterByKey][name]['movies']
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
        item.setFont(QtGui.QFont('TimesNew Roman', 12))
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

    def summaryShow(self, jsonData):
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
        # infoText = '<span style=\" color: #ffffff; font-size: 8pt\">%s</span>' % infoText
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
        genres = {}
        years = {}
        companies = {}
        countries = {}
        userTags = {}

        count = model.rowCount()
        self.progressBar.setMaximum(count)
        progress = 0
        self.isCanceled = False

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
            size = model.getSize(row)

            message = "Processing item (%d/%d): %s" % (progress + 1,
                                                       count,
                                                       title)
            self.statusBar().showMessage(message)
            QtCore.QCoreApplication.processEvents()

            rank = model.getRank(row)
            moviePath = model.getPath(row)
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

                    jsonRuntime = None
                    if 'runtime' in jsonData and jsonData['runtime']:
                        jsonRuntime = jsonData['runtime']

                    titles[folderName] = {'id': jsonId,
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
                                          'size': size}

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

        self.statusBar().showMessage('Writing %s' % fileName)
        QtCore.QCoreApplication.processEvents()

        with open(fileName, "w") as f:
            json.dump(data, f, indent=4)

        self.statusBar().showMessage('Done')
        QtCore.QCoreApplication.processEvents()

        return data

    def downloadMovieData(self, modelIndex, force=False, movieId=None, doJson=True, doCover=True):
        sourceIndex = self.moviesTableProxyModel.mapToSource(modelIndex)
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

    def filterRightMenu(self):
        rightMenu = QtWidgets.QMenu(self.filterTable)
        selectedItem = self.filterTable.itemAt(self.filterTable.mouseLocation)
        row = selectedItem.row()
        openImdbAction = QtWidgets.QAction("Open IMDB Page", self)
        itemText = self.filterTable.item(row, 0).text()
        filterByText = self.filterByComboBox.currentText()
        if filterByText == 'Director' or filterByText == 'Actor':
            openImdbAction.triggered.connect(lambda: self.openPersonImdbPage(itemText))
        else:
            openImdbAction.triggered.connect(lambda: openYearImdbPage(itemText))
        rightMenu.addAction(openImdbAction)
        rightMenu.exec_(QtGui.QCursor.pos())

    def movieInfoRightMenu(self):
        rightMenu = QtWidgets.QMenu(self.movieInfoListView)
        selectedItem = self.movieInfoListView.itemAt(self.movieInfoListView.mouseLocation)
        category = selectedItem.data(QtCore.Qt.UserRole)[0]
        print("category = %s" % category)
        if category == 'director' or category == 'actor' or category == 'year':
            openImdbAction = QtWidgets.QAction("Open IMDB Page", self)
            itemText = selectedItem.text()
            if category == 'director' or category == 'actor':
                openImdbAction.triggered.connect(lambda: self.openPersonImdbPage(itemText))
            elif category == 'year':
                openImdbAction.triggered.connect(lambda: openYearImdbPage(itemText))
            rightMenu.addAction(openImdbAction)
            rightMenu.exec_(QtGui.QCursor.pos())

    def openPersonImdbPage(self, personName):
        personId = self.db.name2imdbID(personName)
        if not personId:
            results = self.db.search_person(personName)
            if not results:
                print('No matches for: %s' % personName)
                return
            person = results[0]
            if isinstance(person, imdb.Person.Person):
                personId = person.getID()

        if personId:
            webbrowser.open('http://imdb.com/name/nm%s' % personId, new=2)

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
        self.clickedMovieTable(modelIndex,
                               self.watchListTableModel,
                               self.watchListTableProxyModel)

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

    def backupListTableRightMenuShow(self, QPos):
        rightMenu = QtWidgets.QMenu(self.moviesTableView)

        selectAllAction = QtWidgets.QAction("Select All", self)
        selectAllAction.triggered.connect(lambda: self.tableSelectAll(self.backupListTableView))
        rightMenu.addAction(selectAllAction)

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

        moveToTopWatchListAction = QtWidgets.QAction("Move To Top", self)
        moveToTopWatchListAction.triggered.connect(lambda: self.backupListMoveRow(self.MoveTo.TOP))
        rightMenu.addAction(moveToTopWatchListAction)

        moveUpWatchListAction = QtWidgets.QAction("Move Up", self)
        moveUpWatchListAction.triggered.connect(lambda: self.backupListMoveRow(self.MoveTo.UP))
        rightMenu.addAction(moveUpWatchListAction)

        moveDownWatchListAction = QtWidgets.QAction("Move Down", self)
        moveDownWatchListAction.triggered.connect(lambda: self.backupListMoveRow(self.MoveTo.DOWN))
        rightMenu.addAction(moveDownWatchListAction)

        modelIndex = self.backupListTableView.selectionModel().selectedRows()[0]
        self.clickedMovieTable(modelIndex,
                               self.backupListTableModel,
                               self.backupListTableProxyModel)

        rightMenu.exec_(QtGui.QCursor.pos())

    def moviesTableHeaderRightMenuShow(self, QPos):
        menu = QtWidgets.QMenu(self.moviesTableView.horizontalHeader())

        showAllAction = QtWidgets.QAction("Show All")
        menu.addAction(showAllAction)

        actions = []
        headers = self.moviesTableModel.getHeaders()
        for c in self.moviesTableModel.Columns:
            header = headers[c.value]
            action = QtWidgets.QAction(header)
            action.setCheckable(True)
            action.setChecked(self.moviesTableColumnsVisible[c.value])
            actions.append(action)
            menu.addAction(action)

        menu.exec_(QtGui.QCursor.pos())

    def moviesTableRightMenuShow(self, QPos):
        moviesTableRightMenu = QtWidgets.QMenu(self.moviesTableView)

        selectAllAction = QtWidgets.QAction("Select All", self)
        selectAllAction.triggered.connect(lambda: self.tableSelectAll(self.moviesTableView))
        moviesTableRightMenu.addAction(selectAllAction)

        playAction = QtWidgets.QAction("Play")
        playAction.triggered.connect(lambda: self.playMovie(self.moviesTableView,
                                                            self.moviesTableProxyModel))
        moviesTableRightMenu.addAction(playAction)

        addToWatchListAction = QtWidgets.QAction("Add To Watch List", self)
        addToWatchListAction.triggered.connect(self.watchListAdd)
        moviesTableRightMenu.addAction(addToWatchListAction)

        addToBackupListAction = QtWidgets.QAction("Add To Backup List", self)
        addToBackupListAction.triggered.connect(self.backupListAdd)
        moviesTableRightMenu.addAction(addToBackupListAction)

        calculateSizesAction = QtWidgets.QAction("Calculate Folder Sizes", self)
        calculateSizesAction.triggered.connect(self.calculateFolderSizes)
        moviesTableRightMenu.addAction(calculateSizesAction)

        calculateDimensionsAction = QtWidgets.QAction("Calculate Movie Dimensions", self)
        calculateDimensionsAction.triggered.connect(self.calculateMovieDimensions)
        moviesTableRightMenu.addAction(calculateDimensionsAction)

        findDuplicatesAction = QtWidgets.QAction("Find Duplicates", self)
        findDuplicatesAction.triggered.connect(self.findDuplicates)
        moviesTableRightMenu.addAction(findDuplicatesAction)

        addNewUserTagAction = QtWidgets.QAction("Add New User Tag", self)
        addNewUserTagAction.triggered.connect(self.addNewUserTag)
        moviesTableRightMenu.addAction(addNewUserTagAction)

        addExistingUserTagAction = QtWidgets.QAction("Add Existing User Tag", self)
        addExistingUserTagAction.triggered.connect(self.addExistingUserTag)
        moviesTableRightMenu.addAction(addExistingUserTagAction)

        clearUserTagsAction = QtWidgets.QAction("Clear User Tags", self)
        clearUserTagsAction.triggered.connect(self.clearUserTags)
        moviesTableRightMenu.addAction(clearUserTagsAction)

        openFolderAction = QtWidgets.QAction("Open Folder", self)
        openFolderAction.triggered.connect(self.openMovieFolder)
        moviesTableRightMenu.addAction(openFolderAction)

        openJsonAction = QtWidgets.QAction("Open Json File", self)
        openJsonAction.triggered.connect(self.openMovieJson)
        moviesTableRightMenu.addAction(openJsonAction)

        openImdbAction = QtWidgets.QAction("Open IMDB Page", self)
        openImdbAction.triggered.connect(self.openMovieImdbPage)
        moviesTableRightMenu.addAction(openImdbAction)

        overrideImdbAction = QtWidgets.QAction("Override IMDB ID", self)
        overrideImdbAction.triggered.connect(self.overrideID)
        moviesTableRightMenu.addAction(overrideImdbAction)

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

        removeJsonFilesAction = QtWidgets.QAction("Remove .json files", self)
        removeJsonFilesAction.triggered.connect(self.removeJsonFilesMenu)
        moviesTableRightMenu.addAction(removeJsonFilesAction)

        removeCoversAction = QtWidgets.QAction("Remove cover files", self)
        removeCoversAction.triggered.connect(self.removeCoverFilesMenu)
        moviesTableRightMenu.addAction(removeCoversAction)

        modelIndex = self.moviesTableView.selectionModel().selectedRows()[0]
        self.clickedMovieTable(modelIndex,
                               self.moviesTableModel,
                               self.moviesTableProxyModel)

        moviesTableRightMenu.exec_(QtGui.QCursor.pos())

    def tableSelectAll(self, table):
        table.selectAll()
        pass

    @staticmethod
    def playMovie(table, proxy):
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
            info = MediaInfo.parse(fileToPlay)
            for track in info.tracks:
                if track.track_type == 'Video':
                    print("Width = %s Height = %s" % (track.width, track.height))
            if os.path.exists(fileToPlay):
                runFile(fileToPlay)
        else:
            # If there are more than one movie like files in the
            # folder, then just open the folder so the user can
            # play the desired file.
            runFile(moviePath)

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
            sourceIndex = self.moviesTableProxyModel.mapToSource(modelIndex)
            sourceRow = sourceIndex.row()
            moviePath = self.moviesTableModel.getPath(sourceRow)
            self.watchListTableModel.addMovie(self.moviesSmdbData,
                                              moviePath)

        self.watchListTableModel.changedLayout()
        self.writeSmdbFile(self.watchListSmdbFile,
                           self.watchListTableModel,
                           titlesOnly=True)

    def backupListAdd(self):
        self.backupListTableModel.layoutAboutToBeChanged.emit()
        for modelIndex in self.moviesTableView.selectionModel().selectedRows():
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
        webbrowser.open('http://imdb.com/title/tt%s' % movieId, new=2)

    def overrideID(self):
        movieId, ok = QtWidgets.QInputDialog.getText(self,
                                                     "Override ID",
                                                     "Enter new ID",
                                                     QtWidgets.QLineEdit.Normal,
                                                     "")
        if 'tt' in movieId:
            movieId = movieId.replace('tt', '')
        if movieId and ok:
            modelIndex = self.moviesTableView.selectionModel().selectedRows()[0]
            self.downloadMovieData(modelIndex, True, movieId)

    def downloadDataMenu(self, force=False, doJson=True, doCover=True):
        numSelectedItems = len(self.moviesTableView.selectionModel().selectedRows())
        self.progressBar.setMaximum(numSelectedItems)
        progress = 0
        self.isCanceled = False
        for modelIndex in self.moviesTableView.selectionModel().selectedRows():
            QtCore.QCoreApplication.processEvents()
            if self.isCanceled:
                self.statusBar().showMessage('Cancelled')
                self.isCanceled = False
                self.progressBar.setValue(0)
                return

            sourceRow = self.getSourceRow(modelIndex)
            title = self.moviesTableModel.getTitle(sourceRow)
            message = "Downloading data (%d/%d): %s" % (progress + 1,
                                                        numSelectedItems,
                                                        title)
            self.statusBar().showMessage(message)
            QtCore.QCoreApplication.processEvents()

            self.downloadMovieData(modelIndex, force, doJson=doJson, doCover=doCover)
            self.moviesTableView.selectRow(modelIndex.row())
            self.clickedMovieTable(modelIndex,
                                   self.moviesTableModel,
                                   self.moviesTableProxyModel)

            progress += 1
            self.progressBar.setValue(progress)
        self.statusBar().showMessage("Done")
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