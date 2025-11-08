from pathlib import Path
import os
import re
import requests
import urllib.request
import ujson
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

    def output(self, *args, **kwargs):
        return self.parent.output(*args, **kwargs)

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
                self.writeJson(movie, None, None, jsonFile)
                if parent.moviesSmdbData and 'titles' in parent.moviesSmdbData:
                    titleEntry = parent.moviesSmdbData['titles'].get(moviePath)
                    if titleEntry is not None:
                        similar_movies = movie.get('SimilarMoviesTmdb') or []
                        titleEntry['similar movies'] = similar_movies
                        try:
                            with open(parent.moviesSmdbFile, "w") as smdbFileHandle:
                                ujson.dump(parent.moviesSmdbData, smdbFileHandle, indent=4)
                        except Exception as e:
                            self.output(f"Error updating smdb_data.json with similar movies: {e}")
                parent.calculateFolderSize(proxyIndex, moviePath, movieFolderName)
                parent.getMovieFileInfo(proxyIndex, moviePath, movieFolderName)

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
        """
        tmdb_id = None
        
        # Step 1: Find the TMDB ID
        if imdbId:
            # Use IMDb ID to find TMDB ID
            find_url = f"https://api.themoviedb.org/3/find/{imdbId}"
            try:
                response = requests.get(find_url, params={
                    "api_key": self.tmdbApiKey,
                    "external_source": "imdb_id"
                })
                if response.status_code != 200:
                    self.output(f"TMDB find request failed for IMDb ID {imdbId}: {response.status_code}")
                    return None
                
                data = response.json()
                movies = data.get("movie_results") or []
                if movies:
                    tmdb_id = movies[0].get("id")
            except Exception as e:
                self.output(f"TMDB find request error for IMDb ID {imdbId}: {e}")
                return None
        
        if not tmdb_id:
            # Search by title and year
            try:
                params = {"api_key": self.tmdbApiKey, "query": title}
                if year:
                    params["year"] = int(year)
                
                response = requests.get("https://api.themoviedb.org/3/search/movie", params=params)
                if response.status_code != 200:
                    self.output(f"TMDB search request failed for \"{title}\"({year}): {response.status_code}")
                    return None
                
                search = response.json()
                results = search.get("results") or []
                
                if not results and year:
                    # Retry without year constraint
                    params.pop("year", None)
                    response = requests.get("https://api.themoviedb.org/3/search/movie", params=params)
                    if response.status_code == 200:
                        search = response.json()
                        results = search.get("results") or []
                
                if not results:
                    self.output(f"No TMDB results found for \"{title}\"({year})")
                    return None
                
                # Choose the best match (prefer exact year)
                best = results[0]
                if year:
                    for r in results:
                        date = (r.get("release_date") or "")[:4]
                        if date and date.isdigit() and int(date) == int(year):
                            best = r
                            break
                
                tmdb_id = best.get("id")
            except Exception as e:
                self.output(f"TMDB search request error for \"{title}\"({year}): {e}")
                return None
        
        if not tmdb_id:
            return None
        
        # Step 2: Fetch comprehensive movie details
        try:
            # Get main movie details with appended data
            details_url = f"https://api.themoviedb.org/3/movie/{tmdb_id}"
            response = requests.get(details_url, params={
                "api_key": self.tmdbApiKey,
                "append_to_response": "credits,images,videos,keywords,recommendations,similar,external_ids,release_dates"
            })
            
            if response.status_code != 200:
                self.output(f"TMDB details request failed for TMDB ID {tmdb_id}: {response.status_code}")
                return None
            
            raw_data = response.json()
            
            # Step 3: Transform to OMDb-compatible format with camelCase keys
            movie_data = {}
            
            # Basic info
            movie_data['Title'] = raw_data.get('title') or raw_data.get('original_title')
            movie_data['Year'] = (raw_data.get('release_date') or '')[:4]
            
            # Get IMDb ID from external_ids
            external_ids = raw_data.get('external_ids', {})
            movie_data['ImdbID'] = external_ids.get('imdb_id')
            
            # Rating (TMDB uses vote_average out of 10, convert to string like OMDb)
            vote_avg = raw_data.get('vote_average')
            movie_data['ImdbRating'] = str(vote_avg) if vote_avg else None
            
            # Get certification/MPAA rating from release_dates
            mpaa_rating = None
            release_dates = raw_data.get('release_dates', {}).get('results', [])
            for country_data in release_dates:
                if country_data.get('iso_3166_1') == 'US':
                    releases = country_data.get('release_dates', [])
                    for release in releases:
                        cert = release.get('certification')
                        if cert:
                            mpaa_rating = cert
                            break
                    break
            movie_data['Rated'] = mpaa_rating
            
            # Countries (production_countries) - as list
            countries = raw_data.get('production_countries', [])
            movie_data['Countries'] = [c.get('name') for c in countries if c.get('name')]
            
            # Runtime (in minutes)
            runtime = raw_data.get('runtime')
            movie_data['Runtime'] = f"{runtime} min" if runtime else None
            
            # Box office (revenue)
            revenue = raw_data.get('revenue')
            if revenue and revenue > 0:
                movie_data['BoxOffice'] = f"${revenue:,}"
            else:
                movie_data['BoxOffice'] = None
            
            # Directors and Actors from credits
            credits = raw_data.get('credits', {})
            
            crew = credits.get('crew', [])
            directors = [c.get('name') for c in crew if c.get('job') == 'Director']
            movie_data['Directors'] = directors
            
            cast = credits.get('cast', [])
            actors = [c.get('name') for c in cast[:10] if c.get('name')]  # Top 10 actors
            movie_data['Actors'] = actors  # List format
            
            # Genres - as list
            genres = raw_data.get('genres', [])
            genre_names = [g.get('name') for g in genres if g.get('name')]
            movie_data['Genres'] = genre_names  # List format
            
            # Plot/Overview
            movie_data['Plot'] = raw_data.get('overview')
            
            # Poster - get from images
            images = raw_data.get('images', {})
            posters = images.get('posters', [])
            if posters:
                # Get configuration for image base URL
                cfg = requests.get("https://api.themoviedb.org/3/configuration",
                                 params={"api_key": self.tmdbApiKey}).json()
                base = cfg["images"]["secure_base_url"]
                poster_path = posters[0]['file_path']
                movie_data['Poster'] = f"{base}w500{poster_path}"
                movie_data['PosterFullSize'] = f"{base}original{poster_path}"
            elif raw_data.get('poster_path'):
                # Fallback to main poster_path
                cfg = requests.get("https://api.themoviedb.org/3/configuration",
                                 params={"api_key": self.tmdbApiKey}).json()
                base = cfg["images"]["secure_base_url"]
                movie_data['Poster'] = f"{base}w500{raw_data['poster_path']}"
                movie_data['PosterFullSize'] = f"{base}original{raw_data['poster_path']}"
            
            # Additional TMDB-specific data (camelCase)
            movie_data['TmdbId'] = tmdb_id
            movie_data['Budget'] = raw_data.get('budget')
            movie_data['Revenue'] = raw_data.get('revenue')
            movie_data['VoteCount'] = raw_data.get('vote_count')
            movie_data['Popularity'] = raw_data.get('popularity')
            movie_data['Tagline'] = raw_data.get('tagline')
            
            # Production companies
            companies = raw_data.get('production_companies', [])
            movie_data['ProductionCompanies'] = [c.get('name') for c in companies if c.get('name')]
            
            # Writers
            writers = [c.get('name') for c in crew if c.get('department') == 'Writing']
            movie_data['Writers'] = writers
            
            # Keywords
            keywords_data = raw_data.get('keywords', {}).get('keywords', [])
            movie_data['Keywords'] = [k.get('name') for k in keywords_data if k.get('name')]
            
            # Similar/Recommended movies
            similar = raw_data.get('similar', {}).get('results', [])
            similar_titles = []
            for m in similar[:5]:  # Top 5
                sim_title = m.get('title')
                sim_year = (m.get('release_date') or '')[:4]
                if sim_title:
                    formatted = f"{sim_title} ({sim_year})" if sim_year else sim_title
                    similar_titles.append(formatted)
            movie_data['SimilarMoviesTmdb'] = similar_titles
            
            recommendations = raw_data.get('recommendations', {}).get('results', [])
            rec_titles = []
            for m in recommendations[:5]:  # Top 5
                rec_title = m.get('title')
                rec_year = (m.get('release_date') or '')[:4]
                if rec_title:
                    formatted = f"{rec_title} ({rec_year})" if rec_year else rec_title
                    rec_titles.append(formatted)
            movie_data['RecommendedMoviesTmdb'] = rec_titles
            
            # Store raw data for debugging
            movie_data['RawTmdbData'] = raw_data
            
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

        try:
            with open(jsonFile, "w", encoding="utf-8") as f:
                ujson.dump(d, f, indent=4)
        except Exception as e:
            self.output(f"Error writing json file: {e}")

