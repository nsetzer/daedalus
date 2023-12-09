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
from .lexer import Lexer, Token, TokenError, reserved_types
from .transform import TransformGrouping, \
    TransformFlatten, TransformOptionalChaining, \
    TransformMagicConstants, TransformRemoveSemicolons, TransformBase
import traceback

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
            break
    return count

class TransformTemplateString(TransformBase):

    def visit(self, token, parent):

        if token.type == Token.T_TEMPLATE_STRING:
            segments = self.parse_string(token)

            tokens = []
            for isExpr, offset, text in segments:
                if not text:
                    continue
                # TODO: technically, these are STRING_LITERALS, not STRINGS
                # the values are not quoted - they get used in slightly
                # different ways by the VM (which needs a STRING) and the formatter
                # (which assumes a literal)
                type_ = Token.T_TEMPLATE_EXPRESSION if isExpr else Token.T_STRING
                tok = Token(type_, 1, 0, text)
                if isExpr:
                    # the option template_string is purely for debug purposes
                    lexer = Lexer({"template_string": 1})
                    # TODO: column offset may not be perfect
                    lexer._first_token = (token.line,token.index + offset + 1)
                    ast = Parser().parse(lexer.lex(text))
                    tok.children = ast.children

                tokens.append(tok)
            token.children = tokens

    def parse_string(self, token):
        """
        parse a template string and get the text and expression segments
        """
        segments = []
        text = token.value[1:-1]
        index=0
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
                        segments.append((1, start, text[start:index]))
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
                        segments.append((0, start, text[start:index-1]))
                        start = index + 1

            index += 1

        segments.append((0, start, text[start:index]))

        return segments

class ParserBase(object):

    def __init__(self):
        super(ParserBase, self).__init__()

        self.precedence = []

        self.token_input_grouping_type = Token.T_SPECIAL
        self.token_output_grouping_type = Token.T_GROUPING
        self.token_ast_type = Token.T_MODULE

    def parse(self, tokens):

        pairs = {
            '(': ')',
            '[': ']',
            '{': '}',
        }

        # iterate in reverse looking for the opening symbol
        # then perform a forward scan to find it's matching pair
        index = len(tokens) - 1
        while index >= 0:
            token = tokens[index]
            if token.type == self.token_input_grouping_type and token.value in pairs:
                self.grouping(tokens, index, token.value, pairs[token.value])
                self.scan(token)
            if token.type == self.token_input_grouping_type and token.value == "<":
                self.group_generic(tokens, index)
            index -= 1

        closers = set(pairs.values())
        for token in tokens:
            if token.type == Token.T_SPECIAL and token.value in closers:
                raise ParseError(token, "unopened grouping")

        mod = Token(self.token_ast_type, 0, 0, "", tokens)
        self.scan(mod)

        return mod

    def group_generic(self, tokens, index):
        # https://www.typescriptlang.org/docs/handbook/2/generics.html
        # TODO: a generic is either:
        #   type identifier = identifier T_GENERIC
        #   interface identifier = identifier T_GENERIC
        #   : identifier T_GENERIC
        #   identifier T_GENERIC T_GROUPING()
        #   class identifier T_GENERIC
        # within angle brackets a generic can contain any valid type definition
        # text, boolean operators, commas, sequences and mappings
        # as well as some typescript specific keywords: extends, keyof, valueof
        
        pairs = {
            '(': ')',
            '[': ']',
            '{': '}',
        }

        valid = {
            Token.T_SPECIAL: ["&", "|", ",", ":"],
            Token.T_STRING: None,
            Token.T_NUMBER: None,
            Token.T_TEXT: None,
            Token.T_KEYWORD: None,
            Token.T_GROUPING: None,
        }

        nested_stack = []

        success = -1

        for i in range(index+1, len(tokens)):

            tok = tokens[i]
            if len(nested_stack) == 0 and tok.type == Token.T_SPECIAL and tok.value == ">":
                success = i
                break
            elif tok.type == Token.T_SPECIAL and tok.value in "({[":
                nested_stack.push(tok.value)
            elif tok.type == Token.T_SPECIAL and tok.value in ")}]":
                if len(nested_stack) > 0:
                    c = nested_stack.pop()
                    if pairs[c] != tok.value:
                        break
                else:
                    break
            elif tok.type in valid:
                if valid[tok.type] is not None:
                    if tok.value not in valid[tok.type]:
                        break
                
        if success < 0:
            return

        is_rhs_grouping = False
        if success + 1 < len(tokens):
            tok = tokens[success + 1]
            is_rhs_grouping = tok.type == Token.T_GROUPING and tok.value == "()"

        is_lhs_type = False
        if index >= 2:
            tok1 = tokens[index-1] # peek?
            tok2 = tokens[index-2] # peek?
            if tok1.type == Token.T_TEXT:
            
                if tok2.type == Token.T_KEYWORD and tok2.value == "class":
                    is_lhs_type = True
                if tok2.type == Token.T_SPECIAL:
                    if tok2.value == ":":
                        is_lhs_type = True
                    if index >= 3 and tok2.value == "=":
                        tok3 = tokens[index-3] # peek?
                        if tok3.value in ("type", "interface"):
                            is_lhs_type = True

        if not is_lhs_type and not is_rhs_grouping:
            return

        grp = tokens[index]
        grp.type = Token.T_GENERIC
        grp.value = "<>"
        tokens.pop(success)
        for i in reversed(range(index+1, success)):
            grp.children.insert(0, tokens.pop(i))

        # TODO: should grp be added as a child of index-1?

        tokens.pop(index)

    def grouping(self, tokens, index, open, close):
        current = tokens[index]

        current.type = self.token_output_grouping_type
        current.value = open + close
        index += 1

        # this takes into account tokens of the same type,
        # however this is not required because of the new reverse scan
        # used by the caller
        counter = 1
        start = index
        while index < len(tokens):
            token = tokens[index]
            if token.type == self.token_input_grouping_type and token.value == open:
                counter += 1
            elif token.type == self.token_input_grouping_type and token.value == close:
                counter -= 1
                if counter == 0:
                    current.children = tokens[start:index]
                    del tokens[start:index+1]
                    break
            index += 1

        if counter != 0:
            raise ParseError(current, "matching %s not found" % close)

    def scan(self, token):
        """
        scan each token in a sequence. tokens which produce nested
        groups have already been processed. scanning can be done in
        either direction: left-to-right or right-to-left.

        the precedence decides how tokens combine together
        """

        for direction, callback, operators in self.precedence:

            i = 0
            while i < len(token.children):

                if direction < 0:
                    j = len(token.children) - i - 1
                else:
                    j = i

                i += callback(token, token.children, j, operators)

def xform_apply_file(mod, filepath):

    seq = [mod]
    while seq:
        child = seq.pop(0)
        seq.extend(child.children)
        child.file = filepath

