from PyQt5 import QtGui, QtWidgets, QtCore
import os


# Define available columns for similar movies
class SimilarMovieColumns:
    """Column definitions for similar movies table."""
    COVER = 'Cover'
    YEAR = 'Year'
    TITLE = 'Title'
    RATING = 'Rating'
    MPAA_RATING = 'MPAA Rating'
    RUNTIME = 'Runtime'
    DIRECTORS = 'Directors'
    GENRES = 'Genres'
    COUNTRIES = 'Countries'
    COMPANIES = 'Companies'
    USER_TAGS = 'User Tags'
    ID = 'ID'
    FOLDER = 'Folder'
    BOX_OFFICE = 'Box Office'
    SIMILARITY = 'Similarity'
    
    # Default visible columns
    DEFAULT_VISIBLE = [COVER, YEAR, TITLE, SIMILARITY]
    
    # All available columns
    ALL_COLUMNS = [
        COVER, YEAR, TITLE, RATING, MPAA_RATING, RUNTIME,
        DIRECTORS, GENRES, COUNTRIES, COMPANIES, USER_TAGS,
        ID, FOLDER, BOX_OFFICE, SIMILARITY
    ]
    
    # Default widths
    DEFAULT_WIDTHS = {
        COVER: 120,
        YEAR: 60,
        TITLE: 400,
        RATING: 60,
        MPAA_RATING: 100,
        RUNTIME: 60,
        DIRECTORS: 150,
        GENRES: 150,
        COUNTRIES: 150,
        COMPANIES: 150,
        USER_TAGS: 150,
        ID: 60,
        FOLDER: 200,
        BOX_OFFICE: 150,
        SIMILARITY: 100
    }


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
        
        # Column configuration
        self.visible_columns = []
        self.column_widths = {}
        
        # Load settings
        self.loadSettings()
        
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
        self.countSpinBox.editingFinished.connect(self.onCountChanged)
        topBar.addWidget(self.countSpinBox)
        
        vLayout.addLayout(topBar)
        
        # Collapsible weight controls section
        weightsSection = QtWidgets.QWidget()
        weightsSectionLayout = QtWidgets.QVBoxLayout()
        weightsSectionLayout.setContentsMargins(0, 0, 0, 0)
        weightsSectionLayout.setSpacing(2)
        weightsSection.setLayout(weightsSectionLayout)
        
        # Header with toggle button
        weightsHeader = QtWidgets.QWidget()
        weightsHeaderLayout = QtWidgets.QHBoxLayout()
        weightsHeaderLayout.setContentsMargins(5, 2, 5, 2)
        weightsHeader.setLayout(weightsHeaderLayout)
        
        self.weightsToggleButton = QtWidgets.QToolButton()
        self.weightsToggleButton.setArrowType(QtCore.Qt.RightArrow)
        self.weightsToggleButton.setCheckable(True)
        self.weightsToggleButton.setChecked(False)
        self.weightsToggleButton.setStyleSheet("QToolButton { border: none; }")
        self.weightsToggleButton.toggled.connect(self.onWeightsToggled)
        weightsHeaderLayout.addWidget(self.weightsToggleButton)
        
        weightsLabel = QtWidgets.QLabel("Embedding Weights")
        weightsLabel.setToolTip("Adjust weights for content vs metadata similarity")
        weightsHeaderLayout.addWidget(weightsLabel)
        weightsHeaderLayout.addStretch()
        
        weightsSectionLayout.addWidget(weightsHeader)
        
        # Container for the sliders (collapsible content)
        self.weightsContainer = QtWidgets.QFrame()
        self.weightsContainer.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.weightsContainer.setVisible(False)  # Hidden by default
        weightsContainerLayout = QtWidgets.QVBoxLayout()
        weightsContainerLayout.setContentsMargins(10, 5, 10, 5)
        self.weightsContainer.setLayout(weightsContainerLayout)
        
        # Content weight slider row
        contentRow = QtWidgets.QHBoxLayout()
        contentLabel = QtWidgets.QLabel("Content:")
        contentLabel.setToolTip("Weight for semantic content (plot, synopsis)")
        contentRow.addWidget(contentLabel)
        
        self.contentSlider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.contentSlider.setMinimum(0)
        self.contentSlider.setMaximum(100)
        self.contentSlider.setValue(70)  # Default 0.7
        self.contentSlider.setTickPosition(QtWidgets.QSlider.TicksBelow)
        self.contentSlider.setTickInterval(10)
        self.contentSlider.setToolTip("Weight for semantic content similarity (0.0 - 1.0)")
        self.contentSlider.valueChanged.connect(self.onWeightLabelUpdate)
        self.contentSlider.sliderReleased.connect(self.onWeightSliderReleased)
        contentRow.addWidget(self.contentSlider)
        
        self.contentValueLabel = QtWidgets.QLabel("0.70")
        self.contentValueLabel.setMinimumWidth(35)
        contentRow.addWidget(self.contentValueLabel)
        
        weightsContainerLayout.addLayout(contentRow)
        
        # Metadata weight slider row
        metadataRow = QtWidgets.QHBoxLayout()
        metadataLabel = QtWidgets.QLabel("Metadata:")
        metadataLabel.setToolTip("Weight for structured metadata (title, year, genres)")
        metadataRow.addWidget(metadataLabel)
        
        self.metadataSlider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.metadataSlider.setMinimum(0)
        self.metadataSlider.setMaximum(100)
        self.metadataSlider.setValue(30)  # Default 0.3
        self.metadataSlider.setTickPosition(QtWidgets.QSlider.TicksBelow)
        self.metadataSlider.setTickInterval(10)
        self.metadataSlider.setToolTip("Weight for metadata similarity (0.0 - 1.0)")
        self.metadataSlider.valueChanged.connect(self.onWeightLabelUpdate)
        self.metadataSlider.sliderReleased.connect(self.onWeightSliderReleased)
        metadataRow.addWidget(self.metadataSlider)
        
        self.metadataValueLabel = QtWidgets.QLabel("0.30")
        self.metadataValueLabel.setMinimumWidth(35)
        metadataRow.addWidget(self.metadataValueLabel)
        
        weightsContainerLayout.addLayout(metadataRow)
        
        weightsSectionLayout.addWidget(self.weightsContainer)
        
        vLayout.addWidget(weightsSection)
        
        # Create table
        self.tableWidget = QtWidgets.QTableWidget()
        self.setupTable()
        
        # Connect selection signal
        self.tableWidget.itemSelectionChanged.connect(self.onMovieSelected)
        
        # Connect header context menu
        header = self.tableWidget.horizontalHeader()
        header.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        header.customContextMenuRequested.connect(self.showHeaderContextMenu)
        header.sectionResized.connect(self.onColumnResized)
        
        vLayout.addWidget(self.tableWidget)
    
    def updateSimilarMovies(self, similar_movies, movie_path):
        """Update the table with similar movies.
        
        Args:
            similar_movies: List of dicts with movie data
            movie_path: Path to the currently selected movie
        """
        self.similar_movies = similar_movies or []
        self.current_movie_path = movie_path
        
        # Populate table with new data
        self.populateTable()
    
    def clearSimilarMovies(self):
        """Clear the similar movies table."""
        self.tableWidget.setRowCount(0)
        self.similar_movies = []
        self.current_movie_path = None
    
    def onCountChanged(self):
        """Handle change in the number of similar movies to display (on Enter or focus loss)."""
        # Recalculate similar movies with new count if we have a current movie
        value = self.countSpinBox.value()
        if self.current_movie_path:
            content_weight, metadata_weight = self.getWeights()
            self.parent.refreshSimilarMovies(self.current_movie_path, k=value, 
                                            content_weight=content_weight, 
                                            metadata_weight=metadata_weight)
    
    def onWeightLabelUpdate(self, value):
        """Update weight labels while dragging slider (no recalculation)."""
        # Update value labels only
        content_weight = self.contentSlider.value() / 100.0
        metadata_weight = self.metadataSlider.value() / 100.0
        
        self.contentValueLabel.setText(f"{content_weight:.2f}")
        self.metadataValueLabel.setText(f"{metadata_weight:.2f}")
    
    def onWeightSliderReleased(self):
        """Handle slider release - recalculate similar movies."""
        # Recalculate similar movies with new weights if we have a current movie
        if self.current_movie_path:
            content_weight, metadata_weight = self.getWeights()
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
    
    def onWeightsToggled(self, checked):
        """Handle expanding/collapsing the weights section."""
        self.weightsContainer.setVisible(checked)
        if checked:
            self.weightsToggleButton.setArrowType(QtCore.Qt.DownArrow)
        else:
            self.weightsToggleButton.setArrowType(QtCore.Qt.RightArrow)
    
    def loadSettings(self):
        """Load column settings from QSettings."""
        settings = QtCore.QSettings('SMDB', 'SimilarMovies')
        
        # Load visible columns
        saved_columns = settings.value('visibleColumns', SimilarMovieColumns.DEFAULT_VISIBLE)
        if saved_columns:
            self.visible_columns = saved_columns
        else:
            self.visible_columns = SimilarMovieColumns.DEFAULT_VISIBLE.copy()
        
        # Load column widths
        self.column_widths = {}
        for col in SimilarMovieColumns.ALL_COLUMNS:
            width = settings.value(f'columnWidth/{col}', SimilarMovieColumns.DEFAULT_WIDTHS.get(col, 100))
            self.column_widths[col] = int(width)
    
    def saveSettings(self):
        """Save column settings to QSettings."""
        settings = QtCore.QSettings('SMDB', 'SimilarMovies')
        settings.setValue('visibleColumns', self.visible_columns)
        
        for col, width in self.column_widths.items():
            settings.setValue(f'columnWidth/{col}', width)
    
    def setupTable(self):
        """Setup table columns based on visible_columns."""
        self.tableWidget.clear()
        self.tableWidget.setColumnCount(len(self.visible_columns))
        self.tableWidget.setHorizontalHeaderLabels(self.visible_columns)
        
        # Configure table
        self.tableWidget.setSortingEnabled(True)
        self.tableWidget.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.tableWidget.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.tableWidget.verticalHeader().hide()
        self.tableWidget.setStyleSheet(f"background: {self.bgColorC};"
                                       f"alternate-background-color: {self.bgColorD};")
        self.tableWidget.setAlternatingRowColors(True)
        self.tableWidget.setShowGrid(False)
        
        # Set row height
        self.tableWidget.verticalHeader().setDefaultSectionSize(100)
        
        # Set column widths
        for idx, col_name in enumerate(self.visible_columns):
            width = self.column_widths.get(col_name, SimilarMovieColumns.DEFAULT_WIDTHS.get(col_name, 100))
            self.tableWidget.setColumnWidth(idx, width)
        
        # Header styling
        hh = self.tableWidget.horizontalHeader()
        hh.setStyleSheet(f"background: {self.bgColorB}; border-radius: 0px;")
        hh.setStretchLastSection(True)
        hh.setSectionsMovable(True)
        hh.setDragEnabled(True)
        hh.setDragDropMode(QtWidgets.QAbstractItemView.InternalMove)
    
    def showHeaderContextMenu(self, position):
        """Show context menu for column visibility."""
        menu = QtWidgets.QMenu(self)
        
        # Add column visibility options
        for col_name in SimilarMovieColumns.ALL_COLUMNS:
            action = QtWidgets.QAction(col_name, self)
            action.setCheckable(True)
            action.setChecked(col_name in self.visible_columns)
            # Similarity column is always visible
            if col_name == SimilarMovieColumns.SIMILARITY:
                action.setEnabled(False)
            action.triggered.connect(lambda checked, col=col_name: self.toggleColumn(col, checked))
            menu.addAction(action)
        
        menu.addSeparator()
        
        # Reset to defaults
        resetAction = QtWidgets.QAction("Reset to Defaults", self)
        resetAction.triggered.connect(self.resetColumnsToDefaults)
        menu.addAction(resetAction)
        
        menu.exec_(self.tableWidget.horizontalHeader().mapToGlobal(position))
    
    def toggleColumn(self, col_name, checked):
        """Toggle column visibility."""
        if checked and col_name not in self.visible_columns:
            # Add column - insert before Similarity if it exists
            if SimilarMovieColumns.SIMILARITY in self.visible_columns:
                idx = self.visible_columns.index(SimilarMovieColumns.SIMILARITY)
                self.visible_columns.insert(idx, col_name)
            else:
                self.visible_columns.append(col_name)
        elif not checked and col_name in self.visible_columns:
            self.visible_columns.remove(col_name)
        
        # Rebuild table and refresh data
        self.setupTable()
        if self.similar_movies:
            self.populateTable()
        
        self.saveSettings()
    
    def resetColumnsToDefaults(self):
        """Reset columns to default configuration."""
        self.visible_columns = SimilarMovieColumns.DEFAULT_VISIBLE.copy()
        self.column_widths = SimilarMovieColumns.DEFAULT_WIDTHS.copy()
        
        self.setupTable()
        if self.similar_movies:
            self.populateTable()
        
        self.saveSettings()
    
    def onColumnResized(self, logicalIndex, oldSize, newSize):
        """Handle column resize event."""
        if logicalIndex < len(self.visible_columns):
            col_name = self.visible_columns[logicalIndex]
            self.column_widths[col_name] = newSize
            self.saveSettings()
    
    def getColumnIndex(self, col_name):
        """Get the index of a column by name."""
        try:
            return self.visible_columns.index(col_name)
        except ValueError:
            return -1
    
    def populateTable(self):
        """Populate table with current similar_movies data."""
        self.tableWidget.setRowCount(0)
        self.tableWidget.setSortingEnabled(False)
        
        for movie in self.similar_movies:
            self.addMovieRow(movie)
        
        self.tableWidget.setSortingEnabled(True)
        # Sort by similarity if visible
        sim_idx = self.getColumnIndex(SimilarMovieColumns.SIMILARITY)
        if sim_idx >= 0:
            self.tableWidget.sortItems(sim_idx, QtCore.Qt.DescendingOrder)
    
    def addMovieRow(self, movie):
        """Add a movie to the table."""
        row = self.tableWidget.rowCount()
        self.tableWidget.insertRow(row)
        
        movie_folder = movie.get('folder', '')
        movie_path_str = movie.get('path', '')
        
        for idx, col_name in enumerate(self.visible_columns):
            if col_name == SimilarMovieColumns.COVER:
                # Cover column
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
                
                coverLabel.setProperty('movieData', movie)
                self.tableWidget.setCellWidget(row, idx, coverLabel)
            
            else:
                # Text columns
                text = self.getMovieColumnValue(movie, col_name)
                item = QtWidgets.QTableWidgetItem(text)
                item.setData(QtCore.Qt.UserRole, movie)
                
                # Make similarity column sortable as number
                if col_name == SimilarMovieColumns.SIMILARITY:
                    try:
                        item.setData(QtCore.Qt.UserRole + 1, float(movie.get('similarity', 0.0)))
                    except (ValueError, TypeError):
                        pass
                
                self.tableWidget.setItem(row, idx, item)
    
    def getMovieColumnValue(self, movie, col_name):
        """Get the display value for a movie column."""
        if col_name == SimilarMovieColumns.YEAR:
            return str(movie.get('year', ''))
        elif col_name == SimilarMovieColumns.TITLE:
            return movie.get('title', '')
        elif col_name == SimilarMovieColumns.SIMILARITY:
            return f"{movie.get('similarity', 0.0):.3f}"
        elif col_name == SimilarMovieColumns.RATING:
            return str(movie.get('rating', ''))
        elif col_name == SimilarMovieColumns.MPAA_RATING:
            return movie.get('mpaa_rating', '')
        elif col_name == SimilarMovieColumns.RUNTIME:
            return str(movie.get('runtime', ''))
        elif col_name == SimilarMovieColumns.DIRECTORS:
            directors = movie.get('directors', [])
            return ', '.join(directors) if isinstance(directors, list) else str(directors)
        elif col_name == SimilarMovieColumns.GENRES:
            genres = movie.get('genres', [])
            return ', '.join(genres) if isinstance(genres, list) else str(genres)
        elif col_name == SimilarMovieColumns.COUNTRIES:
            countries = movie.get('countries', [])
            return ', '.join(countries) if isinstance(countries, list) else str(countries)
        elif col_name == SimilarMovieColumns.COMPANIES:
            companies = movie.get('companies', [])
            return ', '.join(companies) if isinstance(companies, list) else str(companies)
        elif col_name == SimilarMovieColumns.USER_TAGS:
            tags = movie.get('user_tags', [])
            return ', '.join(tags) if isinstance(tags, list) else str(tags)
        elif col_name == SimilarMovieColumns.ID:
            return str(movie.get('id', ''))
        elif col_name == SimilarMovieColumns.FOLDER:
            return movie.get('folder', '')
        elif col_name == SimilarMovieColumns.BOX_OFFICE:
            return movie.get('box_office', '')
        else:
            return ''
