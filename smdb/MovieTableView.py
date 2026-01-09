from PyQt5 import QtWidgets, QtCore


class MovieTableView(QtWidgets.QTableView):
    wheelSpun = QtCore.pyqtSignal(int)

    def wheelEvent(self, event):
        if event.modifiers() & QtCore.Qt.ControlModifier:
            dy = event.angleDelta().y()
            self.wheelSpun.emit(1 if dy > 0 else (-1 if dy < 0 else 0))
            event.accept()
        else:
            # Custom wheel scrolling: one row per wheel click
            delta = event.angleDelta().y()
            
            if delta != 0:
                # Get the vertical scrollbar
                scrollBar = self.verticalScrollBar()
                
                # Calculate number of steps (typically 120 units per notch)
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
            
            # Get the index at this position
            index = self.indexAt(pos)
            if index.isValid():
                # Get the model and fetch movie data
                model = self.model()
                if model:
                    # Get source model (in case we're using a proxy)
                    source_model = model
                    source_index = index
                    if hasattr(model, 'mapToSource'):
                        source_index = model.mapToSource(index)
                        source_model = model.sourceModel()
                    
                    # Get movie data from the source model
                    if hasattr(source_model, 'getMovieData'):
                        movie_data = source_model.getMovieData(source_index.row())
                        if movie_data:
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
        actors = movie_data.get('actors', [])  # Main list uses 'actors' key
        if actors:
            if isinstance(actors, list):
                # Limit to first 5 actors
                actor_list = actors[:5]
                actor_str = ', '.join(actor_list)
                if len(actors) > 5:
                    actor_str += ', ...'
            else:
                actor_str = str(actors)
            parts.append(f"<b>Actors:</b> {actor_str}")
        
        # Rating
        rating = movie_data.get('rating', '')
        if rating:
            parts.append(f"<b>Rating:</b> {rating}")
        
        # Runtime
        runtime = movie_data.get('runtime', '')
        if runtime:
            parts.append(f"<b>Runtime:</b> {runtime} min")
        
        # Box Office
        box_office = movie_data.get('box office', '')
        if box_office:
            parts.append(f"<b>Box Office:</b> {box_office}")
        
        # Companies
        companies = movie_data.get('companies', [])
        if companies:
            if isinstance(companies, list):
                company_str = ', '.join(companies[:3])  # Limit to 3 companies
                if len(companies) > 3:
                    company_str += ', ...'
            else:
                company_str = str(companies)
            parts.append(f"<b>Companies:</b> {company_str}")
        
        # Plot
        plot = movie_data.get('plot', '') or movie_data.get('synopsis', '')
        if plot:
            # Handle both string and list formats
            if isinstance(plot, list):
                plot = ' '.join(str(p) for p in plot if p)
            else:
                plot = str(plot)
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
