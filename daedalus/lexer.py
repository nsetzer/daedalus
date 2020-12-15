#! cd .. && python3 -m daedalus.lexer

# TODO: better support for regex
import logging
import sys
import io

from .token import Token, TokenError

class LexError(TokenError):
    pass

# special characters that never combine with other characters
chset_special1 = "{}[](),~;:#"
# special characters that may combine with other special characters
chset_special2 = "+-*/&|^=<>%!@?"
chset_number_base  = "0123456789"
# characters that may exist in a number, either:
#   int, oct, hex, float, imaginary
# this includes all possible and many impossible combinations
# the compiler will determine if the token is valid
chset_number  = "0123456789nxob_.jtgmkABCDEFabcdef"

# the number of characters to read for a string encoding
char_len = {'o': 3, 'x': 2, 'u': 4, 'U': 8}
# the base used to convert a string to a single character
char_base = {'o': 8, 'x': 16, 'u': 16, 'U': 16}

reserved_words = {
    # types
    'boolean', 'byte', 'char', 'double', 'false', 'int', 'long', 'null', 'short', 'true',
    # keywords
    'async', 'await', 'break', 'case',
    'class', 'const', 'continue', 'debugger', 'default',
    'delete', 'do', 'else', 'enum', 'eval', 'export', 'extends',
    'final', 'finally', 'float', 'for', 'function', 'goto', 'if',
    'implements', 'import', 'in', 'instanceof', 'interface', 'let',
    'new', 'package',
    'return', 'static', 'super', 'switch',
    'this', 'throw', 'throws', 'transient', 'try', 'typeof', 'var',
    'void', 'volatile', 'while', 'with', 'yield', 'do',
}

# TODO: e.x. {public: 'abc123'} will fail since public is a keyword
reserved_words_extra = {
    'private', 'protected', 'public', 'native',
    'abstract', 'arguments', 'synchronized', 'from',
    'module', "pyimport", "catch",
    "constexpr"
}

# symbols for operators that have length 1
operators1 = set("+-~*/%@&^|!:.,;=(){}[]#")

# operators composed of 2 or more special characters
# which do not form a prefix of some other operator
# used to break longers strings of special characters into valid operators
operators2 = {
    "+=", "-=", "*=", "**=", "/=", "%=", "@=", "|=", "&=", "^=", ">>=", "<<=",
    "<", "<=", ">", ">=", "===", "!==",
    "??",
    "&&",
    "||",
    "=>",
    "|>",
    "++", "--",
    "->", "=>", "?.", "..."
}

# operators composed of 2 or more characters that are also a prefix
# of an operator found in the previous list.
operators2_extra = set(["?", "==", "!=", "**", ">>", "<<"])

# the set of all valid operators for this language
# if an operator is not in this list, then it is a syntax error
operators3 = operators1 | operators2 | operators2_extra

def char_reader(f):
    # convert a file like object into a character generator
    buf = f.read(1024)
    while buf:
        for c in buf:
            yield c
        buf = f.read(1024)

class LexerBase(object):
    """
    base class for a generic look-ahead-by-N lexer

    Note: using an array and ''.join() cut the time spent in _putch
    down from 30 seconds to 1 second for inputs as long as 1024 * 1024 bytes.
    previous it was well over a minute when running under cProfile.

    using the char_reader for files is slower than loading the whole file
    into memory first
    """

    def __init__(self):
        super(LexerBase, self).__init__()

    def _init(self, seq, default_type):

        # the line of the most recently consumed character
        self._line = 1
        # the column of the line of the most recently consumed character
        self._index = -1

        self._default_type = default_type
        # the type of the current token
        self._type = default_type
        # the value of the current token
        self._tok = []
        self._len = 0
        # the line where the current token began
        self._initial_line = -1
        # the column of the current line where the token began
        self._initial_index = -1
        # list of characters read from the input stream, but not consumed
        self._peek_char = []
        # the last token successfully pushed
        self._prev_token = None

        # define an iterator (generator) which
        # yields individual (utf-8) characters from
        # either an open file or an existing iterable
        if hasattr(seq, 'read'):
            self.g = char_reader(seq)
            self.g_iter = True
        else:
            self.g = list(seq)
            self.g_iter = False
            self.g_idx = 0
            self.g_len = len(self.g)

        self.tokens = []

    def _getch_impl(self):
        """ read one character from the input stream"""
        if self.g_iter:
            c = next(self.g)
        else:
            if self.g_idx >= self.g_len:
                raise StopIteration()
            c = self.g[self.g_idx]
            self.g_idx += 1

        if c == '\n':
            self._line += 1
            self._index = -1
        else:
            self._index += 1
        return c

    def _getch(self):
        """ return the next character """
        if self._peek_char:
            c = self._peek_char.pop(0)
        else:
            c = self._getch_impl()
        return c

    def _getstr(self, n):
        """ return the next N characters """

        s = ''
        try:
            for i in range(n):
                s += self._getch()
        except StopIteration:
            return None
        return s

    def _peekch(self):
        """ return the next character, do not advance the iterator """

        if not self._peek_char:
            self._peek_char.append(self._getch_impl())
        return self._peek_char[0]

    def _peekstr(self, n):
        """ return the next N characters, do not advance the iterator """
        while len(self._peek_char) < n:
            self._peek_char.append(self._getch_impl())
        return ''.join(self._peek_char[:n])

    def _putch(self, c):
        """ append a character to the current token """

        if self._initial_line < 0:
            self._initial_line = self._line
            self._initial_index = self._index

        self._tok.append(c)

    def _gettok(self):
        return ''.join(self._tok)

    def _restok(self):
        self._tok = []

    def _push_endl(self):
        """ push an end of line token """
        if self.tokens and self.tokens[-1].type == Token.T_NEWLINE:
            return

        self.tokens.append(Token(
            Token.T_NEWLINE,
            self._line,
            0,
            "")
        )
        self._type = self._default_type
        self._initial_line = -1
        self._initial_index = -1
        self._restok()

    def _push(self):
        """ push a new token """

        self._prev_token = Token(
            self._type,
            self._initial_line,
            self._initial_index,
            self._gettok()
        )
        self.tokens.append(self._prev_token)
        self._type = self._default_type
        self._initial_line = -1
        self._initial_index = -1
        self._restok()

    def _maybe_push(self):
        """ push a new token if there is a token to push """
        if self._tok:
            self._push()

    def _error(self, message):

        token = Token(self._type, self._initial_line, self._initial_index, self._tok)
        raise LexError(token, message)

