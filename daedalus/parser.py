#! cd .. && python3 -m daedalus.parser
"""
https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Operators/Operator_Precedence


https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Statements/block
blocks can be labeled

https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Statements/import
imports are complicated


TODO: warning when two lines are arranged such that:
    a = b
    [c] = d

The parser interprets it as:
    a = b[c] = d

"""
import sys
import ast
from .lexer import Lexer, Token, TokenError
from .transform import TransformGrouping, \
    TransformFlatten, TransformOptionalChaining, TransformNullCoalescing, \
    TransformMagicConstants, TransformRemoveSemicolons, TransformBase

class ParseError(TokenError):
    pass

def diag(tokens):
    print([t.value for t in tokens])

def prefix_count(text, char):
    count = 0
    for c in text:
        if c == char:
            count += 1
        else:
            break;
    return count

class TransformTemplateString(TransformBase):

    def visit(self, token, parent):

        if token.type == Token.T_TEMPLATE_STRING:
            segments = self.parse_string(token)

            tokens = []
            for isExpr, text in segments:
                if not text:
                    continue
                type_ = Token.T_TEMPLATE_EXPRESSION if isExpr else Token.T_STRING
                tok = Token(type_, 1, 0, text)
                if isExpr:
                    ast = Parser().parse(Lexer().lex(text))
                    tok.children = ast.children

                tokens.append(tok)
            token.children = tokens

    def parse_string(self, token):
        """
        parse a template string and get the text and expression segments
        """
        segments = []
        text = token.value[1:-1]
        index=0;
        state = 0
        start = 0
        stack = 0
        while index < len(text):
            c = text[index]

            if state == 2:
                if c == '{':
                    stack += 1

                elif c == '}':
                    if stack == 0:
                        state = 0
                        segments.append((1, text[start:index]))
                        start = index + 1
                    else:
                        stack -= 1

            else:
                if c == '\\':
                    index += 1
                elif state == 0:

                    if c == '$':
                        state = 1

                elif state == 1:

                    if c == '{':
                        state = 2
                        segments.append((0, text[start:index-1]))
                        start = index + 1

            index += 1

        segments.append((0, text[start:index]))

        return segments

