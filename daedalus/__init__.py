
# TODO: this is kind of a bad idea, instead the user should
# install the loader prior to running the interpreter.
#try:
#    from .loader import JavascriptFinder
#    # call to enable importing javascript from python
#    install = JavascriptFinder.install
#except ImportError as e:
#    pass

import os

from .token import Token
from .lexer import Lexer
from .parser import Parser
from .formatter import Formatter
from .transform import TransformMinifyScope
from .vm import VmRuntime
from . import cli
from . import webview

def parse(text: str) -> Token:
    """ Parse javascript source into an AST

    :param text: the javascript source to Parse
    """
    lexer = Lexer()
    parser = Parser()
    parser.disable_all_warnings = True

    ast = lexer.lex(text)
    ast = parser.parse(ast)

    return ast

def format(ast: Token, minify=True) -> str:
    """ Format an AST as valid javascript

    :param ast: the AST to minify
    :param minify: If True, minify the source code,
                   including shortening variable names when possible
                   If False, a best effort approach is used
                   to produce idiomatic javascript.
    """

    if minify:
        xform = TransformMinifyScope()
        xform.disable_warnings = True
        xform.transform(ast)

    formatter = Formatter({'minify': minify})

    return formatter.format(ast)

def run_text(self, text):
    runtime = VmRuntime()
    search_path = os.environ.get('DAEDALUS_PATH', "").split(":")
    search_path.append(os.getcwd())
    runtime.search_path = search_path
    return runtime.run_text(text)

def run_script(self, path):
    text = open(path).read()
    return run_text(text)