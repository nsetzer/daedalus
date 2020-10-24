import re
import http.server
import socketserver
import json
import os
import sys
import io
import gzip
import ssl
from urllib.parse import urlparse, unquote
import mimetypes

from .builder import Builder

class Response(object):
    def __init__(self, status_code=200, payload=None, compress=False):
        super(Response, self).__init__()
        self.status_code = status_code
        self.headers = {}
        self.payload = payload or b""

        if isinstance(self.payload, str):
            self.payload = self.payload.encode("utf-8")

        if compress:
            gzip_buffer = io.BytesIO()
            gzip_file = gzip.GzipFile(mode='wb',
                                      fileobj=gzip_buffer)
            gzip_file.write(self.payload)
            gzip_file.close()

            self.payload = gzip_buffer.getvalue()

            self.headers['Vary'] = 'Accept-Encoding'
            self.headers['Content-Encoding'] = 'gzip'

class JsonResponse(Response):
    def __init__(self, obj, status_code=200):
        super(JsonResponse, self).__init__(status_code)
        self.headers = {"Content-Type": "application/json"}
        self.payload = json.dumps(obj).encode('utf-8') + b"\n"

class Resource(object):
    def __init__(self):
        super(Resource, self).__init__()

    def endpoints():
        return []

class Router(object):
    def __init__(self):
        super(Router, self).__init__()
        self.route_table = {
            "DELETE": [],
            "GET": [],
            "POST": [],
            "PUT": [],
        }
        self.endpoints = []

    def registerEndpoints(self, endpoints):
        for method, pattern, callback in endpoints:
            regex, tokens = self.patternToRegex(pattern)
            self.route_table[method].append((regex, tokens, callback))
            self.endpoints.append((method, pattern))

    def getRoute(self, method, path):
        for re_ptn, tokens, callback in self.route_table[method]:
            m = re_ptn.match(path)
            if m:
                return callback, {k: v for k, v in zip(tokens, m.groups())}
        return None

    def patternToRegex(self, pattern):
        # convert a url pattern into a regular expression
        #
        #   /abc        - match exactly
        #   /:abc       - match a path compenent exactly once
        #   /:abc?      - match a path component 0 or 1 times
        #   /:abc+      - match a path component 1 or more times
        #   /:abc*      - match a path component 0 or more times
        #
        # /:abc will match '/foo' with
        #  {'abc': foo}
        # /:bucket/:key* will match '/mybucket/dir1/dir2/fname' with
        #  {'bucket': 'mybucket', key: 'dir1/dir2/fname'}

        parts = [part for part in pattern.split("/") if part]
        tokens = []
        re_str = "^"
        for part in parts:
            if (part.startswith(':')):
                c = part[-1]
                if c == '?':
                    tokens.append(part[1: -1])
                    re_str += "\\/([^\\/]*)"
                elif c == '*':
                    tokens.append(part[1: -1])
                    # todo: match '\\/?'' or '\\/()'
                    # otherwise the / ends up being optional
                    re_str += "\\/?(.*)"
                elif c == '+':
                    tokens.append(part[1: -1])
                    re_str += "\\/?(.+)"
                else:
                    tokens.append(part[1:])
                    re_str += "\\/([^\\/]+)"
            else:
                re_str += '\\/' + part

        if re_str != "^\\/":
            re_str += "\\/?"

        re_str += '$'
        return (re.compile(re_str), tokens)

