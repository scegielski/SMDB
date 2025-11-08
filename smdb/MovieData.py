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

    def writeMovieJsonOmdb(self, movieData, productionCompanies, similarMovies, jsonFile):
        d = {}

        d['title'] = movieData.get('Title')
        d['id'] = movieData.get('imdbID')
        d['kind'] = 'movie'  # OMDb doesn't distinguish TV/miniseries cleanly
        d['year'] = movieData.get('Year')
        d['rating'] = movieData.get('imdbRating')
        d['mpaa rating'] = movieData.get('Rated')
        d['countries'] = [c.strip() for c in movieData.get('Country', '').split(',')]
        d['companies'] = productionCompanies
        runtime = (movieData.get('Runtime') or '')
        d['runtime'] = runtime.split()[0] if runtime else None
        d['box office'] = movieData.get('BoxOffice')
        d['directors'] = [d.strip() for d in movieData.get('Director', '').split(',') if d.strip()]
        d['cast'] = [a.strip() for a in movieData.get('Actors', '').split(',') if a.strip()]
        d['genres'] = [g.strip() for g in movieData.get('Genre', '').split(',') if g.strip()]
        d['plot'] = movieData.get('Plot')
        d['plot outline'] = movieData.get('Plot')  # OMDb doesn't separate this
        d['synopsis'] = movieData.get('Plot')  # same
        d['summary'] = movieData.get('Plot')  # same
        d['cover url'] = movieData.get('Poster')
        d['full-size cover url'] = movieData.get('Poster')  # OMDb only provides one
        d['similar movies'] = similarMovies or []

        try:
            with open(jsonFile, "w", encoding="utf-8") as f:
                ujson.dump(d, f, indent=4)
        except Exception as e:
            self.output(f"Error writing json file: {e}")

    def downloadTMDBCover(self, titleYear, imdbId, coverFile):
        self.output(f"Trying to download cover for \"{titleYear}\" using TMDB...")
        if not imdbId:
            m = re.match(r"(.*)\((\d{4})\)", titleYear)
            title = titleYear
            year = None
            if m:
                title = m.group(1).strip()
                try:
                    year = int(m.group(2))
                except Exception:
                    year = None
            # Try to resolve IMDb ID without IMDbPY
            imdbId = self.resolve_imdb_id(title, year)

        size = "original"
        f = requests.get("https://api.themoviedb.org/3/find/{}".format(imdbId),
                         params={"api_key": self.tmdbApiKey, "external_source": "imdb_id"}).json()
        movies = f.get("movie_results") or []
        if not movies:
            return

        tmdb_id = movies[0]["id"]
        imgs = requests.get(f"https://api.themoviedb.org/3/movie/{tmdb_id}/images",
                            params={"api_key": self.tmdbApiKey}).json()
        posters = imgs.get("posters") or []
        if not posters:
            return

        cfg = requests.get("https://api.themoviedb.org/3/configuration",
                           params={"api_key": self.tmdbApiKey}).json()
        base = cfg["images"]["secure_base_url"]
        movieCoverUrl = f"{base}{size}{posters[0]['file_path']}"
        try:
            urllib.request.urlretrieve(movieCoverUrl, coverFile)
        except Exception as e:
            self.output(f"Problem downloading cover from TMDB for \"{titleYear}\" from: {movieCoverUrl} - {e}")
        self.output(f"Successfully downloaded cover from TMDB for \"{titleYear}\"")

    def getTMDBProductionCompanies(self, titleYear, imdbId):
        if not imdbId:
            return None

        # Step 1: Find the TMDb ID using the IMDb ID
        find_url = f"https://api.themoviedb.org/3/find/{imdbId}"
        f = requests.get(find_url, params={
            "api_key": self.tmdbApiKey,
            "external_source": "imdb_id"
        }).json()

        movies = f.get("movie_results") or []
        if not movies:
            return []

        tmdb_id = movies[0]["id"]

        # Step 2: Query movie details for production companies
        details_url = f"https://api.themoviedb.org/3/movie/{tmdb_id}"
        d = requests.get(details_url, params={"api_key": self.tmdbApiKey}).json()
        companies = d.get("production_companies", [])

        if not companies:
            return []

        # Step 3: Extract and format company names
        result = [c.get("name") for c in companies if c.get("name")]
        return result

    def getYTSSimilarMovies(self, titleYear, imdbId, limit=5):
        if not imdbId:
            self.output(f"No IMDb ID available to fetch similar titles for \"{titleYear}\".")
            return []

        # Step 1: Look up the YTS movie id using the IMDb id
        details_url = "https://yts.mx/api/v2/movie_details.json"
        try:
            details_resp = requests.get(details_url, params={
                "imdb_id": imdbId
            })
            if details_resp.status_code != 200:
                self.output(f"YTS movie details request failed for \"{titleYear}\": HTTP {details_resp.status_code}")
                return []
            details = details_resp.json()
        except Exception as exc:
            self.output(f"YTS movie details request failed for \"{titleYear}\": {exc}")
            return []

        if details.get("status") != "ok":
            self.output(f"YTS movie details lookup returned error for \"{titleYear}\": {details.get('status_message')}")
            return []

        movie_data = (details.get("data") or {}).get("movie") or {}
        movie_id = movie_data.get("id")
        if not movie_id:
            self.output(f"YTS movie details missing movie id for \"{titleYear}\".")
            return []

        # Step 2: Fetch suggestions from YTS
        similar_url = "https://yts.mx/api/v2/movie_suggestions.json"
        try:
            similar_resp = requests.get(similar_url, params={
                "movie_id": movie_id
            })
            if similar_resp.status_code != 200:
                self.output(f"YTS similar request failed for \"{titleYear}\": HTTP {similar_resp.status_code}")
                return []
            similar = similar_resp.json()
        except Exception as exc:
            self.output(f"YTS similar request failed for \"{titleYear}\": {exc}")
            return []

        if similar.get("status") != "ok":
            self.output(f"YTS similar lookup returned error for \"{titleYear}\": {similar.get('status_message')}")
            return []

        results = (similar.get("data") or {}).get("movies") or []
        if not results:
            self.output(f"No similar movies found for \"{titleYear}\" on YTS.")
            return []

        similar_titles = []
        for movie in results[:limit]:
            title = movie.get("title")
            year = movie.get("year")
            if title:
                formatted = f"{title} ({year})" if year else title
                similar_titles.append(formatted)

        if similar_titles:
            joined = ", ".join(similar_titles)
            self.output(f"Similar movies from YTS for \"{titleYear}\": {joined}")
        else:
            self.output(f"No similar movies found for \"{titleYear}\" on YTS.")

        return similar_titles

    def resolve_imdb_id(self, title, year=None):
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
                imdbId = self.resolve_imdb_id(title, year)

            movie = self.getMovieOmdb(title, year, api_key=self.omdbApiKey, imdbId=imdbId)

            if not movie: return ""

            productionCompanies = self.getTMDBProductionCompanies(titleYear, imdbId)
            similarMovies = self.getYTSSimilarMovies(titleYear, imdbId)

            if doJson:
                self.writeMovieJsonOmdb(movie, productionCompanies, similarMovies, jsonFile)
                if parent.moviesSmdbData and 'titles' in parent.moviesSmdbData:
                    titleEntry = parent.moviesSmdbData['titles'].get(moviePath)
                    if titleEntry is not None:
                        titleEntry['similar movies'] = similarMovies or []
                        try:
                            with open(parent.moviesSmdbFile, "w") as smdbFileHandle:
                                ujson.dump(parent.moviesSmdbData, smdbFileHandle, indent=4)
                        except Exception as e:
                            self.output(f"Error updating smdb_data.json with similar movies: {e}")
                parent.calculateFolderSize(proxyIndex, moviePath, movieFolderName)
                parent.getMovieFileInfo(proxyIndex, moviePath, movieFolderName)

            if doCover:
                if not 'Poster' in movie:
                    self.output("Error: No cover image available")
                    return ""
                movieCoverUrl = movie['Poster']
                extension = os.path.splitext(movieCoverUrl)[1]
                if extension == '.png':
                    coverFile = coverFile.replace('.jpg', '.png')
                try:
                    urllib.request.urlretrieve(movieCoverUrl, coverFile)
                except Exception as e:
                    self.output(f"Problem downloading cover for \"{titleYear}\" from: {movieCoverUrl} - {e}")
                    self.downloadTMDBCover(titleYear, imdbId, coverFile)


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
