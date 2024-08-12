
"""
TODO: if a new include file is added to the project
      a refresh will not pick up the new file
      the server will need to be restarted.
      fix loading new project files

TODO: option for clean build (ignore ast cache)

TODO: js ast cache needs a machine uuid embedded
      daedalus commit hash?
      date? to invalidate the cache after some time

TODO: {"a", b:3} does not produce an error
      missing string after property id

TODO: formatter throw as a keyword does not space arguments
            throw"error"
      similar to else:  }else{; and if: if(

TODO: in daedalus-js, implement a util for fmtFloat and fmtInt

TODO "{x:,7}" should be a syntax error


"""
import os
import sys
import time
from . import __path__
import json
from .lexer import Lexer, Token, TokenError
from .parser import Parser, xform_apply_file
from .transform import TransformExtractStyleSheet, TransformMinifyScope, \
    TransformConstEval, getModuleImportExport, TransformIdentityScope
from .formatter import Formatter
import pickle
import base64
import logging

def findFile(name, search_paths):
    """
    look for a file in a directory, if not found search the
    default resources directory
    """
    for path in search_paths:
        filepath = os.path.abspath(os.path.join(path, name))
        if os.path.isfile(filepath):
            return filepath

    mpath = os.path.join(os.path.split(__path__[0])[0], 'res')
    mfilepath = os.path.normpath(os.path.join(mpath, name))
    if os.path.isfile(mfilepath):
        return mfilepath

    raise FileNotFoundError("%s not found in search paths: %s" % (name, search_paths))

def findModule(name, search_paths):
    if name.endswith('.js'):
        path = findFile(name, search_paths)
    else:
        path_name = name.replace(".", "/")
        try:
            file_name = path_name.split("/")[-1]
            file_path = "%s/%s.js" % (path_name, file_name)
            # print(file_path, search_paths)
            path = findFile(file_path, search_paths)
        except FileNotFoundError:
            path = None

        if path is None:
            file_path = path_name + "/index.js"
            # print(file_path, search_paths)
            path = findFile(file_path, search_paths)
    return path

def merge_imports(dst, src):
    for key, val in src.items():
        if key in dst:
            # TODO: if two files import and rename the same symbol
            # differently this will cause a bug here..
            # would be better to throw an error than trying to support
            dst[key].update(val)
        else:
            dst[key] = val

def merge_ast(a, b):
    token = Token(Token.T_MODULE, 0, 0, "")
    token.children = list(a.children)
    token.children.extend(b.children)
    return token

def buildFileIIFI(mod, exports):
    """
    convert a file into an immediatley invoked function interface.
    the function returns an array and populates the current scope
    with the export names

    used to isolate individual files in a module
    """

    def TOKEN(type, value, *children):
        tok = Token(type, 1, 0, value, children)
        #tok.file = "<file_iifi>"
        return tok

    tok_export_names1 = [TOKEN('T_TEXT', text) for text in sorted(exports)]
    tok_export_names2 = [TOKEN('T_TEXT', text) for text in sorted(exports)]
    tok_exports = TOKEN('T_MODULE', '',
        TOKEN('T_RETURN', 'return',
            TOKEN('T_LIST', '[]', *tok_export_names1)))

    tok_ast = merge_ast(mod, tok_exports)

    # insert the file into a function
    tok_fundef = TOKEN('T_ANONYMOUS_FUNCTION', 'function',
        TOKEN('T_TEXT', 'Anonymous'),
        TOKEN('T_ARGLIST', '()'),
        Token(Token.T_BLOCK, 1, 0, "{}", tok_ast.children))

    # invoke that function and assign return values in current scope
    tok_iifi = TOKEN('T_MODULE', '',
        TOKEN('T_VAR', "const",
            TOKEN('T_ASSIGN', '=',
                TOKEN('T_UNPACK_SEQUENCE', '[]', *tok_export_names2),
                TOKEN('T_FUNCTIONCALL', '',
                    TOKEN('T_GROUPING', '()', tok_fundef),
                    TOKEN('T_ARGLIST', '()')))))

    return tok_iifi

