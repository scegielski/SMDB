from PyQt5 import QtGui, QtWidgets, QtCore

from .utilities import *

class FilterTable(QtWidgets.QTableWidget):
    def __init__(self):
        super(FilterTable, self).__init__()
        self.mouseLocation = 0

    def mousePressEvent(self, event):
        if event.type() == QtCore.QEvent.MouseButtonPress:
            if event.button() == QtCore.Qt.RightButton:
                self.mouseLocation = event.pos()
                return
            else:
                super(FilterTable, self).mousePressEvent(event)


class FilterWidget(QtWidgets.QFrame):

    tableSelectionChangedSignal = QtCore.pyqtSignal()
    wheelSpun = QtCore.pyqtSignal(int)

    def wheelEvent(self, event):
        dy = event.angleDelta().y()
        self.wheelSpun.emit(1 if dy > 0 else (-1 if dy < 0 else 0))
        event.accept()

    def __init__(self,
                 filterName="filter",
                 filterBy=0,
                 useMovieList=False,
                 minCount=2,
                 defaultSectionSize=18,
                 column0Width=170,
                 column1Width=60,
                 bgColorA='rgb(50, 50, 50)',
                 bgColorB='rgb(25, 25, 25)',
                 bgColorC='rgb(0, 0, 0)',
                 bgColorD='rgb(15, 15, 15)',
                 fgColor='rgb(255, 255, 255)'):
        super(FilterWidget, self).__init__()

        self.bgColorA = bgColorA
        self.bgColorB = bgColorB
        self.bgColorC = bgColorC
        self.bgColorD = bgColorD
        self.fgColor = fgColor

        self.moviesSmdbData = None
        self.movieList = list()
        self.useMovieList = useMovieList

        self.filterByDict = {
            'Director': 'directors',
            'Actor': 'actors',
            'Genre': 'genres',
            'Mpaa Rating': 'mpaa ratings',
            'User Tags': 'user tags',
            'Year': 'years',
            'Companies': 'companies',
            'Country': 'countries',
            'Ratings': 'ratings'
        }

        self.setFrameShape(QtWidgets.QFrame.Panel | QtWidgets.QFrame.Sunken)
        self.setLineWidth(5)

        filtersVLayout = QtWidgets.QVBoxLayout()
        self.setLayout(filtersVLayout)

        filtersVLayout.addWidget(QtWidgets.QLabel(filterName))

        filterByHLayout = QtWidgets.QHBoxLayout()
        self.layout().addLayout(filterByHLayout)

        filterByLabel = QtWidgets.QLabel("Filter By")
        filterByLabel.setSizePolicy(QtWidgets.QSizePolicy.Maximum,
                                    QtWidgets.QSizePolicy.Maximum)
        filterByHLayout.addWidget(filterByLabel)

        self.filterByComboBox = QtWidgets.QComboBox()
        for i in self.filterByDict.keys():
            self.filterByComboBox.addItem(i)
        self.filterByComboBox.setCurrentIndex(filterBy)
        self.filterByComboBox.activated.connect(self.populateFiltersTable)
        filterByHLayout.addWidget(self.filterByComboBox)

        minCountHLayout = QtWidgets.QHBoxLayout()
        self.layout().addLayout(minCountHLayout)
        self.filterMinCountCheckbox = QtWidgets.QCheckBox()
        self.filterMinCountCheckbox.setText("Enable Min Count")
        self.filterMinCountCheckbox.setChecked(True)
        self.filterMinCountSpinBox = QtWidgets.QSpinBox()
        self.filterMinCountCheckbox.stateChanged.connect(self.filterMinCountSpinBox.setEnabled)
        self.filterMinCountCheckbox.stateChanged.connect(self.populateFiltersTable)
        minCountHLayout.addWidget(self.filterMinCountCheckbox)

        self.filterMinCountSpinBox.setMinimum(0)
        self.filterMinCountSpinBox.setValue(minCount)
        self.filterMinCountSpinBox.valueChanged.connect(self.populateFiltersTable)
        minCountHLayout.addWidget(self.filterMinCountSpinBox)

        self.filterTable = FilterTable()
        self.filterTable.setColumnCount(2)
        self.filterTable.verticalHeader().hide()
        self.filterTable.setHorizontalHeaderLabels(['Name', 'Count'])
        self.filterTable.setColumnWidth(0, column0Width)
        self.filterTable.setColumnWidth(1, column1Width)
        self.filterTable.verticalHeader().setMinimumSectionSize(10)
        self.filterTable.verticalHeader().setDefaultSectionSize(defaultSectionSize)
        self.filterTable.setWordWrap(False)
        self.filterTable.setAlternatingRowColors(True)
        self.filterTable.itemSelectionChanged.connect(lambda: self.tableSelectionChangedSignal.emit())
        filtersVLayout.addWidget(self.filterTable)

        filtersSearchHLayout = QtWidgets.QHBoxLayout()
        filtersVLayout.addLayout(filtersSearchHLayout)

        searchText = QtWidgets.QLabel("Search")
        searchText.setSizePolicy(QtWidgets.QSizePolicy.Maximum,
                                 QtWidgets.QSizePolicy.Maximum)
        filtersSearchHLayout.addWidget(searchText)

        self.searchBox = QtWidgets.QLineEdit(self)
        self.searchBox.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Maximum)
        self.searchBox.setClearButtonEnabled(True)
        filtersSearchHLayout.addWidget(self.searchBox)
        self.searchBox.textChanged.connect(lambda: searchTableWidget(self.searchBox,
                                                                     self.filterTable))
        self.setStyleSheets()

    def setStyleSheets(self):
        self.setStyleSheet(f"background: {self.bgColorB};"
                           f"color: {self.fgColor};"
                           f"border-radius: 10px;")

        self.filterByComboBox.setStyleSheet(f"background: {self.bgColorA};"
                                            f"border-radius: 0px;")

        self.filterMinCountSpinBox.setStyleSheet(f"background: {self.bgColorC};")

        self.filterTable.setStyleSheet(f"background: {self.bgColorC};"
                                       f"alternate-background-color: {self.bgColorD};")

        self.filterTable.horizontalHeader().setStyleSheet(f"background: {self.bgColorB};"
                                                          f"border-radius: 0px;")

        self.searchBox.setStyleSheet(f"background: {self.bgColorC};"
                                     f"border-radius: 5px;")

    def filterRightMenu(self):
        rightMenu = QtWidgets.QMenu(self.filterTable)
        selectedItem = self.filterTable.itemAt(self.filterTable.mouseLocation)
        row = selectedItem.row()
        openImdbAction = QtWidgets.QAction("Open IMDB Page", self)
        itemText = self.filterTable.item(row, 0).text()
        filterByText = self.filterByComboBox.currentText()
        if filterByText == 'Director' or filterByText == 'Actor':
            openImdbAction.triggered.connect(lambda: openPersonImdbPage(itemText))
        else:
            openImdbAction.triggered.connect(lambda: openYearImdbPage(itemText))
        rightMenu.addAction(openImdbAction)
        rightMenu.exec_(QtGui.QCursor.pos())

    def populateFiltersTable(self):
        if not self.moviesSmdbData:
            output("Error: No smbdData")
            return

        if self.useMovieList and len(self.movieList) == 0:
            return

        filterByText = self.filterByComboBox.currentText()
        filterByKey = self.filterByDict[filterByText]

        showMenuTexts = ['Director', 'Actor', 'Year']
        if filterByText in showMenuTexts:
            self.filterTable.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
            try:
                self.filterTable.customContextMenuRequested[QtCore.QPoint].disconnect()
            except Exception:
                pass
            self.filterTable.customContextMenuRequested[QtCore.QPoint].connect(
                self.filterRightMenu)
        else:
            self.filterTable.setContextMenuPolicy(QtCore.Qt.NoContextMenu)

        if filterByKey not in self.moviesSmdbData:
            output("Error: '%s' not in smdbData" % filterByKey)
            return

        self.filterTable.clear()
        self.filterTable.setHorizontalHeaderLabels(['Name', 'Count'])

        row = 0
        numActualRows = 0
        numRows = len(self.moviesSmdbData[filterByKey].keys())
        self.filterTable.setRowCount(numRows)
        self.filterTable.setSortingEnabled(False)
        for name in self.moviesSmdbData[filterByKey].keys():
            if self.useMovieList:
                movies = self.moviesSmdbData[filterByKey][name]['movies']
                count = 0
                for movie in self.movieList:
                    if movie in movies:
                        count = count + 1
            else:
                count = self.moviesSmdbData[filterByKey][name]['num movies']

            if self.filterMinCountCheckbox.isChecked() and count < self.filterMinCountSpinBox.value():
                continue

            nameItem = QtWidgets.QTableWidgetItem(name)
            self.filterTable.setItem(row, 0, nameItem)
            countItem = QtWidgets.QTableWidgetItem('%04d' % count)
            self.filterTable.setItem(row, 1, countItem)
            row += 1
            numActualRows += 1

        self.filterTable.setRowCount(numActualRows)
        if not self.useMovieList:
            self.filterTable.sortItems(1, QtCore.Qt.DescendingOrder)
        self.filterTable.setSortingEnabled(True)
