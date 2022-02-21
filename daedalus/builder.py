
import os
import sys
import time
from . import __path__
import json
from .lexer import Lexer, Token, TokenError
from .parser import Parser
from .transform import TransformExtractStyleSheet, TransformMinifyScope, \
    TransformConstEval, getModuleImportExport
from .formatter import Formatter
from ast import literal_eval

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

    raise FileNotFoundError(name)

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
        tok.file = "<file_iifi>"
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
        tok.file = "<module_iifi>"
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

    tok_import_names = [TOKEN('T_TEXT', text) for text in import_names]
    tok_argument_names = [TOKEN('T_TEXT', text) for text in argument_names]
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

    tok_import_names = [TOKEN('T_TEXT', text) for text in import_names]
    tok_argument_names = [TOKEN('T_TEXT', text) for text in argument_names]
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

class JsFile(object):
    def __init__(self, path, name=None, source_type=1, platform=None, quiet=False):
        super(JsFile, self).__init__()
        self.path = path
        self.imports = {}
        self.module_imports = {}
        self.default_export = None
        self.exports = []
        self.source_type = source_type
        self.mtime = 0
        self.size = 0
        self.ast = None
        self.styles = []
        self.quiet = quiet

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
            dir, _ = os.path.split(path)
            platpath = os.path.join(dir, "%s.%s.js" % (name, platform))
            if os.path.exists(platpath):
                self.source_path = platpath

    def _newBuildError(self, token, ex):
        """
            token: the token that was the source of the exception
            ex: exception instance or string
        """
        if self.source:
            source_lines = self.source.split("\n")
            line_start = token.line - 3
            line_end = min(token.line + 3, len(source_lines))
            print(len(source_lines), line_start, line_end)
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

    def load(self):

        t1 = time.time()
        self.source = self.getSource()
        self.size = len(self.source)

        error = None
        try:
            tokens = Lexer().lex(self.source)
            for token in tokens:
                token.file = self.source_path
            parser = Parser()
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

        self.ast = self._get_imports_exports(ast)

        t2 = time.time()

        self.mtime = os.stat(self.source_path).st_mtime

        if not self.quiet:
            sys.stderr.write("%10d %.2f %s\n" % (len(self.source), t2 - t1, self.source_path))

    def _get_imports_exports(self, ast):

        ast, imports, module_imports, exports = getModuleImportExport(ast, self.source_type != 2)

        self.imports = imports
        self.module_imports = module_imports
        self.exports = exports

        return ast

    def reload(self):
        if self.source_path:
            mtime = os.stat(self.source_path).st_mtime
            if mtime > self.mtime:
                self.load()
                return True
        return False

class JsModule(object):
    def __init__(self, index_js, platform=None, quiet=False):
        super(JsModule, self).__init__()
        self.index_js = index_js
        self.files = {index_js.path: index_js}
        self.static_data = None
        self.module_exports = set()
        self.module_imports = {}
        self.static_exports = set()
        self.import_paths = {}
        self.ast = None
        self.source_size = 0
        self.uid = 0
        self.platform = platform
        self.quiet = quiet

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
                    queue.append(JsFile(path, tmp_name, 2, platform=self.platform, quiet=self.quiet))
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
        return self.index_js.name

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
            tokens = Lexer().lex(source)
            ast = Parser().parse(tokens)
            self.static_data = ast
        else:
            self.static_data = None

