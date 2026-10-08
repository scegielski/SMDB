import io
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
import zipfile

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt5 import QtCore, QtTest, QtWidgets
from smdb.SubtitleDownload import downloadSubtitle, SubtitleDownloadJob
from smdb.RetroChannelWidget import ClipSlot, RetroChannelWidget

CAPTION = b'1\n00:00:00,000 --> 00:00:05,000\nDownloaded caption'


class SubtitleDownloadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def response(self, data=None, content=b'', content_type='application/octet-stream'):
        response = Mock()
        response.json.return_value = data
        response.content = content
        response.headers = {'Content-Type': content_type}
        return response

    def test_shared_api_download_validates_saves_and_reuses_existing_sidecar(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'Movie.srt'
            search = self.response({'data': [{'attributes': {'files': [{'file_id': 42}]}}]})
            link = self.response({'link': 'https://example.invalid/caption.srt'})
            payload = self.response(content=CAPTION)
            with patch('smdb.SubtitleDownload.requests.get', side_effect=[search, payload]) as get, \
                    patch('smdb.SubtitleDownload.requests.post', return_value=link) as post:
                self.assertEqual(downloadSubtitle('tt123', target, 'test-key'), str(target))
                self.assertEqual(target.read_bytes(), CAPTION)
                self.assertEqual(get.call_args_list[0].kwargs['params']['imdb_id'], '123')
                self.assertEqual(get.call_args_list[0].kwargs['params']['languages'], 'en')
                post.assert_called_once()
                downloadSubtitle('tt123', target, 'test-key')
                self.assertEqual(get.call_count, 2)

    def test_zip_content_and_invalid_payload_do_not_overwrite_existing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'Movie.srt'
            archive = io.BytesIO()
            with zipfile.ZipFile(archive, 'w') as output:
                output.writestr('nested/subtitle.srt', CAPTION)
            search = self.response({'data': [{'attributes': {'files': [{'file_id': 42}]}}]})
            link = self.response({'link': 'https://example.invalid/caption.zip'})
            with patch('smdb.SubtitleDownload.requests.get', side_effect=[search, self.response(content=archive.getvalue(), content_type='application/zip')]), \
                    patch('smdb.SubtitleDownload.requests.post', return_value=link):
                downloadSubtitle('123', target, 'test-key')
            self.assertEqual(target.read_bytes(), CAPTION)
            target.write_text('old invalid file')
            link.json.return_value = {'link': 'https://example.invalid/caption.srt'}
            with patch('smdb.SubtitleDownload.requests.get', side_effect=[search, self.response(content=b'<html>error</html>')]), \
                    patch('smdb.SubtitleDownload.requests.post', return_value=link):
                with self.assertRaisesRegex(ValueError, 'no usable'):
                    downloadSubtitle('123', target, 'test-key')
            self.assertEqual(target.read_text(), 'old invalid file')
            self.assertEqual(list(Path(directory).iterdir()), [target])

    def test_no_matches_or_missing_credentials_do_not_leave_a_file(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'Movie.srt'
            with patch('smdb.SubtitleDownload.requests.get', return_value=self.response({'data': []})):
                with self.assertRaisesRegex(ValueError, 'No downloadable'):
                    downloadSubtitle('123', target, 'test-key')
            with self.assertRaisesRegex(ValueError, 'API key'):
                downloadSubtitle('123', target, '')
            self.assertFalse(target.exists())

    def test_worker_download_does_not_block_gui_events(self):
        release = threading.Event()
        started = threading.Event()
        delivered = []
        heartbeat = []

        def download(*arguments):
            started.set()
            release.wait(2)
            return 'Movie.srt'

        pool = QtCore.QThreadPool()
        job = SubtitleDownloadJob('123', 'Movie.srt', 'test-key')
        job.signals.finished.connect(lambda movie, path, error: delivered.append((path, error)))
        with patch('smdb.SubtitleDownload.downloadSubtitle', side_effect=download):
            try:
                pool.start(job)
                self.assertTrue(started.wait(1))
                QtCore.QTimer.singleShot(10, lambda: heartbeat.append(True))
                for _ in range(50):
                    if heartbeat:
                        break
                    QtTest.QTest.qWait(10)
                self.assertEqual(heartbeat, [True])
                self.assertEqual(delivered, [])
            finally:
                release.set()
                pool.waitForDone(1000)
                self.app.processEvents()
        self.assertEqual(delivered, [('Movie.srt', '')])

    def test_automatic_download_message_success_failure_and_stale_completion(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = QtWidgets.QWidget()
            parent.settings = QtCore.QSettings(str(Path(directory) / 'settings.ini'), QtCore.QSettings.IniFormat)
            parent.moviesTableModel = Mock()
            parent.moviesTableModel.getId.return_value = 'tt123'
            parent.openSubtitlesApiKey = 'test-key'
            tv = RetroChannelWidget(parent)
            slot, spare = ClipSlot(tv), ClipSlot(tv)
            movie = str(Path(directory) / 'Movie.mp4')
            Path(movie).write_bytes(b'fixture')
            slot.path = movie
            slot.subtitles.path = movie
            slot.subtitles.enabled = True
            slot.subtitles._probed = True
            tv.subtitlesEnabled = True
            tv.isActive = True
            tv._videoPathCache = {7: movie}
            tv.engines = {0: SimpleNamespace(activeSlot=slot, slotA=slot, slotB=spare)}
            normalized = os.path.normcase(os.path.abspath(movie))
            pool = Mock()
            try:
                with patch('smdb.RetroChannelWidget.QtCore.QThreadPool.globalInstance', return_value=pool):
                    slot.subtitles._pendingJobs = 1
                    tv._ensureCurrentSubtitles()
                    pool.start.assert_not_called()  # wait for embedded-track discovery first
                    slot.subtitles._pendingJobs = 0
                    tv._ensureCurrentSubtitles()
                    tv._ensureCurrentSubtitles()
                    pool.start.assert_called_once()
                    self.assertEqual(slot.subtitles.label.text(), 'Downloading subtitles...')
                    target = Path(directory) / 'Movie.srt'
                    target.write_bytes(CAPTION)
                    tv._onSubtitleDownloadFinished(normalized, str(target), '')
                    self.assertEqual(slot.subtitles.statusMessage, '')
                    self.assertEqual(slot.subtitles.label.text(), 'Downloaded caption')
                    tv._ensureCurrentSubtitles()
                    self.assertEqual(pool.start.call_count, 1)
                    tv._onSubtitleDownloadFinished(normalized, '', 'No matches')
                    self.assertEqual(slot.subtitles.statusMessage, 'Subtitles unavailable')
                    slot.path = str(Path(directory) / 'Another.mp4')
                    slot.subtitles.clear()
                    tv._onSubtitleDownloadFinished(normalized, str(target), '')
                    self.assertEqual(slot.subtitles.cues, [])
                    self.assertEqual(slot.subtitles.statusMessage, '')
            finally:
                slot.stop()
                spare.stop()
                tv.engines = {}
                tv.isActive = False
                tv.close()
                parent.close()
