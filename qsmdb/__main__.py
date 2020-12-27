import sys
from PyQt5.QtWidgets import QApplication
from PyQt5 import QtWidgets
from .mainwindow import MyWindow

def main():
    app = QApplication(sys.argv)
    app.setStyle(QtWidgets.QStyleFactory.create('Fusion'))
    MyWindow()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()