class Lexer(LexerBase):
    """
    read tokens from a file or string
    """

    def __init__(self, opts=None):
        super(Lexer, self).__init__()

        if not opts:
            opts = {}
        self.preserve_documentation = opts.get('preserve_documentation', False)

    def lex(self, seq):

        self._init(seq, Token.T_TEXT)

        error = 0
        try:
            self._lex()
        except StopIteration:
            error = 1

        if error:
            tok = Token("", self._line, self._index, "")
            raise LexError(tok, "Unexpected End of Sequence")

        return self.tokens

    def _lex(self):

        while True:

            try:
                c = self._getch()
            except StopIteration:
                break

            if c == '\n':
                self._maybe_push()
                self._push_endl()

            elif c == '/':
                self._lex_comment()

            elif c == '\\':
                c = self._peekch()

                if c != '\n':
                    raise self._error("expected newline after '\\'. found '%s'" % c)

                self._getch()  # consume the newline

            elif c == '\'' or c == '\"' or c == '`':
                self._lex_string(c)

            elif c in chset_special1:
                self._maybe_push()
                self._putch(c)
                self._type = Token.T_SPECIAL
                self._push()

            elif c == '*':
                self._maybe_push()

                # generator keywords mix special charactes and alpha characters
                # this allows for space between the *, which would normally
                # be a syntax error

                if len(self.tokens) and self.tokens[-1].value in ('function', 'yield'):
                    self.tokens[-1].value += c
                else:
                    self._putch(c)
                    self._lex_special2()

            elif c == '?':
                # collect optional chaining operator when a . follows ?
                # otherwise collect the ternary operator
                self._maybe_push()
                self._type = Token.T_SPECIAL
                self._putch(c)
                try:
                    nc = self._peekch()
                except StopIteration:
                    nc = None

                if nc:
                    if nc == '.' or nc == '?':
                        # collect ?. or ??
                        self._putch(self._getch())
                    self._push()
                else:
                    self._push()

            elif c in chset_special2:
                self._maybe_push()
                self._putch(c)
                self._lex_special2()

            elif c == '.':
                self._maybe_push()
                self._putch(c)
                try:
                    nc = self._peekch()
                except StopIteration:
                    nc = None

                if nc and nc == '.':
                    # collect .. and ...
                    self._type = Token.T_SPECIAL
                    self._putch(self._getch())

                    try:
                        nc = self._peekch()
                    except StopIteration:
                        nc = None

                    if nc and nc == '.':
                        self._putch(self._getch())
                        self._push()

                elif nc and nc in chset_number_base:
                    self._lex_number()
                else:
                    self._type = Token.T_SPECIAL
                    self._push()

            elif not self._tok and c in chset_number_base:
                self._maybe_push()
                self._putch(c)
                self._lex_number()

            elif c == ' ' or c == '\t' or ord(c) < 0x20:
                # ignore white space and ASCII control codes
                # newline was already processed above
                self._maybe_push()
            else:
                self._putch(c)

        self._maybe_push()

    def _lex_special2(self):
        """
        lex sequences of special characters
        break these characters apart using prefix matching

        e.g. '=-' becomes '=' and '-'
        e.g. '+++' becomes '++' and '+'
        """

        self._type = Token.T_SPECIAL

        while True:
            try:
                nc = self._peekch()
            except StopIteration:
                nc = None

            if nc and nc in chset_special2:
                if nc == "/":
                    # next time around the loop lex as a comment/regex/etc
                    break
                else:
                    if self._gettok() + nc not in operators3:
                        self._push()
                        self._type = Token.T_SPECIAL
                    self._putch(self._getch())
                    self._maybe_push_op()
            else:
                self._maybe_push()
                self._type = Token.T_TEXT
                break

    def _lex_string(self, string_terminal):
        """ read a string from the stream, terminated by the given character

        strings are read with no processing so that the compiler can produce
        an identical string token.
        """

        self._maybe_push()
        self._type = Token.T_TEMPLATE_STRING if string_terminal == '`' else Token.T_STRING
        self._putch(string_terminal)

        escape = False

        while True:
            try:
                c = self._getch()
            except StopIteration:
                c = None

            if c is None:
                raise self._error("unterminated string")

            elif c == "\\":
                # expect exactly one character after an escape
                # pass through unmodified, let the downstream
                # parser/compiler handle string processing.
                self._putch(c)
                try:
                    c = self._getch()
                except StopIteration:
                    c = None

                if c is None:
                    raise self._error("expected character")
                self._putch(c)

            elif c == "\n" and string_terminal != '`':
                raise self._error("unterminated string")

            elif c == string_terminal:
                self._putch(string_terminal)
                self._push()
                break
            else:
                self._putch(c)

    def _lex_number(self):
        """ read a number from the stream """

        self._type = Token.T_NUMBER

        while True:
            try:
                c = self._peekch()
            except StopIteration:
                break

            if c in chset_number:
                self._putch(self._getch())
            else:
                self._push()
                break

    def _lex_comment(self):
        """

        the character '/' is overloaded to mean 1 of 5 things

            - //      : single line comment
            - /* */   : multi line comment
            - /** */  : multi line documentation
            - a / b   : division
            - /^$/    : regular expression

        comments produce no token
        """

        self._maybe_push()
        c = self._peekch()

        if c == '/':
            self._lex_single_comment()
        elif c == '=':
            self._putch('/')
            self._lex_special2()
        elif c == '*':
            s = self._peekstr(2)
            if s == '**' and self.preserve_documentation:
                self._lex_documentation()
            else:
                self._lex_multi_comment()
        elif not Token.basicType(self._prev()):
            self._type = Token.T_REGEX
            self._putch('/')
            self._lex_regex()
        else:
            self._type = Token.T_SPECIAL
            self._putch('/')
            self._push()

    def _lex_single_comment(self):
        """ read a comment and produce no token """

        while True:
            try:
                c = self._getch()
            except StopIteration:
                break

            if c == '\n':
                self._push_endl()
                break

    def _lex_multi_comment(self):
        """ read a comment and produce no token """

        while True:
            try:
                c = self._getch()
            except StopIteration:
                break

            if c == '*':
                try:
                    c = self._peekch()
                except StopIteration:
                    break

                if c == '/':
                    self._getch()
                    break

    def _lex_documentation(self):
        """ read a comment and produce no token """
        self._type = Token.T_DOCUMENTATION
        self._putch("/")
        while True:
            try:
                c = self._getch()
            except StopIteration:
                break

            if c == '*':
                try:
                    c2 = self._peekch()
                except StopIteration:
                    break

                self._putch(c)

                if c2 == '/':

                    self._putch(self._getch())
                    self._push()
                    break

            else:
                self._putch(c)

    def _lex_regex(self):

        while True:
            try:
                c = self._getch()
            except StopIteration:
                break

            if c == '\\':
                self._putch(c)
                self._putch(self._getch())
            elif c == '/':
                # terminate the regex parsing but
                # don't push the token
                # this will allow for arbitrary
                # flags to be appended
                # TODO: enumerate the allowed flags
                self._putch(c)
                break
            else:
                self._putch(c)

    def _prev(self):
        i = len(self.tokens) - 1
        while i >= 0:
            if self.tokens[i].type != Token.T_NEWLINE:
                return self.tokens[i]
            i -= 1
        return None

    def _maybe_push_op(self):
        if self._tok and self._gettok() in operators2:
            self._push()
            self._type = Token.T_SPECIAL

    def _push(self):
        t = self._gettok()
        if self._type == Token.T_TEXT and t in reserved_words:
            self._type = Token.T_KEYWORD
        if self._type == Token.T_SPECIAL and t not in operators3:
            self._error("unknown operator")
        super()._push()

Lexer.reserved_words = {*reserved_words, *reserved_words_extra}

import timeit
import cProfile
import re

def perf():

    text = "const x = '%s';" % ("a" * (1024 * 1024))

    lexer = Lexer()
    lexer.lex(text)
    return 0


def main():

    cProfile.run("perf()")

    print("done")

def mainx():  # pragma: no cover

    # r.match(/filename[^;=\\n]*=((['"]).*?\\2|[^;\\n]*)/)
    # r.match(2/3)

    text1 = """
    //var f=/\\{ *([\\w_-]+) *\\}/g

    """

    if len(sys.argv) == 2 and sys.argv[1] == "-":
        text1 = sys.stdin.read()

    print(text1)
    tokens = Lexer().lex(text1)
    for token in tokens:
        print(token)


if __name__ == '__main__':  # pragma: no cover
    main()
