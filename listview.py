from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtWidgets import QApplication, QSplitter
import sys
import os
import fnmatch
from imdb import IMDb
import re
import urllib.request


def splitCamelCase(input):
    return re.sub('([A-Z][a-z]+)', r' \1', \
                  re.sub('([A-Z]+)', \
                         r' \1', input)).split()


class MyWindow(QtWidgets.QWidget):
    def __init__(self):
        super(MyWindow, self).__init__()
        self.db = IMDb()
        self.initUI()
        self.setGeometry(0, 0, 1000, 700)
        self.setWindowTitle("Movie Database")

    def getMovie(self, movieName) -> object:
        m = re.match('(.*)\((.*)\)', movieName)
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

    def copyCoverImage(self, movie, outputFile):
        if not os.path.exists(outputFile):
            movieCoverUrl = ''
            # If the file doesn't exist, download it
            if movie.has_key('full-size cover url'):
                movieCoverUrl = movie['full-size cover url']
            elif movie.has_key('cover'):
                movieCoverUrl = movie['cover url']
            print("Movie Cover: %s" % movieCoverUrl)
            urllib.request.urlretrieve(movieCoverUrl, outputFile)

    def clicked(self, item):
        baseDir = item.data(QtCore.Qt.UserRole)
        fullTitle = item.text()
        outputCoverFile = "%s/%s/%s.jpg" % (baseDir, fullTitle, fullTitle)
        print('outputCoverFile = %s' % outputCoverFile)
        outputCoverFileExists = False
        if os.path.exists(outputCoverFile):
            outputCoverFileExists = True
            print("cover file: %s exists" % outputCoverFile)
            pixMap = QtGui.QPixmap(outputCoverFile)
            print("setPixmap")
            self.movieCover.setPixmap(pixMap.scaled(500, 500,
                                                    QtCore.Qt.KeepAspectRatio,
                                                    QtCore.Qt.SmoothTransformation))
            self.movieCover.show()
        else:
            print("File doesn't exist: %s", outputCoverFile)

        movie = self.getMovie(fullTitle)
        self.db.update(movie)

        if not outputCoverFileExists:
            self.copyCoverImage(movie, outputCoverFile)
            pixMap = QtGui.QPixmap(outputCoverFile)
            self.movieCover.setPixmap(pixMap.scaled(500, 500,
                                                    QtCore.Qt.KeepAspectRatio,
                                                    QtCore.Qt.SmoothTransformation))

        print(movie.summary())

    def rightMenuClick(self, text):
        if text == "Play":
            print(text)

    def rightMenuShow(self, QPos):
        self.removeAction = QtWidgets.QAction("Play", self)
        self.removeAction.triggered.connect(lambda: self.rightMenuClick("Play"))

        self.rightMenu = QtWidgets.QMenu(self.movieList)
        self.rightMenu.addAction(self.removeAction)
        self.rightMenu.exec_(QtGui.QCursor.pos())

    def initUI(self):
        movieDirPattern = "*(*)"
        moviesBaseDir = "J:/Movies"

        self.layout = QtWidgets.QHBoxLayout(self)

        self.splitter = QtWidgets.QSplitter(self)
        self.layout.addWidget(self.splitter)

        self.movieList = QtWidgets.QListWidget(self)
        self.movieList.itemClicked.connect(self.clicked)
        starWarsItem = None
        with os.scandir(moviesBaseDir) as files:
            for f in files:
                if f.is_dir() and fnmatch.fnmatch(f, movieDirPattern):
                    item = QtWidgets.QListWidgetItem(f.name)
                    item.setData(QtCore.Qt.UserRole, moviesBaseDir)
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


def window():
    app = QApplication(sys.argv)
    win = MyWindow()
    win.show()
    sys.exit(app.exec_())


window()
