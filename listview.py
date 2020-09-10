from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtWidgets import QApplication, QSplitter
import sys
import os
import fnmatch
from imdb import IMDb
import re
import urllib.request
import subprocess

# TODO: Add progress bar and button to get movie summaries
# TODO: Create separate derived class for movie list and move methods


def splitCamelCase(inputText):
    return re.sub('([A-Z][a-z]+)', r' \1', re.sub('([A-Z]+)', r' \1', inputText)).split()


def copyCoverImage(movie, coverFile):
    movieCoverUrl = ''
    if 'full-size cover url' in movie:
        movieCoverUrl = movie['full-size cover url']
    elif 'cover' in movie:
        movieCoverUrl = movie['cover url']
    urllib.request.urlretrieve(movieCoverUrl, coverFile)


class MyWindow(QtWidgets.QWidget):
    def __init__(self):
        super(MyWindow, self).__init__()

        self.movieDirPattern = "*(*)"
        self.moviesBaseDir = "J:\Movies"
        self.moviePlayer = "C:/Program Files/MPC-HC/mpc-hc64.exe"

        self.db = IMDb()
        self.initUI()
        self.setGeometry(0, 0, 1000, 700)
        self.setWindowTitle("Movie Database")

    def initUI(self):
        self.layout = QtWidgets.QHBoxLayout(self)

        self.splitter = QtWidgets.QSplitter(self)
        self.layout.addWidget(self.splitter)

        self.movieList = QtWidgets.QListWidget(self)
        self.movieList.itemClicked.connect(self.clicked)
        starWarsItem = None
        with os.scandir(self.moviesBaseDir) as files:
            for f in files:
                if f.is_dir() and fnmatch.fnmatch(f, self.movieDirPattern):
                    item = QtWidgets.QListWidgetItem(f.name)
                    moviePath = os.path.join(self.moviesBaseDir, item.text())
                    item.setData(QtCore.Qt.UserRole, moviePath)
                    self.movieList.addItem(item)
                    if (f.name == 'StarWars-Episode-5-TheEmpireStrikesBack(1980)'):
                        starWarsItem = item
        self.movieList.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.movieList.customContextMenuRequested[QtCore.QPoint].connect(self.rightMenuShow)
        self.splitter.addWidget(self.movieList)

        self.movieCover = QtWidgets.QLabel(self)
        self.movieCover.setScaledContents(False)
        self.movieCover.setObjectName("photo")
        self.movieCover.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.splitter.addWidget(self.movieCover)

        if (starWarsItem):
            self.movieList.setCurrentItem(starWarsItem)
            self.clicked(starWarsItem)

    def clicked(self, item):
        moviePath = item.data(QtCore.Qt.UserRole)
        fullTitle = item.text()
        mdbFile = os.path.join(moviePath, '%s.mdb' % fullTitle)
        coverFile = os.path.join(moviePath, '%s.jpg' % fullTitle)

        if not os.path.exists(mdbFile):
            self.downloadMovieData(fullTitle, mdbFile, coverFile)

        if os.path.exists(mdbFile):
            with open(mdbFile) as f:
                summary = f.read()

            print(summary)
        else:
            print("Error reading mdb file: %s" % mdbFile)

        if os.path.exists(coverFile):
            self.showCoverFile(coverFile)
        else:
            print("Error reading cover file: %s" % coverFile)

    def getMovie(self, movieName) -> object:
        m = re.match(r'(.*)\((.*)\)', movieName)
        title = m.group(1)
        year = m.group(2)
        splitTitle = splitCamelCase(title)

        searchText = '%s %s' % (' '.join(splitTitle), year)

        print('\nSearching for: "%s"' % searchText)

        results = self.db.search_movie(searchText)
        if not results:
            print('No matches for: %s' % movieName)
            return
        else:
            print("Found it!")

        movie = results[0]

        return movie

    def showCoverFile(self, coverFile):
        pixMap = QtGui.QPixmap(coverFile)
        self.movieCover.setPixmap(pixMap.scaled(500, 500,
                                                QtCore.Qt.KeepAspectRatio,
                                                QtCore.Qt.SmoothTransformation))

    def downloadMovieData(self, movieFolderName, mdbFile, coverFile):
        movie = self.getMovie(movieFolderName)
        self.db.update(movie)

        if not os.path.exists(mdbFile):
            with open(mdbFile, "w") as f:
                print(movie.summary(), file=f)

        if not os.path.exists(coverFile):
            copyCoverImage(movie, coverFile)

    def playMovie(self):
        selectedMovie = self.movieList.selectedItems()[0]
        filePath = selectedMovie.data(QtCore.Qt.UserRole)
        movieFiles = []
        for file in os.listdir(filePath):
            extension = os.path.splitext(file)[1]
            if extension == '.mkv' or \
                    extension == '.mp4' or \
                    extension == '.avi' or \
                    extension == '.wmv':
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
        filePath = selectedMovie.data(QtCore.Qt.UserRole)
        os.startfile(filePath)

    def rightMenuShow(self, QPos):
        self.rightMenu = QtWidgets.QMenu(self.movieList)

        selectedMovie = self.movieList.selectedItems()[0]
        self.clicked(selectedMovie)

        self.playAction = QtWidgets.QAction("Play", self)
        self.playAction.triggered.connect(lambda: self.playMovie())
        self.rightMenu.addAction(self.playAction)

        self.openFolderAction = QtWidgets.QAction("Open Folder", self)
        self.openFolderAction.triggered.connect(lambda: self.openMovieFolder())
        self.rightMenu.addAction(self.openFolderAction)

        self.rightMenu.exec_(QtGui.QCursor.pos())


def window():
    app = QApplication(sys.argv)
    win = MyWindow()
    win.show()
    sys.exit(app.exec_())


window()
