from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import Qt, QThread, QObject, pyqtSignal
from PyQt5.QtWidgets import QApplication, QSplitter, QMessageBox
import sys
import os
import fnmatch
from imdb import IMDb
import re
import urllib.request
import subprocess
import time

# TODO: Add progress bar and button to get movie summaries
# TODO: Create separate derived class for movie list and move methods
# TODO: Change colors to dark
# TODO: Add summary panel

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


class MyWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super(MyWindow, self).__init__()

        self.movieDirPattern = "*(*)"
        self.moviesBaseDir = "J:/Movies"
        self.moviePlayer = "C:/Program Files/MPC-HC/mpc-hc64.exe"

        self.db = IMDb()
        self.initUI()
        self.setGeometry(0, 0, 1000, 700)
        self.setWindowTitle("Movie Database")

    def removeFiles(self, filesToDelete, extension):
        if len(filesToDelete) > 0:
            ret = QMessageBox.question(self,
                                       'Confirm Delete',
                                       'Really remove %d %s files?' % (len(filesToDelete), extension),
                                       QMessageBox.Yes | QMessageBox.No,
                                       QMessageBox.No)

            if ret == QMessageBox.Yes:
                for f in filesToDelete:
                    print('Deleting file: %s' % f)
                    os.remove(f)

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
                break

            message = "Downloading data (%d/%d): %s" % (progress,
                                                        numSelectedItems,
                                                        item.text())
            self.statusBar().showMessage(message)
            QtCore.QCoreApplication.processEvents()

            self.downloadMovieData(item)

            progress += 1
            self.progressBar.setValue(progress)

    def removeMdbFilesMenu(self):
        filesToDelete = []
        for item in self.movieList.selectedItems():
            moviePath = item.data(QtCore.Qt.UserRole)
            mdbFile = os.path.join(moviePath, '%s.mdb' % item.text())
            if (os.path.exists(mdbFile)):
                filesToDelete.append(os.path.join(moviePath, mdbFile))
        self.removeFiles(filesToDelete, '.mdb')

    def removeCoverFilesMenu(self):
        filesToDelete = []
        for item in self.movieList.selectedItems():
            moviePath = item.data(QtCore.Qt.UserRole)
            coverFile = os.path.join(moviePath, '%s.jpg' % item.text())
            if os.path.exists(coverFile):
                filesToDelete.append(coverFile)
            else:
                coverFile = os.path.join(moviePath, '%s.png' % item.text())
                if os.path.exists(coverFile):
                    filesToDelete.append(coverFile)

        self.removeFiles(filesToDelete, '.jpg')

    def initUI(self):

        # Menus
        #self.taskMenu = self.menuBar().addMenu("Tasks")

        # Layout
        self.layout = QtWidgets.QVBoxLayout(self)

        self.splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal, self)
        self.layout.addWidget(self.splitter)

        self.movieList = QtWidgets.QListWidget(self)
        self.movieList.itemClicked.connect(self.clickedMovie)
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
        self.movieList.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.splitter.addWidget(self.movieList)

        self.vSplitter = QtWidgets.QSplitter(QtCore.Qt.Vertical, self)
        self.splitter.addWidget(self.vSplitter)

        self.movieCover = QtWidgets.QLabel(self)
        self.movieCover.setScaledContents(False)
        self.movieCover.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Ignored)
        self.vSplitter.addWidget(self.movieCover)

        self.summary = QtWidgets.QTextBrowser()
        self.vSplitter.addWidget(self.summary)

        self.bottomLayout = QtWidgets.QHBoxLayout(self)
        self.layout.addLayout(self.bottomLayout)

        self.goButton = QtWidgets.QPushButton("Go", self)
        self.goButton.clicked.connect(self.goButtonClicked)
        self.bottomLayout.addWidget(self.goButton)

        self.progressBar = QtWidgets.QProgressBar(self)
        self.progressBar.setMaximum(100)
        self.bottomLayout.addWidget(self.progressBar)

        self.cancelButton = QtWidgets.QPushButton("Cancel", self)
        self.cancelButton.clicked.connect(self.cancelButtonClicked)
        self.bottomLayout.addWidget(self.cancelButton)

        self.centralWidget = QtWidgets.QWidget()
        self.centralWidget.setLayout(self.layout)
        self.setCentralWidget(self.centralWidget)

        self.statusBar().showMessage('Welcome to MDB.  Current number of movies: %d' % self.movieList.count())

        if (starWarsItem):
            self.movieList.setCurrentItem(starWarsItem)
            self.clickedMovie(starWarsItem)

    def goButtonClicked(self):
        self.isCanceled = False
        progressMax = 1000000
        self.progressBar.setMaximum(progressMax)
        count = 0
        while count < progressMax:
            QtCore.QCoreApplication.processEvents()
            if self.isCanceled == True:
                self.isCanceled = False
                self.progressBar.setValue(0)
                break
            self.progressBar.setValue(count)
            count += 1

    def cancelButtonClicked(self):
        self.isCanceled = True

    def clickedMovie(self, listItem):
        moviePath = listItem.data(QtCore.Qt.UserRole)
        fullTitle = listItem.text()
        mdbFile = os.path.join(moviePath, '%s.mdb' % fullTitle)
        coverFile = os.path.join(moviePath, '%s.jpg' % fullTitle)
        if not os.path.exists(coverFile):
            coverFilePng = os.path.join(moviePath, '%s.png' % fullTitle)
            if os.path.exists(coverFilePng):
                coverFile = coverFilePng

        if os.path.exists(mdbFile):
            with open(mdbFile) as f:
                summary = f.read()
            self.summary.setText(summary)

        if os.path.exists(coverFile):
            self.showCoverFile(coverFile)

    def getMovie(self, movieName) -> object:
        m = re.match(r'(.*)\((.*)\)', movieName)
        title = m.group(1)
        year = m.group(2)
        splitTitle = splitCamelCase(title)

        #searchText = '%s %s' % (' '.join(splitTitle), year)
        searchText = ' '.join(splitTitle)

        results = self.db.search_movie(searchText)
        if not results:
            print('No matches for: %s' % movieName)
            return

        movie = results[0]
        for res in results:
            if int(res['year']) == int(year) and res['kind'] == 'movie':
                movie = res
                break

        return movie

    def showCoverFile(self, coverFile):
        pixMap = QtGui.QPixmap(coverFile)
        self.movieCover.setPixmap(pixMap.scaled(500, 500,
                                                QtCore.Qt.KeepAspectRatio,
                                                QtCore.Qt.SmoothTransformation))

    def downloadMovieData(self, listItem):
        moviePath = listItem.data(QtCore.Qt.UserRole)
        fullTitle = listItem.text()
        mdbFile = os.path.join(moviePath, '%s.mdb' % fullTitle)
        coverFile = os.path.join(moviePath, '%s.jpg' % fullTitle)
        if not os.path.exists(coverFile):
            coverFilePng = os.path.join(moviePath, '%s.png' % fullTitle)
            if os.path.exists(coverFilePng):
                coverFile = coverFilePng

        if not os.path.exists(mdbFile) or not os.path.exists(coverFile):
            movie = self.getMovie(fullTitle)
            self.db.update(movie)

            if not os.path.exists(mdbFile):
               with open(mdbFile, "w") as f:
                   print(movie.summary(), file=f)

            if not os.path.exists(coverFile):
                coverFile = copyCoverImage(movie, coverFile)

        return coverFile

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

        self.removeMdbAction = QtWidgets.QAction("Remove .mdb files", self)
        self.removeMdbAction.triggered.connect(lambda: self.removeMdbFilesMenu())
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