class RequestHandler(http.server.BaseHTTPRequestHandler):

    BUFFER_RX_SIZE = 16384
    BUFFER_TX_SIZE = 16384

    def __init__(self, router, *args):
        self.router = router
        super(RequestHandler, self).__init__(*args)
        self.protocol_version = 'HTTP/1.1'

    def _handleMethod(self, method):
        url = urlparse(unquote(self.path))
        result = self.router.getRoute(method, url.path)
        if result:
            # TODO: try-block around user code
            callback, matches = result

            parts = url.query.split("&")
            self.query = dict(part.split("=") for part in parts if '=' in part)
            response = callback(self, self.path, matches)

            if not response:
                response = JsonResponse({'error':
                    'endpoint failed to return a response'}, 500)

        else:
            response = JsonResponse({'error': 'path not found'}, 404)

        try:
            self.send_response(response.status_code)
            for k, v in response.headers.items():
                self.send_header(k, v)
            self.end_headers()
            if hasattr(response.payload, "read"):
                buf = response.payload.read(RequestHandler.BUFFER_TX_SIZE)
                while buf:
                    self.wfile.write(buf)
                    buf = response.payload.read(RequestHandler.BUFFER_TX_SIZE)
            else:
                self.wfile.write(response.payload)
        except ConnectionAbortedError as e:
            sys.stderr.write("%s aborted\n" % url.path)
        except BrokenPipeError as e:
            sys.stderr.write("%s aborted\n" % url.path)
        finally:
            if hasattr(response.payload, "close"):
                response.payload.close()

    def do_DELETE(self):
        return self._handleMethod("DELETE")

    def do_GET(self):
        return self._handleMethod("GET")

    def do_POST(self):
        return self._handleMethod("POST")

    def do_PUT(self):
        return self._handleMethod("PUT")

    def json(self):
        length = int(self.headers['content-length'])
        binary_data = self.rfile.read(length)
        obj = json.loads(binary_data.decode('utf-8'))
        return obj

    def saveFile(self, path):
        try:
            length = int(self.headers['content-length'])
            content_type = self.headers['content-type']
            parts = content_type.split(";")
            for part in parts:
                part = part.strip()
                if part.startswith("boundary="):
                    boundary = part[len("boundary="):]

            with open(path, "wb") as wb:

                # attempting to read more than the length
                # will cause the stream to block.
                to_read = min(RequestHandler.BUFFER_RX_SIZE, length)
                buf = self.rfile.read(to_read)
                length -= len(buf)

                # the form upload will contain multiple lines of information
                # before the contents of the file begins
                index = buf.find(b"\x0D\x0A")
                first = True
                while index >= 0:
                    line = buf[:index + 2]
                    buf = buf[index + 2:]
                    index = buf.find(b"\x0D\x0A")
                    if line == b"\x0D\x0A":
                        # an empty line indicates start of the content
                        break
                    if first:
                        # the first line is the boundary
                        # don't trust the boundary given in the header
                        # the stream ends with \r\n$BOUNDARY\r\n
                        # hence the +4 here to cover the new lines
                        length -= len(line) + 4
                        first = False
                wb.write(buf)

                to_read = min(RequestHandler.BUFFER_RX_SIZE, length)
                buf = self.rfile.read(to_read)
                while buf:
                    length -= len(buf)
                    wb.write(buf)
                    to_read = min(RequestHandler.BUFFER_RX_SIZE, length)
                    buf = self.rfile.read(to_read)

        except Exception as e:
            print(e)

    def acceptsGzip(self):
        return "gzip" in self.headers['Accept-Encoding'].lower()

class TcpServer(socketserver.TCPServer):
    allow_reuse_address = True

    def __init__(self, addr, factory):
        super().__init__(addr, factory)
        self.certfile = None
        self.keyfile = None

    def setCert(self, certfile=None, keyfile=None):
        self.certfile = certfile
        self.keyfile = keyfile

    def getProtocol(self):
        return "http" if self.certfile is None and self.keyfile is None else "https"

    def get_request(self):
        socket, fromaddr = self.socket.accept()

        if self.certfile is not None and self.keyfile is not None:
            socket = ssl.wrap_socket(
                socket,
                server_side=True,
                certfile=self.certfile,
                keyfile=self.keyfile,
                ssl_version=ssl.PROTOCOL_TLS
            )

        return socket, fromaddr

