#! cd .. && python3 -m daedalus.jseval

import os

import time
import struct
import marshal

from importlib.util import spec_from_file_location, MAGIC_NUMBER, cache_from_source

from .lexer import Lexer
from .parser import Parser
from .compiler import Compiler
from .builder import Builder
from .builtins import JsObject
from .util import Namespace

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

def compile_file(path):


    paths = [os.path.split(path)[0]]
    static_data = {}
    builder = Builder(paths, static_data)

    compiler = Compiler()
    ast = builder.compile_module(path)
    #try:
    compiler.compile(ast)
    #finally:
    #    print(ast.toString(3, pad=".  "))

    #
    return compiler



def main():

    compile_file("daedalus")
if __name__ == '__main__':
    main()