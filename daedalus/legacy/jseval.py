#! cd .. && python3 -m daedalus.jseval

import os

import time
import struct
import marshal

from importlib.util import MAGIC_NUMBER

from .lexer import Lexer
from .parser import Parser
from .formatter import Formatter
from .compiler import Compiler
from .builder import Builder
from .transform import TransformClassToFunction, TransformMinifyScope,\
    TransformIdentityScope, TransformClassToFunction, \
    TransformReplaceIdentity

def save_module(path, co):
    """
    path: the path to serialize a code object to
    co: a python code object

    serialize using the pyc module format so that
    any python program can import the module
    """

    dirpath, _ = os.path.split(path)
    if not os.path.exists(dirpath):
        os.makedirs(dirpath)

    with open(path, "wb") as wb:
        wb.write(MAGIC_NUMBER)
        wb.write(b"\x00\x00\x00\x00")
        wb.write(struct.pack("I", int(time.time())))
        wb.write(b"\x00\x00\x00\x00")
        marshal.dump(co, wb)

def load_module(path):
    """
    path: the path to a pyc file containing a serialized code object

    returns a code object
    """

    with open(path, "rb") as rb:

        magic = rb.read(4)
        if magic != MAGIC_NUMBER:
            raise ImportError("magic number does not match")
        rb.read(4)
        rb.read(4)
        rb.read(4)
        return marshal.load(rb)

def compile_file(path, quiet=False):


    paths = [os.path.split(path)[0]]
    static_data = {}
    builder = Builder(paths, static_data, platform="python")

    ast = builder.build_module(path)

    TransformIdentityScope().transform(ast)

    TransformClassToFunction().transform(ast)

    TransformReplaceIdentity().transform(ast)

    compiler = Compiler()
    #try:
    compiler.compile(ast)
    #finally:
    #    print(ast.toString(3, pad=".  "))

    #
    return compiler

class JsContext(object):
    def __init__(self):
        super(JsContext, self).__init__()

        self.globals = {}

    def parsejs(self, text):
        """
        run the same parser used for compiling
        """

        tokens = Lexer().lex(text)
        parser = Parser()
        parser.python = True
        ast = parser.parse(tokens)

        transform = TransformIdentityScope()
        transform.disable_warnings = True
        transform.transform(ast)

        TransformClassToFunction().transform(ast)

        TransformReplaceIdentity().transform(ast)

        return ast

    def minifyjs(self, text):

        """
        minify the input text using traditional javascript rules
        """

        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)

        transform = TransformMinifyScope()
        transform.disable_warnings = True
        transform.transform(ast)

        mintext = Formatter().format(ast)

        return mintext

    def compilejs(self, text):

        tokens = Lexer().lex(text)
        parser = Parser()
        #parser.python = True
        ast = parser.parse(tokens)

        transform = TransformIdentityScope()
        transform.disable_warnings = True
        transform.transform(ast)

        TransformClassToFunction().transform(ast)

        xform = TransformReplaceIdentity()
        xform.transform(ast)

        compiler = Compiler(filename="<string>",
            globals=self.globals,
            flags=Compiler.CF_REPL)

        compiler.compile(ast)

        return compiler

    def evaljs(self, text):

        compiler = self.compilejs(text)

        result = compiler.function_body()

        if isinstance(result, dict):
            #self.globals.update(result)
            self.globals.update(compiler.globals)

        return result

    def registerGlobal(self, name, obj):
        """register a python object to be accessable from javascript"""
        self.globals[name] = obj


def main():

    text = JsContext().minifyjs("""
        function f2() {

        }
        return f2
        """)
    print(text)

    #try:
    #    compile_file("daedalus")
    #except TokenError as e:
    #    print("-"*40)
    #    print(e.token.file)
    #    print(e.token.toString(3))
    #    raise e


if __name__ == '__main__':
    main()