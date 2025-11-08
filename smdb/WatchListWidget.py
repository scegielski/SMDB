from PyQt5 import QtGui, QtWidgets, QtCore
from enum import Enum
import os

from .MoviesTableModel import MoviesTableModel, Columns, defaultColumnWidths
from .MovieTableView import MovieTableView


class MoveTo(Enum):
    DOWN = 0
    UP = 1
    TOP = 2


class WatchListWidget(QtWidgets.QFrame):
    """Widget that handles all watch list functionality including UI and operations."""
    
    def __init__(self, parent, settings, bgColorA, bgColorB, bgColorC, bgColorD, 
                 moviesSmdbData, watchListSmdbFile, outputCallback):
        super().__init__(parent)
        
        self.parent = parent
        self.settings = settings
        self.bgColorA = bgColorA
        self.bgColorB = bgColorB
        self.bgColorC = bgColorC
        self.bgColorD = bgColorD
        self.moviesSmdbData = moviesSmdbData
        self.listSmdbFile = watchListSmdbFile
        self.output = outputCallback
        
        # Table setup
        self.listTableView = MovieTableView()
        self.listDefaultColumns = [Columns.Rank.value,
                                   Columns.Year.value,
                                   Columns.Title.value,
                                   Columns.Rating.value]
        
        try:
            self.listColumns = self.settings.value('watchListTableColumns',
                                                   self.listDefaultColumns,
                                                   type=list)
            self.listColumns = [int(m) for m in self.listColumns]
        except TypeError:
            self.listColumns = self.listDefaultColumns
        
        try:
            self.listColumnWidths = self.settings.value('watchListTableColumnWidths',
                                                        defaultColumnWidths,
                                                        type=list)
            self.listColumnWidths = [int(m) for m in self.listColumnWidths]
        except TypeError:
            self.listColumnWidths = defaultColumnWidths
        
        self.listTableView.wheelSpun.connect(self.parent.changeFontSize)
        self.listColumnsVisible = []
        self.listHeaderActions = []
        
        # Data models
        self.listSmdbData = None
        self.listTableModel = None
        self.listTableProxyModel = None
        
        # Initialize UI
        self.initUI()
    
    def initUI(self):
        """Initialize the watch list UI."""
        self.setFrameShape(QtWidgets.QFrame.Panel | QtWidgets.QFrame.Sunken)
        self.setLineWidth(5)
        self.setStyleSheet(f"background: {self.bgColorB};"
                          f"border-radius: 10px;")
        
        watchListVLayout = QtWidgets.QVBoxLayout()
        self.setLayout(watchListVLayout)
        
        watchListLabel = QtWidgets.QLabel("Watch List")
        watchListVLayout.addWidget(watchListLabel)
        
        self.listTableView.setSortingEnabled(False)
        self.listTableView.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.listTableView.verticalHeader().hide()
        self.listTableView.setStyleSheet(f"background: {self.bgColorC};"
                                        f"alternate-background-color: {self.bgColorD};")
        self.listTableView.setAlternatingRowColors(True)
        self.listTableView.setShowGrid(False)
        
        # Right click header menu
        hh = self.listTableView.horizontalHeader()
        hh.setSectionsMovable(True)
        hh.setStyleSheet(f"background: {self.bgColorB};"
                        f"border-radius: 0px;")
        hh.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        hh.customContextMenuRequested[QtCore.QPoint].connect(
            lambda: self.parent.headerRightMenuShow(QtCore.QPoint,
                                                    self.listTableView,
                                                    self.listColumnsVisible,
                                                    self.listTableModel))
        
        # Right click menu
        self.listTableView.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.listTableView.customContextMenuRequested[QtCore.QPoint].connect(self.tableRightMenuShow)
        
        watchListVLayout.addWidget(self.listTableView)
        
        watchListButtonsHLayout = QtWidgets.QHBoxLayout()
        watchListVLayout.addLayout(watchListButtonsHLayout)
        
        addButton = QtWidgets.QPushButton('Add')
        addButton.clicked.connect(self.listAdd)
        addButton.setStyleSheet(f"background: {self.bgColorA};"
                                f"border-radius: 5px;")
        watchListButtonsHLayout.addWidget(addButton)
        
        removeButton = QtWidgets.QPushButton('Remove')
        removeButton.clicked.connect(self.listRemove)
        removeButton.setStyleSheet(f"background: {self.bgColorA};"
                                   f"border-radius: 5px;")
        watchListButtonsHLayout.addWidget(removeButton)
        
        moveToTopButton = QtWidgets.QPushButton('Move To Top')
        moveToTopButton.clicked.connect(lambda: self.listMoveRow(MoveTo.TOP))
        moveToTopButton.setStyleSheet(f"background: {self.bgColorA};"
                                      f"border-radius: 5px;")
        watchListButtonsHLayout.addWidget(moveToTopButton)
        
        moveUpButton = QtWidgets.QPushButton('Move Up')
        moveUpButton.clicked.connect(lambda: self.listMoveRow(MoveTo.UP))
        moveUpButton.setStyleSheet(f"background: {self.bgColorA};"
                                   f"border-radius: 5px;")
        watchListButtonsHLayout.addWidget(moveUpButton)
        
        moveDownButton = QtWidgets.QPushButton('Move Down')
        moveDownButton.clicked.connect(lambda: self.listMoveRow(MoveTo.DOWN))
        moveDownButton.setStyleSheet(f"background: {self.bgColorA};"
                                     f"border-radius: 5px;")
        watchListButtonsHLayout.addWidget(moveDownButton)
    
    def refreshWatchList(self):
        """Refresh the watch list table."""
        (self.listSmdbData,
         self.listTableModel,
         self.listTableProxyModel,
         self.listColumnsVisible,
         smdbData) = self.parent.refreshTable(self.listSmdbFile,
                                              self.listTableView,
                                              self.listColumns,
                                              self.listColumnWidths,
                                              Columns.Rank.value)
        return (self.listSmdbData,
                self.listTableModel,
                self.listTableProxyModel,
                self.listColumnsVisible,
                smdbData)
    
    def tableRightMenuShow(self, QPos):
        """Show right-click context menu for watch list table."""
        rightMenu = QtWidgets.QMenu(self.parent.moviesTableView)
        
        selectAllAction = QtWidgets.QAction("Select All", self)
        selectAllAction.triggered.connect(lambda: self.parent.tableSelectAll(self.listTableView))
        rightMenu.addAction(selectAllAction)
        
        playAction = QtWidgets.QAction("Play", self)
        playAction.triggered.connect(lambda: self.parent.playMovie(self.listTableView,
                                                                   self.listTableProxyModel))
        rightMenu.addAction(playAction)
        
        selectInMainListAction = QtWidgets.QAction("Select movie in main list", self)
        selectInMainListAction.triggered.connect(self.selectMovieInMainList)
        rightMenu.addAction(selectInMainListAction)
        
        removeFromWatchListAction = QtWidgets.QAction("Remove From Watch List", self)
        removeFromWatchListAction.triggered.connect(self.listRemove)
        rightMenu.addAction(removeFromWatchListAction)
        
        moveToTopWatchListAction = QtWidgets.QAction("Move To Top", self)
        moveToTopWatchListAction.triggered.connect(lambda: self.listMoveRow(MoveTo.TOP))
        rightMenu.addAction(moveToTopWatchListAction)
        
        moveUpWatchListAction = QtWidgets.QAction("Move Up", self)
        moveUpWatchListAction.triggered.connect(lambda: self.listMoveRow(MoveTo.UP))
        rightMenu.addAction(moveUpWatchListAction)
        
        moveDownWatchListAction = QtWidgets.QAction("Move Down", self)
        moveDownWatchListAction.triggered.connect(lambda: self.listMoveRow(MoveTo.DOWN))
        rightMenu.addAction(moveDownWatchListAction)
        
        if len(self.listTableView.selectionModel().selectedRows()) > 0:
            modelIndex = self.listTableView.selectionModel().selectedRows()[0]
            self.parent.clickedTable(modelIndex,
                                    self.listTableModel,
                                    self.listTableProxyModel)
        
        rightMenu.exec_(QtGui.QCursor.pos())
    
    def listAdd(self):
        """Add selected movies from main list to watch list."""
        self.listTableModel.aboutToChangeLayout()
        for modelIndex in self.parent.moviesTableView.selectionModel().selectedRows():
            if not self.parent.moviesTableView.isRowHidden(modelIndex.row()):
                sourceIndex = self.parent.moviesTableProxyModel.mapToSource(modelIndex)
                sourceRow = sourceIndex.row()
                moviePath = self.parent.moviesTableModel.getPath(sourceRow)
                self.listTableModel.addMovie(self.parent.moviesSmdbData,
                                            moviePath)
        
        self.listTableModel.changedLayout()
        self.parent.writeSmdbFile(self.listSmdbFile,
                                 self.listTableModel,
                                 titlesOnly=True)
    
    def listRemove(self):
        """Remove selected movies from watch list."""
        selectedRows = self.listTableView.selectionModel().selectedRows()
        if len(selectedRows) == 0:
            return
        
        minRow = selectedRows[0].row()
        maxRow = selectedRows[-1].row()
        self.listTableModel.removeMovies(minRow, maxRow)
        self.listTableView.selectionModel().clearSelection()
        self.parent.writeSmdbFile(self.listSmdbFile,
                                 self.listTableModel,
                                 titlesOnly=True)
    
    def selectMovieInMainList(self):
        """Select the current movie in the main movies list."""
        selectedRows = self.listTableView.selectionModel().selectedRows()
        if len(selectedRows) == 0:
            return
        
        # Get the movie path from the watch list
        proxyIndex = selectedRows[0]
        sourceIndex = self.listTableProxyModel.mapToSource(proxyIndex)
        moviePath = self.listTableModel.getPath(sourceIndex.row())
        
        # Find the movie in the main movies table
        for row in range(self.parent.moviesTableModel.rowCount()):
            if self.parent.moviesTableModel.getPath(row) == moviePath:
                # Find the corresponding proxy row
                sourceIndex = self.parent.moviesTableModel.index(row, 0)
                proxyIndex = self.parent.moviesTableProxyModel.mapFromSource(sourceIndex)
                
                # Select the row in the main table
                self.parent.moviesTableView.selectRow(proxyIndex.row())
                self.parent.moviesTableView.scrollTo(proxyIndex)
                
                # Update the movie display
                self.parent.clickedTable(proxyIndex,
                                        self.parent.moviesTableModel,
                                        self.parent.moviesTableProxyModel)
                break
    
    def listMoveRow(self, moveTo):
        """Move selected rows in the watch list."""
        selectedRows = self.listTableView.selectionModel().selectedRows()
        if len(selectedRows) == 0:
            return
        
        minProxyRow = selectedRows[0].row()
        maxProxyRow = selectedRows[-1].row()
        minSourceRow = self.listTableProxyModel.mapToSource(selectedRows[0]).row()
        maxSourceRow = self.listTableProxyModel.mapToSource(selectedRows[-1]).row()
        
        if ((moveTo == MoveTo.UP or moveTo == MoveTo.TOP) and minSourceRow == 0) or \
           (moveTo == MoveTo.DOWN and maxSourceRow >= (self.listTableModel.getDataSize() - 1)):
            return
        
        self.listTableView.selectionModel().clearSelection()
        
        dstRow = 0
        topRow = 0
        bottomRow = 0
        if moveTo == MoveTo.UP:
            dstRow = minSourceRow - 1
            topRow = minProxyRow - 1
            bottomRow = maxProxyRow - 1
        elif moveTo == MoveTo.DOWN:
            dstRow = minSourceRow + 1
            topRow = minProxyRow + 1
            bottomRow = maxProxyRow + 1
        elif moveTo == MoveTo.TOP:
            dstRow = 0
            topRow = 0
            bottomRow = maxProxyRow - minProxyRow
        
        self.listTableModel.moveRow(minSourceRow, maxSourceRow, dstRow)
        topLeft = self.listTableProxyModel.index(topRow, 0)
        lastColumn = self.parent.moviesTableModel.getLastColumn()
        bottomRight = self.listTableProxyModel.index(bottomRow, lastColumn)
        
        selection = self.listTableView.selectionModel().selection()
        selection.select(topLeft, bottomRight)
        self.listTableView.selectionModel().select(selection,
                                                   QtCore.QItemSelectionModel.ClearAndSelect)
        
        self.parent.writeSmdbFile(self.listSmdbFile,
                                 self.listTableModel,
                                 titlesOnly=True)
