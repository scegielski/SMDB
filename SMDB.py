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

class displayStyles(Enum):
    TOTAL_ITEM = auto(),
    ITEM_TOTAL = auto(),
    YEAR_TITLE = auto(),
    RATING_TITLE_YEAR = auto(),
    TITLE_YEAR = auto(),
    FOLDER = auto()

# TODO: Create separate derived class for movie list and move methods
# TODO: Change colors to dark

def splitCamelCase(inputText):
    return re.sub('([A-Z][a-z]+)', r' \1', re.sub('([A-Z]+)', r' \1', inputText)).split()

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
    urllib.request.urlretrieve(movieCoverUrl, coverFile)
    return coverFile

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

def getNiceTitleAndYear(folderName):
    m = re.match(r'(.*)\((.*)\)', folderName)
    title = m.group(1)
    year = m.group(2)
    splitTitle = splitCamelCase(title)
    if splitTitle[0] == 'The':
        splitTitle.pop(0)
        splitTitle.append(', The')
    niceTitle = ' '.join(splitTitle)
    return niceTitle, year

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


class MyWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super(MyWindow, self).__init__()
        self.setGeometry(210, 75, 1500, 900)
        self.setWindowTitle("Scott's Movie Database")

        self.db = IMDb()

        self.moviesFolder = "J:/Movies"
        self.configFile = os.path.join("smdb_config.json")

        self.readConfigFile()
        if not os.path.exists(self.moviesFolder):
            return
        self.smdbFile = os.path.join(self.moviesFolder, "smdb_data.json")

        self.initUI()
        self.refresh()


    def closeEvent(self, event):
        self.saveConfig()

    def refresh(self):
        self.populateMovieList()
        if not os.path.exists(self.smdbFile):
            self.writeSmdbFile()
        self.readSmdbFile()
        self.populateCriteriaList('directors', self.directorsList)
        self.populateCriteriaList('actors', self.actorsList)
        self.populateCriteriaList('genres', self.genresList)
        self.populateCriteriaList('years', self.yearsList)
        self.listDisplayStyleChanged(self.directorsComboBox, self.directorsList)
        self.listDisplayStyleChanged(self.actorsComboBox, self.actorsList)
        self.listDisplayStyleChanged(self.genresComboBox, self.genresList)
        self.listDisplayStyleChanged(self.yearsComboBox, self.yearsList)

    def readConfigFile(self):
        if not os.path.exists(self.configFile):
            return

        with open(self.configFile) as f:
            configData = json.load(f)

        if 'movies_folder' in configData:
            self.moviesFolder = configData['movies_folder']

    def saveConfig(self):
        configData = {}
        if not self.moviesFolder == self.moviesFolderEdit.text():
            configData['movies_folder'] = self.moviesFolderEdit.text()
        else:
            configData['movies_folder'] = self.moviesFolder

        with open(self.configFile, "w") as f:
            json.dump(configData, f, indent=4)

    def readSmdbFile(self):
        self.smdbData = None
        if os.path.exists(self.smdbFile):
            with open(self.smdbFile) as f:
                self.smdbData = json.load(f)

    def writeSmdbFile(self):
        self.smdbData = {}
        titles = {}
        directors = {}
        actors = {}
        genres = {}
        years = {}

        self.progressBar.setMaximum(self.moviesList.count())
        progress = 0
        self.isCanceled = False

        count = self.moviesList.count()
        for row in range(count):

            listItem = self.moviesList.item(row)

            QtCore.QCoreApplication.processEvents()
            if self.isCanceled == True:
                self.statusBar().showMessage('Cancelled')
                self.isCanceled = False
                self.progressBar.setValue(0)
                self.setMovieListItemColors()
                return

            message = "Downloading data (%d/%d): %s" % (progress + 1,
                                                        count,
                                                        listItem.text())
            self.statusBar().showMessage(message)
            QtCore.QCoreApplication.processEvents()

            moviePath = listItem.data(QtCore.Qt.UserRole)['path']
            folderName = listItem.data(QtCore.Qt.UserRole)['folder name']
            jsonFile = os.path.join(moviePath, '%s.json' % folderName)
            if os.path.exists(jsonFile):
                with open(jsonFile) as f:
                    jsonData = json.load(f)
                if 'title' in jsonData and 'year' in jsonData:
                    jsonTitle = jsonData['title']
                    jsonYear = jsonData['year']
                    titleYear = (jsonTitle, jsonYear)

                    jsonYear = None
                    if 'year' in jsonData and jsonData['year']:
                        jsonYear = jsonData['year']
                        if not jsonYear in years:
                            years[jsonYear] = {}
                            years[jsonYear]['movies'] = []
                        if titleYear not in years[jsonYear]:
                            years[jsonYear]['movies'].append(titleYear)

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
                            directors[directorName]['movies'] = []
                        if titleYear not in directors[directorName]:
                            directors[directorName]['movies'].append(titleYear)

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
                                actors[actorName]['movies'] = []
                            if titleYear not in actors[actorName]:
                                actors[actorName]['movies'].append(titleYear)

                            movieActorsList.append(actorName)

                    jsonGenres = None
                    if 'genres' in jsonData and jsonData['genres']:
                        jsonGenres = jsonData['genres']
                        for genre in jsonGenres:
                            if genre not in genres:
                                genres[genre] = {}
                                genres[genre]['movies'] = []
                            if titleYear not in genres[genre]:
                                genres[genre]['movies'].append(titleYear)

                    titles[jsonTitle] = { 'year': jsonYear, 'director': directorName, 'genres': jsonGenres, 'actors': movieActorsList }

            progress += 1
            self.progressBar.setValue(progress)

        self.smdbData['titles'] = collections.OrderedDict(sorted(titles.items()))
        self.smdbData['years'] = collections.OrderedDict(sorted(years.items()))
        self.smdbData['genres'] = collections.OrderedDict(sorted(genres.items()))
        self.smdbData['directors'] = collections.OrderedDict(sorted(directors.items()))
        self.smdbData['actors'] = collections.OrderedDict(sorted(actors.items()))

        with open(self.smdbFile, "w") as f:
            json.dump(self.smdbData, f, indent=4)

    def addCriteriaWidgets(self, criteriaName, comboBoxEnum = [], displayStyle=0):
        criteriaWidget = QtWidgets.QWidget(self)
        criteriaVLayout = QtWidgets.QVBoxLayout(self)
        criteriaWidget.setLayout(criteriaVLayout)

        criteriaText = QtWidgets.QLabel(criteriaName)
        criteriaText.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Maximum)
        criteriaText.setAlignment(QtCore.Qt.AlignCenter)
        criteriaVLayout.addWidget(criteriaText)

        criteriaDisplayStyleHLayout = QtWidgets.QHBoxLayout(self)
        criteriaVLayout.addLayout(criteriaDisplayStyleHLayout)

        displayStyleText = QtWidgets.QLabel("%s Display Style" % criteriaName)
        displayStyleText.setSizePolicy(QtWidgets.QSizePolicy.Maximum, QtWidgets.QSizePolicy.Maximum)
        criteriaDisplayStyleHLayout.addWidget(displayStyleText)

        criteriaDisplayStyleComboBox = QtWidgets.QComboBox(self)
        for i in comboBoxEnum:
            criteriaDisplayStyleComboBox.addItem(i)
        criteriaDisplayStyleComboBox.setCurrentIndex(displayStyle)
        criteriaDisplayStyleHLayout.addWidget(criteriaDisplayStyleComboBox)

        criteriaList = QtWidgets.QListWidget(self)
        criteriaList.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        criteriaVLayout.addWidget(criteriaList)

        criteriaDisplayStyleComboBox.activated.connect(
            lambda: self.listDisplayStyleChanged(criteriaDisplayStyleComboBox, criteriaList))

        criteriaSearchHLayout = QtWidgets.QHBoxLayout(self)
        criteriaVLayout.addLayout(criteriaSearchHLayout)

        criteriaSearchText = QtWidgets.QLabel("Search")
        criteriaSearchText.setSizePolicy(QtWidgets.QSizePolicy.Maximum, QtWidgets.QSizePolicy.Maximum)
        criteriaSearchHLayout.addWidget(criteriaSearchText)

        searchBox = QtWidgets.QLineEdit(self)
        searchBox.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Maximum)
        searchBox.setClearButtonEnabled(True)
        criteriaSearchHLayout.addWidget(searchBox)

        return criteriaWidget, criteriaList, searchBox, criteriaDisplayStyleComboBox

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
            self.moviesFolderEdit.setText(self.moviesFolder)
            self.moviesFolderEdit.setStyleSheet("color: black; background: white")
            self.readSmdbFile()
            self.populateLists()

    def initUI(self):
        menuBar = self.menuBar()
        fileMenu = menuBar.addMenu('Actions')

        rebuildSmdbFileAction = QtWidgets.QAction("Rebuild SMDB file", self)
        rebuildSmdbFileAction.triggered.connect(self.writeSmdbFile)
        fileMenu.addAction(rebuildSmdbFileAction)

        refreshAction = QtWidgets.QAction("Refresh", self)
        refreshAction.triggered.connect(self.refresh)
        fileMenu.addAction(refreshAction)

        quitAction = QtWidgets.QAction("Quit", self)
        quitAction.triggered.connect(QtCore.QCoreApplication.quit)
        fileMenu.addAction(quitAction)

        centralWidget = QtWidgets.QWidget()
        self.setCentralWidget(centralWidget)

        # Divides top h splitter and bottom progress bar
        mainVLayout = QtWidgets.QVBoxLayout(self)
        centralWidget.setLayout(mainVLayout)

        # Top Horizontal layout
        topHorizontalLayout = QtWidgets.QHBoxLayout(self)
        mainVLayout.addLayout(topHorizontalLayout)

        # Settings
        settingsGroupBox = QtWidgets.QGroupBox()
        settingsGroupBox.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Maximum)
        topHorizontalLayout.addWidget(settingsGroupBox)

        settingsVLayout = QtWidgets.QVBoxLayout(self)
        settingsGroupBox.setLayout(settingsVLayout)

        settingsVLayout.addWidget(QtWidgets.QLabel("Settings"))

        moviesFolderHLayout = QtWidgets.QHBoxLayout(self)
        settingsVLayout.addLayout(moviesFolderHLayout)

        moviesFolderText = QtWidgets.QLabel("Movies Folder")
        moviesFolderText.setSizePolicy(QtWidgets.QSizePolicy.Maximum, QtWidgets.QSizePolicy.Maximum)
        moviesFolderHLayout.addWidget(moviesFolderText)

        self.moviesFolderEdit = QtWidgets.QLineEdit("Click the browse button and select your movie folder")
        self.moviesFolderEdit.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Maximum)
        self.moviesFolderEdit.setText(self.moviesFolder)
        if os.path.exists(self.moviesFolder):
            self.moviesFolderEdit.setStyleSheet("color: black; background: white")
        else:
            self.moviesFolderEdit.setStyleSheet("color: red; background: black")
        moviesFolderHLayout.addWidget(self.moviesFolderEdit)

        moviesFolderBrowse = QtWidgets.QPushButton("Browse")
        moviesFolderBrowse.setSizePolicy(QtWidgets.QSizePolicy.Maximum, QtWidgets.QSizePolicy.Maximum)
        moviesFolderBrowse.clicked.connect(lambda: self.browseMoviesFolder())
        moviesFolderHLayout.addWidget(moviesFolderBrowse)

        # Main H Splitter for criteria, movies list, and cover/info
        mainHSplitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal, self)
        mainHSplitter.setHandleWidth(10)
        mainVLayout.addWidget(mainHSplitter)

        # V Splitter on the left dividing Directors, etc.
        criteriaVSplitter = QtWidgets.QSplitter(QtCore.Qt.Vertical, self)
        criteriaVSplitter.setHandleWidth(20)

        directorsWidget,\
        self.directorsList,\
        self.directorsListSearchBox,\
        self.directorsComboBox = self.addCriteriaWidgets("Directors",
                                                         comboBoxEnum=['(total)director', 'director(total)'])
        self.directorsList.itemSelectionChanged.connect(lambda: self.criteriaSelectionChanged(self.directorsList, 'directors'))
        self.directorsListSearchBox.textChanged.connect(lambda: searchListWidget(self.directorsListSearchBox, self.directorsList))
        self.directorsList.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.directorsList.customContextMenuRequested[QtCore.QPoint].connect(lambda: self.peopleListRightMenuShow(self.directorsList))
        criteriaVSplitter.addWidget(directorsWidget)

        actorsWidget,\
        self.actorsList,\
        self.actorsListSearchBox,\
        self.actorsComboBox = self.addCriteriaWidgets("Actors",
                                                      comboBoxEnum=['(total)actor', 'actor(total)'])
        self.actorsList.itemSelectionChanged.connect(lambda: self.criteriaSelectionChanged(self.actorsList, 'actors'))
        self.actorsListSearchBox.textChanged.connect(lambda: searchListWidget(self.actorsListSearchBox, self.actorsList))
        self.actorsList.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.actorsList.customContextMenuRequested[QtCore.QPoint].connect(lambda: self.peopleListRightMenuShow(self.actorsList))
        criteriaVSplitter.addWidget(actorsWidget)

        genresWidget,\
        self.genresList,\
        self.genresListSearchBox,\
        self.genresComboBox = self.addCriteriaWidgets("Genres",
                                                      comboBoxEnum=['(total)genre', 'genre(total)'])
        self.genresList.itemSelectionChanged.connect(lambda: self.criteriaSelectionChanged(self.genresList, 'genres'))
        self.genresListSearchBox.textChanged.connect(lambda: searchListWidget(self.genresListSearchBox, self.genresList))
        criteriaVSplitter.addWidget(genresWidget)

        yearsWidget,\
        self.yearsList,\
        self.yearsListSearchBox,\
        self.yearsComboBox = self.addCriteriaWidgets("Years",
                                                     comboBoxEnum=['(total)year', 'year(total)'],
                                                     displayStyle=1)
        self.yearsList.itemSelectionChanged.connect(lambda: self.criteriaSelectionChanged(self.yearsList, 'years'))
        self.yearsListSearchBox.textChanged.connect(lambda: searchListWidget(self.yearsListSearchBox, self.yearsList))
        criteriaVSplitter.addWidget(yearsWidget)

        moviesWidget, \
        self.moviesList, \
        self.moviesListSearchBox, \
        self.moviesComboBox = self.addCriteriaWidgets("Movies",
                                                      comboBoxEnum=["(year)title",
                                                                    "(rating)title",
                                                                    "title(year)",
                                                                    "folder name"])
        self.moviesList.itemSelectionChanged.connect(lambda: self.movieSelectionChanged())
        self.moviesListSearchBox.textChanged.connect(lambda: searchListWidget(self.moviesListSearchBox, self.moviesList))
        self.moviesList.doubleClicked.connect(self.playMovie)
        self.moviesList.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.moviesList.customContextMenuRequested[QtCore.QPoint].connect(self.moviesListRightMenuShow)

        # Cover and Summary ---------------------------------------------------------------------------------------
        movieSummaryVSplitter = QtWidgets.QSplitter(QtCore.Qt.Vertical, self)
        movieSummaryVSplitter.setHandleWidth(20)

        self.movieCover = QtWidgets.QLabel(self)
        self.movieCover.setScaledContents(False)
        self.movieCover.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Ignored)
        movieSummaryVSplitter.addWidget(self.movieCover)

        self.summary = QtWidgets.QTextBrowser()
        movieSummaryVSplitter.addWidget(self.summary)

        # Add the sub-layouts to the mainHSplitter
        mainHSplitter.addWidget(criteriaVSplitter)
        mainHSplitter.addWidget(moviesWidget)
        mainHSplitter.addWidget(movieSummaryVSplitter)
        mainHSplitter.setSizes([400, 400, 600])

        # Bottom ---------------------------------------------------------------------------------------
        bottomLayout = QtWidgets.QHBoxLayout(self)
        mainVLayout.addLayout(bottomLayout)

        self.progressBar = QtWidgets.QProgressBar(self)
        self.progressBar.setMaximum(100)
        bottomLayout.addWidget(self.progressBar)

        cancelButton = QtWidgets.QPushButton("Cancel", self)
        cancelButton.clicked.connect(self.cancelButtonClicked)
        bottomLayout.addWidget(cancelButton)

    def listDisplayStyleChanged(self, comboBoxWidget, listWidget):
        comboBoxText = comboBoxWidget.currentText()
        displayStyle = 0
        if comboBoxText == "(year)title":
            displayStyle = displayStyles.YEAR_TITLE
        elif comboBoxText == "(rating)title":
            displayStyle = displayStyles.RATING_TITLE_YEAR
        elif comboBoxText == "title(year)":
            displayStyle = displayStyles.TITLE_YEAR
        elif comboBoxText == "folder name":
            displayStyle = displayStyles.FOLDER
        elif re.match(r'\((.*)\).*', comboBoxText):
            displayStyle = displayStyles.TOTAL_ITEM
        elif re.match(r'.*\((.*)\)', comboBoxText):
            displayStyle = displayStyles.ITEM_TOTAL

        for row in range(listWidget.count()):
            item = listWidget.item(row)
            if displayStyle == displayStyles.TOTAL_ITEM:
                criteriaKey = item.data(QtCore.Qt.UserRole)['criteria key']
                criteria = item.data(QtCore.Qt.UserRole)['criteria']
                displayText = '(%04d) %s' % (len(self.smdbData[criteriaKey][criteria]['movies']), criteria)
            elif displayStyle == displayStyles.ITEM_TOTAL:
                criteriaKey = item.data(QtCore.Qt.UserRole)['criteria key']
                criteria = item.data(QtCore.Qt.UserRole)['criteria']
                displayText = '%s (%04d)' % (criteria, len(self.smdbData[criteriaKey][criteria]['movies']))
            elif displayStyle == displayStyles.YEAR_TITLE:
                folderName = item.data(QtCore.Qt.UserRole)['folder name']
                niceTitle, year = getNiceTitleAndYear(folderName)
                displayText = '(%s) %s' % (year, niceTitle)
            elif displayStyle == displayStyles.RATING_TITLE_YEAR:
                folderName = item.data(QtCore.Qt.UserRole)['folder name']
                rating = item.data(QtCore.Qt.UserRole)['rating']
                niceTitle, year = getNiceTitleAndYear(folderName)
                displayText = '%s - (%s) %s' % (rating, year, niceTitle)
            elif displayStyle == displayStyles.TITLE_YEAR:
                folderName = item.data(QtCore.Qt.UserRole)['folder name']
                niceTitle, year = getNiceTitleAndYear(folderName)
                displayText = '%s (%s)' % (niceTitle, year)
            elif displayStyle == displayStyles.FOLDER:
                folderName = item.data(QtCore.Qt.UserRole)['folder name']
                displayText = folderName
            item.setText(displayText)

        if displayStyle == displayStyles.TOTAL_ITEM or displayStyle == displayStyles.RATING_TITLE_YEAR:
            listWidget.sortItems(QtCore.Qt.DescendingOrder)
        else:
            listWidget.sortItems(QtCore.Qt.AscendingOrder)

    def downloadDataMenu(self, force=False):
        numSelectedItems = len(self.moviesList.selectedItems())
        self.progressBar.setMaximum(numSelectedItems)
        progress = 0
        self.isCanceled = False
        for item in self.moviesList.selectedItems():
            QtCore.QCoreApplication.processEvents()
            if self.isCanceled == True:
                self.statusBar().showMessage('Cancelled')
                self.isCanceled = False
                self.progressBar.setValue(0)
                self.setMovieListItemColors()
                return

            message = "Downloading data (%d/%d): %s" % (progress + 1,
                                                        numSelectedItems,
                                                        item.text())
            self.statusBar().showMessage(message)
            QtCore.QCoreApplication.processEvents()

            self.downloadMovieData(item, force)
            self.clickedMovie(item)

            progress += 1
            self.progressBar.setValue(progress)
        self.statusBar().showMessage("Done")
        self.progressBar.setValue(0)
        self.setMovieListItemColors()

    def removeJsonFilesMenu(self):
        filesToDelete = []
        for item in self.moviesList.selectedItems():
            moviePath = item.data(QtCore.Qt.UserRole)['path']
            movieFolder = item.data(QtCore.Qt.UserRole)['folder name']
            jsonFile = os.path.join(moviePath, '%s.json' % movieFolder)
            if (os.path.exists(jsonFile)):
                filesToDelete.append(os.path.join(moviePath, jsonFile))
        removeFiles(self, filesToDelete, '.json')
        self.setMovieListItemColors()

    def removeCoverFilesMenu(self):
        filesToDelete = []
        for item in self.moviesList.selectedItems():
            moviePath = item.data(QtCore.Qt.UserRole)['path']
            movieFolder = item.data(QtCore.Qt.UserRole)['folder name']

            coverFile = os.path.join(moviePath, '%s.jpg' % movieFolder)
            if os.path.exists(coverFile):
                filesToDelete.append(coverFile)
            else:
                coverFile = os.path.join(moviePath, '%s.png' % item.text())
                if os.path.exists(coverFile):
                    filesToDelete.append(coverFile)

        removeFiles(self, filesToDelete, '.jpg')

    def setMovieListItemColors(self):
        for row in range(self.moviesList.count()):
            listItem = self.moviesList.item(row)
            moviePath = listItem.data(QtCore.Qt.UserRole)['path']
            movieFolder = listItem.data(QtCore.Qt.UserRole)['folder name']
            jsonFile = os.path.join(moviePath, '%s.json' % movieFolder)
            if not os.path.exists(jsonFile):
                listItem.setBackground(QtGui.QColor(220, 220, 220))
            else:
                listItem.setBackground(QtGui.QColor(255, 255, 255))

    def populateCriteriaList(self, criteriaKey, listWidget):
        if not self.smdbData:
            print("Error: No smbdData")
            return

        if criteriaKey not in self.smdbData:
            print("Error: '%s' not in smdbData" % criteriaKey)
            return

        listWidget.clear()
        for c in self.smdbData[criteriaKey].keys():
            item = QtWidgets.QListWidgetItem('')
            userData = {}
            userData['criteria'] = c
            userData['criteria key'] = criteriaKey
            userData['list widget'] = listWidget
            item.setData(QtCore.Qt.UserRole, userData)
            listWidget.addItem(item)
        listWidget.sortItems(QtCore.Qt.DescendingOrder)

    def populateMovieList(self):
        self.moviesList.clear()
        if not os.path.exists(self.moviesFolder):
            return
        with os.scandir(self.moviesFolder) as files:
            for f in files:
                if f.is_dir() and fnmatch.fnmatch(f, '*(*)'):
                    item = QtWidgets.QListWidgetItem(f.name)
                    userData = {}
                    userData['folder name'] = f.name
                    userData['path'] = os.path.join(self.moviesFolder, f.name)
                    userData['title'] = ''
                    userData['year'] = ''
                    userData['rating'] = ''
                    userData['id'] = ''

                    jsonFile = os.path.join(self.moviesFolder, f.name, '%s.json' % f.name)
                    if os.path.exists(jsonFile):
                        with open(jsonFile) as f:
                            data = json.load(f)
                            if 'title' in data:
                                userData['title'] = data['title']
                            if 'year' in data:
                                userData['year'] = data['year']
                            if 'rating' in data:
                                userData['rating'] = data['rating']
                            if 'id' in data:
                                userData['id'] = data['id']
                    item.setData(QtCore.Qt.UserRole, userData)
                    self.moviesList.addItem(item)
        self.setMovieListItemColors()
        self.listDisplayStyleChanged(self.moviesComboBox, self.moviesList)
        self.moviesList.setCurrentItem(self.moviesList.item(0))

    def cancelButtonClicked(self):
        self.isCanceled = True

    def movieSelectionChanged(self):
        numSelected = len(self.moviesList.selectedItems())
        total = self.moviesList.count()
        self.statusBar().showMessage('%s/%s' % (numSelected, total))
        if numSelected == 1:
            self.clickedMovie(self.moviesList.selectedItems()[0])

    def criteriaSelectionChanged(self, listWidget, smdbKey):
        if len(listWidget.selectedItems()) == 0:
            for row in range(listWidget.count()):
                listWidget.item(row).setHidden(False)
            return

        criteriaMovieList = []
        for item in listWidget.selectedItems():
            criteria = item.text()
            userData = item.data(QtCore.Qt.UserRole)
            movies = self.smdbData[smdbKey][userData['criteria']]['movies']
            for movie in movies:
                if movie not in criteriaMovieList:
                    criteriaMovieList.append(movie)

        for row in range(self.moviesList.count()):
            self.moviesList.item(row).setHidden(True)

        # Movies are stored as ['Anchorman: The Legend of Ron Burgundy', 2004]
        self.progressBar.setMaximum(len(criteriaMovieList))
        progress = 0
        for row in range(self.moviesList.count()):
            listItem = self.moviesList.item(row)
            userData = listItem.data(QtCore.Qt.UserRole)
            if 'title' in userData: title = userData['title']
            if 'year' in userData: year = userData['year']
            for (t, y) in criteriaMovieList:
                if t == title and y == year:
                    self.moviesList.item(row).setHidden(False)
            progress += 1
            self.progressBar.setValue(progress)


    def clickedMovie(self, listItem):
        moviePath = listItem.data(QtCore.Qt.UserRole)['path']
        folderName = listItem.data(QtCore.Qt.UserRole)['folder name']
        jsonFile = os.path.join(moviePath, '%s.json' % folderName)
        coverFile = os.path.join(moviePath, '%s.jpg' % folderName)
        if not os.path.exists(coverFile):
            coverFilePng = os.path.join(moviePath, '%s.png' % folderName)
            if os.path.exists(coverFilePng):
                coverFile = coverFilePng

        self.showCoverFile(coverFile)
        self.showSummary(jsonFile)

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

        results = self.db.search_movie(searchText)
        if not results:
            print('No matches for: %s' % searchText)
            return

        movie = results[0]
        for res in results:
            if res.has_key('year') and res.has_key('kind'):
                kind = res['kind']
                print("kind = %s" % res['kind'])
                print("year = %s" % res['year'])
                if res['year'] == year and (kind == 'movie' or kind == 'tv movie' or kind == 'tv miniseries'):
                    movie = res
                    break

        return movie

    def showCoverFile(self, coverFile):
        if os.path.exists(coverFile):
            pixMap = QtGui.QPixmap(coverFile)
            self.movieCover.setPixmap(pixMap.scaled(500, 500,
                                                    QtCore.Qt.KeepAspectRatio,
                                                    QtCore.Qt.SmoothTransformation))
        else:
            self.movieCover.setPixmap(QtGui.QPixmap(0,0))

    def showSummary(self, jsonFile):
        if os.path.exists(jsonFile):
            with open(jsonFile) as f:
                data = json.load(f)
                summary = data['summary']
                self.summary.setText(summary)
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
        print("rating = %s" % d['rating'])
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
        if (cast and isinstance(cast, list)):
            for c in movie['cast']:
                d['cast'].append(c['name'])
        d['genres'] = self.getMovieKey(movie, 'genres')
        d['plot'] = self.getMovieKey(movie, 'plot')
        d['plot outline'] = self.getMovieKey(movie, 'plot outline')
        d['synopsis'] = self.getMovieKey(movie, 'synopsis')
        d['summary'] = movie.summary()
        d['cover url'] = self.getMovieKey(movie, 'cover url')
        d['full-size cover url'] = self.getMovieKey(movie, 'full-size cover url')

        with open(jsonFile, "w") as f:
            json.dump(d, f, indent=4)

    def downloadMovieData(self, listItem, force=False):
        moviePath = listItem.data(QtCore.Qt.UserRole)['path']
        folderName = listItem.data(QtCore.Qt.UserRole)['folder name']
        jsonFile = os.path.join(moviePath, '%s.json' % folderName)
        coverFile = os.path.join(moviePath, '%s.jpg' % folderName)
        if not os.path.exists(coverFile):
            coverFilePng = os.path.join(moviePath, '%s.png' % folderName)
            if os.path.exists(coverFilePng):
                coverFile = coverFilePng

        if force is True or not os.path.exists(jsonFile) or not os.path.exists(coverFile):
            movie = self.getMovie(folderName)
            if not movie:
                return coverFile
            self.db.update(movie)
            self.writeMovieJson(movie, jsonFile)
            coverFile = copyCoverImage(movie, coverFile)

        return coverFile

    def playMovie(self):
        selectedMovie = self.moviesList.selectedItems()[0]
        movieFolder = selectedMovie.data(QtCore.Qt.UserRole)['path']
        if not os.path.exists(movieFolder):
            return

        movieFiles = []
        for file in os.listdir(movieFolder):
            extension = os.path.splitext(file)[1]
            if extension == '.mkv' or \
                    extension == '.mp4' or \
                    extension == '.avi' or \
                    extension == '.avi' or \
                    extension == '.m4v':
                movieFiles.append(file)
        if len(movieFiles) == 1:
            fileToPlay = os.path.join(movieFolder, movieFiles[0])
            if os.path.exists(fileToPlay):
                os.startfile(fileToPlay)
        else:
            # If there are more than one movie like files in the
            # folder, then just open the folder so the user can
            # play the desired file.
            os.startfile(movieFolder)

    def openMovieFolder(self):
        selectedMovie = self.moviesList.selectedItems()[0]
        filePath = selectedMovie.data(QtCore.Qt.UserRole)['path']
        os.startfile(filePath)

    def openMovieImdbPage(self):
        selectedMovie = self.moviesList.selectedItems()[0]
        movieId = selectedMovie.data(QtCore.Qt.UserRole)['id']
        webbrowser.open('http://imdb.com/title/tt%s' % movieId, new=2)

    def openPersonImdbPage(self, personName):
        personId = self.db.name2imdbID(personName)
        if not personId:
            print("Searching for: %s" % personName)
            results = self.db.search_person(personName)
            if not results:
                print('No matches for: %s' % personName)
                return
            person = results[0]
            if isinstance(person, imdb.Person.Person):
                personId = person.getID()

        if (personId):
            print("Opening IMDB page for: %s" % personName)
            webbrowser.open('http://imdb.com/name/nm%s' % personId, new=2)

    def peopleListRightMenuShow(self, peopleList):
        rightMenu = QtWidgets.QMenu(peopleList)
        selectedItem = peopleList.selectedItems()[0]
        userData = selectedItem.data(QtCore.Qt.UserRole)
        personName = userData['criteria']
        openImdbAction = QtWidgets.QAction("Open IMDB Page", self)
        openImdbAction.triggered.connect(lambda: self.openPersonImdbPage(personName))
        rightMenu.addAction(openImdbAction)
        rightMenu.exec_(QtGui.QCursor.pos())

    def moviesListRightMenuShow(self, QPos):
        self.rightMenu = QtWidgets.QMenu(self.moviesList)

        selectedMovie = self.moviesList.selectedItems()[0]
        self.clickedMovie(selectedMovie)

        self.playAction = QtWidgets.QAction("Play", self)
        self.playAction.triggered.connect(lambda: self.playMovie())
        self.rightMenu.addAction(self.playAction)

        self.openFolderAction = QtWidgets.QAction("Open Folder", self)
        self.openFolderAction.triggered.connect(lambda: self.openMovieFolder())
        self.rightMenu.addAction(self.openFolderAction)

        self.openImdbAction = QtWidgets.QAction("Open IMDB Page", self)
        self.openImdbAction.triggered.connect(lambda: self.openMovieImdbPage())
        self.rightMenu.addAction(self.openImdbAction)

        self.downloadDataAction = QtWidgets.QAction("Download Data", self)
        self.downloadDataAction.triggered.connect(lambda: self.downloadDataMenu())
        self.rightMenu.addAction(self.downloadDataAction)

        self.downloadDataAction = QtWidgets.QAction("Force Download Data", self)
        self.downloadDataAction.triggered.connect(lambda: self.downloadDataMenu(force=True))
        self.rightMenu.addAction(self.downloadDataAction)

        self.removeMdbAction = QtWidgets.QAction("Remove .json files", self)
        self.removeMdbAction.triggered.connect(lambda: self.removeJsonFilesMenu())
        self.rightMenu.addAction(self.removeMdbAction)

        self.removeCoversAction = QtWidgets.QAction("Remove cover files", self)
        self.removeCoversAction.triggered.connect(lambda: self.removeCoverFilesMenu())
        self.rightMenu.addAction(self.removeCoversAction)

        self.rightMenu.exec_(QtGui.QCursor.pos())


def window():
    app = QApplication(sys.argv)
    win = MyWindow()
    win.show()
    sys.exit(app.exec_())


window()
