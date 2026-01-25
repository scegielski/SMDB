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
        
        contentLayout.addLayout(chartsLayout)
        contentLayout.addStretch()
        
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
        
        # Add to grid
        layout.addWidget(self.totalMoviesLabel, 0, 0)
        layout.addWidget(self.totalRuntimeLabel, 0, 1)
        layout.addWidget(self.avgRatingLabel, 0, 2)
        layout.addWidget(self.avgRuntimeLabel, 1, 0)
        layout.addWidget(self.uniqueDirectorsLabel, 1, 1)
        layout.addWidget(self.uniqueActorsLabel, 1, 2)
        
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
        
    def createChartCanvas(self):
        """Create a matplotlib canvas for charts."""
        fig = Figure(figsize=(8, 4), facecolor='#191919')
        canvas = FigureCanvas(fig)
        canvas.setMinimumHeight(300)
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
        return group
        
    def createChartGroupWithSpinner(self, title, canvas, default_value, on_change_callback):
        """Create a chart container with title and minimum films spinner."""
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
        
        minLabel = QtWidgets.QLabel("Min Films:")
        minLabel.setStyleSheet(f"color: {self.fgColor}; border: none;")
        headerLayout.addWidget(minLabel)
        
        spinner = QtWidgets.QSpinBox()
        spinner.setMinimum(1)
        spinner.setMaximum(20)
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
        self.plotGenreDistribution(movies_data)
        self.plotRatingDistribution(movies_data)
        self.plotTopDirectors(movies_data)
        self.plotTopDirectorsByRating(movies_data)
        self.plotTopActors(movies_data)
        self.plotTopActorsByRating(movies_data)
        
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
                    
        total_hours = total_minutes // 60
        remaining_mins = total_minutes % 60
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
        for movie in movies_data:
            directors = movie.get('directors', [])
            if isinstance(directors, list):
                all_directors.update(directors)
                
            actors = movie.get('cast', []) or movie.get('actors', [])
            if isinstance(actors, list):
                all_actors.update(actors)
                
        # Update labels
        self.totalMoviesLabel.valueLabel.setText(str(total_movies))
        self.totalRuntimeLabel.valueLabel.setText(f"{total_hours}h {remaining_mins}m")
        self.avgRatingLabel.valueLabel.setText(f"{avg_rating:.1f}")
        self.avgRuntimeLabel.valueLabel.setText(f"{avg_runtime}m")
        self.uniqueDirectorsLabel.valueLabel.setText(str(len(all_directors)))
        self.uniqueActorsLabel.valueLabel.setText(str(len(all_actors)))
        
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
