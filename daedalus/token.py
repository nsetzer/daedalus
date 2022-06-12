
import ast as pyast

class TokenError(Exception):
    def __init__(self, token, message):
        self.original_message = message
        message = "type: %s line: %d column: %d (%r) %s" % (token.type, token.line, token.index, token.value, message)
        super(TokenError, self).__init__(message)

        self.token = token

def ast2json_obj(ast):

    obj = {}

    for pair in ast.children:

        if pair.type == Token.T_BINARY and pair.value == ':':
            lhs, rhs = pair.children

            if lhs.type == Token.T_STRING:
                key = pyast.literal_eval(lhs.value)
            else:
                raise ValueError("%s:%s" % (lhs.type, lhs.value))

            val = ast2json(rhs)

            obj[key] = val

        else:
            raise ValueError("%s:%s" % (pair.type, pair.value))

    return obj

def ast2json_seq(ast):
    seq = []
    for val in ast.children:
        seq.append(ast2json(val))
    return seq

def ast2json(ast):

    if ast.type == Token.T_OBJECT:
        return ast2json_obj(ast)
    elif ast.type == Token.T_LIST:
        return ast2json_seq(ast)
    elif ast.type == Token.T_STRING:
        return pyast.literal_eval(ast.value)
    elif ast.type == Token.T_NUMBER:
        return pyast.literal_eval(ast.value)
    elif ast.type == Token.T_PREFIX:
        if ast.value == "-" and ast.children and ast.children[0].type == Token.T_NUMBER:
            val = ast2json(ast.children[0])
            return -val
        else:
            raise ValueError("%s:%s" % (ast.type, ast.value))
    elif ast.type == Token.T_KEYWORD:
        if ast.value == 'true':
            return True
        elif ast.value == 'false':
            return False
        elif ast.value == 'null':
            return None
        elif ast.value == 'undefined':
            return None
        else:
            raise ValueError("%s:%s" % (ast.type, ast.value))
    else:
        raise ValueError("%s:%s" % (ast.type, ast.value))

