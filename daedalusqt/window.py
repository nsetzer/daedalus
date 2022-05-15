#! python38 $this build
import os, sys
import time
import argparse
import json
#<script type="text/javascript" src="https://getfirebug.com/firebug-lite.js"></script>


sys.path.insert(0, "..")

from daedalus.__main__ import BuildCLI
from daedalus.webview import DaedalusWebView

# https://doc.qt.io/qt-5/qwebengineview.html
# https://myprogrammingnotes.com/communication-c-javascript-qt-webengine.html
# C:\Qt\Examples\Qt-5.12.0\webchannel\standalone

from PyQt5.QtCore import *
# this is required so that the frozen executable
# can find `platforms/qwindows.dll`
if hasattr(sys, "_MEIPASS"):
    QCoreApplication.addLibraryPath(sys._MEIPASS)
    QCoreApplication.addLibraryPath(os.path.join(sys._MEIPASS, "qt5_plugins"))
from PyQt5.QtWebEngineWidgets import *
from PyQt5.QtWidgets import *
from PyQt5.QtWebChannel import *
from PyQt5.QtGui import *
from sip import SIP_VERSION_STR, delete as sip_delete


class Core(QObject):
    """
    note: the event loop needs to be running before signals can be emitted
    """

    # send data to the webpage
    pyCallMe = pyqtSignal(str)

    def __init__(self, parent=None):
        super(Core, self).__init__(parent)

    # receive data from the webpage
    @pyqtSlot(QVariant)
    def jsCallMe(self, arg):
        print("called from js", arg)

def build():

    args = lambda: None
    args.minify = False
    args.onefile = False
    args.platform = "qt"
    args.index_js = "./template.js"
    args.out = "./build"
    args.static = "./static"
    args.paths = None
    args.env = []

    cli = BuildCLI()
    cli.execute(args)

    qt_path_output = os.path.join( args.out, "static", "qwebchannel.js")
    jsFileInfo = QFileInfo(qt_path_output);
    if not jsFileInfo.exists():
        QFile.copy(":/qtwebchannel/qwebchannel.js", jsFileInfo.absoluteFilePath());


class DemoMainWindow(QMainWindow):
    def __init__(self):
        super(DemoMainWindow, self).__init__()

        self.webview = DaedalusWebView("./build/index.html")
        self.setCentralWidget(self.webview)

        self.core1 = Core()
        self.webview.registerObject("core1", self.core1)

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key_F5:

            build()

            self.webview.reload()

        if event.key() == Qt.Key_F4:

            print("emit")
            self.core1.pyCallMe.emit(json.dumps({"text": "update"}))
        if event.key() == Qt.Key_F3:

            self.webview.runJavaScript("window.channel.objects.core1.jsCallMe(123)")


def main():

    print(QT_VERSION_STR)

    os.environ['QTWEBENGINE_REMOTE_DEBUGGING'] = '1234'

    build()

    app = QApplication(sys.argv)
    app.setApplicationName("Daedalus")

    app.setQuitOnLastWindowClosed(True)

    window = DemoMainWindow()
    window.show()

    sys.exit(app.exec_())


if __name__ == '__main__':
    main()