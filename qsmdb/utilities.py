import re
import os
import shutil
import sys
import json
import subprocess
import urllib.request
from urllib.error import URLError

import webbrowser
import imdb

from PyQt5.QtWidgets import QMessageBox
from PyQt5 import QtCore


def getCriterionCollection():
    input_file = 'criterion_collection_films.txt'
    criterion_collection = []
    with open(input_file, 'r', encoding='utf-8') as input_f:
        for line in input_f:
            tokens = re.split('\t', line.strip())
            if len(tokens) > 4:
                rank = tokens[0].strip()
                title = tokens[1].strip()
                year = tokens[4].strip()
                criterion_collection.append((rank, title, year))
    return criterion_collection

def handleRemoveReadonly(func, path, exc_info):
    """
    Error handler for ``shutil.rmtree``.

    If the error is due to an access error (read only file)
    it attempts to add write permission and then retries.

    If the error is for another reason it re-raises the error.

    Usage : ``shutil.rmtree(path, onerror=onerror)``
    """
    import stat
    if not os.access(path, os.W_OK):
        # Is the error an access error ?
        os.chmod(path, stat.S_IWUSR)
        func(path)
    else:
        raise


def bToGb(b):
    return b / (2**30)


def bToMb(b):
    return b / (2**20)


def readSmdbFile(fileName):
    if os.path.exists(fileName):
        try:
            with open(fileName) as f:
                return json.load(f)
        except IOError:
            print("Could not open file: %s" % fileName)


def getMovieKey(movie, key):
    if key in movie:
        return movie[key]
    else:
        return None


def openYearImdbPage(year):
    webbrowser.open('https://www.imdb.com/search/title/?release_date=%s-01-01,%s-12-31' % (year, year), new=2)


def openPersonImdbPage(personName, db):
    personId = db.name2imdbID(personName)
    if not personId:
        try:
            results = db.search_person(personName)
            if not results:
                print('No matches for: %s' % personName)
                return
            person = results[0]
            if isinstance(person, imdb.Person.Person):
                personId = person.getID()
        except imdb._exceptions.IMDbDataAccessError as err:
            print(f"Error: {err}")

    if personId:
        webbrowser.open('http://imdb.com/name/nm%s' % personId, new=2)


def getFolderSize(startPath='.'):
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(startPath):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            # skip if it is symbolic link
            if not os.path.islink(fp):
                total_size += os.path.getsize(fp)
    return total_size


def getFolderSizes(path):
    fileAndSizes = dict()
    for f in os.listdir(path):
        fullPath = os.path.join(path, f)
        if os.path.isdir(fullPath):
            fileSize = getFolderSize(fullPath)
        else:
            fileSize = os.path.getsize(fullPath)
        fileAndSizes[f] = fileSize
    return fileAndSizes


def splitCamelCase(inputText):
    return re.sub('([A-Z][a-z]+)', r' \1', re.sub('([A-Z]+)', r' \1', inputText)).split()


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


def copyCoverImage(movie, coverFile):
    if 'full-size cover url' in movie:
        movieCoverUrl = movie['full-size cover url']
    elif 'cover' in movie:
        movieCoverUrl = movie['cover']
    elif 'cover url' in movie:
        movieCoverUrl = movie['cover']
    else:
        print("Error: No cover image available")
        return ""
    extension = os.path.splitext(movieCoverUrl)[1]
    if extension == '.png':
        coverFile = coverFile.replace('.jpg', '.png')
    try:
        urllib.request.urlretrieve(movieCoverUrl, coverFile)
    except URLError as e:
        print(f"Problem downloading cover file: {coverFile} - {e}")
    return coverFile


def runFile(file):
    if sys.platform == "win32":
        subprocess.Popen(f"start \"\" \"{file}\"", shell=True)
    else:
        opener = "open" if sys.platform == "darwin" else "xdg-open"
        subprocess.call([opener, file])


def removeFolders(parent, foldersToDelete):
    if len(foldersToDelete) > 0:
        ret = QMessageBox.question(parent,
                                   'Confirm Delete',
                                   'Really remove %d movie folders?' % (len(foldersToDelete)),
                                   QMessageBox.Yes | QMessageBox.No,
                                   QMessageBox.No)

        if ret == QMessageBox.Yes:
            for f in foldersToDelete:
                print('Deleting folder: %s' % f)
                try:
                    shutil.rmtree(f,
                                  ignore_errors=False,
                                  onerror=handleRemoveReadonly)
                except FileNotFoundError:
                    pass


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


def searchTableWidget(searchBoxWidget, tableWidget):
    searchText = searchBoxWidget.text()
    if searchText == "":
        for row in range(tableWidget.rowCount()):
            tableWidget.showRow(row)
    else:
        for row in range(tableWidget.rowCount()):
            tableWidget.hideRow(row)
        for foundItem in tableWidget.findItems(searchText, QtCore.Qt.MatchContains):
            tableWidget.showRow(foundItem.row())


def searchTableView(searchBoxWidget, tableView):
    searchText = searchBoxWidget.text()
    proxyModel = tableView.model()
    proxyModel.setFilterKeyColumn(1)
    proxyModel.setFilterRegExp(QtCore.QRegExp(searchText,
                                              QtCore.Qt.CaseInsensitive,
                                              QtCore.QRegExp.FixedString))

    for row in range(proxyModel.rowCount(tableView.rootIndex())):
        tableView.verticalHeader().resizeSection(row, 18)
