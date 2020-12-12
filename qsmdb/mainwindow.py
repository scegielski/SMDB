from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtWidgets import QApplication, QMessageBox
import sys
import os
from pathlib import Path
import fnmatch
import imdb
from imdb import IMDb
from imdb import Movie
import re
import urllib.request
import subprocess
import json
import collections
from enum import Enum, auto
import webbrowser

from .utilities import *
from .moviemodel import MoviesTableModel

class displayStyles(Enum):
    TOTAL_ITEM = auto(),
    ITEM_TOTAL = auto(),
    YEAR_TITLE = auto(),
    RATING_TITLE_YEAR = auto(),
    TITLE_YEAR = auto(),
    BOX_OFFICE_YEAR_TITLE = auto(),
    RUNTIME_YEAR_TITLE = auto(),
    FOLDER = auto()

# TODO: Create separate derived class for movie list and move methods
# TODO: Change colors to dark

def copyCoverImage(movie, coverFile):
    if movie.has_key('full-size cover url'):
        movieCoverUrl = movie['full-size cover url']
    elif movie.has_key('cover'):
        movieCoverUrl = movie['cover']
    else:
        print("Error: No cover image available")
        return ""
    extension = os.path.splitext(movieCoverUrl)[1]
    if extension == '.png':
        coverFile = coverFile.replace('.jpg', '.png')
    try:
        urllib.request.urlretrieve(movieCoverUrl, coverFile)
    except:
        print("Problem downloading cover file: %s" % coverFile)
    return coverFile

def runFile(file):
    if sys.platform == "win32":
        os.startfile(file)
    else:
        opener = "open" if sys.platform == "darwin" else "xdg-open"
        subprocess.call([opener, file])


def removeFiles(parent, filesToDelete, extension):
    if len(filesToDelete) > 0:
        ret = QMessageBox.question(parent,
                                   'Confirm Delete',
                                   'Really remove %d %s files?' % (len(filesToDelete), extension),
                                   QMessageBox.Yes | QMessageBox.No,
                                   QMessageBox.No)

        if ret == QMessageBox.Yes:
            for f in filesToDelete:
                print('Deleting file: %s' % f)
                os.remove(f)



def searchListWidget(searchBoxWidget, listWidget):
    searchText = searchBoxWidget.text()
    if searchText == "":
        for row in range(listWidget.count()):
            listWidget.item(row).setHidden(False)
    else:
        for row in range(listWidget.count()):
            listWidget.item(row).setHidden(True)
        for foundItem in listWidget.findItems(searchText, QtCore.Qt.MatchContains):
            foundItem.setHidden(False)

def searchTableWidget(searchBoxWidget, tableWidget):
    searchText = searchBoxWidget.text()
    if searchText == "":
        for row in range(tableWidget.rowCount()):
            tableWidget.showRow(row)
    else:
        for row in range(tableWidget.rowCount()):
            tableWidget.hideRow(row)
        for foundItem in tableWidget.findItems(searchText, QtCore.Qt.MatchContains):
            tableWidget.showRow(foundItem.row())

def searchTableView(searchBoxWidget, tableView):
    searchText = searchBoxWidget.text()
    proxyModel = tableView.model()
    proxyModel.setFilterKeyColumn(1)
    proxyModel.setFilterRegExp(QtCore.QRegExp(searchText,
                                              QtCore.Qt.CaseInsensitive,
                                              QtCore.QRegExp.FixedString))

    for row in range(proxyModel.rowCount(tableView.rootIndex())):
        tableView.verticalHeader().resizeSection(row, 18)

class MyWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super(MyWindow, self).__init__()
        self.movieCover = None
        self.movieList = None
        self.setGeometry(200, 75, 1275, 700)
        self.setWindowTitle("Scott's Movie Database")
        self.numVisibleMovies = 0
        self.moviesTableWidget = None
        self.filterWidget = None
        self.showFilters = True
        self.showMoviesTable = True
        self.showCover = True
        self.showSummary = True
        self.showWatchList = True

        self.db = IMDb()

        self.settings = QtCore.QSettings("STC", "SMDB")
        self.moviesFolder = self.settings.value('movies_folder', "J:/Movies", type=str)

        self.smdbFile = os.path.join(self.moviesFolder, "smdb_data.json")
        self.smdbData = None

        self.watchListFile = os.path.join(self.moviesFolder, "smdb_data_watch_list.json")
        self.watchListSmdbData = None

        self.initUI()

        if not os.path.exists(self.moviesFolder):
            return

    def readSmdbFile(self, fileName):
        if os.path.exists(fileName):
            with open(fileName) as f:
                return json.load(f)

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
            self.readSmdbFile()
            self.smdbFile = os.path.join(self.moviesFolder, "smdb_data.json")
            self.refresh()

    def initUI(self):
        menuBar = self.menuBar()

        # File Menu ---------------------------------------------------------------------------------------
        fileMenu = menuBar.addMenu('File')

        rebuildSmdbFileAction = QtWidgets.QAction("Rebuild SMDB file", self)
        rebuildSmdbFileAction.triggered.connect(lambda: self.writeSmdbFile(self.smdbFile, self.moviesTableModel))
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
        #centralWidget.setStyleSheet("background-color: black;")

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

        self.filterByDict = {
            'Director': 'directors',
            'Actor': 'actors',
            'Genre': 'genres',
            'Year': 'years',
            'Company': 'companies',
            'Country': 'countries'
        }

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
        self.moviesTable.doubleClicked.connect(self.playMovie)
        style = "::section {""color: black; }"
        self.moviesTable.horizontalHeader().setStyleSheet(style)
        self.moviesTable.setShowGrid(False)
        # TODO: Need to find a better way to set the alternating colors
        # Setting alternate colors to true makes them black and white.
        # Changing the color using a stylesheet looks better but makes
        # the right click menu background also black.
        #self.moviesTable.setAlternatingRowColors(True)
        #self.moviesTable.setStyleSheet("alternate-background-color: #151515;background-color: black;");
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
        self.watchListTable.doubleClicked.connect(self.playMovie)
        style = "::section {""color: black; }"
        self.watchListTable.horizontalHeader().setStyleSheet(style)
        self.watchListTable.setShowGrid(False)
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

        moviesWatchlistVSplitter.setSizes([600, 200])

        # Cover and Summary ---------------------------------------------------------------------------------------
        coverSummaryVSplitter = QtWidgets.QSplitter(QtCore.Qt.Vertical, self)
        coverSummaryVSplitter.setHandleWidth(20)
        coverSummaryVSplitter.splitterMoved.connect(self.resizeCoverFile)

        self.coverWidget = QtWidgets.QWidget()
        self.coverWidget.setStyleSheet("background-color: black;")
        movieVLayout = QtWidgets.QVBoxLayout()
        self.coverWidget.setLayout(movieVLayout)

        # Get a list of available fonts
        #dataBase = QtGui.QFontDatabase()
        #for family in dataBase.families():
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

    def populateFiltersTable(self):
        if not self.smdbData:
            print("Error: No smbdData")
            return

        filterByText = self.filterByComboBox.currentText()
        filterByKey = self.filterByDict[filterByText]

        if filterByKey not in self.smdbData:
            print("Error: '%s' not in smdbData" % filterByKey)
            return

        numEntries = len(self.smdbData[filterByKey].keys())
        message = "Populating list: %s with %s entries" % (filterByKey, numEntries)
        self.statusBar().showMessage(message)
        QtCore.QCoreApplication.processEvents()

        self.progressBar.setMaximum(len(self.smdbData[filterByKey].keys()))
        progress = 0

        self.filterTable.clear()
        self.filterTable.setHorizontalHeaderLabels(['Name', 'Count'])

        row = 0
        numRows = len(self.smdbData[filterByKey].keys())
        self.filterTable.setRowCount(numRows)
        self.filterTable.setSortingEnabled(False)
        for name in self.smdbData[filterByKey].keys():
            count = self.smdbData[filterByKey][name]['num movies']
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

    def moviesTableSelectionChanged(self):
        self.showMoviesTableSelectionStatus()
        numSelected = len(self.moviesTable.selectionModel().selectedRows())
        if numSelected == 1:
            self.clickedMovieTable(self.moviesTable.selectionModel().selectedRows()[0])

    def clickedMovieTable(self, modelIndex):
        title = self.moviesTableProxyModel.index(modelIndex.row(), 1).data(QtCore.Qt.DisplayRole)
        proxyIndex = self.moviesTableProxyModel.index(modelIndex.row(), 1)
        try:
            moviePath = self.moviesTableProxyModel.index(modelIndex.row(), 7).data(QtCore.Qt.DisplayRole)
            folderName = self.moviesTableProxyModel.index(modelIndex.row(), 6).data(QtCore.Qt.DisplayRole)
            year = self.moviesTableProxyModel.index(modelIndex.row(), 0).data(QtCore.Qt.DisplayRole)
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

        movieList = []
        for item in self.filterTable.selectedItems():
            row = item.row()
            name = self.filterTable.item(row, 0).text()
            movies = self.smdbData[filterByKey][name]['movies']
            for movie in movies:
                movieList.append(movie)

        for row in range(self.moviesTableProxyModel.rowCount()):
            self.moviesTable.setRowHidden(row, True)

        # Movies are stored as ['Anchorman: The Legend of Ron Burgundy', 2004]
        self.progressBar.setMaximum(len(movieList))
        progress = 0

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
            self.movieCover.setPixmap(QtGui.QPixmap(0,0))

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
                    #infoText = '<span style=\" color: #ffffff; font-size: 8pt\">%s</span>' % infoText
                    self.summary.setText(infoText)
                except UnicodeDecodeError:
                    print("Error reading %s" % jsonFile)
        else:
            self.summary.clear()

    def getMovieKey(self, movie, key):
        if movie.has_key(key):
            return movie[key]
        else:
            return None

    def writeMovieJson(self, movie, jsonFile):
        d = {}
        d['title'] = self.getMovieKey(movie, 'title')
        d['id'] = movie.getID()
        d['kind'] = self.getMovieKey(movie, 'kind')
        d['year'] = self.getMovieKey(movie, 'year')
        d['rating'] = self.getMovieKey(movie, 'rating')

        d['countries'] = []
        countries = self.getMovieKey(movie, 'countries')
        if countries and isinstance(countries, list):
            for c in countries:
                d['countries'].append(c)
        d['companies'] = []
        companies = self.getMovieKey(movie, 'production companies')
        if companies and isinstance(companies, list):
            for c in companies:
                d['companies'].append(c['name'])
        runtimes = self.getMovieKey(movie, 'runtimes')
        if runtimes:
            d['runtime'] = runtimes[0]
        boxOffice = self.getMovieKey(movie, 'box office')
        if boxOffice:
            for k in boxOffice.keys():
                d['box office'] = boxOffice[k]
        director = self.getMovieKey(movie, 'director')
        if (director):
            if isinstance(director, list):
                directorName = str(director[0]['name'])
                directorId = self.db.name2imdbID(directorName)
                d['director'] = [directorName, directorId]
        d['cast'] = []
        cast = self.getMovieKey(movie, 'cast')
        if cast and isinstance(cast, list):
            for c in movie['cast']:
                d['cast'].append(c['name'])
        d['genres'] = self.getMovieKey(movie, 'genres')
        d['plot'] = self.getMovieKey(movie, 'plot')
        d['plot outline'] = self.getMovieKey(movie, 'plot outline')
        d['synopsis'] = self.getMovieKey(movie, 'synopsis')
        d['summary'] = movie.summary()
        d['cover url'] = self.getMovieKey(movie, 'cover url')
        d['full-size cover url'] = self.getMovieKey(movie, 'full-size cover url')

        try:
            with open(jsonFile, "w") as f:
                json.dump(d, f, indent=4)
        except:
            print("Error writing json file: %s" % jsonFile)

    def writeSmdbFile(self, fileName, model):
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

            moviePath = model.index(row, 7).data(QtCore.Qt.DisplayRole)
            folderName = model.index(row, 6).data(QtCore.Qt.DisplayRole)
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
                        if not jsonYear in years:
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

                    titles[folderName] = { 'id': jsonId,
                                           'title': jsonTitle,
                                           'year': jsonYear,
                                           'rating': jsonRating,
                                           'runtime': jsonRuntime,
                                           'box office': jsonBoxOffice,
                                           'director': directorName,
                                           'genres': jsonGenres,
                                           'actors': movieActorsList }

            progress += 1
            self.progressBar.setValue(progress)

        self.progressBar.setValue(0)

        self.statusBar().showMessage('Sorting Data...')
        QtCore.QCoreApplication.processEvents()

        data = {}
        data['titles'] = collections.OrderedDict(sorted(titles.items()))
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
        rightMenu = QtWidgets.QMenu(self.filterTable)
        selectedItem = self.filterTable.selectedItems()[0]
        row = selectedItem.row()
        personName = self.filterTable.item(row, 0).text()
        openImdbAction = QtWidgets.QAction("Open IMDB Page", self)
        openImdbAction.triggered.connect(lambda: self.openPersonImdbPage(personName))
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

    def moviesTableRightMenuShow(self, QPos):
        self.rightMenu = QtWidgets.QMenu(self.moviesTable)

        self.clickedMovieTable(self.moviesTable.selectionModel().selectedRows()[0])

        self.playAction = QtWidgets.QAction("Play", self)
        self.playAction.triggered.connect(self.playMovie)
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

        self.removeMdbAction = QtWidgets.QAction("Remove .json files", self)
        self.removeMdbAction.triggered.connect(self.removeJsonFilesMenu)
        self.rightMenu.addAction(self.removeMdbAction)

        self.removeCoversAction = QtWidgets.QAction("Remove cover files", self)
        self.removeCoversAction.triggered.connect(self.removeCoverFilesMenu)
        self.rightMenu.addAction(self.removeCoversAction)

        self.rightMenu.exec_(QtGui.QCursor.pos())

    def playMovie(self):
        modelIndex = self.moviesTable.selectionModel().selectedRows()[0]
        moviePath = self.moviesTableProxyModel.index(modelIndex.row(), 7).data(QtCore.Qt.DisplayRole)
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
        modelIndex = self.moviesTable.selectionModel().selectedRows()[0]
        movieName = self.moviesTableProxyModel.index(modelIndex.row(), 1).data(QtCore.Qt.DisplayRole)
        print ("Adding movie: %s to watch list" % movieName)

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
            self.clickedMovieTable(modelIndex)

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
        #self.setMovieListItemColors()

    def removeCoverFilesMenu(self):
        filesToDelete = []
        for modelIndex in self.moviesTable.selectionModel().selectedRows():
            moviePath = self.moviesTableProxyModel.index(modelIndex.row(), 7).data(QtCore.Qt.DisplayRole)
            movieFolder = self.moviesTableProxyModel.index(modelIndex.row(), 6).data(QtCore.Qt.DisplayRole)

            coverFile = os.path.join(moviePath, '%s.jpg' % movieFolder)
            if os.path.exists(coverFile):
                filesToDelete.append(coverFile)
            else:
                coverFile = os.path.join(moviePath, '%s.png' % item.text())
                if os.path.exists(coverFile):
                    filesToDelete.append(coverFile)

        removeFiles(self, filesToDelete, '.jpg')

    def refresh(self, forceScan=False):
        if not os.path.exists(self.moviesFolder):
            return

        if os.path.exists(self.smdbFile):
            self.smdbData = self.readSmdbFile(self.smdbFile)
            self.moviesTableModel = MoviesTableModel(self.smdbData, self.moviesFolder, forceScan)
        else:
            self.moviesTableModel = MoviesTableModel(self.smdbData, self.moviesFolder, forceScan)
            self.smdbData = self.writeSmdbFile(self.smdbFile, self.moviesTableModel)

        self.moviesTableProxyModel = QtCore.QSortFilterProxyModel()
        self.moviesTableProxyModel.setSourceModel(self.moviesTableModel)
        if forceScan:
            # If forScan, sort by exists otherwise title
            self.moviesTableProxyModel.sort(8)
        else:
            self.moviesTableProxyModel.sort(0)

        self.moviesTable.setModel(self.moviesTableProxyModel)
        self.moviesTable.selectionModel().selectionChanged.connect(lambda: self.moviesTableSelectionChanged())
        self.moviesTableProxyModel.setDynamicSortFilter(False)
        self.moviesTable.setColumnWidth(0, 15)  # year
        self.moviesTable.setColumnWidth(1, 200) # title
        self.moviesTable.setColumnWidth(2, 60)  # rating
        self.moviesTable.setColumnWidth(3, 150) # box office
        self.moviesTable.setColumnWidth(4, 60) # runtime
        self.moviesTable.setColumnWidth(5, 60) # id
        self.moviesTable.setColumnWidth(6, 200) # folder
        self.moviesTable.setColumnWidth(7, 300) # path
        self.moviesTable.setColumnWidth(8, 65) # json exists
        self.moviesTable.verticalHeader().setMinimumSectionSize(10)
        self.moviesTable.verticalHeader().setDefaultSectionSize(18)
        self.moviesTable.setWordWrap(False)
        self.moviesTable.hideColumn(5)
        self.moviesTable.hideColumn(6)
        self.moviesTable.hideColumn(7)

        self.numVisibleMovies = self.moviesTableProxyModel.rowCount()
        self.showMoviesTableSelectionStatus()

        self.populateFiltersTable()

        self.moviesTable.selectRow(0)
        self.moviesTableSelectionChanged()
