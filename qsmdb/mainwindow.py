from PyQt5 import QtCore, QtGui, QtWidgets
import sys
import os
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


class MyWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super(MyWindow, self).__init__()

        self.setWindowTitle("Scott's Movie Database")
        self.setGeometry(200, 75, 1275, 900)

        # Menus and Actions
        self.rightMenu = None
        self.playAction = None
        self.addToWatchListAction = None
        self.openFolderAction = None
        self.openJsonAction = None
        self.overrideImdbAction = None
        self.downloadDataAction = None
        self.removeJsonFilesAction = None
        self.removeCoversAction = None

        self.peopleRightMenu = None
        self.openImdbAction = None

        # Widgets
        self.filterWidget = None
        self.moviesTableWidget = None
        self.moviesTable = None
        self.movieCover = None
        self.filterTable = None
        self.filterByComboBox = None
        self.watchListWidget = None
        self.watchListTable = None
        self.coverWidget = None
        self.movieTitle = None
        self.summary = None
        self.progressBar = None

        self.filterByDict = {
            'Director': 'directors',
            'Actor': 'actors',
            'Genre': 'genres',
            'Year': 'years',
            'Company': 'companies',
            'Country': 'countries'
        }

        self.numVisibleMovies = 0

        # Default view state of panels
        self.showFilters = True
        self.showMoviesTable = True
        self.showCover = True
        self.showSummary = True
        self.showWatchList = True
        self.isCanceled = False

        # Create IMDB database
        self.db = IMDb()

        self.settings = QtCore.QSettings("STC", "SMDB")
        self.moviesFolder = self.settings.value('movies_folder', "J:/Movies", type=str)

        self.moviesSmdbFile = os.path.join(self.moviesFolder, "smdb_data.json")
        self.moviesSmdbData = None
        self.moviesTableModel = None
        self.moviesTableProxyModel = None

        self.watchListSmdbFile = os.path.join(self.moviesFolder, "smdb_data_watch_list.json")
        self.watchListSmdbData = None
        self.watchListTableModel = None
        self.watchListTableProxyModel = None

        self.initUI()
        self.show()
        self.refresh()

    def initUI(self):
        menuBar = self.menuBar()

        # File Menu ---------------------------------------------------------------------------------------
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
        refreshAction.triggered.connect(lambda: self.refresh(forceScan=True))
        fileMenu.addAction(refreshAction)

        preferencesAction = QtWidgets.QAction("Preferences", self)
        preferencesAction.triggered.connect(self.preferences)
        fileMenu.addAction(preferencesAction)

        quitAction = QtWidgets.QAction("Quit", self)
        quitAction.triggered.connect(QtCore.QCoreApplication.quit)
        fileMenu.addAction(quitAction)

        # View Menu ---------------------------------------------------------------------------------------
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

        showSummaryAction = QtWidgets.QAction("Show Summary", self)
        showSummaryAction.setCheckable(True)
        showSummaryAction.setChecked(self.showSummary)
        showSummaryAction.triggered.connect(self.showSummaryMenu)
        viewMenu.addAction(showSummaryAction)

        # Central Widget ---------------------------------------------------------------------------------------

        centralWidget = QtWidgets.QWidget()
        self.setCentralWidget(centralWidget)

        # Divides top h splitter and bottom progress bar
        mainVLayout = QtWidgets.QVBoxLayout(self)
        centralWidget.setLayout(mainVLayout)
        # centralWidget.setStyleSheet("background-color: black;")

        # Main H Splitter for criteria, movies list, and cover/info
        mainHSplitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal, self)
        mainHSplitter.setHandleWidth(10)
        mainVLayout.addWidget(mainHSplitter)

        self.setStyleSheet("""
                        QAbstractItemView{
                            background: black;
                            color: white;
                        };
                        """
                           )

        # Filters Table ---------------------------------------------------------------------------------------
        self.filterWidget = QtWidgets.QWidget()
        filtersVLayout = QtWidgets.QVBoxLayout()
        self.filterWidget.setLayout(filtersVLayout)

        filterByHLayout = QtWidgets.QHBoxLayout()
        self.filterWidget.layout().addLayout(filterByHLayout)

        filterByLabel = QtWidgets.QLabel("Filter By")
        filterByLabel.setSizePolicy(QtWidgets.QSizePolicy.Maximum,
                                    QtWidgets.QSizePolicy.Maximum)
        filterByHLayout.addWidget(filterByLabel)

        self.filterByComboBox = QtWidgets.QComboBox()
        for i in self.filterByDict.keys():
            self.filterByComboBox.addItem(i)
        self.filterByComboBox.setCurrentIndex(0)
        self.filterByComboBox.activated.connect(self.populateFiltersTable)
        filterByHLayout.addWidget(self.filterByComboBox)

        self.filterTable = QtWidgets.QTableWidget()
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

        # Movies Table ---------------------------------------------------------------------------------------
        moviesWatchlistVSplitter = QtWidgets.QSplitter(QtCore.Qt.Vertical, self)
        moviesWatchlistVSplitter.setHandleWidth(20)

        self.moviesTableWidget = QtWidgets.QWidget()
        moviesTableViewVLayout = QtWidgets.QVBoxLayout()
        self.moviesTableWidget.setLayout(moviesTableViewVLayout)

        moviesTableViewVLayout.addWidget(QtWidgets.QLabel("Movies"))

        self.moviesTable = QtWidgets.QTableView()
        self.moviesTable.setSortingEnabled(True)
        self.moviesTable.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.moviesTable.verticalHeader().hide()
        style = "::section {""color: black; }"
        self.moviesTable.horizontalHeader().setStyleSheet(style)
        self.moviesTable.setShowGrid(False)
        # TODO: Need to find a better way to set the alternating colors
        # Setting alternate colors to true makes them black and white.
        # Changing the color using a stylesheet looks better but makes
        # the right click menu background also black.
        # self.moviesTable.setAlternatingRowColors(True)
        # self.moviesTable.setStyleSheet("alternate-background-color: #151515;background-color: black;");
        self.moviesTable.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.moviesTable.customContextMenuRequested[QtCore.QPoint].connect(self.moviesTableRightMenuShow)
        moviesTableViewVLayout.addWidget(self.moviesTable)

        moviesTableSearchHLayout = QtWidgets.QHBoxLayout()
        moviesTableViewVLayout.addLayout(moviesTableSearchHLayout)

        searchText = QtWidgets.QLabel("Search")
        searchText.setSizePolicy(QtWidgets.QSizePolicy.Maximum,
                                 QtWidgets.QSizePolicy.Maximum)
        moviesTableSearchHLayout.addWidget(searchText)

        moviesTableSearchBox = QtWidgets.QLineEdit(self)
        moviesTableSearchBox.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Maximum)
        moviesTableSearchBox.setClearButtonEnabled(True)
        moviesTableSearchBox.textChanged.connect(lambda: searchTableView(moviesTableSearchBox, self.moviesTable))
        moviesTableSearchHLayout.addWidget(moviesTableSearchBox)

        moviesWatchlistVSplitter.addWidget(self.moviesTableWidget)

        # Watch List ---------------------------------------------------------------------------------------
        self.watchListWidget = QtWidgets.QWidget()
        watchListVLayout = QtWidgets.QVBoxLayout()
        self.watchListWidget.setLayout(watchListVLayout)

        watchListVLayout.addWidget(QtWidgets.QLabel("Watch List"))

        self.watchListTable = QtWidgets.QTableView()
        self.watchListTable.setSortingEnabled(True)
        self.watchListTable.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.watchListTable.verticalHeader().hide()
        style = "::section {""color: black; }"
        self.watchListTable.horizontalHeader().setStyleSheet(style)
        self.watchListTable.setShowGrid(False)

        self.watchListTable.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.watchListTable.customContextMenuRequested[QtCore.QPoint].connect(self.watchListTableRightMenuShow)

        watchListVLayout.addWidget(self.watchListTable)

        watchListSearchHLayout = QtWidgets.QHBoxLayout()
        watchListVLayout.addLayout(watchListSearchHLayout)

        searchText = QtWidgets.QLabel("Search")
        searchText.setSizePolicy(QtWidgets.QSizePolicy.Maximum,
                                 QtWidgets.QSizePolicy.Maximum)
        watchListSearchHLayout.addWidget(searchText)

        watchListSearchBox = QtWidgets.QLineEdit(self)
        watchListSearchBox.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Maximum)
        watchListSearchBox.setClearButtonEnabled(True)
        watchListSearchBox.textChanged.connect(lambda: searchTableView(watchListSearchBox, self.moviesTable))
        watchListSearchHLayout.addWidget(watchListSearchBox)

        moviesWatchlistVSplitter.addWidget(self.watchListWidget)

        moviesWatchlistVSplitter.setSizes([600, 300])

        # Cover and Summary ---------------------------------------------------------------------------------------
        coverSummaryVSplitter = QtWidgets.QSplitter(QtCore.Qt.Vertical, self)
        coverSummaryVSplitter.setHandleWidth(20)
        coverSummaryVSplitter.splitterMoved.connect(self.resizeCoverFile)

        self.coverWidget = QtWidgets.QWidget()
        self.coverWidget.setStyleSheet("background-color: black;")
        movieVLayout = QtWidgets.QVBoxLayout()
        self.coverWidget.setLayout(movieVLayout)

        # Get a list of available fonts
        # dataBase = QtGui.QFontDatabase()
        # for family in dataBase.families():
        #    print('%s' % family)
        #    for style in dataBase.styles(family):
        #        print('\t%s' % style)

        self.movieTitle = QtWidgets.QLabel('')
        self.movieTitle.setWordWrap(True)
        self.movieTitle.setFont(QtGui.QFont('TimesNew Roman', 20))
        self.movieTitle.setSizePolicy(QtWidgets.QSizePolicy.MinimumExpanding, QtWidgets.QSizePolicy.Fixed)
        self.movieTitle.setStyleSheet("color: white;")
        movieVLayout.addWidget(self.movieTitle)

        self.movieCover = QtWidgets.QLabel(self)
        self.movieCover.setScaledContents(False)
        self.movieCover.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Ignored)

        self.movieCover.setStyleSheet("background-color: black;")

        movieVLayout.addWidget(self.movieCover)

        coverSummaryVSplitter.addWidget(self.coverWidget)

        self.summary = QtWidgets.QTextBrowser()
        self.summary.setFont(QtGui.QFont('TimesNew Roman', 12))
        self.summary.setStyleSheet("color:white; background-color: black;")
        coverSummaryVSplitter.addWidget(self.summary)

        coverSummaryVSplitter.setSizes([600, 200])

        # ---------------------------------------------------------------------------------------

        # Add the sub-layouts to the mainHSplitter
        mainHSplitter.addWidget(self.filterWidget)
        mainHSplitter.addWidget(moviesWatchlistVSplitter)
        mainHSplitter.addWidget(coverSummaryVSplitter)
        mainHSplitter.setSizes([250, 625, 400])

        # Bottom ---------------------------------------------------------------------------------------
        bottomLayout = QtWidgets.QHBoxLayout(self)
        mainVLayout.addLayout(bottomLayout)

        self.progressBar = QtWidgets.QProgressBar(self)
        self.progressBar.setMaximum(100)
        bottomLayout.addWidget(self.progressBar)

        cancelButton = QtWidgets.QPushButton("Cancel", self)
        cancelButton.clicked.connect(self.cancelButtonClicked)
        bottomLayout.addWidget(cancelButton)

    def refresh(self, forceScan=False):
        if not os.path.exists(self.moviesFolder):
            return

        if os.path.exists(self.moviesSmdbFile):
            self.moviesSmdbData = readSmdbFile(self.moviesSmdbFile)
            self.moviesTableModel = MoviesTableModel(self.moviesSmdbData, self.moviesFolder, forceScan)
        else:
            self.moviesTableModel = MoviesTableModel(self.moviesSmdbData, self.moviesFolder, forceScan)
            self.moviesSmdbData = self.writeSmdbFile(self.moviesSmdbFile, self.moviesTableModel)

        self.moviesTableProxyModel = QtCore.QSortFilterProxyModel()
        self.moviesTableProxyModel.setSourceModel(self.moviesTableModel)
        if forceScan:
            # If forScan, sort by exists otherwise title
            self.moviesTableProxyModel.sort(8)
        else:
            self.moviesTableProxyModel.sort(0)

        self.moviesTable.setModel(self.moviesTableProxyModel)
        self.moviesTable.selectionModel().selectionChanged.connect(
            lambda: self.tableSelectionChanged(self.moviesTable, self.moviesTableProxyModel))
        self.moviesTable.doubleClicked.connect(lambda: self.playMovie(self.moviesTable,
                                                                      self.moviesTableProxyModel))
        self.moviesTableProxyModel.setDynamicSortFilter(False)
        self.moviesTable.setWordWrap(False)

        self.moviesTable.setColumnWidth(0, 15)  # year
        self.moviesTable.setColumnWidth(1, 200)  # title
        self.moviesTable.setColumnWidth(2, 60)  # rating
        self.moviesTable.setColumnWidth(3, 150)  # box office
        self.moviesTable.setColumnWidth(4, 60)  # runtime
        self.moviesTable.setColumnWidth(5, 60)  # id
        self.moviesTable.setColumnWidth(6, 200)  # folder
        self.moviesTable.setColumnWidth(7, 300)  # path
        self.moviesTable.setColumnWidth(8, 65)  # json exists
        self.moviesTable.verticalHeader().setMinimumSectionSize(10)
        self.moviesTable.verticalHeader().setDefaultSectionSize(18)
        self.moviesTable.hideColumn(5)
        self.moviesTable.hideColumn(6)
        self.moviesTable.hideColumn(7)
        self.moviesTable.hideColumn(9)

        self.numVisibleMovies = self.moviesTableProxyModel.rowCount()
        self.showMoviesTableSelectionStatus()

        self.populateFiltersTable()

        self.moviesTable.selectRow(0)
        self.tableSelectionChanged(self.moviesTable, self.moviesTableProxyModel)

        # Watch List
        if os.path.exists(self.watchListSmdbFile):
            self.watchListSmdbData = readSmdbFile(self.watchListSmdbFile)
        self.watchListTableModel = MoviesTableModel(self.watchListSmdbData,
                                                    self.moviesFolder,
                                                    False, # force scan
                                                    True) # dont scan the movies folder for the watch list
        self.watchListTableProxyModel = QtCore.QSortFilterProxyModel()
        self.watchListTableProxyModel.setSourceModel(self.watchListTableModel)
        self.watchListTableProxyModel.sort(9)

        self.watchListTable.setModel(self.watchListTableProxyModel)
        self.watchListTable.selectionModel().selectionChanged.connect(
            lambda: self.tableSelectionChanged(self.watchListTable, self.watchListTableProxyModel))
        self.watchListTable.doubleClicked.connect(lambda: self.playMovie(self.watchListTable,
                                                                         self.watchListTableProxyModel))
        self.watchListTableProxyModel.setDynamicSortFilter(False)
        self.watchListTable.setWordWrap(False)

        self.watchListTable.setColumnWidth(0, 15)  # year
        self.watchListTable.setColumnWidth(1, 200)  # title
        self.watchListTable.setColumnWidth(2, 60)  # rating
        self.watchListTable.setColumnWidth(3, 150)  # box office
        self.watchListTable.setColumnWidth(4, 60)  # runtime
        self.watchListTable.setColumnWidth(5, 60)  # id
        self.watchListTable.setColumnWidth(6, 200)  # folder
        self.watchListTable.setColumnWidth(7, 300)  # path
        self.watchListTable.setColumnWidth(9, 40)  # rank
        self.watchListTable.verticalHeader().setMinimumSectionSize(10)
        self.watchListTable.verticalHeader().setDefaultSectionSize(18)
        self.watchListTable.hideColumn(3)
        self.watchListTable.hideColumn(4)
        self.watchListTable.hideColumn(5)
        self.watchListTable.hideColumn(6)
        self.watchListTable.hideColumn(7)
        self.watchListTable.hideColumn(8)

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
            self.settings.setValue('movies_folder', self.moviesFolder)
            print("Saved: moviesFolder = %s" % self.moviesFolder)
            readSmdbFile()
            self.moviesSmdbFile = os.path.join(self.moviesFolder, "smdb_data.json")
            self.refresh()

    def populateFiltersTable(self):
        if not self.moviesSmdbData:
            print("Error: No smbdData")
            return

        filterByText = self.filterByComboBox.currentText()
        filterByKey = self.filterByDict[filterByText]

        if filterByText == 'Director' or filterByText == 'Actor':
            self.filterTable.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
            self.filterTable.customContextMenuRequested[QtCore.QPoint].connect(
                self.filterRightMenuShowPeople)
        elif filterByText == 'Year':
            self.filterTable.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
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
        numRows = len(self.moviesSmdbData[filterByKey].keys())
        self.filterTable.setRowCount(numRows)
        self.filterTable.setSortingEnabled(False)
        for name in self.moviesSmdbData[filterByKey].keys():
            count = self.moviesSmdbData[filterByKey][name]['num movies']
            nameItem = QtWidgets.QTableWidgetItem(name)
            self.filterTable.setItem(row, 0, nameItem)
            countItem = QtWidgets.QTableWidgetItem('%04d' % count)
            self.filterTable.setItem(row, 1, countItem)
            row += 1
            progress += 1
            self.progressBar.setValue(progress)

        self.filterTable.sortItems(1, QtCore.Qt.DescendingOrder)
        self.filterTable.setSortingEnabled(True)

        self.progressBar.setValue(0)

    def cancelButtonClicked(self):
        self.isCanceled = True

    def showMoviesTableSelectionStatus(self):
        numSelected = len(self.moviesTable.selectionModel().selectedRows())
        self.statusBar().showMessage('%s/%s' % (numSelected, self.numVisibleMovies))

    def tableSelectionChanged(self, table, proxyModel):
        self.showMoviesTableSelectionStatus()
        numSelected = len(table.selectionModel().selectedRows())
        if numSelected == 1:
            self.clickedMovieTable(table.selectionModel().selectedRows()[0], proxyModel)

    def clickedMovieTable(self, modelIndex, proxyModel):
        title = proxyModel.index(modelIndex.row(), 1).data(QtCore.Qt.DisplayRole)
        try:
            moviePath = proxyModel.index(modelIndex.row(), 7).data(QtCore.Qt.DisplayRole)
            folderName = proxyModel.index(modelIndex.row(), 6).data(QtCore.Qt.DisplayRole)
            year = proxyModel.index(modelIndex.row(), 0).data(QtCore.Qt.DisplayRole)
            jsonFile = os.path.join(moviePath, '%s.json' % folderName)
            coverFile = os.path.join(moviePath, '%s.jpg' % folderName)
            if not os.path.exists(coverFile):
                coverFilePng = os.path.join(moviePath, '%s.png' % folderName)
                if os.path.exists(coverFilePng):
                    coverFile = coverFilePng

            self.movieTitle.setText('%s (%s)' % (title, year))
            self.showCoverFile(coverFile)
            self.showMovieInfo(jsonFile)
        except:
            print("Error with movie %s" % title)

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
        if self.movieCover:
            self.showCover = not self.showCover
            if not self.showCover:
                self.coverWidget.hide()
            else:
                self.coverWidget.show()

    def showSummaryMenu(self):
        if self.summary:
            self.showSummary = not self.showSummary
            if not self.showSummary:
                self.summary.hide()
            else:
                self.summary.show()

    def filterTableSelectionChanged(self):
        if len(self.filterTable.selectedItems()) == 0:
            self.numVisibleMovies = self.moviesTableProxyModel.rowCount()
            self.showMoviesTableSelectionStatus()
            for row in range(self.moviesTableProxyModel.rowCount()):
                self.moviesTable.setRowHidden(row, False)
            return

        filterByText = self.filterByComboBox.currentText()
        filterByKey = self.filterByDict[filterByText]

        movieList = []
        for item in self.filterTable.selectedItems():
            row = item.row()
            name = self.filterTable.item(row, 0).text()
            movies = self.moviesSmdbData[filterByKey][name]['movies']
            for movie in movies:
                movieList.append(movie)

        for row in range(self.moviesTableProxyModel.rowCount()):
            self.moviesTable.setRowHidden(row, True)

        # Movies are stored as ['Anchorman: The Legend of Ron Burgundy', 2004]
        self.progressBar.setMaximum(len(movieList))

        progress = 0
        firstRow = -1
        self.numVisibleMovies = 0
        for row in range(self.moviesTableProxyModel.rowCount()):
            title = self.moviesTableProxyModel.index(row, 1).data(QtCore.Qt.DisplayRole)
            year = self.moviesTableProxyModel.index(row, 0).data(QtCore.Qt.DisplayRole)
            for (t, y) in movieList:
                if t == title and y == year:
                    self.numVisibleMovies += 1
                    if firstRow == -1:
                        firstRow = row
                    self.moviesTable.setRowHidden(row, False)
            progress += 1
            self.progressBar.setValue(progress)

        self.moviesTable.selectRow(firstRow)
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

    def showMovieInfo(self, jsonFile):
        if os.path.exists(jsonFile):
            with open(jsonFile) as f:
                try:
                    data = json.load(f)
                    infoText = ''
                    if 'director' in data and data['director']:
                        infoText += 'Directed by: %s<br>' % data['director'][0]
                    if 'rating' in data and data['rating']:
                        infoText += '<br>Rating: %s<br>' % data['rating']
                    if 'runtime' in data and data['runtime']:
                        infoText += 'Runtime: %s minutes<br>' % data['runtime']
                    if 'genres' in data and data['genres']:
                        infoText += 'Genres: '
                        for genre in data['genres']:
                            infoText += '%s, ' % genre
                        infoText += '<br>'
                    if 'box office' in data and data['box office']:
                        infoText += 'Box Office: %s<br>' % data['box office']
                    if 'cast' in data and data['cast']:
                        infoText += '<br>Cast:<br>'
                        for c in data['cast']:
                            infoText += '%s<br>' % c
                    if 'plot' in data and data['plot']:
                        infoText += '<br>Plot:<br>'
                        plot = ''
                        if isinstance(data['plot'], list):
                            plot = data['plot'][0]
                        else:
                            plot = data['plot']
                        # Remove the author of the plot's name
                        plot = plot.split('::')[0]
                        infoText += '%s<br>' % plot
                    if 'synopsis' in data and data['synopsis']:
                        infoText += '<br>Synopsis:<br>'
                        synopsis = ''
                        if isinstance(data['synopsis'], list):
                            synopsis = data['synopsis'][0]
                        else:
                            synopsis = data['synopsis']
                        # Remove the author of the synopsis's name
                        synopsis = synopsis.split('::')[0]
                        infoText += '%s<br>' % synopsis
                    # infoText = '<span style=\" color: #ffffff; font-size: 8pt\">%s</span>' % infoText
                    self.summary.setText(infoText)
                except UnicodeDecodeError:
                    print("Error reading %s" % jsonFile)
        else:
            self.summary.clear()

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

            title = model.index(row, 1).data(QtCore.Qt.DisplayRole)

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

                    if 'countries' in jsonData and jsonData['countries']:
                        jsonCompanies = jsonData['countries']
                        for country in jsonCompanies:
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
        moviePath = self.moviesTableProxyModel.index(modelIndex.row(), 7).data(QtCore.Qt.DisplayRole)
        movieFolderName = self.moviesTableProxyModel.index(modelIndex.row(), 6).data(QtCore.Qt.DisplayRole)
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
            proxyIndex = self.moviesTableProxyModel.index(modelIndex.row(), 0)
            sourceIndex = self.moviesTableProxyModel.mapToSource(proxyIndex)
            self.moviesTableModel.setMovieDataWithJson(sourceIndex.row(),
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
        self.peopleRightMenu = QtWidgets.QMenu(self.filterTable)
        selectedItem = self.filterTable.selectedItems()[0]
        row = selectedItem.row()
        self.openImdbAction = QtWidgets.QAction("Open IMDB Page", self)
        personName = self.filterTable.item(row, 0).text()
        self.openImdbAction.triggered.connect(lambda: self.openPersonImdbPage(personName))
        self.peopleRightMenu.addAction(self.openImdbAction)
        self.peopleRightMenu.exec_(QtGui.QCursor.pos())

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
        openImdbAction.triggered.connect(lambda: self.openYearImdbPage(year))
        rightMenu.addAction(openImdbAction)
        rightMenu.exec_(QtGui.QCursor.pos())

    def openYearImdbPage(self, year):
        webbrowser.open('https://www.imdb.com/search/title/?release_date=%s-01-01,%s-12-31' % (year, year), new=2)

    def watchListTableRightMenuShow(self, QPos):
        rightMenu = QtWidgets.QMenu(self.moviesTable)

        playAction = QtWidgets.QAction("Play", self)
        playAction.triggered.connect(lambda: self.playMovie(self.watchListTable,
                                                            self.watchListTableProxyModel))
        rightMenu.addAction(playAction)

        removeFromWatchListAction = QtWidgets.QAction("Remove From Watch List", self)
        removeFromWatchListAction.triggered.connect(self.removeFromWatchList)
        rightMenu.addAction(removeFromWatchListAction)

        self.clickedMovieTable(self.watchListTable.selectionModel().selectedRows()[0],
                               self.watchListTableProxyModel)

        rightMenu.exec_(QtGui.QCursor.pos())

    def moviesTableRightMenuShow(self, QPos):
        self.rightMenu = QtWidgets.QMenu(self.moviesTable)

        self.clickedMovieTable(self.moviesTable.selectionModel().selectedRows()[0],
                               self.moviesTableProxyModel)

        self.playAction = QtWidgets.QAction("Play", self)
        self.playAction.triggered.connect(lambda: self.playMovie(self.moviesTable,
                                                                 self.moviesTableProxyModel))
        self.rightMenu.addAction(self.playAction)

        self.addToWatchListAction = QtWidgets.QAction("Add To Watch List", self)
        self.addToWatchListAction.triggered.connect(self.addToWatchList)
        self.rightMenu.addAction(self.addToWatchListAction)

        self.openFolderAction = QtWidgets.QAction("Open Folder", self)
        self.openFolderAction.triggered.connect(self.openMovieFolder)
        self.rightMenu.addAction(self.openFolderAction)

        self.openJsonAction = QtWidgets.QAction("Open Json File", self)
        self.openJsonAction.triggered.connect(self.openMovieJson)
        self.rightMenu.addAction(self.openJsonAction)

        self.openImdbAction = QtWidgets.QAction("Open IMDB Page", self)
        self.openImdbAction.triggered.connect(self.openMovieImdbPage)
        self.rightMenu.addAction(self.openImdbAction)

        self.overrideImdbAction = QtWidgets.QAction("Override IMDB ID", self)
        self.overrideImdbAction.triggered.connect(self.overrideID)
        self.rightMenu.addAction(self.overrideImdbAction)

        self.downloadDataAction = QtWidgets.QAction("Download Data", self)
        self.downloadDataAction.triggered.connect(self.downloadDataMenu)
        self.rightMenu.addAction(self.downloadDataAction)

        self.downloadDataAction = QtWidgets.QAction("Force Download Data", self)
        self.downloadDataAction.triggered.connect(lambda: self.downloadDataMenu(force=True))
        self.rightMenu.addAction(self.downloadDataAction)

        self.downloadDataAction = QtWidgets.QAction("Force Download Json only", self)
        self.downloadDataAction.triggered.connect(lambda: self.downloadDataMenu(force=True, doJson=True, doCover=False))
        self.rightMenu.addAction(self.downloadDataAction)

        self.downloadDataAction = QtWidgets.QAction("Force Download Cover only", self)
        self.downloadDataAction.triggered.connect(lambda: self.downloadDataMenu(force=True, doJson=False, doCover=True))
        self.rightMenu.addAction(self.downloadDataAction)

        self.removeJsonFilesAction = QtWidgets.QAction("Remove .json files", self)
        self.removeJsonFilesAction.triggered.connect(self.removeJsonFilesMenu)
        self.rightMenu.addAction(self.removeJsonFilesAction)

        self.removeCoversAction = QtWidgets.QAction("Remove cover files", self)
        self.removeCoversAction.triggered.connect(self.removeCoverFilesMenu)
        self.rightMenu.addAction(self.removeCoversAction)

        self.rightMenu.exec_(QtGui.QCursor.pos())

    def playMovie(self, table, proxy):
        modelIndex = table.selectionModel().selectedRows()[0]
        moviePath = proxy.index(modelIndex.row(), 7).data(QtCore.Qt.DisplayRole)
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
        for modelIndex in self.moviesTable.selectionModel().selectedRows():
            movieFolderName = self.moviesTableProxyModel.index(modelIndex.row(), 6).data(QtCore.Qt.DisplayRole)
            moviePath = self.moviesTableProxyModel.index(modelIndex.row(), 7).data(QtCore.Qt.DisplayRole)
            self.watchListTableModel.addMovie(self.moviesSmdbData,
                                              moviePath,
                                              movieFolderName)
        self.writeSmdbFile(self.watchListSmdbFile,
                           self.watchListTableModel,
                           titlesOnly=True)

    def removeFromWatchList(self):
        selectedRows = self.watchListTable.selectionModel().selectedRows()
        minRow = selectedRows[0].row()
        maxRow = selectedRows[-1].row()
        self.watchListTableModel.removeMovies(minRow, maxRow)
        self.watchListTable.selectionModel().clearSelection()
        self.writeSmdbFile(self.watchListSmdbFile,
                           self.watchListTableModel,
                           titlesOnly=True)

    def openMovieFolder(self):
        modelIndex = self.moviesTable.selectionModel().selectedRows()[0]
        moviePath = self.moviesTableProxyModel.index(modelIndex.row(), 7).data(QtCore.Qt.DisplayRole)
        if os.path.exists(moviePath):
            runFile(moviePath)
        else:
            print("Folder doesn't exist")

    def openMovieJson(self):
        modelIndex = self.moviesTable.selectionModel().selectedRows()[0]
        moviePath = self.moviesTableProxyModel.index(modelIndex.row(), 7).data(QtCore.Qt.DisplayRole)
        folderName = self.moviesTableProxyModel.index(modelIndex.row(), 6).data(QtCore.Qt.DisplayRole)
        jsonFile = os.path.join(moviePath, '%s.json' % folderName)
        if os.path.exists(jsonFile):
            runFile(jsonFile)
        else:
            print("jsonFile: %s doesn't exist" % jsonFile)

    def openMovieImdbPage(self):
        modelIndex = self.moviesTable.selectionModel().selectedRows()[0]
        movieId = self.moviesTableProxyModel.index(modelIndex.row(), 5).data(QtCore.Qt.DisplayRole)
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
            modelIndex = self.moviesTable.selectionModel().selectedRows()[0]
            self.downloadMovieData(modelIndex, True, movieId)

    def downloadDataMenu(self, force=False, doJson=True, doCover=True):
        numSelectedItems = len(self.moviesTable.selectionModel().selectedRows())
        self.progressBar.setMaximum(numSelectedItems)
        progress = 0
        self.isCanceled = False
        for modelIndex in self.moviesTable.selectionModel().selectedRows():
            QtCore.QCoreApplication.processEvents()
            if self.isCanceled == True:
                self.statusBar().showMessage('Cancelled')
                self.isCanceled = False
                self.progressBar.setValue(0)
                self.setMovieListItemColors()
                return

            title = self.moviesTableProxyModel.index(modelIndex.row(), 1).data(QtCore.Qt.DisplayRole)
            message = "Downloading data (%d/%d): %s" % (progress + 1,
                                                        numSelectedItems,
                                                        title)
            self.statusBar().showMessage(message)
            QtCore.QCoreApplication.processEvents()

            self.downloadMovieData(modelIndex, force, doJson=doJson, doCover=doCover)
            self.moviesTable.selectRow(modelIndex.row())
            self.clickedMovieTable(modelIndex, self.moviesTableProxyModel)

            progress += 1
            self.progressBar.setValue(progress)
        self.statusBar().showMessage("Done")
        self.progressBar.setValue(0)

    def removeJsonFilesMenu(self):
        filesToDelete = []
        for modelIndex in self.moviesTable.selectionModel().selectedRows():
            moviePath = self.moviesTableProxyModel.index(modelIndex.row(), 7).data(QtCore.Qt.DisplayRole)
            movieFolder = self.moviesTableProxyModel.index(modelIndex.row(), 6).data(QtCore.Qt.DisplayRole)
            jsonFile = os.path.join(moviePath, '%s.json' % movieFolder)
            if (os.path.exists(jsonFile)):
                filesToDelete.append(os.path.join(moviePath, jsonFile))
        removeFiles(self, filesToDelete, '.json')
        # self.setMovieListItemColors()

    def removeCoverFilesMenu(self):
        filesToDelete = []
        for modelIndex in self.moviesTable.selectionModel().selectedRows():
            moviePath = self.moviesTableProxyModel.index(modelIndex.row(), 7).data(QtCore.Qt.DisplayRole)
            movieFolder = self.moviesTableProxyModel.index(modelIndex.row(), 6).data(QtCore.Qt.DisplayRole)

            coverFile = os.path.join(moviePath, '%s.jpg' % movieFolder)
            if os.path.exists(coverFile):
                filesToDelete.append(coverFile)
            else:
                coverFile = os.path.join(moviePath, '%s.png' % movieFolder)
                if os.path.exists(coverFile):
                    filesToDelete.append(coverFile)

        removeFiles(self, filesToDelete, '.jpg')