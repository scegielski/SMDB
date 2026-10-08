import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import unittest
from unittest.mock import Mock,patch
from PyQt5 import QtWidgets
from PyQt5.QtMultimedia import QMediaPlayer
from smdb.RetroChannelWidget import RetroChannelWidget,ChannelClock,ChannelEngine

class PauseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    def test_pause_and_now_layout(self):
        tv=RetroChannelWidget()
        try:
            layout=tv.sideControls.layout()
            grid=next(layout.itemAt(i).layout() for i in range(layout.count())
                if isinstance(layout.itemAt(i).layout(),QtWidgets.QGridLayout))
            self.assertEqual(grid.getItemPosition(grid.indexOf(tv.pauseButton))[:2],(0,1))
            self.assertEqual(grid.getItemPosition(grid.indexOf(tv.nowButton))[:2],(1,1))
        finally:tv.close()
    def test_pause_resume_keeps_position_and_pauses_all_channels(self):
        clock=ChannelClock([0],lambda row:100000)
        engine=ChannelEngine(1,'Action',clock,lambda row:None,str)
        engine.currentRow=0;engine.currentSlotIndex=0
        slot=engine.activeSlot;original=slot.player
        state=[QMediaPlayer.PlayingState]
        slot.player=Mock();slot.player.state.side_effect=lambda:state[0]
        slot.player.pause.side_effect=lambda:state.__setitem__(0,QMediaPlayer.PausedState)
        slot.player.play.side_effect=lambda:state.__setitem__(0,QMediaPlayer.PlayingState)
        slot.path='film.mp4';slot.duration=100000;slot._ready=True;slot._lastPlaybackPosition=42000
        tv=RetroChannelWidget()
        neighbor=ChannelEngine(2,'Other',ChannelClock([1],lambda row:100000),lambda row:None,str)
        neighbor.currentRow=1;neighbor.currentSlotIndex=0
        neighbor.activeSlot.path='other.mp4';neighbor.activeSlot.duration=100000;neighbor.activeSlot._ready=True
        neighbor.activeSlot._lastPlaybackPosition=17000
        tv.engines={0:engine,1:neighbor}
        tv.channels=[{'genre':'Action','clock':clock,'rows':[0]}];tv._updateEmptyState()
        try:
            with patch.object(engine,'_scheduleAdvance') as advance, patch.object(engine,'_maybeSchedulePrefetch'):
                tv.pauseButton.click()
                self.assertEqual(state[0],QMediaPlayer.PausedState)
                self.assertEqual(tv.pauseButton.accessibleName(),'Resume all channels')
                self.assertEqual(clock.resumeInfoForSlot(0)[2],42000)
                self.assertFalse(engine.advanceTimer.isActive())
                self.assertTrue(neighbor._paused)
                self.assertFalse(neighbor.activeSlot._autoplayAfterLoad)
                tv.pauseButton.click()
                self.assertEqual(state[0],QMediaPlayer.PlayingState)
                self.assertEqual(tv.pauseButton.accessibleName(),'Pause all channels')
                self.assertEqual(slot._lastPlaybackPosition,42000)
                advance.assert_called_once_with(58000)
                self.assertFalse(neighbor._paused)
                self.assertEqual(neighbor.clock.resumeInfoForSlot(0)[2],17000)
        finally:
            tv.engines.clear();slot.player=original;engine.shutdown();engine.container.close();neighbor.shutdown();neighbor.container.close();tv.close()

    def test_clock_freezes_and_new_load_remains_paused(self):
        with patch('smdb.RetroChannelWidget.time.monotonic',return_value=0) as now:
            clock=ChannelClock([0],lambda row:100000)
            now.return_value=2
            clock.setPaused(True)
            before=clock.whatsOnNow()
            now.return_value=32
            self.assertEqual(clock.whatsOnNow(),before)
            clock.setPaused(False)
            self.assertEqual(clock.whatsOnNow(),before)
            now.return_value=33
            self.assertGreater(clock.whatsOnNow()[3],before[3])
        engine=ChannelEngine(1,'Action',clock,lambda row:None,str)
        try:
            engine.setPaused(True)
            with patch.object(engine,'_startResolve',side_effect=lambda idx,attr,done:done(0,'film.mp4')), \
                    patch.object(engine.activeSlot,'load') as load:
                engine._tuneIn()
                self.assertFalse(load.call_args.kwargs['autoplay'])
                self.assertFalse(engine.advanceTimer.isActive())
        finally:engine.shutdown();engine.container.close()

    def test_resume_padding_rearms_channel_without_retuning_new_engine(self):
        engine=ChannelEngine(1,'Action',ChannelClock([0]),lambda row:None,str)
        try:
            with patch.object(engine,'_tuneIn') as tune:
                engine.setPaused(False)
                tune.assert_not_called()
                engine.setPaused(True)
                engine.setPaused(False)
                tune.assert_called_once()
        finally:engine.shutdown();engine.container.close()

    def test_paused_ready_channel_shows_video_without_playback_progress(self):
        engine=ChannelEngine(1,'Action',ChannelClock([0]),lambda row:None,str)
        slot=engine.activeSlot;original=slot.player
        slot.player=Mock();slot.player.state.return_value=QMediaPlayer.PausedState
        slot.path='film.mp4';slot.duration=100000;slot._ready=True
        slot._hasPlayingFrame=False
        engine._paused=True
        try:
            self.assertTrue(engine.isShowingStandby())
            engine._onSlotReady(slot)
            self.assertFalse(engine.isShowingStandby())
            self.assertIs(engine._stack.currentWidget(),slot.videoWidget)
            slot.player.play.assert_not_called()
        finally:slot.player=original;engine.shutdown();engine.container.close()

if __name__=='__main__':unittest.main()
