from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtWidgets import QApplication, QMessageBox
import sys
import os
import fnmatch
from imdb import IMDb
from imdb import Movie
import re
import urllib.request
import subprocess
import json

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


class MyWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super(MyWindow, self).__init__()

        self.movieDirPattern = "*(*)"
        self.moviesBaseDir = "J:/Movies"
        self.moviePlayer = "C:/Program Files/MPC-HC/mpc-hc64.exe"

        self.db = IMDb()
        self.initUI()
        self.populateMovieList()

        self.setGeometry(0, 0, 1000, 700)
        self.setWindowTitle("Movie Database")

    def seachMovieList(self):
        searchText = self.movieListSearchBox.text()
        if searchText == "":
            for row in range(self.movieList.count()):
                self.movieList.item(row).setHidden(False)
        else:
            for row in range(self.movieList.count()):
                self.movieList.item(row).setHidden(True)
            for foundItem in self.movieList.findItems(searchText, QtCore.Qt.MatchContains):
                foundItem.setHidden(False)
                print(foundItem.text())

    def initUI(self):
        mainVLayout = QtWidgets.QVBoxLayout(self)

        hSplitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal, self)
        mainVLayout.addWidget(hSplitter)

        movieListWidget = QtWidgets.QWidget(self)
        hSplitter.addWidget(movieListWidget)

        movieListVLayout = QtWidgets.QVBoxLayout(self)
        movieListWidget.setLayout(movieListVLayout)

        self.movieListComboBox = QtWidgets.QComboBox(self)
        self.movieListComboBox.addItem("Folder Names")
        self.movieListComboBox.addItem("Nice Names")
        self.movieListComboBox.addItem("Nice Names Year First")
        self.movieListComboBox.activated.connect(self.movieListComboBoxChanged)
        movieListVLayout.addWidget(self.movieListComboBox)

        self.movieListSearchBox = QtWidgets.QLineEdit(self)
        self.movieListSearchBox.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Maximum)
        self.movieListSearchBox.textChanged.connect(self.seachMovieList)
        movieListVLayout.addWidget(self.movieListSearchBox)

        self.movieList = QtWidgets.QListWidget(self)
        self.movieList.itemSelectionChanged.connect(self.movieSelectionChanged)
        self.movieList.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.movieList.customContextMenuRequested[QtCore.QPoint].connect(self.rightMenuShow)
        self.movieList.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        movieListVLayout.addWidget(self.movieList)

        vSplitter = QtWidgets.QSplitter(QtCore.Qt.Vertical, self)
        hSplitter.addWidget(vSplitter)

        self.movieCover = QtWidgets.QLabel(self)
        self.movieCover.setScaledContents(False)
        self.movieCover.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Ignored)
        vSplitter.addWidget(self.movieCover)

        self.summary = QtWidgets.QTextBrowser()
        vSplitter.addWidget(self.summary)

        bottomLayout = QtWidgets.QHBoxLayout(self)
        mainVLayout.addLayout(bottomLayout)

        self.progressBar = QtWidgets.QProgressBar(self)
        self.progressBar.setMaximum(100)
        bottomLayout.addWidget(self.progressBar)

        cancelButton = QtWidgets.QPushButton("Cancel", self)
        cancelButton.clicked.connect(self.cancelButtonClicked)
        bottomLayout.addWidget(cancelButton)

        centralWidget = QtWidgets.QWidget()
        centralWidget.setLayout(mainVLayout)
        self.setCentralWidget(centralWidget)

    def movieListComboBoxChanged(self):
        currentIndex = self.movieListComboBox.currentIndex()
        if currentIndex == 0:  # Folder Names
            for row in range(self.movieList.count()):
                item = self.movieList.item(row)
                folderName = item.data(QtCore.Qt.UserRole)['folder name']
                item.setText(folderName)
        elif currentIndex == 1:  # Nice Names
            for row in range(self.movieList.count()):
                item = self.movieList.item(row)
                folderName = item.data(QtCore.Qt.UserRole)['folder name']
                niceTitle, year = getNiceTitleAndYear(folderName)
                item.setText('%s (%s)' % (niceTitle, year))
        else:  # Nice Names Year First
            for row in range(self.movieList.count()):
                item = self.movieList.item(row)
                folderName = item.data(QtCore.Qt.UserRole)['folder name']
                niceTitle, year = getNiceTitleAndYear(folderName)
                item.setText('%s - %s' % (year, niceTitle))
        self.movieList.sortItems()


    def downloadDataMenu(self):
        numSelectedItems = len(self.movieList.selectedItems())
        self.progressBar.setMaximum(numSelectedItems)
        progress = 0
        self.isCanceled = False
        for item in self.movieList.selectedItems():
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

            self.downloadMovieData(item)
            self.clickedMovie(item)

            progress += 1
            self.progressBar.setValue(progress)
        self.statusBar().showMessage("Done")
        self.progressBar.setValue(0)
        self.setMovieListItemColors()

    def removeJsonFilesMenu(self):
        filesToDelete = []
        for item in self.movieList.selectedItems():
            moviePath = item.data(QtCore.Qt.UserRole)['path']
            movieFolder = item.data(QtCore.Qt.UserRole)['folder name']
            jsonFile = os.path.join(moviePath, '%s.json' % movieFolder)
            if (os.path.exists(jsonFile)):
                filesToDelete.append(os.path.join(moviePath, jsonFile))
        removeFiles(self, filesToDelete, '.json')
        self.setMovieListItemColors()

    def removeCoverFilesMenu(self):
        filesToDelete = []
        for item in self.movieList.selectedItems():
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
        for row in range(self.movieList.count()):
            listItem = self.movieList.item(row)
            moviePath = listItem.data(QtCore.Qt.UserRole)['path']
            movieFolder = listItem.data(QtCore.Qt.UserRole)['folder name']
            jsonFile = os.path.join(moviePath, '%s.json' % movieFolder)
            if not os.path.exists(jsonFile):
                listItem.setBackground(QtGui.QColor(220, 220, 220))
            else:
                listItem.setBackground(QtGui.QColor(255, 255, 255))

    def populateMovieList(self):
        with os.scandir(self.moviesBaseDir) as files:
            for f in files:
                if f.is_dir() and fnmatch.fnmatch(f, self.movieDirPattern):
                    item = QtWidgets.QListWidgetItem(f.name)
                    userData = {}
                    userData['folder name'] = f.name
                    userData['path'] = os.path.join(self.moviesBaseDir, f.name)
                    item.setData(QtCore.Qt.UserRole, userData)
                    self.movieList.addItem(item)
        self.setMovieListItemColors()
        firstItem = self.movieList.item(0)
        self.movieList.setCurrentItem(firstItem)
        #self.clickedMovie(firstItem)

    def cancelButtonClicked(self):
        self.isCanceled = True

    def movieSelectionChanged(self):
        numSelected = len(self.movieList.selectedItems())
        total = self.movieList.count()
        self.statusBar().showMessage('%s/%s' % (numSelected, total))
        if numSelected == 1:
            self.clickedMovie(self.movieList.selectedItems()[0])

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
            print('Problem converting year to integer for movie: %s' % movieName)
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
                if res['year'] == year and res['kind'] == 'movie':
                    print("Matched year: %s" % year)
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
                d['director'] = str(director[0]['name'])
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

        if not os.path.exists(jsonFile):
            with open(jsonFile, "w") as f:
                json.dump(d, f, indent=4)

    def downloadMovieData(self, listItem):
        moviePath = listItem.data(QtCore.Qt.UserRole)['path']
        folderName = listItem.data(QtCore.Qt.UserRole)['folder name']
        mdbFile = os.path.join(moviePath, '%s.mdb' % folderName)
        jsonFile = os.path.join(moviePath, '%s.json' % folderName)
        coverFile = os.path.join(moviePath, '%s.jpg' % folderName)
        if not os.path.exists(coverFile):
            coverFilePng = os.path.join(moviePath, '%s.png' % folderName)
            if os.path.exists(coverFilePng):
                coverFile = coverFilePng

        if not os.path.exists(jsonFile) or not os.path.exists(coverFile):
            movie = self.getMovie(folderName)
            if not movie:
                return coverFile
            self.db.update(movie)

        if not os.path.exists(jsonFile):
            self.writeMovieJson(movie, jsonFile)

        if not os.path.exists(coverFile):
            coverFile = copyCoverImage(movie, coverFile)

        return coverFile

    def playMovie(self):
        selectedMovie = self.movieList.selectedItems()[0]
        filePath = selectedMovie.data(QtCore.Qt.UserRole)['path']
        movieFiles = []
        for file in os.listdir(filePath):
            extension = os.path.splitext(file)[1]
            if extension == '.mkv' or \
                    extension == '.mp4' or \
                    extension == '.avi' or \
                    extension == '.avi' or \
                    extension == '.m4v':
                movieFiles.append(file)
        if len(movieFiles) == 1:
            fileToPlay = os.path.join(filePath, movieFiles[0])
            print("Playing Movie: %s" % fileToPlay)
            subprocess.run([self.moviePlayer, fileToPlay])
        else:
            # If there are more than one movie like files in the
            # folder, then just open the folder so the user can
            # play the desired file.
            os.startfile(filePath)

    def openMovieFolder(self):
        selectedMovie = self.movieList.selectedItems()[0]
        filePath = selectedMovie.data(QtCore.Qt.UserRole)['path']
        os.startfile(filePath)

    def rightMenuShow(self, QPos):
        self.rightMenu = QtWidgets.QMenu(self.movieList)

        selectedMovie = self.movieList.selectedItems()[0]
        self.clickedMovie(selectedMovie)

        self.playAction = QtWidgets.QAction("Play", self)
        self.playAction.triggered.connect(lambda: self.playMovie())
        self.rightMenu.addAction(self.playAction)

        self.openFolderAction = QtWidgets.QAction("Open Folder", self)
        self.openFolderAction.triggered.connect(lambda: self.openMovieFolder())
        self.rightMenu.addAction(self.openFolderAction)

        self.downloadDataAction = QtWidgets.QAction("Download Data", self)
        self.downloadDataAction.triggered.connect(lambda: self.downloadDataMenu())
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
