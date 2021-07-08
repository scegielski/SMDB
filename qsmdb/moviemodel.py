import json
import fnmatch
import pathlib
import datetime
from enum import Enum
from PyQt5 import QtGui, QtCore

from .utilities import *


class MoviesTableModel(QtCore.QAbstractTableModel):
    emitCoverSignal = QtCore.pyqtSignal(int)

    def __init__(self,
                 smdbData,
                 moviesFolders,
                 forceScan=False,
                 neverScan=False):

        super().__init__()

        self.movieSet = set()
        self._data = []

        self.Columns = Enum('Columns', ['Cover',
                                        'Year',
                                        'Title',
                                        'Rating',
                                        'MpaaRating',
                                        'BoxOffice',
                                        'Runtime',
                                        'Directors',
                                        'Countries',
                                        'Companies',
                                        'Genres',
                                        'UserTags',
                                        'Id',
                                        'Folder',
                                        'Path',
                                        'JsonExists',
                                        'Rank',
                                        'BackupStatus',
                                        'Duplicate',
                                        'Width',
                                        'Height',
                                        'Size',
                                        'DateModified'], start=0)

        self.defaultWidths = {self.Columns.Cover: 150,
                              self.Columns.Year: 50,
                              self.Columns.Title: 200,
                              self.Columns.Rating: 60,
                              self.Columns.MpaaRating: 100,
                              self.Columns.BoxOffice: 150,
                              self.Columns.Runtime: 60,
                              self.Columns.Directors: 150,
                              self.Columns.Countries: 150,
                              self.Columns.Companies: 150,
                              self.Columns.Genres: 150,
                              self.Columns.UserTags: 150,
                              self.Columns.Id: 60,
                              self.Columns.Folder: 200,
                              self.Columns.Path: 300,
                              self.Columns.JsonExists: 65,
                              self.Columns.Rank: 40,
                              self.Columns.BackupStatus: 150,
                              self.Columns.Duplicate: 60,
                              self.Columns.Width: 50,
                              self.Columns.Height: 50,
                              self.Columns.Size: 100,
                              self.Columns.DateModified: 150}

        # Create the header text from the enums
        self._headers = []
        for c in self.Columns:
            tokens = splitCamelCase(c.name)
            self._headers.append(' '.join(tokens))

        for moviesFolder in moviesFolders:
            if not os.path.exists(moviesFolder):
                return

        # Either read the list of movies from the smdb data
        # or scan the movies folder
        moviesFolderDict = dict()
        useSmdbData = False
        if neverScan and (not smdbData or 'titles' not in smdbData):
            return
        elif not forceScan and smdbData and 'titles' in smdbData:
            useSmdbData = True
            for path in smdbData['titles']:
                folder = smdbData['titles'][path]['folder']
                moviesFolderDict[path] = [folder, path]
        else:
            for moviesFolder in moviesFolders:
                numMovies = 0
                with os.scandir(moviesFolder) as files:
                    for f in files:
                        if f.is_dir() and fnmatch.fnmatch(f, '*(*)'):
                            folderName = f.name
                            moviePath = f.path
                            key = moviePath
                            if key in moviesFolderDict:
                                key = key + "duplicate"
                            moviesFolderDict[key] = [folderName, moviePath]
                            numMovies += 1
                        else:
                            print("Not adding: %s to movie list" % f.path)
                print(f"Scanned {numMovies} movies for {moviesFolder}")

        for key in moviesFolderDict.keys():
            movieFolderName = moviesFolderDict[key][0]
            moviePath = moviesFolderDict[key][1]
            data = {}
            if useSmdbData:
                data = smdbData['titles'][moviePath]
            else:
                jsonFile = os.path.join(moviePath,
                                        '%s.json' % movieFolderName)
                if os.path.exists(jsonFile):
                    with open(jsonFile) as f:
                        try:
                            data = json.load(f)
                        except UnicodeDecodeError:
                            print("Error reading %s" % jsonFile)

            movieData = self.createMovieData(data,
                                             moviePath,
                                             movieFolderName,
                                             False,  # Don't generate new rank here, it's for watch list
                                             forceScan)

            folderName = movieData[self.Columns.Folder.value]
            self.movieSet.add(folderName)
            self._data.append(movieData)

        # Sort by year
        self.sort(self.Columns.Year.value, QtCore.Qt.AscendingOrder)

    def createMovieData(self,
                        data,
                        moviePath,
                        movieFolderName,
                        generateNewRank=False,
                        force=False):

        movieData = []
        for column in self.Columns:
            if column == self.Columns.DateModified:
                if 'date' in data:
                    movieData.append(data['date'])
            elif column == self.Columns.Path:
                movieData.append(moviePath)
            elif column == self.Columns.JsonExists:
                if force:
                    jsonFile = os.path.join(moviePath, '%s.json' % movieFolderName)
                    if os.path.exists(jsonFile):
                        movieData.append("True")
                    else:
                        print(f"jsonFile {jsonFile} does not exist")
                        movieData.append("False")
                else:
                    movieData.append("")
            elif column == self.Columns.Folder:
                movieData.append(movieFolderName)
            elif column == self.Columns.Rank and generateNewRank:
                rank = len(self._data)
                movieData.append(rank)
            elif column == self.Columns.Countries:
                if 'countries' in data and data['countries']:
                    countries = ""
                    for country in data['countries']:
                        if country == data['countries'][-1]:
                            countries += '%s' % country
                        else:
                            countries += '%s, ' % country
                    movieData.append(countries)
                else:
                    movieData.append('')
            elif column == self.Columns.Companies:
                if 'companies' in data and data['companies']:
                    companies = ""
                    for company in data['companies']:
                        if company == data['companies'][-1]:
                            companies += '%s' % company
                        else:
                            companies += '%s, ' % company
                    movieData.append(companies)
                else:
                    movieData.append('')
            elif column == self.Columns.Genres:
                if 'genres' in data and data['genres']:
                    genres = ""
                    for genre in data['genres']:
                        if genre == data['genres'][-1]:
                            genres += '%s' % genre
                        else:
                            genres += '%s, ' % genre
                    movieData.append(genres)
                else:
                    movieData.append('')
            elif column == self.Columns.Directors:
                if 'directors' in data and data['directors']:
                    directors = ""
                    for director in data['directors']:
                        if director == data['directors'][-1]:
                            directors += '%s' % director
                        else:
                            directors += '%s, ' % director
                    movieData.append(directors)
                else:
                    movieData.append('')
            elif column == self.Columns.UserTags:
                if 'user tags' in data and data['user tags']:
                    userTags = ""
                    for userTag in data['user tags']:
                        if userTag == data['user tags'][-1]:
                            userTags += '%s' % userTag
                        else:
                            userTags += '%s, ' % userTag
                    movieData.append(userTags)
                else:
                    movieData.append('')
            else:
                # Get a lower case version of the header name
                # which matches the smdb data keys
                header = self._headers[column.value]
                headerLower = header.lower()
                if headerLower not in data:
                    if column == self.Columns.Title:
                        title, year = getNiceTitleAndYear(movieFolderName)
                        movieData.append(title)
                    elif column == self.Columns.Year:
                        title, year = getNiceTitleAndYear(movieFolderName)
                        movieData.append(year)
                    else:
                        movieData.append('')
                else:
                    if column == self.Columns.Runtime:
                        runtime = data[headerLower]
                        if not runtime:
                            runtime = '000'
                        else:
                            runtime = '%03d' % int(runtime)
                        movieData.append(runtime)
                    elif column == self.Columns.Rating:
                        rating = data[headerLower]
                        if not rating:
                            rating = '0.0'
                        else:
                            rating = str(rating)
                            if len(rating) == 1:
                                rating = '%s.0' % rating
                        movieData.append(rating)
                    elif column == self.Columns.MpaaRating:
                        mpaaRating = "No Rating"
                        if 'mpaa rating' in data and data['mpaa rating']:
                            mpaaRating = data['mpaa rating']
                        movieData.append(mpaaRating)
                    else:
                        movieData.append(data[headerLower])
        return movieData

    def setMovieDataWithJson(self, row, jsonFile, moviePath, movieFolderName):
        if os.path.exists(jsonFile):
            with open(jsonFile) as f:
                try:
                    data = json.load(f)
                except UnicodeDecodeError:
                    print("Error reading %s" % jsonFile)
        self.setMovieData(row, data, moviePath, movieFolderName)

    def setMovieData(self, row, data, moviePath, movieFolderName):
        movieData = self.createMovieData(data, moviePath, movieFolderName)
        self._data[row] = movieData
        minIndex = self.index(row, 0)
        maxIndex = self.index(row, self.getLastColumn())
        self.dataChanged.emit(minIndex, maxIndex)

    def getHeaders(self):
        return self._headers

    def getNumColumns(self):
        return len(self.Columns)

    def getLastColumn(self):
        return len(self.Columns) - 1

    def getMpaaRating(self, row):
        return self._data[row][self.Columns.MpaaRating.value]

    def getBackupStatus(self, row):
        return self._data[row][self.Columns.BackupStatus.value]

    def getYear(self, row):
        return self._data[row][self.Columns.Year.value]

    def getTitle(self, row):
        return self._data[row][self.Columns.Title.value]

    def getRating(self, row):
        return self._data[row][self.Columns.Rating.value]

    def getBoxOffice(self, row):
        return self._data[row][self.Columns.BoxOffice.value]

    def getRuntime(self, row):
        return self._data[row][self.Columns.Runtime.value]

    def getId(self, row):
        return self._data[row][self.Columns.Id.value]

    def getDimensions(self, row):
        width = self._data[row][self.Columns.Width.value]
        height = self._data[row][self.Columns.Height.value]
        return width, height

    def getFolderName(self, row):
        return self._data[row][self.Columns.Folder.value]

    def getPath(self, row):
        return self._data[row][self.Columns.Path.value]

    def getJsonExists(self, row):
        return self._data[row][self.Columns.JsonExists.value]

    def getRank(self, row):
        return self._data[row][self.Columns.Rank.value]

    def getSize(self, row):
        return self._data[row][self.Columns.Size.value]

    def getDuplicate(self, row):
        return self._data[row][self.Columns.Duplicate.value]

    def getDataSize(self):
        return len(self._data)

    def aboutToChangeLayout(self):
        self.layoutAboutToBeChanged.emit()

    def changedLayout(self):
        self.layoutChanged.emit()

    def addMovie(self, smdbData, moviePath):
        movieFolderName = os.path.basename(moviePath)
        if movieFolderName not in smdbData['titles']:
            return

        data = smdbData['titles'][movieFolderName]
        movieData = self.createMovieData(data,
                                         moviePath,
                                         movieFolderName,
                                         generateNewRank=True)
        folderName = movieData[self.Columns.Folder.value]
        if folderName not in self.movieSet:
            self.movieSet.add(folderName)
            self._data.append(movieData)

    def removeMovie(self, row):
        folderName = self.getFolderName(row)
        if folderName in self.movieSet:
            self.movieSet.remove(folderName)
        del self._data[row]

    def removeMovies(self, minRow, maxRow):
        # Remove folderName from movieSet
        for row in range(minRow, maxRow + 1, 1):
            folderName = self.getFolderName(row)
            if folderName in self.movieSet:
                self.movieSet.remove(folderName)

        self.layoutAboutToBeChanged.emit()
        del self._data[minRow:maxRow+1]

        # Re-number ranks
        for i in range(len(self._data)):
            self._data[i][9] = i

        self.layoutChanged.emit()

    def moveRow(self, minRow, maxRow, dstRow):
        maxRow = maxRow + 1
        tmpData = self._data[minRow:maxRow]
        self.layoutAboutToBeChanged.emit()
        del self._data[minRow:maxRow]
        self._data[dstRow:dstRow] = tmpData

        # Re-number ranks
        for i in range(len(self._data)):
            self._data[i][self.Columns.Rank.value] = i

        self.layoutChanged.emit()

    def rowCount(self, parent=None):
        return len(self._data)

    def columnCount(self, parent):
        return len(self._headers)

    def setBackupStatus(self, index, value):
        self._data[index.row()][self.Columns.BackupStatus.value] = value
        self.dataChanged.emit(index, index)

    def setSize(self, index, value):
        self._data[index.row()][self.Columns.Size.value] = value
        self.dataChanged.emit(index, index)

    def setDimensions(self, index, width, height):
        self._data[index.row()][self.Columns.Width.value] = width
        self._data[index.row()][self.Columns.Height.value] = height
        self.dataChanged.emit(index, index)

    def setDuplicate(self, index, value):
        self._data[index.row()][self.Columns.Duplicate.value] = value
        self.dataChanged.emit(index, index)

    def setMpaaRating(self, index, value):
        self._data[index.row()][self.Columns.MpaaRating.value] = value
        self.dataChanged.emit(index, index)

    def setData(self, index, value, role=QtCore.Qt.EditRole):
        if role == QtCore.Qt.EditRole:
            self._data[index.row()][index.column()] = value
            self.dataChanged.emit(index, index)
        return True

    def data(self, index, role):
        if role == QtCore.Qt.DisplayRole:
            return self._data[index.row()][index.column()]
        elif role == QtCore.Qt.TextAlignmentRole:
            return QtCore.Qt.AlignLeft
        elif role == QtCore.Qt.BackgroundRole:
            backupStatus = self._data[index.row()][self.Columns.BackupStatus.value]
            if not backupStatus:
                return
            elif backupStatus == "Found":
                return QtGui.QBrush(QtGui.QColor("darkgreen"))
            elif backupStatus == "Folder Missing":
                return QtGui.QBrush(QtGui.QColor("darkred"))
            elif backupStatus == "Files Missing (Destination)":
                return QtGui.QBrush(QtGui.QColor("darkorange"))
            elif backupStatus == "Files Missing (Source)":
                return QtGui.QBrush(QtGui.QColor("darkorange"))
            elif "Size Difference" in backupStatus:
                return QtGui.QBrush(QtGui.QColor("darkgoldenrod"))
        elif role == QtCore.Qt.DecorationRole :
            if index.column() == self.Columns.Cover.value:
                row = index.row()
                folderName = self.getFolderName(row)
                moviePath = self.getPath(row)
                coverFile = os.path.join(moviePath, '%s.jpg' % folderName)
                pixMap = QtGui.QPixmap(coverFile).scaled(200, 200,
                                                         QtCore.Qt.KeepAspectRatio,
                                                         QtCore.Qt.SmoothTransformation)
                return pixMap;

    def headerData(self, section, orientation, role):
        if orientation == QtCore.Qt.Horizontal and role == QtCore.Qt.DisplayRole:
            return self._headers[section]
        else:
            return super().headerData(section, orientation, role)
