
import os
import logging

try:
    from PyQt6.QtCore import QUrl, QObject, pyqtSignal, QFile
    from PyQt6.QtWebEngineCore import QWebEngineUrlRequestInterceptor, QWebEngineUrlSchemeHandler,  QWebEngineSettings, QWebEngineProfile, QWebEnginePage
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    from PyQt6.QtWidgets import QWidget, QVBoxLayout
    from PyQt6.QtWebChannel import QWebChannel

    def export_webchannel_js(path):
        """ writes a required file to the given path

        QWebChannel.js is required for interop between js and python when using Qt
        """
        QFile.copy(":/qtwebchannel/qwebchannel.js", path)

    class _Handler(QWebEngineUrlSchemeHandler):
        # https://doc.qt.io/qt-6.2/qwebengineurlschemehandler.html
        def __init__(self):
            super(_Handler, self).__init__()

        def requestStarted(self, request):
            print(request)
            super().requestStarted(request)

    class _Intercept(QWebEngineUrlRequestInterceptor):
        def __init__(self, view):
            super(_Intercept, self).__init__()
            self.view = view

        def interceptRequest(self, info):
            # https://doc.qt.io/qt-6/qwebengineurlrequestinfo.html
            # rewrite relative urls to be the correct path
            return self.view.interceptRequest(info)

    class Page(QWebEnginePage):

        consoleLogMessage = pyqtSignal(int, str, int, str) # level, message, lineno, sourceId

        levels = {
            QWebEnginePage.JavaScriptConsoleMessageLevel.InfoMessageLevel: logging.INFO,
            QWebEnginePage.JavaScriptConsoleMessageLevel.WarningMessageLevel: logging.WARN,
            QWebEnginePage.JavaScriptConsoleMessageLevel.ErrorMessageLevel: logging.ERROR,
        }
        def __init__(self, profile=None, parent=None):
            super(Page, self).__init__(profile, parent)

        def javaScriptConsoleMessage(self, level, message, lineno, sourceId):
            self.consoleLogMessage.emit(Page.levels[level], message, lineno, sourceId)

    class DaedalusWebView(QWidget):
        consoleLogMessage = pyqtSignal(int, str, int, str) # level, message, lineno, sourceId

        def __init__(self, html_path):
            super(DaedalusWebView, self).__init__()

            if QWebEngineView is None:
                raise RuntimeError("qt6 unavailable")

            # TODO: this should use the builder api to all fast rebuilds
            #       and support pre-built html
            self.url = QUrl.fromLocalFile(os.path.abspath(html_path))

            # https://doc.qt.io/qt-6/qwebengineurlrequestinterceptor.html

            #settings = QWebEngineSettings.defaultSettings()
            #settings.setAttribute(QWebEngineSettings.LocalContentCanAccessRemoteUrls, True)

            # https://doc-snapshots.qt.io/qt6-dev/qwebengineview.html
            self.engine = QWebEngineView(self)
            self.layout = QVBoxLayout(self)
            self.layout.setContentsMargins(0,0,0,0)
            self.layout.addWidget(self.engine)

            # "storage" here is the name of the profile
            # only one application can be running using the same profile at a time
            self.profile =  QWebEngineProfile("daedalus", self.engine)
            self.page = Page(self.profile, self.engine)
            self.page.consoleLogMessage.connect(self.consoleLogMessage)
            self.engine.setPage(self.page)

            print(self.page.settings())

            self.intercept = _Intercept(self)
            #self.handler = _Handler()
            #self.profile.installUrlSchemeHandler(b"http://", self.handler)
            #self.profile.installUrlSchemeHandler(b"https://", self.handler)
            self.profile.setUrlRequestInterceptor(self.intercept)
            #self.page = QWebEnginePage(self.profile, self.engine)


            # disable cors
            # https://doc-snapshots.qt.io/qt6-dev/qwebenginesettings.html
            settings = self.engine.settings()
            settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
            print(settings)
            #self.page.setUrl(self.url)

            self.engine.load(self.url)
            print(settings)

            self.channel = QWebChannel(self.engine.page())
            self.engine.page().setWebChannel(self.channel)



            #self.engine.page().setDevToolsPage(self.engine.page())

        def runJavaScript(self, text):
            """
            execute a javascript expression inside the context of the webview
            """
            self.engine.page().runJavaScript(text)

        def reload(self):

            self.engine.load(self.url)

        def interceptRequest(self, info):
            # https://doc.qt.io/qt-6/qwebengineurlrequestinfo.html
            # rewrite relative urls to be the correct path
            print("intercept", info.resourceType(), info.requestUrl())
            # QUrl()
            # info.redirect(url)
            return

        def registerObject(self, name, obj):
            """
            register an QObject and give it a name.
            the object's signals/Slots can be accessed in JS using

            window.channel.objects.<name>.

            in JS connect to signals to call a function when the
            signal is emitted. or call the function from JS to
            pass data back to python

            Note: registered objects are not available in JS until
            the channel is initizlaied, which happens after window.load
            """
            print("--", isinstance(obj, QObject))
            self.channel.registerObject(name, obj)

except ImportError:
    #print(e)
    #print("daedalus webview import error")

    def export_webchannel_js(path):
        raise RuntimeError("qt6 unavailable")

    class DaedalusWebView():
        def __init__(self, html_path):
            super(DaedalusWebView, self).__init__()
            raise RuntimeError("qt6 unavailable")
