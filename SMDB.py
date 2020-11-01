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
    BOX_OFFICE_YEAR_TITLE = auto(),
    RUNTIME_YEAR_TITLE = auto(),
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
    try:
        urllib.request.urlretrieve(movieCoverUrl, coverFile)
    except:
        print("Problem downloading cover file: %s" % coverFile)
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

class MoviesTableModel(QtCore.QAbstractTableModel):
    def __init__(self, smdbData, moviesFolder, forceScan=False):
        super().__init__()
        self.numVisibleMovies = 0
        if not os.path.exists(moviesFolder):
            return

        reMoneyValue = re.compile(r'(\d+(?:,\d+)*(?:\.\d+)?)')
        reCurrency = re.compile(r'^([A-Z][A-Z][A-Z])(.*)')

        movieList = []
        useSmdbData = False
        if not forceScan and smdbData and 'titles' in smdbData:
            useSmdbData = True
            for title in smdbData['titles']:
                movieList.append(title)
        else:
            with os.scandir(moviesFolder) as files:
                for f in files:
                    if f.is_dir() and fnmatch.fnmatch(f, '*(*)'):
                        movieList.append(f.name)

        self._data = []
        for folderName in movieList:
            data = {}
            if useSmdbData:
                data = smdbData['titles'][folderName]
            else:
                jsonFile = os.path.join(moviesFolder, folderName, '%s.json' % folderName)
                if os.path.exists(jsonFile):
                    with open(jsonFile) as f:
                        try:
                            data = json.load(f)
                        except UnicodeDecodeError:
                            print("Error reading %s" % jsonFile)

            self._headers = ['year',
                             'title',
                             'rating',
                             'box office',
                             'runtime',
                             'id',
                             'folder name',
                             'path']
            movieData = []
            for header in self._headers:
                if header == 'path':
                    movieData.append(os.path.join(moviesFolder, folderName))
                if header == 'folder name':
                    movieData.append(folderName)
                else:
                    if header in data:
                        if header == 'runtime':
                            runtime = data[header]
                            if runtime == None:
                                runtime = '000'
                            else:
                                runtime = '%03d' % int(runtime)
                            movieData.append(runtime)
                        elif header == 'rating':
                            rating = data[header]
                            if rating == None:
                                rating = '0.0'
                            else:
                                rating = str(rating)
                                if len(rating) == 1:
                                    rating = '%s.0' % rating
                            movieData.append(rating)
                        elif header == 'box office':
                            boxOffice = data[header]
                            currency = 'USD'
                            if boxOffice:
                                boxOffice = boxOffice.replace(' (estimated)', '')
                                match = re.match(reCurrency, boxOffice)
                                if match:
                                    currency = match.group(1)
                                    boxOffice = '$%s' % match.group(2)
                                results = re.findall(reMoneyValue, boxOffice)
                                if currency == 'USD':
                                    amount = '$%s' % results[0]
                                else:
                                    amount = '%s' % results[0]
                            else:
                                amount = '$0'
                            displayText = '%3s %15s' % (currency, amount)
                            movieData.append(displayText)
                        else:
                            movieData.append(data[header])
                    else:
                        movieData.append('')
            self._data.append(movieData)

        self.sort(0, QtCore.Qt.AscendingOrder)

    def rowCount(self, parent):
        return len(self._data)

    def columnCount(self, parent):
        return len(self._headers)

    def data(self, index, role):
        if role == QtCore.Qt.DisplayRole:
            return self._data[index.row()][index.column()]

    def headerData(self, section, orientation, role):
        if orientation == QtCore.Qt.Horizontal and role == QtCore.Qt.DisplayRole:
            return self._headers[section]
        else:
            return super().headerData(section, orientation, role)

    def sort(self, column, order):
        self.layoutAboutToBeChanged.emit()
        #self._data.sort(key=lambda x: x[column] if x[column] else '')
        self._data.sort(key=lambda x: str(x[column]) if x[column] else '')
        #self._data.sort(key=cmp_to_key(myCompare))
        if order == QtCore.Qt.DescendingOrder:
            self._data.reverse()
        self.layoutChanged.emit()

class MyWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super(MyWindow, self).__init__()
        self.setGeometry(200, 75, 1600, 900)
        self.setWindowTitle("Scott's Movie Database")
        self.numVisibleMovies = 0

        self.db = IMDb()

        self.settings = QtCore.QSettings("STC", "SMDB")
        self.moviesFolder = self.settings.value('movies_folder', "J:/Movies", type=str)

        if not os.path.exists(self.moviesFolder):
            return
        self.smdbFile = os.path.join(self.moviesFolder, "smdb_data.json")

        self.initUI()

    def refresh(self, forceScan=False):

        if os.path.exists(self.smdbFile):
            self.readSmdbFile()
            self.populateMovieList(forceScan)
        else:
            self.populateMovieList(forceScan)
            self.writeSmdbFile()

        self.moviesTableModel = MoviesTableModel(self.smdbData, self.moviesFolder, forceScan)
        self.moviesTable.setModel(self.moviesTableModel)

        if forceScan:
            return

        self.populateCriteriaList('directors', self.directorsList, self.directorsComboBox)
        self.populateCriteriaList('actors', self.actorsList, self.actorsComboBox)
        self.populateCriteriaList('genres', self.genresList, self.genresComboBox)
        self.populateCriteriaList('years', self.yearsList, self.yearsComboBox)
        self.populateCriteriaList('companies', self.companiesList, self.companiesComboBox)
        self.populateCriteriaList('countries', self.countriesList, self.countriesComboBox)
        self.moviesList.setCurrentItem(self.moviesList.item(0))
        self.movieSelectionChanged()

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
        companies = {}
        countries = {}

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

            message = "Processing item (%d/%d): %s" % (progress + 1,
                                                        count,
                                                        listItem.text())
            self.statusBar().showMessage(message)
            QtCore.QCoreApplication.processEvents()

            moviePath = listItem.data(QtCore.Qt.UserRole)['path']
            folderName = listItem.data(QtCore.Qt.UserRole)['folder name']
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
        self.smdbData['titles'] = collections.OrderedDict(sorted(titles.items()))
        self.smdbData['years'] = collections.OrderedDict(sorted(years.items()))
        self.smdbData['genres'] = collections.OrderedDict(sorted(genres.items()))
        self.smdbData['directors'] = collections.OrderedDict(sorted(directors.items()))
        self.smdbData['actors'] = collections.OrderedDict(sorted(actors.items()))
        self.smdbData['companies'] = collections.OrderedDict(sorted(companies.items()))
        self.smdbData['countries'] = collections.OrderedDict(sorted(countries.items()))

        self.statusBar().showMessage('Writing %s' % self.smdbFile)
        with open(self.smdbFile, "w") as f:
            json.dump(self.smdbData, f, indent=4)

        self.statusBar().showMessage('Done')

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

        displayStyleText = QtWidgets.QLabel("Display Style")
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
            self.settings.setValue('movies_folder', self.moviesFolder)
            self.readSmdbFile()
            self.refresh()

    def initUI(self):
        menuBar = self.menuBar()
        fileMenu = menuBar.addMenu('File')

        rebuildSmdbFileAction = QtWidgets.QAction("Rebuild SMDB file", self)
        rebuildSmdbFileAction.triggered.connect(self.writeSmdbFile)
        fileMenu.addAction(rebuildSmdbFileAction)

        setMovieFolderAction = QtWidgets.QAction("Set movie folder", self)
        setMovieFolderAction.triggered.connect(self.browseMoviesFolder)
        fileMenu.addAction(setMovieFolderAction)

        refreshAction = QtWidgets.QAction("Rescan movies dir", self)
        refreshAction.triggered.connect(lambda: self.refresh(forceScan=True))
        fileMenu.addAction(refreshAction)

        quitAction = QtWidgets.QAction("Quit", self)
        quitAction.triggered.connect(QtCore.QCoreApplication.quit)
        fileMenu.addAction(quitAction)

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

        # V Splitter on the left dividing Directors, etc.
        criteriaVSplitter1 = QtWidgets.QSplitter(QtCore.Qt.Vertical, self)
        criteriaVSplitter1.setHandleWidth(20)

        self.setStyleSheet("""QListWidget{
                            background: black;
                            color: white;
                        }
                        """
                           )

        self.setStyleSheet("QLabel { background: red; }")

        directorsWidget,\
        self.directorsList,\
        self.directorsListSearchBox,\
        self.directorsComboBox = self.addCriteriaWidgets("Directors",
                                                         comboBoxEnum=['(total)director', 'director(total)'])
        self.directorsList.itemSelectionChanged.connect(lambda: self.criteriaSelectionChanged(self.directorsList, 'directors'))
        self.directorsListSearchBox.textChanged.connect(lambda: searchListWidget(self.directorsListSearchBox, self.directorsList))
        self.directorsList.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.directorsList.customContextMenuRequested[QtCore.QPoint].connect(lambda: self.peopleListRightMenuShow(self.directorsList))
        criteriaVSplitter1.addWidget(directorsWidget)

        actorsWidget,\
        self.actorsList,\
        self.actorsListSearchBox,\
        self.actorsComboBox = self.addCriteriaWidgets("Actors",
                                                      comboBoxEnum=['(total)actor', 'actor(total)'])
        self.actorsList.itemSelectionChanged.connect(lambda: self.criteriaSelectionChanged(self.actorsList, 'actors'))
        self.actorsListSearchBox.textChanged.connect(lambda: searchListWidget(self.actorsListSearchBox, self.actorsList))
        self.actorsList.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.actorsList.customContextMenuRequested[QtCore.QPoint].connect(lambda: self.peopleListRightMenuShow(self.actorsList))
        criteriaVSplitter1.addWidget(actorsWidget)

        genresWidget,\
        self.genresList,\
        self.genresListSearchBox,\
        self.genresComboBox = self.addCriteriaWidgets("Genres",
                                                      comboBoxEnum=['(total)genre', 'genre(total)'])
        self.genresList.itemSelectionChanged.connect(lambda: self.criteriaSelectionChanged(self.genresList, 'genres'))
        self.genresListSearchBox.textChanged.connect(lambda: searchListWidget(self.genresListSearchBox, self.genresList))
        criteriaVSplitter1.addWidget(genresWidget)

        criteriaVSplitter2 = QtWidgets.QSplitter(QtCore.Qt.Vertical, self)
        criteriaVSplitter2.setHandleWidth(20)

        yearsWidget,\
        self.yearsList,\
        self.yearsListSearchBox,\
        self.yearsComboBox = self.addCriteriaWidgets("Years",
                                                     comboBoxEnum=['(total)year', 'year(total)'],
                                                     displayStyle=1)
        self.yearsList.itemSelectionChanged.connect(lambda: self.criteriaSelectionChanged(self.yearsList, 'years'))
        self.yearsListSearchBox.textChanged.connect(lambda: searchListWidget(self.yearsListSearchBox, self.yearsList))
        criteriaVSplitter2.addWidget(yearsWidget)

        companiesWidget, \
        self.companiesList, \
        self.companiesListSearchBox, \
        self.companiesComboBox = self.addCriteriaWidgets("Companies",
                                                     comboBoxEnum=['(total)company', 'company(total)'],
                                                     displayStyle=0)
        self.companiesList.itemSelectionChanged.connect(lambda: self.criteriaSelectionChanged(self.companiesList, 'companies'))
        self.companiesListSearchBox.textChanged.connect(lambda: searchListWidget(self.companiesListSearchBox, self.companiesList))
        criteriaVSplitter2.addWidget(companiesWidget)

        countriesWidget, \
        self.countriesList, \
        self.countriesListSearchBox, \
        self.countriesComboBox = self.addCriteriaWidgets("Countries",
                                                         comboBoxEnum=['(total)country', 'country(total)'],
                                                         displayStyle=0)
        self.countriesList.itemSelectionChanged.connect(lambda: self.criteriaSelectionChanged(self.countriesList, 'countries'))
        self.countriesListSearchBox.textChanged.connect(lambda: searchListWidget(self.countriesListSearchBox, self.countriesList))
        criteriaVSplitter2.addWidget(countriesWidget)

        moviesWidget, \
        self.moviesList, \
        self.moviesListSearchBox, \
        self.moviesComboBox = self.addCriteriaWidgets("Movies",
                                                      comboBoxEnum=["(year)title",
                                                                    "title(year)",
                                                                    "rating - (year)title",
                                                                    "box office - (year)title",
                                                                    "runtime - (year)title",
                                                                    "folder name"])
        self.moviesList.itemSelectionChanged.connect(lambda: self.movieSelectionChanged())
        self.moviesListSearchBox.textChanged.connect(lambda: searchListWidget(self.moviesListSearchBox, self.moviesList))
        self.moviesList.doubleClicked.connect(self.playMovie)
        self.moviesList.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.moviesList.customContextMenuRequested[QtCore.QPoint].connect(self.moviesListRightMenuShow)

        moviesTableViewWidget = QtWidgets.QWidget()
        moviesTableViewWidget.setLayout(QtWidgets.QVBoxLayout())
        self.moviesTable = QtWidgets.QTableView()
        self.moviesTable.setSortingEnabled(True)
        moviesTableViewWidget.layout().addWidget(QtWidgets.QLabel("Movies Table"))
        moviesTableViewWidget.layout().addWidget(self.moviesTable)

        # Cover and Summary ---------------------------------------------------------------------------------------
        movieSummaryVSplitter = QtWidgets.QSplitter(QtCore.Qt.Vertical, self)
        movieSummaryVSplitter.setHandleWidth(20)
        movieSummaryVSplitter.splitterMoved.connect(self.resizeCoverFile)

        movieWidget = QtWidgets.QWidget()
        movieWidget.setStyleSheet("background-color: black;")
        movieVLayout = QtWidgets.QVBoxLayout()
        movieWidget.setLayout(movieVLayout)

        # Get a list of available fonts
        #dataBase = QtGui.QFontDatabase()
        #for family in dataBase.families():
        #    print('%s' % family)
        #    for style in dataBase.styles(family):
        #        print('\t%s' % style)

        self.movieTitle = QtWidgets.QLabel('')
        self.movieTitle.setFont(QtGui.QFont('TimesNew Roman', 15))
        self.movieTitle.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.movieTitle.setStyleSheet("color: white;")
        movieVLayout.addWidget(self.movieTitle)

        self.movieCover = QtWidgets.QLabel(self)
        self.movieCover.setScaledContents(False)
        self.movieCover.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Ignored)

        self.movieCover.setStyleSheet("background-color: black;")

        movieVLayout.addWidget(self.movieCover)

        movieSummaryVSplitter.addWidget(movieWidget)

        self.summary = QtWidgets.QTextBrowser()
        self.summary.setStyleSheet("background-color: black;")
        #self.summary.setFontPointSize(20)
        movieSummaryVSplitter.addWidget(self.summary)

        movieSummaryVSplitter.setSizes([600, 200])

        # Add the sub-layouts to the mainHSplitter
        mainHSplitter.addWidget(criteriaVSplitter1)
        mainHSplitter.addWidget(criteriaVSplitter2)
        mainHSplitter.addWidget(moviesWidget)
        mainHSplitter.addWidget(moviesTableViewWidget)
        mainHSplitter.addWidget(movieSummaryVSplitter)
        mainHSplitter.setSizes([200, 200, 300, 300, 200])

        # Bottom ---------------------------------------------------------------------------------------
        bottomLayout = QtWidgets.QHBoxLayout(self)
        mainVLayout.addLayout(bottomLayout)

        self.progressBar = QtWidgets.QProgressBar(self)
        self.progressBar.setMaximum(100)
        bottomLayout.addWidget(self.progressBar)

        cancelButton = QtWidgets.QPushButton("Cancel", self)
        cancelButton.clicked.connect(self.cancelButtonClicked)
        bottomLayout.addWidget(cancelButton)

    def getDisplayStyle(self, comboBoxWidget):
        comboBoxText = comboBoxWidget.currentText()
        displayStyle = 0
        if comboBoxText == "(year)title":
            displayStyle = displayStyles.YEAR_TITLE
        elif comboBoxText == "title(year)":
            displayStyle = displayStyles.TITLE_YEAR
        elif comboBoxText == "rating - (year)title":
            displayStyle = displayStyles.RATING_TITLE_YEAR
        elif comboBoxText == "box office - (year)title":
            displayStyle = displayStyles.BOX_OFFICE_YEAR_TITLE
        elif comboBoxText == "runtime - (year)title":
            displayStyle = displayStyles.RUNTIME_YEAR_TITLE
        elif comboBoxText == "folder name":
            displayStyle = displayStyles.FOLDER
        elif re.match(r'\((.*)\).*', comboBoxText):
            displayStyle = displayStyles.TOTAL_ITEM
        elif re.match(r'.*\((.*)\)', comboBoxText):
            displayStyle = displayStyles.ITEM_TOTAL
        return displayStyle

    def listDisplayStyleChanged(self, comboBoxWidget, listWidget):
        displayStyle = self.getDisplayStyle(comboBoxWidget)

        self.progressBar.setMaximum(listWidget.count())
        progress = 0

        reMoneyValue = re.compile(r'(\d+(?:,\d+)*(?:\.\d+)?)')
        reCurrency = re.compile(r'^([A-Z][A-Z][A-Z])(.*)')

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
            elif displayStyle == displayStyles.BOX_OFFICE_YEAR_TITLE:
                folderName = item.data(QtCore.Qt.UserRole)['folder name']
                boxOffice = item.data(QtCore.Qt.UserRole)['box office']
                currency = 'USD'
                if boxOffice:
                    boxOffice = boxOffice.replace(' (estimated)', '')
                    match = re.match(reCurrency, boxOffice)
                    if match:
                        currency = match.group(1)
                        boxOffice = '$%s' % match.group(2)
                    results = re.findall(reMoneyValue, boxOffice)
                    if currency == 'USD':
                        amount = '$%s' % results[0]
                    else:
                        amount = '%s' % results[0]
                else:
                    amount = '$0'
                niceTitle, year = getNiceTitleAndYear(folderName)
                displayText = '%3s %15s - (%s) %s' % (currency, amount, year, niceTitle)
            elif displayStyle == displayStyles.RUNTIME_YEAR_TITLE:
                folderName = item.data(QtCore.Qt.UserRole)['folder name']
                runtime = item.data(QtCore.Qt.UserRole)['runtime']
                niceTitle, year = getNiceTitleAndYear(folderName)
                displayText = '%4s - %s (%s)' % (runtime, niceTitle, year)

            elif displayStyle == displayStyles.FOLDER:
                folderName = item.data(QtCore.Qt.UserRole)['folder name']
                displayText = folderName
            item.setText(displayText)
            progress += 1
            self.progressBar.setValue(progress)

        self.statusBar().showMessage("Done")
        self.progressBar.setValue(0)

        if  displayStyle == displayStyles.TOTAL_ITEM or \
            displayStyle == displayStyles.RATING_TITLE_YEAR or \
            displayStyle == displayStyles.BOX_OFFICE_YEAR_TITLE or \
            displayStyle == displayStyles.RUNTIME_YEAR_TITLE:

            listWidget.sortItems(QtCore.Qt.DescendingOrder)
        else:
            listWidget.sortItems(QtCore.Qt.AscendingOrder)

    def downloadDataMenu(self, force=False, doJson=True, doCover=True):
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

            self.downloadMovieData(item, force, doJson=doJson, doCover=doCover)
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
                listItem.setBackground(QtGui.QColor(0, 0, 0))

    def populateCriteriaList(self, criteriaKey, listWidget, comboBoxWidget):
        """ criteriaKey is 'directors', 'actors', 'genres', 'years """
        if not self.smdbData:
            print("Error: No smbdData")
            return

        if criteriaKey not in self.smdbData:
            print("Error: '%s' not in smdbData" % criteriaKey)
            return

        numEntries = len(self.smdbData[criteriaKey].keys())
        message = "Populating list: %s with %s entries" % (criteriaKey, numEntries)
        self.statusBar().showMessage(message)
        QtCore.QCoreApplication.processEvents()

        self.progressBar.setMaximum(len(self.smdbData[criteriaKey].keys()))
        progress = 0

        listWidget.clear()
        displayStyle = self.getDisplayStyle(comboBoxWidget)
        for criteria in self.smdbData[criteriaKey].keys():
            numMovies = self.smdbData[criteriaKey][criteria]['num movies']
            #print("criteria = %s numMovies = %s" % (criteria, numMovies))

            if displayStyle == displayStyles.TOTAL_ITEM:
                displayText = '(%04d) %s' % (numMovies, criteria)
            elif displayStyle == displayStyles.ITEM_TOTAL:
                displayText = '%s (%04d)' % (criteria, numMovies)
            item = QtWidgets.QListWidgetItem(displayText)
            userData = {}
            userData['criteria'] = criteria
            userData['criteria key'] = criteriaKey
            userData['list widget'] = listWidget
            item.setData(QtCore.Qt.UserRole, userData)
            listWidget.addItem(item)
            progress += 1
            self.progressBar.setValue(progress)
        if displayStyle == displayStyles.TOTAL_ITEM or displayStyle == displayStyles.RATING_TITLE_YEAR:
            listWidget.sortItems(QtCore.Qt.DescendingOrder)
        else:
            listWidget.sortItems(QtCore.Qt.AscendingOrder)
        self.progressBar.setValue(0)

    def setMovieItemUserData(self, item, folderName, data):
        userData = {}
        userData['folder name'] = folderName
        userData['path'] = os.path.join(self.moviesFolder, folderName)
        if not data:
            item.setData(QtCore.Qt.UserRole, userData)
            return userData

        if 'title' in data:
            userData['title'] = data['title']
        else:
            userData['title'] = ''

        if 'year' in data:
            userData['year'] = data['year']
        else:
            userData['year'] = ''

        if 'rating' in data:
            userData['rating'] = data['rating']
        else:
            userData['rating'] = ''

        if 'box office' in data:
            userData['box office'] = data['box office']
        else:
            userData['box office'] = ''

        if 'id' in data:
            userData['id'] = data['id']
        else:
            userData['id'] = ''

        if 'runtime' in data:
            userData['runtime'] = data['runtime']
        else:
            userData['runtime'] = ''

        item.setData(QtCore.Qt.UserRole, userData)
        return userData

    def populateMovieList(self, forceScan=False):
        self.moviesList.clear()
        self.numVisibleMovies = 0
        if not os.path.exists(self.moviesFolder):
            return

        movieList = []

        useSmdbData = False
        if not forceScan and self.smdbData and 'titles' in self.smdbData:
            useSmdbData = True
            for title in self.smdbData['titles']:
                movieList.append(title)
        else:
            with os.scandir(self.moviesFolder) as files:
                for f in files:
                    if f.is_dir() and fnmatch.fnmatch(f, '*(*)'):
                        movieList.append(f.name)
                    else:
                        print("Not adding folder: %s" % f.name)

        progress = 0
        self.progressBar.setMaximum(len(movieList))

        for folderName in movieList:
            item = QtWidgets.QListWidgetItem(folderName)
            data = {}
            if useSmdbData:
                data = self.smdbData['titles'][folderName]
            else:
                jsonFile = os.path.join(self.moviesFolder, folderName, '%s.json' % folderName)
                if os.path.exists(jsonFile):
                    with open(jsonFile) as f:
                        try:
                            data = json.load(f)
                        except UnicodeDecodeError:
                            item.setForeground(QtGui.QColor(255, 0, 0))
                            print("Error reading %s" % jsonFile)

            self.setMovieItemUserData(item, folderName, data)
            self.moviesList.addItem(item)
            self.numVisibleMovies += 1
            progress += 1
            self.progressBar.setValue(progress)
        print("numVisibleMovies = %s" % self.numVisibleMovies)
        self.progressBar.setValue(0)
        if forceScan:
            self.setMovieListItemColors()
        self.listDisplayStyleChanged(self.moviesComboBox, self.moviesList)

    def cancelButtonClicked(self):
        self.isCanceled = True

    def showMovieSelectionStatus(self):
        numSelected = len(self.moviesList.selectedItems())
        self.statusBar().showMessage('%s/%s' % (numSelected, self.numVisibleMovies))

    def movieSelectionChanged(self):
        self.showMovieSelectionStatus()
        numSelected = len(self.moviesList.selectedItems())
        if numSelected == 1:
            self.clickedMovie(self.moviesList.selectedItems()[0])

    def criteriaSelectionChanged(self, listWidget, smdbKey):
        if len(listWidget.selectedItems()) == 0:
            for row in range(self.moviesList.count()):
                self.moviesList.item(row).setHidden(False)
            return

        criteriaMovieList = []
        for item in listWidget.selectedItems():
            criteria = item.text()
            userData = item.data(QtCore.Qt.UserRole)
            movies = self.smdbData[smdbKey][userData['criteria']]['movies']
            for movie in movies:
                if movie not in criteriaMovieList:
                    criteriaMovieList.append(movie)

        self.numVisibleMovies = 0
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
                    self.numVisibleMovies += 1
                    self.moviesList.item(row).setHidden(False)
            progress += 1
            self.progressBar.setValue(progress)

        self.progressBar.setValue(0)
        self.showMovieSelectionStatus()

    def clickedMovie(self, listItem):
        try:
            moviePath = listItem.data(QtCore.Qt.UserRole)['path']
            folderName = listItem.data(QtCore.Qt.UserRole)['folder name']
            title = listItem.data(QtCore.Qt.UserRole)['title']
            year = listItem.data(QtCore.Qt.UserRole)['year']
            jsonFile = os.path.join(moviePath, '%s.json' % folderName)
            coverFile = os.path.join(moviePath, '%s.jpg' % folderName)
            if not os.path.exists(coverFile):
                coverFilePng = os.path.join(moviePath, '%s.png' % folderName)
                if os.path.exists(coverFilePng):
                    coverFile = coverFilePng

            self.showCoverFile(coverFile)
            self.showSummary(jsonFile)
            self.movieTitle.setText('%s (%s)' % (title, year))
        except:
            print("Error with movie %s" % listItem.text())

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

    def resizeCoverFile(self):
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

    def showSummary(self, jsonFile):
        if os.path.exists(jsonFile):
            with open(jsonFile) as f:
                try:
                    data = json.load(f)
                    summary = ''
                    if 'rating' in data and data['rating']:
                        summary += 'Rating: %s<br>' % data['rating']
                    if 'runtime' in data and data['runtime']:
                        summary += 'Runtime: %s minutes<br>' % data['runtime']
                    if 'genres' in data and data['genres']:
                        summary += 'Genres: '
                        for genre in data['genres']:
                            summary += '%s, ' % genre
                        summary += '<br>'
                    if 'box office' in data and data['box office']:
                        summary += 'Box Office: %s<br>' % data['box office']
                    if 'director' in data and data['director']:
                        summary += '<br>Directed by: %s<br>' % data['director'][0]
                    if 'plot' in data and data['plot']:
                        summary += '<br>Plot:<br>'
                        if isinstance(data['plot'], list):
                            summary += data['plot'][0]
                    if 'cast' in data and data['cast']:
                        summary += '<br><br>Cast:<br>'
                        for c in data['cast']:
                            summary += '%s<br>' % c
                    else:
                        summary = data['summary']
                    summary = '<span style=\" color: #ffffff; font-size: 12pt\">%s</span>' % summary
                    self.summary.setText(summary)
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

    def downloadMovieData(self, listItem, force=False, movieId=None, doJson=True, doCover=True):
        moviePath = listItem.data(QtCore.Qt.UserRole)['path']
        folderName = listItem.data(QtCore.Qt.UserRole)['folder name']
        jsonFile = os.path.join(moviePath, '%s.json' % folderName)
        coverFile = os.path.join(moviePath, '%s.jpg' % folderName)
        if not os.path.exists(coverFile):
            coverFilePng = os.path.join(moviePath, '%s.png' % folderName)
            if os.path.exists(coverFilePng):
                coverFile = coverFilePng

        if force is True or not os.path.exists(jsonFile) or not os.path.exists(coverFile):
            if movieId:
                movie = self.getMovieWithId(movieId)
            else:
                movie = self.getMovie(folderName)
            if not movie:
                return coverFile
            self.db.update(movie)
            if doJson:
                self.writeMovieJson(movie, jsonFile)
            if doCover:
                coverFile = copyCoverImage(movie, coverFile)
            self.setMovieItemUserData(listItem, folderName, movie)

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
                    extension == '.mpg' or \
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
        if os.path.exists(filePath):
            os.startfile(filePath)
        else:
            print("Folder doesn't exist")

    def openMovieJson(self):
        selectedMovie = self.moviesList.selectedItems()[0]
        moviePath = selectedMovie.data(QtCore.Qt.UserRole)['path']
        folderName = selectedMovie.data(QtCore.Qt.UserRole)['folder name']
        jsonFile = os.path.join(moviePath, '%s.json' % folderName)
        if os.path.exists(jsonFile):
            os.startfile(jsonFile)
        else:
            print("jsonFile: %s doesn't exist" % jsonFile)

    def openMovieImdbPage(self):
        selectedMovie = self.moviesList.selectedItems()[0]
        movieId = selectedMovie.data(QtCore.Qt.UserRole)['id']
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
            listItem = self.moviesList.currentItem()
            self.downloadMovieData(listItem, True, movieId)

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

        self.openJsonAction = QtWidgets.QAction("Open Json File", self)
        self.openJsonAction.triggered.connect(lambda: self.openMovieJson())
        self.rightMenu.addAction(self.openJsonAction)

        self.openImdbAction = QtWidgets.QAction("Open IMDB Page", self)
        self.openImdbAction.triggered.connect(lambda: self.openMovieImdbPage())
        self.rightMenu.addAction(self.openImdbAction)

        self.overrideImdbAction = QtWidgets.QAction("Override IMDB ID", self)
        self.overrideImdbAction.triggered.connect(lambda: self.overrideID())
        self.rightMenu.addAction(self.overrideImdbAction)

        self.downloadDataAction = QtWidgets.QAction("Download Data", self)
        self.downloadDataAction.triggered.connect(lambda: self.downloadDataMenu())
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
    QtCore.QCoreApplication.processEvents()
    win.refresh()
    sys.exit(app.exec_())


window()
