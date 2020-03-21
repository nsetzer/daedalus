
import os
import sys
import argparse
import logging

from .builder import Builder
from .server import SampleServer
from .repl import Repl
from .jseval import compile_file, JsContext

def makedirs(path):
    if not os.path.exists(path):
        os.makedirs(path)

class CLI(object):
    def __init__(self):
        super(CLI, self).__init__()

    def register(self, parser):
        pass

    def execute(self, args):
        pass

class BuildHtmlCLI(CLI):
    """
    compile a js and html file for production use
    """

    def register(self, parser):
        subparser = parser.add_parser('build_html',
            help="compile javascript into a single html file")
        subparser.set_defaults(func=self.execute, cli=self)

        subparser.add_argument('--paths', default=None)
        subparser.add_argument('--env', type=str, action='append', default=[])
        subparser.add_argument('--platform', type=str, default=None)
        subparser.add_argument('--onefile', action='store_true')
        subparser.add_argument('index_js')
        subparser.add_argument('out_html')

    def execute(self, args):

        paths = []
        if args.paths:
            paths = args.paths.split(":")

        jspath = os.path.abspath(args.index_js)
        paths.insert(0, os.path.split(jspath)[0])

        static_data = {"daedalus": {"env": dict([s.split('=', 1) for s in args.env])}}
        builder = Builder(paths, static_data)

        css, js, html = builder.build(args.index_js, onefile=True)

        makedirs(os.path.split(args.out_html)[0])

        with open(args.out_html, "w") as wf:
            cmd = 'daedalus ' + ' '.join(sys.argv[1:])
            wf.write("<!--%s-->\n" % cmd)
            wf.write(html)

class BuildCLI(CLI):
    """
    compile a js and html file for production use
    """

    def register(self, parser):
        subparser = parser.add_parser('build',
            help="compile javascript and create the release html + js")
        subparser.set_defaults(func=self.execute, cli=self)

        subparser.add_argument('--minify', action='store_true')
        subparser.add_argument('--paths', default=None)
        subparser.add_argument('--env', type=str, action='append', default=[])
        subparser.add_argument('--platform', type=str, default=None)
        subparser.add_argument('--static', type=str, default=None)
        subparser.add_argument('index_js')
        subparser.add_argument('out')

    def execute(self, args):

        paths = []
        if args.paths:
            paths = args.paths.split(":")

        jspath = os.path.abspath(args.index_js)
        paths.insert(0, os.path.split(jspath)[0])

        static_data = {"daedalus": {"env": dict([s.split('=', 1) for s in args.env])}}
        builder = Builder(paths, static_data, platform=args.platform)

        css, js, html = builder.build(args.index_js, minify=args.minify)

        makedirs(os.path.join(args.out, "static"))

        out_html = os.path.join(args.out, "index.html")
        with open(out_html, "w") as wf:
            wf.write(html)

        out_js = os.path.join(args.out, "static", "index.js")
        with open(out_js, "w") as wf:
            wf.write(js)

        out_css = os.path.join(args.out, "static", "index.css")
        with open(out_css, "w") as wf:
            wf.write(css)

        if args.static and os.path.exists(args.static):
            for dirpath, dirnames, filenames in os.walk(args.static):
                paths = []
                for dirname in dirnames:
                    src_path = os.path.join(dirpath, dirname)
                    dst_path = os.path.join(args.out, "static", os.path.relpath(src_path, args.static))
                    if not os.path.exists(dst_path):
                        os.makedirs(dst_path)

                for filename in filenames:
                    src_path = os.path.join(dirpath, filename)
                    dst_path = os.path.join(args.out, "static", os.path.relpath(src_path, args.static))
                    with open(src_path, "rb") as rb:
                        with open(dst_path, "wb") as wb:
                            wb.write(rb.read())

        inp_favicon = builder.find("favicon.ico")
        out_favicon = os.path.join(args.out, "favicon.ico")
        with open(inp_favicon, "rb") as rb:
            with open(out_favicon, "wb") as wb:
                wb.write(rb.read())

class CompileCLI(CLI):
    """
    compile a js file (and all imports) into a single file
    """

    def register(self, parser):
        subparser = parser.add_parser('compile',
            help="compile javascript into a single file")
        subparser.set_defaults(func=self.execute, cli=self)

        subparser.add_argument('--minify', action='store_true')
        subparser.add_argument('--standalone', action='store_true')
        subparser.add_argument('--paths', default=None)
        subparser.add_argument('--env', type=str, action='append', default=[])
        subparser.add_argument('--platform', type=str, default=None)
        subparser.add_argument('index_js')
        subparser.add_argument('out_js')
        subparser.add_argument('out_css')

    def execute(self, args):

        paths = []
        if args.paths:
            paths = args.paths.split(":")

        jspath = os.path.abspath(args.index_js)
        paths.insert(0, os.path.split(jspath)[0])

        static_data = {"daedalus": {"env": dict([s.split('=', 1) for s in args.env])}}

        builder = Builder(paths, static_data)

        # TODO: add flag to not pre-compile style sheets
        css, js, root = builder.compile(args.index_js, standalone=args.standalone)

        with open(args.out_js, "w") as wf:
            wf.write(js)
            wf.write("\n")

        with open(args.out_css, "w") as wf:
            wf.write(css)
            wf.write("\n")

