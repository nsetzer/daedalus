

class TokenError(Exception):
    def __init__(self, token, message):
        self.original_message = message
        message = "type: %s line: %d column: %d (%r) %s" % (token.type, token.line, token.index, token.value, message)
        super(TokenError, self).__init__(message)

        self.token = token

class Token(object):

    # tokens produced by the lexer
    T_TEXT = "T_TEXT"
    T_KEYWORD = "T_KEYWORD"
    T_NUMBER = "T_NUMBER"
    T_STRING = "T_STRING"
    T_TEMPLATE_STRING = "T_TEMPLATE_STRING"
    T_DOCUMENTATION = "T_DOCUMENTATION"
    T_SPECIAL = "T_SPECIAL"
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
    T_LIST = "T_LIST"
    T_OBJECT = "T_OBJECT"
    T_PREFIX = "T_PREFIX"
    T_POSTFIX = "T_POSTFIX"
    T_BINARY = "T_BINARY"
    T_TERNARY = "T_TERNARY"
    T_COMMA = "T_COMMA"
    T_ASSIGN = "T_ASSIGN"

    # tokens created by the parser (processed keywords)
    T_BREAK = "T_BREAK"
    T_BRANCH = "T_BRANCH"
    T_CASE = "T_CASE"
    T_CATCH = "T_CATCH"
    T_CLASS = "T_CLASS"
    T_CONTINUE = "T_CONTINUE"
    T_DEFAULT = "T_DEFAULT"
    T_DOWHILE = "T_DOWHILE"
    T_EXPORT = "T_EXPORT"
    T_EXPORT_DEFAULT = "T_EXPORT_DEFAULT"
    T_IMPORT = "T_IMPORT"
    T_IMPORT_MODULE = "T_IMPORT_MODULE"
    T_PYIMPORT = "T_PYIMPORT"
    T_INCLUDE = "T_INCLUDE"
    T_FINALLY = "T_FINALLY"
    T_FOR = "T_FOR"
    T_FOR_OF = "T_FOR_OF"
    T_FOR_IN = "T_FOR_IN"
    T_NEW = "T_NEW"
    T_RETURN = "T_RETURN"
    T_SWITCH = "T_SWITCH"
    T_THROW = "T_THROW"
    T_TRY = "T_TRY"
    T_VAR = "T_VAR"
    T_WHILE = "T_WHILE"
    T_OPTIONAL_CHAINING = "T_OPTIONAL_CHAINING"
    T_UNPACK_SEQUENCE = "T_UNPACK_SEQUENCE"
    T_LOGICAL_AND = "T_LOGICAL_AND"
    T_LOGICAL_OR = "T_LOGICAL_OR"
    T_INSTANCE_OF = "T_INSTANCE_OF"
    T_SPREAD = "T_SPREAD"
    T_YIELD = "T_YIELD"
    T_YIELD_FROM = "T_YIELD_FROM"

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
    T_STATIC_METHOD = "T_STATIC_METHOD"
    T_LAMBDA = "T_LAMBDA"  # arrow function

    # these variables are assigned by the transform engine for variable scopes
    T_GLOBAL_VAR = 'T_GLOBAL_VAR'
    T_LOCAL_VAR = 'T_LOCAL_VAR'
    T_DELETE_VAR = 'T_DELETE_VAR'
    T_CLOSURE = 'T_CLOSURE'
    T_CELL_VAR = 'T_CELL_VAR'
    T_FREE_VAR = 'T_FREE_VAR'

    # a token which stands for no token
    T_EMPTY_TOKEN = "T_EMPTY_TOKEN"

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
        tok.__dict__.update(keys)
        return tok

