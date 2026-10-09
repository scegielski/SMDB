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
            tv.setDlssEnabled(True)
            self.assertEqual(tv.dlssButton.text(), 'DLSS WAITING')
            self.assertTrue(tv.dlssButton.isChecked())
            tv._dlssProcessor.frameCount = 2
            tv._dlssFrameReady()
            self.assertEqual(tv.dlssButton.text(), 'DLSS ON')
            self.assertIn('2 frames processed', tv.dlssButton.toolTip())
            self.assertEqual(tv._videoOsdStatus['dlss'][0], 'DLSS 5 ACTIVE')
            tv._dlssFailed('Test error')
            self.assertFalse(tv.dlssButton.isChecked())
            self.assertEqual(tv.dlssButton.text(), 'DLSS FAILED')
            self.assertIn('Test error', tv.dlssButton.toolTip())
            self.assertTrue(tv._dlssProcessor.logPath.is_file())
        finally:
            tv.close()

    def test_prewarm_keeps_normal_video_and_reuses_worker_on_toggle(self):
        processor = DlssProcessor()
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
        finally:
            processor.stop(); surface.stop(); view.close()

    def test_native_pipeline_returns_enhanced_frame_and_toggle_restores_original(self):
        processor = DlssProcessor()
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
            view.setDlssEnabled(False, processor)
            self.assertFalse(view._enhancedItem.isVisible())
        finally:
            processor.stop(); surface.stop(); view.close()


if __name__ == '__main__':
    unittest.main()
