#! cd .. && python3 -m daedalus.formatter
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
from .lexer import Lexer, Token, TokenError
from .parser import Parser

class FormatError(TokenError):
    pass

def diag(tokens):
    print([t.value for t in tokens])

def isalphanum(a, b):
    """ return true if a+b is not a reversible operation"""
    if a and b:
        c1 = a[-1]
        c2 = b[0]

        return (c1.isalnum() or c1 in '_$' or ord(c1) > 127) and \
               (c2.isalnum() or c2 in '_$' or ord(c2) > 127)
    return False

def isfunction(child):

    return child.type in (
        Token.T_FUNCTION,
        Token.T_ASYNC_FUNCTION,
        Token.T_GENERATOR,
        Token.T_ASYNC_GENERATOR,
        Token.T_ANONYMOUS_FUNCTION,
        Token.T_ASYNC_ANONYMOUS_FUNCTION,
        Token.T_ANONYMOUS_GENERATOR,
        Token.T_ASYNC_ANONYMOUS_GENERATOR,
        Token.T_METHOD,
        Token.T_LAMBDA,
    );

def isctrlflow(child):
    """
    returns true when there is no reason to place a semicolon
    after the production of the given token
    """
    if child.type == Token.T_BLOCK:
        return True
    elif child.type in (Token.T_BRANCH, Token.T_FOR_IN, Token.T_FOR_OF, Token.T_FOR):
        return True
    elif child.type in (Token.T_SWITCH, Token.T_WHILE, Token.T_FINALLY):
        if (child.children[-1].type == Token.T_BLOCK):
            return True
    elif child.type == Token.T_CLASS:
        if (child.children[-1].type == Token.T_CLASS_BLOCK):
            return True
    elif isfunction(child):
        if (child.children[-1].type == Token.T_BLOCK):
            return True
    elif child.type == Token.T_DOWHILE:
        if (child.children[-1].type == Token.T_ARGLIST):
            return True
    return False

