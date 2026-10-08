import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace
from PyQt5 import QtCore, QtGui, QtWidgets
from smdb.VideoView import VideoView
from smdb.RetroChannelWidget import RetroChannelWidget

class VideoOsdTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    def test_transparent_rendering_font_independence_and_timeout(self):
        video=VideoView();video.resize(640,360);video.show();self.app.processEvents()
        try:
            with patch('smdb.VideoView.time.monotonic',return_value=10) as clock:
                video.osd.display('channel',(3,'Adventure'))
                video.osd.display('volume',64)
                first=video.grab().toImage()
                self.assertGreater(sum(1 for y in range(first.height()) for x in range(first.width())
                    if first.pixelColor(x,y).green()>200 and first.pixelColor(x,y).red()<100),100)
                video.setFont(QtGui.QFont('Arial',72))
                self.assertEqual(video.grab().toImage(),first)
                self.assertEqual(first.pixelColor(320,180).name(),'#000000')
                self.assertTrue(video.osd.testAttribute(QtCore.Qt.WA_TransparentForMouseEvents))
                clock.return_value=12
                video.osd.display('volume',0)
                clock.return_value=13.1;video.osd._expire()
                self.assertEqual(set(video.osd.items),{'volume'})
                clock.return_value=15.1;video.osd._expire()
                self.assertTrue(video.osd.isHidden())
                self.assertFalse(video.osd.timer.isActive())
        finally: video.close()
    def test_volume_changes_only_update_current_video_buffers(self):
        tv=RetroChannelWidget();tv.standbyPollTimer.stop()
        engine=SimpleNamespace(slotA=SimpleNamespace(videoWidget=Mock()),slotB=SimpleNamespace(videoWidget=Mock()),setDesiredVolume=Mock())
        neighbor=Mock();tv.engines={0:engine,1:neighbor}
        try:
            tv.setVolume(64)
            engine.slotA.videoWidget.osd.display.assert_called_once_with('volume',64)
            engine.slotB.videoWidget.osd.display.assert_called_once_with('volume',64)
            neighbor.setDesiredVolume.assert_not_called()
            tv.setVolume(64)
            self.assertEqual(engine.slotA.videoWidget.osd.display.call_count,1)
            tv.toggleMute()
            engine.slotA.videoWidget.osd.display.assert_called_with('volume',0)
        finally:
            tv.engines.clear();tv.close()

    def test_seek_buttons_show_updated_broadcast_time_and_expire(self):
        tv=RetroChannelWidget()
        slot=SimpleNamespace(duration=100000,_lastPlaybackPosition=20000)
        clock=Mock();clock.publishedSlotTimes.return_value=(1700000000,1700000100)
        engine=SimpleNamespace(activeSlot=slot,currentSlotIndex=0,clock=clock,
            slotA=SimpleNamespace(videoWidget=Mock()),slotB=SimpleNamespace(videoWidget=Mock()))
        def seek(offset,beginning):
            slot._lastPlaybackPosition+=offset
            return True
        engine.seekCurrentFilm=seek
        tv.engines={0:engine}
        tv.channels=[{'genre':'Test','clock':clock}]
        tv._updateEmptyState()
        try:
            tv.forwardTenButton.click()
            engine.slotA.videoWidget.osd.display.assert_called_with('seek',(10,1700000030.0))
            tv.backTenButton.click()
            engine.slotB.videoWidget.osd.display.assert_called_with('seek',(-10,1700000020.0))
            video=VideoView();video.resize(640,360);video.show();self.app.processEvents()
            try:
                with patch('smdb.VideoView.time.monotonic',return_value=10) as timer:
                    video.osd.display('seek',(10,1700000030))
                    picture=video.grab().toImage()
                    green=sum(1 for y in range(100,200) for x in range(640)
                        if picture.pixelColor(x,y).green()>200 and picture.pixelColor(x,y).red()<100)
                    self.assertGreater(green,100)
                    video.osd.updateValue('seek',(10,1700000031))
                    self.assertEqual(video.osd.items['seek'][1],13)
                    timer.return_value=13.1;video.osd._expire()
                    self.assertTrue(video.osd.isHidden())
            finally:video.close()
        finally:tv.engines.clear();tv.channels=[];tv.close()

if __name__=='__main__':unittest.main()
