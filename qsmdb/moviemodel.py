from PyQt5 import QtCore
import os
import json
import fnmatch
import re

from .utilities import *

class MoviesTableModel(QtCore.QAbstractTableModel):
    def __init__(self, smdbData, moviesFolder, forceScan=False, neverScan=False):
        super().__init__()
        self.numVisibleMovies = 0

        self._data = []
        self._headers = ['Year',
                         'Title',
                         'Rating',
                         'Box office',
                         'Runtime',
                         'Id',
                         'Folder name',
                         'Path',
                         'Json Exists',
                         'Rank']

        if not os.path.exists(moviesFolder):
            return

        movieList = []
        useSmdbData = False
        if neverScan and (not smdbData or not 'titles' in smdbData):
            return
        elif not forceScan and smdbData and 'titles' in smdbData:
            useSmdbData = True
            for title in smdbData['titles']:
                movieList.append(title)
        else:
            with os.scandir(moviesFolder) as files:
                for f in files:
                    if f.is_dir() and fnmatch.fnmatch(f, '*(*)'):
                        movieList.append(f.name)

        for movieFolderName in movieList:
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
            movieData = self.createMovieData(data, moviePath, movieFolderName)
            self._data.append(movieData)

        self.sort(0, QtCore.Qt.AscendingOrder)

    def addMovie(self, smdbData, moviePath, movieFolderName):
        self.layoutAboutToBeChanged.emit()
        data = smdbData['titles'][movieFolderName]
        movieData = self.createMovieData(data, moviePath, movieFolderName)
        self._data.append(movieData)
        self.layoutChanged.emit()

    def removeMovie(self, row):
        print("In removeMovie")
        del self._data[row]

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
        maxIndex = self.index(row, 8)
        self.dataChanged.emit(minIndex, maxIndex)

    def createMovieData(self, data, moviePath, movieFolderName):
        reMoneyValue = re.compile(r'(\d+(?:,\d+)*(?:\.\d+)?)')
        reCurrency = re.compile(r'^([A-Z][A-Z][A-Z])(.*)')
        movieData = []
        for header in self._headers:
            headerLower = header.lower()
            if headerLower == 'path':
                movieData.append(moviePath)
            elif headerLower == 'json exists':
                jsonFile = os.path.join(moviePath, '%s.json' % movieFolderName)
                if os.path.exists(jsonFile):
                    movieData.append("True")
                else:
                    movieData.append("False")
            elif headerLower == 'folder name':
                movieData.append(movieFolderName)
            elif headerLower == 'rank':
                movieData.append("0")
            else:
                if headerLower not in data:
                    if headerLower == 'title':
                        title, year = getNiceTitleAndYear(movieFolderName)
                        movieData.append(title)
                    elif headerLower == 'year':
                        title, year = getNiceTitleAndYear(movieFolderName)
                        movieData.append(year)
                    else:
                        movieData.append('')
                else:
                    if headerLower == 'runtime':
                        runtime = data[headerLower]
                        if not runtime:
                            runtime = '000'
                        else:
                            runtime = '%03d' % int(runtime)
                        movieData.append(runtime)
                    elif headerLower == 'rating':
                        rating = data[headerLower]
                        if not rating:
                            rating = '0.0'
                        else:
                            rating = str(rating)
                            if len(rating) == 1:
                                rating = '%s.0' % rating
                        movieData.append(rating)
                    elif headerLower == 'box office':
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

    def headerData(self, section, orientation, role):
        if orientation == QtCore.Qt.Horizontal and role == QtCore.Qt.DisplayRole:
            return self._headers[section]
        else:
            return super().headerData(section, orientation, role)
