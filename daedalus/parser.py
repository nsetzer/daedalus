#! cd .. && python3 -m daedalus.parser
"""
https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Operators/Operator_Precedence


https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Statements/block
blocks can be labeled

https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Statements/import
imports are complicated

"""
import sys
import ast
from .lexer import Lexer, Token, TokenError

class ParseError(TokenError):
    pass

def diag(tokens):
    print([t.value for t in tokens])

class Parser(object):

    W_BRANCH_FALSE = 1
    W_BRANCH_TRUE  = 2
    W_BLOCK_UNSAFE  = 3
    W_UNSUPPORTED = 4
    W_EXPORT_DEFAULT = 5
    W_VAR_USED = 6

    def __init__(self,):
        super(Parser, self).__init__()

        L2R = 1
        R2L = -1

        self.precedence = [
            (L2R, self.visit_grouping, ['(', '{', '[']),
            (R2L, self.visit_unary_prefix, ['#']),
            (L2R, self.visit_grouping2, ['.', "?."]),  # also: x[], x()
            (L2R, self.visit_new, []),
            (L2R, self.visit_unary_postfix, ['++', '--']),
            (R2L, self.visit_unary_prefix, ['!', '~', '+', '-', '++', '--']),
            (R2L, self.visit_prefix, ['typeof', 'void', 'delete', 'await']),
            (R2L, self.visit_binary, ['**']),
            (L2R, self.visit_binary, ['*', '/', '%']),
            (L2R, self.visit_binary, ['+', '-']),
            (L2R, self.visit_binary, ['<<', '>>', ">>>"]),
            (L2R, self.visit_binary, ['<', '<=', ">", ">=", "in", "instanceof"]),
            (L2R, self.visit_binary, ['==', '!=', '===', '!==']),
            (L2R, self.visit_binary, ['&']),
            (L2R, self.visit_binary, ['^']),
            (L2R, self.visit_binary, ['|']),
            (L2R, self.visit_binary, ['??']),
            (L2R, self.visit_binary, ['&&']),
            (L2R, self.visit_binary, ['||']),
            (L2R, self.visit_ternary, ['?']),
            (L2R, self.visit_binary, ['|>']),  # unsure where to place in sequence
            (L2R, self.visit_unary, ['...']),
            (L2R, self.visit_binary, ['=', '+=', '-=', '**=', '*=', '/=',
                                      '&=', '<<=', '>>=', '>>>=', '&=', '^=',
                                      '|=']),
            (R2L, self.visit_unary, ['yield', 'yield*']),
            (L2R, self.visit_keyword_case, []),
            (L2R, self.visit_binary, [':']),
            (L2R, self.visit_lambda, ['=>']),
            (L2R, self.visit_comma, [',']),
            (L2R, self.visit_keyword, []),
            (L2R, self.visit_keyword_import_export, []),
            (L2R, self.visit_cleanup, []),
        ]

        self.warnings = {
            Parser.W_BRANCH_FALSE: "false branch of if statement is not safe",
            Parser.W_BRANCH_TRUE: "true branch of if statement is not safe",
            Parser.W_BLOCK_UNSAFE: "block statement is not safe",
            Parser.W_UNSUPPORTED: "token not supported",
            Parser.W_EXPORT_DEFAULT: "meaningless export default",
            Parser.W_VAR_USED: "unsafe use of keyword var",
        }

        self.disabled_warnings = set()

        self._offset = 0  # used by consume in the negative direction

    def warn(self, token, type, message=None):

        if type in self.disabled_warnings:
            return

        text = self.warnings[type]
        if message:
            text += ":" + message

        text = "WARNING: line: %d column: %d type: %s value: %s : %s\n" % (
            token.line, token.index, token.type, token.value, text)

        sys.stdout.write(text)

    def parse(self, tokens):

        self.group(tokens)

        mod = Token(Token.T_MODULE, 0, 0, "")
        mod.children = tokens

        self.transform_grouping(mod, None)
        self.transform_flatten(mod, None)

        return mod

    def peek_token(self, tokens, token, index, direction):
        """
        return the index of the token that would be returned by consume
        """

        j = index + direction
        while 0 <= j < len(tokens):
            tok1 = tokens[j]
            if tok1.type == Token.T_SPECIAL and tok1.value == ";":
                break
            elif tok1.type == Token.T_SPECIAL and tok1.value == ",":
                break
            elif tok1.type == Token.T_NEWLINE:
                j += direction
            elif tok1.type == Token.T_KEYWORD and tok1.value not in ("true", "false", "null", "this", "new", "function", "class"):
                break
            else:
                return j
        return None

    def peek_keyword(self, tokens, token, index, direction):
        """
        return the index of the token that would be returned by consume
        """

        j = index + direction
        while 0 <= j < len(tokens):
            tok1 = tokens[j]
            if tok1.type == Token.T_SPECIAL and tok1.value == ";":
                break
            elif tok1.type == Token.T_SPECIAL and tok1.value == ",":
                break
            elif tok1.type == Token.T_NEWLINE:
                j += direction
            else:
                return j
        return None

    def consume(self, tokens, token, index, direction, maybe=False):
        """

        Note: self._offset is set when direction is negative this counts
        the number of items consumed and should be added to the index
        self._offset is reset on ever call, and should be cached
        """

        expression_whitelist = ("true", "false", "null", "this", "new", "function", "class", "catch")
        self._offset = 0
        index_tok1 = index + direction
        while 0 <= index_tok1 < len(tokens):
            tok1 = tokens[index_tok1]

            if tok1.type == Token.T_SPECIAL and tok1.value == ";":
                break
            elif tok1.type == Token.T_SPECIAL and tok1.value == ",":
                break
            elif tok1.type == Token.T_NEWLINE:
                tokens.pop(index_tok1)
                if direction < 0:
                    self._offset += direction
                    index_tok1 += direction
            elif tok1.type == Token.T_KEYWORD and tok1.value not in expression_whitelist:
                break
            else:
                return tokens.pop(index_tok1)

        if maybe:
            return None

        side = "rhs" if direction > 0 else "lhs"
        if 0 <= index_tok1 < len(tokens):
            raise ParseError(tokens[index_tok1], "invalid token on %s of %s" % (side, token.value))
        raise ParseError(token, "missing token on %s" % side)

    def consume_keyword(self, tokens, token, index, direction, maybe=False):
        # TODO: this should be changed to only accept keywords
        index_tok1 = index + direction
        while 0 <= index_tok1 < len(tokens):
            tok1 = tokens[index_tok1]

            if tok1.type == Token.T_SPECIAL and tok1.value == ";":
                break
            elif tok1.type == Token.T_SPECIAL and tok1.value == ",":
                break
            elif tok1.type == Token.T_NEWLINE:
                tokens.pop(index_tok1)
            else:
                return tokens.pop(index_tok1)

        if maybe:
            return None

        side = "rhs" if direction > 0 else "lhs"
        if 0 <= index_tok1 < len(tokens):
            raise ParseError(tokens[index_tok1], "invalid token on %s of %s" % (side, token.value))
        raise ParseError(token, "missing token on %s" % side)

    def group(self, tokens, parent=None):

        for direction, callback, operators in self.precedence:
            i = 0
            while i < len(tokens):

                if direction < 0:
                    j = len(tokens) - i - 1
                else:
                    j = i

                i += callback(parent, tokens, j, operators)

    def visit_grouping(self, parent, tokens, index, operators):

        token = tokens[index]

        if token.value not in operators or token.type not in Token.T_SPECIAL:
            return 1

        pairs = {
            '(': ')',
            '[': ']',
            '{': '}',
        }

        if token.value in pairs:
            self.collect_grouping(tokens, index, token.value, pairs[token.value])
            self.group(token.children, token)
            return 1
        return 1

    def visit_grouping2(self, parent, tokens, index, operators):

        token = tokens[index]
        if token.type == Token.T_SPECIAL and token.value in ('.', '?.'):
            rhs = self.consume(tokens, token, index,  1)
            lhs = self.consume(tokens, token, index, -1)
            if rhs.type == Token.T_TEXT:
                rhs.type = Token.T_ATTR
            token.type = Token.T_BINARY
            token.children = [lhs, rhs]

            return self._offset

        if token.type == Token.T_GROUPING and token.value == '()':
            i1 = self.peek_token(tokens, token, index, -1)
            # or (tokens[i1].type == Token.T_BINARY and tokens[i1].value in (".", "?."))
            if i1 is not None and tokens[i1].type != Token.T_SPECIAL:
                lhs = self.consume(tokens, token, index, -1)
                if lhs.type == Token.T_KEYWORD:
                    tok1 = Token(Token.T_FUNCTIONDEF, token.line, token.index, "")
                else:
                    tok1 = Token(Token.T_FUNCTIONCALL, token.line, token.index, "")
                tok1.children = [lhs, token]

                if tok1.type == Token.T_FUNCTIONDEF:
                    tok1.children.append(self.consume(tokens, token, index+self._offset-1, 1))

                token.type = Token.T_ARGLIST
                tokens[index-1] = tok1
                return self._offset

        if token.type == Token.T_GROUPING and token.value == '[]':
            i1 = self.peek_token(tokens, token, index, -1)
            if i1 is not None and tokens[i1].type != Token.T_SPECIAL:
                lhs = self.consume(tokens, token, index, -1)
                tok1 = Token(Token.T_SUBSCR, token.line, token.index, "")
                tok1.children = [lhs] + token.children
                tokens[index-1] = tok1
                return self._offset
            else:
                token.type = Token.T_LIST

        return 1

    def visit_new(self, parent, tokens, index, operators):

        token = tokens[index]

        if token.type == Token.T_KEYWORD and token.value == 'new':
            i1 = self.peek_token(tokens, token, index, 1)
            if i1 is None:
                return 1
            i2 = self.peek_token(tokens, token, i1, 1)

            consume2 = i2 is not None and tokens[i2].type == Token.T_GROUPING

            token.children.append(self.consume(tokens, token, index, 1))
            if consume2:
                token.children.append(self.consume(tokens, token, index, 1))

            token.type = Token.T_NEW

        return 1

    def visit_unary_postfix(self, parent, tokens, index, operators):

        token = tokens[index]

        if token.type not in (Token.T_SPECIAL, Token.T_KEYWORD) or \
           token.value not in operators:
            return 1

        i1 = self.peek_token(tokens, token, index, -1)
        i2 = self.peek_token(tokens, token, index, 1)

        rv = 1
        no_rhs = i2 is None or tokens[i2].type == Token.T_SPECIAL
        if no_rhs and i1 is not None:
            token.children.append(self.consume(tokens, token, index, -1))
            token.type = Token.T_POSTFIX
            rv += self._offset

        return rv

    def visit_unary_prefix(self, parent, tokens, index, operators):

        token = tokens[index]

        if token.type not in (Token.T_SPECIAL, Token.T_KEYWORD) or \
           token.value not in operators:
            return 1

        i1 = self.peek_token(tokens, token, index, -1)
        i2 = self.peek_token(tokens, token, index, 1)

        no_lhs = i1 is None or tokens[i1].type == Token.T_SPECIAL
        if no_lhs and i2 is not None:
            token.children.append(self.consume(tokens, token, index, 1))
            token.type = Token.T_PREFIX

        return 1

    def visit_prefix(self, parent, tokens, index, operators):

        token = tokens[index]

        if token.type not in (Token.T_SPECIAL, Token.T_KEYWORD) or \
           token.value not in operators:
            return 1

        token.children.append(self.consume(tokens, token, index, 1))
        token.type = Token.T_PREFIX

        return 1

    def visit_unary(self, parent, tokens, index, operators):
        token = tokens[index]

        if token.type not in (Token.T_SPECIAL, Token.T_KEYWORD) or \
           token.value not in operators:
            return 1

        rhs = self.consume(tokens, token, index, 1)
        token.children.append(rhs)
        token.type = Token.T_PREFIX

        return 1

    def visit_binary(self, parent, tokens, index, operators):
        token = tokens[index]

        if token.type not in (Token.T_SPECIAL, Token.T_KEYWORD) or \
           token.value not in operators:
            return 1

        rhs = self.consume(tokens, token, index, 1)
        lhs = self.consume(tokens, token, index, -1)
        token.children.append(lhs)
        token.children.append(rhs)
        token.type = Token.T_BINARY

        return self._offset

    def visit_lambda(self, parent, tokens, index, operators):
        token = tokens[index]

        if token.type not in (Token.T_SPECIAL, Token.T_KEYWORD) or \
           token.value not in operators:
            return 1

        rhs = self.consume_keyword(tokens, token, index, 1)
        lhs = self.consume(tokens, token, index, -1)
        token.children.append(lhs)
        token.children.append(rhs)
        token.type = Token.T_BINARY

        if lhs.type == Token.T_GROUPING:
            lhs.type = Token.T_ARGLIST

        return self._offset

    def visit_comma(self, parent, tokens, index, operators):
        """
        the comma operator is a binary operator where the lhs and rhs are optional

        this allows for a production rule where the trailing comma can
        be omitted
        """
        token = tokens[index]

        if token.type not in (Token.T_SPECIAL, Token.T_KEYWORD) or \
           token.value not in operators:
            return 1

        rhs = None
        while index+1 < len(tokens):
            tmp = tokens.pop(index+1)
            if tmp.type != Token.T_NEWLINE:
                rhs = tmp
                break

        rv = 1

        lhs = None
        while index-1 >= 0:
            tmp = tokens.pop(index-1)
            index -= 1
            rv -= 1
            if tmp.type != Token.T_NEWLINE:
                lhs = tmp
                break

        if lhs:
            token.children.append(lhs)

        if rhs:
            token.children.append(rhs)
        token.type = Token.T_COMMA

        return rv

    def visit_ternary(self, parent, tokens, index, operators):
        """

        """
        token = tokens[index]

        if token.type not in (Token.T_SPECIAL, Token.T_KEYWORD) or \
           token.value not in operators:
            return 1

        rhs1 = self.consume(tokens, token, index, 1)
        rhs2 = self.consume(tokens, token, index, 1)
        rhs3 = self.consume(tokens, token, index, 1)
        lhs0 = self.consume(tokens, token, index, -1)

        if rhs2.type != Token.T_SPECIAL or rhs2.value != ':':
            raise ParseError(rhs2, "invalid ternary expression")

        token.type = Token.T_TERNARY
        token.children = [lhs0, rhs1, rhs3]

        return self._offset

    def visit_keyword_case(self, parent, tokens, index, operators):
        """
        the case keyword needs to be visited early on. the operator colon
        has two different meanings depending on if it is part of a switch
        case statement or inside a map constructor.
        """

        token = tokens[index]
        if token.type != Token.T_KEYWORD:
            return 1

        if token.value == 'case':
            self.collect_keyword_switch_case(tokens, index)

        if token.value == 'default':
            self.collect_keyword_switch_default(tokens, index)

        return 1

    def visit_keyword(self, parent, tokens, index, operators):

        token = tokens[index]
        if token.type != Token.T_KEYWORD:
            return 1

        # --

        if token.value == 'break':
            self.collect_keyword_break(tokens, index)

        elif token.value == 'catch':
            raise ParseError(token, "catch without matching try")

        elif token.value == 'class':
            self.collect_keyword_class(tokens, index)

        elif token.value == 'const':
            self.collect_keyword_var(tokens, index)

        elif token.value == 'continue':
            self.collect_keyword_continue(tokens, index)

        elif token.value == 'do':
            self.collect_keyword_dowhile(tokens, index)

        elif token.value == 'else':
            raise ParseError(token, "else without matching if")

        elif token.value == 'finally':
            raise ParseError(token, "finally without matching try")

        elif token.value == 'for':
            self.collect_keyword_for(tokens, index)

        elif token.value == 'function':
            self.collect_keyword_function(tokens, index)

        elif token.value == 'if':
            self.collect_keyword_if(tokens, index)

        elif token.value == 'let':
            self.collect_keyword_var(tokens, index)

        elif token.value == 'return':
            self.collect_keyword_return(tokens, index)

        elif token.value == 'super':
            self.collect_keyword_super(tokens, index)

        elif token.value == 'switch':
            self.collect_keyword_switch(tokens, index)

        elif token.value == 'throw':
            self.collect_keyword_throw(tokens, index)

        elif token.value == 'try':
            self.collect_keyword_trycatch(tokens, index)

        elif token.value == 'var':
            self.warn(token, Parser.W_VAR_USED)
            self.collect_keyword_var(tokens, index)

        elif token.value == 'while':
            self.collect_keyword_while(tokens, index)

        elif token.value in ('this', 'import', 'export', "with", "true", "false", "null"):
            pass
        else:
            self.warn(token, Parser.W_UNSUPPORTED)

        return 1

    def visit_keyword_import_export(self, parent, tokens, index, operators):

        token = tokens[index]
        if token.type != Token.T_KEYWORD:
            return 1

        # --

        if token.value == 'export':
            # this can't be collected until after class, function
            self.collect_keyword_export(tokens, index)

        if token.value == 'import':
            self.collect_keyword_import(tokens, index)

        return 1

    def visit_cleanup(self, parent, tokens, index, operators):

        token = tokens[index]
        if token.type == Token.T_NEWLINE:
            tokens.pop(index)
            return 0
        if token.type == Token.T_SPECIAL and token.value == ';':
            tokens.pop(index)
            return 0
        return 1

    def collect_grouping(self, tokens, index, open, close):

        current = tokens[index]

        current.type = Token.T_GROUPING
        current.value = open + close
        index += 1

        counter = 1
        while index < len(tokens):
            token = tokens[index]
            if token.type == Token.T_SPECIAL and token.value == open:
                current.children.append(tokens.pop(index))
                counter += 1
            elif token.type == Token.T_SPECIAL and token.value == close:

                counter -= 1
                if counter == 0:
                    tokens.pop(index)
                    break;
                else:
                    current.children.append(tokens.pop(index))
            else:
                current.children.append(tokens.pop(index))

    def collect_keyword_break(self, tokens, index):
        token = tokens[index]
        token.type = Token.T_BREAK

    def collect_keyword_continue(self, tokens, index):
        token = tokens[index]
        token.type = Token.T_CONTINUE

    def collect_keyword_class(self, tokens, index):
        """
        the three valid forms of a class are:
            class block
            class name block
            class name extends name block

        the resulting class token always has three children
            1. name
            2. extends { name }
            3. block

        functions in the block will be transformed into function definitions
        """
        token = tokens[index]
        token.type = Token.T_CLASS

        i1 = self.peek_token(tokens, token, index, 1)
        if i1 is not None and tokens[i1].type == Token.T_TEXT:
            token.children = [self.consume(tokens, token, index, 1)]
        else:
            token.children = [Token(Token.T_TEXT, token.line, token.index, "")]

        i2 = self.peek_keyword(tokens, token, index, 1)
        if (i2 is not None and tokens[i2].type == Token.T_KEYWORD and tokens[i2].value == 'extends'):
            rhs2 = self.consume_keyword(tokens, token, index, 1)
            rhs3 = self.consume(tokens, token, index, 1)
            rhs2.children = [rhs3]
            token.children.append(rhs2)
        else:
            token.children.append(Token(Token.T_KEYWORD, token.line, token.index, "extends"))

        rhs1 = self.consume(tokens, token, index, 1)
        token.children.append(rhs1)

        for i, child in enumerate(rhs1.children):
            if child.type == Token.T_FUNCTIONCALL:
                child.type = Token.T_FUNCTIONDEF
                child.children.append(self.consume(rhs1.children, child, i, 1))

    def collect_keyword_switch_case(self, tokens, index):
        token = tokens[index]

        rhs1 = self.consume(tokens, token, index, 1)
        rhs2 = self.consume(tokens, token, index, 1)

        if rhs2.type != Token.T_SPECIAL or rhs2.value != ":":
            raise ParseError(token, "expected label")

        token.children = [rhs1]
        token.type = Token.T_CASE

    def collect_keyword_switch_default(self, tokens, index):
        token = tokens[index]

        rhs1 = self.consume(tokens, token, index, 1)

        if rhs1.type != Token.T_SPECIAL or rhs1.value != ":":
            raise ParseError(token, "expected label")

        token.type = Token.T_DEFAULT

    def collect_keyword_dowhile(self, tokens, index):
        """
        output token has two children
            1: block
            2: test
        """
        token = tokens[index]

        rhs1 = self.consume(tokens, token, index, 1)
        rhs2 = self.consume_keyword(tokens, token, index, 1)
        rhs3 = self.consume(tokens, token, index, 1)

        if rhs2.type != Token.T_KEYWORD or rhs2.value != "while":
            raise ParseError(rhs2, "expected while")

        if rhs1.type != Token.T_GROUPING:
            self.warn(rhs1, Parser.W_BLOCK_UNSAFE)
        else:
            rhs1.type = Token.T_BLOCK

        if rhs3.type != Token.T_GROUPING:
            raise ParseError(rh3, "expected parenthetical grouping")
        else:
            rhs3.type = Token.T_ARGLIST
        # drop the while keyword
        token.children = [rhs1, rhs3]
        token.type = Token.T_DOWHILE

    def collect_keyword_export(self, tokens, index):
        """

        Export named values
        export a
        export a = 1
        export const a = 1
        export let a = 1
        export var a = 1
        export function a () {}
        export class a {}

        Anonymous exports will cause a ParseError
        export function () {}
        export class {}

        """
        token = tokens[index]

        # consume the word default, but don't do anything with it
        i1 = self.peek_keyword(tokens, token, index, 1)
        if i1 is not None and tokens[i1].type == Token.T_KEYWORD and tokens[i1].value == 'default':
            self.consume(tokens, token, index, 1)
            self.warn(token, Parser.W_EXPORT_DEFAULT)

        child = self.consume(tokens, token, index, 1)

        node = child
        while node:
            if node.type == Token.T_TEXT:
                if not node.value:
                    raise ParseError(token, "unable to export anonymous entity")
                token.value = node.value
                break
            elif node.type == Token.T_BINARY and node.value == "=":
                node = node.children[0]
            elif node.type == Token.T_VAR:
                node = node.children[0]
            elif node.type == Token.T_CLASS:
                node = node.children[0]
            elif node.type == Token.T_FUNCTION:
                node = node.children[0]
            else:
                raise ParseError(node, "unable to export token")

        token.type = Token.T_EXPORT
        token.children = [child]

    def collect_keyword_import(self, tokens, index):
        token = tokens[index]

        module = self.consume(tokens, token, index, 1)

        if module.type == Token.T_BINARY:
            text = ""
            node = module
            while node.type == Token.T_BINARY:
                if node.children[1].type == Token.T_ATTR:
                    text = node.children[1].value + text
                else:
                    raise ParseError(node.children[1], "invalid")

                text = '.' + text

                if node.children[0].type == Token.T_BINARY:
                    node = node.children[0]
                elif node.children[0].type == Token.T_TEXT:
                    text = node.children[0].value + text
                    break
                else:
                    raise ParseError(node.children[0], "invalid")

            token.value = text
        elif module.type == Token.T_STRING:
            token.value = ast.literal_eval(module.value)
        elif module.type == Token.T_TEXT:
            token.value = module.value
        else:
            raise ParseError(module, "invalid module name")

        token.type = Token.T_IMPORT

        i1 = self.peek_keyword(tokens, token, index, 1)
        if i1 is not None and tokens[i1].type == Token.T_KEYWORD and tokens[i1].value == 'with':
            self.consume_keyword(tokens, token, index, 1)
            fromlist = self.consume(tokens, token, index, 1)
            if fromlist.type != Token.T_GROUPING:
                raise ParseError(fromlist, "expected {} for fromlist")
            else:
                fromlist.type = Token.T_OBJECT
            token.children.append(fromlist)
        else:
            token.children.append(Token(Token.T_OBJECT, token.line, token.index, "{}"))

    def collect_keyword_for(self, tokens, index):
        token = tokens[index]

        rhs1 = self.consume(tokens, token, index, 1)
        rhs2 = self.consume(tokens, token, index, 1)

        if rhs1.type != Token.T_GROUPING:
            raise ParseError(token, "expected grouping")
        else:
            rhs1.type = Token.T_ARGLIST

        if rhs2.type != Token.T_GROUPING:
            self.warn(rhs2, Parser.W_BLOCK_UNSAFE)
        else:
            rhs2.type = Token.T_BLOCK

        token.children = [rhs1, rhs2]
        token.type = Token.T_FOR

    def collect_keyword_function(self, tokens, index):
        token = tokens[index]

        rhs1 = self.consume(tokens, token, index, 1)

        # function () {}
        # function name() {}

        if rhs1.type == Token.T_FUNCTIONCALL:
            token.children = rhs1.children
        elif rhs1.type == Token.T_GROUPING:
            # anonymous function
            token.children = [Token(Token.T_TEXT, token.line, token.index, ""), rhs1]
        else:
            # name, arglist
            token.children = [rhs1, self.consume(tokens, token, index, 1)]

        # function body
        body = self.consume(tokens, token, index, 1)
        token.children.append(body)

        if token.children[1].type not in (Token.T_GROUPING, Token.T_ARGLIST):
            raise ParseError(token, "expected arglist")

        token.children[1].type = Token.T_ARGLIST

        if body.type != Token.T_GROUPING:
            self.warn(body, Parser.W_BLOCK_UNSAFE)
        else:
            body.type = Token.T_BLOCK

        token.type = Token.T_FUNCTION

    def collect_keyword_if(self, tokens, index):
        """
        collect branching statements

        a branch token has 2 or 3 tokens,
            1: the test
            2: the true case
            3: the optional false case
        """

        token = tokens[index]

        rhs1 = self.consume(tokens, token, index, 1)
        rhs2 = self.consume(tokens, token, index, 1)
        i3 = self.peek_keyword(tokens, token, index, 1)

        if rhs2.type != Token.T_GROUPING:
            self.warn(rhs2, Parser.W_BRANCH_TRUE)
        else:
            rhs2.type = Token.T_BLOCK

        if (rhs1.type != Token.T_GROUPING):
            raise ParseError(token, "expected grouping")

        rhs1.type = Token.T_ARGLIST
        token.children = [rhs1, rhs2]
        token.type = Token.T_BRANCH

        # check for else
        if i3 is not None:
            tok3 = tokens[i3]
            if tok3.type != Token.T_KEYWORD or tok3.value != 'else':
                return

            # drop the else
            tokens.pop(i3)

            # check for else if
            i4 = self.peek_keyword(tokens, token, index, 1)
            if i4 is not None and \
               tokens[i4].type == Token.T_KEYWORD and tokens[i4].value == 'if':
                self.collect_keyword_if(tokens, i4)

            elif i4 is not None and tokens[i4].type != Token.T_GROUPING:
                self.warn(tokens[i4], Parser.W_BRANCH_FALSE)

            # consume the subsequent token as the else branch of this token
            tok4 = self.consume_keyword(tokens, token, index, 1)
            token.children.append(tok4)

            if tok4.type != Token.T_GROUPING:
                if token.children[-1].type != Token.T_BRANCH:
                    self.warn(token.children[-1], Parser.W_BRANCH_FALSE)
            else:
                token.children[-1].type = Token.T_BLOCK

    def collect_keyword_return(self, tokens, index):
        """
        optionally consume one value
        """
        token = tokens[index]
        i1 = self.peek_token(tokens, token, index, 1)
        if i1 is not None:
            token.children = [self.consume(tokens, token, index, 1)]
        token.type = Token.T_RETURN

    def collect_keyword_super(self, tokens, index):

        token = tokens[index]
        rhs1 = self.consume(tokens, token, index, 1)

        if rhs1.type != Token.T_GROUPING:
            raise ParseError(rs1, "expected function call")
        else:
            rhs1.type = Token.T_ARGLIST

        token.children = [Token(Token.T_KEYWORD, token.line, token.index, "super"), rhs1]
        token.type = Token.T_FUNCTIONCALL
        token.value = ""

    def collect_keyword_switch(self, tokens, index):

        token = tokens[index]
        rhs1 = self.consume(tokens, token, index, 1)
        rhs2 = self.consume(tokens, token, index, 1)

        if rhs2.type != Token.T_GROUPING:
            raise ParseError(rhs2, "expected block")
        else:
            rhs2.type = Token.T_BLOCK

        token.children = [rhs1, rhs2]
        token.type = Token.T_SWITCH

    def collect_keyword_throw(self, tokens, index):

        token = tokens[index]

        rhs = self.consume_keyword(tokens, token, index, 1)
        token.children = [rhs]
        token.type = Token.T_THROW

    def collect_keyword_trycatch(self, tokens, index):
        """
        try {...} catch (e) {...} finally {...}

        Note:
            nonstandard feature: catch (e if e instanceof TypeError)
            try {...} catch (e) {if (e instanceof TypeError) {...}}
            it would be possible to manipulate the ast to support

        """

        token = tokens[index]

        rhs = self.consume(tokens, token, index, 1)
        if rhs.type != Token.T_GROUPING:
            self.warn(rhs, Parser.W_BLOCK_UNSAFE)
        else:
            rhs.type = Token.T_BLOCK
        token.children = [rhs]
        token.type = Token.T_TRY

        i2 = self.peek_keyword(tokens, token, index, 1)
        while (i2 is not None and tokens[i2].type == Token.T_KEYWORD and tokens[i2].value == 'catch'):
            rhs1 = self.consume_keyword(tokens, token, index, 1)
            rhs2 = self.consume(tokens, token, index, 1)
            rhs3 = self.consume(tokens, token, index, 1)
            if rhs3.type != Token.T_GROUPING:
                self.warn(rhs3, Parser.W_BLOCK_UNSAFE)
            else:
                rhs3.type = Token.T_BLOCK
            rhs1.children.append(rhs2)
            rhs1.children.append(rhs3)
            token.children.append(rhs1)
            rhs1.type = Token.T_CATCH
            i2 = self.peek_keyword(tokens, token, index, 1)

        if (i2 is not None and tokens[i2].type == Token.T_KEYWORD and tokens[i2].value == 'finally'):
            rhs1 = self.consume_keyword(tokens, token, index, 1)
            rhs2 = self.consume(tokens, token, index, 1)
            if rhs2.type != Token.T_GROUPING:
                self.warn(rhs2, Parser.W_BLOCK_UNSAFE)
            else:
                rhs3.type = Token.T_BLOCK
            rhs1.children.append(rhs2)
            rhs1.type = Token.T_FINALLY
            token.children.append(rhs1)

    def collect_keyword_var(self, tokens, index):

        token = tokens[index]
        if index + 1 < len(tokens):
            rhs = tokens.pop(index + 1)
        else:
            raise ParseError(token, "expected rhs")
        token.children = [rhs]
        token.type = Token.T_VAR

    def collect_keyword_while(self, tokens, index):

        token = tokens[index]
        rhs1 = self.consume(tokens, token, index, 1)
        rhs2 = self.consume(tokens, token, index, 1)

        if (rhs1.type != Token.T_GROUPING):
            raise ParseError(token, "expected grouping")
        else:
            rhs1.type = Token.T_ARGLIST

        if rhs2.type != Token.T_GROUPING:
            self.warn(rhs2, Parser.W_BLOCK_UNSAFE)
        else:
            rhs2.type = Token.T_BLOCK

        token.children = [rhs1, rhs2]
        token.type = Token.T_WHILE

    def transform_grouping(self, token, parent):
        """
        transform any remaining instances of GROUPING{}
        many will be transformed as part of collecting various keywords

        """
        for child in token.children:

            if child.type == Token.T_GROUPING and child.value == "{}":

                if (token.type == Token.T_MODULE) or \
                   (token.type == Token.T_FUNCTIONDEF) or \
                   (token.type == Token.T_CLASS) or \
                   (token.type == Token.T_BLOCK) or \
                   (token.type == Token.T_BINARY and token.value == "=>") or \
                   (token.type == Token.T_GROUPING and token.value == "{}"):
                    # next test this is not an object
                    # objects:
                    #   {} {a} {a:b} {...a} {a,b} {a:b,c:d}
                    # not objects:
                    #   {1} {a.b} {f()}
                    ref = self._isObject(child)
                    if ref is None:
                        child.type = Token.T_OBJECT
                    else:
                        child.type = Token.T_BLOCK
                else:

                    ref = self._isObject(child)
                    if ref is not None:
                        raise ref
                    child.type = Token.T_OBJECT

            self.transform_grouping(child, token)

    def _isObject(self, token):
        # test if a token is an object, this is only valid
        # if the object contents have not been flattened

        if token.type != Token.T_GROUPING or token.value != "{}":
            return ParseError(token, "expected object")

        if len(token.children) > 1:
            # likely there is a missing comma
            # left-recursive drill down into the first non comma or colon
            # that is usually the first token after a missing comma
            child = token.children[1]
            while child.type == Token.T_COMMA or (child.type == Token.T_BINARY and child.value == ':'):
                child = child.children[0]
            return ParseError(child, "malformed object. maybe a comma is missing?")

        if len(token.children) == 0:
            return None

        child = token.children[0]
        t = child.type
        v = child.value

        if (t == Token.T_TEXT) or \
           (t == Token.T_PREFIX and v == '...') or \
           (t == Token.T_BINARY and (v == ':')) or \
           (t == Token.T_COMMA):
            return None

        return ParseError(token, "expected object")

    def transform_flatten(self, token, parent):
        """
        Objects, Argument Lists, Parenthetical Grouping, and Lists
        all uses commas to separate clauses. The comma can be removed
        and the contents flattened into a single list of children
        """

        for child in token.children:
            self.transform_flatten(child, token)

        if token.type == Token.T_GROUPING and token.value != "()":
            # either a {} block was incorrectly parsed
            # or a [] block was not labeled list of subscr
            raise ParseError(token, "parser error: invalid grouping node: " + token.value)

        if token.type == Token.T_OBJECT or \
           token.type == Token.T_ARGLIST or \
           token.type == Token.T_LIST or \
           token.type == Token.T_GROUPING:

            chlst = token.children
            index = 0;
            while index < len(chlst):
                if chlst[index].type == Token.T_COMMA:
                    child = chlst.pop(index)
                    for j in range(len(child.children)):
                        chlst.insert(index+j, child.children[j])
                else:
                    index += 1

def main():

    # TODO: let x,y,z
    # TODO: if (true) {x=1;} + 1
    #       this gives an odd error message
    #       expected object but the error is because of the parent node
    # TODO: if x {} throws a weird error

    text1 = """
    if x.y() {
        throw "this"
    }

    """

    tokens = Lexer({'preserve_documentation':True}).lex(text1)
    mod = Parser().parse(tokens)

    print(mod.toString(2))



if __name__ == '__main__':
    main()