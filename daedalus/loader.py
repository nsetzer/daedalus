
import sys
import os.path

import time
import struct
import marshal
from importlib.abc import Loader, MetaPathFinder
from importlib.util import spec_from_file_location, MAGIC_NUMBER, cache_from_source
import types

from .lexer import Lexer
from .parser import Parser
from .compiler import Compiler
from .builder import Builder
from .builtins import JsObject
from .util import Namespace
from .jseval import save_module, load_module, compile_file

def isNewer(source_path, compiled_path):
    return os.stat(source_path).st_mtime > os.stat(compiled_path).st_mtime

class JavascriptFinder(MetaPathFinder):

    _installed = False
    def find_spec(self, fullname, path, target=None):

        if path is None or path == "":
            path = sys.path # top level import --

        if "." in fullname:
            *_, name = fullname.split(".")
        else:
            name = fullname

        for entry in path:
            if os.path.isdir(os.path.join(entry, name)):
                filename = os.path.join(entry, name, "%s.js" % name)
                submodule_locations = [os.path.join(entry, name)]
            else:
                filename = os.path.join(entry, name + ".js")
                submodule_locations = None

            if not os.path.exists(filename):
                continue

            # sys.stderr.write("loader found `%s`\n" % filename)

            return spec_from_file_location(fullname, filename,
                loader=JavascriptLoader(filename),
                submodule_search_locations=submodule_locations)

        return None # we don't know how to import this

    @staticmethod
    def install():
        if not JavascriptFinder._installed:
            sys.meta_path.insert(0, JavascriptFinder())
            JavascriptFinder._installed = True

class JavascriptLoader(Loader):
    def __init__(self, filename):

        self.filename = filename

    def create_module(self, spec):

        cpath = cache_from_source(spec.origin)
        code = None
        mod_fptr = None
        #if os.path.exists(cpath) and not isNewer(spec.origin, cpath):
        #    try:
        #        code = load_module(cpath)
        #        mod_fptr = types.FunctionType(code, Compiler.defaultGlobals(), spec.name)
        #    except ImportError as e:
        #        pass
        #    except EOFError as e:
        #        pass

        if not mod_fptr:

            compiler = compile_file(spec.origin)

            mod_fptr = compiler.function_body
            code = mod_fptr.__code__
            save_module(cpath, code)

        mod = types.ModuleType(spec.name)

        mod.__name__ = spec.name
        mod.__file__ = spec.origin
        mod.__cached__ = cpath
        # TODO: set package name
        # https://docs.python.org/3/reference/import.html#__package__
        mod.__package__ = spec.name
        mod.__loader__ = self
        mod.__spec__ = spec

        mod.__body__ = mod_fptr

        return mod

    def exec_module(self, module):

        result = module.__body__()
        delattr(module, '__body__')

        if isinstance(result, JsObject):
            for name in JsObject.keys(result):
                if not name.startswith("_"):
                    setattr(module, name, result[name])
        elif isinstance(result, dict):
            for name, attr in result.items():
                if not name.startswith("_"):
                    setattr(module, name, attr)
        else:
            raise ImportError("not a proper JS module")