class Parser(ParserBase):

    W_BRANCH_FALSE = 1
    W_BRANCH_TRUE  = 2
    W_BLOCK_UNSAFE  = 3
    W_UNSUPPORTED = 4
    W_EXPORT_DEFAULT = 5
    W_VAR_USED = 6
    W_UNSAFE_BOOLEAN_TEST = 7  # Note: could be expanded to testing between operator &&, ||
    W_USELESS_KEYWORD = 8
    W_GROUPING = 9
    W_ELSE_UNSAFE = 10

    def __init__(self):
        super(Parser, self).__init__()

        # when true, output an AST which is more friendly for compiling
        self.python = False

        L2R = 1
        R2L = -1

        self.precedence = [
            (R2L, self.visit_mutable_prefix, ['#']),
            (L2R, self.visit_attr, ['.', "?."]),  # also: x[], x()
            (L2R, self.visit_new, []),
            (L2R, self.visit_unary_postfix, ['++', '--']),
            (R2L, self.visit_unary_prefix, ['!', '~', '+', '-', '++', '--']),
            (R2L, self.visit_prefix, ['typeof', 'void', 'delete', 'await', "keyof", "valueof"]),
            (R2L, self.visit_binary, ['**']),
            (L2R, self.visit_math_mul, ['*', '/', '%']),
            (L2R, self.visit_binary, ['+', '-']),
            (L2R, self.visit_binary, ['<<', '>>', ">>>"]),
            (L2R, self.visit_generic_lambda, ['=>',]),
            #(L2R, self.visit_binary, ['<', '<=', ">", ">=", "in", "of", "instanceof"]),
            (L2R, self.visit_binary, ['<', '<=', ">", ">=", "instanceof"]),
            (L2R, self.visit_binary, ['==', '!=', '===', '!==']),
            (L2R, self.visit_binary, ['&']),
            (L2R, self.visit_binary, ['^']),
            (L2R, self.visit_binary, ['|']),
            (L2R, self.visit_binary, ['??']),
            (L2R, self.visit_binary, ['&&']),
            (L2R, self.visit_binary, ['||']),
            (L2R, self.visit_binary, ['|>']),  # unsure where to place in sequence
            (L2R, self.visit_unary, ['...']),
            (L2R, self.visit_type_annotations, []),
            #(R2L, self.visit_ternary, ['?']), # merged with visit_assign_v2
            (R2L, self.visit_assign_v2, [
                    '=>',
                    '=', '+=', '-=', '**=', '*=', '/=',
                    '<<=', '>>=',
                    '&=', '|=', '^=',
                    '||=', "??=", "&&=",
                    ">>>="
                    ]),
            #(L2R, self.visit_binary, ["in", "of"]),
            (R2L, self.visit_unary, ['yield', 'yield*']),
            (L2R, self.visit_keyword_case, []),
            (L2R, self.visit_colon, [':']),
            (L2R, self.visit_import_as, ['as']),
            (L2R, self.visit_comma_before, []),
            (L2R, self.visit_comma, [',']),
            (L2R, self.visit_comma_after, []),
            (L2R, self.visit_keyword_arg, []),
            (L2R, self.visit_keyword, []),
            (L2R, self.visit_keyword_import_export, []),
            (L2R, self.visit_cleanup, []),
        ]

        self.module_name = "<string>"

        self.warnings = {
            Parser.W_BRANCH_FALSE: "false branch of if statement is not safe",
            Parser.W_BRANCH_TRUE: "true branch of if statement is not safe",
            Parser.W_BLOCK_UNSAFE: "block statement is not safe",
            Parser.W_UNSUPPORTED: "token not supported",
            Parser.W_EXPORT_DEFAULT: "meaningless export default",
            Parser.W_VAR_USED: "unsafe use of keyword var",
            Parser.W_UNSAFE_BOOLEAN_TEST: "unsafe boolean test. use (!!{token}) or (({token} !== undefined) && ({token} !== null))",
            Parser.W_USELESS_KEYWORD: "useless use of keyword",
            Parser.W_GROUPING: "expected parenthetical grouping",
            Parser.W_ELSE_UNSAFE: "unsafe `else` expression. did you mean `else if`",
        }
        self.warnings_count = {}

        self.disabled_warnings = set()
        self.disable_all_warnings = False

        self.feat_xform_optional_chaining = True
        #self.feat_xform_null_coalescing = True

        self._offset = 0  # used by consume in the negative direction

    def parse(self, tokens, source_file=None):

        mod = super().parse(tokens)

        TransformRemoveSemicolons().transform(mod)
        TransformGrouping().transform(mod)
        TransformFlatten().transform(mod)
        if self.feat_xform_optional_chaining:
            TransformOptionalChaining().transform(mod)
        #if self.feat_xform_null_coalescing:
        #    TransformNullCoalescing().transform(mod)
        TransformMagicConstants().transform(mod)

        # the template transform is last because it recursively uses the parser
        TransformTemplateString().transform(mod)



        return mod

    def warn(self, token, type, message=None):
        """
        print a warning message, up to N of each type, as long as
        warnings are not disabled and
        """

        if type not in self.warnings_count:
            self.warnings_count[type] = 0
        else:
            self.warnings_count[type] += 1

        if self.warnings_count[type] > 5:
            return

        if self.disable_all_warnings:
            return

        if type in self.disabled_warnings:
            return

        text = self.warnings[type].format(token=token.value)
        if message:
            text += ":" + message

        text = "WARNING: module: %s line: %d column: %d type: %s value: %s : %s\n" % (
            self.module_name, token.line, token.index, token.type, token.value, text)

        sys.stdout.write("\n")
        sys.stdout.write(text)
        #print(traceback.print_stack())

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
            elif tok1.type == Token.T_KEYWORD and tok1.value not in ("true", "false", "null", "undefined", "this", "new", "function", "function*", "class"):
                break
            elif tok1.type == Token.T_TEXT and tok1.value == "of":
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

        expression_whitelist = ("super", "true", "false", "null", "this", "new", "function", "function*", "class", "catch", "finally", "undefined")
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
        #print([token.value for token in tokens])
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

    def consume_block(self, tokens, index):
        """
        like consume_keyword, but consume a single executable line
        direction is always to the rhs of the given index (+1)

        This also 'fixes' the code to ensure the return value is a node
        that represents a block, a sequence of statements
        """

        j = self.peek_keyword(tokens, tokens[index], index, 1)

        tok = None
        if j is not None and tokens[j].type == Token.T_KEYWORD:
            self.visit_keyword(None, tokens, j, [])
            tok = tokens.pop(j)
            self._remove_special(tokens, j)
            #tok = Token(Token.T_BLOCK, tok.line, tok.index, '{}', [tok])
        else:
            try:
                tok = self.consume(tokens, tokens[index], index, 1)
                if tok.type != Token.T_GROUPING:
                    self._remove_special(tokens, index+1)
                    self.warn(tok, Parser.W_BLOCK_UNSAFE)
                    #tok = Token(Token.T_BLOCK, tok.line, tok.index, '{}', [tok])
                else:
                    tok.type = Token.T_BLOCK
            except ParseError as e:
                if index + 1 < len(tokens) \
                  and tokens[index + 1].type == Token.T_SPECIAL \
                  and tokens[index + 1].value == ';':
                    self.warn(tokens[index], Parser.W_USELESS_KEYWORD)
                    tok = Token(Token.T_BLOCK, tokens[index].line, tokens[index].index, "{}")
                else:
                    raise e

        if self.python and tok.type != Token.T_GROUPING:
            tok = Token(Token.T_BLOCK, tok.line, tok.index, '{}', [tok])

        return tok

    def consume_type(self, tokens, index):

        rhs1 = self.consume_keyword(tokens, tokens[index], index, 1)

        if rhs1.type == Token.T_LAMBDA:
            rhs1.children.pop(0)

        seq = [rhs1]

        idx = self.peek_keyword(tokens, tokens[index], index, 1)
        while idx is not None and tokens[idx].type == Token.T_SPECIAL and tokens[idx].value == '=>':
            seq.append(self.consume_keyword(tokens, tokens[index], index, 1))
            seq.append(self.consume_keyword(tokens, tokens[index], index, 1))
            idx = self.peek_keyword(tokens, tokens[index], index, 1)

        while len(seq) > 1:
            rhs = seq.pop()
            sym = seq.pop()
            lhs = seq.pop()
            sym.children.append(lhs)
            sym.children.append(rhs)
            seq.append(sym)
            sym.type = Token.T_LAMBDA

        return seq[0]

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

        #elif token.type == Token.T_SPECIAL and token.value == '=>':
        #    return self.visit_lambda(parent, tokens, index, ["=>"])

        elif token.type == Token.T_GROUPING and token.value == '()':
            i1 = self.peek_token(tokens, token, index, -1)
            if i1:
                i2 = self.peek_token(tokens, token, i1, -1)
            else:
                i2 = None

            # special case for `() => {} ()`
            # correct syntax would be (()=>{})()
            if i1 is not None and i2 is not None:
                if tokens[i2].type == Token.T_SPECIAL and tokens[i2].value == "=>":
                     if tokens[i1].type == Token.T_GROUPING:
                        #self.visit_lambda(parent, tokens, i2, ["=>"])
                        #return -2
                        self.warn(tokens[i2], Parser.W_GROUPING)

            if i1 is not None and tokens[i1].type not in (Token.T_SPECIAL, Token.T_NUMBER, Token.T_STRING):
                i2 = self.peek_keyword(tokens, token, i1, -1)
                # TODO: for (x in y) (expr)()
                # only 1 of these is a valid function call,
                # this attempts to handle the keyword case, but not all
                if i2 is not None and tokens[i2].value == "for":
                    return 1
                lhs = self.consume(tokens, token, index, -1)

                if lhs.type == Token.T_TEXT and lhs.value in ("catch", "finally"):
                    # the syntax looks like a function call:
                    #   catch(expr) {}
                    # but catch is a keyword, produce a catch node instead
                    tok1 = Token(Token.T_CATCH, token.line, token.index, lhs.value)
                    tok1.children = [token]
                    token.type = Token.T_ARGLIST
                    tokens[index - 1] = tok1
                else:
                    # the syntax looks like a function call:
                    #   expr(expr) {}
                    # produce a function call node, without a body

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
                    i1 = self.peek_keyword(tokens, token, index, -1)
                    if i1 is not None:
                        tok = tokens[i1]
                        if tok.type == Token.T_KEYWORD and tok.value in reserved_types:
                            lhs = self.consume_keyword(tokens, token, index, -1)
                            tok1 = Token(Token.T_SUBSCR, token.line, token.index, "")
                            tok1.children = [lhs] + token.children
                            tokens[index - 1] = tok1
                            return self._offset

                    token.type = Token.T_LIST

        elif token.type == Token.T_TEMPLATE_STRING:

            i1 = self.peek_token(tokens, token, index, -1)
            if i1 is not None and tokens[i1].type in (Token.T_TEXT, Token.T_GET_ATTR):

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

    def visit_mutable_prefix(self, parent, tokens, index, operators):

        token = tokens[index]

        if token.type not in (Token.T_SPECIAL) or \
           token.value not in operators:
            return 1

        i2 = self.peek_token(tokens, token, index, 1)

        if i2 is not None:
            next = tokens[i2]
            if next.type == Token.T_GROUPING:
                if next.value == "[]":
                    next.type = Token.T_TUPLE
                elif next.value == "{}":
                    next.type = Token.T_RECORD
                tokens.pop(index)
                return 0
            elif next.type == Token.T_TEXT:
                # hash can be a prefix to an identifier when used in
                # a class context to indicate a private variable
                token.type = Token.T_TEXT
                token.value += self.consume(tokens, token, index, 1).value
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

        Notes:
            the use of a pound sign (#) is an unused javascript extension

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

        if token.type not in (Token.T_SPECIAL, Token.T_KEYWORD, Token.T_TEXT) or \
           token.value not in operators:
            return 1

        idx = self.peek_token(tokens, token, index, 1)
        if idx is None and token.type == Token.T_KEYWORD and token.value == "void":
            pass
        elif idx is not None and tokens[idx].type == Token.T_SPECIAL and tokens[idx].value == '=>':
            pass
        else:
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

    def visit_generic_lambda(self, parent, tokens, index, operators):

        token = tokens[index]

        if token.type not in (Token.T_SPECIAL, Token.T_KEYWORD) or \
           token.value not in operators:
            return 1

        start_index = index
        index -= 2
        if index >= 0 and tokens[index].type == Token.T_SPECIAL and tokens[index].value == ">":
            # reverse grouping
            current = tokens[index]
            current.type = Token.T_SPECIAL
            current.value = "<>"
            index -= 1

            # this takes into account tokens of the same type,
            # however this is not required because of the new reverse scan
            # used by the caller
            counter = 1
            start = index
            while index >= 0:
                token = tokens[index]
                if token.type == Token.T_SPECIAL and token.value == ">":
                    counter += 1
                elif token.type == Token.T_SPECIAL and token.value == "<":
                    counter -= 1
                    if counter == 0:
                        current.children = tokens[index+1:start+1]
                        del tokens[index:start+1]
                        break
                index -= 1

            if counter != 0:
                raise ParseError(current, "matching `>` not found")

            tokens.pop(index)

            rv = (index - start_index) + 2
            print([token.value for token in tokens], start_index + rv)
            return rv

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
        #if token.value == 'in':
        #    i1 = self.peek_token(tokens, token, index, -1)
        #    if i1 is not None:
        #        i2 = self.peek_keyword(tokens, token, i1, -1)
        #        if i2 is not None:
        #            tok2 = tokens[i2]
        #            if tok2.type == Token.T_KEYWORD and tok2.value in ('constexpr', 'const', 'let', 'var'):
        #                return 1

        if token.value == '*':
            # for javascript style module imports
            #   import * as alias from path
            #   detect `import *` and skip
            i1 = self.peek_keyword(tokens, token, index, -1)
            if i1 is not None:
                tok1 = tokens[i1]
                if tok1.type == Token.T_KEYWORD and tok1.value == 'import':
                    return 1

        rhs = self.consume_keyword(tokens, token, index, 1)
        lhs = self.consume_keyword(tokens, token, index, -1)
        token.children.append(lhs)
        token.children.append(rhs)

        if token.value == 'instanceof':
            token.type = Token.T_INSTANCE_OF
        elif token.value == '&&':
            token.type = Token.T_LOGICAL_AND
        elif token.value == '||':
            token.type = Token.T_LOGICAL_OR
        elif token.value == '??':
            token.type = Token.T_NULLISH_COALESCING
        else:
            token.type = Token.T_BINARY

        return self._offset

    def visit_in_of(self, parent, tokens, index, operators):
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
                    if tok2.type == Token.T_KEYWORD and tok2.value in ('constexpr', 'const', 'let', 'var'):
                        return 1

        rhs = self.consume(tokens, token, index, 1)
        lhs = self.consume(tokens, token, index, -1)
        token.children.append(lhs)
        token.children.append(rhs)
        token.type = Token.T_BINARY

        return self._offset

    def visit_math_mul(self, parent, tokens, index, operators):
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

        if token.value == '*':
            # for javascript style module imports
            #   import * as alias from path
            #   detect `import *` and skip
            i1 = self.peek_keyword(tokens, token, index, -1)
            if i1 is not None:
                tok1 = tokens[i1]
                if tok1.type == Token.T_KEYWORD and tok1.value == 'import' or tok1.value == 'export':
                    return 1

        rhs = self.consume(tokens, token, index, 1)
        lhs = self.consume(tokens, token, index, -1)
        token.children.append(lhs)
        token.children.append(rhs)


        token.type = Token.T_BINARY

        return self._offset

    def visit_colon(self, parent, tokens, index, operators):
        """
        parse colon separated pairs,
        in certain cases this can be parsed as a block label instead

        in other cases the binary result may be transformed into
        a block label if the object test transform fails later on.

        produce:

            T_BINARY<:>
                <expr_lhs>
                <expr_rhs>

            T_BLOCK_LABEL
                <ident>
        """
        token = tokens[index]

        if token.type not in (Token.T_SPECIAL, Token.T_KEYWORD) or \
           token.value not in operators:
            return 1

        idx = self.peek_keyword(tokens, token, index, 1)
        rhs = None
        if idx is not None:
            if tokens[idx].type == Token.T_KEYWORD and (
                tokens[idx].value in reserved_types or tokens[idx].value in ('null', 'undefined', 'true', 'false', 'this')):
                rhs = self.consume_keyword(tokens, token, index, 1)

            elif tokens[idx].type != Token.T_KEYWORD:
                rhs = self.consume(tokens, token, index, 1)


        annotation = False
        idx = self.peek_keyword(tokens, token, index, -2)
        if idx is not None:
            if (tokens[idx].type == Token.T_KEYWORD and tokens[idx].value in ('static', 'const', 'let', 'var')) or \
               (tokens[idx].type == Token.T_TEXT and tokens[idx].value in ('public', 'private')):
                annotation = True

        lhs = self.consume_keyword(tokens, token, index, -1)

        if annotation:

            if rhs is not None:
                tmp = tokens.pop(index - 1)
                tmp.children.append(rhs)
                tmp.type = Token.T_ANNOTATION
                tmp.value = ""
                tokens.insert(index-1, lhs)
                lhs.children.append(tmp)
            else:
                raise ParseError(token, "invalid type annotation")

        else:

            if rhs is None:
                token.children = []
                token.type = Token.T_BLOCK_LABEL
                token.value = lhs.value
            else:
                token.children.append(lhs)
                token.children.append(rhs)
                token.type = Token.T_BINARY

        return self._offset

    def visit_import_as(self, parent, tokens, index, operators):
        token = tokens[index]

        if token.type not in (Token.T_TEXT, Token.T_KEYWORD) or \
           token.value not in operators:
            return 1

        rhs = self.consume_keyword(tokens, token, index, 1)
        lhs = self.consume_keyword(tokens, token, index, -1)

        token.children = [lhs, rhs]
        token.type = Token.T_KEYWORD

        return  1

    def visit_assign_v2(self, parent, tokens, index, operators):
        """
        Example:
            const f = (d,k,v) => d[k] = v

        collect binary operators Right-To-Left
        """
        if tokens[index].type == 'T_KEYWORD' and (tokens[index].value == 'in' or tokens[index].value == 'of'):
            return self.visit_in_of(parent, tokens, index, ['in', 'of'])
        elif tokens[index].type == 'T_SPECIAL' and tokens[index].value == '?':
            return self.visit_ternary(parent, tokens, index, ['?'])
        elif tokens[index].type == 'T_SPECIAL' and tokens[index].value == '=>':
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

        # attempt 2  at type annotations
        if token.type == Token.T_SPECIAL and token.value == "=":
            i = index - 4
            j = index - 3
            k = index - 2
            # test pattern is # TEXT colon something equalsign
            #print([tok.value for tok in tokens[i:index+2]])

            if i < 0 or \
               i >= 0 and (tokens[i].type == Token.T_COMMA or (tokens[i].type == Token.T_SPECIAL and tokens[i].value == ',') or \
                           (tokens[i].type == Token.T_TEXT and tokens[i].value in ("private", "public")) or \
                           (tokens[i].type == Token.T_KEYWORD and \
                           tokens[i].value in  ('constexpr', 'const', 'let', 'var', 'static'))):
                if tokens[j].type == Token.T_TEXT and tokens[k].type==Token.T_SPECIAL and tokens[k].value == ":":
                    type_ = self.consume_keyword(tokens, tokens[k], k, 1)
                    tokens.pop(k)
                    anno = Token(Token.T_ANNOTATION, type_.line, type_.index, "", [type_])
                    tokens[j].children.append(anno)
                    # this will trigger a visit of this node again
                    # but with the correct index
                    return 0

        rhs = self.consume(tokens, token, index, 1)
        lhs = self.consume(tokens, token, index, -1)

        #if lhs.type == Token.T_GROUPING and token.value == "[]" or lhs.type == Token.:

        # check if the LHS is assigning to a list, or a list declaration
        if lhs.type == Token.T_LIST:
            lhs.type = Token.T_UNPACK_SEQUENCE
            self._visit_assign_fix(token, lhs)

        elif lhs.type == Token.T_GROUPING:
            lhs.type = Token.T_UNPACK_OBJECT
            self._visit_assign_fix(token, lhs)

        elif lhs.type == Token.T_VAR:
            if lhs.children[0].type == Token.T_LIST:
                lhs.children[0].type = Token.T_UNPACK_SEQUENCE

        token.children.append(lhs)
        token.children.append(rhs)

        if token.value == "??=":
            token.type = Token.T_NULLISH_ASSIGN
        else:
            token.type = Token.T_ASSIGN

        return self._offset - 1

    def _visit_assign_fix(self, parent, token):
        tokens = [token]
        while tokens:
            tok = tokens.pop()

            idx = 0
            while idx < len(tok.children):
                child = tok.children[idx]

                # convert groupings that are children
                # of a UNPACK_* into the corresponding UNPACK token
                if tok.type == Token.T_GROUPING:
                    if tok.value == "[]":
                        tok.type = Token.T_UNPACK_SEQUENCE
                    if tok.value == "{}":
                        tok.type = Token.T_UNPACK_OBJECT

                # ---
                # replace comma or skip to next
                if child.type == Token.T_COMMA:
                    tok.children[idx:idx+1] = child.children
                else:
                    idx += 1

            #if tok.type == Token.T_ASSIGN and tok.value == "=":
            #    if tok.children[1].type == Token.T_LIST:
            #        tok.type = Token.T_UNPACK_SEQUENCE
            #elif tok.type == Token.T_BINARY and tok.value == ":":
            #    if tok.children[1].type == Token.T_GROUPING:
            #        tok.children[1].type = Token.T_UNPACK_OBJECT

            tokens.extend(tok.children)

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

        if rhs.type == Token.T_GROUPING and rhs.value == '{}':
            rhs._maybe_illegal = True

        if lhs.type == Token.T_GROUPING and lhs.value == "()":
            lhs.type = Token.T_ARGLIST

        for arg in lhs.children:
            if arg.type == Token.T_LIST:
                arg.type = Token.T_UNPACK_SEQUENCE
            if arg.type == Token.T_GROUPING:
                arg.type = Token.T_UNPACK_OBJECT

        return self._offset

    def visit_comma_before(self, parent, tokens, index, operators):

        # fix grouping (objects) prior to parsing commas
        if parent.type == Token.T_GROUPING:
            tok = tokens[index]
            if tok.type == Token.T_FUNCTIONCALL:
                idx = self.peek_token(tokens, tok, index, 1)
                if idx is not None and tokens[idx].type == Token.T_GROUPING:
                    rhs = self.consume(tokens, tok, index, 1)
                    rhs.type = Token.T_BLOCK
                    tok.type = Token.T_FUNCTION
                    tok.children.append(rhs)



        return 1

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
            if tokens[index+1].type == Token.T_SPECIAL and tokens[index+1].value == ",":
                rhs = Token(Token.T_EMPTY_TOKEN, token.line, token.index, "")
                break
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
            if lhs.type == Token.T_BINARY and lhs.value in ('in', 'of'):
                tokens[index] = lhs
                tmp = lhs.children[1]
                lhs.children[1] = token
                lhs = tmp

            token.children.append(lhs)

        if rhs:
            token.children.append(rhs)

        token.type = Token.T_COMMA

        return rv

    def visit_comma_after(self, parent, tokens, index, operators):
        """
        validate that the grouping created by a comma sequence is valid

        for now only tests groups within a parenthetical region
            - does not test lists or objects
        """
        tokens[index]

        if parent.type != Token.T_GROUPING or parent.value != "()":
            return 1

        if index < len(tokens) - 1:
            return 1

        # split on semicolons to support c style for loops
        splits = [[]]
        for tok in tokens:
            if tok.type == Token.T_SPECIAL and tok.value == ";":
                splits.append([])
            else:
                splits[-1].append(tok)

        # in any sequence, all tokens must be wrapped in a comma
        # or a comma is missing
        for split in splits:
            any_comma = any([tok.type == Token.T_COMMA for tok in split])
            # T_KEYWORD is a hack for var, let, const
            all_comma = all([tok.type in (Token.T_COMMA, Token.T_NEWLINE, Token.T_KEYWORD) for tok in split])

            if any_comma and not all_comma:
                for tok in tokens:
                    if tok.type != Token.T_NEWLINE:
                        raise ParseError(tok, "expected comma")

        return 1


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
        return -3 # consumed 3 on RHS

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

        if token.type == Token.T_TEXT and token.value == "constexpr":
            self.collect_keyword_var(tokens, index)

        if token.type == Token.T_TEXT and token.value == "type":
            # type declarations are converted to 'const'
            self.collect_keyword_var(tokens, index)


        if token.type != Token.T_KEYWORD:
            return 1

        if token.value == 'const':
            self.collect_keyword_var(tokens, index)

        elif token.value == 'var':
            self.warn(token, Parser.W_VAR_USED)
            self.collect_keyword_var(tokens, index)

        elif token.value == 'let':
            self.collect_keyword_var(tokens, index)

        elif token.value == 'return':
            self.collect_keyword_return(tokens, index)

        elif token.value == 'throw':
            self.collect_keyword_throw(tokens, index)

        return 1

    def visit_keyword(self, parent, tokens, index, operators):
        # assumes: parent could be null

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

        elif token.value in ('this', 'import', 'export', "with", "true", "false", "null", "default", "static", "extends"):
            pass
        elif token.value == 'in':
            # TODO: this may be consumed in a higher layer...
            # is there  a better way for this lower layer to signal that
            pass
        elif token.value in reserved_types:
            pass
        else:
            self.warn(token, Parser.W_UNSUPPORTED)

        return 1

    def visit_keyword_import_export(self, parent, tokens, index, operators):

        token = tokens[index]

        if token.type == Token.T_FUNCTIONCALL:
            if token.children[0].type == Token.T_TEXT:

                # treat the following pairs as equal
                #
                #    from module name import {...}
                #    $import("name", {...})
                #
                #    import module name
                #    $import("name")
                #
                #    include 'path.js'
                #    $include('path.js')

                if token.children[0].value == "$import":
                    args = token.children[1].children
                    if args[0].type == Token.T_COMMA:
                        args = args[0].children
                    token.type = Token.T_IMPORT_MODULE
                    token.value = ast.literal_eval(args[0].value)
                    if len(args) > 1:
                        args[1].type = Token.T_OBJECT

                        token.children = [args[1]]
                    else:
                        token.children = []
                    return 1

                if token.children[0].value == "$include":
                    token.children[0]
                    args = token.children[1].children
                    token.type = Token.T_INCLUDE
                    token.value = "include"
                    token.children = [args[0]]
                    return 1


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

    def visit_type_annotations(self, parent, tokens, index, operators):

        token = tokens[index]

        # text
        # text [equalsign expression]
        # text colon [text|keyword|pipe|arrow...] [equalsign expression]

        #if token.type == Token.T_KEYWORD and token.value in ('const', 'let', 'var', 'constexpr'):
        #    print([token.value for token in tokens])

        #if tokens[index].type == 'T_SPECIAL' and tokens[index].value == ':':
        #    j = index - 2
        #    if j >= 0:
        #        print([token.value for token in tokens])
        #        if tokens[j].type == 'T_SPECIAL' and tokens[j].value == '?':
        #            return 1
        #        self.consume_type(tokens, index)
        #        tokens.pop(index)
        #        return 0

        #if tokens[index].type == 'T_SPECIAL' and tokens[index].value == ':':
        #    b = self.consume_type(tokens, index)
        #    a = tokens.pop(index)
        #    tokens[index-1].children = [b]

        if token.type == Token.T_KEYWORD and token.value == 'interface':
            token.type = Token.T_INTERFACE
            rhs1 = self.consume(tokens, token, index, 1)
            rhs2 = self.consume(tokens, token, index, 1)
            token.children.append(rhs1)
            token.children.append(rhs2)
            rhs2.type = Token.T_OBJECT

        return 1

    def visit_cleanup(self, parent, tokens, index, operators):

        token = tokens[index]
        if token.type == Token.T_NEWLINE:
            tokens.pop(index)
            return 0

        # fix for type definitions
        #  allow 'type' to be an identifier
        #  allow 'type x = expression' to be a type definition
        if token.type == Token.T_TEXT and token.value == "type":
            raise ValueError()
            i1 = self.peek_token(tokens, token, index, 1)
            if i1 is not None and tokens[i1].type == Token.T_ASSIGN:
                if tokens[i1].value != "=":
                    raise ParseError(tokens[i1], "expected assignment")
                token.children = [self.consume(tokens, token, index, 1)]
                token.type = Token.T_TYPE
                return 1

        return 1

    def collect_keyword_break(self, tokens, index):
        token = tokens[index]
        token.type = Token.T_BREAK

        i1 = self.peek_token(tokens, token, index, 1)
        if i1 is not None and tokens[i1].type == Token.T_TEXT:
            rhs = self.consume(tokens, token, index, 1)
            token.children = [rhs]

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

        # check for the class name
        i1 = self.peek_token(tokens, token, index, 1)
        if i1 is not None and tokens[i1].type == Token.T_TEXT:
            token.children = [self.consume(tokens, token, index, 1)]
        else:
            # anonymous class
            token.children = [Token(Token.T_TEXT, token.line, token.index, "")]

        # check for inheritance
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
            self._remove_special(tokens, index + 1)
            if self.python:
                tmp = Token(Token.T_CLASS_BLOCK, rhs1.line, rhs1.index, '{}')
                tmp.children= [rhs1]
                rhs1 = tmp
            else:
                self.warn(rhs1, Parser.W_BLOCK_UNSAFE)
        else:
            rhs1.type = Token.T_CLASS_BLOCK

        token.children.append(rhs1)
        #print(token.toString(2))

        # loop over the class body
        index = 0
        while index < len(rhs1.children):
            child = rhs1.children[index]
            #print(child.toString(2))
            # a function call inside of an object is actually a method def
            offset = 1
            if child.type == Token.T_ASSIGN:
                # check for static class properties
                li = index - 1
                if li >= 0:
                    tok = rhs1.children[li]
                    if tok.type == Token.T_KEYWORD and tok.value == 'static':

                        tok.type = Token.T_STATIC_PROPERTY
                        tmp = rhs1.children.pop(index)
                        tmp.children[0].type = Token.T_ATTR
                        tok.children.append(tmp)
            elif child.type == Token.T_FUNCTION:
                child.type = Token.T_METHOD

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
            elif child.type == Token.T_FUNCTIONCALL:
                #TODO: this should no longer be reached
                #      when the comma hack is in place

                # the child has type 'method'
                # store meta data about the method in the value position
                # the metadata will be get, set, public, private, static
                # not all of those keywords are valid javascript
                child.type = Token.T_METHOD

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
            elif child.type == Token.T_TEXT and (child.value == 'public' or child.value == 'private'):
                i = self.peek_keyword(rhs1.children, child, index, 1)
                if i is not None:
                    tok = rhs1.children[i]
                    if tok.type == Token.T_KEYWORD and tok.value == 'static':
                        rhs1.children.pop(i)
                        if child.value == 'public':
                            child.type = Token.T_PUBLIC_STATIC_PROPERTY
                        if child.value == 'private':
                            child.type = Token.T_PRIVATE_STATIC_PROPERTY
                    else:
                        if child.value == 'public':
                            child.type = Token.T_PUBLIC_PROPERTY
                        if child.value == 'private':
                            child.type = Token.T_PRIVATE_PROPERTY
                    tmp = rhs1.children.pop(i)
                    #tmp.children[0].type = Token.T_ATTR
                    child.children.append(tmp)

            elif child.type == Token.T_KEYWORD and child.value == 'static':
                # static member variables
                tok = self.consume(rhs1.children, child, index, 1)
                if tok.type == Token.T_FUNCTION:
                    tok.type = Token.T_METHOD
                    tok.value = "static"
                    rhs1.children[index] = tok
                elif tok.type == Token.T_ASSIGN:
                    child.type = Token.T_STATIC_PROPERTY
                    child.children.append(tok)
                else:
                    child.type = Token.T_STATIC_PROPERTY
                    child.children.append(tok)

            elif child.type == Token.T_GROUPING:
                raise ParseError(child, "unexpected object in class body")
            elif child.type == Token.T_BINARY and child.value == ":":
                blhs,brhs = child.children
                rhs1.children[index] = blhs
                blhs.children.append(Token(Token.T_ANNOTATION, blhs.line, blhs.index, "", [brhs]))

            index += offset

    def collect_keyword_switch_case(self, tokens, index):
        token = tokens[index]

        rhs1 = self.consume(tokens, token, index, 1)
        rhs2 = self.consume(tokens, token, index, 1)

        if rhs2.type != Token.T_SPECIAL or rhs2.value != ":":
            raise ParseError(token, "expected label")

        token.children = [rhs1]
        token.type = Token.T_CASE

        # TODO: parse elseware
        #j = index + 1
        #while j < len(tokens):
        #    print("+", j, len(tokens))
        #    rhs = tokens[j]
        #    if rhs.type == Token.T_KEYWORD and rhs.value == "case" or rhs.value == "default":
        #        break;
        #    child = tokens.pop(j)
        #    print("!child", child)
        #    token.children.append(child)


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

        rhs1 = self.consume_block(tokens, index)
        rhs2 = self.consume_keyword(tokens, token, index, 1)
        rhs3 = self.consume(tokens, token, index, 1)

        if rhs2.type != Token.T_KEYWORD or rhs2.value != "while":
            raise ParseError(rhs2, "expected while")

        if rhs3.type != Token.T_GROUPING:
            raise ParseError(rhs3, "expected parenthetical grouping")
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

        export <comma_list> from <source>

        Anonymous exports will cause a ParseError
        export function () {}
        export class {}

        The resulting token has the form

            Token<T_EXPORT, export_name>
                Token<T_ARGLIST, export_name>
                Token<T_ARGLIST, exports>
                [Token<T_ARGLIST>]

            Token<T_EXPORT_DEFAULT, export_name>
                Token<T_ARGLIST, export_name>
                Token<T_ARGLIST, exports>
                [Token<T_ARGLIST>]


        """
        token = tokens[index]

        # consume the word default, but don't do anything with it
        kind = Token.T_EXPORT
        i1 = self.peek_keyword(tokens, token, index, 1)
        if i1 is not None and tokens[i1].type == Token.T_KEYWORD and tokens[i1].value == 'default':
            self.consume_keyword(tokens, token, index, 1)
            kind = Token.T_EXPORT_DEFAULT

        child = self.consume_keyword(tokens, token, index, 1)

        if child.type == Token.T_GROUPING and child.value == "{}":
            pass

        from_source = None
        i2 = self.peek_keyword(tokens, token, index, 1)
        if i2 is not None and tokens[i2].type == Token.T_TEXT and tokens[i2].value == 'from':
            self.consume_keyword(tokens, token, index, 1)
            from_source = self.consume(tokens, token, index, 1)

        exports = []

        # collect all of the export names into a single list
        stack = [child]
        while stack:

            node = stack.pop()

            if node.type == Token.T_TEXT:
                if not node.value:
                    raise ParseError(token, "unable to export anonymous entity")
                exports.insert(0, Token(Token.T_TEXT, child.line, child.index, node.value))
            elif node.type == Token.T_ASSIGN and node.value == "=":
                stack.append(node.children[0])
            elif node.type == Token.T_VAR:
                stack.append(node.children[0])
            elif node.type == Token.T_INTERFACE:
                # an interface is "identity object" without a binary op
                stack.append(node.children[0])
            elif node.type == Token.T_TYPE:
                # a type is "identity = object" with a binary op
                stack.append(node.children[0])
            elif node.type == Token.T_CLASS:
                stack.append(node.children[0])
            elif node.type == Token.T_FUNCTION:
                stack.append(node.children[0])
            elif node.type == Token.T_COMMA:
                stack.extend(node.children)
            elif node.type == Token.T_GROUPING:
                stack.extend(node.children)
            elif node.type == Token.T_KEYWORD and node.value == "as":
                stack.extend(node.children)
            elif node.type == Token.T_SPECIAL and node.value == "*":
                pass
            else:
                raise ParseError(node, "unable to export token")

        # flatten the exports into a single list
        arglist = Token(Token.T_EXPORT_ARGS, token.line, token.index, "()", [child])
        i=0
        while i < len(arglist.children):
            if arglist.children[i].type == Token.T_COMMA:
                node = arglist.children.pop(i)
                arglist.children.insert(i, node.children[1])
                arglist.children.insert(i, node.children[0])
            else:
                i += 1

        arglist2 = Token(Token.T_EXPORT_ARGS, token.line, token.index, "()", exports)

        # the output is:
        #   the list of exported names,
        #   the list of exported nodes,
        #   optionally a from list
        token.type = kind
        token.children = [arglist2, arglist]
        if from_source:
            token.children.append(from_source)

        if token.type == Token.T_EXPORT_DEFAULT and len(exports) > 1:
            raise ParseError(token, "export default can only export a single name")

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

        """
         pyimport module
         pyimport .module {a,b,c}
         pyimport .module {a=b,c} # import a as name b
        """

        token = tokens[index]

        module = self.consume(tokens, token, index, 1)
        import_level = 0
        if module.type == Token.T_SPECIAL_IMPORT:
            import_level = len(module.value) # just count the prefix dots
            module = self.consume(tokens, token, index, 1)

        token.type = Token.T_PYIMPORT
        import_path = self._collect_keyword_import_get_name(module)
        import_name = import_path.split('.')[0]
        #import_level = prefix_count(import_path, '.')

        # the name is just the first component
        # the full module path is stored in the pyimport token
        tok_name = Token(Token.T_TEXT, token.line, token.index, import_name)
        tok_level = Token(Token.T_NUMBER, token.line, token.index, str(import_level))

        tok_fromlist = None
        j = self.peek_token(tokens, token, index, 1)
        if j is not None:
            if tokens[j].type == Token.T_GROUPING:
                tok_fromlist = self.consume(tokens, token, index, 1)
                tok_fromlist.type = Token.T_OBJECT
        if tok_fromlist is None:
            tok_fromlist = Token(Token.T_OBJECT, token.line, token.index, "{}")

        token.value = import_path
        token.children = [tok_name, tok_level, tok_fromlist]

    def collect_keyword_import(self, tokens, index):
        """

        Daedalus Imports:

            import foo.bar
            import module foo.bar

        Javascript Style Imports
            import {name} from './modules/module.js';
            import {name as foo} from './modules/module.js';
            import {name1, name2} from './modules/module.js';
            import {name1 as foo, name2 as bar} from './modules/module.js';
            import * as Module from './modules/module.js';
            import * from './modules/module.js';
        """
        token = tokens[index]

        next_tok = self.consume(tokens, token, index, 1)

        if next_tok.type == Token.T_TEXT and next_tok.value == 'module':
            token.type = Token.T_IMPORT_MODULE
            module = self.consume(tokens, token, index, 1)
        else:
            token.type = Token.T_IMPORT
            module = next_tok

        if module.type == Token.T_SPECIAL and module.value == "*":
            from_ = self.consume(tokens, token, index, 1)

            if from_.value != "from":
                name_ = from_
                from_ = self.consume(tokens, token, index, 1)
                path_ = self.consume(tokens, token, index, 1)
                children = [name_]
            else:
                path_ = self.consume(tokens, token, index, 1)
                children = []

            token.type = Token.T_IMPORT_JS_MODULE_AS
            token.value = path_.value
            token.children = children

            raise ParseError(token, "not yet supported")

        elif module.type == Token.T_GROUPING:
            # javascript style module import
            #token.type = Token.T_GROUPING
            #token.value = "{}"
            grouping = Token(Token.T_GROUPING, token.line, token.index, "{}")
            token.children = [grouping]
            grouping.children = module.children

            # undo the previous comma parsing
            #j=0
            #while j < len(grouping.children):
            #    if grouping.children[j].type == Token.T_COMMA:
            #        grouping.children[j:j+1] = grouping.children[j].children
            #    j += 1

            # group based on special keyword 'as'
            #j=0
            #while j < len(grouping.children):
            #    tok = grouping.children[j]
            #    if tok.type == Token.T_TEXT and \
            #       tok.value == "as" and len(tok.children) == 0:
            #        if j == 0 or j == len(grouping.children) - 1:
            #            # missing lhs or rhs value
            #            raise ParseError(tok, "invalid import alias")
            #        rhs = grouping.children.pop(j+1)
            #        if rhs.type == Token.T_KEYWORD or \
            #           (rhs.type == Token.T_TEXT and \
            #            rhs.value == "as"):
            #            raise ParseError(rhs, "invalid import alias")
            #        lhs = grouping.children.pop(j-1)
            #        if lhs.type == Token.T_KEYWORD or \
            #           (lhs.type == Token.T_TEXT and \
            #            lhs.value == "as"):
            #            raise ParseError(lhs, "invalid import alias")
            #        tok.type = Token.T_KEYWORD
            #        tok.children = [lhs, rhs]
            #    else:
            #        j += 1

            # now every direct child of grouping is either a import name
            # or an import alias

            from_ = self.consume_keyword(tokens, token, index, 1)
            if from_.type != Token.T_TEXT or from_.value != "from":
                raise ParseError(from_, "expected keyword 'from'")

            path = self.consume(tokens, token, index, 1)
            if path.type != Token.T_STRING:
                raise ParseError(path, "expected path to module as string")
            token.value = ast.literal_eval(path.value)
            token.type = Token.T_IMPORT_MODULE

        else:
            # daedalus style import
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

        j = self.peek_token(tokens, token, index, 1)

        if j is None:
            # token 'from' likely used as a variable instead
            return

        next_tok = tokens[j]

        """
        from module modname import {name, }
        from modname import {name, }
        """

        if next_tok.type == Token.T_TEXT and next_tok.value == 'module':
            self.consume(tokens, token, index, 1)
            token.type = Token.T_IMPORT_MODULE
            module = self.consume(tokens, token, index, 1)
        elif next_tok.type == Token.T_TEXT or next_tok.type == Token.T_GET_ATTR:
            self.consume(tokens, token, index, 1)
            token.type = Token.T_IMPORT
            module = next_tok
        else:
            # token 'from' likely used as a variable instead
            return

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
            for await (expr1) expr
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

        flag_await = False
        idx1 = self.peek_keyword(tokens, token, index, 1)
        rhs1 = None
        if idx1 is not None:
            rhs = tokens[idx1]
            if rhs.type == Token.T_PREFIX and rhs.value == 'await':
                self.consume_keyword(tokens, token, index, 1)
                rhs1 = rhs.children[0]
                flag_await = True

        if rhs1 is None:
            rhs1 = self.consume(tokens, token, index, 1)

        if rhs1.type != Token.T_GROUPING:
            raise ParseError(token, "expected grouping")
        else:
            rhs1.type = Token.T_ARGLIST

        if len(rhs1.children) == 0:
            raise ParseError(rhs1, "empty argument list")

        rhs2 = self.consume_block(tokens, index)

        token.children = []
        if len(rhs1.children) == 1 and rhs1.children[0].value == "in" and rhs1.children[0].type == Token.T_BINARY:
            mid = rhs1.children[0]
            token.children.append(mid.children[0])
            token.children.append(mid.children[1])
            token.type = Token.T_FOR_IN

        elif len(rhs1.children) > 1 and rhs1.children[1].value == "of" and rhs1.children[1].type == Token.T_TEXT:
            token.children.append(rhs1.children[0])
            token.children.append(rhs1.children[2])
            if flag_await:
                token.type = Token.T_FOR_AWAIT_OF
            else:
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

        token.children.append(rhs2)

    def collect_keyword_function(self, tokens, index):
        token = tokens[index]

        rhs1 = self.consume(tokens, token, index, 1)

        # check if this function is a generic function, pop the generic attribute
        i2 = self.peek_token(tokens, token, index, 1)
        if i2 is not None and tokens[i2].type == token.T_SPECIAL and tokens[i2].value == "<":
            self.grouping(tokens, i2, "<", ">")
            tmp = tokens.pop(i2)
            tmp.type = Token.T_GENERIC
            rhs1.children.append(tmp) # not sure where to put this

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
            arglist = self.consume(tokens, token, index, 1)
            token.children = [rhs1, arglist]

        # function body
        body = self.consume(tokens, token, index, 1)

        # check to see if a return type was given for this function
        if body.type == Token.T_SPECIAL and body.value == ":":
            type_ = self.consume_type(tokens, index)
            anno = Token(Token.T_ANNOTATION, type_.line, type_.index, "", [type_])
            token.children[0].children.append(anno)
            body = self.consume(tokens, token, index, 1)

        if token.children[1].type not in (Token.T_GROUPING, Token.T_ARGLIST):
            raise ParseError(token, "expected arglist")

        arglist = token.children[1]
        arglist.type = Token.T_ARGLIST
        k = 0;
        while k < len(arglist.children):

            arg = arglist.children[k]

            if arg.type == Token.T_COMMA:
                arglist.children = arglist.children[:k] + arglist.children[k].children + arglist.children[k+1:] 
                continue

            if arg.type == Token.T_BINARY and arg.value==":":
                # fix the type annotation for this argument
                token.children[1].children[k] = arg.children[0]
                type_ = self.consume_type(arg.children, 0)
                anno = Token(Token.T_ANNOTATION, type_.line, type_.index, "", [type_])
                arg.children[0].children = [anno]

            # TODO: not clear what this does
            if arg.type == Token.T_LIST:
                arg.type = Token.T_UNPACK_SEQUENCE
            if arg.type == Token.T_GROUPING:
                arg.type = Token.T_UNPACK_OBJECT

            k += 1

        if body.type != Token.T_GROUPING:
            self._remove_special(tokens, index + 1)
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
        if ia is not None and tokens[ia].type == Token.T_KEYWORD and tokens[ia].value == 'async':
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
        rhs2 = self.consume_block(tokens, index)

        if (rhs1.type != Token.T_GROUPING):
            raise ParseError(token, "expected grouping")

        rhs1.type = Token.T_ARGLIST

        if len(rhs1.children) == 1:
            if rhs1.children[0].type == Token.T_TEXT:
                # self.warn(rhs1.children[0], Parser.W_UNSAFE_BOOLEAN_TEST)
                pass

        token.children = [rhs1, rhs2]
        token.type = Token.T_BRANCH

        # check for else
        i3 = self.peek_keyword(tokens, token, index, 1)
        if i3 is not None:
            tok3 = tokens[i3]
            if tok3.type != Token.T_KEYWORD or tok3.value != 'else':
                return

            # drop the else
            tok_else = tokens.pop(i3)

            # consume else block
            # this could be another if, or other control flow
            # or a block or single statement
            tok4 = self.consume_block(tokens, index)
            if not (tok4.type in (Token.T_GROUPING, Token.T_BLOCK) and tok4.value == '{}') and \
               not tok4.type == Token.T_BRANCH:
                j = self.peek_token(tokens, tok4, index, 1)
                if j is not None:
                    # catch what JS considers to be a specific syntax error
                    # be permissive, but warn that the allowed syntax is ambiguous.
                    if tokens[j].type == Token.T_GROUPING and tokens[j].value == "{}":
                        raise ParseError(tokens[j], "Unexpected {")
                    else:
                        print(tok_else.value, tok4.type, tok4.value, tokens[j].value)
                        self.warn(tok_else, Parser.W_ELSE_UNSAFE)
            token.children.append(tok4)

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

        rhs = self.consume_block(tokens, index)

        token.children = [rhs]
        token.type = Token.T_TRY

        i2 = self.peek_keyword(tokens, token, index, 1)

        while (i2 is not None and tokens[i2].type == Token.T_CATCH):
            rhs1 = self.consume(tokens, token, index, 1) # catch
            rhs2 = self.consume_block(tokens, index)     # body

            rhs1.children.append(rhs2) # block body
            token.children.append(rhs1)
            i2 = self.peek_keyword(tokens, token, index, 1)

        if (i2 is not None and tokens[i2].type == Token.T_KEYWORD and tokens[i2].value == 'finally'):
            rhs1 = self.consume_keyword(tokens, token, index, 1)
            rhs2 = self.consume_block(tokens, index)
            rhs1.children.append(rhs2)
            rhs1.type = Token.T_FINALLY
            token.children.append(rhs1)

    def collect_keyword_var(self, tokens, index):

        token = tokens[index]
        if index + 1 < len(tokens):
            rhs = tokens.pop(index + 1)
        else:
            if token.value == "type":
                return
            else:
                raise ParseError(token, "expected rhs")
        token.children = [rhs]
        token.type = Token.T_VAR

        if rhs.type == Token.T_COMMA:
            nodes = [rhs]
            while nodes:
                tmp = nodes.pop(0)
                for i, child in enumerate(tmp.children):
                    if child.type == Token.T_COMMA:
                        nodes.append(child)
                    if child.type == Token.T_BINARY and child.value==":":
                        child.type = Token.T_ANNOTATION
                        child.value = ""
                        tmp2 = child.children.pop(0)
                        tmp2.children.append(child)
                        tmp.children[i] = tmp2

        if token.value == "type":
            token.type = Token.T_TYPE

    def collect_keyword_while(self, tokens, index):

        token = tokens[index]
        rhs1 = self.consume(tokens, token, index, 1)
        rhs2 = self.consume_block(tokens, index)

        if (rhs1.type != Token.T_GROUPING):
            raise ParseError(token, "expected grouping")
        else:
            rhs1.type = Token.T_ARGLIST

        token.children = [rhs1, rhs2]
        token.type = Token.T_WHILE

    def _remove_special(self, tokens, index):

        while index < len(tokens) and tokens[index].type == Token.T_SPECIAL and tokens[index].value == ';':
            tokens.pop(index)

def main():  # pragma: no cover

    # TODO: if (true) {x=1;} + 1
    #       this gives an odd error message
    #       expected object but the error is because of the parent node

    text1 = "try {x} catch (e) {e} finally {z}"
    text1 = "import module foo.bar"
    text1 = "from module foo import {bar}"
    text1 = "if (true) {x=1;} + 1"
    text1 = "x?.[0]"
    text1 = "export let x=1,y=2"
    text1 = "0xfor"

    text1 = "x : a | x" # special case, should be an error...
    text1 = "let add: (obj: int) => void" # requires special handling in type annotation visitor
    text1 = "let x : int = 0, y : int, z"
    text1 = "let x : string"
    text1 = "let x : void => void"
    text1 = "let x : (name: string) => void"
    text1 = "function f(x: string){}"
    text1 = "function f(x: int): int {}"
    text1 = "function f(x: a=>b): a=>b {}"
    text1 = "let x : List[int] | List[float]"
    text1 = "interface Point {x: int, y: int}"
    text1 = "class Point {x: int y: int}"
    text1 = """ a=x?b=y:c=z """  # challenge 13 breaks types
    text1 = """ const b : int = a ? 1 : 2, c  b+= 1"""
    text1 = """ x = {x : null} """
    text1 = """ type Foo = (()=>void) | Set[int] """
    text1 = "let f = (x: int) : int => x"
    text1 = "function f<T>(arg: T) : T { return arg }"
    text1 = "type x = <G>(arg: T) => H"
    text1 = "x = 1e-6"

    # TODO: types should have a T_ANNOTATION with a single child, the type information
    text1 = "function f<T>(arg: T) : T { return arg }"
    text1 = "export * from e"
    text1 = """obj = {["fun"](){}, b:c}"""
    text1 = """x = "\\U0001f441" """
    text1 = """from module x import {a=b, c}"""
    text1 = """pyimport ...os.path {a=b, c}"""
    text1 = """class A { #priv; } const instance = new A(); a.#priv"""
    text1 = """
    function add(x: number, y: number): number {
                return x + y;
            }

    """
    # defining an object with numerical functions works in firefox
    text1 = """ let _ = {0x2 () {return 2}} """
    text1 = """
        //from module engine import {Application as App}
        //$import("engine")
        //$import("engine", {Application as App})
        include './foo.js'
        $include('./foo.js')
        """



    text1 = "if (true) {} else 4 {}"
    text1 = "if (true)\n {\n} \nelse \n{\n}"
    text1 = "type T = {x:number, y:number}"

    text1 = """

    $import("./a", {a,b,C as c})
    import { a, b, C as c } from "./a"

    import * from "./a"
    //export a, b

    //$import("./a", {a, b, c as d})
    //export a, b, c

    //export { a, b, c } from "./a";




    """

    text1 = """

        $import("daedalus", {})
        import {} from "@daedalus/daedalus"

        export {a,b,c}

        export {a,b,c} from "@daedalus/daedalus"

        export * from "./daedalus.js"
        $include("./a.js")

        import {} from "./daedalus.js"
    """

    text1 = """

    export function fn(x:number,x:number,x:number) {}

    """
    text1 = """

    // everything within < and > must describe a valid type
    // if a semicolon is found, or certain expression (&&, ||)
    // then the search can end
    // if a pair is found, and it parses to a valid type
    // then that pair represents a generic type def
    // otherwise it should not be consumed
    // this creates the first branch in the parser
    // that may not resolve to anything

    //let x = 1 < 2 && 3 > 2
    //let list: Array<number> = [1, 2, 3];
    //let result = fn<number>(213)
    //function first<T>(x : T[]) : T | undefined { return x[] }

    //function fn<Type, Key extends keyof Type>(obj: Type, key: Key){}

    //let x = a < 3 & c > 4

    //let x : fn<int>()

    export a from b

    """

    #text1 = "(x:int): int => x"
    print("="* 79)
    print(text1)
    print("="* 79)

    tokens = Lexer({'preserve_documentation': True}).lex(text1)
    mod = Parser().parse(tokens)

    print(mod.toString(3, pad=". "))

if __name__ == '__main__':  # pragma: no cover
    main()


