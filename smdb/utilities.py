import os
import shutil
import sys
import json
import subprocess
import urllib.request
from urllib.error import URLError
from unidecode import unidecode
import platform
import re

import webbrowser
import imdb

from PyQt5.QtWidgets import QMessageBox
from PyQt5 import QtCore

import re
from unidecode import unidecode

# Optional binary serialization (MessagePack) for faster SMDB IO
try:
    import msgpack  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    msgpack = None

# Track how SMDB was last read (for logging/reporting)
_last_smdb_read_format = None  # 'msgpack' | 'json' | None
_last_smdb_read_path = None


def get_last_smdb_read_format():
    return _last_smdb_read_format


def get_last_smdb_read_path():
    return _last_smdb_read_path

import re
from unidecode import unidecode


# Global output function - can be set by MainWindow to redirect to log panel
_output_function = None

def set_output_function(func):
    """Set the global output function to be used by all modules"""
    global _output_function
    _output_function = func

def output(*args, **kwargs):
    """Output function that uses the global output function if set, otherwise prints to console"""
    if _output_function is not None:
        _output_function(*args, **kwargs)
    else:
        print(*args, **kwargs)


def getCollection(input_file):
    collection = []
    with open(input_file, 'r', encoding='utf-8') as input_f:
        rank = 1
        for line in input_f:
                pattern = r'^(.*?)\s+\((\d{4})\).*$'
                match = re.match(pattern, line)
                if match:
                    full_title = match.group(1).strip()
                    year = int(match.group(2))
                    collection.append((rank, full_title, year))
                    rank = rank + 1

    return collection

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


def bToKb(b):
    return b / (2**10)


def formatSizeDiff(sizeInBytes):
    """Format a size difference with appropriate units (Kb or Mb) without zero padding.
    
    Args:
        sizeInBytes: Size difference in bytes (can be positive or negative)
        
    Returns:
        Formatted string like "+5 Mb", "-512 Kb", or "0 Kb"
    """
    if sizeInBytes == 0:
        return "0 Kb"
    
    sizeMb = abs(bToMb(sizeInBytes))
    sign = "+" if sizeInBytes > 0 else "-"
    
    if sizeMb < 1:
        # Display in Kb if less than 1 Mb
        sizeKb = abs(bToKb(sizeInBytes))
        return f"{sign}{sizeKb:.0f} Kb"
    else:
        # Display in Mb
        return f"{sign}{sizeMb:.0f} Mb"


def _smdb_mpk_path(fileName: str) -> str:
    base, ext = os.path.splitext(fileName)
    # Prefer replacing .json with .mpk, otherwise append .mpk
    return f"{base}.mpk" if ext.lower() != ".mpk" else fileName


def _read_smdb_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_smdb_mpk(path: str, data) -> None:
    if not msgpack:
        return
    try:
        # Ensure directory exists
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "wb") as f:
            msgpack.pack(data, f, use_bin_type=True)
    except Exception as e:
        # Non-fatal; just log
        output(f"Warning: failed to write MessagePack SMDB '{path}': {e}")


def readSmdbFile(fileName):
    """Read SMDB data with fast binary fallback.

    Prefers MessagePack (".mpk") if present and msgpack is available; otherwise
    reads the JSON file and, when possible, writes a one-time ".mpk" next to it
    to speed up future loads.
    """
    global _last_smdb_read_format, _last_smdb_read_path
    _last_smdb_read_format, _last_smdb_read_path = None, None

    mpk_path = _smdb_mpk_path(fileName)
    # 1) Prefer MessagePack if available
    if msgpack and os.path.exists(mpk_path):
        try:
            with open(mpk_path, "rb") as f:
                # Allow non-string keys (e.g., years as ints) to match in-memory data
                data = msgpack.unpack(f, raw=False, strict_map_key=False)
                _last_smdb_read_format, _last_smdb_read_path = 'msgpack', mpk_path
                return data
        except Exception as e:
            output(f"Warning: failed to read MessagePack SMDB '{mpk_path}': {e}")
            # Fall back to JSON

    # 2) Fall back to JSON
    if os.path.exists(fileName):
        try:
            data = _read_smdb_json(fileName)
            _last_smdb_read_format, _last_smdb_read_path = 'json', fileName
        except Exception as e:
            output(f"Could not open or parse file: {fileName}: {e}")
            return None

        # 3) If we have msgpack, migrate/write .mpk for next time
        if msgpack:
            _write_smdb_mpk(mpk_path, data)
        return data

    # Nothing found
    return None


