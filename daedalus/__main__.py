
import os
import sys
import argparse
import logging

from .builder import Builder
from .server import SampleServer

enable_compiler = True
try:
    import bytecode
    import requests
    from .repl import Repl
    from .jseval import compile_file, JsContext
except ImportError as e:
    enable_compiler = False

def makedirs(path):
    if not os.path.exists(path):
        os.makedirs(path)

def parse_paths(paths, js_root=None):

    paths = []
    if paths:
        paths = paths.split(":")

    if js_root:
        paths.insert(0, os.path.split(js_root)[0])

    return paths

def copy_staticdir(staticdir, outdir):

    if staticdir and os.path.exists(staticdir):

        for dirpath, dirnames, filenames in os.walk(staticdir):
            paths = []
            for dirname in dirnames:
                src_path = os.path.join(dirpath, dirname)
                dst_path = os.path.join(outdir, "static", os.path.relpath(src_path, staticdir))
                if not os.path.exists(dst_path):
                    os.makedirs(dst_path)

            for filename in filenames:
                src_path = os.path.join(dirpath, filename)
                dst_path = os.path.join(outdir, "static", os.path.relpath(src_path, staticdir))
                with open(src_path, "rb") as rb:
                    with open(dst_path, "wb") as wb:
                        wb.write(rb.read())

def copy_favicon(builder, outdir):
    inp_favicon = builder.find("favicon.ico")
    out_favicon = os.path.join(outdir, "favicon.ico")
    with open(inp_favicon, "rb") as rb:
        with open(out_favicon, "wb") as wb:
            wb.write(rb.read())

class CLI(object):
    def __init__(self):
        super(CLI, self).__init__()

    def register(self, parser):
        pass

    def execute(self, args):
        pass

class BuildCLI(CLI):
    """
    compile a js and html file for production use
    """

    def register(self, parser):
        subparser = parser.add_parser('build',
            help="compile javascript and create the release html + js")
        subparser.set_defaults(func=self.execute, cli=self)

        subparser.add_argument('--minify', action='store_true')
        subparser.add_argument('--onefile', action='store_true')
        subparser.add_argument('--paths', default=None)
        subparser.add_argument('--env', type=str, action='append', default=[])
        subparser.add_argument('--platform', type=str, default=None)
        subparser.add_argument('--static', type=str, default=None)
        subparser.add_argument('index_js')
        subparser.add_argument('out')

    def execute(self, args):

        outdir = args.out
        staticdir = args.static
        envparams = args.env
        platform = args.platform
        minify = args.minify
        onefile = args.onefile
        js_path_input = os.path.abspath(args.index_js)
        html_path_output = os.path.join(outdir, "index.html")
        js_path_output = os.path.join(outdir, "static", "index.js")
        css_path_output = os.path.join(outdir, "static", "index.css")

        paths = parse_paths(args.paths, js_path_input)
        static_data = {"daedalus": {"env": dict([s.split('=', 1) for s in envparams])}}
        builder = Builder(paths, static_data, platform=platform)
        css, js, html = builder.build(js_path_input, minify=minify, onefile=onefile)

        makedirs(outdir)

        with open(html_path_output, "w") as wf:
            cmd = 'daedalus ' + ' '.join(sys.argv[1:])
            wf.write("<!--%s-->\n" % cmd)
            wf.write(html)

        if not onefile:
            makedirs(os.path.join(outdir, 'static'))
            with open(js_path_output, "w") as wf:
                wf.write(js)

            with open(css_path_output, "w") as wf:
                wf.write(css)

        copy_staticdir(staticdir, outdir)
        copy_favicon(builder, outdir)

class ServeCLI(CLI):

    def register(self, parser):
        subparser = parser.add_parser('serve',
            help="serve a page")
        subparser.set_defaults(func=self.execute, cli=self)

        subparser.add_argument('--minify', action='store_true')
        subparser.add_argument('--onefile', action='store_true')
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
            static_data, args.static, platform=args.platform, onefile=args.onefile, minify=args.minify)
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

        v = 0
        try:
            v = cc.execute()
        finally:
            print(v)

def register_parsers(parser):

    BuildCLI().register(parser)
    ServeCLI().register(parser)
    if enable_compiler:
        AstCLI().register(parser)
        DisCLI().register(parser)
        RunCLI().register(parser)

def getArgs():
    parser = argparse.ArgumentParser(
        description='unopinionated javascript framework')
    subparsers = parser.add_subparsers()
    parser.add_argument('--verbose', '-v', action='count', default=0)
    register_parsers(subparsers)
    args = parser.parse_args()

    return parser, args

def main():

    if enable_compiler and len(sys.argv) == 1:
        Repl().main()
    else:
        parser, args = getArgs()

        FORMAT = '%(levelname)-8s - %(message)s'
        logging.basicConfig(level=logging.INFO, format=FORMAT)

        if not hasattr(args, 'func'):
            parser.print_help()
        else:
            args.func(args)


if __name__ == '__main__':
    main()