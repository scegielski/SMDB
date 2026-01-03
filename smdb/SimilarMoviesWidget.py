from PyQt5 import QtGui, QtWidgets, QtCore


class SimilarMoviesWidget(QtWidgets.QFrame):
    """Widget that displays similar movies in a table."""
    
    def __init__(self, parent, bgColorA, bgColorB, bgColorC, bgColorD):
        super().__init__(parent)
        
        self.parent = parent
        self.bgColorA = bgColorA
        self.bgColorB = bgColorB
        self.bgColorC = bgColorC
        self.bgColorD = bgColorD
        
        # Data
        self.similar_movies = []
        self.current_movie_path = None
        
        # Initialize UI
        self.initUI()
    
    def initUI(self):
        """Initialize the similar movies UI."""
        self.setFrameShape(QtWidgets.QFrame.Panel | QtWidgets.QFrame.Sunken)
        self.setLineWidth(5)
        self.setStyleSheet(f"background: {self.bgColorB};"
                          f"border-radius: 10px;")
        
        vLayout = QtWidgets.QVBoxLayout()
        self.setLayout(vLayout)
        
        label = QtWidgets.QLabel("Similar Movies")
        vLayout.addWidget(label)
        
        # Create table
        self.tableWidget = QtWidgets.QTableWidget()
        self.tableWidget.setColumnCount(3)
        self.tableWidget.setHorizontalHeaderLabels(['Year', 'Title', 'Similarity'])
        self.tableWidget.setSortingEnabled(True)
        self.tableWidget.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.tableWidget.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.tableWidget.verticalHeader().hide()
        self.tableWidget.setStyleSheet(f"background: {self.bgColorC};"
                                       f"alternate-background-color: {self.bgColorD};")
        self.tableWidget.setAlternatingRowColors(True)
        self.tableWidget.setShowGrid(False)
        
        # Set column widths
        self.tableWidget.setColumnWidth(0, 60)   # Year
        self.tableWidget.setColumnWidth(1, 400)  # Title
        self.tableWidget.setColumnWidth(2, 100)  # Similarity
        
        # Header styling
        hh = self.tableWidget.horizontalHeader()
        hh.setStyleSheet(f"background: {self.bgColorB};"
                        f"border-radius: 0px;")
        hh.setStretchLastSection(True)
        
        # Connect selection signal
        self.tableWidget.itemSelectionChanged.connect(self.onMovieSelected)
        
        vLayout.addWidget(self.tableWidget)
    
    def updateSimilarMovies(self, similar_movies, movie_path):
        """Update the table with similar movies.
        
        Args:
            similar_movies: List of dicts with 'title', 'year', 'similarity' keys
            movie_path: Path to the currently selected movie
        """
        self.similar_movies = similar_movies or []
        self.current_movie_path = movie_path
        
        # Clear and populate table
        self.tableWidget.setRowCount(0)
        self.tableWidget.setSortingEnabled(False)
        
        for movie in self.similar_movies:
            row = self.tableWidget.rowCount()
            self.tableWidget.insertRow(row)
            
            # Year column
            year = str(movie.get('year', ''))
            yearItem = QtWidgets.QTableWidgetItem(year)
            yearItem.setData(QtCore.Qt.UserRole, movie)  # Store full movie data
            self.tableWidget.setItem(row, 0, yearItem)
            
            # Title column
            title = movie.get('title', '')
            titleItem = QtWidgets.QTableWidgetItem(title)
            titleItem.setData(QtCore.Qt.UserRole, movie)
            self.tableWidget.setItem(row, 1, titleItem)
            
            # Similarity column
            similarity = movie.get('similarity', 0.0)
            similarityItem = QtWidgets.QTableWidgetItem(f"{similarity:.3f}")
            similarityItem.setData(QtCore.Qt.UserRole, movie)
            # Make similarity sortable as number
            similarityItem.setData(QtCore.Qt.UserRole + 1, similarity)
            self.tableWidget.setItem(row, 2, similarityItem)
        
        self.tableWidget.setSortingEnabled(True)
        # Sort by similarity descending by default
        self.tableWidget.sortItems(2, QtCore.Qt.DescendingOrder)
    
    def clearSimilarMovies(self):
        """Clear the similar movies table."""
        self.tableWidget.setRowCount(0)
        self.similar_movies = []
        self.current_movie_path = None
    
    def onMovieSelected(self):
        """Handle movie selection in the similar movies table."""
        selectedItems = self.tableWidget.selectedItems()
        if not selectedItems:
            return
        
        # Get the movie data from the first selected item
        movieData = selectedItems[0].data(QtCore.Qt.UserRole)
        if not movieData:
            return
        
        title = movieData.get('title', '')
        year = movieData.get('year', '')
        
        # Call parent method to select this movie in the main list
        self.parent.selectMovieInMainList(title, year)