def buildModuleIIFI(modname, mod, imports, exports, merge):
    """
    convert a module into an immediatley invoked function interface.
    the function accepts arguments for the imports and returns an
    object containing the exports.

    used to isolate one module from other modules in the project
    """

    def TOKEN(type, value, *children):
        tok = Token(type, 1, 0, value, children)
        #tok.file = "<module_iifi>"
        return tok

    import_names = sorted(list(imports.keys()))
    argument_names = import_names[:]
    for i, name in enumerate(import_names):
        # TODO: this change is the result of a design bug in the original builder
        #       and an artifact of the changes made to sort_modules, due to needing
        #       better module names for source maps
        #       there is no namespace separation of submodules between packages
        #       the correct thing to do would be to insert a line inside the module function
        #       to unpack the imports.
        #       e.g.
        #       instead of:
        #           (iifi(api, daedalus) { ... })(app.api, daedalus)
        #       use:
        #           (iifi(app, daedalus) { const api = app.api; ... })(app, daedalus)
        # TODO: implement some form of name mangling to prevent name collisions
        #       export * from "@daedalus/api" => 'daedalus_api' instead of 'api'
        #       unclear if still required

        import_names[i] = name.split('.')[-1]
        argument_names[i] = name
        # print("fix name!!", name, import_names[i])
        #if name.endswith('.js'):
        #    import_names[i] = os.path.splitext(os.path.split(name)[1])[0]
        #    argument_names[i] = import_names[i]
        #else:
        #    import_names[i] = name.split('.')[0]
        #    argument_names[i] = name.split('.')[0]

    if modname.endswith('.js'):
        raise ValueError(modname)
    #if modname.endswith('.js'):
    #    sys.stderr.write("warning: module with invalid modname %s\n" % modname)
    #    modname = os.path.splitext(os.path.split(modname)[1])[0]

    tok_import_names = [TOKEN('T_TEXT', text) for text in import_names]
    #tok_argument_names = [TOKEN('T_TEXT', text) for text in argument_names]

    # IFFI argument names need to be unpacked so that minify works
    tok_argument_names = []
    for text in argument_names:
        if '.' in text:
            parts = text.split(".")
            lhs = TOKEN('T_TEXT', parts[0])
            for i in range(1, len(parts)):
                rhs = TOKEN('T_TEXT', parts[i])
                lhs = TOKEN('T_GET_ATTR', ".", lhs, rhs)
            tok_argument_names.append(lhs)
        else:
            tok_argument_names.append(TOKEN('T_TEXT', text))

    tok_export_names = [TOKEN('T_TEXT', text) for text in sorted(exports)]
    tok_exports = TOKEN('T_MODULE', '',
        TOKEN('T_RETURN', 'return',
            TOKEN('T_OBJECT', '{}', *tok_export_names)))

    tok_imports1 = []
    for varname, names in imports.items():
        for src, dst in names.items():
            # TODO: unclear if this is completely correct, what about case like a.b.c
            _x_varname = varname.split('.')[-1]
            tok = TOKEN('T_ASSIGN', '=',
                TOKEN('T_VAR', 'const', TOKEN('T_TEXT', dst)),
                TOKEN('T_GET_ATTR', '.',
                    TOKEN('T_TEXT', _x_varname),
                    TOKEN('T_ATTR', src)))
            tok_imports1.append(tok)
    tok_imports = TOKEN('T_MODULE', '', *tok_imports1)

    tok_ast = merge_ast(tok_imports, mod)
    tok_ast = merge_ast(tok_ast, tok_exports)
    tok_ast.children.insert(0, TOKEN('T_STRING', '"use strict"'))

    tok_fundef = TOKEN('T_ANONYMOUS_FUNCTION', 'function',
        TOKEN('T_TEXT', 'Anonymous'),
        TOKEN('T_ARGLIST', '()', *tok_import_names),
        Token(Token.T_BLOCK, 1, 0, "{}", tok_ast.children))

    if merge:
        tok_iifi = TOKEN('T_MODULE', '',
            TOKEN('T_FUNCTIONCALL', '',
                TOKEN('T_GET_ATTR', '.',
                    TOKEN('T_TEXT', 'Object'),
                    TOKEN('T_TEXT', 'assign')),
                TOKEN('T_ARGLIST', '()',
                    TOKEN('T_TEXT', modname),
                    TOKEN('T_FUNCTIONCALL', '',
                        TOKEN('T_GROUPING', '()', tok_fundef),
                        TOKEN('T_ARGLIST', '()', *tok_argument_names)))))

    else:

        if '.' in modname:
            parts = modname.split('.')

            mod_tok = TOKEN('T_GET_ATTR', '.',
                TOKEN('T_TEXT', parts[0]),
                TOKEN('T_TEXT', parts[1]))

            for i in range(2, len(parts)):
                mod_tok = TOKEN('T_GET_ATTR', '.',
                            mod_tok,
                            TOKEN('T_TEXT', parts[i]))

        else:
            mod_tok = TOKEN('T_TEXT', modname)

        tok_iifi = TOKEN('T_MODULE', '',
            TOKEN('T_ASSIGN', '=',
                mod_tok,
                TOKEN('T_FUNCTIONCALL', '',
                    TOKEN('T_GROUPING', '()', tok_fundef),
                    TOKEN('T_ARGLIST', '()', *tok_argument_names))))

    return tok_iifi

