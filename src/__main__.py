import sys
from PyQt5.QtWidgets import QApplication
from PyQt5 import QtWidgets
from .MainWindow import MainWindow

def main():
    app = QApplication(sys.argv)
    app.setStyle(QtWidgets.QStyleFactory.create('Fusion'))
    MainWindow()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()