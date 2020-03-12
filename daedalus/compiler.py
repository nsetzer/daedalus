#! cd .. && python3 -m daedalus.compiler
"""
https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Operators/Operator_Precedence


https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Statements/block
blocks can be labeled

https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Statements/import
imports are complicated

lhs of => is an arglist
rhs of => is a ???

"""
import sys
import io
import base64
from .lexer import Lexer, Token, TokenError
from .parser import Parser

class CompileError(TokenError):
    pass

def diag(tokens):
    print([t.value for t in tokens])

text_group = {
    Token.T_KEYWORD,
    Token.T_BREAK,
    Token.T_BRANCH,
    Token.T_CASE,
    Token.T_CLASS,
    Token.T_CONTINUE,
    Token.T_DEFAULT,
    Token.T_DOWHILE,
    Token.T_FOR,
    Token.T_FUNCTION,
    Token.T_RETURN,
    Token.T_SWITCH,
    Token.T_TRY,
    Token.T_VAR,
    Token.T_WHILE,
    Token.T_ATTR,
    Token.T_TEXT,
}

class SourceMap(object):
    """
    5 fields: output column, file index, input line, input column, name index
    4 fields: output column, file index, input line, input column,
    1 fields: column
    """
    ALPHABET="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
    def __init__(self):
        super(SourceMap, self).__init__()

        self.version = "3"
        self.sources = []
        self.names = {}
        self.mappings = []
        self.sourceRoot = ""
        self.file = ""
        self.column = 0

    def toJsonObject(self):

        mappings = ";".join([",".join(m) for m in self.mappings])

        obj = {
            "version": self.version,
            "sources": self.sources,
            "names": self.names,
            "mappings": mappings,
        }

        return obj; 0x1c8

    def _encode(self, value):

        text = ""
        # 456 : 1 1000 0 | 0 11100
        signed = 0
        if value < 0:
            signed = 1
            value *= -1

        first = True
        while first or value:

            if first:
                tmp = ((value&0xF)<<1) | signed
                value >>= 4
                first = False
            else:
                tmp = value&0x1F
                value >>= 5

            if value:
                tmp |= 1<<5

            text += SourceMap.ALPHABET[tmp]

        return text

    def b64encode(self, seq):
        return ''.join(self._encode(i) for i in seq)

    def b64decode(self, text):

        seq = []

        pos=0
        sign = 1
        value = 0
        for char in text:
            i = SourceMap.ALPHABET.index(char)
            if pos==0:
                if i&1:
                    sign = -1
                value = (i>>1)&0xF
                pos += 4
            else:
                value |= (i&0x1F) << pos
                pos += 5


            if 0x20&i==0:
                seq.append(value * sign)
                sign = 1
                value = 0
                pos = 0
        return seq

    def write(self, token):

        if token.type == Token.T_NEWLINE:
            self.mappings.append([])
            self.column = 0

        elif token.type == Token.T_TEXT:
            fields = [self.column, token.file, token.line, token.column]
            if token.original_value:
                fields.append(self.getIndex(token.original_value))
            self.mappings[-1].append(self.b64encode(fields))
            self.column += len(token.value)
        else:
            self.column += len(token.value)

    def getIndex(self, name):
        if name not in self.names:
            self.names[name] = len(self.names)
        return self.names[name]

def isalphanum(a, b):
    """ return true if a+b is not a reversable operation"""
    if a and b:
        c1 = a[-1]
        c2 = b[0]


        return (c1.isalnum() or c1 == '_' or ord(c1) > 127) and \
               (c2.isalnum() or c2 == '_' or ord(c2) > 127)
    return False