def buildPythonAst(modname, mod, imports, exports):

    def TOKEN(type, value, *children):
        tok = Token(type, 1, 0, value, children)
        tok.file = "<python_ast>"
        return tok

    import_names = sorted(list(imports.keys()))
    argument_names = import_names[:]
    for i, name in enumerate(import_names):
        if name.endswith('.js'):
            import_names[i] = os.path.splitext(os.path.split(name)[1])[0]
            argument_names[i] = import_names[i]
        else:
            import_names[i] = name.split('.')[0]
            argument_names[i] = name.split('.')[0]

    if modname.endswith('.js'):
        sys.stderr.write("warning: module with invalid modname %s\n" % modname)
        modname = os.path.splitext(os.path.split(modname)[1])[0]

    [TOKEN('T_TEXT', text) for text in import_names]
    [TOKEN('T_TEXT', text) for text in argument_names]
    tok_export_names = [TOKEN('T_TEXT', text) for text in sorted(exports)]
    tok_exports = TOKEN('T_MODULE', '',
        TOKEN('T_RETURN', 'return',
            TOKEN('T_OBJECT', '{}', *tok_export_names)))

    tok_imports1 = []
    for varname, names in imports.items():
        for src, dst in names.items():
            tok = TOKEN('T_ASSIGN', '=',
                TOKEN('T_VAR', 'const', TOKEN('T_TEXT', dst)),
                TOKEN('T_GET_ATTR', '.',
                    TOKEN('T_TEXT', varname),
                    TOKEN('T_ATTR', src)))
            tok_imports1.append(tok)
    tok_imports = TOKEN('T_MODULE', '', *tok_imports1)

    tok_ast = merge_ast(tok_imports, mod)
    tok_ast = merge_ast(tok_ast, tok_exports)
    tok_ast.children.insert(0, TOKEN('T_STRING', '"use strict"'))

    return tok_ast

class BuildError(Exception):
    def __init__(self, filepath, token, lines, message, raw_message=None):
        super(BuildError, self).__init__(message)
        self.filepath = filepath
        self.line = -1
        self.column = -1
        self.raw_message = raw_message
        self.token = token
        self.lines = lines

        if token:
            self.line = token.line
            self.column = token.index

    @staticmethod
    def fromTokenError(filepath, error):
        e = BuildError(filepath, error.token, [], str(error))
        e.line = error.token.line
        e.column = error.token.index
        return e

class JsFile(object):
    def __init__(self, path, name=None, source_type=1, platform=None, quiet=False):
        super(JsFile, self).__init__()

        self.path = path
        self.ast = None
        # imports are a dictionary of file_path => list of included names
        self.imports = {}
        # module_imports are a dictionary for module_name => list of included names
        self.module_imports = {}
        # exports are a list of exported names from this ast module
        self.exports = []

        # styles is a list of strings, each string is a single valid css rule
        self.styles = []

        self.source_type = source_type
        self.source = None
        self.mtime = 0  # modified time from the last time this was loaded
        self.size = 0
        self.quiet = quiet

        self.lexer_opts = {}

        if not name:
            self.name = os.path.splitext(os.path.split(name)[1])[0]
        else:
            self.name = name

        if '.js' in self.name:
            raise Exception(self.name)

        # if a platform specific implementation of this file
        # exists use that file instead
        self.source_path = path
        if platform:
            fdir, fname = os.path.split(path)
            fname, _ = os.path.splitext(fname)
            platpath = os.path.join(fdir, "%s.%s.js" % (fname, platform))
            if os.path.exists(platpath):
                self.source_path = platpath

    def __repr__(self):
        return f"<JsFile({self.name})"

    def _newBuildError(self, token, ex):
        """
            token: the token that was the source of the exception
            ex: exception instance or string
        """
        source = None

        if self.source:
            source = self.source
        elif self.source_path and os.path.exists(self.source_path):
            source = self.getSource()

        if source:
            offset_b = 3 # lines before error
            offset_a = 3 # lines after error

            source_lines = source.split("\n")

            line_start = token.line - offset_b
            line_end = min(token.line + offset_a, len(source_lines))

            b_lines = ["%4d: %s" % (i + 1, source_lines[i]) for i in range(line_start, token.line)]
            a_lines = ["%4d: %s" % (i + 1, source_lines[i]) for i in range(token.line, line_end)]

            lines = b_lines + ["      " + " " * token.index + "^"] + a_lines
        else:
            lines = []

        if isinstance(ex, BaseException):
            org_msg = ex.original_message
            msg = str(ex)
        else:
            org_msg = msg = str(ex)

        return BuildError(self.source_path, token, lines, org_msg, msg)

    def getSource(self):

        with open(self.source_path, "r") as rf:
            return rf.read()

    def load(self, force=False):

        t1 = time.time()

        dirpath, filename = os.path.split(self.source_path)
        cachename = os.path.splitext(filename)[0] + ".ast"
        cachedir = os.path.join(dirpath, "__pycache__")
        cachepath = os.path.join(dirpath, "__pycache__", cachename)

        self.ast = None
        # try to load the file data from the cache
        if force is False and os.path.exists(cachepath):

            mtime1 = os.stat(self.source_path).st_mtime
            mtime2 = os.stat(cachepath).st_mtime

            if mtime1 < mtime2:
                try:
                    with open(cachepath, 'rb') as f:
                        self.size, self.ast, self.imports, \
                            self.module_imports, self.exports, \
                            self.styles = pickle.load(f)
                except pickle.PickleError:
                    self.ast = None
                except ValueError:
                    self.ast = None

        if self.ast is None:

            source = self.getSource()
            error = None
            try:
                tokens = Lexer(self.lexer_opts).lex(source)
                for token in tokens:
                    token.file = self.source_path
                parser = Parser()
                parser.module_name = self.path
                ast = parser.parse(tokens)
                TransformConstEval().transform(ast)
                uid = TransformExtractStyleSheet.generateUid(self.source_path)
                tr1 = TransformExtractStyleSheet(uid)
                tr1.transform(ast)
                self.styles = tr1.getStyles()
            except TokenError as e:
                error = self._newBuildError(e.token, e)

            if error:
                raise error

            self.size = len(source)
            try:
                self.ast, self.imports, self.module_imports, self.exports = \
                    getModuleImportExport(ast, self.source_type != 2)
            except TokenError as e:
                raise BuildError.fromTokenError(self.source_path, e)

            if not os.path.exists(cachedir):
                os.makedirs(cachedir)

            data = (self.size, self.ast, self.imports,
                self.module_imports, self.exports, self.styles)

            # reset the file path for all tokens in the ast
            # use the absolute dotted name of this file
            xform_apply_file(self.ast, self.name)

            with open(cachepath, 'wb') as f:
                pickle.dump(data, f)

        self.mtime = os.stat(self.source_path).st_mtime

        t2 = time.time()

        if not self.quiet:
            sys.stderr.write("%10d %.2f %s\n" % (
                self.size, t2 - t1, self.source_path))

    def reload(self):
        if self.source_path:
            if self.mtime == 0:
                self.load(False)
            else:
                mtime = os.stat(self.source_path).st_mtime
                if mtime > self.mtime:
                    self.load()
            return True
        return False

