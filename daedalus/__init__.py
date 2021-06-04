
# TODO: this is kind of a bad idea, instead the user should
# install the loader prior to running the interpreter.
#try:
#    from .loader import JavascriptFinder
#    # call to enable importing javascript from python
#    install = JavascriptFinder.install
#except ImportError as e:
#    pass

from .token import Token
from .lexer import Lexer
from .parser import Parser
from .formatter import Formatter

def parse(text):
    lexer = Lexer()
    parser = Parser()
    parser.disable_all_warnings = True

    ast = lexer.lex(text)
    ast = parser.parse(ast)

    return ast

def format(ast, minify=True):

    formatter = Formatter({'minify': minify})

    return formatter.format(ast)