class CompileModuleCLI(CLI):
    """
    compile a js file (and all imports) into a single file
    """

    def register(self, parser):
        subparser = parser.add_parser('cm',
            help="compile javascript into a single file")
        subparser.set_defaults(func=self.execute, cli=self)

        subparser.add_argument('--minify', action='store_true')
        subparser.add_argument('--paths', default=None)
        subparser.add_argument('--env', type=str, action='append', default=[])
        subparser.add_argument('--platform', type=str, default=None)
        subparser.add_argument('index_js')
        subparser.add_argument('out_js')

    def execute(self, args):

        paths = []
        if args.paths:
            paths = args.paths.split(":")

        jspath = os.path.abspath(args.index_js)
        paths.insert(0, os.path.split(jspath)[0])

        static_data = {"daedalus": {"env": dict([s.split('=', 1) for s in args.env])}}

        builder = Builder(paths, static_data)

        # TODO: add flag to not pre-compile style sheets
        js = builder.compile_module(args.index_js)

        with open(args.out_js, "w") as wf:
            wf.write(js)
            wf.write("\n")

class ServeCLI(CLI):

    def register(self, parser):
        subparser = parser.add_parser('serve',
            help="serve a page")
        subparser.set_defaults(func=self.execute, cli=self)

        subparser.add_argument('--minify', action='store_true')
        subparser.add_argument('--paths', default=None)
        subparser.add_argument('--host', default='0.0.0.0', type=str)
        subparser.add_argument('--port', default=4100, type=int)
        subparser.add_argument('--env', type=str, action='append', default=[])
        subparser.add_argument('--platform', type=str, default=None)
        subparser.add_argument('--static', type=str, default="./static")
        subparser.add_argument('--cert', type=str, default=None)
        subparser.add_argument('--keyfile', type=str, default=None)
        subparser.add_argument('index_js')

    def execute(self, args):

        paths = []
        if args.paths:
            paths = args.paths.split(":")

        jspath = os.path.abspath(args.index_js)
        paths.insert(0, os.path.split(jspath)[0])

        static_data = {"daedalus": {"env": dict([s.split('=', 1) for s in args.env])}}

        server = SampleServer(args.host, args.port,
            args.index_js, paths,
            static_data, args.static, platform=args.platform)
        server.setCert(args.cert, args.keyfile)
        server.run()

class AstCLI(CLI):

    def register(self, parser):
        subparser = parser.add_parser('ast',
            help="print ast for source file")
        subparser.set_defaults(func=self.execute, cli=self)

        subparser.add_argument('--paths', default=None)
        subparser.add_argument('--env', type=str, action='append', default=[])
        subparser.add_argument('--platform', type=str, default=None)
        subparser.add_argument('index_js')

    def execute(self, args):

        paths = []
        if args.paths:
            paths = args.paths.split(":")

        jspath = os.path.abspath(args.index_js)

        with open(jspath) as rf:
            text = rf.read()

        ast = JsContext().parsejs(text)

        print(ast.toString(3))

class DisCLI(CLI):

    def register(self, parser):
        subparser = parser.add_parser('dis',
            help="print disassembly")
        subparser.set_defaults(func=self.execute, cli=self)

        subparser.add_argument('--paths', default=None)
        subparser.add_argument('--env', type=str, action='append', default=[])
        subparser.add_argument('--platform', type=str, default=None)
        subparser.add_argument('index_js')

    def execute(self, args):

        paths = []
        if args.paths:
            paths = args.paths.split(":")

        jspath = os.path.abspath(args.index_js)

        cc = compile_file(jspath)

        cc.dump()

class RunCLI(CLI):

    def register(self, parser):
        subparser = parser.add_parser('run',
            help="run a script")
        subparser.set_defaults(func=self.execute, cli=self)

        subparser.add_argument('--paths', default=None)
        subparser.add_argument('--env', type=str, action='append', default=[])
        subparser.add_argument('--platform', type=str, default=None)
        subparser.add_argument('index_js')

    def execute(self, args):

        paths = []
        if args.paths:
            paths = args.paths.split(":")

        jspath = os.path.abspath(args.index_js)

        cc = compile_file(jspath)

        try:
            v = cc.execute()
        finally:
            print(v)


def getArgs():
    parser = argparse.ArgumentParser(
        description='unopinionated javascript framework')
    subparsers = parser.add_subparsers()
    parser.add_argument('--verbose', '-v', action='count', default=0)
    register_parsers(subparsers)
    args = parser.parse_args()

    return args

def register_parsers(parser):

    BuildHtmlCLI().register(parser)
    BuildCLI().register(parser)
    CompileCLI().register(parser)
    CompileModuleCLI().register(parser)
    ServeCLI().register(parser)
    AstCLI().register(parser)
    DisCLI().register(parser)
    RunCLI().register(parser)

def main():

    if len(sys.argv) == 1:
        Repl().main()
    else:
        args = getArgs()

        FORMAT = '%(levelname)-8s - %(message)s'
        logging.basicConfig(level=logging.INFO, format=FORMAT)

        if not hasattr(args, 'func'):
            parser.print_help()
        else:
            args.func(args)


if __name__ == '__main__':
    main()