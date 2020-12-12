import sys
from PyQt5 import QtCore
from PyQt5.QtWidgets import QApplication
from .mainwindow import MyWindow

def main():
    app = QApplication(sys.argv)
    win = MyWindow()
    win.show()
    QtCore.QCoreApplication.processEvents()
    win.refresh()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()