class Builder(object):
    def __init__(self, search_paths, static_data, platform=None):
        super(Builder, self).__init__()
        self.search_paths = search_paths

        self.files = {}
        self.modules = {}
        self.source_types = {}
        self.quiet = True
        self.disable_warnings = False

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
        if name.endswith('.js'):
            path = self.find(name)
        else:
            path_name = name.replace(".", "/")
            try:
                file_name = path_name.split("/")[-1]
                path = self.find("%s/%s.js" % (path_name, file_name))
            except FileNotFoundError:
                path = None

            if path is None:
                path = self.find(path_name + "/index.js")

        return path

    def _discover(self, jsm):

        queue = [jsm]
        visited = set()
        while queue:
            jsm = queue.pop()
            files = jsm.load()
            self.files.update(files)

            for modname in jsm.module_imports.keys():
                modpath = self._name2path(modname)

                if modpath not in self.files:
                    if modname.endswith(".js"):
                        modname = os.path.splitext(os.path.split(modpath)[1])[0]
                    self.files[modpath] = JsFile(modpath, modname, 2, platform=self.platform, quiet=self.quiet)

                if modpath not in self.modules:
                    self.modules[modpath] = JsModule(self.files[modpath], platform=self.platform, quiet=self.quiet)
                    self.modules[modpath].setStaticData(self.static_data.get(modname, None))

                if modpath not in visited:
                    queue.append(self.modules[modpath])
                    visited.add(modpath)

    def discover(self, path):
        """
        load all imported modules and files starting with the given file
        """

        if path.endswith(".js"):
            source_type = 1
            modname = os.path.splitext(os.path.split(path)[1])[0]
        else:
            modname = path
            path = self._name2path(modname)
            source_type = 2

        if path not in self.files:
            # for the root file check pwd otherwise use findFile
            tmp = os.path.abspath(path)
            if os.path.exists(tmp):
                path = tmp
            else:
                path = self._name2path(path)

        if path not in self.files:
            name = os.path.splitext(os.path.split(path)[1])[0]
            self.files[path] = JsFile(path, name, source_type, platform=self.platform, quiet=self.quiet)

        if self.files[path].source_type != source_type:
            raise Exception("incompatible types")

        if path not in self.modules:
            self.modules[path] = JsModule(self.files[path], platform=self.platform, quiet=self.quiet)
            self.modules[path].setStaticData(self.static_data.get(modname, None))

        self._discover(self.modules[path])

        return self.modules[path]

    def _sort_modules(self, jsm):
        name2path = {m.name(): m.index_js.path for m in self.modules.values()}
        queue = [(jsm, 0)]
        depth = {jsm.index_js.path: 0}
        while queue:
            m, d = queue.pop(0)
            d = depth[m.index_js.path]
            for n in m.module_imports:
                if n.endswith(".js"):
                    n = os.path.splitext(os.path.split(n)[1])[0]
                p = name2path[n]
                if p not in depth:
                    depth[p] = d + 1
                else:
                    depth[p] = max(depth[p], d + 1)

                jsm = self.modules[p]

                # worst case depth is a simple linked list with length
                # of N where N is the number of modules. If the computed
                # depth is greater than that, then there is a cycle somewhere
                if d > len(self.modules):
                    msg = "import cycle detected. %s imports %s" % (jsm.index_js.name, m.index_js.name)
                    raise BuildError(m.index_js.path, None, [], msg)
                queue.append((jsm, d + 1))

        order = sorted(depth.keys(), key=lambda p: depth[p], reverse=True)
        return [self.modules[p] for p in order]

    def build_module(self, path, minify=False):
        jsm = self.discover(path)
        ast = jsm.getAST()

        return ast

    def _build_impl(self, path, standalone=False, minify=False):
        t1 = time.time()

        jsm = self.discover(path)

        if len(jsm.module_exports) == 0:
            raise BuildError(jsm.index_js.path, None, [], "does not export any symbols")

        if len(jsm.module_exports) > 1:
            sys.stderr.write("warning: root module exports more than one symbol\n")

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
                    tokens = Lexer().lex(source)
                    ast = merge_ast(ast, Parser().parse(tokens))

            for mod in order:
                struct = _get(mod.name())
                ast = merge_ast(ast, mod.getAST(merge=len(struct) > 0))
                source_size += mod.source_size

            styles = sum([mod.styles for mod in order], [])
        else:
            ast = jsm.getAST()
            styles = jsm.styles
            source_size = jsm.source_size



        css = "\n".join(styles)
        error = None
        try:
            self.globals = {}

            if minify:
                ast = Token.deepCopy(ast)
                xform = TransformMinifyScope()
                xform.disable_warnings = self.disable_warnings
                self.globals = xform.transform(ast)

            formatter = Formatter(opts={'minify': minify})
            js = formatter.format(ast)

        except TokenError as e:
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

    def build(self, path, minify=False, onefile=False):
        # make this have API functions which
        # can be overridden

        try:
            css, js, root = self._build_impl(path, minify=minify)
        except BuildError as e:
            return self.build_error(e)

        script = '<script src="/static/index.js"></script>'
        try:
            index_html = self.find("index.%s.html" % self.platform)
        except FileNotFoundError as e:
            index_html = None

        if index_html is None:
            index_html = self.find("index.html")
        with open(index_html, "r") as hfile:
            html = hfile.read()

        if self.globals and 'daedalus' in self.globals:
            render_function = self.globals['daedalus'] + '.render'
        else:
            render_function = 'daedalus.render'

        html = html \
            .replace("${PATH}", self.getPlatformPathPrefix().rstrip("/")) \
            .replace("<!--TITLE-->", self.getHtmlTitle()) \
            .replace("<!--FAVICON-->", self.getHtmlFavIcon()) \
            .replace("<!--STYLE-->", self.getHtmlStyle(css, onefile)) \
            .replace("<!--SOURCE-->", self.getHtmlSource(js, onefile)) \
            .replace("<!--EVENT-->", self.getHtmlEvent(js, onefile)) \
            .replace("<!--RENDER-->", self.getHtmlRender(render_function, root))

        return css, js, html

    def build_error(self, e):
        sys.stderr.write("\nError:\n")
        sys.stderr.write("Filepath: %s\n" % e.filepath)
        sys.stderr.write("Line: %s\n" % e.line)
        sys.stderr.write("message: %s\n" % e)
        if e.lines:
            sys.stderr.write("Source:\n")
            sys.stderr.write("\n".join(e.lines))
            sys.stderr.write("\n")

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
            '' if not e.filepath else '<p>File: %s</p>' % e.filepath,
            '' if e.line < 0 else '<p>Line: %s</p>' % e.line,
            '' if e.column < 0 else '<p>Column: %s</p>' % e.column,
            "<br>".join(e.lines),
            '' if not e.raw_message else '<p>Raw Error: %s</p>' % e.raw_message,
        )
        return "", "", html

    def getPlatformPathPrefix(self):
        """ get the resource path for the platform"""
        # TODO: hardcoding the platform prefix for now
        # allow for a user defined value

        if self.platform == "android":
            return "file:///android_asset/site/"
        elif self.platform == "qt":
            return "./"
        else:
            return "/"

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

    def getHtmlEvent(self, js, onefile):
        """
        Returns platform dependent HTML/JS for handling API gateways
        """
        prefix = self.getPlatformPathPrefix()

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
                "</script>\n";
        if self.platform == "qt":
            return "<script type=\"text/javascript\" src=\"./static/qwebchannel.js\"></script>"
        return ""

    def getHtmlRender(self, render_function, root):
        """
        generate the script which will render the root element

        the script removes all existing children of the root dom node
        and then mounts the root element.
        """
        lines = [
            '<script type="text/javascript">',
            'const document_root = document.getElementById("root")',
            'while (document_root.hasChildNodes()) {',
            '    document_root.removeChild(document_root.lastChild);',
            '}',
            '%s(document_root, new %s())' % (render_function, root),
            '</script>',
        ]

        return "\n".join(lines)

