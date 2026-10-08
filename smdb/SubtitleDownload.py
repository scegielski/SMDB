"""Shared OpenSubtitles download path for the database and SMTV."""
import io
import os
from pathlib import Path
import tempfile
import zipfile

import requests
from PyQt5 import QtCore
from .Subtitles import readSubtitles


def downloadSubtitle(imdb_id, target_path, api_key, language='en'):
    imdb_id = str(imdb_id).removeprefix('tt').strip()
    if not imdb_id.isdigit():
        raise ValueError('No IMDb ID is available for this movie.')
    if not api_key:
        raise ValueError('Configure the OpenSubtitles API key in SMDB first.')
    target = Path(target_path)
    if target.is_file() and readSubtitles(target):
        return str(target)
    headers = {'Api-Key': api_key, 'Accept': 'application/json', 'User-Agent': 'SMDB/1.0'}
    response = requests.get('https://api.opensubtitles.com/api/v1/subtitles', headers=headers,
                            params={'imdb_id': imdb_id, 'languages': language, 'order_by': 'downloads',
                                    'order_direction': 'desc', 'type': 'movie'}, timeout=20)
    response.raise_for_status()
    items = response.json().get('data') or []
    files = items[0].get('attributes', {}).get('files', []) if items else []
    if not files or not files[0].get('file_id'):
        raise ValueError('No downloadable subtitles were found for this movie.')
    post_headers = dict(headers, **{'Content-Type': 'application/json'})
    response = requests.post('https://api.opensubtitles.com/api/v1/download', headers=post_headers,
                             json={'file_id': files[0]['file_id']}, timeout=20)
    response.raise_for_status()
    link = response.json().get('link')
    if not link:
        raise ValueError('OpenSubtitles did not provide a download link.')
    response = requests.get(link, timeout=60)
    response.raise_for_status()
    data = response.content
    if 'zip' in response.headers.get('Content-Type', '').lower() or link.lower().endswith('.zip'):
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            member = next((name for name in archive.namelist() if name.lower().endswith('.srt')), None)
            if member is None:
                raise ValueError('The downloaded archive contains no SRT subtitles.')
            data = archive.read(member)
    # Save atomically only after validating actual subtitle cues.
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, suffix='.srt', delete=False) as output:
            temporary = output.name
            output.write(data)
        if not readSubtitles(temporary):
            raise ValueError('The downloaded file contains no usable subtitle cues.')
        os.replace(temporary, target)
        temporary = None
    finally:
        if temporary:
            os.unlink(temporary)
    return str(target)


class _DownloadSignals(QtCore.QObject):
    finished = QtCore.pyqtSignal(str, str, str)


class SubtitleDownloadJob(QtCore.QRunnable):
    def __init__(self, imdb_id, target_path, api_key, video_path=''):
        super().__init__()
        self.arguments = (imdb_id, target_path, api_key)
        self.videoPath = video_path
        self.signals = _DownloadSignals()

    def run(self):
        try:
            path = downloadSubtitle(*self.arguments)
            self.signals.finished.emit(self.videoPath, path, '')
        except Exception as error:
            self.signals.finished.emit(self.videoPath, '', str(error))
