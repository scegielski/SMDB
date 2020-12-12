import sys
from PyQt5.QtWidgets import QApplication
from .mainwindow import MyWindow

def main():
    app = QApplication(sys.argv)
    MyWindow()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()