from PyQt5 import QtGui, QtWidgets, QtCore
import os

from .MoviesTableModel import MoviesTableModel, Columns, defaultColumnWidths
from .MovieTableView import MovieTableView


class HistoryWidget(QtWidgets.QFrame):
    """Widget that handles all history list functionality including UI and operations."""
    
    def __init__(self, parent, settings, bgColorA, bgColorB, bgColorC, bgColorD, 
                 moviesSmdbData, historyListSmdbFile, outputCallback):
        super().__init__(parent)
        
        self.parent = parent
        self.settings = settings
        self.bgColorA = bgColorA
        self.bgColorB = bgColorB
        self.bgColorC = bgColorC
        self.bgColorD = bgColorD
        self.moviesSmdbData = moviesSmdbData
        self.listSmdbFile = historyListSmdbFile
        self.output = outputCallback
        
        # State variables
        self.maxHistory = 50
        
        # Table setup
        self.listTableView = MovieTableView()
        self.listDefaultColumns = [Columns.Rank.value,
                                   Columns.Year.value,
                                   Columns.Title.value,
                                   Columns.Rating.value,
                                   Columns.DateWatched.value]
        
        try:
            self.listColumns = self.settings.value('historyListTableColumns',
                                                   self.listDefaultColumns,
                                                   type=list)
            self.listColumns = [int(m) for m in self.listColumns]
        except TypeError:
            self.listColumns = self.listDefaultColumns
        
        try:
            self.listColumnWidths = self.settings.value('historyListTableColumnWidths',
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
        """Initialize the history list UI."""
        self.setFrameShape(QtWidgets.QFrame.Panel | QtWidgets.QFrame.Sunken)
        self.setLineWidth(5)
        self.setStyleSheet(f"background: {self.bgColorB};"
                          f"border-radius: 10px;")
        
        historyListVLayout = QtWidgets.QVBoxLayout()
        self.setLayout(historyListVLayout)
        
        historyListLabel = QtWidgets.QLabel("History List")
        historyListVLayout.addWidget(historyListLabel)
        
        self.listTableView.setSortingEnabled(True)
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
        
        historyListVLayout.addWidget(self.listTableView)
        
        historyListButtonsHLayout = QtWidgets.QHBoxLayout()
        historyListVLayout.addLayout(historyListButtonsHLayout)
        
        removeButton = QtWidgets.QPushButton('Remove')
        removeButton.clicked.connect(self.listRemove)
        removeButton.setStyleSheet(f"background: {self.bgColorA};"
                                  f"border-radius: 5px;")
        historyListButtonsHLayout.addWidget(removeButton)
    
    def refresh(self):
        """Refresh the history list table."""
        (self.listSmdbData,
         self.listTableModel,
         self.listTableProxyModel,
         self.listColumnsVisible,
         smdbData) = self.parent.refreshTable(self.listSmdbFile,
                                              self.listTableView,
                                              self.listColumns,
                                              self.listColumnWidths,
                                              Columns.Rank.value,
                                              sortAscending=False)
        return (self.listSmdbData,
                self.listTableModel,
                self.listTableProxyModel,
                self.listColumnsVisible,
                smdbData)
    
    def tableRightMenuShow(self, QPos):
        """Show right-click context menu for history list table."""
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
        
        removeFromHistoryListAction = QtWidgets.QAction("Remove From History List", self)
        removeFromHistoryListAction.triggered.connect(self.listRemove)
        rightMenu.addAction(removeFromHistoryListAction)
        
        if len(self.listTableView.selectionModel().selectedRows()) > 0:
            modelIndex = self.listTableView.selectionModel().selectedRows()[0]
            self.parent.clickedTable(modelIndex,
                                    self.listTableModel,
                                    self.listTableProxyModel)
        
        rightMenu.exec_(QtGui.QCursor.pos())
    
    def listAdd(self, table, proxy):
        """Add selected movie to history list."""
        self.listTableModel.aboutToChangeLayout()
        modelIndex = table.selectionModel().selectedRows()[0]
        if not table.isRowHidden(modelIndex.row()):
            sourceIndex = proxy.mapToSource(modelIndex)
            sourceRow = sourceIndex.row()
            moviePath = proxy.sourceModel().getPath(sourceRow)
            # Use parent's current moviesSmdbData instead of the stale copy
            self.listTableModel.addMovie(self.parent.moviesSmdbData,
                                        moviePath)
        rowCount = self.listTableModel.rowCount()
        if rowCount > self.maxHistory:
            self.listTableModel.removeMovies(0, 0)
        
        self.listTableModel.renumberRanks()
        
        self.listTableModel.changedLayout()
        self.parent.writeSmdbFile(self.listSmdbFile,
                                 self.listTableModel,
                                 titlesOnly=True)
    
    def listRemove(self):
        """Remove selected movies from history list."""
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
        
        # Get the movie path from the history list
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
