from PyQt5 import QtCore, QtGui, QtWidgets
import sys
import os
from enum import Enum
from pathlib import Path
import imdb
from imdb import IMDb
import json
import collections
import webbrowser

from .utilities import *
from .moviemodel import MoviesTableModel


def readSmdbFile(fileName):
    if os.path.exists(fileName):
        with open(fileName) as f:
            return json.load(f)


def getMovieKey(movie, key):
    if movie.has_key(key):
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
        if i != 0: # leave the first column visible
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

    actionsList = []
    for c in model.Columns:
        header = model._headers[c.value]
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


class MyWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super(MyWindow, self).__init__()

        self.numVisibleMovies = 0

        # Create IMDB database
        self.db = IMDb()

        # Read the movies folder from the settings
        self.settings = QtCore.QSettings("STC", "SMDB")
        self.moviesFolder = self.settings.value('movies_folder', "J:/Movies", type=str)

        # Init UI
        self.setWindowTitle("SMDB %s" % self.moviesFolder)
        self.setGeometry(100, 75, 1800, 900)

        # Set foreground/background colors for item views
        self.setStyleSheet("""QAbstractItemView{ background: black; color: white; }; """)

        # Default view state of UI sections
        self.showFilters = True
        self.showMoviesTable = True
        self.showCover = True
        self.showCastCrew = True
        self.showSummary = True
        self.showWatchList = True

        # Default state of cancel button
        self.isCanceled = False

        # Main Menus
        self.initUIFileMenu()
        self.initUIViewMenu()

        # Add the central widget
        centralWidget = QtWidgets.QWidget()
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
            'Year': 'years',
            'Company': 'companies',
            'Country': 'countries'
        }
        self.filterWidget = QtWidgets.QWidget()
        self.filterByComboBox = QtWidgets.QComboBox()
        self.filterMinCountCheckbox = QtWidgets.QCheckBox()
        self.filterMinCountSpinBox = QtWidgets.QSpinBox()
        self.filterTable = QtWidgets.QTableWidget()
        self.initUIFilterTable()

        # Splitter for Movies Table and Watch List
        moviesWatchListVSplitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        moviesWatchListVSplitter.setHandleWidth(20)

        # Movies Table
        self.moviesTableWidget = QtWidgets.QWidget()
        self.moviesTableView = QtWidgets.QTableView()
        self.moviesTableSearchBox = QtWidgets.QLineEdit()
        self.moviesTableColumnsVisible = []
        self.moviesListHeaderActions = []
        self.initUIMoviesTable()
        moviesWatchListVSplitter.addWidget(self.moviesTableWidget)

        # Watch List
        self.watchListWidget = QtWidgets.QWidget()
        self.watchListTableView = QtWidgets.QTableView()
        self.watchListColumnsVisible = []
        self.watchListHeaderActions = []
        self.initUIWatchList()
        moviesWatchListVSplitter.addWidget(self.watchListWidget)

        moviesWatchListVSplitter.setSizes([700, 200])

        # Cover and Summary V Splitter
        coverSummaryVSplitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        coverSummaryVSplitter.setHandleWidth(20)
        coverSummaryVSplitter.splitterMoved.connect(self.resizeCoverFile)

        # Title/Cover and Cast/Crew H Splitter
        coverCrewHSplitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)

        coverSummaryVSplitter.addWidget(coverCrewHSplitter)

        # Title and Cover
        self.titleAndCoverWidget = QtWidgets.QWidget()
        self.movieTitle = QtWidgets.QLabel('')
        self.movieCover = QtWidgets.QLabel()
        self.initUITitleAndCover()

        coverCrewHSplitter.addWidget(self.titleAndCoverWidget)

        # Cast and Crew list
        self.castCrewWidget = QtWidgets.QWidget()
        coverCrewHSplitter.addWidget(self.castCrewWidget)
        coverCrewHSplitter.splitterMoved.connect(self.resizeCoverFile)
        castCrewVLayout = QtWidgets.QVBoxLayout()
        self.castCrewWidget.setLayout(castCrewVLayout)
        castCrewLabel = QtWidgets.QLabel("Cast and Crew")
        castCrewVLayout.addWidget(castCrewLabel)
        self.castCrewListView = QtWidgets.QListWidget()
        self.castCrewListView.itemSelectionChanged.connect(self.castCrewSelectionChanged)
        castCrewVLayout.addWidget(self.castCrewListView)
        coverCrewHSplitter.setSizes([500, 200])

        # Summary
        self.summary = QtWidgets.QTextBrowser()
        self.summary.setFont(QtGui.QFont('TimesNew Roman', 12))
        self.summary.setStyleSheet("color:white; background-color: black;")
        coverSummaryVSplitter.setSizes([600, 200])
        coverSummaryVSplitter.addWidget(self.summary)

        # Add the sub-layouts to the mainHSplitter
        mainHSplitter.addWidget(self.filterWidget)
        mainHSplitter.addWidget(moviesWatchListVSplitter)
        mainHSplitter.addWidget(coverSummaryVSplitter)
        mainHSplitter.setSizes([300, 800, 700])
        mainHSplitter.splitterMoved.connect(self.resizeCoverFile)

        # Bottom
        bottomLayout = QtWidgets.QHBoxLayout(self)
        mainVLayout.addLayout(bottomLayout)
        self.progressBar = QtWidgets.QProgressBar()
        self.progressBar.setMaximum(100)
        bottomLayout.addWidget(self.progressBar)
        cancelButton = QtWidgets.QPushButton("Cancel", self)
        cancelButton.clicked.connect(self.cancelButtonClicked)
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

        backupMoviesFolderAction = QtWidgets.QAction("Backup movie folder", self)
        backupMoviesFolderAction.triggered.connect(self.backupMoviesFolder)
        fileMenu.addAction(backupMoviesFolderAction)

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

        showCoverAction = QtWidgets.QAction("Show Cover", self)
        showCoverAction.setCheckable(True)
        showCoverAction.setChecked(self.showCover)
        showCoverAction.triggered.connect(self.showCoverMenu)
        viewMenu.addAction(showCoverAction)

        showCastCrewAction = QtWidgets.QAction("Show Cast and Crew", self)
        showCastCrewAction.setCheckable(True)
        showCastCrewAction.setChecked(self.showCastCrew)
        showCastCrewAction.triggered.connect(self.showCastCrewMenu)
        viewMenu.addAction(showCastCrewAction)

        showSummaryAction = QtWidgets.QAction("Show Summary", self)
        showSummaryAction.setCheckable(True)
        showSummaryAction.setChecked(self.showSummary)
        showSummaryAction.triggered.connect(self.showSummaryMenu)
        viewMenu.addAction(showSummaryAction)

    def initUIFilterTable(self):
        filtersVLayout = QtWidgets.QVBoxLayout()
        self.filterWidget.setLayout(filtersVLayout)

        filterByHLayout = QtWidgets.QHBoxLayout()
        self.filterWidget.layout().addLayout(filterByHLayout)

        filterByLabel = QtWidgets.QLabel("Filter By")
        filterByLabel.setSizePolicy(QtWidgets.QSizePolicy.Maximum,
                                    QtWidgets.QSizePolicy.Maximum)
        filterByHLayout.addWidget(filterByLabel)

        for i in self.filterByDict.keys():
            self.filterByComboBox.addItem(i)
        self.filterByComboBox.setCurrentIndex(0)
        self.filterByComboBox.activated.connect(self.populateFiltersTable)
        filterByHLayout.addWidget(self.filterByComboBox)

        minCountHLayout = QtWidgets.QHBoxLayout()
        self.filterWidget.layout().addLayout(minCountHLayout)
        self.filterMinCountCheckbox.setText("Enable Min Count")
        self.filterMinCountCheckbox.setChecked(True)
        minCountHLayout.addWidget(self.filterMinCountCheckbox)

        self.filterMinCountSpinBox.setMinimum(0)
        self.filterMinCountSpinBox.setValue(2)
        self.filterMinCountSpinBox.valueChanged.connect(self.populateFiltersTable)
        minCountHLayout.addWidget(self.filterMinCountSpinBox)

        self.filterMinCountCheckbox.stateChanged.connect(self.filterMinCountSpinBox.setEnabled)
        self.filterMinCountCheckbox.stateChanged.connect(self.populateFiltersTable)

        self.filterTable.setColumnCount(2)
        self.filterTable.verticalHeader().hide()
        self.filterTable.setHorizontalHeaderLabels(['Name', 'Count'])
        self.filterTable.setColumnWidth(0, 170)
        self.filterTable.setColumnWidth(1, 45)
        self.filterTable.verticalHeader().setMinimumSectionSize(10)
        self.filterTable.verticalHeader().setDefaultSectionSize(18)
        self.filterTable.setWordWrap(False)
        style = "::section {""color: black; }"
        self.filterTable.horizontalHeader().setStyleSheet(style)
        self.filterTable.itemSelectionChanged.connect(self.filterTableSelectionChanged)
        filtersVLayout.addWidget(self.filterTable)

        filtersSearchHLayout = QtWidgets.QHBoxLayout()
        filtersVLayout.addLayout(filtersSearchHLayout)

        searchText = QtWidgets.QLabel("Search")
        searchText.setSizePolicy(QtWidgets.QSizePolicy.Maximum,
                                 QtWidgets.QSizePolicy.Maximum)
        filtersSearchHLayout.addWidget(searchText)

        filterTableSearchBox = QtWidgets.QLineEdit(self)
        filterTableSearchBox.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Maximum)
        filterTableSearchBox.setClearButtonEnabled(True)
        filtersSearchHLayout.addWidget(filterTableSearchBox)
        filterTableSearchBox.textChanged.connect(lambda: searchTableWidget(filterTableSearchBox, self.filterTable))

    def initUIMoviesTable(self):
        moviesTableViewVLayout = QtWidgets.QVBoxLayout()
        self.moviesTableWidget.setLayout(moviesTableViewVLayout)

        moviesTableViewVLayout.addWidget(QtWidgets.QLabel("Movies"))

        self.moviesTableView.setSortingEnabled(True)
        self.moviesTableView.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.moviesTableView.verticalHeader().hide()
        style = "::section {""color: black; }"
        self.moviesTableView.horizontalHeader().setStyleSheet(style)
        self.moviesTableView.horizontalHeader().setSectionsMovable(True)
        self.moviesTableView.setShowGrid(False)

        # TODO: Need to find a better way to set the alternating colors
        # Setting alternate colors to true makes them black and white.
        # Changing the color using a stylesheet looks better but makes
        # the right click menu background also black.
        # self.moviesTable.setAlternatingRowColors(True)
        # self.moviesTable.setStyleSheet("alternate-background-color: #151515;background-color: black;");

        # Right click header menu
        hh = self.moviesTableView.horizontalHeader()
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
        showAllButton.setSizePolicy(QtWidgets.QSizePolicy.Maximum,
                                    QtWidgets.QSizePolicy.Maximum)
        showAllButton.clicked.connect(self.showAllMoviesTableView)
        moviesTableSearchHLayout.addWidget(showAllButton)

        # Search box
        searchText = QtWidgets.QLabel("Search")
        searchText.setSizePolicy(QtWidgets.QSizePolicy.Maximum,
                                 QtWidgets.QSizePolicy.Maximum)
        moviesTableSearchHLayout.addWidget(searchText)

        self.moviesTableSearchBox.setSizePolicy(QtWidgets.QSizePolicy.Ignored,
                                                QtWidgets.QSizePolicy.Maximum)
        self.moviesTableSearchBox.setClearButtonEnabled(True)
        self.moviesTableSearchBox.textChanged.connect(self.searchMoviesTableView)
        moviesTableSearchHLayout.addWidget(self.moviesTableSearchBox)


    def initUIWatchList(self):
        watchListVLayout = QtWidgets.QVBoxLayout()
        self.watchListWidget.setLayout(watchListVLayout)

        watchListVLayout.addWidget(QtWidgets.QLabel("Watch List"))

        self.watchListTableView.setSortingEnabled(False)
        self.watchListTableView.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.watchListTableView.verticalHeader().hide()
        style = "::section {""color: black; }"
        self.watchListTableView.horizontalHeader().setStyleSheet(style)
        self.watchListTableView.horizontalHeader().setSectionsMovable(True)
        self.watchListTableView.setShowGrid(False)

        # Right click header menu
        hh = self.watchListTableView.horizontalHeader()
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
        addButton.clicked.connect(self.addToWatchList)
        watchListButtonsHLayout.addWidget(addButton)

        removeButton = QtWidgets.QPushButton('Remove')
        removeButton.clicked.connect(self.removeFromWatchList)
        watchListButtonsHLayout.addWidget(removeButton)

        moveToTopButton = QtWidgets.QPushButton('Move To Top')
        moveToTopButton.clicked.connect(lambda: self.watchListMoveRow(self.MoveTo.TOP))
        watchListButtonsHLayout.addWidget(moveToTopButton)

        moveUpButton = QtWidgets.QPushButton('Move Up')
        moveUpButton.clicked.connect(lambda: self.watchListMoveRow(self.MoveTo.UP))
        watchListButtonsHLayout.addWidget(moveUpButton)

        moveDownButton = QtWidgets.QPushButton('Move Down')
        moveDownButton.clicked.connect(lambda: self.watchListMoveRow(self.MoveTo.DOWN))
        watchListButtonsHLayout.addWidget(moveDownButton)


    def initUITitleAndCover(self):
        self.titleAndCoverWidget.setStyleSheet("background-color: black;")
        movieVLayout = QtWidgets.QVBoxLayout()
        self.titleAndCoverWidget.setLayout(movieVLayout)

        self.movieTitle.setWordWrap(True)
        self.movieTitle.setAlignment(QtCore.Qt.AlignTop)
        self.movieTitle.setFont(QtGui.QFont('TimesNew Roman', 15))
        self.movieTitle.setSizePolicy(QtWidgets.QSizePolicy.MinimumExpanding, QtWidgets.QSizePolicy.Fixed)
        self.movieTitle.setStyleSheet("color: yellow;")
        movieVLayout.addWidget(self.movieTitle)

        self.movieCover.setScaledContents(False)
        self.movieCover.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Ignored)
        self.movieCover.setStyleSheet("background-color: black;")
        movieVLayout.addWidget(self.movieCover)

    def refreshMoviesList(self, forceScan=False):
        if os.path.exists(self.moviesSmdbFile):
            self.moviesSmdbData = readSmdbFile(self.moviesSmdbFile)
            self.moviesTableModel = MoviesTableModel(self.moviesSmdbData,
                                                     self.moviesFolder,
                                                     forceScan)
        else:
            self.moviesTableModel = MoviesTableModel(self.moviesSmdbData,
                                                     self.moviesFolder,
                                                     True) # Force scan if no smdb file
            # Generate smdb data from movies table model and write
            # out smdb file
            self.moviesSmdbData = self.writeSmdbFile(self.moviesSmdbFile,
                                                     self.moviesTableModel)

        self.moviesTableProxyModel = QtCore.QSortFilterProxyModel()
        self.moviesTableProxyModel.setSourceModel(self.moviesTableModel)

        mtv = self.moviesTableView
        mtm = self.moviesTableModel
        mtpm = self.moviesTableProxyModel

        # If forScan, sort by exists otherwise year
        if forceScan:
            mtpm.sort(mtm.Columns.JsonExists.value)
        else:
            mtpm.sort(mtm.Columns.Year.value)

        mtv.setModel(mtpm)
        mtv.selectionModel().selectionChanged.connect(lambda: self.tableSelectionChanged(mtv, mtm, mtpm))
        mtv.doubleClicked.connect(lambda: self.playMovie(mtv, mtpm))

        # Don't sort the table when the data changes
        mtpm.setDynamicSortFilter(False)

        mtv.setWordWrap(False)

        # Set the column widths
        self.moviesTableColumnsVisible = []
        for col in mtm.Columns:
            mtv.setColumnWidth(col.value, mtm.defaultWidths[col])
            self.moviesTableColumnsVisible.append(True)

        # For the movie list, hide
        # id, folder, path, company, country, and rank by default
        columnsToHide = [mtm.Columns.Id,
                         mtm.Columns.Country,
                         mtm.Columns.Company,
                         mtm.Columns.Folder,
                         mtm.Columns.Path,
                         mtm.Columns.Rank]
        for c in columnsToHide:
            index = c.value
            mtv.hideColumn(index)
            self.moviesTableColumnsVisible[index] = False

        # Make the row height smaller
        mtv.verticalHeader().setMinimumSectionSize(10)
        mtv.verticalHeader().setDefaultSectionSize(18)

        self.numVisibleMovies = mtpm.rowCount()
        self.showMoviesTableSelectionStatus()

        mtv.selectRow(0)
        self.tableSelectionChanged(mtv, mtm, mtpm)

    def refreshWatchList(self):
        if os.path.exists(self.watchListSmdbFile):
            self.watchListSmdbData = readSmdbFile(self.watchListSmdbFile)
        self.watchListTableModel = MoviesTableModel(self.watchListSmdbData,
                                                    self.moviesFolder,
                                                    False, # force scan
                                                    True) # dont scan the movies folder for the watch list
        self.watchListTableProxyModel = QtCore.QSortFilterProxyModel()
        self.watchListTableProxyModel.setSourceModel(self.watchListTableModel)

        wtv = self.watchListTableView
        wtm = self.watchListTableModel
        wtpm = self.watchListTableProxyModel

        # Sort the watch list by rankl
        wtpm.sort(wtm.Columns.Rank.value)

        wtv.setModel(wtpm)
        wtv.selectionModel().selectionChanged.connect(lambda: self.tableSelectionChanged(wtv, wtm, wtpm))
        wtv.doubleClicked.connect(lambda: self.playMovie(wtv, wtpm))
        wtpm.setDynamicSortFilter(False)
        wtv.setWordWrap(False)

        self.watchListColumnsVisible = []
        for col in wtm.Columns:
            wtv.setColumnWidth(col.value, wtm.defaultWidths[col])
            self.watchListColumnsVisible.append(True)

        # For the watch list, hide
        # country, company, box office, runtime, id,
        # folder, path, and json exists by default
        columnsToHide = [wtm.Columns.BoxOffice,
                         wtm.Columns.Runtime,
                         wtm.Columns.Director,
                         wtm.Columns.Country,
                         wtm.Columns.Company,
                         wtm.Columns.Id,
                         wtm.Columns.Folder,
                         wtm.Columns.Path,
                         wtm.Columns.JsonExists]
        for c in columnsToHide:
            index = c.value
            wtv.hideColumn(index)
            self.watchListColumnsVisible[index] = False

        # Set rank as the first column
        wtv.horizontalHeader().moveSection(wtm.Columns.Rank.value, 0)

        wtv.verticalHeader().setMinimumSectionSize(10)
        wtv.verticalHeader().setDefaultSectionSize(18)

    def backupMoviesFolder(self):
        pass

    def preferences(self):
        pass

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
            self.setWindowTitle("SMDB %s" % self.moviesFolder)
            self.settings.setValue('movies_folder', self.moviesFolder)
            print("Saved: moviesFolder = %s" % self.moviesFolder)
            readSmdbFile(self.moviesSmdbFile)
            self.moviesSmdbFile = os.path.join(self.moviesFolder, "smdb_data.json")
            self.refreshMoviesList()

    def populateFiltersTable(self):
        if not self.moviesSmdbData:
            print("Error: No smbdData")
            return

        filterByText = self.filterByComboBox.currentText()
        filterByKey = self.filterByDict[filterByText]

        if filterByText == 'Director' or filterByText == 'Actor':
            self.filterTable.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
            try: self.filterTable.customContextMenuRequested[QtCore.QPoint].disconnect()
            except Exception: pass
            self.filterTable.customContextMenuRequested[QtCore.QPoint].connect(
                self.filterRightMenuShowPeople)
        elif filterByText == 'Year':
            self.filterTable.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
            try: self.filterTable.customContextMenuRequested[QtCore.QPoint].disconnect()
            except Exception: pass
            self.filterTable.customContextMenuRequested[QtCore.QPoint].connect(
                self.filterRightMenuShowYear)
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

        self.movieTitle.setText('%s (%s)' % (title, year))
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

        self.showMovieInfo(jsonData)
        self.showCastCrewInfo(jsonData)

    def showAllMoviesTableView(self):
        self.moviesTableSearchBox.clear()
        self.numVisibleMovies = self.moviesTableProxyModel.rowCount()
        self.showMoviesTableSelectionStatus()
        for row in range(self.moviesTableProxyModel.rowCount()):
            self.moviesTableView.setRowHidden(row, False)

    def searchMoviesTableView(self):
        searchText = self.moviesTableSearchBox.text()
        self.moviesTableProxyModel.setFilterKeyColumn(1)
        self.moviesTableProxyModel.setFilterRegExp(
            QtCore.QRegExp(searchText,
                           QtCore.Qt.CaseInsensitive,
                           QtCore.QRegExp.FixedString))
        if not searchText:
            self.moviesTableProxyModel.sort(0)
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

    def showCoverMenu(self):
        if self.titleAndCoverWidget:
            self.showCover = not self.showCover
            if not self.showCover:
                self.titleAndCoverWidget.hide()
            else:
                self.titleAndCoverWidget.show()

    def showCastCrewMenu(self):
        if self.castCrewWidget:
            self.showCastCrew = not self.showCastCrew
            if not self.showCastCrew:
                self.castCrewWidget.hide()
            else:
                self.castCrewWidget.show()

    def showSummaryMenu(self):
        if self.summary:
            self.showSummary = not self.showSummary
            if not self.showSummary:
                self.summary.hide()
            else:
                self.summary.show()

    def castCrewSelectionChanged(self):
        if len(self.castCrewListView.selectedItems()) == 0:
            return

        self.moviesTableSearchBox.clear()

        movieList = []
        for item in self.castCrewListView.selectedItems():
            smdbKey = None
            category = item.data(QtCore.Qt.UserRole)[0]
            name = item.data(QtCore.Qt.UserRole)[1]
            if category:
                if category == 'actor':
                    smdbKey = 'actors'
                elif category == 'director':
                    smdbKey = 'directors'
                else:
                    continue

            if smdbKey:
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

    def showCastCrewInfo(self, jsonData):
        if not jsonData: return
        self.castCrewListView.clear()

        directorHeaderItem = QtWidgets.QListWidgetItem("Director:")
        directorHeaderItem.setFlags(QtCore.Qt.ItemIsEnabled)
        self.castCrewListView.addItem(directorHeaderItem)

        if 'director' in jsonData and jsonData['director']:
            directorName = jsonData['director'][0]
            numMovies = 0
            if directorName in self.moviesSmdbData['directors']:
                numMovies = self.moviesSmdbData['directors'][directorName]['num movies']
            directorItem = QtWidgets.QListWidgetItem('%s(%d)' % (directorName, numMovies))
            directorItem.setData(QtCore.Qt.UserRole, ['director', directorName])
            self.castCrewListView.addItem(directorItem)

        spacerItem = QtWidgets.QListWidgetItem("")
        spacerItem.setFlags(QtCore.Qt.ItemIsEnabled)
        self.castCrewListView.addItem(spacerItem)

        castHeaderItem = QtWidgets.QListWidgetItem("Cast:")
        castHeaderItem.setFlags(QtCore.Qt.ItemIsEnabled)
        self.castCrewListView.addItem(castHeaderItem)

        if 'cast' in jsonData and jsonData['cast']:
            for actorName in jsonData['cast']:
                numMovies = 0
                if actorName in self.moviesSmdbData['actors']:
                    numMovies = self.moviesSmdbData['actors'][actorName]['num movies']
                castItem = QtWidgets.QListWidgetItem('%s(%d)' % (actorName, numMovies))
                castItem.setData(QtCore.Qt.UserRole, ['actor', actorName])
                self.castCrewListView.addItem(castItem)

    def showMovieInfo(self, jsonData):
        if not jsonData: return

        infoText = ''
        if 'plot' in jsonData and jsonData['plot']:
            infoText += '<br>Plot:<br>'
            plot = ''
            if isinstance(jsonData['plot'], list):
                plot = jsonData['plot'][0]
            else:
                plot = jsonData['plot']
            # Remove the author of the plot's name
            plot = plot.split('::')[0]
            infoText += '%s<br>' % plot
        if 'synopsis' in jsonData and jsonData['synopsis']:
            infoText += '<br>Synopsis:<br>'
            synopsis = ''
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
        director = getMovieKey(movie, 'director')
        if (director):
            if isinstance(director, list):
                directorName = str(director[0]['name'])
                directorId = self.db.name2imdbID(directorName)
                d['director'] = [directorName, directorId]
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
        genres = {}
        years = {}
        companies = {}
        countries = {}

        count = model.rowCount()
        self.progressBar.setMaximum(count)
        progress = 0
        self.isCanceled = False

        for row in range(count):

            QtCore.QCoreApplication.processEvents()
            if self.isCanceled == True:
                self.statusBar().showMessage('Cancelled')
                self.isCanceled = False
                self.progressBar.setValue(0)
                self.setMovieListItemColors()
                return

            title = model.getTitle(row)

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

                    if 'director' in jsonData and jsonData['director']:
                        directorData = jsonData['director']

                        if isinstance(directorData, list):
                            directorName = directorData[0]
                            directorId = directorData[1]
                        else:
                            directorName = directorData
                            directorId = ''

                        if not directorName in directors:
                            directors[directorName] = {}
                            directors[directorName]['id'] = directorId
                            directors[directorName]['num movies'] = 0
                            directors[directorName]['movies'] = []
                        if titleYear not in directors[directorName]['movies']:
                            directors[directorName]['movies'].append(titleYear)
                            directors[directorName]['num movies'] += 1

                    movieActorsList = []
                    if 'cast' in jsonData and jsonData['cast']:
                        jsonActors = jsonData['cast']
                        for actorData in jsonActors:
                            if isinstance(actorData, list):
                                actorName = actorData[0]
                                actorId = actorData[1]
                            else:
                                actorName = actorData
                                actorId = ''

                            if actorName not in actors:
                                actors[actorName] = {}
                                actors[actorName]['id'] = actorId
                                actors[actorName]['num movies'] = 0
                                actors[actorName]['movies'] = []
                            if titleYear not in actors[actorName]['movies']:
                                actors[actorName]['movies'].append(titleYear)
                                actors[actorName]['num movies'] += 1

                            movieActorsList.append(actorName)

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
                                          'runtime': jsonRuntime,
                                          'box office': jsonBoxOffice,
                                          'director': directorName,
                                          'genres': jsonGenres,
                                          'countries': jsonCountries,
                                          'companies': jsonCompanies,
                                          'actors': movieActorsList,
                                          'rank': rank}

            progress += 1
            self.progressBar.setValue(progress)

        self.progressBar.setValue(0)

        self.statusBar().showMessage('Sorting Data...')
        QtCore.QCoreApplication.processEvents()

        data = {}
        data['titles'] = collections.OrderedDict(sorted(titles.items()))
        if not titlesOnly:
            data['years'] = collections.OrderedDict(sorted(years.items()))
            data['genres'] = collections.OrderedDict(sorted(genres.items()))
            data['directors'] = collections.OrderedDict(sorted(directors.items()))
            data['actors'] = collections.OrderedDict(sorted(actors.items()))
            data['companies'] = collections.OrderedDict(sorted(companies.items()))
            data['countries'] = collections.OrderedDict(sorted(countries.items()))

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
            if res.has_key('year') and res.has_key('kind'):
                kind = res['kind']
                if res['year'] == year and (kind in acceptableKinds):
                    movie = res
                    print('Found result: %s (%s)' % (movie['title'], movie['year']))
                    break

        return movie

    # Context Menus -----------------------------------------------------------

    def filterRightMenuShowPeople(self):
        peopleRightMenu = QtWidgets.QMenu(self.filterTable)
        selectedItem = self.filterTable.selectedItems()[0]
        row = selectedItem.row()
        openImdbAction = QtWidgets.QAction("Open IMDB Page", self)
        personName = self.filterTable.item(row, 0).text()
        openImdbAction.triggered.connect(lambda: self.openPersonImdbPage(personName))
        peopleRightMenu.addAction(openImdbAction)
        peopleRightMenu.exec_(QtGui.QCursor.pos())

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

        if (personId):
            webbrowser.open('http://imdb.com/name/nm%s' % personId, new=2)

    def filterRightMenuShowYear(self):
        rightMenu = QtWidgets.QMenu(self.filterTable)
        selectedItem = self.filterTable.selectedItems()[0]
        row = selectedItem.row()
        year = self.filterTable.item(row, 0).text()
        openImdbAction = QtWidgets.QAction("Open IMDB Page", self)
        openImdbAction.triggered.connect(lambda: openYearImdbPage(year))
        rightMenu.addAction(openImdbAction)
        rightMenu.exec_(QtGui.QCursor.pos())

    def watchListTableRightMenuShow(self, QPos):
        rightMenu = QtWidgets.QMenu(self.moviesTableView)

        playAction = QtWidgets.QAction("Play", self)
        playAction.triggered.connect(lambda: self.playMovie(self.watchListTableView,
                                                            self.watchListTableProxyModel))
        rightMenu.addAction(playAction)

        removeFromWatchListAction = QtWidgets.QAction("Remove From Watch List", self)
        removeFromWatchListAction.triggered.connect(self.removeFromWatchList)
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


    def moviesTableHeaderRightMenuShow(self, QPos):
        menu = QtWidgets.QMenu(self.moviesTableView.horizontalHeader())

        showAllAction = QtWidgets.QAction("Show All")
        menu.addAction(showAllAction)

        actions = []
        for c in self.moviesTableModel.Columns:
            header = self.moviesTableModel._headers[c.value]
            action = QtWidgets.QAction(header)
            action.setCheckable(True)
            action.setChecked(self.moviesTableColumnsVisible[c.value])
            actions.append(action)
            menu.addAction(action)

        menu.exec_(QtGui.QCursor.pos())

    def moviesTableRightMenuShow(self, QPos):
        moviesTableRightMenu = QtWidgets.QMenu(self.moviesTableView)

        playAction = QtWidgets.QAction("Play")
        playAction.triggered.connect(lambda: self.playMovie(self.moviesTableView,
                                                            self.moviesTableProxyModel))
        moviesTableRightMenu.addAction(playAction)

        addToWatchListAction = QtWidgets.QAction("Add To Watch List", self)
        addToWatchListAction.triggered.connect(self.addToWatchList)
        moviesTableRightMenu.addAction(addToWatchListAction)

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

    def playMovie(self, table, proxy):
        proxyIndex = table.selectionModel().selectedRows()[0]
        sourceIndex = proxy.mapToSource(proxyIndex)
        sourceRow = sourceIndex.row()
        moviePath = proxy.sourceModel().getPath(sourceRow)
        if not os.path.exists(moviePath):
            return

        movieFiles = []
        for file in os.listdir(moviePath):
            extension = os.path.splitext(file)[1]
            if extension == '.mkv' or \
                    extension == '.mpg' or \
                    extension == '.mp4' or \
                    extension == '.avi' or \
                    extension == '.avi' or \
                    extension == '.m4v':
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

    def addToWatchList(self):
        for modelIndex in self.moviesTableView.selectionModel().selectedRows():
            sourceIndex = self.moviesTableProxyModel.mapToSource(modelIndex)
            sourceRow = sourceIndex.row()
            movieFolderName = self.moviesTableModel.getFolderName(sourceRow)
            moviePath = self.moviesTableModel.getPath(sourceRow)
            self.watchListTableModel.addMovie(self.moviesSmdbData,
                                              moviePath,
                                              movieFolderName)
        self.writeSmdbFile(self.watchListSmdbFile,
                           self.watchListTableModel,
                           titlesOnly=True)

    def removeFromWatchList(self):
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

    class MoveTo(Enum):
        DOWN = 0
        UP = 1
        TOP = 2

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
            if self.isCanceled == True:
                self.statusBar().showMessage('Cancelled')
                self.isCanceled = False
                self.progressBar.setValue(0)
                self.setMovieListItemColors()
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
            if (os.path.exists(jsonFile)):
                filesToDelete.append(os.path.join(moviePath, jsonFile))
        removeFiles(self, filesToDelete, '.json')
        # self.setMovieListItemColors()

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