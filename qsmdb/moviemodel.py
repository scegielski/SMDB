import json
import fnmatch
from enum import Enum
from PyQt5 import QtGui

from .utilities import *


class MoviesTableModel(QtCore.QAbstractTableModel):
    def __init__(self, smdbData, moviesFolder, forceScan=False, neverScan=False):
        super().__init__()

        self.movieSet = set()
        self._data = []

        self.Columns = Enum('Columns', ['Year',
                                        'Title',
                                        'Rating',
                                        'BoxOffice',
                                        'Runtime',
                                        'Director',
                                        'Country',
                                        'Company',
                                        'Genre',
                                        'UserTags',
                                        'Id',
                                        'Folder',
                                        'Path',
                                        'JsonExists',
                                        'Rank',
                                        'BackupStatus',
                                        'Size'], start=0)

        self.defaultWidths = {self.Columns.Year: 50,
                              self.Columns.Title: 200,
                              self.Columns.Rating: 60,
                              self.Columns.BoxOffice: 150,
                              self.Columns.Runtime: 60,
                              self.Columns.Director: 150,
                              self.Columns.Country: 150,
                              self.Columns.Company: 150,
                              self.Columns.Genre: 150,
                              self.Columns.UserTags: 150,
                              self.Columns.Id: 60,
                              self.Columns.Folder: 200,
                              self.Columns.Path: 300,
                              self.Columns.JsonExists: 65,
                              self.Columns.Rank: 40,
                              self.Columns.BackupStatus: 150,
                              self.Columns.Size: 100}

        self._headers = []
        for c in self.Columns:
            tokens = splitCamelCase(c.name)
            self._headers.append(' '.join(tokens))

        if not os.path.exists(moviesFolder):
            return

        # Either read the list of movie folders from the smdb data
        # or scan the movies folder
        moviesFolderList = []
        useSmdbData = False
        if neverScan and (not smdbData or 'titles' not in smdbData):
            return
        elif not forceScan and smdbData and 'titles' in smdbData:
            useSmdbData = True
            for title in smdbData['titles']:
                moviesFolderList.append(title)
        else:
            with os.scandir(moviesFolder) as files:
                for f in files:
                    if f.is_dir() and fnmatch.fnmatch(f, '*(*)'):
                        moviesFolderList.append(f.name)
                    else:
                        print("Not adding %s to movie list" % f.name)

        for movieFolderName in moviesFolderList:
            data = {}
            if useSmdbData:
                data = smdbData['titles'][movieFolderName]
            else:
                jsonFile = os.path.join(moviesFolder,
                                        movieFolderName,
                                        '%s.json' % movieFolderName)
                if os.path.exists(jsonFile):
                    with open(jsonFile) as f:
                        try:
                            data = json.load(f)
                        except UnicodeDecodeError:
                            print("Error reading %s" % jsonFile)

            moviePath = os.path.join(moviesFolder, movieFolderName)
            movieData = self.createMovieData(data,
                                             moviePath,
                                             movieFolderName)

            folderName = movieData[self.Columns.Folder.value]
            if folderName not in self.movieSet:
                self.movieSet.add(folderName)
                self._data.append(movieData)

        # Sort by year
        self.sort(self.Columns.Year.value, QtCore.Qt.AscendingOrder)

    def getHeaders(self):
        return self._headers

    def getNumColumns(self):
        return len(self.Columns)

    def getLastColumn(self):
        return len(self.Columns) - 1

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

    def getDataSize(self):
        return len(self._data)

    def aboutToChangeLayout(self):
        self.layoutAboutToBeChanged.emit()

    def changedLayout(self):
        self.layoutChanged.emit()

    def addMovie(self, smdbData, moviePath):
        movieFolderName = os.path.basename(moviePath)
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

    def createMovieData(self, data, moviePath, movieFolderName, generateNewRank=False):
        reMoneyValue = re.compile(r'(\d+(?:,\d+)*(?:\.\d+)?)')
        reCurrency = re.compile(r'^([A-Z][A-Z][A-Z])(.*)')

        movieData = []
        for column in self.Columns:
            if column == self.Columns.Path:
                movieData.append(moviePath)
            elif column == self.Columns.JsonExists:
                jsonFile = os.path.join(moviePath, '%s.json' % movieFolderName)
                if os.path.exists(jsonFile):
                    movieData.append("True")
                else:
                    movieData.append("False")
            elif column == self.Columns.Folder:
                movieData.append(movieFolderName)
            elif column == self.Columns.Rank and generateNewRank:
                rank = len(self._data)
                movieData.append(rank)
            elif column == self.Columns.Country:
                if 'countries' in data and data['countries']:
                    country = data['countries'][0]
                    movieData.append(country)
                else:
                    movieData.append('')
            elif column == self.Columns.Company:
                if 'companies' in data and data['companies']:
                    company = data['companies'][0]
                    movieData.append(company)
                else:
                    movieData.append('')
            elif column == self.Columns.Genre:
                if 'genres' in data and data['genres']:
                    genre = data['genres'][0]
                    movieData.append(genre)
                else:
                    movieData.append('')
            elif column == self.Columns.UserTags:
                if 'user tags' in data and data['user tags']:
                    userTag = data['user tags'][0]
                    movieData.append(userTag)
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
                    elif column == self.Columns.BoxOffice:
                        boxOffice = data[headerLower]
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
                        displayText = '%-3s %15s' % (currency, amount)
                        movieData.append(displayText)
                    else:
                        movieData.append(data[headerLower])
        return movieData

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
            elif backupStatus == "Files Missing":
                return QtGui.QBrush(QtGui.QColor("darkorange"))
            elif "Size Difference" in backupStatus:
                return QtGui.QBrush(QtGui.QColor("darkgoldenrod"))

    def headerData(self, section, orientation, role):
        if orientation == QtCore.Qt.Horizontal and role == QtCore.Qt.DisplayRole:
            return self._headers[section]
        else:
            return super().headerData(section, orientation, role)