class JsModule(object):
    def __init__(self, index_js, module_name=None, platform=None, quiet=False):
        super(JsModule, self).__init__()
        self.index_js = index_js
        self.files = {index_js.path: index_js}
        self.static_data = None

        self.module_name = module_name or os.path.split(os.path.split(index_js.path)[0])[1]

        self.module_exports = set()
        self.module_imports = {}
        self.static_exports = set()
        self.import_paths = {}
        self.ast = None
        self.source_size = 0
        self.uid = 0
        self.platform = platform
        self.quiet = quiet
        self.lexer_opts = {}

    def __repr__(self):
        return f"<JsModule({self.module_name})"

    def _getFiles(self):
        # sort include files
        jsf = self.index_js
        queue = [(jsf, 0)]
        depth = {jsf.path: 0}
        while queue:
            c, d = queue.pop(0)
            d = depth[c.path]

            if d > len(self.files):
                msg = "include cycle detected."
                raise BuildError(c.path, None, [], msg)

            for p in self.import_paths[c.path]:
                if p not in depth:
                    depth[p] = d + 1
                else:
                    depth[p] = max(depth[p], d + 1)
                queue.append((self.files[p], d + 1))

        order = sorted(depth.keys(), key=lambda p: depth[p], reverse=True)
        self.source_size = sum([self.files[p].size for p in order])
        return [self.files[p] for p in order]

    def load(self):
        self.module_imports = {}
        queue = [self.index_js]
        files = {}
        module_imports = {}
        module_exports = set()
        self.dirty = False
        while queue:
            jsf = queue.pop()
            if jsf.path in files:
                continue
            files[jsf.path] = jsf
            result = jsf.reload()
            if result:
                self.dirty = True

            merge_imports(module_imports, jsf.module_imports)
            module_exports |= set(jsf.exports)

            moddir = os.path.split(self.index_js.path)[0]
            self.import_paths[jsf.path] = []
            for name in jsf.imports.keys():
                path = os.path.normpath(os.path.join(moddir, name))
                self.import_paths[jsf.path].append(path)
                if path in files:
                    pass
                elif path not in self.files:
                    tmp_name = os.path.splitext(os.path.split(path)[1])[0]
                    if self.module_name:
                        tmp_name = self.module_name + "." + tmp_name
                    jf = JsFile(path, tmp_name, 2, platform=self.platform, quiet=self.quiet)
                    jf.lexer_opts = self.lexer_opts
                    queue.append(jf)
                    self.dirty = True
                else:
                    queue.append(self.files[path])
        if self.dirty:
            self.ast = None

        self.files = files
        self.module_imports = module_imports
        self.module_exports = module_exports
        return files

    def name(self):
        return self.module_name # self.index_js.name

    def getAST(self, merge=False):
        t1 = time.time()

        if self.ast and not self.dirty:
            return self.ast

        order = self._getFiles()

        if len(order) > 1:
            if self.static_data:
                ast = self.static_data
            else:
                ast = Token(Token.T_MODULE, 0, 0, "")

            for jsf in order:
                ast = merge_ast(ast, buildFileIIFI(jsf.ast, jsf.exports))
        else:
            ast = order[0].ast

        self.styles = sum([jsf.styles for jsf in order], [])

        all_exports = self.module_exports | self.static_exports

        if self.platform == "python":
            self.ast = buildPythonAst(self.name(), ast, self.module_imports, all_exports)
        else:
            self.ast = buildModuleIIFI(self.name(), ast, self.module_imports, all_exports, merge)

        self.dirty = False
        t2 = time.time()
        if not self.quiet:
            sys.stderr.write("%10s %.2f rebuild ast: %s\n" % ('', t2 - t1, self.name()))
        return self.ast

    def setStaticData(self, data):
        # parse the user provided static data
        lines = []
        self.static_exports = set()
        if data:
            for key, value in data.items():
                line = "const %s=%s;" % (key, json.dumps(value))
                lines.append(line)
                self.static_exports.add(key)
        if lines:
            source = "\n".join(lines)
            tokens = Lexer(self.lexer_opts).lex(source)
            ast = Parser().parse(tokens)
            self.static_data = ast
        else:
            self.static_data = None