def getMovieKey(movie, key):
    if not movie:
        return None
    return movie.get(key, None)

def _is_wsl():
    """Return True when running under Windows Subsystem for Linux."""
    if 'WSL_DISTRO_NAME' in os.environ:
        return True
    try:
        return 'microsoft' in platform.release().lower()
    except Exception:
        return False


def open_url(url, new=2):
    """
    Open the provided URL, handling WSL by delegating to Windows when needed.

    Returns True when an opener was launched successfully, False otherwise.
    """
    try:
        if sys.platform == "win32":
            return webbrowser.open(url, new=new)

        if _is_wsl():
            wslview = shutil.which("wslview")
            if wslview:
                try:
                    subprocess.Popen([wslview, url])
                    return True
                except Exception as e:
                    output(f"wslview failed: {e}")

            if shutil.which("powershell.exe"):
                subprocess.Popen(["powershell.exe", "-NoProfile", "Start-Process", url])
                return True

            if shutil.which("cmd.exe"):
                subprocess.Popen(["cmd.exe", "/C", "start", "", url])
                return True

        opener = "open" if sys.platform == "darwin" else "xdg-open"
        if shutil.which(opener):
            subprocess.Popen([opener, url])
            return True

        return webbrowser.open(url, new=new)
    except Exception as e:
        output(f"Failed to open URL {url}: {e}")
        return False


def openYearImdbPage(year):
    open_url('https://www.imdb.com/search/title/?release_date=%s-01-01,%s-12-31' % (year, year), new=2)


def openPersonImdbPage(personName, db):
    personId = db.name2imdbID(personName)
    if not personId:
        try:
            results = db.search_person(personName)
            if not results:
                output('No matches for: %s' % personName)
                return
            person = results[0]
            if isinstance(person, imdb.Person.Person):
                personId = person.getID()
        except imdb._exceptions.IMDbDataAccessError as err:
            output(f"Error: {err}")

    if personId:
        open_url('http://imdb.com/name/nm%s' % personId, new=2)


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
    """Get sizes of immediate children (files and folders) in a single pass.
    
    Optimized to walk the tree once instead of calling getFolderSize() for each subdirectory.

    The returned sizes are in bytes.
    """
    fileAndSizes = dict()
    
    # Walk the entire tree once and accumulate sizes
    for root, dirs, files in os.walk(path):
        # Calculate relative path from the base path
        rel_path = os.path.relpath(root, path)
        
        if rel_path == '.':
            # Direct children of the base path
            # Add file sizes
            for f in files:
                fileAndSizes[f] = os.path.getsize(os.path.join(root, f))
            # Initialize folder sizes (will accumulate as we walk)
            for d in dirs:
                if d not in fileAndSizes:
                    fileAndSizes[d] = 0
        else:
            # We're inside a subdirectory - add file sizes to the top-level folder
            top_level_folder = rel_path.split(os.sep)[0]
            for f in files:
                fileAndSizes[top_level_folder] += os.path.getsize(os.path.join(root, f))
    
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
        output("Error: No cover image available")
        return ""
    extension = os.path.splitext(movieCoverUrl)[1]
    if extension == '.png':
        coverFile = coverFile.replace('.jpg', '.png')
    try:
        urllib.request.urlretrieve(movieCoverUrl, coverFile)
    except URLError as e:
        output(f"Problem downloading cover file: {coverFile} - {e}")
    return coverFile


def runFile(file):
    import shutil
    if sys.platform == "win32":
        subprocess.Popen(f"start \"\" \"{file}\"", shell=True)
    elif "microsoft" in os.uname().release.lower():  # WSL detection
        # Try xdg-open first
        if shutil.which("xdg-open"):
            try:
                subprocess.call(["xdg-open", file])
                return
            except Exception as e:
                output(f"xdg-open failed: {e}")
        # Fallback to Windows default app
        win_path = os.path.abspath(file)
        # Convert WSL path to Windows path
        try:
            completed = subprocess.run(["wslpath", "-w", win_path], capture_output=True, text=True)
            if completed.returncode == 0:
                win_path = completed.stdout.strip()
        except Exception as e:
            output(f"wslpath failed: {e}")
        subprocess.Popen(["cmd.exe", "/C", "start", "", win_path])
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
                output('Deleting folder: %s' % f)
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
                output('Deleting file: %s' % f)
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
