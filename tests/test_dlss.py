import os
from pathlib import Path
import time
import unittest
from PyQt5 import QtCore, QtGui, QtWidgets, QtTest
from PyQt5.QtMultimedia import QVideoFrame, QVideoSurfaceFormat
from smdb.VideoView import VideoView
from smdb.Dlss import DlssProcessor


class DlssTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_original_surface_still_presents_rgb_and_seek_hides_stale_enhancement(self):
        view = VideoView()
        view.resize(200, 200); view.show(); self.app.processEvents()
        image = QtGui.QImage(2, 2, QtGui.QImage.Format_RGB32)
        image.fill(QtGui.QColor('red'))
        surface = view.videoSurface()
        try:
            self.assertTrue(surface.start(QVideoSurfaceFormat(image.size(), QVideoFrame.Format_RGB32)))
            self.assertTrue(surface.present(QVideoFrame(image)))
            self.app.processEvents()
            self.assertEqual(view.viewport().grab().toImage().pixelColor(100, 100), QtGui.QColor('red'))
            view.showDlssFrame(image)
            old = view._dlssGeneration
            view.resetDlssFrame()
            self.assertFalse(view._enhancedItem.isVisible())
            self.assertGreater(view._dlssGeneration, old)
        finally:
            surface.stop(); view.close()

    def test_remote_reports_waiting_active_and_failure(self):
        from smdb.RetroChannelWidget import RetroChannelWidget
        tv = RetroChannelWidget()
        try:
            self.assertTrue(tv.dlssSliders.isHidden())
            tv.dlssToneSlider.setValue(65)
            tv.dlssStructureSlider.setValue(150)
            self.assertEqual(tv._dlssProcessor.tonePercent, 65)
            self.assertEqual(tv._dlssProcessor.structurePercent, 150)
            self.assertEqual(tv.dlssToneLabel.text(), 'DLSS TONE 65%')
            self.assertEqual(tv.dlssStructureLabel.text(), 'DLSS STRUCTURE 150%')
            self.assertEqual(tv.dlssModeButton.text(), 'Natural')
            for name, style in (('Cinematic', 2), ('Default', 0), ('Natural', 1)):
                QtTest.QTest.mouseClick(tv.dlssModeButton, QtCore.Qt.LeftButton)
                self.assertEqual(tv.dlssModeButton.text(), name)
                self.assertEqual(tv._dlssProcessor.style, style)
                self.assertEqual(tv._videoOsdStatus['dlss-mode'][0], 'DLSS 5 ' + name.upper())
            tv.setDlssEnabled(True)
            self.assertFalse(tv.dlssSliders.isHidden())
            tv.setDlssEnabled(False)
            self.assertTrue(tv.dlssSliders.isHidden())
            tv.setDlssEnabled(True)
            self.assertEqual(tv.dlssToneSlider.value(), 65)
            self.assertEqual(tv.dlssButton.text(), 'DLSS')
            self.assertTrue(tv.dlssButton.isChecked())
            tv._dlssProcessor.frameCount = 2
            tv._dlssFrameReady()
            self.assertEqual(tv.dlssButton.text(), 'DLSS')
            self.assertIn('2 frames processed', tv.dlssButton.toolTip())
            self.assertEqual(tv._videoOsdStatus['dlss'][0], 'DLSS 5 ACTIVE')
            tv._dlssFailed('Test error')
            self.assertTrue(tv.dlssSliders.isHidden())
            self.assertFalse(tv.dlssButton.isChecked())
            self.assertEqual(tv.dlssButton.text(), 'DLSS')
            self.assertIn('Test error', tv.dlssButton.toolTip())
            self.assertTrue(tv._dlssProcessor.logPath.is_file())
        finally:
            tv.close()

    def test_prewarm_keeps_normal_video_and_reuses_worker_on_toggle(self):
        processor = DlssProcessor()
        processor.useGpuPresentation = False
        if os.name != 'nt' or not processor.available():
            self.skipTest('Native worker and local DLSS runtime required')
        view = VideoView()
        image = QtGui.QImage(640, 360, QtGui.QImage.Format_RGB32)
        image.fill(QtGui.QColor('blue'))
        surface = view.videoSurface()
        failures = []
        processor.failed.connect(failures.append)
        def waitFor(condition):
            deadline = time.monotonic() + 15
            while not condition() and not failures and time.monotonic() < deadline:
                QtTest.QTest.qWait(10)
            self.assertFalse(failures, processor.log)
            self.assertTrue(condition(), processor.log)
        try:
            view.setDlssEnabled(False, processor, prewarm=True)
            self.assertTrue(surface.start(QVideoSurfaceFormat(image.size(), QVideoFrame.Format_RGB32)))
            self.assertTrue(surface.present(QVideoFrame(image)))
            waitFor(lambda: processor._warmSize == (640, 360))
            pid = processor.process.processId()
            self.assertEqual(processor.frameCount, 0)
            self.assertFalse(view._enhancedItem.isVisible())
            start = time.monotonic()
            view.setDlssEnabled(True, processor, prewarm=True)
            waitFor(lambda: processor.frameCount == 1)
            print('Warmed toggle first-frame latency:', round(time.monotonic() - start, 3), 'seconds')
            self.assertEqual(processor.process.processId(), pid)
            view.setDlssEnabled(False, processor, prewarm=True)
            self.assertFalse(view._enhancedItem.isVisible())
            self.assertFalse(processor.needsWarm(640, 360))
            view.setDlssEnabled(True, processor, prewarm=True)
            waitFor(lambda: processor.frameCount == 2)
            self.assertEqual(processor.process.processId(), pid)
            self.assertEqual(processor.log.count('feature created'), 1)
            view.setDlssEnabled(False, processor, prewarm=True)
            smaller = image.scaled(320, 180)
            surface.stop()
            self.assertTrue(surface.start(QVideoSurfaceFormat(smaller.size(), QVideoFrame.Format_RGB32)))
            surface.present(QVideoFrame(smaller))
            waitFor(lambda: processor._warmSize == (320, 180))
            self.assertEqual(processor.process.processId(), pid)
            view.setDlssEnabled(True, processor, prewarm=True)
            waitFor(lambda: processor.frameCount == 3)
            self.assertEqual(processor.log.count('feature created'), 2)
            processor.intensityPercent = 0
            view._frameSurface.submitFrame()
            waitFor(lambda: processor.frameCount == 4)
            self.assertEqual(view._enhancedItem.pixmap().toImage().pixelColor(100, 100), QtGui.QColor('blue'))
            processor.intensityPercent = 200
            view._frameSurface.submitFrame()
            waitFor(lambda: processor.frameCount == 5)
        finally:
            processor.stop(); surface.stop(); view.close()

    def test_unavailable_gpu_compositor_falls_back_without_disabling_dlss(self):
        from unittest.mock import patch
        processor = DlssProcessor()
        if os.name != 'nt' or not processor.available():
            self.skipTest('Native Windows GPU runtime required')
        view = VideoView(); view.resize(200,200); view.show()
        if not view._gpuView.supported():
            view.close(); self.skipTest('GPU helper required')
        image = QtGui.QImage(320,180,QtGui.QImage.Format_RGB32)
        image.fill(QtGui.QColor('blue'))
        surface=view.videoSurface()
        failures=[];processor.failed.connect(failures.append)
        try:
            surface.start(QVideoSurfaceFormat(image.size(),QVideoFrame.Format_RGB32))
            surface.present(QVideoFrame(image))
            with patch.object(view,'showDlssGpuFrame',side_effect=RuntimeError('Unsupported compositor')):
                view.setDlssEnabled(True,processor)
                deadline=time.monotonic()+15
                while not processor.frameCount and not failures and time.monotonic()<deadline:
                    QtTest.QTest.qWait(10)
            self.assertFalse(failures,processor.log)
            self.assertGreater(processor.frameCount,0)
            self.assertFalse(processor.useGpuPresentation)
            self.assertTrue(view.dlssEnabled)
            self.assertTrue(view._enhancedItem.isVisible())
        finally:
            processor.stop();surface.stop();view.close()

    def test_gpu_presentation_preserves_orientation_captions_and_original_on_toggle(self):
        from smdb.Subtitles import SubtitleController
        processor = DlssProcessor()
        if os.name != 'nt' or not processor.available():
            self.skipTest('Native Windows GPU runtime required')
        view = VideoView(); view.resize(640, 360); view.show()
        if not view._gpuView.supported():
            view.close(); self.skipTest('GPU presentation helper required')
        processor.intensityPercent = 0
        image = QtGui.QImage(640, 360, QtGui.QImage.Format_RGB32)
        image.fill(QtGui.QColor('blue'))
        painter = QtGui.QPainter(image)
        painter.fillRect(0, 0, 640, 90, QtGui.QColor('red')); painter.end()
        surface = view.videoSurface()
        failures = []; processor.failed.connect(failures.append)
        def waitFor(condition):
            deadline = time.monotonic()+15
            while not condition() and not failures and time.monotonic()<deadline:
                QtTest.QTest.qWait(10)
            self.assertFalse(failures, processor.log)
            self.assertTrue(condition(), processor.log)
        try:
            surface.start(QVideoSurfaceFormat(image.size(), QVideoFrame.Format_RGB32))
            surface.present(QVideoFrame(image))
            view.setDlssEnabled(True, processor)
            waitFor(lambda: processor.frameCount == 1)
            self.assertTrue(view._gpuView.isVisible())
            self.assertFalse(view._enhancedItem.isVisible())
            frame = view._gpuView.grabFramebuffer()
            self.assertEqual(frame.pixelColor(320, 30), QtGui.QColor('red'))
            self.assertEqual(frame.pixelColor(320, 180), QtGui.QColor('blue'))
            captions = SubtitleController(view); captions.enabled = True
            captions._setCues([(0, 5000, 'GPU caption')]); captions.updatePosition(1000)
            view.osd.display('volume', 70); self.app.processEvents()
            rendered = view.grab().toImage()
            self.assertGreater(sum(rendered.pixelColor(x, y).red()>200 and
                                   rendered.pixelColor(x, y).green()>200
                                   for x in range(190,450) for y in range(305,335)), 50)
            view.showFullScreen(); self.app.processEvents()
            view._frameSurface.submitFrame()
            waitFor(lambda: processor.frameCount == 2)
            self.assertIsNone(view._gpuView.error)
            view.showNormal(); view.resize(640,360); self.app.processEvents()
            # Resolution/texture changes must not reuse the old registration.
            smaller = image.scaled(320, 180)
            surface.stop(); surface.start(QVideoSurfaceFormat(smaller.size(), QVideoFrame.Format_RGB32))
            surface.present(QVideoFrame(smaller))
            waitFor(lambda: processor.frameCount == 3)
            self.assertEqual(processor._warmSize, (320,180))
            # All styles must evaluate while paused, without restarting the worker.
            pid = processor.process.processId()
            for count, style in enumerate((0, 2, 1), start=4):
                processor.style = style
                view._frameSurface.submitFrame()
                waitFor(lambda: processor.frameCount == count)
                self.assertEqual(processor.process.processId(), pid)
                self.assertIsNone(view._gpuView.error)
            self.assertIn('NR style changed: 0', processor.log)
            self.assertIn('NR style changed: 2', processor.log)
            self.assertIn('NR style changed: 1', processor.log)
            for count, (tone, structure) in enumerate(((0, 200), (200, 0), (100, 100)), start=7):
                processor.tonePercent = tone
                processor.structurePercent = structure
                view._frameSurface.submitFrame()
                waitFor(lambda: processor.frameCount == count)
                self.assertEqual(processor.process.processId(), pid)
                self.assertIsNone(view._gpuView.error)
            self.assertIn('NR tuning: tone=0 structure=200', processor.log)
            self.assertIn('NR tuning: tone=200 structure=0', processor.log)
            view.setDlssEnabled(False, processor)
            self.assertFalse(view._gpuView.isVisible())
            self.app.processEvents()
            self.assertEqual(view.viewport().grab().toImage().pixelColor(320, 180), QtGui.QColor('blue'))
        finally:
            processor.stop(); surface.stop(); view.close()

    def test_native_pipeline_returns_enhanced_frame_and_toggle_restores_original(self):
        processor = DlssProcessor()
        processor.useGpuPresentation = False
        if os.name != 'nt' or not processor.available():
            self.skipTest('Native worker and local DLSS runtime required')
        view = VideoView(); view.resize(640, 360); view.show()
        image = QtGui.QImage(str(Path(__file__).parents[1] / 'smdb/assets/promos/promo1.png'))
        image = image.scaled(640, 360).convertToFormat(QtGui.QImage.Format_RGB32)
        surface = view.videoSurface()
        failures = []; frames = []
        processor.failed.connect(failures.append)
        processor.frameProcessed.connect(lambda: frames.append(True))
        try:
            self.assertTrue(surface.start(QVideoSurfaceFormat(image.size(), QVideoFrame.Format_RGB32)))
            self.assertTrue(surface.present(QVideoFrame(image)))
            view.setDlssEnabled(True, processor)
            start = time.monotonic()
            while not frames and not failures and time.monotonic() - start < 15:
                QtTest.QTest.qWait(50)
            self.assertFalse(failures, processor.log)
            self.assertTrue(frames, processor.log)
            self.assertTrue(view._enhancedItem.isVisible())
            self.assertIn('feature created', processor.log)
            # During an in-flight evaluation, decode newer frames without copying
            # each one; completion must process the most recent decoded frame.
            frame = QVideoFrame(image); frame.setStartTime(100000)
            surface.present(frame)
            frame = QVideoFrame(image); frame.setStartTime(200000)
            surface.present(frame)
            frame = QVideoFrame(image); frame.setStartTime(300000)
            surface.present(frame)
            deadline = time.monotonic() + 15
            while processor._lastTimestamp != 300000 and not failures and time.monotonic() < deadline:
                QtTest.QTest.qWait(10)
            self.assertFalse(failures, processor.log)
            self.assertEqual(processor._lastTimestamp, 300000)
            view.setDlssEnabled(False, processor)
            self.assertFalse(view._enhancedItem.isVisible())
        finally:
            processor.stop(); surface.stop(); view.close()


if __name__ == '__main__':
    unittest.main()
