from PyQt5 import QtWidgets, QtCore, QtGui
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.pyplot as plt
from collections import Counter, defaultdict
import os
import ujson
import re


class StatisticsWidget(QtWidgets.QWidget):
    """Widget displaying collection statistics with charts and metrics."""
    
    def __init__(self, parent=None, bgColorA='rgb(50, 50, 50)', bgColorB='rgb(25, 25, 25)', 
                 bgColorC='rgb(0, 0, 0)', fgColor='rgb(255, 255, 255)'):
        super().__init__(parent)
        
        self.parent = parent
        self.bgColorA = bgColorA
        self.bgColorB = bgColorB
        self.bgColorC = bgColorC
        self.fgColor = fgColor
        
        # Minimum films for rating charts
        self.minFilmsDirectors = 10
        self.minFilmsActors = 10
        self.minFilmsWriters = 10
        self.minFilmsProducers = 10
        self.minFilmsComposers = 10
        
        # Number of top genres to show per decade
        self.topGenreCount = 10
        
        # Set matplotlib style for dark theme
        plt.style.use('dark_background')
        
        self.initUI()
        
    def initUI(self):
        """Initialize the user interface."""
        # Main layout
        mainLayout = QtWidgets.QVBoxLayout()
        mainLayout.setContentsMargins(5, 5, 5, 5)
        mainLayout.setSpacing(5)
        
        # Header
        headerLabel = QtWidgets.QLabel("Collection Statistics")
        headerLabel.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {self.fgColor}; padding: 5px;")
        headerLabel.setAlignment(QtCore.Qt.AlignCenter)
        mainLayout.addWidget(headerLabel)
        
        # Scroll area for content
        scrollArea = QtWidgets.QScrollArea()
        scrollArea.setWidgetResizable(True)
        scrollArea.setStyleSheet(f"background: {self.bgColorB}; border: none;")
        
        # Content widget
        contentWidget = QtWidgets.QWidget()
        contentLayout = QtWidgets.QVBoxLayout()
        contentLayout.setContentsMargins(5, 5, 5, 5)
        contentLayout.setSpacing(10)
        
        # Top metrics panel
        self.metricsPanel = self.createMetricsPanel()
        contentLayout.addWidget(self.metricsPanel)
        
        # Charts container
        chartsLayout = QtWidgets.QVBoxLayout()
        chartsLayout.setSpacing(10)
        
        # Movies per decade chart
        self.decadeCanvas = self.createChartCanvas()
        chartsLayout.addWidget(self.createChartGroup("Movies per Decade", self.decadeCanvas))
        
        # Genre distribution by decade chart
        self.genreByDecadeCanvas = self.createChartCanvas(height=8)
        genreByDecadeGroup = self.createChartGroupWithSpinner(
            "Top Genres by Decade",
            self.genreByDecadeCanvas,
            self.topGenreCount,
            lambda val: self.onTopGenreCountChanged(val),
            spinner_label="Top N:"
        )
        chartsLayout.addWidget(genreByDecadeGroup)

        # MPAA rating distribution by decade chart
        self.mpaaByDecadeCanvas = self.createChartCanvas(height=8)
        chartsLayout.addWidget(self.createChartGroup("MPAA Rating Distribution by Decade", self.mpaaByDecadeCanvas))
        
        # Genre distribution chart
        self.genreCanvas = self.createChartCanvas()
        chartsLayout.addWidget(self.createChartGroup("Genre Distribution", self.genreCanvas))
        
        # Rating distribution chart
        self.ratingCanvas = self.createChartCanvas()
        chartsLayout.addWidget(self.createChartGroup("Rating Distribution", self.ratingCanvas))
        
        # Top directors chart
        self.directorsCanvas = self.createChartCanvas()
        chartsLayout.addWidget(self.createChartGroup("Top 10 Directors (by Volume)", self.directorsCanvas))
        
        # Top actors chart
        self.actorsCanvas = self.createChartCanvas()
        chartsLayout.addWidget(self.createChartGroup("Top 10 Actors (by Volume)", self.actorsCanvas))
        
        # Top writers chart
        self.writersCanvas = self.createChartCanvas()
        chartsLayout.addWidget(self.createChartGroup("Top 10 Writers (by Volume)", self.writersCanvas))
        
        # Top producers chart
        self.producersCanvas = self.createChartCanvas()
        chartsLayout.addWidget(self.createChartGroup("Top 10 Producers (by Volume)", self.producersCanvas))
        
        # Top composers chart
        self.composersCanvas = self.createChartCanvas()
        chartsLayout.addWidget(self.createChartGroup("Top 10 Composers (by Volume)", self.composersCanvas))
        
        # Top directors by rating chart
        self.directorsRatingCanvas = self.createChartCanvas()
        directorsRatingGroup = self.createChartGroupWithSpinner(
            "Top 10 Directors (by Avg Rating)",
            self.directorsRatingCanvas,
            self.minFilmsDirectors,
            lambda val: self.onMinFilmsDirectorsChanged(val)
        )
        chartsLayout.addWidget(directorsRatingGroup)
        
        # Top actors by rating chart
        self.actorsRatingCanvas = self.createChartCanvas()
        actorsRatingGroup = self.createChartGroupWithSpinner(
            "Top 10 Actors (by Avg Rating)",
            self.actorsRatingCanvas,
            self.minFilmsActors,
            lambda val: self.onMinFilmsActorsChanged(val)
        )
        chartsLayout.addWidget(actorsRatingGroup)
        
        # Top writers by rating chart
        self.writersRatingCanvas = self.createChartCanvas()
        writersRatingGroup = self.createChartGroupWithSpinner(
            "Top 10 Writers (by Avg Rating)",
            self.writersRatingCanvas,
            self.minFilmsWriters,
            lambda val: self.onMinFilmsWritersChanged(val)
        )
        chartsLayout.addWidget(writersRatingGroup)
        
        # Top producers by rating chart
        self.producersRatingCanvas = self.createChartCanvas()
        producersRatingGroup = self.createChartGroupWithSpinner(
            "Top 10 Producers (by Avg Rating)",
            self.producersRatingCanvas,
            self.minFilmsProducers,
            lambda val: self.onMinFilmsProducersChanged(val)
        )
        chartsLayout.addWidget(producersRatingGroup)
        
        # Top composers by rating chart
        self.composersRatingCanvas = self.createChartCanvas()
        composersRatingGroup = self.createChartGroupWithSpinner(
            "Top 10 Composers (by Avg Rating)",
            self.composersRatingCanvas,
            self.minFilmsComposers,
            lambda val: self.onMinFilmsComposersChanged(val)
        )
        chartsLayout.addWidget(composersRatingGroup)
        
        contentLayout.addLayout(chartsLayout)
        
        contentWidget.setLayout(contentLayout)
        scrollArea.setWidget(contentWidget)
        
        mainLayout.addWidget(scrollArea)
        
        self.setLayout(mainLayout)
        self.setStyleSheet(f"background: {self.bgColorB};")
        
    def createMetricsPanel(self):
        """Create the top metrics display panel."""
        panel = QtWidgets.QFrame()
        panel.setStyleSheet(f"""
            QFrame {{
                background: {self.bgColorC};
                border-radius: 10px;
                padding: 10px;
            }}
        """)
        
        layout = QtWidgets.QGridLayout()
        layout.setSpacing(15)
        
        # Metric labels (will be populated in refresh)
        self.totalMoviesLabel = self.createMetricLabel("0", "Total Movies")
        self.totalRuntimeLabel = self.createMetricLabel("0h 0m", "Total Runtime")
        self.avgRatingLabel = self.createMetricLabel("0.0", "Avg Rating")
        self.avgRuntimeLabel = self.createMetricLabel("0m", "Avg Runtime")
        self.uniqueDirectorsLabel = self.createMetricLabel("0", "Directors")
        self.uniqueActorsLabel = self.createMetricLabel("0", "Actors")
        self.uniqueWritersLabel = self.createMetricLabel("0", "Writers")
        self.uniqueProducersLabel = self.createMetricLabel("0", "Producers")
        self.uniqueComposersLabel = self.createMetricLabel("0", "Composers")
        
        # Add to grid
        layout.addWidget(self.totalMoviesLabel, 0, 0)
        layout.addWidget(self.totalRuntimeLabel, 0, 1)
        layout.addWidget(self.avgRatingLabel, 0, 2)
        layout.addWidget(self.avgRuntimeLabel, 1, 0)
        layout.addWidget(self.uniqueDirectorsLabel, 1, 1)
        layout.addWidget(self.uniqueActorsLabel, 1, 2)
        layout.addWidget(self.uniqueWritersLabel, 2, 0)
        layout.addWidget(self.uniqueProducersLabel, 2, 1)
        layout.addWidget(self.uniqueComposersLabel, 2, 2)
        
        panel.setLayout(layout)
        return panel
        
    def createMetricLabel(self, value, label):
        """Create a metric display widget."""
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(5)
        
        valueLabel = QtWidgets.QLabel(value)
        valueLabel.setStyleSheet(f"font-size: 24px; font-weight: bold; color: {self.fgColor};")
        valueLabel.setAlignment(QtCore.Qt.AlignCenter)
        
        textLabel = QtWidgets.QLabel(label)
        textLabel.setStyleSheet(f"font-size: 11px; color: #888; text-transform: uppercase;")
        textLabel.setAlignment(QtCore.Qt.AlignCenter)
        
        layout.addWidget(valueLabel)
        layout.addWidget(textLabel)
        
        widget.setLayout(layout)
        widget.valueLabel = valueLabel  # Store reference for updates
        return widget
        
    def createChartCanvas(self, height=4):
        """Create a matplotlib canvas for charts."""
        fig = Figure(figsize=(8, height), facecolor='#191919')
        canvas = FigureCanvas(fig)
        canvas.setMinimumHeight(int(height * 75))
        canvas.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        return canvas
        
    def createChartGroup(self, title, canvas):
        """Create a chart container with title."""
        group = QtWidgets.QGroupBox(title)
        group.setStyleSheet(f"""
            QGroupBox {{
                color: {self.fgColor};
                border: 1px solid #444;
                border-radius: 5px;
                margin-top: 10px;
                font-weight: bold;
                padding-top: 10px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top center;
                padding: 5px 10px;
            }}
        """)
        
        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(canvas)
        group.setLayout(layout)
        group.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        return group
        
    def createChartGroupWithSpinner(self, title, canvas, default_value, on_change_callback, spinner_label="Min Films:"):
        """Create a chart container with title and spinner control."""
        group = QtWidgets.QGroupBox()
        group.setStyleSheet(f"""
            QGroupBox {{
                color: {self.fgColor};
                border: 1px solid #444;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
            }}
        """)
        
        # Header with title and spinner
        headerWidget = QtWidgets.QWidget()
        headerLayout = QtWidgets.QHBoxLayout()
        headerLayout.setContentsMargins(10, 5, 10, 5)
        
        titleLabel = QtWidgets.QLabel(title)
        titleLabel.setStyleSheet(f"color: {self.fgColor}; font-weight: bold; border: none;")
        headerLayout.addWidget(titleLabel)
        
        headerLayout.addStretch()
        
        minLabel = QtWidgets.QLabel(spinner_label)
        minLabel.setStyleSheet(f"color: {self.fgColor}; border: none;")
        headerLayout.addWidget(minLabel)
        
        spinner = QtWidgets.QSpinBox()
        spinner.setMinimum(1)
        spinner.setMaximum(99999)
        spinner.setValue(default_value)
        spinner.setStyleSheet(f"""
            QSpinBox {{
                background: {self.bgColorC};
                color: {self.fgColor};
                border: 1px solid #666;
                border-radius: 3px;
                padding: 3px;
                min-width: 50px;
            }}
            QSpinBox::up-button, QSpinBox::down-button {{
                background: {self.bgColorA};
                border: 1px solid #666;
            }}
            QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
                background: {self.fgColor};
            }}
        """)
        spinner.valueChanged.connect(on_change_callback)
        headerLayout.addWidget(spinner)
        
        headerWidget.setLayout(headerLayout)
        
        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(headerWidget)
        layout.addWidget(canvas)
        group.setLayout(layout)
        group.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        return group
        
    def onMinFilmsDirectorsChanged(self, value):
        """Handle change in minimum films for directors."""
        self.minFilmsDirectors = value
        # Replot only the directors rating chart if we have data
        if hasattr(self, '_cached_movies_data') and self._cached_movies_data:
            self.plotTopDirectorsByRating(self._cached_movies_data)
            
    def onMinFilmsActorsChanged(self, value):
        """Handle change in minimum films for actors."""
        self.minFilmsActors = value
        # Replot only the actors rating chart if we have data
        if hasattr(self, '_cached_movies_data') and self._cached_movies_data:
            self.plotTopActorsByRating(self._cached_movies_data)
            
    def onTopGenreCountChanged(self, value):
        """Handle change in number of top genres to show."""
        self.topGenreCount = value
        # Replot only the genre by decade chart if we have data
        if hasattr(self, '_cached_movies_data') and self._cached_movies_data:
            self.plotGenreByDecade(self._cached_movies_data)
            
    def onMinFilmsWritersChanged(self, value):
        """Handle change in minimum films for writers."""
        self.minFilmsWriters = value
        if hasattr(self, '_cached_movies_data') and self._cached_movies_data:
            self.plotTopWritersByRating(self._cached_movies_data)
            
    def onMinFilmsProducersChanged(self, value):
        """Handle change in minimum films for producers."""
        self.minFilmsProducers = value
        if hasattr(self, '_cached_movies_data') and self._cached_movies_data:
            self.plotTopProducersByRating(self._cached_movies_data)
            
    def onMinFilmsComposersChanged(self, value):
        """Handle change in minimum films for composers."""
        self.minFilmsComposers = value
        if hasattr(self, '_cached_movies_data') and self._cached_movies_data:
            self.plotTopComposersByRating(self._cached_movies_data)
        
    def refresh(self):
        """Refresh statistics from the movie data."""
        if not self.parent or not hasattr(self.parent, 'moviesSmdbData'):
            return
            
        smdb_data = self.parent.moviesSmdbData
        if not smdb_data or 'titles' not in smdb_data:
            return
        
        titles_data = smdb_data['titles']
        
        # Collect data - titles_data values are the movie dictionaries
        movies_data = list(titles_data.values())
                
        if not movies_data:
            return
            
        # Cache for spinner updates
        self._cached_movies_data = movies_data
            
        # Calculate statistics
        self.calculateMetrics(movies_data)
        self.plotDecadeDistribution(movies_data)
        self.plotGenreByDecade(movies_data)
        self.plotMpaaByDecade(movies_data)
        self.plotGenreDistribution(movies_data)
        self.plotRatingDistribution(movies_data)
        self.plotTopDirectors(movies_data)
        self.plotTopActors(movies_data)
        self.plotTopWriters(movies_data)
        self.plotTopProducers(movies_data)
        self.plotTopComposers(movies_data)
        self.plotTopDirectorsByRating(movies_data)
        self.plotTopActorsByRating(movies_data)
        self.plotTopWritersByRating(movies_data)
        self.plotTopProducersByRating(movies_data)
        self.plotTopComposersByRating(movies_data)
        
    def calculateMetrics(self, movies_data):
        """Calculate and display top-level metrics."""
        total_movies = len(movies_data)
        
        # Total runtime
        total_minutes = 0
        valid_runtimes = 0
        for movie in movies_data:
            runtime = movie.get('runtime')
            if runtime:
                try:
                    mins = int(str(runtime).split()[0]) if isinstance(runtime, str) else int(runtime)
                    total_minutes += mins
                    valid_runtimes += 1
                except (ValueError, IndexError):
                    pass
                    
        # Calculate years, days, hours, minutes
        total_hours = total_minutes // 60
        remaining_mins = total_minutes % 60
        total_days = total_hours // 24
        remaining_hours = total_hours % 24
        total_years = total_days // 365
        remaining_days = total_days % 365
        avg_runtime = total_minutes // valid_runtimes if valid_runtimes > 0 else 0
        
        # Average rating
        ratings = []
        for movie in movies_data:
            rating = movie.get('rating')
            if rating:
                try:
                    ratings.append(float(rating))
                except (ValueError, TypeError):
                    pass
                    
        avg_rating = sum(ratings) / len(ratings) if ratings else 0.0
        
        # Unique directors and actors
        all_directors = set()
        all_actors = set()
        all_writers = set()
        all_producers = set()
        all_composers = set()
        for movie in movies_data:
            directors = movie.get('directors', [])
            if isinstance(directors, list):
                all_directors.update(directors)
                
            actors = movie.get('cast', []) or movie.get('actors', [])
            if isinstance(actors, list):
                all_actors.update(actors)
                
            writers = movie.get('writers', [])
            if isinstance(writers, list):
                all_writers.update(writers)
                
            producers = movie.get('producers', [])
            if isinstance(producers, list):
                all_producers.update(producers)
                
            composers = movie.get('composers', [])
            if isinstance(composers, list):
                all_composers.update(composers)
                
        # Update labels
        self.totalMoviesLabel.valueLabel.setText(str(total_movies))
        # Show as Yy Dd Hh Mm
        runtime_str = f"{total_years}y {remaining_days}d {remaining_hours}h {remaining_mins}m"
        self.totalRuntimeLabel.valueLabel.setText(runtime_str)
        self.avgRatingLabel.valueLabel.setText(f"{avg_rating:.1f}")
        self.avgRuntimeLabel.valueLabel.setText(f"{avg_runtime}m")
        self.uniqueDirectorsLabel.valueLabel.setText(str(len(all_directors)))
        self.uniqueActorsLabel.valueLabel.setText(str(len(all_actors)))
        self.uniqueWritersLabel.valueLabel.setText(str(len(all_writers)))
        self.uniqueProducersLabel.valueLabel.setText(str(len(all_producers)))
        self.uniqueComposersLabel.valueLabel.setText(str(len(all_composers)))
        
    def plotDecadeDistribution(self, movies_data):
        """Plot movies per decade."""
        decades = defaultdict(int)
        for movie in movies_data:
            year = movie.get('year')
            if year:
                try:
                    year_int = int(year)
                    decade = (year_int // 10) * 10
                    decades[decade] += 1
                except (ValueError, TypeError):
                    pass
                    
        if not decades:
            return
            
        # Sort by decade
        sorted_decades = sorted(decades.items())
        labels = [f"{d}s" for d, _ in sorted_decades]
        values = [count for _, count in sorted_decades]
        
        # Plot
        fig = self.decadeCanvas.figure
        fig.clear()
        ax = fig.add_subplot(111)
        
        bars = ax.bar(labels, values, color='#1f77b4', edgecolor='white', linewidth=0.7)
        ax.set_xlabel('Decade', color='white')
        ax.set_ylabel('Number of Movies', color='white')
        ax.tick_params(colors='white')
        ax.spines['bottom'].set_color('white')
        ax.spines['left'].set_color('white')
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        
        # Add value labels on bars
        for bar in bars:
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., height,
                   f'{int(height)}',
                   ha='center', va='bottom', color='white', fontsize=9)
        
        fig.tight_layout()
        self.decadeCanvas.draw()
        
    def plotGenreByDecade(self, movies_data):
        """Plot top N genres per decade with color-coded stacked bars."""
        # Collect genre counts by decade
        decade_genres = defaultdict(lambda: Counter())
        for movie in movies_data:
            year = movie.get('year')
            genres = movie.get('genres', [])
            
            if not year:
                continue
                
            try:
                year_int = int(year)
                decade = (year_int // 10) * 10
            except (ValueError, TypeError):
                continue
            
            if isinstance(genres, list):
                for genre in genres:
                    if genre:
                        decade_genres[decade][genre] += 1
            elif isinstance(genres, str):
                for genre in [g.strip() for g in genres.split(',')]:
                    if genre:
                        decade_genres[decade][genre] += 1
        
        if not decade_genres:
            return
        
        # Sort decades
        sorted_decades = sorted(decade_genres.keys())
        labels = [f"{d}s" for d in sorted_decades]
        
        # Get top N genres for each decade
        n = self.topGenreCount
        genre_data = [[] for _ in range(n)]  # List of lists for each rank
        genre_names_data = [[] for _ in range(n)]
        
        for decade in sorted_decades:
            top_genres = decade_genres[decade].most_common(n)
            
            # Pad with zeros if fewer than n genres
            while len(top_genres) < n:
                top_genres.append(('', 0))
            
            for i in range(n):
                genre_names_data[i].append(top_genres[i][0] if top_genres[i][0] else '')
                genre_data[i].append(top_genres[i][1])
        
        # Plot stacked bar chart
        fig = self.genreByDecadeCanvas.figure
        fig.clear()
        ax = fig.add_subplot(111)
        
        x = range(len(labels))
        width = 0.6
        
        # Color palette for different ranks
        colors = ['#e74c3c', '#3498db', '#2ecc71', '#f39c12', '#9b59b6', '#1abc9c', '#e67e22', '#34495e', '#95a5a6', '#c0392b']
        
        # Create stacked bars dynamically
        bars = []
        bottoms = [0] * len(labels)
        
        for i in range(n):
            color = colors[i % len(colors)]
            bar = ax.bar(x, genre_data[i], width, bottom=bottoms, 
                        label=f'#{i+1} Genre', color=color, edgecolor='white', linewidth=0.7)
            bars.append(bar)
            
            # Update bottoms for next stack
            bottoms = [bottoms[j] + genre_data[i][j] for j in range(len(labels))]
        
        ax.set_xlabel('Decade', color='white')
        ax.set_ylabel('Number of Movies', color='white')
        ax.set_xticks(x)
        ax.set_xticklabels(labels)
        ax.tick_params(colors='white')
        ax.spines['bottom'].set_color('white')
        ax.spines['left'].set_color('white')
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        
        # Add genre labels on bars
        cumulative_bottoms = [[0] * len(labels) for _ in range(n)]
        for i in range(n):
            if i > 0:
                cumulative_bottoms[i] = [cumulative_bottoms[i-1][j] + genre_data[i-1][j] for j in range(len(labels))]
        
        for rank in range(n):
            for idx, bar in enumerate(bars[rank]):
                if genre_data[rank][idx] > 0:
                    height = bar.get_height()
                    if height > 20:  # Only show if tall enough
                        y_pos = cumulative_bottoms[rank][idx] + height/2.
                        ax.text(bar.get_x() + bar.get_width()/2., y_pos,
                               genre_names_data[rank][idx][:3],  # Abbreviated
                               ha='center', va='center', color='white', fontsize=8, fontweight='bold')
        
        # Legend
        ax.legend(facecolor='#191919', edgecolor='white', labelcolor='white', loc='upper left')
        
        # Add hover tooltips
        annot = ax.annotate("", xy=(0,0), xytext=(10,10), textcoords="offset points",
                           bbox=dict(boxstyle="round", fc="black", ec="white", alpha=0.9),
                           color="white", fontsize=10, visible=False)
        
        def on_hover(event):
            if event.inaxes == ax:
                vis = annot.get_visible()
                found = False
                
                # Check all bar ranks
                for rank in range(n):
                    for idx, bar in enumerate(bars[rank]):
                        cont, _ = bar.contains(event)
                        if cont and genre_data[rank][idx] > 0:
                            annot.xy = (event.xdata, event.ydata)
                            annot.set_text(f'{genre_names_data[rank][idx]}: {genre_data[rank][idx]} films')
                            annot.set_visible(True)
                            found = True
                            break
                    if found:
                        break
                
                if not found and vis:
                    annot.set_visible(False)
                
                fig.canvas.draw_idle()
        
        fig.canvas.mpl_connect('motion_notify_event', on_hover)
        
        fig.tight_layout()
        self.genreByDecadeCanvas.draw()
        
    def plotGenreDistribution(self, movies_data):
        """Plot genre distribution."""
        genre_counts = Counter()
        for movie in movies_data:
            genres = movie.get('genres', [])
            if isinstance(genres, list):
                genre_counts.update(genres)
            elif isinstance(genres, str):
                genre_counts.update([g.strip() for g in genres.split(',')])
                
        if not genre_counts:
            return
            
        # Top 10 genres
        top_genres = genre_counts.most_common(10)
        labels = [genre for genre, _ in top_genres]
        values = [count for _, count in top_genres]
        
        # Plot
        fig = self.genreCanvas.figure
        fig.clear()
        ax = fig.add_subplot(111)
        
        bars = ax.barh(labels, values, color='#ff7f0e', edgecolor='white', linewidth=0.7)
        ax.set_xlabel('Number of Movies', color='white')
        ax.tick_params(colors='white')
        ax.spines['bottom'].set_color('white')
        ax.spines['left'].set_color('white')
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.invert_yaxis()  # Highest at top
        
        # Add value labels
        for i, bar in enumerate(bars):
            width = bar.get_width()
            ax.text(width, bar.get_y() + bar.get_height()/2.,
                   f' {int(width)}',
                   ha='left', va='center', color='white', fontsize=9)
        
        fig.tight_layout()
        self.genreCanvas.draw()
        
    def plotRatingDistribution(self, movies_data):
        """Plot rating distribution histogram."""
        ratings = []
        for movie in movies_data:
            rating = movie.get('rating')
            if rating:
                try:
                    ratings.append(float(rating))
                except (ValueError, TypeError):
                    pass
                    
        if not ratings:
            return
            
        # Plot
        fig = self.ratingCanvas.figure
        fig.clear()
        ax = fig.add_subplot(111)
        
        n, bins, patches = ax.hist(ratings, bins=20, color='#2ca02c', edgecolor='white', linewidth=0.7)
        ax.set_xlabel('Rating', color='white')
        ax.set_ylabel('Number of Movies', color='white')
        ax.tick_params(colors='white')
        ax.spines['bottom'].set_color('white')
        ax.spines['left'].set_color('white')
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.set_xlim(0, 10)
        
        # Add mean line
        mean_rating = sum(ratings) / len(ratings)
        ax.axvline(mean_rating, color='red', linestyle='--', linewidth=2, label=f'Mean: {mean_rating:.1f}')
        ax.legend(facecolor='#191919', edgecolor='white', labelcolor='white')
        
        fig.tight_layout()
        self.ratingCanvas.draw()
        
    def plotTopDirectors(self, movies_data):
        """Plot top 10 directors by movie count."""
        director_counts = Counter()
        for movie in movies_data:
            directors = movie.get('directors', [])
            if isinstance(directors, list):
                director_counts.update(directors)
            elif isinstance(directors, str):
                director_counts.update([d.strip() for d in directors.split(',')])
                
        if not director_counts:
            return
            
        # Top 10
        top_directors = director_counts.most_common(10)
        labels = [director for director, _ in top_directors]
        values = [count for _, count in top_directors]
        
        # Plot
        fig = self.directorsCanvas.figure
        fig.clear()
        ax = fig.add_subplot(111)
        
        bars = ax.barh(labels, values, color='#d62728', edgecolor='white', linewidth=0.7)
        ax.set_xlabel('Number of Movies', color='white')
        ax.tick_params(colors='white')
        ax.spines['bottom'].set_color('white')
        ax.spines['left'].set_color('white')
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.invert_yaxis()
        
        # Add value labels
        for i, bar in enumerate(bars):
            width = bar.get_width()
            ax.text(width, bar.get_y() + bar.get_height()/2.,
                   f' {int(width)}',
                   ha='left', va='center', color='white', fontsize=9)
        
        fig.tight_layout()
        self.directorsCanvas.draw()
        
    def plotTopDirectorsByRating(self, movies_data):
        """Plot top 10 directors by average rating."""
        # Calculate average rating per director (min N movies)
        director_ratings = defaultdict(list)
        for movie in movies_data:
            directors = movie.get('directors', [])
            rating = movie.get('rating')
            if not rating:
                continue
            try:
                rating_val = float(rating)
            except (ValueError, TypeError):
                continue
                
            if isinstance(directors, list):
                for director in directors:
                    if director:
                        director_ratings[director].append(rating_val)
            elif isinstance(directors, str):
                for director in [d.strip() for d in directors.split(',')]:
                    if director:
                        director_ratings[director].append(rating_val)
        
        # Calculate averages for directors with at least N movies
        director_avgs = []
        for director, ratings in director_ratings.items():
            if len(ratings) >= self.minFilmsDirectors:
                avg_rating = sum(ratings) / len(ratings)
                director_avgs.append((director, avg_rating, len(ratings)))
        
        if not director_avgs:
            return
        
        # Sort by average rating and take top 10
        director_avgs.sort(key=lambda x: x[1], reverse=True)
        top_directors = director_avgs[:10]
        
        labels = [f"{director} ({count})" for director, _, count in top_directors]
        values = [avg_rating for _, avg_rating, _ in top_directors]
        
        # Plot
        fig = self.directorsRatingCanvas.figure
        fig.clear()
        ax = fig.add_subplot(111)
        
        bars = ax.barh(labels, values, color='#ff6b6b', edgecolor='white', linewidth=0.7)
        ax.set_xlabel('Average Rating', color='white')
        ax.tick_params(colors='white')
        ax.spines['bottom'].set_color('white')
        ax.spines['left'].set_color('white')
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.invert_yaxis()
        ax.set_xlim(0, 10)
        
        # Add value labels
        for i, bar in enumerate(bars):
            width = bar.get_width()
            ax.text(width, bar.get_y() + bar.get_height()/2.,
                   f' {width:.1f}',
                   ha='left', va='center', color='white', fontsize=9)
        
        fig.tight_layout()
        self.directorsRatingCanvas.draw()
        
    def plotTopActors(self, movies_data):
        """Plot top 10 actors by movie count."""
        actor_counts = Counter()
        for movie in movies_data:
            actors = movie.get('cast', []) or movie.get('actors', [])
            if isinstance(actors, list):
                actor_counts.update(actors)
            elif isinstance(actors, str):
                actor_counts.update([a.strip() for a in actors.split(',')])
                
        if not actor_counts:
            return
            
        # Top 10
        top_actors = actor_counts.most_common(10)
        labels = [actor for actor, _ in top_actors]
        values = [count for _, count in top_actors]
        
        # Plot
        fig = self.actorsCanvas.figure
        fig.clear()
        ax = fig.add_subplot(111)
        
        bars = ax.barh(labels, values, color='#9467bd', edgecolor='white', linewidth=0.7)
        ax.set_xlabel('Number of Movies', color='white')
        ax.tick_params(colors='white')
        ax.spines['bottom'].set_color('white')
        ax.spines['left'].set_color('white')
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.invert_yaxis()
        
        # Add value labels
        for i, bar in enumerate(bars):
            width = bar.get_width()
            ax.text(width, bar.get_y() + bar.get_height()/2.,
                   f' {int(width)}',
                   ha='left', va='center', color='white', fontsize=9)
        
        fig.tight_layout()
        self.actorsCanvas.draw()
        
    def plotTopWriters(self, movies_data):
        """Plot top 10 writers by movie count."""
        writer_counts = Counter()
        for movie in movies_data:
            writers = movie.get('writers', [])
            if isinstance(writers, list):
                writer_counts.update(writers)
            elif isinstance(writers, str):
                writer_counts.update([w.strip() for w in writers.split(',')])
                
        if not writer_counts:
            return
            
        # Top 10
        top_writers = writer_counts.most_common(10)
        labels = [writer for writer, _ in top_writers]
        values = [count for _, count in top_writers]
        
        # Plot
        fig = self.writersCanvas.figure
        fig.clear()
        ax = fig.add_subplot(111)
        
        bars = ax.barh(labels, values, color='#e67e22', edgecolor='white', linewidth=0.7)
        ax.set_xlabel('Number of Movies', color='white')
        ax.tick_params(colors='white')
        ax.spines['bottom'].set_color('white')
        ax.spines['left'].set_color('white')
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.invert_yaxis()
        
        # Add value labels
        for i, bar in enumerate(bars):
            width = bar.get_width()
            ax.text(width, bar.get_y() + bar.get_height()/2.,
                   f' {int(width)}',
                   ha='left', va='center', color='white', fontsize=9)
        
        fig.tight_layout()
        self.writersCanvas.draw()
        
    def plotTopProducers(self, movies_data):
        """Plot top 10 producers by movie count."""
        producer_counts = Counter()
        for movie in movies_data:
            producers = movie.get('producers', [])
            if isinstance(producers, list):
                producer_counts.update(producers)
            elif isinstance(producers, str):
                producer_counts.update([p.strip() for p in producers.split(',')])
                
        if not producer_counts:
            return
            
        # Top 10
        top_producers = producer_counts.most_common(10)
        labels = [producer for producer, _ in top_producers]
        values = [count for _, count in top_producers]
        
        # Plot
        fig = self.producersCanvas.figure
        fig.clear()
        ax = fig.add_subplot(111)
        
        bars = ax.barh(labels, values, color='#16a085', edgecolor='white', linewidth=0.7)
        ax.set_xlabel('Number of Movies', color='white')
        ax.tick_params(colors='white')
        ax.spines['bottom'].set_color('white')
        ax.spines['left'].set_color('white')
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.invert_yaxis()
        
        # Add value labels
        for i, bar in enumerate(bars):
            width = bar.get_width()
            ax.text(width, bar.get_y() + bar.get_height()/2.,
                   f' {int(width)}',
                   ha='left', va='center', color='white', fontsize=9)
        
        fig.tight_layout()
        self.producersCanvas.draw()
        
    def plotTopComposers(self, movies_data):
        """Plot top 10 composers by movie count."""
        composer_counts = Counter()
        for movie in movies_data:
            composers = movie.get('composers', [])
            if isinstance(composers, list):
                composer_counts.update(composers)
            elif isinstance(composers, str):
                composer_counts.update([c.strip() for c in composers.split(',')])
                
        if not composer_counts:
            return
            
        # Top 10
        top_composers = composer_counts.most_common(10)
        labels = [composer for composer, _ in top_composers]
        values = [count for _, count in top_composers]
        
        # Plot
        fig = self.composersCanvas.figure
        fig.clear()
        ax = fig.add_subplot(111)
        
        bars = ax.barh(labels, values, color='#8e44ad', edgecolor='white', linewidth=0.7)
        ax.set_xlabel('Number of Movies', color='white')
        ax.tick_params(colors='white')
        ax.spines['bottom'].set_color('white')
        ax.spines['left'].set_color('white')
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.invert_yaxis()
        
        # Add value labels
        for i, bar in enumerate(bars):
            width = bar.get_width()
            ax.text(width, bar.get_y() + bar.get_height()/2.,
                   f' {int(width)}',
                   ha='left', va='center', color='white', fontsize=9)
        
        fig.tight_layout()
        self.composersCanvas.draw()
        
    def plotTopActorsByRating(self, movies_data):
        """Plot top 10 actors by average rating."""
        # Calculate average rating per actor (min N movies)
        actor_ratings = defaultdict(list)
        for movie in movies_data:
            actors = movie.get('cast', []) or movie.get('actors', [])
            rating = movie.get('rating')
            if not rating:
                continue
            try:
                rating_val = float(rating)
            except (ValueError, TypeError):
                continue
                
            if isinstance(actors, list):
                for actor in actors:
                    if actor:
                        actor_ratings[actor].append(rating_val)
            elif isinstance(actors, str):
                for actor in [a.strip() for a in actors.split(',')]:
                    if actor:
                        actor_ratings[actor].append(rating_val)
        
        # Calculate averages for actors with at least N movies
        actor_avgs = []
        for actor, ratings in actor_ratings.items():
            if len(ratings) >= self.minFilmsActors:
                avg_rating = sum(ratings) / len(ratings)
                actor_avgs.append((actor, avg_rating, len(ratings)))
        
        if not actor_avgs:
            return
        
        # Sort by average rating and take top 10
        actor_avgs.sort(key=lambda x: x[1], reverse=True)
        top_actors = actor_avgs[:10]
        
        labels = [f"{actor} ({count})" for actor, _, count in top_actors]
        values = [avg_rating for _, avg_rating, _ in top_actors]
        
        # Plot
        fig = self.actorsRatingCanvas.figure
        fig.clear()
        ax = fig.add_subplot(111)
        
        bars = ax.barh(labels, values, color='#4ecdc4', edgecolor='white', linewidth=0.7)
        ax.set_xlabel('Average Rating', color='white')
        ax.tick_params(colors='white')
        ax.spines['bottom'].set_color('white')
        ax.spines['left'].set_color('white')
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.invert_yaxis()
        ax.set_xlim(0, 10)
        
        # Add value labels
        for i, bar in enumerate(bars):
            width = bar.get_width()
            ax.text(width, bar.get_y() + bar.get_height()/2.,
                   f' {width:.1f}',
                   ha='left', va='center', color='white', fontsize=9)
        
        fig.tight_layout()
        self.actorsRatingCanvas.draw()
        
    def plotTopWritersByRating(self, movies_data):
        """Plot top 10 writers by average rating."""
        writer_ratings = defaultdict(list)
        for movie in movies_data:
            writers = movie.get('writers', [])
            rating = movie.get('rating')
            if not rating:
                continue
            try:
                rating_val = float(rating)
            except (ValueError, TypeError):
                continue
                
            if isinstance(writers, list):
                for writer in writers:
                    if writer:
                        writer_ratings[writer].append(rating_val)
            elif isinstance(writers, str):
                for writer in [w.strip() for w in writers.split(',')]:
                    if writer:
                        writer_ratings[writer].append(rating_val)
        
        writer_avgs = []
        for writer, ratings in writer_ratings.items():
            if len(ratings) >= self.minFilmsWriters:
                avg_rating = sum(ratings) / len(ratings)
                writer_avgs.append((writer, avg_rating, len(ratings)))
        
        if not writer_avgs:
            return
        
        writer_avgs.sort(key=lambda x: x[1], reverse=True)
        top_writers = writer_avgs[:10]
        
        labels = [f"{writer} ({count})" for writer, _, count in top_writers]
        values = [avg_rating for _, avg_rating, _ in top_writers]
        
        fig = self.writersRatingCanvas.figure
        fig.clear()
        ax = fig.add_subplot(111)
        
        bars = ax.barh(labels, values, color='#f39c12', edgecolor='white', linewidth=0.7)
        ax.set_xlabel('Average Rating', color='white')
        ax.tick_params(colors='white')
        ax.spines['bottom'].set_color('white')
        ax.spines['left'].set_color('white')
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.invert_yaxis()
        ax.set_xlim(0, 10)
        
        for i, bar in enumerate(bars):
            width = bar.get_width()
            ax.text(width, bar.get_y() + bar.get_height()/2.,
                   f' {width:.1f}',
                   ha='left', va='center', color='white', fontsize=9)
        
        fig.tight_layout()
        self.writersRatingCanvas.draw()
        
    def plotTopProducersByRating(self, movies_data):
        """Plot top 10 producers by average rating."""
        producer_ratings = defaultdict(list)
        for movie in movies_data:
            producers = movie.get('producers', [])
            rating = movie.get('rating')
            if not rating:
                continue
            try:
                rating_val = float(rating)
            except (ValueError, TypeError):
                continue
                
            if isinstance(producers, list):
                for producer in producers:
                    if producer:
                        producer_ratings[producer].append(rating_val)
            elif isinstance(producers, str):
                for producer in [p.strip() for p in producers.split(',')]:
                    if producer:
                        producer_ratings[producer].append(rating_val)
        
        producer_avgs = []
        for producer, ratings in producer_ratings.items():
            if len(ratings) >= self.minFilmsProducers:
                avg_rating = sum(ratings) / len(ratings)
                producer_avgs.append((producer, avg_rating, len(ratings)))
        
        if not producer_avgs:
            return
        
        producer_avgs.sort(key=lambda x: x[1], reverse=True)
        top_producers = producer_avgs[:10]
        
        labels = [f"{producer} ({count})" for producer, _, count in top_producers]
        values = [avg_rating for _, avg_rating, _ in top_producers]
        
        fig = self.producersRatingCanvas.figure
        fig.clear()
        ax = fig.add_subplot(111)
        
        bars = ax.barh(labels, values, color='#27ae60', edgecolor='white', linewidth=0.7)
        ax.set_xlabel('Average Rating', color='white')
        ax.tick_params(colors='white')
        ax.spines['bottom'].set_color('white')
        ax.spines['left'].set_color('white')
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.invert_yaxis()
        ax.set_xlim(0, 10)
        
        for i, bar in enumerate(bars):
            width = bar.get_width()
            ax.text(width, bar.get_y() + bar.get_height()/2.,
                   f' {width:.1f}',
                   ha='left', va='center', color='white', fontsize=9)
        
        fig.tight_layout()
        self.producersRatingCanvas.draw()
        
    def plotTopComposersByRating(self, movies_data):
        """Plot top 10 composers by average rating."""
        composer_ratings = defaultdict(list)
        for movie in movies_data:
            composers = movie.get('composers', [])
            rating = movie.get('rating')
            if not rating:
                continue
            try:
                rating_val = float(rating)
            except (ValueError, TypeError):
                continue
                
            if isinstance(composers, list):
                for composer in composers:
                    if composer:
                        composer_ratings[composer].append(rating_val)
            elif isinstance(composers, str):
                for composer in [c.strip() for c in composers.split(',')]:
                    if composer:
                        composer_ratings[composer].append(rating_val)
        
        composer_avgs = []
        for composer, ratings in composer_ratings.items():
            if len(ratings) >= self.minFilmsComposers:
                avg_rating = sum(ratings) / len(ratings)
                composer_avgs.append((composer, avg_rating, len(ratings)))
        
        if not composer_avgs:
            return
        
        composer_avgs.sort(key=lambda x: x[1], reverse=True)
        top_composers = composer_avgs[:10]
        
        labels = [f"{composer} ({count})" for composer, _, count in top_composers]
        values = [avg_rating for _, avg_rating, _ in top_composers]
        
        fig = self.composersRatingCanvas.figure
        fig.clear()
        ax = fig.add_subplot(111)
        
        bars = ax.barh(labels, values, color='#9b59b6', edgecolor='white', linewidth=0.7)
        ax.set_xlabel('Average Rating', color='white')
        ax.tick_params(colors='white')
        ax.spines['bottom'].set_color('white')
        ax.spines['left'].set_color('white')
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.invert_yaxis()
        ax.set_xlim(0, 10)
        
        for i, bar in enumerate(bars):
            width = bar.get_width()
            ax.text(width, bar.get_y() + bar.get_height()/2.,
                   f' {width:.1f}',
                   ha='left', va='center', color='white', fontsize=9)
        
        fig.tight_layout()
        self.composersRatingCanvas.draw()
        
    def plotMpaaByDecade(self, movies_data):
        """Plot the distribution of MPAA ratings per decade as a stacked bar chart."""
        # Collect MPAA ratings by decade
        decade_ratings = defaultdict(lambda: Counter())
        for movie in movies_data:
            year = movie.get('year')
            mpaa = movie.get('mpaa rating')
            if not year or not mpaa:
                continue
            try:
                year_int = int(year)
                decade = (year_int // 10) * 10
            except (ValueError, TypeError):
                continue
            # Normalize MPAA rating (strip spaces, uppercase, only first part if comma)
            if isinstance(mpaa, str):
                mpaa = mpaa.split(',')[0].strip().upper()
                if mpaa in ('NOT RATED', 'UNRATED'):
                    mpaa = 'NR'
            decade_ratings[decade][mpaa] += 1

        if not decade_ratings:
            return

        # Sort decades and restrict to common ratings
        sorted_decades = sorted(decade_ratings.keys())
        common_ratings = ['G', 'PG', 'PG-13', 'R', 'NC-17', 'X', 'APPROVED', 'PASSED', 'NR']
        # Only include ratings present in data
        present_ratings = [r for r in common_ratings if any(r in c for c in decade_ratings.values())]
        sorted_ratings = present_ratings

        # Prepare data for stacked bar
        labels = [f"{d}s" for d in sorted_decades]
        data = {rating: [] for rating in sorted_ratings}
        for decade in sorted_decades:
            counter = decade_ratings[decade]
            for rating in sorted_ratings:
                data[rating].append(counter.get(rating, 0))

        # Plot
        fig = self.mpaaByDecadeCanvas.figure
        fig.clear()
        ax = fig.add_subplot(111)

        x = range(len(labels))
        width = 0.7
        bottoms = [0] * len(labels)
        color_map = {
            'G': '#2ecc71',
            'PG': '#3498db',
            'PG-13': '#f1c40f',
            'R': '#e74c3c',
            'NC-17': '#8e44ad',
            'NR': '#7f8c8d',
            'UNRATED': '#95a5a6',
            'X': '#d35400',
        }
        bars = []
        for rating in sorted_ratings:
            color = color_map.get(rating, None)
            bar = ax.bar(x, data[rating], width, bottom=bottoms, label=rating, color=color, edgecolor='white', linewidth=0.7)
            bars.append(bar)
            bottoms = [bottoms[i] + data[rating][i] for i in range(len(labels))]

        ax.set_xlabel('Decade', color='white')
        ax.set_ylabel('Number of Movies', color='white')
        ax.set_xticks(x)
        ax.set_xticklabels(labels)
        ax.tick_params(colors='white')
        ax.spines['bottom'].set_color('white')
        ax.spines['left'].set_color('white')
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)

        # Add legend
        ax.legend(title='MPAA', facecolor='#191919', edgecolor='white', labelcolor='white', title_fontsize=10)

        # Add value labels on top of each stack
        for i, decade in enumerate(sorted_decades):
            total = sum(data[rating][i] for rating in sorted_ratings)
            if total > 0:
                ax.text(i, total + 1, str(total), ha='center', va='bottom', color='white', fontsize=9)

        fig.tight_layout()
        self.mpaaByDecadeCanvas.draw()
