
import os
import sys
import argparse
import logging
import time
import cProfile
import json

from .builder import Builder
from .server import SampleServer
from .lexer import Lexer
from .parser import Parser
from .formatter import Formatter
from .transform import TransformMinifyScope


from .cli_util import build

from .vm import vmGetAst, VmRuntime
from .vm_compiler import VmCompiler
from .vm_repl import Repl

def parse_env(envparams):
    env = {}
    for s in envparams:
        ks, v = s.split('=', 1)
        try:
            v = json.loads(v)
        except Exception as e:
            print(e)
            pass
        parts = ks.split('.')
        obj = env
        k = parts.pop()
        for part in parts:
            if part not in obj:
                obj[part] = {}
            obj = obj[part]
            if not isinstance(obj, dict):
                raise KeyError(k)
        obj[k] = v
    return {"daedalus": {"env": env}}

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
    compile javascript and create the release html + js
    """

    def register(self, parser):
        subparser = parser.add_parser('build',
            description=self.__doc__,
            help=self.__doc__.strip().split("\n")[0])
        subparser.set_defaults(func=self.execute, cli=self)

        subparser.add_argument('--minify', action='store_true')
        subparser.add_argument('--onefile', action='store_true')
        subparser.add_argument('--paths', default=None)
        subparser.add_argument('--env', type=str, action='append', default=[],
            help="key=value settings, can be provided multiple times")
        subparser.add_argument('--platform', type=str, default=None)
        subparser.add_argument('--static', type=str, default="./static")
        subparser.add_argument('--htmlname', type=str, default="index.html")
        subparser.add_argument('--sourcemap', action='store_true')
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

        staticdata = parse_env(args.env)

        build(outdir, index_js,
            staticdir=staticdir,
            staticdata=staticdata,
            paths=paths,
            platform=platform,
            minify=minify,
            onefile=onefile,
            htmlname=args.htmlname,
            sourcemap=args.sourcemap)

class BuildProfileCLI(CLI):
    """
    compile a js and html file with the python profiler enabled
    """

    def register(self, parser):

        subparser = parser.add_parser('build-profile',
            description=self.__doc__,
            help=self.__doc__.strip().split("\n")[0])
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
    """ serve a page
    """

    def register(self, parser):
        subparser = parser.add_parser('serve',
            description=self.__doc__,
            help=self.__doc__.strip().split("\n")[0])
        subparser.set_defaults(func=self.execute, cli=self)

        subparser.add_argument('--minify', action='store_true')
        subparser.add_argument('--onefile', action='store_true')
        subparser.add_argument('--paths', default=None)
        subparser.add_argument('--host', default='0.0.0.0', type=str)
        subparser.add_argument('--port', default=4100, type=int)
        subparser.add_argument('--env', type=str, action='append', default=[],
            help="key=value settings, can be provided multiple times")
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

        staticdata = parse_env(args.env)

        server = SampleServer(args.host, args.port,
            args.index_js, paths,
            staticdata, args.static,
            platform=args.platform,
            onefile=args.onefile,
            minify=args.minify)
        server.setCert(args.cert, args.keyfile)
        server.run()

class FormatCLI(CLI):
    """ reformat a js file
    """
    def register(self, parser):
        subparser = parser.add_parser('format',
            aliases=['fmt'],
            description=self.__doc__,
            help=self.__doc__.strip().split("\n")[0])
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
    """ print ast for a compiled source file

    any transforms required to run the source file in the VM are performed.
    """

    def register(self, parser):
        subparser = parser.add_parser('ast',
            description=self.__doc__,
            help=self.__doc__.strip().split("\n")[0])
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

        ast = vmGetAst(text)

        print(ast.toString(3))

class DisCLI(CLI):
    """ print disassembly for a js file

    displays the opcodes and variables for each function
    """
    def register(self, parser):
        subparser = parser.add_parser('dis',
            description=self.__doc__,
            help=self.__doc__.strip().split("\n")[0])
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

        ast = vmGetAst(open(jspath).read())
        compiler = VmCompiler()
        mod = compiler.compile(ast)
        mod.dump()

class RunCLI(CLI):
    """ run a script
    """

    def register(self, parser):
        subparser = parser.add_parser('run',
            description=self.__doc__,
            help=self.__doc__.strip().split("\n")[0])
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

        runtime = VmRuntime()
        search_path = os.environ.get('DAEDALUS_PATH', "").split(":")
        search_path.append(os.getcwd())
        runtime.search_path = search_path
        runtime.enable_diag=False
        rv, _ = runtime.run_text(open(jspath).read())
        return 0 # todo return proper exit status

class ModPackCLI(CLI):
    """ package a single daedalus module for export
        allows importing said module using modern js syntax

        this cli tool is a placeholder. serving to document this feature.

        In order to support modern js, which uses modules, a new builder
        will need to be written. this builder should output valid js modules

        daedalus modpack  res/daedalus/daedalus.js ./dist/daedalus.jsm
    """

    def register(self, parser):
        subparser = parser.add_parser('modpack',
            description=self.__doc__,
            help=self.__doc__.strip().split("\n")[0])
        subparser.set_defaults(func=self.execute, cli=self)

        subparser.add_argument('--minify', action='store_true')
        subparser.add_argument('--paths', default=None)
        subparser.add_argument('--env', type=str, action='append', default=[],
            help="key=value settings, can be provided multiple times")
        subparser.add_argument('--platform', type=str, default=None)
        subparser.add_argument('--static', type=str, default="./static")
        subparser.add_argument('index_js')
        subparser.add_argument('out')

    def execute(self, args):

        return 0 # todo return proper exit status


def register_parsers(parser):

    BuildCLI().register(parser)
    BuildProfileCLI().register(parser)
    ServeCLI().register(parser)
    FormatCLI().register(parser)
    AstCLI().register(parser)
    DisCLI().register(parser)
    RunCLI().register(parser)
