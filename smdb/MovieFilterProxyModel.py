from PyQt5 import QtCore
from .MoviesTableModel import Columns


class MovieFilterProxyModel(QtCore.QSortFilterProxyModel):
    """
    Custom proxy model that handles filtering movies by multiple criteria.
    This replaces the manual row hiding approach with proper proxy-based filtering.
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Filter criteria storage
        self.filter_movie_list = []  # List of (title, year) tuples to show
        self.filter_mode = 'none'  # 'none', 'include', or 'exclude'
        self._filter_set = set()
        self._filter_set_dirty = True
        
        # Enable dynamic sorting/filtering
        self.setDynamicSortFilter(False)
        
    def setMovieListFilter(self, movie_list, mode='include'):
        """
        Set a list of movies to filter by.
        
        Args:
            movie_list: List of (title, year) tuples
            mode: 'include' to show only these movies, 'exclude' to hide these movies, 
                  'none' to show all movies
        """
        self.filter_movie_list = movie_list if movie_list else []
        self.filter_mode = mode if movie_list else 'none'
        self._filter_set_dirty = True
        self.invalidateFilter()
    
    def clearMovieListFilter(self):
        """Clear the movie list filter, showing all movies."""
        self.filter_movie_list = []
        self.filter_mode = 'none'
        self._filter_set_dirty = True
        self.invalidateFilter()
    
    def filterAcceptsRow(self, source_row, source_parent):
        """
        Determine if a row should be shown based on filter criteria.
        
        This method is called by Qt for each row to determine visibility.
        """
        # First check the built-in filter (used for title search)
        if not super().filterAcceptsRow(source_row, source_parent):
            return False
        
        # If no movie list filter is active, accept all rows
        if self.filter_mode == 'none' or not self.filter_movie_list:
            return True
        
        # Get the source model
        model = self.sourceModel()
        if not model:
            return True
        
        # Get title and year from the source model
        try:
            title = model.getTitle(source_row)
            year = model.getYear(source_row)
            
            # Convert year to int for comparison (matching the format in moviesSmdbData)
            try:
                year_int = int(year) if year else 0
            except (ValueError, TypeError):
                year_int = 0
            
            # The filter list contains items from moviesSmdbData which may be lists [title, year]
            # Convert to tuples for hashing in the set
            movie_tuple = (title, year_int)
            
            # Use a set for faster lookup - convert lists to tuples when building set
            if not hasattr(self, '_filter_set') or self._filter_set_dirty:
                self._filter_set = set()
                for item in self.filter_movie_list:
                    if isinstance(item, (list, tuple)) and len(item) >= 2:
                        # Convert to tuple (title, year)
                        self._filter_set.add((item[0], item[1]))
                self._filter_set_dirty = False
            
            is_in_list = movie_tuple in self._filter_set
            
            # Return based on filter mode
            if self.filter_mode == 'include':
                return is_in_list
            elif self.filter_mode == 'exclude':
                return not is_in_list
            else:
                return True
                
        except Exception as e:
            # If there's any error accessing the data, don't filter out the row
            return True
