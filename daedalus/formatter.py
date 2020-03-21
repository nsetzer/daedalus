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
    """ return true if a+b is not a reversable operation"""
    if a and b:
        c1 = a[-1]
        c2 = b[0]

        return (c1.isalnum() or c1 == '_' or ord(c1) > 127) and \
               (c2.isalnum() or c2 == '_' or ord(c2) > 127)
    return False

class Formatter(object):
    def __init__(self, opts=None):
        super(Formatter, self).__init__()

        self.pretty_print = True
        self.padding = "    "

        if not opts:
            opts = {}

        self.minify = opts.get('minify', False)

    def format(self, mod):

        self.tokens = []
        self.stream = io.StringIO()
        self._null = Token(Token.T_NEWLINE, mod.line, mod.index, "")
        self._prev = self._null
        self._prev_char = ''

        self.tokens = self._format(mod)

        return self._write_minified()

    def _write_minified(self):

        # maximum length for any line is 4095 becuase of limitations
        # of some javascript compilers
        width = 240
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

    def _format(self, token):
        """ non-recursive implementation of _format

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
                    seq.append((depth + 1, None, child))
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

                    seq.append((depth + 1, None, child))

                    first = False
                seq.append((depth, Token.T_SPECIAL, token.value[0]))
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
            elif token.type in (Token.T_BINARY, Token.T_LOGICAL_OR, Token.T_LOGICAL_AND, Token.T_INSTANCE_OF):
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
                else:
                    seq.append((depth, None, token.children[0]))
            elif token.type in (Token.T_TEXT, Token.T_GLOBAL_VAR, Token.T_LOCAL_VAR, Token.T_FREE_VAR):

                out.append((token.type, token.value))
            elif token.type == Token.T_REGEX:

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

                raise FormatError(token, "unexpected")
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
            elif token.type == Token.T_STATIC_METHOD:
                seq.append((depth, None, token.children[2]))
                seq.append((depth, None, token.children[1]))
                seq.append((depth, None, token.children[0]))
                seq.append((depth, Token.T_KEYWORD, "static"))
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
            elif token.type == Token.T_EXPORT:
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
            elif token.type == Token.T_FOR_IN:
                varexpr, iterable, block = token.children
                seq.append((depth, None, block))
                seq.append((depth, Token.T_SPECIAL, ')'))
                seq.append((depth, None, iterable))
                seq.append((depth, Token.T_KEYWORD, 'in'))
                seq.append((depth, None, varexpr))
                seq.append((depth, Token.T_SPECIAL, '('))
                seq.append((depth, token.type, token.value))
            elif token.type == Token.T_FOR_OF:
                varexpr, iterable, block = token.children
                seq.append((depth, None, block))
                seq.append((depth, Token.T_SPECIAL, ')'))
                seq.append((depth, None, iterable))
                seq.append((depth, Token.T_KEYWORD, 'of'))
                seq.append((depth, None, varexpr))
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

    text1 = """
    async function (x) { return 1 }
    """

    #text1 = open("./res/daedalus/index.js").read()

    tokens = Lexer().lex(text1)
    mod = Parser().parse(tokens)

    print(mod.toString())

    cc = Formatter()
    text2 = Formatter().format(mod)

    print("-" * 79)

    print(text2)
    print("-" * 79)
    print(len(text2), len(text1))


if __name__ == '__main__':  # pragma: no cover
    main()
