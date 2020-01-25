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


        return (c1.isalnum() or ord(c1) > 127) and \
               (c2.isalnum() or ord(c2) > 127)
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
        self._compile(mod)

        return self._write_minified()

    def _x_write_pretty(self):  # pragma: no cover
        """
        not so much pretty as 'not ugly'
        """

        # maximum length for any line is 4095 becuase of limitations
        # of some javascript compilers
        depth = 0
        width=80
        line_len = 0
        prev_type = ""
        prev_text = ""
        for type, text in self.tokens:

            if type == Token.T_NEWLINE:
                if prev_type != Token.T_NEWLINE:
                    self.stream.write("\n" + "  " * depth)
                    line_len = 0
                    prev_type = type
                    prev_text = ""

            elif type == Token.T_SPECIAL and text == ';':
                if prev_type != Token.T_NEWLINE:
                    self.stream.write(";")
                if prev_type != Token.T_NEWLINE:
                    self.stream.write("\n" + "  " * depth)
                    line_len = 0
                    prev_type = Token.T_NEWLINE
                    prev_text = ""

            elif type == Token.T_BLOCK_PUSH:
                depth += 1
                line_len += self.stream.write(text)
            elif type == Token.T_BLOCK_POP:
                depth -= 1

                if prev_type != Token.T_NEWLINE:
                    self.stream.write("\n" + "  " * depth)
                    line_len = 0
                    prev_type = Token.T_NEWLINE
                    prev_text = ""

                line_len += self.stream.write(text)

                self.stream.write("\n" + "  " * depth)
                line_len = 0
                prev_type = Token.T_NEWLINE
                prev_text = ""

            else:

                if isalphanum(prev_text, text):
                    line_len += self.stream.write(" ")

                line_len += self.stream.write(text)

                prev_type = type
                prev_text = text

                if line_len > width and text in {'(', '{', '[', ';', ','}:
                    self.stream.write("\n" + "  " * (depth+1))
                    line_len = 0
                    prev_type = Token.T_NEWLINE
                    prev_text = ""


        return self.stream.getvalue()

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

    def _x_compile_pretty(self, token, depth=0):  # pragma: no cover

        if token.type == Token.T_MODULE:
            insert = False
            for child in token.children:
                if insert:
                    self._write_char(";")
                self._compile(child, depth + 1)
                insert = True
        elif token.type in (Token.T_LIST, Token.T_GROUPING, Token.T_OBJECT, Token.T_ARGLIST):
            # commas are implied between clauses
            self._write_char(token.value[0])
            insert = False
            for child in token.children:
                if insert:
                    self._write_char(",")
                self._compile(child, depth + 1)
                insert = True
            self._write_char(token.value[1])
        elif token.type == Token.T_BLOCK:
            self._write_char(token.value[0], Token.T_BLOCK_PUSH)
            insert = False
            for child in token.children:
                if insert:
                    self._write_char(";")
                self._compile(child, depth + 1)
                insert = True
            self._write_char(token.value[1], Token.T_BLOCK_POP)
        elif token.type == Token.T_PREFIX:
            self._write(token)
            self._compile(token.children[0], depth)
        elif token.type == Token.T_POSTFIX:
            self._compile(token.children[0], depth)
            self._write(token)
        elif token.type == Token.T_BINARY:
            self._compile(token.children[0], depth)
            if token.value.isalpha():
                self._write(Token(Token.T_KEYWORD, token.line, token.index, token.value))
            else:
                self._write(token)
            self._compile(token.children[1], depth)
        elif token.type == Token.T_TERNARY:
            self._compile(token.children[0], depth)
            self._write_char("?")
            self._compile(token.children[1], depth)
            self._write_char(":")
            self._compile(token.children[2], depth)
        elif token.type == Token.T_VAR:
            self._write(token)
            self._compile(token.children[0], depth)
        elif token.type in (Token.T_TEXT, Token.T_NUMBER, Token.T_STRING):

            self._write(token)
        elif token.type == Token.T_FUNCTION:
            self._write(token)
            self._compile(token.children[0], depth)
            self._compile(token.children[1], depth)
            self._compile(token.children[2], depth)
        elif token.type == Token.T_FUNCTIONCALL:
            for child in token.children:
                self._compile(child, depth)
        elif token.type == Token.T_FUNCTIONDEF:
            for child in token.children:
                self._compile(child, depth)

        elif token.type == Token.T_SUBSCR:
            # this isnt strictly valid javascript
            text = self._compile(token.children[0], depth) + "[" + \
                ','.join([self._compile(child, depth) for child in token.children[1:]]) + \
                "]"
            return text
        elif token.type == Token.T_BRANCH:
            text = "if " + \
                self._compile(token.children[0], depth) + \
                self._compile(token.children[1], depth)

            if len(token.children) == 3:
                text += "else " + self._compile(token.children[2], depth)
            return text
        elif token.type == Token.T_FOR:
            args, block = token.children
            # this arglist is special, if there are multiple clauses
            # separate them by semicolons instead of commas
            text = "for(" + \
                ';'.join([self._compile(child, depth) for child in args.children]) + \
                ")" + self._compile(block, depth)
            return text
        elif token.type == Token.T_DOWHILE:
            text = "do" + \
                self._compile(token.children[0], depth) + \
                "while" + \
                self._compile(token.children[1], depth)
            return text
        elif token.type == Token.T_WHILE:
            text = "while" + \
                self._compile(token.children[0], depth) + \
                self._compile(token.children[1], depth)
            return text
        elif token.type == Token.T_CLASS:

            text = "class " + self._compile(token.children[0], depth)
            if len(token.children[1].children) > 0:
                text += " extends " + self._compile(token.children[1], depth)
            text + self._compile(token.children[2], depth)
            return text
        elif token.type == Token.T_RETURN:
            if token.children: # length is zero or one
                return "return " + self._compile(token.children[0], depth)
            return "return"
        elif token.type == Token.T_COMMA:
            if len(token.children) == 2:
                a = self._compile(token.children[0], depth)
                b = self._compile(token.children[1], depth)
                return "%s,%s" % (a, b)
            else:
                return self._compile(token.children[0], depth)
        elif token.type == Token.T_BREAK or token.type == Token.T_CONTINUE:

            return token.text
        elif token.type == Token.T_NEW:

            return "new " + self._compile(token.children[0], depth)
        elif token.type == Token.T_KEYWORD:
            if token.children:
                raise CompileError(token, "token has children")
            return token.text
        elif token.type == Token.T_ATTR:

            return token.text
        elif token.type == Token.T_DOCUMENTATION:

            pass
        elif token.type == Token.T_NEWLINE:

            raise CompileError(token, "unexpected")
        else:
            raise CompileError(token, "unable to compile token")

    def _compile(self, token, depth=0):

        if token.type == Token.T_MODULE:
            insert = False
            for child in token.children:
                if insert:
                    self._write_char(";")
                self._compile(child, depth + 1)
                insert = True
        elif token.type in (Token.T_OBJECT,):
            # commas are implied between clauses
            #self._write_char("??")
            self._write_char(token.value[0])
            insert = False
            for child in token.children:
                if insert:
                    self._write_char(",")
                self._write_line(depth)
                self._compile(child, depth + 1)

                insert = True
            if token.children:
                self._write_line(depth)
            self._write_char(token.value[1])
        elif token.type in (Token.T_LIST, Token.T_GROUPING, Token.T_ARGLIST):
            # commas are implied between clauses
            #self._write_char("??")
            self._write_char(token.value[0])
            insert = False
            for child in token.children:
                if insert:
                    self._write_char(",")
                self._compile(child, depth + 1)
                insert = True
            self._write_char(token.value[1])
        elif token.type == Token.T_BLOCK:
            self._write_char(token.value[0], Token.T_BLOCK_PUSH)
            self._write_line(depth+1)
            insert = False
            for child in token.children:
                if insert:
                    self._write_char(";")
                self._compile(child, depth + 1)
                insert = True
            self._write_char(token.value[1], Token.T_BLOCK_POP)
        elif token.type == Token.T_PREFIX:
            self._write(token)
            self._compile(token.children[0], depth)
        elif token.type == Token.T_POSTFIX:
            self._compile(token.children[0], depth)
            self._write(token)
        elif token.type == Token.T_BINARY:
            self._compile(token.children[0], depth)
            if token.value.isalpha():
                self._write(Token(Token.T_KEYWORD, token.line, token.index, token.value))
            else:
                self._write(token)
            self._compile(token.children[1], depth)
        elif token.type == Token.T_TERNARY:
            self._compile(token.children[0], depth)
            self._write_char("?")
            self._compile(token.children[1], depth)
            self._write_char(":")
            self._compile(token.children[2], depth)
        elif token.type == Token.T_VAR:
            self._write(token)
            self._compile(token.children[0], depth)
            #self._write_char(";")
        elif token.type in (Token.T_TEXT, Token.T_NUMBER, Token.T_STRING, Token.T_TEMPLATE_STRING):

            self._write(token)
        elif token.type == Token.T_FUNCTION:
            # TODO: resolve difference of T_FUNCTION T_FUNCTIONDEF
            self._write(token)
            self._compile(token.children[0], depth)
            self._compile(token.children[1], depth)
            self._compile(token.children[2], depth)
        elif token.type == Token.T_FUNCTIONCALL:
            for child in token.children:
                self._compile(child, depth)
        elif token.type == Token.T_FUNCTIONDEF:
            self._write_line(depth)
            for child in token.children:
                self._compile(child, depth)
        elif token.type == Token.T_IMPORT:
            self._write(Token(Token.T_KEYWORD, token.line, token.index, "import"))
            if token.value.endswith('.js'):
                self._write(Token(Token.T_STRING, token.line, token.index, repr(token.value)))
            else:
                self._write(token)
            if token.children[0].children:
                self._write(Token(Token.T_KEYWORD, token.line, token.index, "with"))
                self._compile(token.children[0], depth)
            self._write_line(depth)
        elif token.type == Token.T_EXPORT:
            pass
        elif token.type == Token.T_SUBSCR:
            self._compile(token.children[0], depth)
            self._write_char("[")
            for child in token.children[1:]:  # zero or one
                self._compile(child, depth)
            self._write_char("]")
        elif token.type == Token.T_BRANCH:
            self._write_line(depth)
            self._write(token)
            self._compile(token.children[0], depth)
            self._compile(token.children[1], depth)
            if len(token.children) == 3:
                self._write(Token(Token.T_KEYWORD, token.line, token.index, "else"))
                index = len(self.tokens)
                self._compile(token.children[2], depth)
        elif token.type == Token.T_FOR:
            self._write_line(depth)
            self._write(token)
            args, block = token.children

            # this arglist is special, if there are multiple clauses
            # separate them by semicolons instead of commas
            self._write_char('(')
            insert = False
            for child in args.children:
                if insert:
                    self._write_char(";")
                self._compile(child, depth)
                insert = True
            self._write_char(')')

            self._compile(block, depth)
        elif token.type == Token.T_DOWHILE:
            self._write_line(depth)
            self._write(token)
            self._compile(token.children[0], depth)
            self._write(Token(Token.T_KEYWORD, token.line, token.index, "while"))
            self._compile(token.children[1], depth)
        elif token.type == Token.T_WHILE:
            self._write_line(depth)
            self._write(token)
            self._compile(token.children[0], depth)
            self._compile(token.children[1], depth)
        elif token.type == Token.T_SWITCH:
            self._write(token)
            self._compile(token.children[0], depth)

            child = token.children[1]
            self._write_char(child.value[0], Token.T_BLOCK_PUSH)
            self._write_line(depth+1)
            insert = False
            for gchild in child.children:
                if insert:
                    self._write_char(";")
                self._compile(gchild, depth + 1)
                insert = True

                if gchild.type in (Token.T_CASE, Token.T_DEFAULT):
                    insert = False

            self._write_char(child.value[1], Token.T_BLOCK_POP)

        elif token.type == Token.T_CASE:
            self._write(token)
            self._compile(token.children[0], depth)
            self._write_char(':')

        elif token.type == Token.T_DEFAULT:
            self._write(token)
            self._write_char(':')

        elif token.type == Token.T_CLASS:
            self._write_line(depth)
            self._write(token)
            self._compile(token.children[0], depth)
            if len(token.children[1].children) > 0:
                self._write(Token(Token.T_KEYWORD, token.line, token.index, "extends"))
                self._write(token.children[1].children[0])
            self._compile(token.children[2], depth)
        elif token.type == Token.T_RETURN:
            self._write_line(depth)
            self._write(token)
            for child in token.children: # length is zero or one
                self._compile(child, depth)
        elif token.type == Token.T_COMMA:
            if len(token.children) == 2:
                self._compile(token.children[0], depth)
                self._write_char(",")
                self._compile(token.children[1], depth)
            else:
                self._compile(token.children[0], depth)
        elif token.type == Token.T_BREAK or token.type == Token.T_CONTINUE:
            self._write_line(depth)
            self._write(token)
        elif token.type == Token.T_NEW:
            self._write(token)
            for child in token.children:
                self._compile(child, depth)
        elif token.type == Token.T_THROW:
            self._write(token)
            for child in token.children:
                self._compile(child, depth)
        elif token.type in (Token.T_TRY, Token.T_CATCH, Token.T_FINALLY):
            # note that try will have one or more children
            # while catch always has 2 and finally always has 1
            self._write(token)
            for child in token.children:
                self._compile(child, depth)
        elif token.type == Token.T_KEYWORD:
            if token.children:
                raise CompileError(token, "token has children")
            self._write(token)
        elif token.type == Token.T_ATTR:

            self._write(token)
        elif token.type == Token.T_DOCUMENTATION:

            pass
        elif token.type == Token.T_NEWLINE:

            raise CompileError(token, "unexpected")
        else:
            raise CompileError(token, "unable to compile token")

    def _write(self, token):

        self.tokens.append((token.type, token.value))

    def _write_char(self, char, type=Token.T_SPECIAL):

        if self.tokens:
            t, c = self.tokens[-1]
            if char == ';':
                if t == Token.T_SPECIAL and c == ';':
                    return
                # this is valid when pretty printing, but not
                # when minifying
                #if t == Token.T_BLOCK_POP:
                #    return

        self.tokens.append((type, char))

    def _write_line(self, depth):
        self.tokens.append((Token.T_NEWLINE, ""))

def main():  # pragma: no cover

    text1 = """
    const \u263A = 1
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