class Server(object):
    def __init__(self, host, port):
        super(Server, self).__init__()
        self.host = host
        self.port = port
        self.certfile = None
        self.keyfile = None

    def setCert(self, certfile=None, keyfile=None):
        self.certfile = certfile
        self.keyfile = keyfile

    def buildRouter(self):
        raise NotImplementedError()

    def run(self):
        addr = (self.host, self.port)
        router = self.buildRouter()
        # construct a factory for a RequestHandler that is aware
        # of the current router.
        factory = lambda *args: RequestHandler(router, *args)
        with TcpServer(addr, factory) as httpd:

            httpd.setCert(self.certfile, self.keyfile)

            for endpoint in router.endpoints:
                print("%-8s %s" % endpoint)

            proto = httpd.getProtocol()

            print(f"Daedalus Server listening on {proto}://{self.host}:{self.port}. Not for production use!")

            httpd.serve_forever()

class SampleResource(Resource):

    def __init__(self, index_js, search_path, static_data, static_path, platform=None, **opts):
        super(SampleResource, self).__init__()
        self.builder = Builder(search_path, static_data, platform=platform)
        self.index_js = index_js
        self.opts = opts
        self.style, self.source, self.html = self.builder.build(self.index_js, **self.opts)
        self.static_path = static_path

    def endpoints(self):
        return [
            ("GET", "/static/index.css", self.get_style),
            ("GET", "/static/index.js", self.get_source),
            ("GET", "/static/:path*", self.get_static),
            ("GET", "/favicon.ico", self.get_favicon),
            ("GET", "/:path*", self.get_path),
        ]

    def get_style(self, request, location, matches):
        """
        serve the compiled css
        """
        response = Response(payload=self.style, compress=request.acceptsGzip())
        response.headers['Content-Type'] = 'text/css'
        return response

    def get_source(self, request, location, matches):
        """
        serve the compiled javascript code
        """
        response = Response(payload=self.source, compress=request.acceptsGzip())
        response.headers['Content-Type'] = 'application/javascript'
        return response

    def get_static(self, request, location, matches):
        """
        serve files found inside the provided static directory
        """
        # Note: Not For Production Use. This is a security risk
        path = os.path.join(self.static_path, matches['path'])

        if not os.path.exists(path):
            return JsonResponse({"error": "not found"}, status_code=404)

        response = Response(payload=open(path, "rb"))
        type, _ = mimetypes.guess_type(path)
        response.headers['Content-Type'] = type
        return response

    def get_path(self, request, location, matches):
        """
        rebuild the javascript and html, return the html
        """
        self.style, self.source, self.html = self.builder.build(self.index_js, **self.opts)
        return Response(payload=self.html)

    def get_favicon(self, request, location, matches):
        """
        serve the favicon
        """
        path = self.builder.find("favicon.ico")

        if not os.path.exists(path):
            return JsonResponse({"error": "not found"}, status_code=404)

        response = Response(payload=open(path, "rb"))
        type, _ = mimetypes.guess_type(path)
        response.headers['Content-Type'] = type
        return response

class SampleServer(Server):

    def __init__(self, host, port, index_js, search_path, static_data=None, static_path="./static", platform=None, **opts):
        super(SampleServer, self).__init__(host, port)
        self.index_js = index_js
        self.search_path = search_path
        self.static_data = static_data
        self.static_path = static_path
        self.platform = platform
        self.opts = opts

    def buildRouter(self):
        router = Router()
        res = SampleResource(self.index_js, self.search_path, self.static_data, self.static_path, platform=self.platform, **self.opts)
        router.registerEndpoints(res.endpoints())
        return router

def main():  # pragma: no cover

    class DemoResource(Resource):

        def endpoints(self):
            return [
                ("GET", "/greet", self.greet)
            ]

        def greet(self, request, location, matches):
            name = request.query.get("name", "World")
            return JsonResponse({"response": f"Hello {name}!"})

    class DemoServer(Server):

        def buildRouter(self):
            router = Router()

            router.registerEndpoints(DemoResource().endpoints())

            return router

    server = DemoServer("0.0.0.0", 80)

    server.run()


if __name__ == '__main__':  # pragma: no cover
    main()
