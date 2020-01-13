
import os
import sys
import time
from . import __path__
import json
from .lexer import Lexer, Token, TokenError
from .parser import Parser
from .transform import TransformExtractStyleSheet
from .compiler import Compiler

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
        return Token(type, 0, 0, value, children)

    tok_export_names = [TOKEN('T_TEXT', text) for text in sorted(exports)]
    tok_exports = TOKEN('T_MODULE', '',
        TOKEN('T_RETURN', 'return',
            TOKEN('T_LIST', '[]', *tok_export_names)))

    tok_ast = merge_ast(mod, tok_exports)

    # insert the file into a function
    tok_fundef = TOKEN('T_FUNCTION', 'function',
        TOKEN('T_TEXT', ''),
        TOKEN('T_ARGLIST', '()'),
        Token(Token.T_BLOCK, 0, 0, "{}", tok_ast.children))

    # invoke that function and assign return values in current scope
    tok_iifi = TOKEN('T_MODULE', '',
        TOKEN('T_BINARY', '=',
            TOKEN('T_VAR', "const", TOKEN('T_LIST', '[]', *tok_export_names)),
            TOKEN('T_FUNCTIONCALL', '',
                TOKEN('T_GROUPING', '()', tok_fundef),
                TOKEN('T_ARGLIST', '()'))))

    return tok_iifi

def buildModuleIIFI(modname, mod, imports, exports, merge):
    """
    convert a module into an immediatley invoked function interface.
    the function accepts arguments for the imports and returns an
    object containing the exports.

    used to isolate one module from other modules in the project
    """

    def TOKEN(type, value, *children):
        return Token(type, 0, 0, value, children)

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
        print("warning: module with invalid modname", modname)
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
            tok = TOKEN('T_BINARY', '=',
                TOKEN('T_TEXT', dst),
                TOKEN('T_BINARY', '.',
                    TOKEN('T_TEXT', varname),
                    TOKEN('T_ATTR', src)))
            tok_imports1.append(tok)
    tok_imports = TOKEN('T_MODULE', '', *tok_imports1)

    tok_ast = merge_ast(tok_imports, mod)
    tok_ast = merge_ast(tok_ast, tok_exports)

    tok_fundef = TOKEN('T_FUNCTION', 'function',
        TOKEN('T_TEXT', ''),
        TOKEN('T_ARGLIST', '()', *tok_import_names),
        Token(Token.T_BLOCK, 0, 0, "{}", tok_ast.children))

    if merge:
        tok_iifi = TOKEN('T_MODULE', '',
            TOKEN('T_FUNCTIONCALL', '',
                TOKEN('T_BINARY', '.',
                    TOKEN('T_TEXT', 'Object'),
                    TOKEN('T_TEXT', 'assign')),
                TOKEN('T_ARGLIST', '()',
                    TOKEN('T_TEXT', modname),
                    TOKEN('T_FUNCTIONCALL', '',
                        TOKEN('T_GROUPING', '()', tok_fundef),
                        TOKEN('T_ARGLIST', '()', *tok_argument_names)))))

    else:
        tok_iifi = TOKEN('T_MODULE', '',
            TOKEN('T_BINARY', '=',
                TOKEN('T_TEXT', modname),
                TOKEN('T_FUNCTIONCALL', '',
                    TOKEN('T_GROUPING', '()', tok_fundef),
                    TOKEN('T_ARGLIST', '()', *tok_argument_names))))


    return tok_iifi

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
    def __init__(self, path, name=None, source_type=1):
        super(JsFile, self).__init__()
        self.path = path
        self.imports = {}
        self.module_imports = {}
        self.exports = []
        self.source_type = source_type
        self.mtime = 0
        self.size = 0
        self.ast = None
        self.styles = []

        if not name:
            self.name = os.path.splitext(os.path.split(name)[1])[0]
        else:
            self.name = name

        if '.js' in self.name:
            raise Exception(self.name)

    def getSource(self):

        with open(self.path, "r") as rf:
            return rf.read()

    def load(self):

        t1 = time.time()
        source = self.getSource()
        self.size = len(source)

        error = None
        try:
            tokens = Lexer().lex(source)
            for token in tokens:
                token.file = self.path
            ast = Parser().parse(tokens)
            uid = TransformExtractStyleSheet.generateUid(self.path)
            tr1 = TransformExtractStyleSheet(uid)
            tr1.transform(ast)
            self.styles = tr1.getStyles()
        except TokenError as e:
            source_lines=source.split("\n")
            line_start = e.token.line - 3
            line_end = e.token.line + 3
            b_lines = ["%4d: %s" % (i+1, source_lines[i]) for i in range(line_start,e.token.line)]
            a_lines = ["%4d: %s" % (i+1, source_lines[i]) for i in range(e.token.line,line_end)]

            lines = b_lines + ["      " + " " * e.token.index + "^"] + a_lines
            error = BuildError(self.path, e.token, lines, e.original_message, str(e))

        if error:
            raise error

        self.ast = self._get_imports_exports(ast)

        t2 = time.time()

        self.mtime = os.stat(self.path).st_mtime

        print("%10d %.2f %s" % (len(source), t2-t1, self.path))

    def _get_imports_exports(self, ast):
        self.imports = {}
        self.module_imports = {}
        self.exports = []
        i = 0
        while i < len(ast.children):
            token = ast.children[i]
            if token.type == Token.T_IMPORT:
                fromlist = []
                for child in token.children[0].children:
                    if child.type == Token.T_TEXT:
                        fromlist.append((child.value, child.value))
                    else:
                        fromlist.append((child.children[0].value, child.children[1].value))
                if token.value.endswith(".js") and self.source_type==2:
                    self.imports[token.value] = dict(fromlist)
                else:
                    self.module_imports[token.value] = dict(fromlist)
                ast.children.pop(0)
            elif token.type == Token.T_EXPORT:
                self.exports.append(token.value)
                child = token.children[0]
                if child.type == Token.T_TEXT:
                    ast.children.pop(0)
                else:
                    ast.children[i] = token.children[0]
                    i += 1
            else:
                i += 1
        return ast

    def reload(self):
        if self.path:
            mtime = os.stat(self.path).st_mtime
            if mtime > self.mtime:
                self.load()
                return True
        return False

