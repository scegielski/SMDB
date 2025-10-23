import json
import fnmatch
import pathlib
import datetime
from enum import Enum, auto
from PyQt5 import QtGui, QtCore

from .utilities import *

class Columns(Enum):
    Cover = 0
    Year = auto()
    Title = auto()
    Rating = auto()
    MpaaRating = auto()
    BoxOffice = auto()
    Runtime = auto()
    Directors = auto()
    Countries = auto()
    Companies = auto()
    Genres = auto()
    UserTags = auto()
    Id = auto()
    Folder = auto()
    Path = auto()
    JsonExists = auto()
    CoverExists = auto()
    Rank = auto()
    BackupStatus =auto()
    Duplicate = auto()
    Width = auto()
    Height = auto()
    Channels = auto()
    Size = auto()
    DateModified = auto()
    DateWatched = auto()
    SubtitlesExist = auto()


defaultColumnWidths = {Columns.Cover.value: 150,
                       Columns.Year.value: 50,
                       Columns.Title.value: 200,
                       Columns.Rating.value: 60,
                       Columns.MpaaRating.value: 100,
                       Columns.BoxOffice.value: 150,
                       Columns.Runtime.value: 60,
                       Columns.Directors.value: 150,
                       Columns.Countries.value: 150,
                       Columns.Companies.value: 150,
                       Columns.Genres.value: 150,
                       Columns.UserTags.value: 150,
                       Columns.Id.value: 60,
                       Columns.Folder.value: 200,
                       Columns.Path.value: 300,
                       Columns.JsonExists.value: 65,
                       Columns.CoverExists.value: 65,
                       Columns.Rank.value: 40,
                       Columns.BackupStatus.value: 150,
                       Columns.Duplicate.value: 60,
                       Columns.Width.value: 50,
                       Columns.Height.value: 50,
                       Columns.Channels.value: 50,
                       Columns.Size.value: 100,
                       Columns.DateModified.value: 150,
                       Columns.DateWatched.value: 150,
                       Columns.SubtitlesExist.value: 65}

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

        # Create the header text from the enums
        self._headers = []
        for c in Columns:
            tokens = splitCamelCase(c.name)
            self._headers.append(' '.join(tokens))

        for moviesFolder in moviesFolders:
            if not os.path.exists(moviesFolder):
                print(f"Error: Movies folder {moviesFolder} does not exist")

        # Either read the list of movies from the smdb data
        # or scan the movies folder(s)
        moviesFolderDict = dict()
        useSmdbData = False

        if neverScan and (not smdbData or 'titles' not in smdbData):
            return

        if not forceScan and smdbData and 'titles' in smdbData:
            useSmdbData = True
            for path in smdbData['titles']:
                folder = smdbData['titles'][path]['folder']
                moviesFolderDict[path] = [folder, path]
        else:
            for moviesFolder in moviesFolders:
                if not os.path.exists(moviesFolder):
                    continue
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

            folderName = movieData[Columns.Folder.value]
            self.movieSet.add(folderName)
            self._data.append(movieData)

        # Sort by year
        self.sort(Columns.Year.value, QtCore.Qt.AscendingOrder)

    def addMovieData(self,
                     data,
                     moviePath,
                     movieFolderName,
                     generateRank=False,
                     force=False):
        movieData = self.createMovieData(data,
                                         moviePath,
                                         movieFolderName,
                                         generateRank,
                                         force)
        self.beginInsertRows(self.index(0, 0), 0, 0)
        self._data.append(movieData)
        self.endInsertRows()

    def createMovieData(self,
                        data,
                        moviePath,
                        movieFolderName,
                        generateNewRank=False,
                        force=False):

        movieData = []
        for column in Columns:
            if column == Columns.DateModified:
                if 'date' in data:
                    movieData.append(data['date'])
                else:
                    movieData.append('no date')
            elif column == Columns.DateWatched:
                if 'date watched' in data:
                    movieData.append(data['date watched'])
                else:
                    movieData.append('no date')
            elif column == Columns.Path:
                movieData.append(moviePath)
            elif column == Columns.JsonExists:
                if force:
                    jsonFile = os.path.join(moviePath, '%s.json' % movieFolderName)
                    if os.path.exists(jsonFile):
                        movieData.append("True")
                    else:
                        print(f"jsonFile {jsonFile} does not exist")
                        movieData.append("False")
                else:
                    movieData.append("")
            elif column == Columns.CoverExists:
                if force:
                    coverFile = os.path.join(moviePath, '%s.jpg' % movieFolderName)
                    if os.path.exists(coverFile):
                        movieData.append("True")
                    else:
                        print(f"coverFile {coverFile} does not exist")
                        movieData.append("False")
                else:
                    movieData.append("")
            elif column == Columns.SubtitlesExist:
                if force:
                    has_srt = any([f.lower().endswith('.srt') for f in os.listdir(moviePath)]) if os.path.exists(moviePath) else False
                    movieData.append("True" if has_srt else "False")
                else:
                    # Populate from smdb_data.json if available, otherwise blank
                    val = None
                    if 'subtitles exist' in data:
                        val = data['subtitles exist']
                        if isinstance(val, bool):
                            val = "True" if val else "False"
                        else:
                            val = str(val)
                    movieData.append(val if val is not None else "")
            elif column == Columns.Folder:
                movieData.append(movieFolderName)
            elif column == Columns.Rank and generateNewRank:
                rank = len(self._data)
                movieData.append(rank)
            elif column == Columns.Countries:
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
            elif column == Columns.Companies:
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
            elif column == Columns.Genres:
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
            elif column == Columns.Directors:
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
            elif column == Columns.UserTags:
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
                    if column == Columns.Title:
                        title, year = getNiceTitleAndYear(movieFolderName)
                        movieData.append(title)
                    elif column == Columns.Year:
                        title, year = getNiceTitleAndYear(movieFolderName)
                        movieData.append(year)
                    else:
                        movieData.append('')
                else:
                    if column == Columns.Runtime:
                        runtime = data[headerLower]
                        if not runtime:
                            runtime = '000'
                        else:
                            try:
                                runtime = runtime.split()[0]
                                runtime = '%03d' % int(runtime)
                            except ValueError:
                                pass
                        movieData.append(runtime)
                    elif column == Columns.Rating:
                        rating = data[headerLower]
                        if not rating:
                            rating = '0.0'
                        else:
                            rating = str(rating)
                            if len(rating) == 1:
                                rating = '%s.0' % rating
                        movieData.append(rating)
                    elif column == Columns.MpaaRating:
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
        return len(Columns)

    def getLastColumn(self):
        return len(Columns) - 1

    def getMpaaRating(self, row):
        return self._data[row][Columns.MpaaRating.value]

    def getBackupStatus(self, row):
        return self._data[row][Columns.BackupStatus.value]

    def getYear(self, row):
        return self._data[row][Columns.Year.value]

    def getTitle(self, row):
        return self._data[row][Columns.Title.value]

    def getDateWatched(self, row):
        return self._data[row][Columns.DateWatched.value]

    def getRating(self, row):
        return self._data[row][Columns.Rating.value]

    def getBoxOffice(self, row):
        return self._data[row][Columns.BoxOffice.value]

    def getRuntime(self, row):
        return self._data[row][Columns.Runtime.value]

    def getId(self, row):
        return self._data[row][Columns.Id.value]

    def getChannels(self, row):
        return self._data[row][Columns.Channels.value]

    def getDimensions(self, row):
        width = self._data[row][Columns.Width.value]
        height = self._data[row][Columns.Height.value]
        return width, height

    def getFolderName(self, row):
        return self._data[row][Columns.Folder.value]

    def getPath(self, row):
        return self._data[row][Columns.Path.value]

    def getJsonExists(self, row):
        return self._data[row][Columns.JsonExists.value]

    def getCoverExists(self, row):
        return self._data[row][Columns.CoverExists.value]

    def getRank(self, row):
        return self._data[row][Columns.Rank.value]

    def getSize(self, row):
        return self._data[row][Columns.Size.value]

    def getDuplicate(self, row):
        return self._data[row][Columns.Duplicate.value]

    def getDataSize(self):
        return len(self._data)

    def aboutToChangeLayout(self):
        self.layoutAboutToBeChanged.emit()

    def changedLayout(self):
        self.layoutChanged.emit()

    def addMovie(self, smdbData, moviePath):
        if moviePath not in smdbData['titles']:
            return

        movieFolderName = smdbData['titles'][moviePath]['folder']

        data = smdbData['titles'][moviePath]
        movieData = self.createMovieData(data,
                                         moviePath,
                                         movieFolderName,
                                         generateNewRank=True)
        folderName = movieData[Columns.Folder.value]
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

    def renumberRanks(self):
        for i in range(len(self._data)):
            self._data[i][Columns.Rank.value] = i

    def moveRow(self, minRow, maxRow, dstRow):
        maxRow = maxRow + 1
        tmpData = self._data[minRow:maxRow]
        self.layoutAboutToBeChanged.emit()
        del self._data[minRow:maxRow]
        self._data[dstRow:dstRow] = tmpData

        self.renumberRanks()

        self.layoutChanged.emit()

    def rowCount(self, parent=None):
        return len(self._data)

    def columnCount(self, parent):
        return len(self._headers)

    def setBackupStatus(self, index, value):
        self._data[index.row()][Columns.BackupStatus.value] = value
        self.dataChanged.emit(index, index)

    def setSize(self, index, value):
        self._data[index.row()][Columns.Size.value] = value
        self.dataChanged.emit(index, index)

    def setDimensions(self, index, width, height):
        self._data[index.row()][Columns.Width.value] = width
        self._data[index.row()][Columns.Height.value] = height
        self.dataChanged.emit(index, index)

    def setChannels(self, index, channels):
        self._data[index.row()][Columns.Channels.value] = channels
        self.dataChanged.emit(index, index)

    def setDuplicate(self, index, value):
        self._data[index.row()][Columns.Duplicate.value] = value
        self.dataChanged.emit(index, index)

    def setRank(self, index, value):
        self._data[index.row()][Columns.Rank.value] = int(value)
        self.dataChanged.emit(index, index)

    def setMpaaRating(self, index, value):
        self._data[index.row()][Columns.MpaaRating.value] = value
        self.dataChanged.emit(index, index)

    def setDateWatched(self, index, dateWatched):
        self._data[index.row()][Columns.DateWatched.value] = dateWatched
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
            backupStatus = self._data[index.row()][Columns.BackupStatus.value]
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
            if index.column() == Columns.Cover.value:
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
