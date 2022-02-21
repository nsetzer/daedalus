
import os
import sys
import argparse
import logging
import time
import cProfile

from .builder import Builder
from .server import SampleServer
from .lexer import Lexer
from .parser import Parser
from .formatter import Formatter
from .transform import TransformMinifyScope

enable_compiler = True
try:
    import bytecode
    import requests
    from .repl import Repl
    from .jseval import compile_file, JsContext
except ImportError as e:
    enable_compiler = False

from .cli_util import build

class Clock(object):
    def __init__(self, text):
        super(Clock, self).__init__()
        self.text = text

    def __enter__(self):
        self.ts = time.perf_counter()
        return self

    def __exit__(self, *args):
        self.te = time.perf_counter()
        print("%s: %.6f" % (self.text, self.te - self.ts))

        return False

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
        subparser.add_argument('--static', type=str, default="./static")
        subparser.add_argument('index_js')
        subparser.add_argument('out')

    def execute(self, args):

        outdir = args.out
        staticdir = args.static
        platform = args.platform
        minify = args.minify
        onefile = args.onefile
        index_js = os.path.abspath(args.index_js)
        if args.paths:
            paths = args.paths.split(":")
        else:
            paths = []

        paths.insert(0, os.path.split(index_js)[0])

        envparams = args.env
        staticdata = {"daedalus": {"env": dict([s.split('=', 1) for s in envparams])}}

        build(outdir, index_js,
            staticdir=staticdir,
            staticdata=staticdata,
            paths=paths,
            platform=platform,
            minify=minify,
            onefile=onefile)

class BuildProfileCLI(CLI):
    """
    compile a js and html file for production use
    """

    def register(self, parser):

        subparser = parser.add_parser('build-profile',
            help="run build with cProfile enabled")
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

        cProfile.runctx(
            "cli.execute(args)",
            {"cli": BuildCLI(), "args": args},
            {},
            filename=None,
            sort='cumtime')

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

class FormatCLI(CLI):

    def register(self, parser):
        subparser = parser.add_parser('format',
            help="reformat javascript file", aliases=['fmt'])
        subparser.set_defaults(func=self.execute, cli=self)

        subparser.add_argument('--minify', action='store_true')
        subparser.add_argument('in_js')
        subparser.add_argument('out_js')

    def execute(self, args):


        if args.in_js == "-":
            text = sys.stdin.read()
        else:
            path_in = os.path.abspath(args.in_js)
            with open(path_in, "r") as rf:
                text = rf.read()

        with Clock("lex"):
            tokens = Lexer().lex(text)

        with Clock("parse"):
            ast = Parser().parse(tokens)

        if args.minify:
            with Clock("minify"):
                TransformMinifyScope().transform(ast)

        with Clock("format"):
            out_text = Formatter({'minify': args.minify}).format(ast)

        if args.out_js == "-":
            sys.stdout.write(out_text)
            sys.stdout.write("\n")

        else:
            path_out = os.path.abspath(args.out_js)
            with open(path_out, "w") as wf:
                wf.write(out_text)
                wf.write("\n")

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

        cc = compile_file(jspath, quiet=True)

        v = 0
        try:
            v = cc.execute()
        finally:
            pass

        rv = 0
        if 'main' in cc.globals:
            f = cc.globals['main']
            rv_ = f()
            if isinstance(rv_, int):
                rv = rv_
        return rv

def register_parsers(parser):

    BuildCLI().register(parser)
    BuildProfileCLI().register(parser)
    ServeCLI().register(parser)
    FormatCLI().register(parser)
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

        rv = 0
        if not hasattr(args, 'func'):
            parser.print_help()
        else:
            rv = args.func(args)

        if rv:
            sys.exit(rv)



if __name__ == '__main__':
    main()