class Parser(object):

    W_BRANCH_FALSE = 1
    W_BRANCH_TRUE  = 2
    W_BLOCK_UNSAFE  = 3
    W_UNSUPPORTED = 4
    W_EXPORT_DEFAULT = 5
    W_VAR_USED = 6
    W_UNSAFE_BOOLEAN_TEST = 7  # Note: could be expanded to testing between operator &&, ||

    def __init__(self):
        super(Parser, self).__init__()

        # when true, output an AST which is more friendly for compiling
        self.python = False

        L2R = 1
        R2L = -1

        self.precedence = [
            (R2L, self.visit_unary_prefix, ['#']),
            (L2R, self.visit_attr, ['.', "?."]),  # also: x[], x()
            (L2R, self.visit_new, []),
            (L2R, self.visit_unary_postfix, ['++', '--']),
            (R2L, self.visit_unary_prefix, ['!', '~', '+', '-', '++', '--']),
            (R2L, self.visit_prefix, ['typeof', 'void', 'delete', 'await']),
            (R2L, self.visit_binary, ['**']),
            (L2R, self.visit_binary, ['*', '/', '%']),
            (L2R, self.visit_binary, ['+', '-']),
            (L2R, self.visit_binary, ['<<', '>>', ">>>"]),
            (L2R, self.visit_binary, ['<', '<=', ">", ">=", "in", "of", "instanceof"]),
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
            (R2L, self.visit_assign_v2, ['=>', '=', '+=', '-=', '**=', '*=', '/=',
                                      '&=', '<<=', '>>=', '&=', '^=',
                                      '|=']),
            (R2L, self.visit_unary, ['yield', 'yield*']),
            (L2R, self.visit_keyword_case, []),
            (L2R, self.visit_binary, [':']),
            (L2R, self.visit_comma, [',']),
            (L2R, self.visit_keyword_arg, []),
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
            Parser.W_UNSAFE_BOOLEAN_TEST: "unsafe boolean test. use (!!{token}) or (({token} !== undefined) && ({token} !== null))",
        }

        self.disabled_warnings = set()
        self.disable_all_warnings = False

        self._offset = 0  # used by consume in the negative direction

    def warn(self, token, type, message=None):

        if self.disable_all_warnings:
            return

        if type in self.disabled_warnings:
            return

        text = self.warnings[type].format(token=token.value)
        if message:
            text += ":" + message

        text = "WARNING: line: %d column: %d type: %s value: %s : %s\n" % (
            token.line, token.index, token.type, token.value, text)

        sys.stdout.write(text)

    def parse(self, tokens):

        self.group(tokens)

        mod = Token(Token.T_MODULE, 0, 0, "")
        mod.children = tokens

        TransformRemoveSemicolons().transform(mod)
        TransformGrouping().transform(mod)
        TransformFlatten().transform(mod)
        TransformOptionalChaining().transform(mod)
        TransformNullCoalescing().transform(mod)
        TransformMagicConstants().transform(mod)

        # the template transform is last because it recursively uses the parser
        TransformTemplateString().transform(mod)

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
            elif tok1.type == Token.T_KEYWORD and tok1.value not in ("true", "false", "null", "this", "new", "function", "function*", "class"):
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

        expression_whitelist = ("super", "true", "false", "null", "this", "new", "function", "function*", "class", "catch")
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

    def group(self, initial_tokens):
        """

        This is a DFS algorithm that scans the document from top
        to bottom and from the outer most nesting in.
        """

        pairs = {
            '(': ')',
            '[': ']',
            '{': '}',
        }

        seq = [[None, initial_tokens, 0]]

        while len(seq):

            parent, tokens, i = seq[-1]
            while i < len(tokens):

                token = tokens[i]

                if token.type == Token.T_SPECIAL and token.value in pairs:

                    self.collect_grouping(tokens, i, token.value, pairs[token.value])

                    if token is not None:
                        # save the current state and continue processing the child
                        seq[-1][2] = i
                        seq.append([token, token.children, 0])
                        break
                i += 1

            # remove the token when scanning has finished
            if i >= len(tokens):
                self.scan(parent, tokens)
                seq.pop()

    def scan(self, parent, tokens):
        """
        scan each token in a sequence. tokens which produce nested
        groups have already been processed. scanning can be done in
        either direction: left-to-right or right-to-left.

        the precedence decides how tokens combine together
        """

        for direction, callback, operators in self.precedence:
            i = 0
            while i < len(tokens):

                if direction < 0:
                    j = len(tokens) - i - 1
                else:
                    j = i

                i += callback(parent, tokens, j, operators)

    def visit_attr(self, parent, tokens, index, operators):
        """
        Handle the various forms of attribute access

        consume:
            x.y
            x[y]
            x()
            x?.y
            x?.[y]
            x?.()
            function()  - anonymous function
            []          - square brakets with no prefix declare a new list
            tag`template`

        produce:

            T_BINARY
                <any>
                T_ATTR

            T_OPTIONAL_CHAINING
                <any>
                T_ATTR

            T_OPTIONAL_CHAINING
                <any>
                T_ARGLIST

            T_OPTIONAL_CHAINING
                <any>
                T_SUBSCR

            T_FUNCTIONCALL
                <any>
                T_ARGLIST

            T_ANONYMOUS_FUNCTION
                T_TEXT
                T_ARGLIST
                <any>

            T_LIST
        """

        token = tokens[index]
        # check for attribute operator or 'optional chaining' / elvis operator
        if token.type == Token.T_SPECIAL and token.value == '.':

            rhs = self.consume(tokens, token, index, 1)
            lhs = self.consume(tokens, token, index, -1)

            if rhs.type == Token.T_TEXT:
                rhs.type = Token.T_ATTR

            token.type = Token.T_GET_ATTR
            token.children = [lhs, rhs]
            return self._offset

        elif token.type == Token.T_SPECIAL and token.value == '?.':
            i1 = self.peek_token(tokens, token, index, 1)

            if i1 and tokens[i1].type == Token.T_GROUPING:

                rhs = self.consume(tokens, token, index, 1)
                lhs = self.consume(tokens, token, index, -1)

                if rhs.value == '()':
                    tok = Token(Token.T_FUNCTIONCALL, token.line, token.index, '()')
                    tok.children = [lhs, rhs]
                    token.children = [tok]
                    rhs.type = Token.T_ARGLIST
                    token.type = Token.T_OPTIONAL_CHAINING

                if rhs.value == '[]':
                    rhs.type = Token.T_SUBSCR
                    rhs.children.insert(0, lhs)
                    token.children = [rhs]
                token.type = Token.T_OPTIONAL_CHAINING

            else:

                rhs = self.consume(tokens, token, index, 1)
                lhs = self.consume(tokens, token, index, -1)

                if rhs.type == Token.T_TEXT:
                    rhs.type = Token.T_ATTR

                token.type = Token.T_OPTIONAL_CHAINING
                token.children = [lhs, rhs]

            return self._offset

        elif token.type == token.T_KEYWORD and token.value in ("function", "function*"):
            self.collect_keyword_function(tokens, index)

        # class cannot be collected here yet because the `extends X` clause
        # can be an arbitrary expression.

        #elif token.type == token.T_KEYWORD and token.value == "class":
        #    self.collect_keyword_class(tokens, index)

        elif token.type == Token.T_GROUPING and token.value == '()':
            i1 = self.peek_token(tokens, token, index, -1)
            if i1 is not None and tokens[i1].type != Token.T_SPECIAL:
                lhs = self.consume(tokens, token, index, -1)
                n = 0

                tok1 = Token(Token.T_FUNCTIONCALL, token.line, token.index, "")

                tok1.children = [lhs, token]

                token.type = Token.T_ARGLIST
                tokens[index - 1] = tok1
                return self._offset

        elif token.type == Token.T_GROUPING and token.value == '[]':
            # special case if the square bracket starts a new line
            # then assume this is the start of a list
            # alternative would be to check if the rhs is a assignment operator
            if index > 1 and tokens[index-1].type == Token.T_NEWLINE:
                token.type = Token.T_LIST

            else:
                i1 = self.peek_token(tokens, token, index, -1)
                if i1 is not None and tokens[i1].type != Token.T_SPECIAL:
                    lhs = self.consume(tokens, token, index, -1)
                    tok1 = Token(Token.T_SUBSCR, token.line, token.index, "")
                    tok1.children = [lhs] + token.children
                    tokens[index - 1] = tok1
                    return self._offset
                else:
                    token.type = Token.T_LIST

        elif token.type == Token.T_TEMPLATE_STRING:

            i1 = self.peek_token(tokens, token, index, -1)
            if i1 is not None and tokens[i1].type == Token.T_TEXT:

                lhs = self.consume(tokens, token, index, -1)
                tok = Token(Token.T_TAGGED_TEMPLATE, token.line, token.index, '')

                tok.children = lhs, token
                tokens[index-1] = tok

                return self._offset

        return 1

    def visit_new(self, parent, tokens, index, operators):
        """

        consume:

            new constructor
            new constructor()

        produce:

            T_NEW
                <any>

        Note:

            when this function is run the function call for the constructor
            has already been processed. This collects a single expression after
            the keyword
        """

        token = tokens[index]

        if token.type != Token.T_KEYWORD or token.value != 'new':
            return 1

        #i1 = self.peek_token(tokens, token, index, 1)
        # if i1 is None:
        #    raise ParseError(token, "expected expression")
        #i2 = self.peek_token(tokens, token, i1, 1)
        #consume2 = i2 is not None and tokens[i2].type == Token.T_GROUPING

        token.children.append(self.consume(tokens, token, index, 1))
        # if consume2:
        #    token.children.append(self.consume(tokens, token, index, 1))

        token.type = Token.T_NEW

        return 1

    def visit_unary_postfix(self, parent, tokens, index, operators):
        """
        handle postfix increment and decrement

        consume:

            x++
            x--

        produce:

            T_POSTFIX
                <any>

        """

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
        """
        handle prefix operators which can be confused for binary operators

        consume:

            ++x
            --x
            !x
            ~x
            +x
            -x

        produce:

            T_PREFIX
                <any>

        """
        token = tokens[index]

        if token.type not in (Token.T_SPECIAL, Token.T_KEYWORD) or \
           token.value not in operators:
            return 1

        i1 = self.peek_token(tokens, token, index, -1)
        i2 = self.peek_token(tokens, token, index, 1)

        no_lhs = i1 is None or tokens[i1].type in Token.T_SPECIAL

        rv = 1
        if no_lhs and i2 is not None:
            token.children.append(self.consume(tokens, token, index, 1))
            token.type = Token.T_PREFIX
            rv = 0

        return rv

    def visit_prefix(self, parent, tokens, index, operators):
        """
        handle generic prefix operators

        consume:

            typeof expr
            void expr
            delete expr
            await expr

        produce:

            T_PREFIX
                <expr>
        """

        token = tokens[index]

        if token.type not in (Token.T_SPECIAL, Token.T_KEYWORD) or \
           token.value not in operators:
            return 1

        token.children.append(self.consume(tokens, token, index, 1))


        token.type = Token.T_PREFIX

        return 1

    def visit_unary(self, parent, tokens, index, operators):
        """
            handle prefix operators which cannot be confused for binary operators

        consume:

            ...expr         - spread
            yield expr      -
            yield* expr     -

        produce:

            T_PREFIX
                <expr>
        """
        token = tokens[index]

        if token.type not in (Token.T_SPECIAL, Token.T_KEYWORD) or \
           token.value not in operators:
            return 1

        rhs = self.consume(tokens, token, index, 1)
        token.children.append(rhs)

        if token.value == '...':
            token.type = Token.T_SPREAD

        elif token.value == 'yield':
            token.type = Token.T_YIELD

        elif token.value == 'yield*':
            token.type = Token.T_YIELD_FROM

        else:
            token.type = Token.T_PREFIX


        return 1

    def visit_binary(self, parent, tokens, index, operators):
        """
        handle binary operators

        produce:

            T_BINARY
                <expr_lhs>
                <expr_rhs>
        """
        token = tokens[index]

        if token.type not in (Token.T_SPECIAL, Token.T_KEYWORD) or \
           token.value not in operators:
            return 1

        # special case for the in keyword which appears after a
        # variable definition, which is only legal inside a for loop
        # 'of' is not treated as a keyword and avoids this fate
        if token.value == 'in':
            i1 = self.peek_token(tokens, token, index, -1)
            if i1 is not None:
                i2 = self.peek_keyword(tokens, token, i1, -1)
                if i2 is not None:
                    tok2 = tokens[i2]
                    if tok2.type == Token.T_KEYWORD and tok2.value in ('const', 'let', 'var'):
                        return 1

        rhs = self.consume(tokens, token, index, 1)
        lhs = self.consume(tokens, token, index, -1)
        token.children.append(lhs)
        token.children.append(rhs)

        if token.value == 'instanceof':
            token.type = Token.T_INSTANCE_OF
        elif token.value == '&&':
            token.type = Token.T_LOGICAL_AND
        elif token.value == '||':
            token.type = Token.T_LOGICAL_OR
        else:
            token.type = Token.T_BINARY

        return self._offset

    def visit_assign_v2(self, parent, tokens, index, operators):
        """
        Example:
            const f = (d,k,v) => d[k] = v

        collect binary operators Right-To-Left
        """
        if tokens[index].value == '=>':
            return self.visit_lambda(parent, tokens, index, operators)
        else:
            return self.visit_assign(parent, tokens, index, operators)

    def visit_assign(self, parent, tokens, index, operators):
        """
        handle binary operators for assignment

        consume:

            expr_lhs = expr_rhs
            [identifier0, ...] = expr_rhs

        produce:

            T_ASSIGN
                <expr_lhs>
                <expr_rhs>

            T_ASSIGN
                T_UNPACK_SEQUENCE
                    <identifier0>
                    ...
                <expr_rhs>
        """
        token = tokens[index]

        if token.type not in (Token.T_SPECIAL, Token.T_KEYWORD) or \
           token.value not in operators:
            return 1

        rhs = self.consume(tokens, token, index, 1)
        lhs = self.consume(tokens, token, index, -1)

        #if lhs.type == Token.T_GROUPING and token.value == "[]" or lhs.type == Token.:
        if lhs.type == Token.T_LIST:
            lhs.type = Token.T_UNPACK_SEQUENCE
        if lhs.type == Token.T_VAR:
            if lhs.children[0].type == Token.T_LIST:
                lhs.children[0].type = Token.T_UNPACK_SEQUENCE

        token.children.append(lhs)
        token.children.append(rhs)
        token.type = Token.T_ASSIGN

        return self._offset

    def visit_lambda(self, parent, tokens, index, operators):
        """
        handle the es6 arrow operator

        consume:
            () => {}
            a => b

        produce:

            T_LAMBDA
                T_TEXT
                T_ARGLIST
                <any>
        """
        token = tokens[index]

        if token.type not in (Token.T_SPECIAL, Token.T_KEYWORD) or \
           token.value not in operators:
            return 1

        rhs = self.consume_keyword(tokens, token, index, 1)
        lhs = self.consume(tokens, token, index, -1)
        token.children.append(Token(Token.T_TEXT, token.line, token.index, "Anonymous"))
        token.children.append(lhs)
        token.children.append(rhs)
        token.type = Token.T_LAMBDA

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
        while index + 1 < len(tokens):
            tmp = tokens.pop(index + 1)
            if tmp.type != Token.T_NEWLINE:
                rhs = tmp
                break

        rv = 1

        lhs = None
        while index - 1 >= 0:
            tmp = tokens.pop(index - 1)
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

    def visit_keyword_arg(self, parent, tokens, index, operators):
        """ collect keywords which accept a single argument """

        token = tokens[index]
        if token.type != Token.T_KEYWORD:
            return 1

        if token.value == 'const':
            self.collect_keyword_var(tokens, index)

        elif token.value == 'return':
            self.collect_keyword_return(tokens, index)

        elif token.value == 'var':
            self.warn(token, Parser.W_VAR_USED)
            self.collect_keyword_var(tokens, index)

        elif token.value == 'let':
            self.collect_keyword_var(tokens, index)

        elif token.value == 'throw':
            self.collect_keyword_throw(tokens, index)

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

        elif token.value == 'if':
            self.collect_keyword_if(tokens, index)

        elif token.value == 'super':
            self.collect_keyword_super(tokens, index)

        elif token.value == 'switch':
            self.collect_keyword_switch(tokens, index)

        elif token.value == 'try':
            self.collect_keyword_trycatch(tokens, index)

        elif token.value == 'while':
            self.collect_keyword_while(tokens, index)

        elif token.value in ('this', 'import', 'export', "with", "true", "false", "null", "default"):
            pass
        elif token.value == 'in':
            # TODO: this may be consumed in a higher layer...
            # is there  a better way for this lower layer to signal that
            pass
        else:
            self.warn(token, Parser.W_UNSUPPORTED)

        return 1

    def visit_keyword_import_export(self, parent, tokens, index, operators):

        token = tokens[index]

        if token.type != Token.T_KEYWORD and \
           not (token.type == Token.T_TEXT and token.value in ('from', 'include', 'pyimport')):
            return 1

        # --

        if token.value == 'export':
            # this can't be collected until after class, function
            self.collect_keyword_export(tokens, index)

        if token.value == 'import':
            self.collect_keyword_import(tokens, index)

        if token.value == 'pyimport':
            self.collect_keyword_pyimport(tokens, index)

        if token.value == 'include':
            self.collect_keyword_include(tokens, index)

        if token.value == 'from':
            self.collect_keyword_import_from(tokens, index)

        return 1

    def visit_cleanup(self, parent, tokens, index, operators):

        token = tokens[index]
        if token.type == Token.T_NEWLINE:
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
                    break
                else:
                    current.children.append(tokens.pop(index))
            else:
                current.children.append(tokens.pop(index))

        if counter != 0:
            raise ParseError(current, "matching %s not found" % close)

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

        if rhs1.type == Token.T_FUNCTIONCALL:
            raise ParseError(rhs1, "remove () from class def")

        if rhs1.type != Token.T_GROUPING:
            if self.python:
                tmp = Token(Token.T_BLOCK, rhs1.line, rhs1.index, '{}')
                tmp.children= [rhs1]
                rhs1 = tmp
            else:
                self.warn(rhs1, Parser.W_BLOCK_UNSAFE)
        else:
            rhs1.type = Token.T_BLOCK

        token.children.append(rhs1)

        index = 0
        while index < len(rhs1.children):
            child = rhs1.children[index]
            # a function call inside of an object is actually a method def
            offset = 1
            if child.type == Token.T_FUNCTIONCALL:
                child.type = Token.T_METHOD

                # store meta data about the method in the value position
                # the metadata will be get, set, public, private, static
                # not all of those keywords are valid javascript

                li = index - 1
                if li >= 0:
                    tok = rhs1.children[li]
                    if tok.type in (Token.T_KEYWORD, Token.T_TEXT) and \
                      tok.value in ('get', 'set', 'public', 'private', 'static'):
                        rhs1.children.pop(li)
                        offset -= 1
                        child.value = tok.value
                    else:
                        child.value = ''
                else:
                    child.value = ''

                ri = index + offset
                if ri < len(rhs1.children):
                    tok = rhs1.children.pop(ri)
                    if tok.type != Token.T_GROUPING:
                        if self.python:
                            tmp = Token(Token.T_BLOCK, tok.line, tok.index, '{}')
                            tmp.children= [tok]
                            tok = tmp
                        else:
                            self.warn(tok, Parser.W_BLOCK_UNSAFE)
                    else:
                        tok.type = Token.T_BLOCK
                    child.children.append(tok)

                else:
                    raise ParseError(child, "expected function body")




            index += offset

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

        # ignore the default keyword when it comes after the keyword 'export'
        i = self.peek_keyword(tokens, token, index, -1)
        if i is not None and i >= 0:
            if tokens[i].type == Token.T_KEYWORD and tokens[i].value == 'export':
                return 1

        rhs1 = self.consume(tokens, token, index, 1)

        if rhs1.type != Token.T_SPECIAL or rhs1.value != ":":
            raise ParseError(token, "expected label")

        token.type = Token.T_DEFAULT

    def collect_keyword_dowhile(self, tokens, index):
        """
        The resulting token has the form

        Token<T_DOWHILE, _>
            Token<..., body>
            Token<..., test>
        """
        token = tokens[index]

        rhs1 = self.consume(tokens, token, index, 1)
        rhs2 = self.consume_keyword(tokens, token, index, 1)
        rhs3 = self.consume(tokens, token, index, 1)

        if rhs2.type != Token.T_KEYWORD or rhs2.value != "while":
            raise ParseError(rhs2, "expected while")

        if rhs1.type != Token.T_GROUPING:
            if self.python:
                tmp = Token(Token.T_BLOCK, rhs1.line, rhs1.index, '{}')
                tmp.children= [rhs1]
                rhs1 = tmp
            else:
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

        The resulting token has the form

            Token<T_EXPORT, export_name>
                Token<T_TEXT, export_name>
                Token<..., body>

            Token<T_EXPORT_DEFAULT, export_name>
                Token<T_TEXT, export_name>
                Token<..., body>


        """
        token = tokens[index]

        # consume the word default, but don't do anything with it
        kind = Token.T_EXPORT
        i1 = self.peek_keyword(tokens, token, index, 1)
        if i1 is not None and tokens[i1].type == Token.T_KEYWORD and tokens[i1].value == 'default':
            self.consume_keyword(tokens, token, index, 1)
            kind = Token.T_EXPORT_DEFAULT

        child = self.consume_keyword(tokens, token, index, 1)

        node = child
        while node:
            if node.type == Token.T_TEXT:
                if not node.value:
                    raise ParseError(token, "unable to export anonymous entity")
                token.value = node.value
                break
            elif node.type == Token.T_ASSIGN and node.value == "=":
                node = node.children[0]
            elif node.type == Token.T_VAR:
                node = node.children[0]
            elif node.type == Token.T_CLASS:
                node = node.children[0]
            elif node.type == Token.T_FUNCTION:
                node = node.children[0]
            else:
                raise ParseError(node, "unable to export token")

        name = Token(Token.T_TEXT, child.line, child.index, token.value)
        token.type = kind
        token.children = [name, child]

    def _collect_keyword_import_get_name(self, module):

        if module.type == Token.T_GET_ATTR:
            text = ""
            node = module
            while node.type == Token.T_GET_ATTR:
                if node.children[1].type == Token.T_ATTR:
                    text = node.children[1].value + text
                else:
                    raise ParseError(node.children[1], "invalid")

                text = '.' + text

                if node.children[0].type == Token.T_GET_ATTR:
                    node = node.children[0]
                elif node.children[0].type == Token.T_TEXT:
                    text = node.children[0].value + text
                    break
                else:
                    raise ParseError(node.children[0], "invalid")

            return text
        elif module.type == Token.T_STRING:
            return ast.literal_eval(module.value)
        elif module.type == Token.T_TEXT:
            return module.value
        else:
            raise ParseError(module, "invalid module name")

    def collect_keyword_pyimport(self, tokens, index):

        token = tokens[index]

        module = self.consume(tokens, token, index, 1)

        token.type = Token.T_PYIMPORT
        import_path = self._collect_keyword_import_get_name(module)
        import_name = import_path.split('.')[0]
        import_level = prefix_count(import_path, '.')

        tok_name = Token(Token.T_TEXT, token.line, token.index, import_name)
        tok_level = Token(Token.T_NUMBER, token.line, token.index, str(import_level))
        tok_fromlist = tok1 = Token(Token.T_ARGLIST, token.line, token.index, "()")

        token.value = import_path
        token.children = [tok_name, tok_level, tok_fromlist]

    def collect_keyword_import(self, tokens, index):
        token = tokens[index]

        next_tok = self.consume(tokens, token, index, 1)

        if next_tok.type == Token.T_TEXT and next_tok.value == 'module':
            token.type = Token.T_IMPORT_MODULE
            module = self.consume(tokens, token, index, 1)
        else:
            token.type = Token.T_IMPORT
            module = next_tok

        token.value = self._collect_keyword_import_get_name(module)

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

    def collect_keyword_import_from(self, tokens, index):
        token = tokens[index]

        next_tok = self.consume(tokens, token, index, 1)

        if next_tok.type == Token.T_TEXT and next_tok.value == 'module':
            token.type = Token.T_IMPORT_MODULE
            module = self.consume(tokens, token, index, 1)
        else:
            token.type = Token.T_IMPORT
            module = next_tok

        token.value = self._collect_keyword_import_get_name(module)

        i1 = self.peek_keyword(tokens, token, index, 1)
        if i1 is not None and tokens[i1].type == Token.T_KEYWORD and tokens[i1].value == 'import':
            self.consume_keyword(tokens, token, index, 1)
            fromlist = self.consume(tokens, token, index, 1)
            if fromlist.type != Token.T_GROUPING:
                raise ParseError(fromlist, "expected {} for fromlist")
            else:
                fromlist.type = Token.T_OBJECT
            token.children.append(fromlist)
        else:
            raise ParseError(token, "expected keyword 'import'")

    def collect_keyword_include(self, tokens, index):
        token = tokens[index]

        path = self.consume(tokens, token, index, 1)

        if path.type != Token.T_STRING:
            raise ParseError(token, "expect string for include path")

        token.children.append(path)

        token.type = Token.T_INCLUDE

    def collect_keyword_for(self, tokens, index):
        """


        Note: this is the only use of 'of' as a keyword.
            firefox allows for assigning to a variable 'of'.
            for these reasons 'of' is not a keyword but is
            made a special case here

        consume:

            for (expr; expr; expr) expr
            for (expr1) expr
            where expr1 is one of:
                [const] property in object
                [const] item of iterable

        produce:

            T_FOR
                T_ARGLIST
                    <expr_init>
                    <expr_test>
                    <expr_incr>
                <any>

            T_FOR_IN
                <expr_var>
                <iterable>
                <any>

            T_FOR_OF
                <expr_var>
                <iterable>
                <any>
        """
        token = tokens[index]

        rhs1 = self.consume(tokens, token, index, 1)
        rhs2 = self.consume(tokens, token, index, 1)

        if rhs1.type != Token.T_GROUPING:
            raise ParseError(token, "expected grouping")
        else:
            rhs1.type = Token.T_ARGLIST

        if len(rhs1.children) == 0:
            raise ParseError(rhs1, "empty argument list")

        token.children = []
        if len(rhs1.children) == 1 and rhs1.children[0].value == "in" and rhs1.children[0].type == Token.T_BINARY:
            mid = rhs1.children[0]
            token.children.append(mid.children[0])
            token.children.append(mid.children[1])
            token.type = Token.T_FOR_IN

        elif len(rhs1.children) > 1 and rhs1.children[1].value == "of" and rhs1.children[1].type == Token.T_TEXT:
            token.children.append(rhs1.children[0])
            token.children.append(rhs1.children[2])
            token.type = Token.T_FOR_OF

        elif len(rhs1.children) > 1 and rhs1.children[1].value == "in" and rhs1.children[1].type == Token.T_KEYWORD:
            token.children.append(rhs1.children[0])
            token.children.append(rhs1.children[2])
            token.type = Token.T_FOR_IN

        else:
            # discover sub expressions separated by semi-colons
            exprs = [Token('T_EMPTY_TOKEN', token.line, token.index, ""),
                     Token('T_EMPTY_TOKEN', token.line, token.index, ""),
                     Token('T_EMPTY_TOKEN', token.line, token.index, "")]

            index = 0
            for child in rhs1.children:
                if child.type == Token.T_SPECIAL and child.value == ';':
                    index += 1
                elif index < 3:
                    exprs[index] = child

            rhs1.children = exprs
            token.type = Token.T_FOR
            token.children = [rhs1]

        if rhs2.type != Token.T_GROUPING:
            if self.python:
                tmp = Token(Token.T_BLOCK, rhs2.line, rhs2.index, '{}')
                tmp.children= [rhs2]
                rhs2 = tmp
            else:
                self.warn(rhs2, Parser.W_BLOCK_UNSAFE)
        else:
            rhs2.type = Token.T_BLOCK

        token.children.append(rhs2)

    def collect_keyword_function(self, tokens, index):
        token = tokens[index]

        rhs1 = self.consume(tokens, token, index, 1)

        # function () {}
        # function name() {}
        anonymous = False

        if rhs1.type == Token.T_FUNCTIONCALL:
            token.children = rhs1.children
        elif rhs1.type == Token.T_GROUPING:
            # anonymous function
            anonymous = True
            token.children = [Token(Token.T_TEXT, token.line, token.index, "Anonymous"), rhs1]
        else:
            # name, arglist
            token.children = [rhs1, self.consume(tokens, token, index, 1)]

        # function body
        body = self.consume(tokens, token, index, 1)

        if token.children[1].type not in (Token.T_GROUPING, Token.T_ARGLIST):
            raise ParseError(token, "expected arglist")

        token.children[1].type = Token.T_ARGLIST

        if body.type != Token.T_GROUPING:
            if self.python:
                tmp = Token(Token.T_BLOCK, body.line, body.index, '{}')
                tmp.children= [body]
                body = tmp
            else:
                self.warn(body, Parser.W_BLOCK_UNSAFE)
        else:
            body.type = Token.T_BLOCK

        if token.value == 'function*':
            if anonymous:
                token.type = Token.T_ANONYMOUS_GENERATOR
            else:
                token.type = Token.T_GENERATOR
        else:
            if anonymous:
                token.type = Token.T_ANONYMOUS_FUNCTION
            else:
                token.type = Token.T_FUNCTION

        ia = self.peek_keyword(tokens, token, index, -1)
        if ia and tokens[ia].type == Token.T_KEYWORD and tokens[ia].value == 'async':
            _ = self.consume_keyword(tokens, token, index, -1)

            if token.type == Token.T_FUNCTION:
                token.type = Token.T_ASYNC_FUNCTION

            elif token.type == Token.T_ANONYMOUS_FUNCTION:
                token.type = Token.T_ASYNC_ANONYMOUS_FUNCTION

            elif token.type == Token.T_GENERATOR:
                token.type = Token.T_ASYNC_GENERATOR

            elif token.type == Token.T_ANONYMOUS_GENERATOR:
                token.type = Token.T_ASYNC_ANONYMOUS_GENERATOR

        token.children.append(body)

    def collect_keyword_if(self, tokens, index):
        """
        collect branching statements

        a branch token has 2 or 3 tokens,
            1: the test
            2: the true case
            3: the optional false case


        if (...) {}
        if (...) {} else {}
        if (...) {} else if (...) {}
        if (...) {} else if (...) {} else {}
        """

        token = tokens[index]

        rhs1 = self.consume(tokens, token, index, 1)
        rhs2 = self.consume_keyword(tokens, token, index, 1)
        i3 = self.peek_keyword(tokens, token, index, 1)

        if rhs2.type != Token.T_GROUPING:
            self.warn(rhs2, Parser.W_BRANCH_TRUE)
        else:
            rhs2.type = Token.T_BLOCK

        if (rhs1.type != Token.T_GROUPING):
            raise ParseError(token, "expected grouping")

        rhs1.type = Token.T_ARGLIST

        if len(rhs1.children) == 1:
            if rhs1.children[0].type == Token.T_TEXT:
                self.warn(rhs1.children[0], Parser.W_UNSAFE_BOOLEAN_TEST)

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
        """
        super([args])
        super.parentFunction([args])
        """
        token = tokens[index]
        rhs1 = self.consume(tokens, token, index, 1)

        if rhs1.type != Token.T_GROUPING:
            raise ParseError(rhs1, "expected function call")
        else:
            rhs1.type = Token.T_ARGLIST

        token.children = [Token(Token.T_KEYWORD, token.line, token.index, "super"), rhs1]
        token.type = Token.T_FUNCTIONCALL
        token.value = ""

    def collect_keyword_switch(self, tokens, index):
        """
        switch (expr) { case expr: break; default: break; }
        """

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
        """
        throw expr
        """

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
            if self.python:
                tmp = Token(Token.T_BLOCK, rhs.line, rhs.index, '{}')
                tmp.children= [rhs]
                rhs = tmp
            else:
                self.warn(rhs, Parser.W_BLOCK_UNSAFE)
        else:
            rhs.type = Token.T_BLOCK

        token.children = [rhs]
        token.type = Token.T_TRY

        i2 = self.peek_token(tokens, token, index, 1)
        # consequence of making catch not a KEYWORD is that
        # it gets processed as a function call
        #while (i2 is not None and tokens[i2].type == Token.T_TEXT and tokens[i2].value == 'catch'):
        while (i2 is not None and tokens[i2].type == Token.T_FUNCTIONCALL and tokens[i2].children[0].value == 'catch'):
            rhs1 = self.consume(tokens, token, index, 1)
            rhs1, rhs2 = rhs1.children
            #rhs1 = self.consume_keyword(tokens, token, index, 1)
            #rhs2 = self.consume(tokens, token, index, 1)
            rhs3 = self.consume(tokens, token, index, 1)
            if rhs3.type != Token.T_GROUPING:
                if self.python:
                    tmp = Token(Token.T_BLOCK, rhs3.line, rhs3.index, '{}')
                    tmp.children= [rhs3]
                    rhs3 = tmp
                else:
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
                if self.python:
                    tmp = Token(Token.T_BLOCK, rhs2.line, rhs2.index, '{}')
                    tmp.children= [rhs2]
                    rhs2 = tmp
                else:
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
            if self.python:
                tmp = Token(Token.T_BLOCK, rhs2.line, rhs2.index, '{}')
                tmp.children= [rhs2]
                rhs2 = tmp
            else:
                self.warn(rhs2, Parser.W_BLOCK_UNSAFE)
        else:
            rhs2.type = Token.T_BLOCK

        token.children = [rhs1, rhs2]
        token.type = Token.T_WHILE

def main():  # pragma: no cover

    # TODO: let x,y,z
    # TODO: if (true) {x=1;} + 1
    #       this gives an odd error message
    #       expected object but the error is because of the parent node
    # TODO: if x {} throws a weird error

    text1 = """

    from module foo.bar import {}
    from foo.bar import {}
    import module foo.bar
    import foo.bar
    include 'foo.js'
    export a
    export a = 1
    export const a = 1
    export let a = 1
    export var a = 1
    export function a () {}
    export class a {}
    export default a
    export default a = 1
    export default const a = 1
    export default let a = 1
    export default var a = 1
    export default function a () {}
    export default class a {}
    """

    text1 = """
    let x,y,z
    """

    tokens = Lexer({'preserve_documentation': True}).lex(text1)
    mod = Parser().parse(tokens)

    print(mod.toString(3))


if __name__ == '__main__':  # pragma: no cover
    main()
