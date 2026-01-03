from pathlib import Path
import os
import re
import requests
import urllib.request
import ujson
from datetime import datetime
from pymediainfo import MediaInfo
from .utilities import *


class MovieData:
    """Encapsulate movie-data download and JSON writing logic.

    This class is intentionally thin and delegates UI/logging back to the
    MainWindow instance passed as `parent` so we don't duplicate UI code.
    """

    def __init__(self, parent):
        self.parent = parent
        
        # API keys for external services (will be loaded from settings or prompted)
        self.tmdbApiKey = None
        self.omdbApiKey = None
        
        # Cache for TMDB configuration (image base URLs)
        self._tmdb_config_cache = None
        
        # Reusable session for connection pooling
        self._session = requests.Session()
        # Set User-Agent for Wikipedia API compliance
        self._session.headers.update({
            'User-Agent': 'SMDB/1.0 (Movie Database Application; Python/requests)'
        })

    def _ensureApiKeys(self):
        """
        Ensure API keys are available. Load from settings or prompt the user.
        Returns True if keys are available, False if user canceled.
        """
        from PyQt5.QtWidgets import QInputDialog, QMessageBox
        
        settings = self.parent.settings
        
        # Try to load from settings if not already set
        if self.tmdbApiKey is None:
            self.tmdbApiKey = settings.value('tmdbApiKey', '', type=str)
            if not self.tmdbApiKey:
                self.tmdbApiKey = None
        
        if self.omdbApiKey is None:
            self.omdbApiKey = settings.value('omdbApiKey', '', type=str)
            if not self.omdbApiKey:
                self.omdbApiKey = None
        
        # Prompt for TMDB API key if missing
        if not self.tmdbApiKey:
            key, ok = QInputDialog.getText(
                self.parent,
                "TMDB API Key Required",
                "Please enter your TMDB API key:\n(Get one free at https://www.themoviedb.org/settings/api)",
                text=""
            )
            if ok and key:
                self.tmdbApiKey = key
                settings.setValue('tmdbApiKey', key)
            else:
                QMessageBox.warning(
                    self.parent,
                    "API Key Required",
                    "TMDB API key is required to download movie data."
                )
                return False
        
        # Prompt for OMDb API key if missing
        if not self.omdbApiKey:
            key, ok = QInputDialog.getText(
                self.parent,
                "OMDb API Key Required",
                "Please enter your OMDb API key:\n(Get one free at http://www.omdbapi.com/apikey.aspx)",
                text=""
            )
            if ok and key:
                self.omdbApiKey = key
                settings.setValue('omdbApiKey', key)
            else:
                QMessageBox.warning(
                    self.parent,
                    "API Key Required",
                    "OMDb API key is required for fallback movie data lookups."
                )
                return False
        
        return True

    def downloadMovieData(self, proxyIndex, force=False, imdbId=None, doJson=True, doCover=True):
        # Ensure API keys are available before proceeding
        if not self._ensureApiKeys():
            return None
        
        parent = self.parent
        sourceIndex = parent.moviesTableProxyModel.mapToSource(proxyIndex)
        sourceRow = sourceIndex.row()
        movieFolderName = parent.moviesTableModel.getFolderName(sourceRow)
        moviePath = parent.moviesTableModel.getPath(sourceRow)
        moviePath = parent.findMovie(moviePath, movieFolderName)
        if not moviePath:
            return
        jsonFile = os.path.join(moviePath, '%s.json' % movieFolderName)
        coverFile = os.path.join(moviePath, '%s.jpg' % movieFolderName)
        if not os.path.exists(coverFile):
            coverFilePng = os.path.join(moviePath, '%s.png' % movieFolderName)
            if os.path.exists(coverFilePng):
                coverFile = coverFilePng

        if force is True or not os.path.exists(jsonFile) or not os.path.exists(coverFile):

            m = re.match(r'(.*)\((.*)\)', movieFolderName)
            title = m.group(1)
            title = ' '.join(splitCamelCase(title))
            try:
                year = int(m.group(2))
            except Exception:
                year = None
            titleYear = f"{title} ({year})"

            if not imdbId:
                imdbId = self._resolveImdbId(title, year)
            if not imdbId:
                self._output(f"Could not resolve IMDb ID for \"{titleYear}\"")
                return ""

            # Try TMDB first
            movie = self._getMovieTmdb(title, year, imdbId)
            
            # Fall back to OMDb if TMDB fails
            if not movie:
                self._output(f"TMDB lookup failed, falling back to OMDb for \"{titleYear}\"")
                movie = self._getMovieOmdb(title, year, imdbId)

            if not movie: return ""

            if doJson:
                # Get movie file info and add to movie dict
                self._getMovieFileInfo(moviePath, movie)
                
                # Write JSON with size and movie info
                self._writeJson(movie, jsonFile)

            if doCover:
                movieCoverUrl = None
                coverDownloaded = False
                
                # Try OMDB first for cover
                omdb_data = self._getMovieOmdb(title, year, imdbId)
                if omdb_data and omdb_data.get('Poster') and omdb_data['Poster'] != 'N/A':
                    movieCoverUrl = omdb_data['Poster']
                    try:
                        urllib.request.urlretrieve(movieCoverUrl, coverFile)
                        coverDownloaded = True
                        self._output(f"Downloaded cover from OMDb for \"{titleYear}\"")
                    except Exception as e:
                        self._output(f"OMDb cover download failed: {e}")
                
                # Fallback to TMDB if OMDB failed
                if not coverDownloaded:
                    if 'PosterFullSize' in movie:
                        movieCoverUrl = movie['PosterFullSize']
                    elif 'Poster' in movie:
                        movieCoverUrl = movie['Poster']
                    
                    if movieCoverUrl:
                        try:
                            urllib.request.urlretrieve(movieCoverUrl, coverFile)
                            self._output(f"Downloaded cover from TMDB for \"{titleYear}\"")
                        except Exception as e:
                            self._output(f"TMDB cover download failed: {e}")
                    else:
                        self._output("Error: No cover image available")

            parent.moviesTableModel.setMovieDataWithJson(sourceRow,
                                                       jsonFile,
                                                       moviePath,
                                                       movieFolderName)

        return coverFile

    def _calculateFolderSize(self, moviePath):
        """Calculate the total size of a movie folder in MB.
        
        Args:
            moviePath: Path to the movie folder
            
        Returns:
            Formatted size string like '01234 Mb'
        """
        total_size = 0
        for dirpath, dirnames, filenames in os.walk(moviePath):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                if not os.path.islink(fp):
                    total_size += os.path.getsize(fp)
        return '%05d Mb' % (total_size / (2**20))
    
    def _getMovieFileInfo(self, moviePath, movie):
        """Extract video file metadata and folder size, adding them to the movie dict.
        
        Args:
            moviePath: Path to the movie folder
            movie: Movie dictionary to update with size and file info
        """
        # Calculate folder size
        folderSize = self._calculateFolderSize(moviePath)
        
        # Extract video file metadata
        width, height, channels = 0, 0, 0
        validExtentions = ['.mkv', '.mpg', '.mp4', '.avi', '.flv', '.wmv', '.m4v', '.divx', '.ogm']
        movieFiles = []
        
        for file in os.listdir(moviePath):
            extension = os.path.splitext(file)[1].lower()
            if extension in validExtentions:
                movieFiles.append(file)
        
        if len(movieFiles) > 0:
            movieFile = os.path.join(moviePath, movieFiles[0])
            info = MediaInfo.parse(movieFile)
            for track in info.tracks:
                if track.track_type == 'Video':
                    width = track.width
                    height = track.height
                elif track.track_type == 'Audio':
                    channels = track.channel_s
        
        # Add size and movie info to movie dict
        movie['size'] = folderSize
        movie['width'] = width
        movie['height'] = height
        movie['channels'] = channels

    def _output(self, *args, **kwargs):
        return self.parent.output(*args, **kwargs)
    
    def _normalizeImdbId(self, imdb_id):
        """Ensure IMDb ID has the 'tt' prefix.
        
        Args:
            imdb_id: IMDb ID with or without 'tt' prefix
            
        Returns:
            IMDb ID with 'tt' prefix, or None if input is None/empty
        """
        if not imdb_id:
            return None
        return imdb_id if imdb_id.startswith('tt') else f"tt{imdb_id}"
    
    def _getWikipediaPlot(self, title, year):
        """Fetch detailed plot from Wikipedia.
        
        Args:
            title: Movie title
            year: Movie year
            
        Returns:
            Detailed plot text from Wikipedia, or None if not found
        """
        try:
            # Try with year first for disambiguation
            search_titles = [
                f"{title} ({year} film)",
                f"{title} (film)",
                f"{title} {year}",
                title
            ] if year else [f"{title} (film)", title]
            
            for search_title in search_titles:
                try:
                    # Search for the page
                    search_params = {
                        'action': 'query',
                        'list': 'search',
                        'srsearch': search_title,
                        'format': 'json',
                        'srlimit': 5  # Get top 5 results
                    }
                    
                    search_response = self._session.get(
                        'https://en.wikipedia.org/w/api.php',
                        params=search_params,
                        timeout=10
                    )
                    
                    if search_response.status_code != 200:
                        self._output(f"Wikipedia search failed with status {search_response.status_code}")
                        continue
                    
                    search_data = search_response.json()
                    search_results = search_data.get('query', {}).get('search', [])
                    
                    if not search_results:
                        self._output(f"No Wikipedia results for '{search_title}'")
                        continue
                    
                    # Try each search result
                    for result in search_results:
                        page_title = result['title']
                        page_lower = page_title.lower()
                        
                        # Skip obviously non-film articles
                        skip_keywords = ['list of', 'category:', 'template:', 'festival', 'award', 'in film']
                        if any(keyword in page_lower for keyword in skip_keywords):
                            continue
                        
                        # Prioritize pages with exact title match or film-related terms
                        title_lower = title.lower()
                        is_exact_match = page_lower == title_lower
                        has_film_keyword = 'film' in page_lower or 'movie' in page_lower
                        has_year = year and str(year) in page_title
                        
                        # Skip if it's not an exact match and doesn't have film indicators
                        if not is_exact_match and not has_film_keyword and not has_year:
                            # Check if this is actually a person's page
                            if 'director' in page_lower or 'actor' in page_lower or 'actress' in page_lower:
                                continue
                        
                        self._output(f"Trying Wikipedia page: '{page_title}'")
                        
                        # Get the page content
                        parse_params = {
                            'action': 'parse',
                            'page': page_title,
                            'prop': 'wikitext',
                            'format': 'json'
                        }
                        
                        parse_response = self._session.get(
                            'https://en.wikipedia.org/w/api.php',
                            params=parse_params,
                            timeout=10
                        )
                        
                        if parse_response.status_code != 200:
                            continue
                        
                        parse_data = parse_response.json()
                        
                        if 'error' in parse_data:
                            continue
                        
                        wikitext = parse_data.get('parse', {}).get('wikitext', {}).get('*', '')
                        
                        if not wikitext:
                            continue
                        
                        # Check if this is actually a film article by looking for Infobox film
                        has_film_infobox = 'Infobox film' in wikitext or '{{Infobox Film' in wikitext
                        if not has_film_infobox:
                            # If exact title match, still try it
                            if not is_exact_match:
                                continue
                        
                        # If we have a year, verify it matches the infobox year
                        if year and has_film_infobox:
                            # Look for year in infobox (e.g., | released = {{Film date|1949|...)
                            year_match = re.search(
                                r'\|\s*(?:released|release[_ ]date)\s*=\s*.*?(\d{4})',
                                wikitext,
                                re.IGNORECASE
                            )
                            if year_match:
                                wiki_year = int(year_match.group(1))
                                # Allow 1 year difference for release date variations
                                if abs(wiki_year - int(year)) > 1:
                                    self._output(f"Skipping '{page_title}' - year mismatch (Wikipedia: {wiki_year}, expected: {year})")
                                    continue
                        
                        # Verify title similarity to avoid wrong movies with matching year
                        # Extract significant words from both titles (ignore common words)
                        def extract_significant_words(text):
                            """Extract significant words, ignoring common articles and prepositions"""
                            common_words = {'the', 'a', 'an', 'of', 'in', 'at', 'to', 'for', 'and', 'or', 
                                          'from', 'with', 'part', 'i', 'ii', 'iii', 'iv', 'v', 'film', 'movie'}
                            # Remove year, parentheses, and special chars, then split
                            cleaned = re.sub(r'[\(\)\[\]:,\-]', ' ', text.lower())
                            cleaned = re.sub(r'\b\d{4}\b', '', cleaned)  # Remove years
                            words = cleaned.split()
                            return {w for w in words if w and len(w) > 2 and w not in common_words}
                        
                        title_words = extract_significant_words(title)
                        page_words = extract_significant_words(page_title)
                        
                        if title_words and page_words:
                            # Calculate overlap - at least one significant word should match
                            common_words_count = len(title_words & page_words)
                            if common_words_count == 0 and not is_exact_match:
                                self._output(f"Skipping '{page_title}' - no title words match '{title}'")
                                continue
                        
                        # Extract the Plot section (try multiple variations)
                        plot_match = re.search(
                            r'==\s*(Plot|Synopsis|Story)\s*==\s*\n(.*?)(?=\n==|$)',
                            wikitext,
                            re.DOTALL | re.IGNORECASE
                        )
                        
                        if plot_match:
                            plot_text = plot_match.group(2).strip()
                            
                            # Clean up wiki markup
                            # Remove references like {{cite}} or <ref>...</ref>
                            plot_text = re.sub(r'<ref[^>]*>.*?</ref>', '', plot_text, flags=re.DOTALL)
                            plot_text = re.sub(r'<ref[^>]*/?>', '', plot_text)
                            plot_text = re.sub(r'{{[^}]+}}', '', plot_text)
                            
                            # Remove wiki links but keep the display text
                            plot_text = re.sub(r'\[\[(?:[^|\]]+\|)?([^\]]+)\]\]', r'\1', plot_text)
                            
                            # Remove bold/italic markup
                            plot_text = re.sub(r"'{2,}", '', plot_text)
                            
                            # Remove HTML comments
                            plot_text = re.sub(r'<!--.*?-->', '', plot_text, flags=re.DOTALL)
                            
                            # Clean up whitespace
                            plot_text = re.sub(r'\n\n+', '\n\n', plot_text)
                            plot_text = plot_text.strip()
                            
                            if plot_text and len(plot_text) > 100:  # Ensure we got meaningful content
                                return plot_text
                
                except Exception as e:
                    self._output(f"Error checking '{search_title}': {e}")
                    continue
            
            return None
            
        except Exception as e:
            self._output(f"Wikipedia plot fetch error for '{title}' ({year}): {e}")
            return None
    
    def _resolveImdbId(self, title, year):
        """
        Resolve an IMDb ID for a movie using title and optional year via TMDb,
        with OMDb as fallback. Always returns an ID with 'tt' prefix like 'tt1234567' or None.
        """
        # Try TMDb first: search by title/year, then get external_ids
        try:
            params = {"api_key": self.tmdbApiKey, "query": title}
            if year:
                params["year"] = int(year)
            search = self._session.get("https://api.themoviedb.org/3/search/movie", params=params, timeout=10).json()
            results = search.get("results") or []
            if not results and year:
                # retry without year constraint
                params.pop("year", None)
                search = self._session.get("https://api.themoviedb.org/3/search/movie", params=params, timeout=10).json()
                results = search.get("results") or []
            
            if results:
                # choose the best match (prefer exact year)
                best = results[0]
                if year:
                    for r in results:
                        date = (r.get("release_date") or "")[:4]
                        if date and date.isdigit() and int(date) == int(year):
                            best = r
                            break

                tmdb_id = best.get("id")
                if tmdb_id:
                    ext = self._session.get(f"https://api.themoviedb.org/3/movie/{tmdb_id}/external_ids",
                                       params={"api_key": self.tmdbApiKey}, timeout=10).json()
                    imdb_id = ext.get("imdb_id")
                    if imdb_id:
                        return self._normalizeImdbId(imdb_id)
        except Exception:
            pass
        
        # Fallback to OMDb
        try:
            data = self._getMovieOmdb(title, year, imdbId=None)
            if data and data.get('imdbID'):
                return self._normalizeImdbId(data.get('imdbID'))
        except Exception:
            pass
        
        return None

    def _getMovieOmdb(self, title, year, imdbId):
        params = dict()
        params['apikey'] = self.omdbApiKey
        if imdbId:
            params['i'] = imdbId
        else:
            params['t'] = title

        if year: params['y'] = str(year)

        response = self._session.get("http://www.omdbapi.com/", params=params, timeout=10)
        if response.status_code != 200:
            self._output(f"OMDb request failed for \"{title}\"({year}): {response.status_code}")
            return None

        data = response.json()
        if data.get('Response') == 'False':
            self._output(f"OMDb error for \"{title}\"({year}): {data.get('Error')}")
            return None

        return data

    def _getTmdbConfig(self):
        """Get TMDB configuration with caching to avoid redundant API calls."""
        if self._tmdb_config_cache is None:
            try:
                response = self._session.get(
                    "https://api.themoviedb.org/3/configuration",
                    params={"api_key": self.tmdbApiKey},
                    timeout=10
                )
                if response.status_code == 200:
                    self._tmdb_config_cache = response.json()
            except Exception as e:
                self._output(f"Failed to fetch TMDB configuration: {e}")
                # Fallback to default values
                self._tmdb_config_cache = {
                    "images": {
                        "secure_base_url": "https://image.tmdb.org/t/p/"
                    }
                }
        return self._tmdb_config_cache
    
    def _buildPosterUrls(self, poster_path):
        """Build poster URLs from TMDB poster path."""
        if not poster_path:
            return None, None
        
        config = self._getTmdbConfig()
        base_url = config.get("images", {}).get("secure_base_url", "https://image.tmdb.org/t/p/")
        return f"{base_url}w500{poster_path}", f"{base_url}original{poster_path}"

    def _getMovieTmdb(self, title, year, imdbId):
        """
        Fetch comprehensive movie data from TMDB.
        Returns a dictionary with OMDb-compatible keys (Title, imdbID, Year, etc.)
        plus additional TMDB-specific data.
        
        Optimized for:
        - Reduced API calls via caching
        - Connection pooling via session
        - Single-pass data extraction
        """
        tmdb_id = None
        
        # Step 1: Find the TMDB ID
        if imdbId:
            # Use IMDb ID to find TMDB ID
            try:
                response = self._session.get(
                    f"https://api.themoviedb.org/3/find/{imdbId}",
                    params={
                        "api_key": self.tmdbApiKey,
                        "external_source": "imdb_id"
                    },
                    timeout=10
                )
                if response.status_code == 200:
                    data = response.json()
                    movies = data.get("movie_results", [])
                    if movies:
                        tmdb_id = movies[0].get("id")
                else:
                    self._output(f"TMDB find request failed for IMDb ID {imdbId}: {response.status_code}")
            except Exception as e:
                self._output(f"TMDB find request error for IMDb ID {imdbId}: {e}")
        
        if not tmdb_id:
            # Search by title and year
            try:
                params = {"api_key": self.tmdbApiKey, "query": title}
                if year:
                    params["year"] = int(year)
                
                response = self._session.get(
                    "https://api.themoviedb.org/3/search/movie",
                    params=params,
                    timeout=10
                )
                if response.status_code != 200:
                    self._output(f"TMDB search request failed for \"{title}\"({year}): {response.status_code}")
                    return None
                
                results = response.json().get("results", [])
                
                # Retry without year if no results
                if not results and year:
                    params.pop("year", None)
                    response = self._session.get(
                        "https://api.themoviedb.org/3/search/movie",
                        params=params,
                        timeout=10
                    )
                    if response.status_code == 200:
                        results = response.json().get("results", [])
                
                if not results:
                    self._output(f"No TMDB results found for \"{title}\"({year})")
                    return None
                
                # Choose the best match (prefer exact year)
                best = results[0]
                if year:
                    for r in results:
                        date = (r.get("release_date", ""))[:4]
                        if date and date.isdigit() and int(date) == int(year):
                            best = r
                            break
                
                tmdb_id = best.get("id")
            except Exception as e:
                self._output(f"TMDB search request error for \"{title}\"({year}): {e}")
                return None
        
        if not tmdb_id:
            return None
        
        # Step 2: Fetch comprehensive movie details (single API call with append_to_response)
        try:
            response = self._session.get(
                f"https://api.themoviedb.org/3/movie/{tmdb_id}",
                params={
                    "api_key": self.tmdbApiKey,
                    "append_to_response": "credits,images,keywords,recommendations,similar,external_ids,release_dates"
                },
                timeout=15
            )
            
            if response.status_code != 200:
                self._output(f"TMDB details request failed for TMDB ID {tmdb_id}: {response.status_code}")
                return None
            
            raw_data = response.json()
            
            # Step 3: Transform to OMDb-compatible format - single-pass extraction
            external_ids = raw_data.get('external_ids', {})
            credits = raw_data.get('credits', {})
            crew = credits.get('crew', [])
            cast = credits.get('cast', [])
            
            # Build movie data dictionary
            movie_data = {
                # Basic info
                'Title': raw_data.get('title') or raw_data.get('original_title'),
                'Year': (raw_data.get('release_date', ''))[:4],
                'ImdbID': external_ids.get('imdb_id'),
                'ImdbRating': str(raw_data['vote_average']) if raw_data.get('vote_average') else None,
                
                # Runtime
                'Runtime': f"{raw_data['runtime']} min" if raw_data.get('runtime') else None,
                
                # Plot
                'Plot': raw_data.get('overview'),
                
                # Lists - use list comprehensions for efficiency
                'Countries': [c['name'] for c in raw_data.get('production_countries', []) if c.get('name')],
                'Directors': [c['name'] for c in crew if c.get('job') == 'Director' and c.get('name')],
                'Actors': [c['name'] for c in cast[:10] if c.get('name')],
                'Genres': [g['name'] for g in raw_data.get('genres', []) if g.get('name')],
                'ProductionCompanies': [c['name'] for c in raw_data.get('production_companies', []) if c.get('name')],
                'Writers': [c['name'] for c in crew if c.get('department') == 'Writing' and c.get('name')],
                'Producers': [c['name'] for c in crew if c.get('job') in ['Producer', 'Executive Producer'] and c.get('name')],
                'Composers': [c['name'] for c in crew if c.get('department') == 'Sound' and c.get('job') == 'Original Music Composer' and c.get('name')],
                'Keywords': [k['name'] for k in raw_data.get('keywords', {}).get('keywords', []) if k.get('name')],
                
                # TMDB-specific
                'TmdbId': tmdb_id,
                'Budget': raw_data.get('budget'),
                'Revenue': raw_data.get('revenue'),
                'VoteCount': raw_data.get('vote_count'),
                'Popularity': raw_data.get('popularity'),
                'Tagline': raw_data.get('tagline'),
                'RawTmdbData': raw_data
            }
            
            # Box office
            revenue = raw_data.get('revenue')
            movie_data['BoxOffice'] = f"${revenue:,}" if revenue and revenue > 0 else None
            
            # MPAA rating from release_dates
            mpaa_rating = None
            for country_data in raw_data.get('release_dates', {}).get('results', []):
                if country_data.get('iso_3166_1') == 'US':
                    for release in country_data.get('release_dates', []):
                        cert = release.get('certification')
                        if cert:
                            mpaa_rating = cert
                            break
                    if mpaa_rating:
                        break
            movie_data['Rated'] = mpaa_rating
            
            # Poster URLs - optimized with single config fetch
            posters = raw_data.get('images', {}).get('posters', [])
            poster_path = posters[0]['file_path'] if posters else raw_data.get('poster_path')
            if poster_path:
                poster_url, poster_full = self._buildPosterUrls(poster_path)
                movie_data['Poster'] = poster_url
                movie_data['PosterFullSize'] = poster_full
            
            # Fetch detailed plot from Wikipedia for synopsis
            self._output(f"Fetching Wikipedia plot for '{movie_data['Title']}' ({movie_data['Year']})...")
            wiki_plot = self._getWikipediaPlot(movie_data['Title'], movie_data['Year'])
            if wiki_plot:
                movie_data['Synopsis'] = wiki_plot
                self._output(f"Successfully fetched Wikipedia plot ({len(wiki_plot)} characters)")
            else:
                self._output("No Wikipedia plot found")
            
            return movie_data
            
        except Exception as e:
            self._output(f"TMDB details request error for TMDB ID {tmdb_id}: {e}")
            return None

    def _writeJson(self, movieData, jsonFile):
        d = {}
        
        # First, read existing JSON file to preserve certain fields like embeddings
        existing_data = {}
        if os.path.exists(jsonFile):
            try:
                with open(jsonFile, 'r', encoding='utf-8') as f:
                    existing_data = ujson.load(f)
            except Exception:
                pass  # If we can't read it, just continue with empty existing_data

        d['title'] = movieData.get('Title')
        d['id'] = movieData.get('ImdbID') or movieData.get('imdbID')  # Support both formats
        d['kind'] = 'movie'
        d['year'] = movieData.get('Year')
        d['rating'] = movieData.get('ImdbRating') or movieData.get('imdbRating')
        d['mpaa rating'] = movieData.get('Rated')
        d['date'] = datetime.now().strftime('%Y/%m/%d')
        
        # Handle both list format (TMDB) and comma-separated string (OMDb)
        countries = movieData.get('Countries')
        if isinstance(countries, list):
            d['countries'] = countries
        else:
            country_str = movieData.get('Country', '')
            d['countries'] = [c.strip() for c in country_str.split(',') if c.strip()]
        
        # Use production companies from TMDB data
        d['companies'] = movieData.get('ProductionCompanies') or []
        
        runtime = (movieData.get('Runtime') or '')
        d['runtime'] = runtime.split()[0] if runtime else None
        d['box office'] = movieData.get('BoxOffice')
        
        # Handle both list format (TMDB) and comma-separated string (OMDb)
        directors = movieData.get('Directors')
        if isinstance(directors, list):
            d['directors'] = directors
        else:
            director_str = movieData.get('Director', '')
            d['directors'] = [d.strip() for d in director_str.split(',') if d.strip()]
        
        # Handle both list format (TMDB) and comma-separated string (OMDb)
        actors = movieData.get('Actors')
        if isinstance(actors, list):
            d['cast'] = actors
        else:
            d['cast'] = [a.strip() for a in actors.split(',') if a.strip()] if actors else []
        
        # Handle both list format (TMDB) and comma-separated string (OMDb)
        genres = movieData.get('Genres')
        if isinstance(genres, list):
            d['genres'] = genres
        else:
            genre_str = movieData.get('Genre', '')
            d['genres'] = [g.strip() for g in genre_str.split(',') if g.strip()]
        
        d['plot'] = movieData.get('Plot')
        d['cover url'] = movieData.get('Poster')
        d['full-size cover url'] = movieData.get('PosterFullSize') or movieData.get('Poster')
        
        # Add additional TMDB data if available
        if movieData.get('Writers'):
            d['writers'] = movieData.get('Writers')
        if movieData.get('Producers'):
            d['producers'] = movieData.get('Producers')
        if movieData.get('Composers'):
            d['composers'] = movieData.get('Composers')
        if movieData.get('Keywords'):
            d['keywords'] = movieData.get('Keywords')
        if movieData.get('Tagline'):
            d['tagline'] = movieData.get('Tagline')
        if movieData.get('Budget'):
            d['budget'] = movieData.get('Budget')
        if movieData.get('Revenue'):
            d['revenue'] = movieData.get('Revenue')
        
        # Add Wikipedia synopsis if available
        if movieData.get('Synopsis'):
            d['synopsis'] = movieData.get('Synopsis')
        
        # Add size and movie file info if present in movieData
        if movieData.get('size'):
            d['size'] = movieData.get('size')
        if movieData.get('width'):
            d['width'] = movieData.get('width')
        if movieData.get('height'):
            d['height'] = movieData.get('height')
        if movieData.get('channels'):
            d['channels'] = movieData.get('channels')
        
        # Preserve embedding fields from existing JSON if they exist
        if existing_data.get('embedding'):
            d['embedding'] = existing_data['embedding']
        if existing_data.get('embedding_model'):
            d['embedding_model'] = existing_data['embedding_model']
        if existing_data.get('embedding_dimension'):
            d['embedding_dimension'] = existing_data['embedding_dimension']

        try:
            with open(jsonFile, "w", encoding="utf-8") as f:
                ujson.dump(d, f, indent=4)
        except Exception as e:
            self._output(f"Error writing json file: {e}")
