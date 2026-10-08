import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import unittest
from types import SimpleNamespace
from PyQt5 import QtGui, QtWidgets
from smdb.RetroChannelWidget import StandByScreen

class StandbyScreenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_rendering_is_independent_of_inherited_and_explicit_fonts(self):
        parent = QtWidgets.QWidget()
        screen = StandByScreen(parent)
        screen.resize(640, 360)
        screen._elapsed = SimpleNamespace(isValid=lambda: True, elapsed=lambda: 1250)
        original = screen.grab().toImage()
        for size in (4, 12, 48, 96, 4):
            parent.setFont(QtGui.QFont('Courier New', size))
            screen.setFont(QtGui.QFont('Times New Roman', size))
            self.assertEqual(screen.grab().toImage(), original)
        self.assertEqual(original.pixelColor(10, 10).name(), '#ebebeb')
        self.assertEqual(original.pixelColor(200, 10).name(), '#00ebeb')
        for width, height in ((320, 180), (640, 360), (1920, 1080)):
            font = screen._titleFont(width, height)
            self.assertLessEqual(QtGui.QFontMetrics(font).horizontalAdvance('PLEASE STAND BY'), width * .9)
        parent.close()

    def test_countdown_repeats_and_animation_only_runs_when_visible(self):
        screen = StandByScreen()
        screen.show()
        self.app.processEvents()
        self.assertTrue(screen._animationTimer.isActive())
        screen.hide()
        self.assertFalse(screen._animationTimer.isActive())
        for elapsed, number, fraction in ((0, 5, 0), (1250, 4, .25), (4999, 1, .999), (5000, 5, 0)):
            screen._elapsed = SimpleNamespace(isValid=lambda: True, elapsed=lambda: elapsed)
            self.assertEqual(screen._leaderPosition(), (number, fraction))
        screen.close()

if __name__ == '__main__':
    unittest.main()
