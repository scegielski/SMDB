import os
import sys
from pathlib import Path
from PyQt5.QtWidgets import QApplication
from PyQt5 import QtWidgets

MODULE_DIR = Path(__file__).resolve().parent
PACKAGE_PARENT = MODULE_DIR.parent
if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))

try:
    from .MainWindow import MainWindow
except ImportError:
    from smdb.MainWindow import MainWindow

def main():
    app = QApplication(sys.argv)
    app.setStyle(QtWidgets.QStyleFactory.create('Fusion'))
    MainWindow()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