class JsModule(object):
    def __init__(self, index_js):
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

    def _getFiles(self):
        jsf = self.index_js
        queue = [(jsf, 0)]
        depth = {jsf.path: 0}
        while queue:
            c, d = queue.pop(0)
            d = depth[c.path]
            for p in self.import_paths[c.path]:
                if p not in depth:
                    depth[p] = d + 1
                else:
                    depth[p] = max(depth[p], d + 1)
                queue.append((self.files[p], d+1))

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
                    queue.append(JsFile(path, tmp_name, 2))
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

        self.styles = sum([jsf.styles for jsf in order],[])

        all_exports = self.module_exports | self.static_exports
        self.ast = buildModuleIIFI(self.name(), ast, self.module_imports, all_exports, merge)

        self.dirty = False
        t2 = time.time()
        print("%10s %.2f rebuild ast: %s" % ('', t2 - t1, self.name()))
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
    def __init__(self, search_paths, static_data):
        super(Builder, self).__init__()
        self.search_paths = search_paths
        self.static_data = static_data
        self.files = {}
        self.modules = {}
        self.source_types = {}

    def find(self, name):
        return findFile(name, self.search_paths)

    def _name2path(self, name):
        if name.endswith('.js'):
            path = self.find(name)
        else:
            path = self.find(name.replace(".", "/") + "/index.js")
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
                    self.files[modpath] = JsFile(modpath, modname, 2)

                if modpath not in self.modules:
                    self.modules[modpath] = JsModule(self.files[modpath])
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
            self.files[path] = JsFile(path, name, source_type)

        if self.files[path].source_type != source_type:
            raise Exception("incompatible types")

        if path not in self.modules:
            self.modules[path] = JsModule(self.files[path])
            self.modules[path].setStaticData(self.static_data.get(modname, None))

        self._discover(self.modules[path])

        return self.modules[path]

    def _sort_modules(self, jsm):
        name2path = {m.name():m.index_js.path for m in self.modules.values()}
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
                queue.append((self.modules[p], d+1))

        order = sorted(depth.keys(), key=lambda p: depth[p], reverse=True)
        return [self.modules[p] for p in order]

    def compile(self, path, standalone=False, minify=False):
        t1 = time.time()

        jsm = self.discover(path)

        if len(jsm.module_exports) == 0:
            raise BuildError(jsm.index_js.path, None, [], "does not export any symbols")

        if len(jsm.module_exports) > 1:
            sys.stderr.write("warning: root module exports more than one symbol")

        export_name = jsm.name() + "." + list(jsm.module_exports)[0]

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
                ast = merge_ast(ast, mod.getAST(merge=len(struct)>0))
                source_size += mod.source_size

            styles = sum([mod.styles for mod in order], [])
        else:
            ast = jsm.getAST()
            styles = jsm.styles
            source_size = jsm.source_size

        css = "\n".join(styles)
        error = None
        try:
            js = Compiler(opts={'minify': minify}).compile(ast)

        except TokenError as e:
            filepath = ""
            lines = []
            if e.token.file:
                jsf = self.files[e.token.file]
                filepath = e.token.file
                source = jsf.getSource()
                source_lines=source.split("\n")
                line_start = e.token.line - 3
                line_end = e.token.line + 3
                lines = source_lines[line_start:e.token.line]
                lines.append(" " * e.token.index + "^")
                lines.extend(source_lines[e.token.line:line_end])
            error = BuildError(filepath, e.token, lines, e.original_message, str(e))

        if error:
            raise error

        final_source_size = len(js)
        p = final_source_size / source_size
        t2 = time.time()
        print("%10d %.2f %.2f%% of %d" % (final_source_size, t2-t1, p, source_size))
        return css, js, export_name

    def build(self, path, minify=False, onefile=False):
        # make this have API functions which
        # can be overridden

        try:
            css, js, root = self.compile(path, minify=minify)
        except BuildError as e:
            return self.build_error(e)

        script = '<script src="/static/index.js"></script>'
        index_html = self.find("index.html")
        with open(index_html, "r") as hfile:
            html = hfile.read()
        render_function = 'daedalus.render'

        html = html \
            .replace("<!--TITLE-->", self.getHtmlTitle()) \
            .replace("<!--STYLE-->", self.getHtmlStyle(css, onefile)) \
            .replace("<!--SOURCE-->", self.getHtmlSource(js, onefile)) \
            .replace("<!--RENDER-->", self.getHtmlRender(render_function, root))

        return css, js, html

    def build_error(self, e):
        print(e.filepath)
        print(e)
        print("\n".join(e.lines))

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
            '' if e.line<0 else '<p>Line: %s</p>' % e.line,
            '' if e.column<0 else '<p>Column: %s</p>' % e.column,
            "<br>".join(e.lines),
            '' if not e.raw_message else '<p>Raw Error: %s</p>' % e.raw_message,
        )
        return "", "", html

    def getHtmlTitle(self):
        return '<title>Daedalus</title>'

    def getHtmlStyle(self, css, onefile):
        if not css:
            return ""
        elif onefile:
            return '<style>\n%s\n</style>' % css
        else:
            return '<link rel="stylesheet" href="/static/index.css">'

    def getHtmlSource(self, js, onefile):
        if onefile:
            return '<script type="text/javascript">\n%s\n</script>' % js
        else:
            return '<script src="/static/index.js" type="text/javascript"></script>'

    def getHtmlRender(self, render_function, root):
        return ('<script type="text/javascript">' \
            '%s(document.getElementById("root"), new %s())</script>') % (
            render_function, root)

