from pathlib import Path
import os
import re
import requests
import urllib.request
import ujson
from pymediainfo import MediaInfo
from .utilities import *


class MovieData:
    """Encapsulate movie-data download and JSON writing logic.

    This class is intentionally thin and delegates UI/logging back to the
    MainWindow instance passed as `parent` so we don't duplicate UI code.
    """

    def __init__(self, parent):
        self.parent = parent
        
        # API keys for external services
        self.tmdbApiKey = "acaa3a2b3d6ebbb8749bfa43bd3d8af7"
        self.omdbApiKey = "fe5db83f"
        
        # Cache for TMDB configuration (image base URLs)
        self._tmdb_config_cache = None
        
        # Reusable session for connection pooling
        self._session = requests.Session()

    def output(self, *args, **kwargs):
        return self.parent.output(*args, **kwargs)
    
    def _get_tmdb_config(self):
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
                self.output(f"Failed to fetch TMDB configuration: {e}")
                # Fallback to default values
                self._tmdb_config_cache = {
                    "images": {
                        "secure_base_url": "https://image.tmdb.org/t/p/"
                    }
                }
        return self._tmdb_config_cache
    
    def _build_poster_urls(self, poster_path):
        """Build poster URLs from TMDB poster path."""
        if not poster_path:
            return None, None
        
        config = self._get_tmdb_config()
        base_url = config.get("images", {}).get("secure_base_url", "https://image.tmdb.org/t/p/")
        return f"{base_url}w500{poster_path}", f"{base_url}original{poster_path}"

    def resolveImdbId(self, title, year=None):
        """
        Resolve an IMDb ID for a movie using title and optional year via OMDb first,
        then TMDb as a fallback. Always returns an ID with 'tt' prefix like 'tt1234567' or None.
        """
        # 1) Try OMDb
        try:
            data = self.getMovieOmdb(title, year, api_key=self.omdbApiKey)
            if data and data.get('imdbID'):
                imdb_id = data.get('imdbID')
                if imdb_id:
                    # Ensure tt prefix
                    if not imdb_id.startswith('tt'):
                        imdb_id = f"tt{imdb_id}"
                    return imdb_id
        except Exception:
            pass

        # 2) Fallback to TMDb: search by title/year, then get external_ids
        try:
            params = {"api_key": self.tmdbApiKey, "query": title}
            if year:
                params["year"] = int(year)
            search = requests.get("https://api.themoviedb.org/3/search/movie", params=params).json()
            results = search.get("results") or []
            if not results and year:
                # retry without year constraint
                params.pop("year", None)
                search = requests.get("https://api.themoviedb.org/3/search/movie", params=params).json()
                results = search.get("results") or []
            if not results:
                return None

            # choose the best match (prefer exact year)
            best = results[0]
            if year:
                for r in results:
                    date = (r.get("release_date") or "")[:4]
                    if date and date.isdigit() and int(date) == int(year):
                        best = r
                        break

            tmdb_id = best.get("id")
            if not tmdb_id:
                return None
            ext = requests.get(f"https://api.themoviedb.org/3/movie/{tmdb_id}/external_ids",
                               params={"api_key": self.tmdbApiKey}).json()
            imdb_id = ext.get("imdb_id")
            if imdb_id:
                # Ensure tt prefix
                if not imdb_id.startswith('tt'):
                    imdb_id = f"tt{imdb_id}"
                return imdb_id
        except Exception:
            pass
        
        return None

    def downloadMovieData(self, proxyIndex, force=False, imdbId=None, doJson=True, doCover=True):
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
                imdbId = self.resolveImdbId(title, year)
            if not imdbId:
                self.output(f"Could not resolve IMDb ID for \"{titleYear}\"")
                return ""

            # Try TMDB first
            movie = self.getMovieTmdb(title, year, imdbId=imdbId)
            
            # Fall back to OMDb if TMDB fails
            if not movie:
                self.output(f"TMDB lookup failed, falling back to OMDb for \"{titleYear}\"")
                movie = self.getMovieOmdb(title, year, api_key=self.omdbApiKey, imdbId=imdbId)

            if not movie: return ""

            if doJson:
                # Calculate folder size
                total_size = 0
                for dirpath, dirnames, filenames in os.walk(moviePath):
                    for f in filenames:
                        fp = os.path.join(dirpath, f)
                        if not os.path.islink(fp):
                            total_size += os.path.getsize(fp)
                folderSize = '%05d Mb' % (total_size / (2**20))
                
                # Get movie file info
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
                
                # Write JSON with size and movie info
                self.writeJson(movie, None, None, jsonFile)
                
                # Update table model
                parent.moviesTableModel.setSize(sourceIndex, folderSize)
                parent.moviesTableModel.setMovieData(sourceRow, 
                                                    {'width': width, 'height': height, 'channels': channels},
                                                    moviePath, 
                                                    movieFolderName)

            coverFile = ""
            if doCover:
                if 'PosterFullSize' in movie:
                    movieCoverUrl = movie['PosterFullSize']
                elif 'Poster' in movie:
                    movieCoverUrl = movie['Poster']
                else:
                    self.output("Error: No cover image available")

                try:
                    urllib.request.urlretrieve(movieCoverUrl, coverFile)
                except Exception as e:
                    self.output("No TMDB ID available for fallback cover download")


            parent.moviesTableModel.setMovieDataWithJson(sourceRow,
                                                       jsonFile,
                                                       moviePath,
                                                       movieFolderName)

        return coverFile

    def getMovieOmdb(self, title, year=None, api_key="YOUR_API_KEY", imdbId=None):
        params = dict()
        params['apikey'] = api_key
        if imdbId:
            params['i'] = imdbId
        else:
            params['t'] = title

        if year: params['y'] = str(year)

        response = requests.get("http://www.omdbapi.com/", params=params)
        if response.status_code != 200:
            self.output(f"OMDb request failed for \"{title}\"({year}): {response.status_code}")
            return None

        data = response.json()
        if data.get('Response') == 'False':
            self.output(f"OMDb error for \"{title}\"({year}): {data.get('Error')}")
            return None

        return data

    def getMovieTmdb(self, title, year=None, imdbId=None):
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
                    self.output(f"TMDB find request failed for IMDb ID {imdbId}: {response.status_code}")
            except Exception as e:
                self.output(f"TMDB find request error for IMDb ID {imdbId}: {e}")
        
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
                    self.output(f"TMDB search request failed for \"{title}\"({year}): {response.status_code}")
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
                    self.output(f"No TMDB results found for \"{title}\"({year})")
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
                self.output(f"TMDB search request error for \"{title}\"({year}): {e}")
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
                self.output(f"TMDB details request failed for TMDB ID {tmdb_id}: {response.status_code}")
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
                poster_url, poster_full = self._build_poster_urls(poster_path)
                movie_data['Poster'] = poster_url
                movie_data['PosterFullSize'] = poster_full
            
            # Similar/Recommended movies - optimized formatting
            def format_movies(movies_list, limit=5):
                result = []
                for m in movies_list[:limit]:
                    title = m.get('title')
                    if title:
                        year_str = (m.get('release_date', ''))[:4]
                        result.append(f"{title} ({year_str})" if year_str else title)
                return result
            
            movie_data['SimilarMoviesTmdb'] = format_movies(
                raw_data.get('similar', {}).get('results', [])
            )
            movie_data['RecommendedMoviesTmdb'] = format_movies(
                raw_data.get('recommendations', {}).get('results', [])
            )
            
            return movie_data
            
        except Exception as e:
            self.output(f"TMDB details request error for TMDB ID {tmdb_id}: {e}")
            return None

    def writeJson(self, movieData, productionCompanies, similarMovies, jsonFile):
        d = {}

        d['title'] = movieData.get('Title')
        d['id'] = movieData.get('ImdbID') or movieData.get('imdbID')  # Support both formats
        d['kind'] = 'movie'
        d['year'] = movieData.get('Year')
        d['rating'] = movieData.get('ImdbRating') or movieData.get('imdbRating')
        d['mpaa rating'] = movieData.get('Rated')
        
        # Handle both list format (TMDB) and comma-separated string (OMDb)
        countries = movieData.get('Countries')
        if isinstance(countries, list):
            d['countries'] = countries
        else:
            country_str = movieData.get('Country', '')
            d['countries'] = [c.strip() for c in country_str.split(',') if c.strip()]
        
        # Use production companies from TMDB data if available, otherwise use passed parameter
        d['companies'] = movieData.get('ProductionCompanies') or productionCompanies or []
        
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
        d['plot outline'] = movieData.get('Plot')
        d['synopsis'] = movieData.get('Plot')
        d['summary'] = movieData.get('Plot')
        d['cover url'] = movieData.get('Poster')
        d['full-size cover url'] = movieData.get('PosterFullSize') or movieData.get('Poster')
        
        # Use TMDB similar movies if available, otherwise use passed parameter
        d['similar movies'] = movieData.get('SimilarMoviesTmdb') or similarMovies or []
        
        # Add additional TMDB data if available
        if movieData.get('Writers'):
            d['writers'] = movieData.get('Writers')
        if movieData.get('Keywords'):
            d['keywords'] = movieData.get('Keywords')
        if movieData.get('Tagline'):
            d['tagline'] = movieData.get('Tagline')
        if movieData.get('Budget'):
            d['budget'] = movieData.get('Budget')
        if movieData.get('Revenue'):
            d['revenue'] = movieData.get('Revenue')
        
        # Add size and movie file info if present in movieData
        if movieData.get('size'):
            d['size'] = movieData.get('size')
        if movieData.get('width'):
            d['width'] = movieData.get('width')
        if movieData.get('height'):
            d['height'] = movieData.get('height')
        if movieData.get('channels'):
            d['channels'] = movieData.get('channels')

        try:
            with open(jsonFile, "w", encoding="utf-8") as f:
                ujson.dump(d, f, indent=4)
        except Exception as e:
            self.output(f"Error writing json file: {e}")

