
import os
from daedalus.builder import Builder
from daedalus.server import Server, Resource, Router, Response, JsonResponse

class DemoResource(Resource):

    def __init__(self):
        super(DemoResource, self).__init__()
        self.builder = Builder(['./examples'], {})
        self.index_js = "./examples/index.js"
        self.source, self.html = self.builder.build(self.index_js)

    def endpoints(self):
        return [
            ("GET", "/static/index.js", self.get_source),
            ("GET", "/favicon.ico", self.get_favicon),
            ("GET", "/:path*", self.get_path),
        ]

    def get_source(self, request, location, matches):
        return Response(payload=self.source, compress=request.acceptsGzip())

    def get_path(self, request, location, matches):
        self.source, self.html = self.builder.build(self.index_js)
        return Response(payload=self.html, compress=request.acceptsGzip())

    def get_favicon(self, request, location, matches):
        path = self.builder.find("favicon.ico")
        payload = open(path, "rb").read()
        response = Response(payload=payload)
        response.headers['Content-Type'] = 'image/x-icon'
        return response

class FileResource(Resource):

    def __init__(self):
        super(FileResource, self).__init__()

    def endpoints(self):
        return [
            ("GET", "/api/files/list/:path*", self.files_list_path),
            ("POST", "/api/files/:path*", self.files_upload),
        ]

    def files_list_path(self, request, location, matches):
        path = matches['path']
        if not path:
            path = "./"
        elif not os.path.exists(path):
            return JsonResponse({"error": "exists"}, status_code=404)

        if os.path.isdir(path):
            # return json contaning information on the files in the directory
            return JsonResponse(self._load_directory(path))
        else:
            # return the contents of the file
            payload = open(path, "rb").read()
            response = Response(payload=payload)
            response.headers['Content-Type'] = 'application/octet-stream'
            response.headers['Content-Disposition'] = 'filename=%s;' % os.path.split(path)[1]
            return response

    def _load_directory(self, path):

        names = os.listdir(path)
        files = []
        for name in names:
            filepath = os.path.join(path, name)
            isdir = os.path.isdir(filepath)

            files.append({
                "name": name,
                "mode": 2 if isdir else 1,
            })

        path = path.rstrip("/")

        if os.path.samefile("./", path):
            path = ""
            parent = ""
        else:
            parent = os.path.split(path)[0]

        if path and not path.startswith("/"):
            path = "/" + path

        if parent and not parent.startswith("/"):
            parent = "/" + parent

        # print("<%s> <%s>" % (path, parent))

        result = {
            "path": path,
            "parent": parent,
            "files": files,
        }
        return result

    def files_upload(self, request, location, matches):
        path = matches['path']
        if not path:
            return JsonResponse({"error": "exists"}, status_code=400)
        if os.path.isdir(path):
            return JsonResponse({"error": "exists"}, status_code=400)

        request.saveFile(path)

        return JsonResponse({"staus": "ok"}, status_code=200)

class ListResource(Resource):

    def __init__(self):
        super(ListResource, self).__init__()

        self.todolist = [
            "groceries",
            "laundry",
            "term paper",
            "electric bill"
        ]
    def endpoints(self):
        return [
            ("GET", "/api/todo", self.get_list),
            ("POST", "/api/todo", self.set_list),
        ]

    def get_list(self, request, location, matches):

        return JsonResponse({"result": self.todolist})

    def set_list(self, request, location, matches):
        self.todolist = request.json()
        print(self.todolist)
        return JsonResponse({"status": "ok"})

class DemoServer(Server):

    def buildRouter(self):
        router = Router()

        router.registerEndpoints(FileResource().endpoints())
        router.registerEndpoints(ListResource().endpoints())
        router.registerEndpoints(DemoResource().endpoints())

        return router

def main():
    server = DemoServer("0.0.0.0", 4100)

    server.run()

if __name__ == '__main__':
    main()