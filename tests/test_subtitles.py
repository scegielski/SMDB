import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt5 import QtCore, QtTest, QtWidgets
from smdb.VideoView import VideoView as QVideoWidget
from smdb.Subtitles import SubtitleController, mediaTool, parseSubtitles, readSubtitles
from smdb.RetroChannelWidget import ClipSlot, RetroChannelWidget


class SubtitleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_offset_buttons_shift_captions_and_show_temporary_total(self):
        from unittest.mock import Mock, patch
        tv = RetroChannelWidget()
        slot = ClipSlot(tv)
        tv.engines = {0: Mock(slotA=slot, slotB=slot)}
        tv.currentIndex = 0
        controller = slot.subtitles
        controller.enabled = True
        controller._setCues([(1000, 2000, 'Caption')])
        controller.updatePosition(1500)
        try:
            self.assertEqual(controller.label.text(), 'Caption')
            with patch('smdb.VideoView.time.monotonic', return_value=10) as clock:
                tv.subtitleLaterButton.click()
                self.assertEqual(tv.subtitleOffsetMs, 1000)
                self.assertEqual(controller.position, 1500)
                self.assertEqual(controller.label.text(), '')
                self.assertEqual(slot.videoWidget.osd.items['subtitleOffset'], (1, 13))
                controller.updatePosition(2500)
                self.assertEqual(controller.label.text(), 'Caption')
                tv.subtitleLaterButton.click()
                self.assertEqual(tv.subtitleOffsetMs, 2000)
                tv.subtitleEarlierButton.click()
                self.assertEqual(tv.subtitleOffsetMs, 1000)
                tv.subtitleEarlierButton.click()
                tv.subtitleEarlierButton.click()
                self.assertEqual(tv.subtitleOffsetMs, -1000)
                controller.updatePosition(500)
                self.assertEqual(controller.label.text(), 'Caption')
                later = ClipSlot(tv)
                self.assertEqual(later.subtitles.offsetMs, -1000)
                later.stop()
                clock.return_value = 14
                slot.videoWidget.osd._expire()
                self.assertNotIn('subtitleOffset', slot.videoWidget.osd.items)
        finally:
            tv.engines = {}
            slot.stop()
            tv.close()

    def test_channel_change_resets_offsets_including_warmed_and_new_slots(self):
        from unittest.mock import Mock
        tv = RetroChannelWidget()
        slots = [ClipSlot(tv) for _ in range(3)]
        tv.engines = {0: Mock(slotA=slots[0], slotB=slots[1])}
        tv.guidePreviewSlot = slots[2]
        tv.channels = [{'genre': 'Action'}, {'genre': 'Comedy'}]
        tv._powerOn = False
        try:
            for offset in (2000, -3000):
                tv.adjustSubtitleOffset(offset)
                tv._tuneTo(tv.currentIndex)
                self.assertEqual(tv.subtitleOffsetMs, offset)
                tv.channelUp()
                self.assertEqual(tv.subtitleOffsetMs, 0)
                for slot in slots:
                    self.assertEqual(slot.subtitles.offsetMs, 0)
                newSlot = ClipSlot(tv)
                self.assertEqual(newSlot.subtitles.offsetMs, 0)
                newSlot.stop()
                self.assertEqual(tv._videoOsdStatus['subtitleOffset'][0], 0)
        finally:
            tv.engines = {}
            tv.guidePreviewSlot = None
            for slot in slots:
                slot.stop()
            tv.close()

    def test_srt_vtt_unicode_markup_and_overlapping_cues(self):
        text = '\ufeff1\n00:00:01,000 --> 00:00:03,000\n<b>Hello</b> &amp; goodbye\nSecond line\n\n2\n00:00:02,000 --> 00:00:02,500\nOverlap\n'
        cues = parseSubtitles(text)
        self.assertEqual(cues[0], (1000, 3000, 'Hello & goodbye\nSecond line'))
        self.assertEqual(parseSubtitles('WEBVTT\n\n00:01.000 --> 00:02.000 align:center\nCafé'), [(1000, 2000, 'Café')])
        video = QVideoWidget()
        video.resize(640, 360)
        controller = SubtitleController(video)
        controller.enabled = True
        controller._setCues(cues)
        controller.updatePosition(2100)
        self.assertIn('Overlap', controller.label.text())
        controller.updatePosition(2900)
        self.assertEqual(controller.label.text(), 'Hello & goodbye\nSecond line')
        controller.updatePosition(3000)
        self.assertTrue(controller.label.isHidden())
        controller.updatePosition(1500)  # seeking backwards immediately restores the cue
        self.assertIn('Hello', controller.label.text())
        controller.setEnabled(False)
        self.assertTrue(controller.label.isHidden())
        video.close()

    def test_sidecars_track_switching_and_new_movie_clear(self):
        with tempfile.TemporaryDirectory() as directory:
            movie = Path(directory) / 'Film.mkv'
            english = Path(directory) / 'Film.en.srt'
            english.write_text('1\n00:00:01,000 --> 00:00:02,000\nEnglish', encoding='utf-8')
            french = Path(directory) / 'Film.fr.vtt'
            french.write_text('WEBVTT\n\n00:01.000 --> 00:02.000\nFrançais', encoding='utf-16')
            (Path(directory) / 'Film sequel.srt').write_text('ignored')
            self.assertEqual(readSubtitles(french)[0][2], 'Français')
            slot = ClipSlot()
            slot.subtitles.load(str(movie))
            self.assertEqual(len(slot.subtitles.tracks), 2)
            slot.subtitles.enabled = True
            slot.subtitles.select(str(french))
            slot._onPlaybackPosition(1500)
            self.assertEqual(slot.subtitles.label.text(), 'Français')
            slot.subtitles.load(str(Path(directory) / 'Other.mkv'))
            self.assertEqual(slot.subtitles.cues, [])
            self.assertTrue(slot.subtitles.label.isHidden())
            slot.stop()

    def test_enabled_preference_restores_without_changing_fonts(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = QtWidgets.QWidget()
            parent.settings = QtCore.QSettings(str(Path(directory) / 'settings.ini'), QtCore.QSettings.IniFormat)
            tv = RetroChannelWidget(parent)
            sizes = dict(tv.sectionFontScales)
            self.assertIsNone(tv.subtitleButton.menu())
            tv.setSubtitlesEnabled(False)
            tv.subtitleButton.click()
            self.assertTrue(tv.subtitlesEnabled)
            self.assertTrue(tv.subtitleButton.isChecked())
            self.assertEqual(tv.subtitleButton.text(), 'SUBTITLES')
            tv.subtitleButton.click()
            self.assertFalse(tv.subtitlesEnabled)
            self.assertFalse(tv.subtitleButton.isChecked())
            self.assertEqual(tv.subtitleButton.text(), 'SUBTITLES')
            tv.subtitleButton.click()
            self.assertEqual(tv.sectionFontScales, sizes)
            restored = RetroChannelWidget(parent)
            self.assertTrue(restored.subtitlesEnabled)
            tv.close()
            restored.close()

    def test_deleted_video_ignores_late_position_and_cleanup(self):
        video = QVideoWidget()
        controller = SubtitleController(video)
        video.deleteLater()
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
        controller.updatePosition(1000)
        controller.clear()

    def test_captions_are_drawn_in_the_video_viewport(self):
        video = QVideoWidget()
        video.resize(640, 360)
        video.show()
        self.app.processEvents()
        controller = SubtitleController(video)
        controller.enabled = True
        try:
            controller._setCues([(0, 5000, 'Visible caption')])
            controller.updatePosition(1000)
            self.assertFalse(controller.label.isWindow())
            self.assertIs(controller.label.parentWidget(), video.viewport())
            rendered = video.grab().toImage()
            rect = controller.label.geometry()
            white = sum(1 for y in range(rect.top(), rect.bottom())
                        for x in range(rect.left(), rect.right())
                        if min(rendered.pixelColor(x, y).getRgb()[:3]) > 200)
            self.assertGreater(white, 50, 'Caption glyphs must be visible in the rendered video view')
            controller.setEnabled(False)
            hidden = video.grab().toImage()
            self.assertEqual(sum(1 for y in range(rect.top(), rect.bottom())
                                 for x in range(rect.left(), rect.right())
                                 if min(hidden.pixelColor(x, y).getRgb()[:3]) > 200), 0)
        finally:
            controller.clear()
            video.close()

    @unittest.skipUnless(mediaTool('ffmpeg') and mediaTool('ffprobe'), 'FFmpeg tools unavailable')
    def test_real_embedded_text_track_discovery_extraction_and_seek(self):
        with tempfile.TemporaryDirectory() as directory:
            subtitle = Path(directory) / 'input.srt'
            subtitle.write_text('1\n00:00:00,500 --> 00:00:01,500\nEmbedded caption', encoding='utf-8')
            movie = Path(directory) / 'movie.mkv'
            subprocess.run([mediaTool('ffmpeg'), '-v', 'error', '-f', 'lavfi', '-i', 'color=c=blue:s=320x180:d=2',
                            '-i', str(subtitle), '-map', '0:v', '-map', '1:s', '-c:v', 'mpeg4', '-c:s', 'srt',
                            '-metadata:s:s:0', 'language=eng', '-y', str(movie)], check=True,
                           capture_output=True, creationflags=0x08000000 if os.name == 'nt' else 0)
            slot = ClipSlot()
            video = slot.videoWidget
            video.resize(640, 360)
            video.show()
            controller = slot.subtitles
            errors = []
            controller.error.connect(errors.append)
            controller.enabled = True
            try:
                slot.load(str(movie), autoplay=True, seekFraction=0)
                deadline = time.monotonic() + 10
                while (not controller.cues or not slot._hasPlayingFrame
                       or video.grab().toImage().pixelColor(100, 100).blue() < 100) and time.monotonic() < deadline:
                    QtTest.QTest.qWait(20)
                self.assertEqual(errors, [])
                self.assertEqual(len(controller.tracks), 1)
                self.assertTrue(controller.selected.startswith('embedded:'))
                controller.updatePosition(1000)
                self.assertEqual(controller.label.text(), 'Embedded caption')
                rendered = video.grab().toImage()
                picture = rendered.pixelColor(100, 100)
                self.assertGreater(picture.blue(), 100)
                self.assertLess(picture.red(), 40)
                rect = controller.label.geometry()
                emptyBackground = rendered.pixelColor(rect.left() + 2, rect.center().y())
                self.assertGreater(emptyBackground.blue(), 200, 'Caption box must leave the blue video unchanged')
                self.assertLess(emptyBackground.red(), 40)
                self.assertGreater(sum(1 for y in range(rect.top(), rect.bottom())
                                       for x in range(rect.left(), rect.right())
                                       if min(rendered.pixelColor(x, y).getRgb()[:3]) > 200), 50)
                controller.updatePosition(1700)
                self.assertTrue(controller.label.isHidden())
            finally:
                controller.clear()
                slot.stop()
                video.close()