class Compiler(object):
    def __init__(self, opts=None):
        super(Compiler, self).__init__()

        self.pretty_print = True
        self.padding = "    "

        if not opts:
            opts = {}

        self.minify = opts.get('minify', False)

    def compile(self, mod):

        self.tokens = []
        self.stream = io.StringIO()
        self._null = Token(Token.T_NEWLINE, mod.line, mod.index, "")
        self._prev = self._null
        self._prev_char = ''

        self.tokens = self._compile(mod)

        return self._write_minified()

    def _write_minified(self):

        # maximum length for any line is 4095 becuase of limitations
        # of some javascript compilers
        width=240
        line_len = 0
        prev_type = Token.T_NEWLINE
        prev_text = ""
        for type, text in self.tokens:

            if type == Token.T_NEWLINE:
                continue

            if isalphanum(prev_text, text):
                line_len += self.stream.write(" ")
            line_len += self.stream.write(text)

            if line_len > width and text in {'(', '{', '[', ';', ','}:
                self.stream.write("\n")
                line_len = 0
            prev_type = type
            prev_text = text
        return self.stream.getvalue()

    def _compile(self, token):
        """ non-recursive implementation of _compile

        for each node process the children in reverse order
        """

        seq = [(0, None, token)]
        out = []

        while seq:
            depth, state, token = seq.pop()

            if isinstance(token, str):

                out.append((state, token))
            elif token.type == Token.T_MODULE:
                insert = False
                for child in reversed(token.children):
                    if insert:
                        seq.append((depth, Token.T_SPECIAL, ";"))
                    seq.append((depth+1, None, child))
                    insert = True
            elif token.type == Token.T_BLOCK:
                seq.append((depth, Token.T_SPECIAL, token.value[1]))
                first = True
                for child in reversed(token.children):
                    if child.type in (Token.T_CASE, Token.T_DEFAULT) or first:
                        insert = False
                    else:
                        insert = True

                    if insert:
                        seq.append((depth, Token.T_SPECIAL, ";"))

                    seq.append((depth+1, None, child))

                    first = False
                seq.append((depth, Token.T_SPECIAL, token.value[0]))
            elif token.type in (Token.T_OBJECT, Token.T_LIST, Token.T_GROUPING, Token.T_ARGLIST):
                # commas are implied between clauses
                seq.append((depth, Token.T_SPECIAL, token.value[1]))
                insert = False
                for child in reversed(token.children):
                    if insert:
                        seq.append((depth, Token.T_SPECIAL, ","))
                    seq.append((depth+1, None, child))
                    insert = True
                seq.append((depth, Token.T_SPECIAL, token.value[0]))
            elif token.type == Token.T_LAMBDA:
                seq.append((depth, None, token.children[2]))

                if token.value.isalpha():
                    seq.append((depth, Token.T_KEYWORD, token.value))
                else:
                    seq.append((depth, token.type, token.value))
                seq.append((depth, None, token.children[1]))
            elif token.type == Token.T_BINARY:
                seq.append((depth, None, token.children[1]))

                if token.value.isalpha():
                    seq.append((depth, Token.T_KEYWORD, token.value))
                else:
                    seq.append((depth, token.type, token.value))
                seq.append((depth, None, token.children[0]))

            elif token.type == Token.T_ASSIGN:
                seq.append((depth, None, token.children[1]))

                if token.value.isalpha():
                    seq.append((depth, Token.T_KEYWORD, token.value))
                else:
                    seq.append((depth, token.type, token.value))
                seq.append((depth, None, token.children[0]))

            elif token.type == Token.T_TERNARY:
                seq.append((depth, None, token.children[2]))
                seq.append((depth, Token.T_SPECIAL, ":"))
                seq.append((depth, None, token.children[1]))
                seq.append((depth, Token.T_SPECIAL, "?"))
                seq.append((depth, None, token.children[0]))
            elif token.type == Token.T_PREFIX:
                seq.append((depth, None, token.children[0]))
                seq.append((depth, token.type, token.value))
            elif token.type == Token.T_POSTFIX:
                seq.append((depth, token.type, token.value))
                seq.append((depth, None, token.children[0]))
            elif token.type == Token.T_COMMA:
                if len(token.children) == 2:
                    seq.append((depth, None, token.children[1]))
                    seq.append((depth, Token.T_SPECIAL, ","))
                    seq.append((depth, None, token.children[0]))
                else:
                    seq.append((depth, None, token.children[0]))
            elif token.type == Token.T_TEXT:

                out.append((token.type, token.value))
            elif token.type == Token.T_NUMBER:

                out.append((token.type, token.value))
            elif token.type in (Token.T_STRING, Token.T_TEMPLATE_STRING):

                out.append((token.type, token.value))
            elif token.type == Token.T_KEYWORD:

                out.append((token.type, token.value))
            elif token.type == Token.T_ATTR:

                out.append((token.type, token.value))
            elif token.type == Token.T_DOCUMENTATION:

                out.append((token.type, token.value))
            elif token.type == Token.T_NEWLINE:

                raise CompileError(token, "unexpected")
            elif token.type == Token.T_VAR:
                seq.append((depth, None, token.children[0]))
                seq.append((depth, token.type, token.value))
            elif token.type == Token.T_CLASS:

                seq.append((depth, None, token.children[2]))
                if len(token.children[1].children) > 0:
                    seq.append((depth, None, token.children[1].children[0]))
                    seq.append((depth, Token.T_KEYWORD, "extends"))
                seq.append((depth, None, token.children[0]))
                seq.append((depth, token.type, token.value))
            elif token.type == Token.T_FUNCTION:
                seq.append((depth, None, token.children[2]))
                seq.append((depth, None, token.children[1]))
                seq.append((depth, None, token.children[0]))
                seq.append((depth, token.type, token.value))
            elif token.type == Token.T_METHOD:
                seq.append((depth, None, token.children[2]))
                seq.append((depth, None, token.children[1]))
                seq.append((depth, None, token.children[0]))
                seq.append((depth, token.type, token.value))
            elif token.type == Token.T_FUNCTIONCALL:
                for child in reversed(token.children):
                    seq.append((depth, None, child))
            elif token.type == Token.T_ANONYMOUS_FUNCTION:
                for child in reversed(token.children[1:]):
                    seq.append((depth, None, child))
            elif token.type == Token.T_IMPORT:

                pass
            elif token.type == Token.T_EXPORT:

                pass
            elif token.type == Token.T_SUBSCR:
                seq.append((depth, Token.T_SPECIAL, "]"))
                for child in reversed(token.children[1:]):
                    seq.append((depth, None, child))
                seq.append((depth, Token.T_SPECIAL, "["))
                seq.append((depth, None, token.children[0]))
            elif token.type == Token.T_BRANCH:
                if len(token.children) == 3:
                    seq.append((depth, None, token.children[2]))
                    seq.append((depth, Token.T_KEYWORD, "else"))
                seq.append((depth, None, token.children[1]))
                seq.append((depth, None, token.children[0]))
                seq.append((depth, token.type, token.value))
            elif token.type == Token.T_FOR:
                args, block = token.children

                # this arglist is special, if there are multiple clauses
                # separate them by semicolons instead of commas
                seq.append((depth, None, block))
                seq.append((depth, Token.T_SPECIAL, ')'))
                insert = False
                for child in reversed(args.children):
                    if insert:
                        seq.append((depth, Token.T_SPECIAL, ";"))
                    seq.append((depth, None, child))
                    insert = True
                seq.append((depth, Token.T_SPECIAL, '('))
                seq.append((depth, token.type, token.value))
            elif token.type == Token.T_DOWHILE:
                seq.append((depth, None, token.children[1]))
                seq.append((depth, Token.T_KEYWORD, "while"))
                seq.append((depth, None, token.children[0]))
                seq.append((depth, token.type, token.value))
            elif token.type == Token.T_WHILE:
                seq.append((depth, None, token.children[1]))
                seq.append((depth, None, token.children[0]))
                seq.append((depth, token.type, token.value))
            elif token.type == Token.T_SWITCH:
                seq.append((depth, None, token.children[1]))
                seq.append((depth, None, token.children[0]))
                seq.append((depth, token.type, token.value))
            elif token.type == Token.T_CASE:
                seq.append((depth, Token.T_SPECIAL, ":"))
                seq.append((depth, None, token.children[0]))
                seq.append((depth, token.type, token.value))
            elif token.type == Token.T_DEFAULT:
                seq.append((depth, Token.T_SPECIAL, ":"))
                seq.append((depth, token.type, token.value))
            elif token.type == Token.T_BREAK or token.type == Token.T_CONTINUE:

                out.append((token.type, token.value))
            elif token.type == Token.T_RETURN:
                for child in reversed(token.children): # length is zero or one
                    seq.append((depth, None, child))
                seq.append((depth, token.type, token.value))
            elif token.type == Token.T_NEW:
                for child in reversed(token.children): # length is zero or one
                    seq.append((depth, None, child))
                seq.append((depth, token.type, token.value))
            elif token.type == Token.T_THROW:
                for child in reversed(token.children): # length is zero or one
                    seq.append((depth, None, child))
                seq.append((depth, token.type, token.value))
            elif token.type in (Token.T_TRY, Token.T_CATCH, Token.T_FINALLY):
                # note that try will have one or more children
                # while catch always has 2 and finally always has 1
                for child in reversed(token.children): # length is zero or one
                    seq.append((depth, None, child))
                seq.append((depth, token.type, token.value))

            elif token.type == Token.T_EMPTY_TOKEN:
                pass
            else:
                raise CompileError(token, "token not supported")
        return out

def main():  # pragma: no cover

    text1 = """
    function f1() {}
    f2 = function() {}
    f3 = () => {}
    class A extends B {
        constructor() {

        }
    }
    """

    #text1 = open("./res/daedalus/index.js").read()


    tokens = Lexer().lex(text1)
    mod = Parser().parse(tokens)

    print(mod.toString())

    cc = Compiler()
    text2 = Compiler().compile(mod)

    print("-" * 79)

    print(text2)
    print("-" * 79)
    print(len(text2), len(text1))

if __name__ == '__main__':  # pragma: no cover
    main()