class Token(object):

    # tokens produced by the lexer
    T_TEXT = "T_TEXT"
    T_KEYWORD = "T_KEYWORD"
    T_NUMBER = "T_NUMBER"
    T_STRING = "T_STRING"
    T_TEMPLATE_STRING = "T_TEMPLATE_STRING"
    T_DOCUMENTATION = "T_DOCUMENTATION"
    T_SPECIAL = "T_SPECIAL"
    T_SPECIAL_IMPORT = "T_SPECIAL_IMPORT"
    T_NEWLINE = "T_NEWLINE"
    T_REGEX = "T_REGEX"

    # tokens created by the parser
    T_MODULE = "T_MODULE"
    T_ATTR = "T_ATTR"
    T_GROUPING = "T_GROUPING"
    T_ARGLIST = "T_ARGLIST"
    T_FUNCTIONCALL = "T_FUNCTIONCALL"

    T_SUBSCR = "T_SUBSCR"
    T_BLOCK = "T_BLOCK"
    T_BLOCK_LABEL = "T_BLOCK_LABEL"
    T_LIST = "T_LIST"
    T_OBJECT = "T_OBJECT"
    T_TUPLE = "T_TUPLE" # immutable list
    T_RECORD = "T_RECORD" # immutable object
    T_PREFIX = "T_PREFIX"
    T_POSTFIX = "T_POSTFIX"
    T_BINARY = "T_BINARY"
    T_TERNARY = "T_TERNARY"
    T_COMMA = "T_COMMA"
    T_ASSIGN = "T_ASSIGN"

    # tokens created by the parser (processed keywords)
    T_GET_ATTR = "T_GET_ATTR"
    T_BREAK = "T_BREAK"
    T_BRANCH = "T_BRANCH"
    T_CASE = "T_CASE"
    T_CATCH = "T_CATCH"
    T_CLASS = "T_CLASS"
    T_CLASS_BLOCK = "T_CLASS_BLOCK"
    T_CONTINUE = "T_CONTINUE"
    T_DEFAULT = "T_DEFAULT"
    T_EXPORT = "T_EXPORT"
    T_EXPORT_DEFAULT = "T_EXPORT_DEFAULT"
    T_EXPORT_ARGS = "T_EXPORT_ARGS"
    T_IMPORT = "T_IMPORT"
    T_IMPORT_JS_MODULE = "T_IMPORT_JS_MODULE"
    T_IMPORT_JS_MODULE_AS = "T_IMPORT_JS_MODULE_AS"
    T_IMPORT_MODULE = "T_IMPORT_MODULE"
    T_PYIMPORT = "T_PYIMPORT"
    T_INCLUDE = "T_INCLUDE"
    T_FINALLY = "T_FINALLY"

    T_DOWHILE = "T_DOWHILE"
    T_WHILE = "T_WHILE"
    T_FOR = "T_FOR"
    T_FOR_OF = "T_FOR_OF"
    T_FOR_AWAIT_OF = "T_FOR_AWAIT_OF"
    T_FOR_IN = "T_FOR_IN"

    T_NEW = "T_NEW"
    T_RETURN = "T_RETURN"
    T_SWITCH = "T_SWITCH"
    T_THROW = "T_THROW"
    T_TRY = "T_TRY"
    T_VAR = "T_VAR"

    T_OPTIONAL_CHAINING = "T_OPTIONAL_CHAINING"
    T_NULLISH_COALESCING = "T_NULLISH_COALESCING"
    T_NULLISH_ASSIGN = "T_NULLISH_ASSIGN"
    T_UNPACK_SEQUENCE = "T_UNPACK_SEQUENCE"
    T_UNPACK_OBJECT = "T_UNPACK_OBJECT"
    T_LOGICAL_AND = "T_LOGICAL_AND"
    T_LOGICAL_OR = "T_LOGICAL_OR"
    T_INSTANCE_OF = "T_INSTANCE_OF"
    T_SPREAD = "T_SPREAD"
    T_STATIC_PROPERTY = "T_STATIC_PROPERTY"
    T_YIELD = "T_YIELD"
    T_YIELD_FROM = "T_YIELD_FROM"
    T_INTERFACE = "T_INTERFACE"

    # function types
    T_FUNCTION = "T_FUNCTION"
    T_ASYNC_FUNCTION = "T_ASYNC_FUNCTION"
    T_GENERATOR = "T_GENERATOR"
    T_ASYNC_GENERATOR = "T_ASYNC_GENERATOR"

    T_ANONYMOUS_FUNCTION = "T_ANONYMOUS_FUNCTION"
    T_ASYNC_ANONYMOUS_FUNCTION = "T_ASYNC_ANONYMOUS_FUNCTION"
    T_ANONYMOUS_GENERATOR = "T_ANONYMOUS_GENERATOR"
    T_ASYNC_ANONYMOUS_GENERATOR = "T_ASYNC_ANONYMOUS_GENERATOR"

    T_METHOD = "T_METHOD"
    T_LAMBDA = "T_LAMBDA"  # arrow function

    # these variables are assigned by the transform engine for variable scopes
    T_GLOBAL_VAR = 'T_GLOBAL_VAR'
    T_LOCAL_VAR = 'T_LOCAL_VAR'
    T_SAVE_VAR = 'T_SAVE_VAR'
    T_RESTORE_VAR = 'T_RESTORE_VAR'
    T_DELETE_VAR = 'T_DELETE_VAR'
    T_CLOSURE = 'T_CLOSURE'
    T_CELL_VAR = 'T_CELL_VAR'
    T_FREE_VAR = 'T_FREE_VAR'

    T_TEMPLATE_EXPRESSION = "T_TEMPLATE_EXPRESSION"
    T_TAGGED_TEMPLATE = "T_TAGGED_TEMPLATE"

    # a token which stands for no token
    T_EMPTY_TOKEN = "T_EMPTY_TOKEN"

    T_TYPE = "T_TYPE"
    T_ANNOTATION = "T_ANNOTATION"

    # tokens created by the compiler
    T_BLOCK_PUSH = "T_BLOCK_PUSH"
    T_BLOCK_POP = "T_BLOCK_POP"

    def __init__(self, type, line=0, index=0, value="", children=None):
        super(Token, self).__init__()
        self.type = type
        self.line = line
        self.index = index
        self.value = value
        self.children = list(children) if children is not None else []
        self.file = None
        self.original_value = None
        self.ref = None
        self.ref_attr = 0 # 1: define, 2: store, 4: load

    def __str__(self):

        return self.toString(False, 0)

    def __repr__(self):
        return "Token(Token.%s, %r, %r, %r)" % (
            self.type, self.line, self.index, self.value)

    def toString(self, pretty=True, depth=0, pad="  "):

        if pretty == 3:
            s = "%s<%r>" % (self.type, self.value)
            parts = ["%s%s\n" % (pad * depth, s)]

            for child in self.children:
                try:
                    parts.append(child.toString(pretty, depth + 1, pad))
                except:
                    print(child)

            return ''.join(parts)

        elif pretty == 2:

            if len(self.children) == 0:
                s = "\n%sTOKEN(%r, %r)" % ("    " * depth, self.type, self.value)
                return s
            else:
                s = "\n%sTOKEN(%r, %r, " % ("    " * depth, self.type, self.value)
                c = [child.toString(pretty, depth + 1) for child in self.children]
                return s + ', '.join(c) + ")"

        elif pretty:
            s = "%s<%s,%s,%r>" % (self.type, self.line, self.index, self.value)
            parts = ["%s%s\n" % (pad * depth, s)]

            for child in self.children:
                try:
                    parts.append(child.toString(pretty, depth + 1))
                except:
                    print(child)

            return ''.join(parts)

        elif self.children:
            s = "%s<%r>" % (self.type, self.value)
            t = ','.join(child.toString(False) for child in self.children)
            return "%s{%s}" % (s, t)
        else:
            return "%s<%r>" % (self.type, self.value)

    def flatten(self, depth=0):
        items = [(depth, self)]
        for child in self.children:
            items.extend(child.flatten(depth + 1))
        return items

    @staticmethod
    def basicType(token):
        return token and (token.type in (Token.T_TEXT, Token.T_NUMBER, Token.T_STRING) or
               token.type == Token.T_SPECIAL and token.value in "])")

    def clone(self, **keys):

        tok = Token(self.type, self.line, self.index, self.value)
        tok.file = self.file
        tok.original_value = self.original_value
        tok.children = [c.clone() for c in self.children]
        tok.ref = self.ref
        tok.ref_attr = self.ref_attr
        tok.__dict__.update(keys)
        return tok

    @staticmethod
    def deepCopy(token):

        queue = []

        root = Token(token.type, token.line, token.index, token.value)

        root.file = token.file
        root.original_value = token.original_value

        for child in reversed(token.children):
            queue.append((child, root))

        while queue:
            tok, parent = queue.pop()

            new_tok = Token(tok.type, tok.line, tok.index, tok.value)

            new_tok.file = tok.file
            new_tok.original_value = tok.original_value

            parent.children.append(new_tok)

            for child in reversed(tok.children):
                queue.append((child, new_tok))

        return root


    def toJson(self):

        return ast2json(self)

