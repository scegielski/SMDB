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
                    picture=video.osd.grab().toImage()
                    green=sum(1 for y in range(250,350) for x in range(640)
                        if picture.pixelColor(x,y).green()>200 and picture.pixelColor(x,y).red()<100)
                    self.assertGreater(green,100)
                    self.assertFalse(any(picture.pixelColor(x,y).green()>200 and picture.pixelColor(x,y).red()<100
                                         for y in range(0,180) for x in range(640)))
                    video.osd.updateValue('seek',(10,1700000031))
                    self.assertEqual(video.osd.items['seek'][1],13)
                    timer.return_value=13.1;video.osd._expire()
                    self.assertTrue(video.osd.isHidden())
            finally:video.close()
        finally:tv.engines.clear();tv.channels=[];tv.close()

    def test_info_button_position_details_and_loading_title(self):
        tv = RetroChannelWidget()
        model = Mock()
        model.getTitle.return_value = 'The Matrix'
        model.getYear.return_value = 1999
        model.getCoverPath.return_value = None
        model.getMovieData.return_value = {'director': ['Lana Wachowski', 'Lilly Wachowski'],
            'cast': ['Keanu Reeves', 'Laurence Fishburne', 'Carrie-Anne Moss'], 'plot': 'A programmer discovers a hidden reality.'}
        tv.mainWindow = SimpleNamespace(moviesTableModel=model)
        engine = SimpleNamespace(currentRow=4,currentTitle='The Matrix (1999)',
            isShowingComingUp=lambda:False,slotA=SimpleNamespace(videoWidget=Mock()),slotB=SimpleNamespace(videoWidget=Mock()))
        tv.channels=[{'genre':'Action'}]
        tv.engines={0:engine}
        try:
            layout=tv.channelUpButton.parentWidget().layout()
            self.assertEqual(layout.getItemPosition(layout.indexOf(tv.infoButton))[:2],(0,2))
            tv.infoButton.setEnabled(True)
            tv.infoButton.click()
            kind, value, seconds=engine.slotA.videoWidget.osd.display.call_args.args
            self.assertEqual((kind,seconds),('info',float('inf')))
            self.assertTrue(tv.infoButton.isChecked())
            tv.infoButton.click()
            self.assertFalse(tv.infoButton.isChecked())
            engine.slotA.videoWidget.osd.dismiss.assert_called_with('info')
            self.assertNotIn('info',tv._videoOsdStatus)
            self.assertEqual(value['title'],'The Matrix (1999)')
            self.assertIn('Keanu Reeves',value['actors'])
            self.assertIn('Wachowski',value['directors'])
            self.assertIn('programmer',value['synopsis'])
            self.assertEqual(tv._channelOsdPayload(0),(1,'Action','The Matrix (1999)'))
            engine.currentTitle=''
            self.assertIn('Loading',tv._channelOsdPayload(0)[2])
        finally:
            tv.engines.clear();tv.channels=[];tv.close()

    def test_info_card_wraps_at_bottom_until_dismissed(self):
        video=VideoView();video.resize(960,540);video.show();self.app.processEvents()
        try:
            with patch('smdb.VideoView.time.monotonic',return_value=10) as clock:
                video.osd.display('info',{'title':'The Matrix (1999)',
                    'directors':'Lana Wachowski, Lilly Wachowski',
                    'actors':'Keanu Reeves, Laurence Fishburne, Carrie-Anne Moss',
                    'synopsis':'A computer programmer discovers that the world he knows is a simulation and joins a rebellion against its controllers.'},float('inf'))
                picture=video.grab().toImage()
                if os.environ.get('SMTV_INFO_SCREENSHOT'):
                    picture.save(os.environ['SMTV_INFO_SCREENSHOT'])
                self.assertTrue(video.osd.testAttribute(QtCore.Qt.WA_TransparentForMouseEvents))
                self.assertEqual(picture.pixelColor(480,100).name(),'#000000')
                self.assertGreater(sum(1 for y in range(250,500) for x in range(40,900)
                    if picture.pixelColor(x,y).green()>200),100)
                clock.return_value=10000;video.osd._expire()
                self.assertFalse(video.osd.isHidden())
                video.osd.dismiss('info')
                self.assertTrue(video.osd.isHidden())
        finally:video.close()

    def test_info_with_channel_and_volume_survives_repaint_and_resize(self):
        video=VideoView();video.resize(960,540);video.show();self.app.processEvents()
        try:
            video.osd.display('info',{'title':'Example (1999)','directors':'Example Director',
                'actors':'Actor One, Actor Two','synopsis':'A brief synopsis that wraps around to the next line.'},float('inf'))
            video.osd.display('channel',(1,'Action','Example (1999)'))
            video.osd.display('volume',70)
            for width,height in ((960,540),(640,360),(1280,720)):
                video.resize(width,height);self.app.processEvents()
                self.assertFalse(video.grab().toImage().isNull())
                self.assertEqual(set(video.osd.items),{'info','channel','volume'})
            video.osd.dismiss('channel')
            video.osd.dismiss('volume')
            self.assertIn('info',video.osd.items)
            self.assertFalse(video.grab().toImage().isNull())
        finally:video.close()

    def test_channel_overlay_contains_title_and_refreshes_on_resolve(self):
        tv=RetroChannelWidget()
        engine=SimpleNamespace(currentTitle='The Matrix (1999)',channelNumber=1,genreName='Action',
            isShowingComingUp=lambda:False, slotA=SimpleNamespace(videoWidget=Mock()),slotB=SimpleNamespace(videoWidget=Mock()))
        tv.channels=[{'genre':'Action'}];tv.engines={0:engine}
        try:
            with patch.object(tv,'_warmSurroundingVideoPaths'),patch.object(tv,'_showBanner'):
                tv._onProgramChanged(0)
            engine.slotA.videoWidget.osd.display.assert_called_with('channel',(1,'Action','The Matrix (1999)'))
            tv._infoVisible=True
            with patch.object(tv,'_warmSurroundingVideoPaths'),patch.object(tv,'_showBanner'),patch.object(tv,'showProgramInfo') as refresh:
                tv._onProgramChanged(0)
                refresh.assert_called_once()
        finally:tv.engines.clear();tv.channels=[];tv.close()

if __name__=='__main__':unittest.main()