class Builder(object):
    def __init__(self, search_paths, static_data, platform=None):
        super(Builder, self).__init__()
        self.error = None
        self.search_paths = search_paths

        self.files = {}
        self.modules = {}
        self.root_module = None
        self.source_types = {}
        self.quiet = True
        self.disable_warnings = False
        self.lexer_opts = {}

        self.webroot = "/"

        if static_data is None:
            static_data = {}

        if 'daedalus' not in static_data:
            static_data['daedalus'] = {}

        if platform is not None:
            static_data['daedalus']['build_platform'] = platform
        else:
            static_data['daedalus']['build_platform'] = 'web'

        self.platform = platform
        self.static_data = static_data

        self.html_title = "Daedalus"

    def setTitle(self, title):
        self.html_title = title

    def find(self, name):

        return findFile(name, self.search_paths)

    def _name2path(self, name):
        return findModule(name, self.search_paths)

    def _discover(self, jsm):

        queue = [jsm]
        visited = set()

        modroots = [os.path.abspath(p) for p in self.search_paths]

        while queue:
            jsm = queue.pop()
            files = jsm.load()
            self.files.update(files)
            # print("visit", jsm.name(), list(jsm.module_imports.keys()))
            #print("   ", ','.join(list([x.name for x in files.values()])))

            for modname in jsm.module_imports.keys():
                # modname here is the name of the module, as imported in the source code
                # this section determines the true name of the module, and where it is located

                #if modname.startswith("."):
                #    # allow `$import('daedalus', {})`  ==> daedalus not daedalus.res.daedalus
                #    # allow `$import('api.requests', {})` ==> api.requests
                #    # TODO: allow `$import('.requests', {})` ==> api.requests
                #    modname = absname

                # TODO: chicken/egg problem: modname must be the complete dotted name
                modpath = os.path.abspath(self._name2path(modname))

                modpath = self._name2path(modname)
                #modname = os.path.split(os.path.split(modpath)[0])[1]

                commonpath = ""
                for root in modroots:
                    common = os.path.commonpath([root, modpath])
                    if len(common) > len(commonpath):
                        commonpath = common
                absname = os.path.splitext(modpath[len(commonpath)+1:])[0].replace("/", ".")
                if absname == "daedalus.res.daedalus.daedalus":
                    absname = "daedalus.daedalus"

                if modpath not in self.files:
                    jsname = absname
                    jf = JsFile(modpath, jsname, 2, platform=self.platform, quiet=self.quiet)
                    jf.lexer_opts = self.lexer_opts
                    self.files[modpath] = jf

                if modpath not in self.modules:
                    jm = JsModule(self.files[modpath], module_name=modname, platform=self.platform, quiet=self.quiet)
                    jm.lexer_opts = self.lexer_opts
                    self.modules[modpath] = jm
                    self.modules[modpath].setStaticData(self.static_data.get(modname, None))

                if modpath not in visited:
                    queue.append(self.modules[modpath])
                    visited.add(modpath)
                

    def discover(self, path):
        """
        load all imported modules and files starting with the given file
        """

        source_type = 1 # TODO: deprecate and remove
                        # source_map == 2 is only used to surpress warnings

        if path.endswith(".js"):
            path = os.path.abspath(path)
            modname = path.replace("\\","/").split("/")[-1]
            if modname.endswith(".js"):
                modname = modname[:-3]
        else:
            modname = path
            path = self._name2path(modname)

        jf = JsFile(path, modname, source_type, platform=self.platform, quiet=self.quiet)
        jf.lexer_opts = self.lexer_opts
        self.files[path] = jf
        jm = JsModule(self.files[path], modname, platform=self.platform, quiet=self.quiet)
        jm.lexer_opts = self.lexer_opts
        jm.setStaticData(self.static_data.get(modname, None))
        self.modules[path] = jm

        self.root_module = jm

        self._discover(jm)

        self._fix_export_star()

        return jm

    def _fix_export_star(self):

        name2mod = {mod.module_name: mod for mod in self.modules.values()}

        for path, mod in self.modules.items():

            # resolve `export *` where all names in the chil module should be exported
            # with along with the current module
            values = list(mod.module_exports)
            print(mod.module_name, values)
            for name in values:
                if name.endswith("/*"):
                    print("fixing:", names)
                    mod.module_exports.remove(name)
                    name = name[:-2]
                    mod.module_exports |= name2mod[name].module_exports
            
            for modname, names in mod.module_imports.items():
                
                if "*" in names:
                    other = name2mod[modname]
                    #print()
                    #print(path)
                    #print(mod.module_name)
                    #print(mod.module_imports.keys())
                    #print(other.module_name)
                    #print(other.module_exports)
                    mod.module_imports[modname] = {v:v for v in other.module_exports}

    def _sort_modules(self, jsm):
        name2mod = {m.name(): m for m in self.modules.values()}
        queue = [(jsm, 0)]
        depth = {jsm.name(): 0}
        while queue:
            m, d = queue.pop(0)
            d = depth[m.name()]

            _x_module_imports = {}
            for n in m.module_imports:

                original_name = n
                # TODO: this seems like something that should have been resolved
                #       when building the imports list
                if n not in name2mod:
                    t1 = m.name() + "." + n
                    t2 = self.root_module.name() + "." + n # TODO: root module name
                    for t in [t1, t2]:
                        if t in name2mod:
                            n = t
                            break

                if n not in depth:
                    depth[n] = d + 1
                else:
                    depth[n] = max(depth[n], d + 1)

                if n not in name2mod:
                    print(list(sorted(name2mod.keys())))
                jsm = name2mod[n]
                _x_module_imports[original_name] = n

                # worst case depth is a simple linked list with length
                # of N where N is the number of modules. If the computed
                # depth is greater than that, then there is a cycle somewhere
                if d > len(self.modules):
                    msg = "import cycle detected. %s imports %s" % (jsm.index_js.name, m.index_js.name)
                    raise BuildError(m.index_js.path, None, [], msg)
                queue.append((jsm, d + 1))

            # TODO: this is a hack, can the imports be fixed prior to sort?
            m.module_imports = {_x_module_imports[k]:v for k,v in m.module_imports.items()}

        order = sorted(depth.keys(), key=lambda n: depth[n], reverse=True)
        return [name2mod[n] for n in order]

    def build_module(self, path, minify=False):
        jsm = self.discover(path)
        ast = jsm.getAST()

        return ast

    def _build_impl(self, path, standalone=False, sourcemap=False, minify=False):
        t1 = time.time()
        try:

            jsm = self.discover(path)

            if len(jsm.module_exports) == 0:
                raise BuildError(jsm.index_js.path, None, [], "does not export any symbols")

            if len(jsm.module_exports) > 1:
                sys.stderr.write("warning: root module exports more than one symbol\n")

            self.root_exports = jsm.module_exports

            if standalone is False:
                order = self._sort_modules(jsm)
                ast = Token(Token.T_MODULE, 0, 0, "")
                source_size = 0
                mod_structure = {}

                def _get(name):
                    struct = mod_structure
                    for part in name.split('.'):
                        if part not in struct:
                            struct[part] = {}
                        struct = struct[part]
                    return struct

                for mod in order:
                    _get(mod.name())

                for key, struct in mod_structure.items():
                    if struct:
                        source = '%s = %s' % (key, json.dumps(struct))
                        tokens = Lexer(self.lexer_opts).lex(source)
                        ast = merge_ast(ast, Parser().parse(tokens))

                for mod in order:
                    struct = _get(mod.name())
                    ast2 = mod.getAST(merge=len(struct) > 0)
                    ast = merge_ast(ast, ast2)
                    source_size += mod.source_size
                

                styles = sum([mod.styles for mod in order], [])
            else:
                ast = jsm.getAST()
                styles = jsm.styles
                source_size = jsm.source_size

            css = "\n".join(styles)
            error = None
            self.globals = {}


            if minify:
                ast = Token.deepCopy(ast)
                xform = TransformMinifyScope()
                xform.disable_warnings = self.disable_warnings
                self.globals = xform.transform(ast)

            else:
                ast_source = ast
                ast = Token.deepCopy(ast)

                xform = TransformIdentityScope()
                xform.disable_warnings = self.disable_warnings
                try:
                    self.globals = xform.transform(ast)
                except TokenError as e:

                    # certain syntax errors (double defines)
                    # can trigger this

                    # feels like a hack.
                    name2path = {}
                    for path, jf in self.files.items():
                        name2path[jf.name] = path
                    e.token.file = name2path[e.token.file]

                    # TODO: the source file could be None: need to fix this
                    nodes = [ast_source]
                    sources = set()
                    while nodes:
                        node = nodes.pop(0)
                        sources.add(node.file)
                        nodes.extend(node.children)
                    print(sources)
                    raise e


            formatter = Formatter(opts={'minify': minify})

            js = formatter.format(ast)

            if sourcemap:
                sources = formatter.sourcemap.sources
                name2path = {}
                url2path = {}
                url2index = {}

                # TODO: clean this up
                #
                for path, jf in self.files.items():
                    name2path[jf.name] = path

                for srcname in sources.keys():

                    if srcname in name2path:
                        abspath = name2path[srcname]
                        # TODO: optional relative path to support github actions
                        # TODO: support typescript when the original path is typescript
                        url = f'srcmap/{srcname.replace(".", "/")}.js'
                        url2index[url] = sources[srcname]
                        url2path[url] = abspath
                        #print("adding sourcemap", url)
                    else:
                        print("sourcemap not found:", srcname)

                formatter.sourcemap.sources = url2index
                formatter.sourcemap.source_routes = url2path

                # the sourcemap payload is:
                #  - a dictionary mapping a url to a local path
                #  - a json object, the source map data.
                self.sourcemap_obj = formatter.sourcemap.getSourceMap()
                self.servermap = formatter.sourcemap.getServerMap()
                self.sourcemap_url2path = url2path


        except TokenError as e:
            logging.exception("error building module")
            filepath = ""
            lines = []
            if e.token.file:
                jsf = self.files[e.token.file]
                filepath = e.token.file
                source = jsf.getSource()
                source_lines = source.split("\n")
                line_start = e.token.line - 3
                line_end = e.token.line + 3
                lines = source_lines[line_start:e.token.line]
                lines.append(" " * e.token.index + "^")
                lines.extend(source_lines[e.token.line:line_end])
            error = BuildError(filepath, e.token, lines, e.original_message, str(e))

        if error:
            raise error

        # return True

        if self.globals:
            export_name = self.globals[jsm.name()] + "." + list(jsm.module_exports)[0]
        else:
            export_name = jsm.name() + "." + list(jsm.module_exports)[0]

        final_source_size = len(js)
        p = 100 * final_source_size / source_size
        t2 = time.time()
        if not self.quiet:
            sys.stderr.write("%10d %.2f %.2f%% of %d bytes\n" % (final_source_size, t2 - t1, p, source_size))

        return css, js, export_name

    def build(self, path, minify=False, onefile=False, sourcemap=False):
        self.error = None
        # make this have API functions which
        # can be overridden
        try:
            css, js, root = self._build_impl(path, sourcemap=sourcemap, minify=minify)
        except BuildError as e:
            return self.build_error(e)
        except FileNotFoundError as e:
            logging.exception(f"file not found when building path: {path}")
            return self.build_error(e)

        if sourcemap:
            # inject the file content into the sourcemap

            sources = []
            for src in self.sourcemap_obj['sources']:
                path = self.sourcemap_url2path[src]
                with open(path) as rf:
                    sources.append(rf.read())
            self.sourcemap_obj['sourcesContent'] = sources

            srcmap_content = json.dumps(self.sourcemap_obj)

            if onefile:

                header = "//# sourceMappingURL=data:application/json;base64,"
                header += base64.b64encode(srcmap_content.encode("UTF-8")).decode("utf-8")
                header += "\n"
                js = header + js

            else:
                js = "//# sourceMappingURL=index.js.map\n" + js

            self.sourcemap = (self.sourcemap_url2path, srcmap_content)

        else:
            #srcmap_content = "" #json.dumps(self.sourcemap_obj)
            self.sourcemap = ({}, "")



        try:
            index_html = self.find("index.%s.html" % self.platform)
        except FileNotFoundError:
            index_html = None

        if index_html is None:
            index_html = self.find("index.html")

        with open(index_html, "r") as hfile:
            html = hfile.read()

        if self.globals and 'daedalus' in self.globals:
            render_function = self.globals['daedalus'] + '.render'
        else:
            render_function = 'daedalus.render'

        try:
            self.favicon_path = findFile("favicon.ico", self.search_paths)
        except FileNotFoundError:
            self.favicon_path = None

        html = html \
            .replace("${PATH}", self.getPlatformPathPrefix().rstrip("/")) \
            .replace("<!--TITLE-->", self.getHtmlTitle()) \
            .replace("<!--FAVICON-->", self.getHtmlFavIcon()) \
            .replace("<!--STYLE-->", self.getHtmlStyle(css, onefile)) \
            .replace("<!--SOURCE-->", self.getHtmlSource(js, onefile)) \
            .replace("<!--EVENT-->", self.getHtmlEvent(onefile)) \
            .replace("<!--RENDER-->", self.getHtmlRender(render_function, root))

        return css, js, html

    def build_error(self, e):

        message = [str(e)]
        message.append("\nError:\n")

        filepath =  getattr(e, 'filepath', '<>')
        message.append("Filepath: %s\n" % filepath)
        if hasattr(e, 'line'):
            message.append("Line: %s\n" % e.line)
        message.append("message: %s\n" % e)
        if hasattr(e, 'lines'):
            if e.lines:
                message.append("Source:\n")
                message.append("\n".join(e.lines))
                message.append("\n")

        message = "".join(message)
        sys.stdout.write(message)

        # BuildError(filepath, token, lines, message, raw_message)
        self.error = Exception(message)

        _filename = getattr(e, 'filepath', '<>')
        print("=--= filepath", _filename)
        print("=--= filepath", getattr(e, 'filename', '<>'))
        _line = getattr(e, 'line', -1)
        _column = getattr(e, 'column', -1)
        _raw_message = getattr(e, 'raw_message', str(e))
        _lines = getattr(e, 'lines', [])
        html = (
            '<!DOCTYPE html>'
            '<meta charset="UTF-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1,shrink-to-fit=no">'
            '<html lang="en">'
            '<head>'
            '<title>Compile Error</title>'
            '</head>'
            '<body>'
            '%s'
            '%s'
            '%s'
            '%s'
            '<hr><pre>%s</pre><hr>'
            '%s'
            '</body>'
            '</html>'
        ) % (
            '<p>Error: %s</p>' % str(e),
            '<p>File: %s</p>' % _filename,
            '' if _line < 0 else '<p>Line: %s</p>' % _line,
            '' if _column < 0 else '<p>Column: %s</p>' % _column,
            "<br>".join(_lines),
            '' if not _raw_message else '<p>Raw Error: %s</p>' % _raw_message,
        )
        return "", "", html

    def getPlatformPathPrefix(self):
        """ get the resource path for the platform"""
        # TODO: hardcoding the platform prefix for now
        # allow for a user defined value

        if self.platform == "android":
            return "/android_asset/site/"
        elif self.platform == "qt":
            return "./"
        else:
            return self.webroot

    def getHtmlTitle(self):

        return f'<title>{self.html_title}</title>'

    def getHtmlFavIcon(self):

        prefix = self.getPlatformPathPrefix()

        return f'<link rel="icon" type="image/x-icon" href="{prefix}favicon.ico" />'

    def getHtmlStyle(self, css, onefile):

        prefix = self.getPlatformPathPrefix()

        if not css:
            return ""
        elif onefile:
            return '<style type="text/css">\n%s\n</style>' % css
        else:
            return f'<link rel="stylesheet" type="text/css" href="{prefix}static/index.css">'

    def getHtmlSource(self, js, onefile):

        prefix = self.getPlatformPathPrefix()

        if onefile:
            return '<script type="text/javascript">\n%s\n</script>' % js
        else:
            return f'<script type="text/javascript" src="{prefix}static/index.js"></script>'

    def getHtmlEvent(self, onefile):
        """
        Returns platform dependent HTML/JS for handling API gateways
        """
        self.getPlatformPathPrefix()

        if self.platform == "android":
            return "<script type=\"text/javascript\">\n" \
                "AndroidEvents = {}\n" \
                "function registerAndroidEvent(name, callback) {\n" \
                "    AndroidEvents[name] = callback;\n" \
                "}\n" \
                "function invokeAndroidEvent(name, payload) {\n" \
                "    if (!!AndroidEvents[name]) {\n" \
                "        AndroidEvents[name](JSON.parse(payload));\n" \
                "    } else {\n" \
                "        console.error(\"unregistered event: \" + name);\n" \
                "    }\n" \
                "}\n" \
                "</script>\n"
        if self.platform == "qt":
            # TODO: does src need {[refix]}
            return "<script type=\"text/javascript\" src=\"static/qwebchannel.js\"></script>\n" \
                "<script type=\"text/javascript\">\n" \
                "window.channel = new QWebChannel(qt.webChannelTransport, (channel)=>{\n" \
                "    console.log(\"channel init\")\n" \
                "})\n" \
                "</script>"

        return ""

    def getHtmlRender(self, render_function, root):
        """
        generate the script which will render the root element

        the script removes all existing children of the root dom node
        and then mounts the root element.
        """
        # construct the document root node first, so that the javascript
        # is parsed and syntax errors can be uncovered. may delay page rendering
        lines = [
            '<script type="text/javascript">',
            'const document_node = new %s();' % (root),
            'const document_root = document.getElementById("root");',
            'while (document_root.hasChildNodes()) {',
            '    document_root.removeChild(document_root.lastChild);',
            '}',
            '%s(document_root, document_node)' % (render_function),
            '</script>',
        ]

        return "\n".join(lines)

