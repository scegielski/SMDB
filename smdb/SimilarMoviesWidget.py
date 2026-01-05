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


class SimilarMoviesTableWidget(QtWidgets.QTableWidget):
    """Custom table widget with controlled wheel scrolling and tooltips."""
    
    def wheelEvent(self, event):
        """Override wheel event to scroll exactly one row per wheel click."""
        # Get the wheel delta (typically ±120 per notch)
        delta = event.angleDelta().y()
        
        if delta != 0:
            # Get the vertical scrollbar
            scrollBar = self.verticalScrollBar()
            
            # Calculate number of steps (typically 120 units per notch)
            # Most mice send ±120 per click
            steps = delta / 120
            
            # Use the singleStep value which should be set to row height
            step_size = scrollBar.singleStep()
            
            # Calculate the scroll amount (negative steps for scrolling down)
            scroll_amount = -int(steps * step_size)
            
            # Apply the scroll
            new_value = scrollBar.value() + scroll_amount
            scrollBar.setValue(new_value)
            
            event.accept()
        else:
            super().wheelEvent(event)
    
    def viewportEvent(self, event):
        """Override viewport event to handle custom tooltips."""
        if event.type() == QtCore.QEvent.ToolTip:
            # Get the position where the tooltip should appear
            help_event = event
            pos = help_event.pos()
            
            # Try to get movie data from either item or widget
            movie_data = None
            
            # First, try to get the item at this position
            item = self.itemAt(pos)
            if item:
                movie_data = item.data(QtCore.Qt.UserRole)
            
            # If no item, check if there's a widget (like the cover column)
            if not movie_data:
                row = self.rowAt(pos.y())
                col = self.columnAt(pos.x())
                if row >= 0 and col >= 0:
                    widget = self.cellWidget(row, col)
                    if widget:
                        movie_data = widget.property('movieData')
                    # If still no data from widget, try to get from any other column in the same row
                    if not movie_data:
                        for c in range(self.columnCount()):
                            item = self.item(row, c)
                            if item:
                                movie_data = item.data(QtCore.Qt.UserRole)
                                if movie_data:
                                    break
            
            if movie_data:
                # Generate and show the tooltip
                tooltip = self.generateMovieTooltip(movie_data)
                QtWidgets.QToolTip.showText(help_event.globalPos(), tooltip, self)
                return True
            
            # If we get here, hide any existing tooltip
            QtWidgets.QToolTip.hideText()
            return True
        
        return super().viewportEvent(event)
    
    def generateMovieTooltip(self, movie_data):
        """Generate a formatted tooltip for a movie.
        
        Args:
            movie_data: Dictionary containing movie information
            
        Returns:
            Formatted string with movie details
        """
        title = movie_data.get('title', 'Unknown')
        year = movie_data.get('year', '')
        
        # Debug: Print available keys and cast value to see what data we have
        print(f"Movie data keys: {list(movie_data.keys())}")
        print(f"Cast value: {movie_data.get('cast')} (type: {type(movie_data.get('cast'))})")
        print(f"Plot value length: {len(movie_data.get('plot', ''))} chars")
        print(f"Synopsis value length: {len(movie_data.get('synopsis', ''))} chars")
        
        # Build tooltip parts
        parts = []
        
        # Title and year
        if year:
            parts.append(f"<b>{title} ({year})</b>")
        else:
            parts.append(f"<b>{title}</b>")
        
        # Genres
        genres = movie_data.get('genres', [])
        if genres:
            if isinstance(genres, list):
                genre_str = ', '.join(genres)
            else:
                genre_str = str(genres)
            parts.append(f"<b>Genre:</b> {genre_str}")
        
        # Directors
        directors = movie_data.get('directors', [])
        if directors:
            if isinstance(directors, list):
                director_str = ', '.join(directors)
            else:
                director_str = str(directors)
            parts.append(f"<b>Director:</b> {director_str}")
        
        # Actors (cast)
        cast = movie_data.get('cast', [])
        print(f"Cast after get: {cast}, bool: {bool(cast)}")
        if cast:
            if isinstance(cast, list):
                # Limit to first 5 actors
                actor_list = cast[:5]
                actor_str = ', '.join(actor_list)
                if len(cast) > 5:
                    actor_str += ', ...'
            else:
                actor_str = str(cast)
            parts.append(f"<b>Actors:</b> {actor_str}")
        
        # Plot
        plot = movie_data.get('plot', '') or movie_data.get('synopsis', '')
        if plot:
            # Limit plot length for tooltip
            max_plot_length = 500
            if len(plot) > max_plot_length:
                plot = plot[:max_plot_length] + '...'
            parts.append(f"<b>Plot:</b> {plot}")
        
        # Wrap in styled div for better visibility
        content = '<br>'.join(parts)
        styled_tooltip = f'''
        <div style="
            background-color: #2b2b2b;
            border: 2px solid #888888;
            border-radius: 5px;
            padding: 10px;
            color: #ffffff;
        ">
            {content}
        </div>
        '''
        return styled_tooltip


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
        self.master_column_order = []  # Complete order including hidden columns
        
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
        
        # Title bar
        titleBar = QtWidgets.QHBoxLayout()
        label = QtWidgets.QLabel("Similar Movies")
        titleBar.addWidget(label)
        titleBar.addStretch()
        vLayout.addLayout(titleBar)
        
        # Collapsible options section
        optionsSection = QtWidgets.QWidget()
        optionsSectionLayout = QtWidgets.QVBoxLayout()
        optionsSectionLayout.setContentsMargins(0, 0, 0, 0)
        optionsSectionLayout.setSpacing(2)
        optionsSection.setLayout(optionsSectionLayout)
        
        # Header with toggle button
        optionsHeader = QtWidgets.QWidget()
        optionsHeaderLayout = QtWidgets.QHBoxLayout()
        optionsHeaderLayout.setContentsMargins(5, 2, 5, 2)
        optionsHeader.setLayout(optionsHeaderLayout)
        
        self.optionsToggleButton = QtWidgets.QToolButton()
        self.optionsToggleButton.setArrowType(QtCore.Qt.RightArrow)
        self.optionsToggleButton.setCheckable(True)
        self.optionsToggleButton.setChecked(False)
        self.optionsToggleButton.setStyleSheet("QToolButton { border: none; }")
        self.optionsToggleButton.toggled.connect(self.onOptionsToggled)
        optionsHeaderLayout.addWidget(self.optionsToggleButton)
        
        optionsLabel = QtWidgets.QLabel("Display Options")
        optionsLabel.setToolTip("Adjust cover scale and results count")
        optionsHeaderLayout.addWidget(optionsLabel)
        optionsHeaderLayout.addStretch()
        
        optionsSectionLayout.addWidget(optionsHeader)
        
        # Container for the controls (collapsible content)
        self.optionsContainer = QtWidgets.QFrame()
        self.optionsContainer.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.optionsContainer.setVisible(False)  # Hidden by default
        optionsContainerLayout = QtWidgets.QVBoxLayout()
        optionsContainerLayout.setContentsMargins(10, 5, 10, 5)
        self.optionsContainer.setLayout(optionsContainerLayout)
        
        # Cover scale slider row
        coverScaleRow = QtWidgets.QHBoxLayout()
        coverScaleLabel = QtWidgets.QLabel("Cover Scale:")
        coverScaleRow.addWidget(coverScaleLabel)
        
        self.coverScaleSlider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.coverScaleSlider.setMinimum(50)
        self.coverScaleSlider.setMaximum(300)
        self.coverScaleSlider.setValue(self.saved_cover_scale)  # Use saved value
        self.coverScaleSlider.setTickInterval(50)
        self.coverScaleSlider.setTickPosition(QtWidgets.QSlider.TicksBelow)
        self.coverScaleSlider.setToolTip("Adjust cover image size")
        self.coverScaleSlider.valueChanged.connect(self.onCoverScaleSliderChanged)
        self.coverScaleSlider.sliderReleased.connect(self.onCoverScaleSliderReleased)
        coverScaleRow.addWidget(self.coverScaleSlider)
        
        self.coverScaleSpinBox = QtWidgets.QSpinBox()
        self.coverScaleSpinBox.setMinimum(50)
        self.coverScaleSpinBox.setMaximum(300)
        self.coverScaleSpinBox.setValue(self.saved_cover_scale)
        self.coverScaleSpinBox.setToolTip("Adjust cover image size")
        self.coverScaleSpinBox.valueChanged.connect(self.onCoverScaleSpinBoxChanged)
        coverScaleRow.addWidget(self.coverScaleSpinBox)
        
        optionsContainerLayout.addLayout(coverScaleRow)
        
        # Results count slider row
        resultsRow = QtWidgets.QHBoxLayout()
        countLabel = QtWidgets.QLabel("Results returned:")
        resultsRow.addWidget(countLabel)
        
        self.resultsSlider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.resultsSlider.setMinimum(1)
        self.resultsSlider.setMaximum(100)
        self.resultsSlider.setValue(20)
        self.resultsSlider.setTickInterval(10)
        self.resultsSlider.setTickPosition(QtWidgets.QSlider.TicksBelow)
        self.resultsSlider.setToolTip("Number of similar movies to display")
        self.resultsSlider.valueChanged.connect(self.onResultsSliderChanged)
        self.resultsSlider.sliderReleased.connect(self.onCountChanged)
        resultsRow.addWidget(self.resultsSlider)
        
        self.countSpinBox = QtWidgets.QSpinBox()
        self.countSpinBox.setMinimum(1)
        self.countSpinBox.setMaximum(100)
        self.countSpinBox.setValue(20)
        self.countSpinBox.setToolTip("Number of similar movies to display")
        self.countSpinBox.valueChanged.connect(self.onResultsSpinBoxChanged)
        self.countSpinBox.editingFinished.connect(self.onCountChanged)
        resultsRow.addWidget(self.countSpinBox)
        
        optionsContainerLayout.addLayout(resultsRow)
        
        optionsSectionLayout.addWidget(self.optionsContainer)
        
        vLayout.addWidget(optionsSection)
        
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
        
        weightsLabel = QtWidgets.QLabel("Criteria Weights")
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
        self.tableWidget = SimilarMoviesTableWidget()
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
        """Handle change in the number of similar movies to display (when slider is released or spinbox editing finished)."""
        # Recalculate similar movies with new count if we have a current movie
        value = self.countSpinBox.value()
        if self.current_movie_path:
            content_weight, metadata_weight = self.getWeights()
            self.parent.refreshSimilarMovies(self.current_movie_path, k=value, 
                                            content_weight=content_weight, 
                                            metadata_weight=metadata_weight)
    
    def onResultsSliderChanged(self, value):
        """Update the spinbox when results slider changes."""
        self.countSpinBox.blockSignals(True)
        self.countSpinBox.setValue(value)
        self.countSpinBox.blockSignals(False)
    
    def onResultsSpinBoxChanged(self, value):
        """Update the slider when results spinbox changes."""
        self.resultsSlider.blockSignals(True)
        self.resultsSlider.setValue(value)
        self.resultsSlider.blockSignals(False)
    
    def onCoverScaleSliderChanged(self, value):
        """Handle cover scale slider change - only sync spinbox."""
        self.coverScaleSpinBox.blockSignals(True)
        self.coverScaleSpinBox.setValue(value)
        self.coverScaleSpinBox.blockSignals(False)
    
    def onCoverScaleSliderReleased(self):
        """Handle cover scale slider release - apply the resize."""
        value = self.coverScaleSlider.value()
        # Update row height and repopulate to resize covers
        if SimilarMovieColumns.COVER in self.visible_columns:
            new_row_height = value + 10  # Add some padding
            self.tableWidget.verticalHeader().setDefaultSectionSize(new_row_height)
            # Set scroll step to match row height
            self.tableWidget.verticalScrollBar().setSingleStep(new_row_height)
            # Repopulate to resize covers
            if self.similar_movies:
                self.populateTable()
    
    def onCoverScaleSpinBoxChanged(self, value):
        """Handle cover scale spinbox change."""
        self.coverScaleSlider.blockSignals(True)
        self.coverScaleSlider.setValue(value)
        self.coverScaleSlider.blockSignals(False)
        # Update row height and repopulate to resize covers
        if SimilarMovieColumns.COVER in self.visible_columns:
            new_row_height = value + 10  # Add some padding
            self.tableWidget.verticalHeader().setDefaultSectionSize(new_row_height)
            # Set scroll step to match row height
            self.tableWidget.verticalScrollBar().setSingleStep(new_row_height)
            # Repopulate to resize covers
            if self.similar_movies:
                self.populateTable()
    
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
    
    def onOptionsToggled(self, checked):
        """Handle expanding/collapsing the options section."""
        self.optionsContainer.setVisible(checked)
        if checked:
            self.optionsToggleButton.setArrowType(QtCore.Qt.DownArrow)
        else:
            self.optionsToggleButton.setArrowType(QtCore.Qt.RightArrow)
    
    def loadSettings(self):
        """Load column settings from QSettings."""
        settings = QtCore.QSettings('SMDB', 'SimilarMovies')
        
        # Load visible columns
        saved_columns = settings.value('visibleColumns', SimilarMovieColumns.DEFAULT_VISIBLE)
        if saved_columns:
            self.visible_columns = saved_columns
        else:
            self.visible_columns = SimilarMovieColumns.DEFAULT_VISIBLE.copy()
        
        # Load master column order (complete order including hidden columns)
        saved_master_order = settings.value('masterColumnOrder', None)
        if saved_master_order and isinstance(saved_master_order, list):
            self.master_column_order = saved_master_order
        else:
            # Default order: all columns
            self.master_column_order = SimilarMovieColumns.ALL_COLUMNS.copy()
        
        # Load column widths
        self.column_widths = {}
        for col in SimilarMovieColumns.ALL_COLUMNS:
            width = settings.value(f'columnWidth/{col}', SimilarMovieColumns.DEFAULT_WIDTHS.get(col, 100))
            self.column_widths[col] = int(width)
        
        # Load cover scale (will be applied after UI is created)
        self.saved_cover_scale = settings.value('coverScale', 150, type=int)
    
    def saveSettings(self):
        """Save column settings to QSettings."""
        settings = QtCore.QSettings('SMDB', 'SimilarMovies')
        settings.setValue('visibleColumns', self.visible_columns)
        
        for col, width in self.column_widths.items():
            settings.setValue(f'columnWidth/{col}', width)
        
        # Save cover scale
        if hasattr(self, 'coverScaleSlider'):
            settings.setValue('coverScale', self.coverScaleSlider.value())
        
        # Update master column order from visual order
        header = self.tableWidget.horizontalHeader()
        orderedColumns = []
        for visual_idx in range(header.count()):
            logical_idx = header.logicalIndex(visual_idx)
            if logical_idx < len(self.visible_columns):
                orderedColumns.append(self.visible_columns[logical_idx])
        
        # Build new master order: start with visible columns in their visual order,
        # then insert hidden columns at their appropriate positions
        hidden_columns = [col for col in self.master_column_order if col not in orderedColumns]
        new_master_order = orderedColumns.copy()
        
        # Insert each hidden column right before the next visible column that comes after it
        for hidden_col in hidden_columns:
            # Find where in the OLD master order this hidden column was
            old_hidden_idx = self.master_column_order.index(hidden_col)
            
            # Find the first visible column that came after it in the old master order
            insert_before = None
            for i in range(old_hidden_idx + 1, len(self.master_column_order)):
                if self.master_column_order[i] in new_master_order:
                    insert_before = self.master_column_order[i]
                    break
            
            if insert_before:
                # Insert hidden column before this visible column
                insert_pos = new_master_order.index(insert_before)
                new_master_order.insert(insert_pos, hidden_col)
            else:
                # No visible column after it, append at end
                new_master_order.append(hidden_col)
        
        self.master_column_order = new_master_order
        settings.setValue('masterColumnOrder', self.master_column_order)
        settings.setValue('columnOrder', orderedColumns)
    
    def updateMasterOrderFromVisualOrder(self):
        """Update master column order based on current visual order in the table."""
        # Get current visual order of visible columns
        header = self.tableWidget.horizontalHeader()
        orderedColumns = []
        for visual_idx in range(header.count()):
            logical_idx = header.logicalIndex(visual_idx)
            if logical_idx < len(self.visible_columns):
                orderedColumns.append(self.visible_columns[logical_idx])
        
        # Build new master order: start with visible columns in their visual order,
        # then insert hidden columns at their appropriate positions
        hidden_columns = [col for col in self.master_column_order if col not in orderedColumns]
        new_master_order = orderedColumns.copy()
        
        # Insert each hidden column right before the next visible column that comes after it
        for hidden_col in hidden_columns:
            # Find where in the OLD master order this hidden column was
            old_hidden_idx = self.master_column_order.index(hidden_col)
            
            # Find the first visible column that came after it in the old master order
            insert_before = None
            for i in range(old_hidden_idx + 1, len(self.master_column_order)):
                if self.master_column_order[i] in new_master_order:
                    insert_before = self.master_column_order[i]
                    break
            
            if insert_before:
                # Insert hidden column before this visible column
                insert_pos = new_master_order.index(insert_before)
                new_master_order.insert(insert_pos, hidden_col)
            else:
                # No visible column after it, append at end
                new_master_order.append(hidden_col)
        
        self.master_column_order = new_master_order
    
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
                                       f"alternate-background-color: {self.bgColorD};"
                                       f"border-radius: 0px;")
        self.tableWidget.setAlternatingRowColors(True)
        self.tableWidget.setShowGrid(False)
        
        # Set row height based on cover visibility
        if SimilarMovieColumns.COVER in self.visible_columns:
            # Use cover scale slider value
            cover_scale = self.coverScaleSlider.value()
            row_height = cover_scale + 10
            self.tableWidget.verticalHeader().setDefaultSectionSize(row_height)
        else:
            row_height = self.parent.rowHeightWithoutCover
            self.tableWidget.verticalHeader().setDefaultSectionSize(row_height)
        
        # Set vertical scroll to move one row per wheel click
        self.tableWidget.verticalScrollBar().setSingleStep(row_height)
        
        # Use uniform row heights to prevent auto-resizing
        self.tableWidget.verticalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Fixed)
        self.tableWidget.verticalHeader().setMinimumSectionSize(10)
        
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
        
        # Restore column visual order from settings (by column names)
        settings = QtCore.QSettings('SMDB', 'SimilarMovies')
        savedOrder = settings.value('columnOrder', None)
        if savedOrder and isinstance(savedOrder, list):
            # Reorder visible_columns to match saved order (for columns that still exist)
            new_order = []
            for col_name in savedOrder:
                if col_name in self.visible_columns:
                    new_order.append(col_name)
            # Add any new columns that weren't in the saved order
            for col_name in self.visible_columns:
                if col_name not in new_order:
                    new_order.append(col_name)
            # Only apply if we have a meaningful reorder
            if len(new_order) == len(self.visible_columns):
                self.visible_columns = new_order
                # Rebuild the table with new order
                self.tableWidget.setHorizontalHeaderLabels(self.visible_columns)
                # Reset column widths after reordering
                for idx, col_name in enumerate(self.visible_columns):
                    width = self.column_widths.get(col_name, SimilarMovieColumns.DEFAULT_WIDTHS.get(col_name, 100))
                    self.tableWidget.setColumnWidth(idx, width)
    
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
            # Add column - restore it to its position based on master column order
            target_index = 0
            for master_col in self.master_column_order:
                if master_col == col_name:
                    break
                if master_col in self.visible_columns:
                    target_index += 1
            self.visible_columns.insert(target_index, col_name)
        elif not checked and col_name in self.visible_columns:
            # Before removing, update master order to capture current visual positions
            self.updateMasterOrderFromVisualOrder()
            self.visible_columns.remove(col_name)
        
        # Adjust row height based on cover visibility
        if col_name == SimilarMovieColumns.COVER:
            if checked:
                # Cover is now visible - use tall rows
                self.tableWidget.verticalHeader().setDefaultSectionSize(self.parent.rowHeightWithCover)
            else:
                # Cover is now hidden - use short rows
                self.tableWidget.verticalHeader().setDefaultSectionSize(self.parent.rowHeightWithoutCover)
            # Force rows to update
            self.tableWidget.verticalHeader().resetDefaultSectionSize()
            if checked:
                self.tableWidget.verticalHeader().setDefaultSectionSize(self.parent.rowHeightWithCover)
            else:
                self.tableWidget.verticalHeader().setDefaultSectionSize(self.parent.rowHeightWithoutCover)
        
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
                        # Scale based on slider value
                        scale_size = self.coverScaleSlider.value()
                        scaled_pm = pm.scaled(scale_size, scale_size, 
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