class Formatter(object):
    def __init__(self, opts=None):
        super(Formatter, self).__init__()

        if not opts:
            opts = {}

        self.minify = opts.get('minify', True)
        self.pretty_print = not self.minify
        self.indent_width = int(opts.get('indent', 2))
        self.max_columns = int(opts.get('columns', 80 if self.pretty_print else 500))

    def format(self, mod):

        self.tokens = []
        self.stream = io.StringIO()
        self._null = Token(Token.T_NEWLINE, mod.line, mod.index, "")
        self._prev = self._null
        self._prev_char = ''

        self.tokens = self._format(mod)

        if self.pretty_print:
            return self._write_pretty()
        else:
            return self._write_minified()

    def _write_minified(self):

        # maximum length for any line is 4095 because of limitations
        # with some javascript compilers

        width = self.max_columns
        line_len = 0
        prev_type = Token.T_NEWLINE
        prev_text = ""
        for depth, type, text in self.tokens:

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

    def _write_pretty(self):

        width = self.max_columns
        line_len = 0
        prev_type = Token.T_NEWLINE
        prev_text = ""
        padding = " " * self.indent_width
        for depth, type, text in self.tokens:

            if line_len == 0 and type != Token.T_NEWLINE:
                line_len += self.stream.write(padding * (depth-1))

            elif isalphanum(prev_text, text):
                line_len += self.stream.write(" ")

            line_len += self.stream.write(text)

            if type == Token.T_NEWLINE:
                line_len = 0

            elif line_len > width and text in {'(', '{', '[', ';', ','}:
                self.stream.write("\n")
                line_len += self.stream.write(padding * (depth-1))
                line_len = 0

            prev_type = type
            prev_text = text
        return self.stream.getvalue()

    def _format(self, token):
        """ non-recursive implementation of _format

        for each node process the children in reverse order
        """

        seq = [(0, None, token)]
        out = []

        while seq:
            depth, state, token = seq.pop()

            if isinstance(token, str):

                out.append((depth, state, token))
            elif token.type == Token.T_MODULE:
                insert = False
                if self.pretty_print and len(token.children) > 0 and not isctrlflow(token.children[-1]):
                    seq.append((depth + 1, Token.T_SPECIAL, ";"))
                for child in reversed(token.children):

                    if insert and isctrlflow(child):
                        seq.append((depth + 1, Token.T_NEWLINE, "\n"))
                    elif insert:
                        seq.append((depth + 1, Token.T_NEWLINE, "\n"))
                        seq.append((depth + 1, Token.T_SPECIAL, ";"))
                    seq.append((depth + 1, None, child))
                    insert = True
            elif token.type == Token.T_BLOCK:
                seq.append((depth, Token.T_SPECIAL, token.value[1]))
                seq.append((depth, Token.T_NEWLINE, "\n"))
                first = True
                if self.pretty_print and len(token.children) > 0 and not isctrlflow(token.children[-1]):
                    seq.append((depth + 1, Token.T_SPECIAL, ";"))
                for child in reversed(token.children):
                    if child.type in (Token.T_CASE, Token.T_DEFAULT) or first:
                        insert = False
                    else:
                        insert = True

                    if insert and isctrlflow(child):
                        seq.append((depth + 1, Token.T_NEWLINE, "\n"))
                    elif insert:
                        seq.append((depth + 1, Token.T_NEWLINE, "\n"))
                        seq.append((depth + 1, Token.T_SPECIAL, ";"))

                    seq.append((depth + 1, None, child))

                    first = False

                seq.append((depth, Token.T_NEWLINE, "\n"))
                seq.append((depth, Token.T_SPECIAL, token.value[0]))
            elif token.type == Token.T_CLASS_BLOCK:
                # assumes all children are function definitions
                # which do not need a semicolon
                seq.append((depth, Token.T_SPECIAL, token.value[1]))
                seq.append((depth, Token.T_NEWLINE, "\n"))
                first = True
                for child in reversed(token.children):
                    if child.type in (Token.T_CASE, Token.T_DEFAULT) or first:
                        insert = False
                    else:
                        insert = True

                    if insert:
                        seq.append((depth + 1, Token.T_NEWLINE, "\n"))

                    seq.append((depth + 1, None, child))

                    first = False

                seq.append((depth, Token.T_NEWLINE, "\n"))
                seq.append((depth, Token.T_SPECIAL, token.value[0]))
            elif token.type == Token.T_OBJECT:
                seq.append((depth, Token.T_OBJECT, token.value[1]))
                insert = False
                for child in reversed(token.children):
                    if insert:
                        seq.append((depth, Token.T_SPECIAL, ","))
                    seq.append((depth + 1, None, child))
                    insert = True
                seq.append((depth, Token.T_OBJECT, token.value[0]))
            elif token.type in (Token.T_OBJECT, Token.T_LIST, Token.T_GROUPING, Token.T_ARGLIST):
                # commas are implied between clauses
                if len(token.value)!=2:
                    token.value = '[]'
                    print("TODO: warning %s" % token.type)
                seq.append((depth, Token.T_SPECIAL, token.value[1]))
                insert = False
                for child in reversed(token.children):
                    if insert:
                        seq.append((depth, Token.T_SPECIAL, ","))
                    seq.append((depth + 1, None, child))
                    insert = True
                seq.append((depth, Token.T_SPECIAL, token.value[0]))
            elif token.type == Token.T_UNPACK_SEQUENCE:
                # commas are implied between clauses
                seq.append((depth, Token.T_SPECIAL, token.value[1]))
                insert = False
                for child in reversed(token.children):
                    if insert:
                        seq.append((depth, Token.T_SPECIAL, ","))
                    seq.append((depth + 1, None, child))
                    insert = True
                seq.append((depth, Token.T_SPECIAL, token.value[0]))
            elif token.type == Token.T_LAMBDA:
                seq.append((depth, None, token.children[2]))

                if token.value.isalpha():
                    seq.append((depth, Token.T_KEYWORD, token.value))
                else:
                    seq.append((depth, token.type, token.value))
                seq.append((depth, None, token.children[1]))
            elif token.type in (Token.T_BINARY, Token.T_GET_ATTR, Token.T_LOGICAL_OR, Token.T_LOGICAL_AND, Token.T_INSTANCE_OF):
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
            elif token.type in (Token.T_PREFIX, Token.T_SPREAD, Token.T_YIELD, Token.T_YIELD_FROM):
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
                elif len(token.children) == 0:
                    raise FormatError(token, "no children")
                else:
                    seq.append((depth, None, token.children[0]))
            elif token.type in (Token.T_TEXT, Token.T_GLOBAL_VAR, Token.T_LOCAL_VAR, Token.T_FREE_VAR):

                out.append((depth, token.type, token.value))
            elif token.type == Token.T_REGEX:

                out.append((depth, token.type, token.value))
            elif token.type == Token.T_NUMBER:

                out.append((depth, token.type, token.value))
            elif token.type == Token.T_TAGGED_TEMPLATE:
                lhs,rhs = token.children
                seq.append((depth, None, rhs))
                seq.append((depth, None, lhs))
            elif token.type == Token.T_TEMPLATE_EXPRESSION:
                seq.append((depth, Token.T_SPECIAL, '}'))
                for child in reversed(token.children):
                    seq.append((depth, None, child))
                seq.append((depth, Token.T_SPECIAL, '${'))
            elif token.type == Token.T_TEMPLATE_STRING:
                # the value of a template string is the original unparsed value
                # the children represent the parsed and transformed value
                # children are either T_STRING or T_TEMPLATE_EXPRESSION
                seq.append((depth, Token.T_SPECIAL, '`'))
                for child in reversed(token.children):
                    seq.append((depth, None, child))
                seq.append((depth, Token.T_SPECIAL, '`'))
            elif token.type == Token.T_STRING:

                out.append((depth, token.type, token.value))
            elif token.type == Token.T_KEYWORD:

                out.append((depth, token.type, token.value))
            elif token.type == Token.T_ATTR:

                out.append((depth, token.type, token.value))
            elif token.type == Token.T_DOCUMENTATION:

                out.append((depth, token.type, token.value))
            elif token.type == Token.T_NEWLINE:

                raise FormatError(token, "unexpected")
            elif token.type == Token.T_VAR:
                first = True
                for child in reversed(token.children):
                    if not first:
                        seq.append((depth + 1, Token.T_SPECIAL, ","))
                    seq.append((depth, None, child))

                    first = False
                seq.append((depth, token.type, token.value))
            elif token.type == Token.T_CLASS:
                seq.append((depth, None, token.children[2]))
                if len(token.children[1].children) > 0:
                    if self.pretty_print:
                        seq.append((depth, Token.T_TEXT, " "))
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
                if token.value:
                    seq.append((depth, token.type, token.value))
            elif token.type == Token.T_GENERATOR:
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
                seq.append((depth, Token.T_KEYWORD, "function"))
            elif token.type == Token.T_ANONYMOUS_GENERATOR:
                for child in reversed(token.children[1:]):
                    seq.append((depth, None, child))
                seq.append((depth, Token.T_KEYWORD, "function*"))
            elif token.type == Token.T_ASYNC_FUNCTION:
                for child in reversed(token.children):
                    seq.append((depth, None, child))
                seq.append((depth, Token.T_KEYWORD, "function"))
                seq.append((depth, Token.T_KEYWORD, "async"))
            elif token.type == Token.T_ASYNC_GENERATOR:
                for child in reversed(token.children):
                    seq.append((depth, None, child))
                seq.append((depth, Token.T_KEYWORD, "function*"))
                seq.append((depth, Token.T_KEYWORD, "async"))
            elif token.type == Token.T_ASYNC_ANONYMOUS_FUNCTION:
                for child in reversed(token.children[1:]):
                    seq.append((depth, None, child))
                seq.append((depth, Token.T_KEYWORD, "function"))
                seq.append((depth, Token.T_KEYWORD, "async"))
            elif token.type == Token.T_ASYNC_ANONYMOUS_GENERATOR:
                for child in reversed(token.children[1:]):
                    seq.append((depth, None, child))
                seq.append((depth, Token.T_KEYWORD, "function*"))
                seq.append((depth, Token.T_KEYWORD, "async"))
            elif token.type == Token.T_IMPORT:
                sys.stdout.write("import not implemented\n")
                pass
            elif token.type == Token.T_IMPORT_MODULE:
                sys.stdout.write("import module not implemented\n")
                pass
            elif token.type == Token.T_INCLUDE:
                sys.stdout.write("include not implemented\n")
                pass
            elif token.type == Token.T_EXPORT:
                sys.stdout.write("export not implemented\n")
                pass
            elif token.type == Token.T_EXPORT_DEFAULT:
                sys.stdout.write("export not implemented\n")
                pass
            elif token.type == Token.T_SUBSCR:
                seq.append((depth, Token.T_SPECIAL, "]"))
                for child in reversed(token.children[1:]):
                    seq.append((depth, None, child))
                seq.append((depth, Token.T_SPECIAL, "["))
                seq.append((depth, None, token.children[0]))
            elif token.type == Token.T_BRANCH:
                if len(token.children) == 3:
                    if not isctrlflow(token.children[2]):
                        seq.append((depth, Token.T_SPECIAL, ";"))
                    seq.append((depth, None, token.children[2]))
                    seq.append((depth, Token.T_KEYWORD, "else"))
                if not isctrlflow(token.children[1]):
                    seq.append((depth, Token.T_SPECIAL, ";"))
                seq.append((depth, None, token.children[1]))
                seq.append((depth, None, token.children[0]))
                seq.append((depth, token.type, token.value))
            elif token.type == Token.T_FOR:
                if len(token.children) == 1:
                    print(token.toString(2))
                    sys.stderr.write("error: line: %d col: %d" % (token.line, token.index));
                    args = token.children[0]
                else:
                    args, block = token.children
                    if not isctrlflow(block):
                        seq.append((depth, Token.T_SPECIAL, ";"))
                    seq.append((depth+1, None, block))
                # this arglist is special, if there are multiple clauses
                # separate them by semicolons instead of commas

                if self.pretty_print:
                    seq.append((depth, Token.T_NEWLINE, "\n"))

                seq.append((depth, Token.T_SPECIAL, ')'))
                insert = False
                for child in reversed(args.children):
                    if insert:
                        seq.append((depth, Token.T_SPECIAL, ";"))
                    seq.append((depth, None, child))
                    insert = True
                seq.append((depth, Token.T_SPECIAL, '('))
                seq.append((depth, token.type, token.value))
            elif token.type == Token.T_FOR_IN:
                varexpr, iterable, block = token.children
                if not isctrlflow(block):
                    seq.append((depth, Token.T_SPECIAL, ";"))
                seq.append((depth, None, block))
                seq.append((depth, Token.T_SPECIAL, ')'))
                seq.append((depth, None, iterable))
                seq.append((depth, Token.T_KEYWORD, 'in'))
                seq.append((depth, None, varexpr))
                seq.append((depth, Token.T_SPECIAL, '('))
                seq.append((depth, token.type, token.value))
            elif token.type == Token.T_FOR_OF:
                varexpr, iterable, block = token.children
                if not isctrlflow(block):
                    seq.append((depth, Token.T_SPECIAL, ";"))
                seq.append((depth, None, block))
                seq.append((depth, Token.T_SPECIAL, ')'))
                seq.append((depth, None, iterable))
                seq.append((depth, Token.T_KEYWORD, 'of'))
                seq.append((depth, None, varexpr))
                seq.append((depth, Token.T_SPECIAL, '('))
                seq.append((depth, token.type, token.value))
            elif token.type == Token.T_DOWHILE:
                seq.append((depth, None, token.children[1]))
                if self.pretty_print:
                    seq.append((depth, Token.T_TEXT, " "))
                seq.append((depth, Token.T_KEYWORD, "while"))
                if self.pretty_print:
                    seq.append((depth, Token.T_TEXT, " "))
                seq.append((depth, None, token.children[0]))
                if self.pretty_print:
                    seq.append((depth, Token.T_TEXT, " "))
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

                out.append((depth,token.type, token.value))
            elif token.type == Token.T_RETURN:
                for child in reversed(token.children):  # length is zero or one
                    seq.append((depth, None, child))
                seq.append((depth, token.type, token.value))
            elif token.type == Token.T_NEW:
                for child in reversed(token.children):  # length is zero or one
                    seq.append((depth, None, child))
                seq.append((depth, token.type, token.value))
            elif token.type == Token.T_THROW:
                for child in reversed(token.children):  # length is zero or one
                    seq.append((depth, None, child))
                seq.append((depth, token.type, token.value))
            elif token.type in (Token.T_TRY, Token.T_CATCH, Token.T_FINALLY):
                # note that try will have one or more children
                # while catch always has 2 and finally always has 1
                for child in reversed(token.children):  # length is zero or one
                    seq.append((depth, None, child))
                seq.append((depth, token.type, token.value))
            elif token.type == Token.T_EMPTY_TOKEN:
                pass
            elif token.type == Token.T_CLOSURE:
                print("TODO warning closure")
            elif token.type == Token.T_DELETE_VAR:
                print("TODO warning delete var")
            else:
                raise FormatError(token, "token not supported: %s" % token.type)
        return out

def main():  # pragma: no cover

    #text1 = open("./res/daedalus/index.js").read()

    text1 = """for (;a,b;c,d) {}"""

    text1 = """
    switch() {}
    do {} while ()
    x = 0
    """

    tokens = Lexer().lex(text1)
    mod = Parser().parse(tokens)

    print(mod.toString())

    text2 = Formatter({'minify': False}).format(mod)

    print("-" * 79)

    print(text2)
    print("-" * 79)
    print(len(text2), len(text1))


if __name__ == '__main__':  # pragma: no cover
    main()
