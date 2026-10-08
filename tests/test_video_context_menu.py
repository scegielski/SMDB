import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from PyQt5 import QtCore, QtGui, QtWidgets
from smdb.MainWindow import MainWindow
from smdb.MovieFilterProxyModel import MovieFilterProxyModel
from smdb.RetroChannelWidget import RetroChannelWidget, ClipSlot


class VideoContextMenuTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_filtered_video_target_and_database_selection_restored(self):
        model = QtGui.QStandardItemModel()
        for title in ('Database selection', 'Playing film', 'Other film'):
            model.appendRow(QtGui.QStandardItem(title))
        proxy = MovieFilterProxyModel()
        proxy.setSourceModel(model)
        proxy.setFilterFixedString('Database')
        table = QtWidgets.QTableView()
        table.setModel(proxy)
        table.selectRow(0)
        def action():
            selected = table.selectionModel().selectedRows()
            self.assertEqual([proxy.mapToSource(i).row() for i in selected], [1])
            self.assertEqual(proxy.filterRegExp().pattern(), 'Database')
        window = SimpleNamespace(moviesTableModel=model, moviesTableProxyModel=proxy,
                                 moviesTableView=table)
        MainWindow._runMovieContextAction(window, 1, action)
        self.assertEqual(proxy.rowCount(), 1)
        self.assertEqual([proxy.mapToSource(i).row() for i in table.selectionModel().selectedRows()], [0])
        self.assertFalse(proxy._contextMovieIndex.isValid())
        table.close()

    def test_opening_video_menu_does_not_select_or_load_database_movie(self):
        window = SimpleNamespace(moviesTableRightMenuShow=Mock())
        MainWindow.movieVideoRightMenuShow(window, 7, QtCore.QPoint(12, 34))
        window.moviesTableRightMenuShow.assert_called_once_with(None, QtCore.QPoint(12, 34), sourceRow=7)

    def test_video_menu_defers_target_selection_until_action_trigger(self):
        class Window(QtWidgets.QWidget):
            def __getattr__(self, name):
                callback = Mock()
                setattr(self, name, callback)
                return callback
        window = Window()
        model = QtGui.QStandardItemModel(2, 1)
        proxy = MovieFilterProxyModel()
        proxy.setSourceModel(model)
        table = QtWidgets.QTableView(window)
        table.setModel(proxy)
        table.selectRow(0)
        window.moviesTableView = table
        window.moviesTableProxyModel = proxy
        window.moviesTableModel = model
        window.collections = []
        window._runMovieContextAction = lambda row, callback: MainWindow._runMovieContextAction(window, row, callback)
        seen = []
        window.openMovieFolder = lambda: seen.append(proxy.mapToSource(table.selectionModel().selectedRows()[0]).row())
        def execute(menu, point):
            self.assertEqual(table.selectionModel().selectedRows()[0].row(), 0)
            self.assertFalse(proxy._contextMovieIndex.isValid())
            next(action for action in menu.actions() if action.text() == 'Open Folder').trigger()
            return None
        with patch.object(QtWidgets.QMenu, 'exec_', new=execute):
            MainWindow.moviesTableRightMenuShow(window, None, QtCore.QPoint(), sourceRow=1)
        self.assertEqual(seen, [1])
        window.clickedTable.assert_not_called()
        self.assertEqual(table.selectionModel().selectedRows()[0].row(), 0)
        window.close()

    def test_selection_restored_when_menu_raises(self):
        model = QtGui.QStandardItemModel(2, 1)
        proxy = MovieFilterProxyModel()
        proxy.setSourceModel(model)
        table = QtWidgets.QTableView()
        table.setModel(proxy)
        table.selectRow(0)
        window = SimpleNamespace(moviesTableModel=model, moviesTableProxyModel=proxy,
            moviesTableView=table, moviesTableRightMenuShow=Mock(side_effect=RuntimeError('test')))
        with self.assertRaises(RuntimeError):
            MainWindow._runMovieContextAction(window, 1, window.moviesTableRightMenuShow)
        self.assertEqual(table.selectionModel().selectedRows()[0].row(), 0)
        self.assertFalse(proxy._contextMovieIndex.isValid())
        table.close()

    def test_video_context_signal_targets_displayed_movie(self):
        parent = QtWidgets.QWidget()
        parent.movieVideoRightMenuShow = Mock()
        tv = RetroChannelWidget(parent)
        tv.standbyPollTimer.stop()
        slot = ClipSlot(tv)
        tv.guidePreviewSlot = slot
        slot.path = os.path.abspath('Playing.mp4')
        tv._videoPathCache = {7: slot.path, 8: os.path.abspath('Other.mp4')}
        event = QtGui.QContextMenuEvent(QtGui.QContextMenuEvent.Mouse, QtCore.QPoint(5, 6),
                                       slot.videoWidget.viewport().mapToGlobal(QtCore.QPoint(5, 6)))
        QtWidgets.QApplication.sendEvent(slot.videoWidget.viewport(), event)
        parent.movieVideoRightMenuShow.assert_called_once_with(7, slot.videoWidget.mapToGlobal(QtCore.QPoint(5, 6)))
        parent.movieVideoRightMenuShow.reset_mock()
        other = ClipSlot(tv)
        other.videoWidget.customContextMenuRequested.emit(QtCore.QPoint())
        parent.movieVideoRightMenuShow.assert_not_called()
        other.stop()
        slot.stop()
        tv.close()
        parent.close()

if __name__ == '__main__':
    unittest.main()
