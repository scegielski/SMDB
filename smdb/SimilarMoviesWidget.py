from PyQt5 import QtGui, QtWidgets, QtCore
import os


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
        
        # Top bar with label and count control
        topBar = QtWidgets.QHBoxLayout()
        
        label = QtWidgets.QLabel("Similar Movies")
        topBar.addWidget(label)
        
        topBar.addStretch()
        
        # Add spinbox for controlling number of movies shown
        countLabel = QtWidgets.QLabel("Show:")
        topBar.addWidget(countLabel)
        
        self.countSpinBox = QtWidgets.QSpinBox()
        self.countSpinBox.setMinimum(5)
        self.countSpinBox.setMaximum(100)
        self.countSpinBox.setValue(20)
        self.countSpinBox.setSingleStep(5)
        self.countSpinBox.setToolTip("Number of similar movies to display")
        self.countSpinBox.valueChanged.connect(self.onCountChanged)
        topBar.addWidget(self.countSpinBox)
        
        vLayout.addLayout(topBar)
        
        # Second bar with weight controls for hybrid embeddings
        weightsBar = QtWidgets.QHBoxLayout()
        
        # Content weight slider
        contentLabel = QtWidgets.QLabel("Content:")
        contentLabel.setToolTip("Weight for semantic content (plot, synopsis)")
        weightsBar.addWidget(contentLabel)
        
        self.contentSlider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.contentSlider.setMinimum(0)
        self.contentSlider.setMaximum(100)
        self.contentSlider.setValue(70)  # Default 0.7
        self.contentSlider.setTickPosition(QtWidgets.QSlider.TicksBelow)
        self.contentSlider.setTickInterval(10)
        self.contentSlider.setToolTip("Weight for semantic content similarity (0.0 - 1.0)")
        self.contentSlider.valueChanged.connect(self.onWeightChanged)
        weightsBar.addWidget(self.contentSlider)
        
        self.contentValueLabel = QtWidgets.QLabel("0.70")
        self.contentValueLabel.setMinimumWidth(35)
        weightsBar.addWidget(self.contentValueLabel)
        
        weightsBar.addSpacing(15)
        
        # Metadata weight slider
        metadataLabel = QtWidgets.QLabel("Metadata:")
        metadataLabel.setToolTip("Weight for structured metadata (title, year, genres)")
        weightsBar.addWidget(metadataLabel)
        
        self.metadataSlider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.metadataSlider.setMinimum(0)
        self.metadataSlider.setMaximum(100)
        self.metadataSlider.setValue(30)  # Default 0.3
        self.metadataSlider.setTickPosition(QtWidgets.QSlider.TicksBelow)
        self.metadataSlider.setTickInterval(10)
        self.metadataSlider.setToolTip("Weight for metadata similarity (0.0 - 1.0)")
        self.metadataSlider.valueChanged.connect(self.onWeightChanged)
        weightsBar.addWidget(self.metadataSlider)
        
        self.metadataValueLabel = QtWidgets.QLabel("0.30")
        self.metadataValueLabel.setMinimumWidth(35)
        weightsBar.addWidget(self.metadataValueLabel)
        
        vLayout.addLayout(weightsBar)
        
        # Create table
        self.tableWidget = QtWidgets.QTableWidget()
        self.tableWidget.setColumnCount(4)
        self.tableWidget.setHorizontalHeaderLabels(['Cover', 'Year', 'Title', 'Similarity'])
        self.tableWidget.setSortingEnabled(True)
        self.tableWidget.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.tableWidget.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.tableWidget.verticalHeader().hide()
        self.tableWidget.setStyleSheet(f"background: {self.bgColorC};"
                                       f"alternate-background-color: {self.bgColorD};")
        self.tableWidget.setAlternatingRowColors(True)
        self.tableWidget.setShowGrid(False)
        
        # Set column widths
        self.tableWidget.setColumnWidth(0, 120)  # Cover
        self.tableWidget.setColumnWidth(1, 60)   # Year
        self.tableWidget.setColumnWidth(2, 400)  # Title
        self.tableWidget.setColumnWidth(3, 100)  # Similarity
        
        # Set row height for covers
        self.tableWidget.verticalHeader().setDefaultSectionSize(100)
        
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
            similar_movies: List of dicts with 'title', 'year', 'similarity', 'path', 'folder' keys
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
            
            # Cover column
            movie_folder = movie.get('folder', '')
            movie_path_str = movie.get('path', '')
            coverFile = os.path.join(movie_path_str, f'{movie_folder}.jpg')
            if not os.path.exists(coverFile):
                coverFilePng = os.path.join(movie_path_str, f'{movie_folder}.png')
                if os.path.exists(coverFilePng):
                    coverFile = coverFilePng
            
            coverLabel = QtWidgets.QLabel()
            if os.path.exists(coverFile):
                pm = QtGui.QPixmap(coverFile)
                if not pm.isNull():
                    scaled_pm = pm.scaled(100, 100, 
                                         QtCore.Qt.KeepAspectRatio,
                                         QtCore.Qt.SmoothTransformation)
                    coverLabel.setPixmap(scaled_pm)
                    coverLabel.setAlignment(QtCore.Qt.AlignCenter)
            else:
                coverLabel.setText("No Cover")
                coverLabel.setAlignment(QtCore.Qt.AlignCenter)
            
            # Store movie data in the label
            coverLabel.setProperty('movieData', movie)
            self.tableWidget.setCellWidget(row, 0, coverLabel)
            
            # Year column
            year = str(movie.get('year', ''))
            yearItem = QtWidgets.QTableWidgetItem(year)
            yearItem.setData(QtCore.Qt.UserRole, movie)  # Store full movie data
            self.tableWidget.setItem(row, 1, yearItem)
            
            # Title column
            title = movie.get('title', '')
            titleItem = QtWidgets.QTableWidgetItem(title)
            titleItem.setData(QtCore.Qt.UserRole, movie)
            self.tableWidget.setItem(row, 2, titleItem)
            
            # Similarity column
            similarity = movie.get('similarity', 0.0)
            similarityItem = QtWidgets.QTableWidgetItem(f"{similarity:.3f}")
            similarityItem.setData(QtCore.Qt.UserRole, movie)
            # Make similarity sortable as number
            similarityItem.setData(QtCore.Qt.UserRole + 1, similarity)
            self.tableWidget.setItem(row, 3, similarityItem)
        
        self.tableWidget.setSortingEnabled(True)
        # Sort by similarity descending by default
        self.tableWidget.sortItems(3, QtCore.Qt.DescendingOrder)
    
    def clearSimilarMovies(self):
        """Clear the similar movies table."""
        self.tableWidget.setRowCount(0)
        self.similar_movies = []
        self.current_movie_path = None
    
    def onCountChanged(self, value):
        """Handle change in the number of similar movies to display."""
        # Recalculate similar movies with new count if we have a current movie
        if self.current_movie_path:
            content_weight, metadata_weight = self.getWeights()
            self.parent.refreshSimilarMovies(self.current_movie_path, k=value, 
                                            content_weight=content_weight, 
                                            metadata_weight=metadata_weight)
    
    def onWeightChanged(self, value):
        """Handle change in weight sliders."""
        # Update value labels
        content_weight = self.contentSlider.value() / 100.0
        metadata_weight = self.metadataSlider.value() / 100.0
        
        self.contentValueLabel.setText(f"{content_weight:.2f}")
        self.metadataValueLabel.setText(f"{metadata_weight:.2f}")
        
        # Recalculate similar movies with new weights if we have a current movie
        if self.current_movie_path:
            k = self.countSpinBox.value()
            self.parent.refreshSimilarMovies(self.current_movie_path, k=k,
                                            content_weight=content_weight,
                                            metadata_weight=metadata_weight)
    
    def getWeights(self):
        """Get the current weight settings for hybrid embeddings.
        
        Returns:
            Tuple of (content_weight, metadata_weight) as floats 0.0-1.0
        """
        content_weight = self.contentSlider.value() / 100.0
        metadata_weight = self.metadataSlider.value() / 100.0
        return (content_weight, metadata_weight)
    
    def getSimilarMoviesCount(self):
        """Get the current count setting for similar movies."""
        return self.countSpinBox.value()
    
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
