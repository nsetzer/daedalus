#! cd .. && python3 -m daedalus.transform
import os
import sys
import io
import ast
import hashlib
from .lexer import Lexer, Token, TokenError

class TransformError(TokenError):
    pass

class TransformBase(object):
    def __init__(self):
        super(TransformBase, self).__init__()

    def transform(self, ast):

        self.scan(ast)

    def scan(self, token):

        tokens = [(token, token)]

        while tokens:
            # process tokens from in the order they are discovered. (DFS)
            token, parent = tokens.pop()

            self.visit(token, parent)

            for child in reversed(token.children):
                tokens.append((child, token))

    def visit(self, token, parent):
        raise NotImplementedError()

class TransformGrouping(TransformBase):

    def visit(self, token, parent):
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
                   (token.type == Token.T_FINALLY) or \
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


    def _isObject(self, token):
        # test if a token is an object, this is only valid
        # if the object contents have not been flattened

        if token.type != Token.T_GROUPING or token.value != "{}":
            return TransformError(token, "expected object")

        if len(token.children) > 1:
            # likely there is a missing comma
            # left-recursive drill down into the first non comma or colon
            # that is usually the first token after a missing comma
            child = token.children[1]
            while child.type == Token.T_COMMA or (child.type == Token.T_BINARY and child.value == ':'):
                child = child.children[0]
            return TransformError(child, "malformed object. maybe a comma is missing?")

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

        return TransformError(token, "expected object")

class TransformFlatten(TransformBase):

    def visit(self, token, parent):

        if token.type == Token.T_GROUPING and token.value != "()":
            # either a {} block was incorrectly parsed
            # or a [] block was not labeled list of subscr
            raise ParseError(token, "invalid grouping node: " + token.value)

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

            if token.type == Token.T_OBJECT:
                self._objectKeyFix(token)

    def _objectKeyFix(self, token):
        """
        Non-Standard Javascript feature

        The left-hand-side of an object literal must be a scalar value.
        Check for cases where binary operators are used to separate text
        values and merge them into a single string token

        example:
            {min-height:0} => {"min-height": 0}

        TODO: put this behind a feature flag
        """
        for pair in token.children:
            if pair.type == Token.T_BINARY and pair.value == ":":
                tok_key = pair.children[0]
                if tok_key.type == Token.T_BINARY:
                    text = ""
                    while tok_key.type == Token.T_BINARY:
                        text = tok_key.value + tok_key.children[1].value + text
                        tok_key = tok_key.children[0]
                    text = tok_key.value + text
                    # form a new token based on the original lhs attribute key
                    org = pair.children[0].clone(type=Token.T_STRING, value=repr(text), children=[])
                    pair.children[0] = org

class TransformOptionalChaining(TransformBase):

    def visit(self, token, parent):

        if token.type != Token.T_OPTIONAL_CHAINING:
            return

        # Implement optional chaining for attribute access
        #   x?.y :: ((x)||{}).y

        if len(token.children) == 2:

            token.type = Token.T_BINARY
            token.value = "."
            lhs, rhs = token.children
            ln = token.line
            idx = token.index

            token.children = [
            Token(Token.T_GROUPING, ln, idx, "()",
                [Token(Token.T_BINARY, ln, idx, "||",
                    [
                        Token(Token.T_GROUPING, ln, idx, "()", [lhs]),
                        Token(Token.T_OBJECT, ln, idx, "{}")
                    ]
                )]
            ), rhs]

        # Implement optional chaining for function calls
        #   x?.(...) :: ((x)||(()=>null))(...)

        if len(token.children) == 1 and token.children[0].type == Token.T_FUNCTIONCALL:
            token.type = Token.T_FUNCTIONCALL
            token.value = ""
            lhs, rhs = token.children[0].children
            ln = token.line
            idx = token.index

            token.children = [
            Token(Token.T_GROUPING, ln, idx, "()",
                [Token(Token.T_BINARY, ln, idx, "||",
                    [
                        Token(Token.T_GROUPING, ln, idx, "()", [lhs]),
                        Token(Token.T_GROUPING, ln, idx, "()", [
                                Token(Token.T_BINARY, ln, idx, "=>", [
                                    Token(Token.T_ARGLIST, ln, idx, "()"),
                                    Token(Token.T_KEYWORD, ln, idx, "null")
                                ])
                        ])
                    ]
                )]
            ), rhs]

        # Implement optional chaining for object subscript
        #   x?.[...] :: ((x)||{})[...]

        if len(token.children) == 1 and token.children[0].type == Token.T_SUBSCR:
            token.type = Token.T_SUBSCR
            token.value = "[]"
            lhs, rhs = token.children[0].children
            ln = token.line
            idx = token.index

            token.children = [
            Token(Token.T_GROUPING, ln, idx, "()",
                [Token(Token.T_BINARY, ln, idx, "||",
                    [
                        Token(Token.T_GROUPING, ln, idx, "()", [lhs]),
                        Token(Token.T_OBJECT, ln, idx, "{}")
                    ]
                )]
            ), rhs]

class TransformNullCoalescing(TransformBase):

    def visit(self, token, parent):

        """

        transform
            a ?? b
        into
            ((x,y)=>(x!==null&&x!==undefined)?x:y)(a,b)

        """

        if token.type != Token.T_BINARY and token.value != "??":
            return

class TransformMagicConstants(TransformBase):

    def visit(self, token, parent):

        """

        transform
            a ?? b
        into
            ((x,y)=>(x!==null&&x!==undefined)?x:y)(a,b)

        """

        if token.type != Token.T_TEXT:
            return

        if token.value == "__LINE__":
            token.type = Token.T_NUMBER
            token.value = str(token.line)

        if token.value == "__COLUMN__":
            token.type = Token.T_NUMBER
            token.value = str(token.index)

        if token.value == "__FILENAME__":

            if token.file:
                token.type = Token.T_STRING
                token.value = "'%s'" % os.path.split(token.file)[1]
            else:

                token.type = Token.T_STRING
                token.value = "'undefined'"

def shell_format(text, vars):

    pos = 0
    s = text.find("${", pos)
    e = text.find("}", pos)

    while s < e:
        varname = text[s+2:e]

        if varname not in vars:
            sys.stderr.write("warning: unable to find stylesheet variable: %s\n" % varname)
            return None

        text = text[:s] + vars[varname] + text[e+1:]

        pos = s
        s = text.find("${", pos)
        e = text.find("}", pos)
    return text

class TransformExtractStyleSheet(TransformBase):

    def __init__(self, uid):
        super(TransformExtractStyleSheet, self).__init__()

        self.style_count = 0
        self.styles = []
        self.uid = uid

        self.named_styles = {}

    def visit(self, token, parent):

        if token.type == Token.T_FUNCTIONCALL:
            child = token.children[0]
            if child.type == Token.T_TEXT and child.value == 'StyleSheet':
                rv = self._extract(token, parent)
                if not rv:
                    sys.stderr.write("warning: failed to convert style sheet\n")

    def _extract(self, token, parent):

        arglist = token.children[1]

        style_name = None
        if parent and parent.type == Token.T_BINARY and parent.value == ':':
            key = parent.children[0]
            if key.type == Token.T_STRING:
                style_name = 'style.' + ast.literal_eval(key.value)
            elif key.type == Token.T_TEXT:
                style_name = 'style.' + key.value

        if len(arglist.children) == 1:
            arg0 = arglist.children[0]

            if arg0.type != Token.T_OBJECT:
                return False

            return self._extract_stylesheet(style_name, token, arg0)

        elif len(arglist.children) == 2:
            arg0 = arglist.children[0]
            arg1 = arglist.children[1]

            return self._extract_stylesheet_with_selector(style_name, token, arg0, arg1)

        else:
            return False

    def _extract_stylesheet_with_selector(self, style_name, token, selector, obj):
        """
        TODO: only partial support for styles with selectors

        the selector must either be a literal string or a template string
        where variables are named 'style.<varname>'

        example:

            `${style.example}:hover`

        """

        selector_text = None
        if selector.type == Token.T_STRING:
            selector_text = ast.literal_eval(selector.value)
        elif selector.type == Token.T_TEMPLATE_STRING:
            selector_text = ast.literal_eval('"'+selector.value[1:-1]+'"')
            selector_text = shell_format(selector_text, self.named_styles)

        if not selector_text:
            return False

        style = self._object2style(selector_text, obj)
        self.styles.append(style)

        name = "dcs-%s-%d" % (self.uid, self.style_count)
        self.style_count += 1

        token.type = Token.T_STRING
        token.value = repr(selector_text)
        token.children = []

        return True

    def _extract_stylesheet(self, style_name, token, obj):

        try:
            # daedalus-compiled-style
            # TODO: may require a unique identifier
            # for the case of separately compiled files
            name = "dcs-%s-%d" % (self.uid, self.style_count)
            selector = "." + name
            style = self._object2style(selector, obj)
            self.styles.append(style)

            token.type = Token.T_STRING
            token.value = repr(name)
            token.children = []

            if style_name:
                self.named_styles[style_name] = name

            self.style_count += 1
        except TransformError as e:
            # the style is not trivial and cannot be processed
            return False

        return True

    def _object2style(self, selector, token):
        """ return a style rule for an object token """

        obj = self._object2style_helper("", token)
        # insert items in the order they were found in the document
        arr = ["  %s: %s;" % (k, v) for k, v in obj.items()]
        body = "\n".join(arr)
        return "%s {\n%s\n}" % (selector, body)

    def _object2style_helper(self, prefix, token):

        """compiles a javascript AST of an Object into a style sheet
        using the same rules as daedalus.StyleSheet
        """
        obj = {}
        for child in token.children:

            if child.type == Token.T_BINARY and child.value == ':':
                lhs, rhs = child.children

                lhs_value = None
                if lhs.type == Token.T_TEXT:
                    lhs_value = lhs.value
                elif lhs.type == Token.T_STRING:
                    lhs_value = ast.literal_eval(lhs.value)

                rhs_value = None
                if rhs.type == Token.T_TEXT:
                    rhs_value = rhs.value
                elif rhs.type == Token.T_STRING:
                    rhs_value = ast.literal_eval(rhs.value)
                elif rhs.type == Token.T_NUMBER:
                    rhs_value = rhs.value
                elif rhs.type == Token.T_OBJECT:

                    if lhs_value is not None:
                        obj.update(self._object2style_helper(prefix + lhs_value + "-", rhs))
                    else:
                        raise TransformError(lhs.type)
                    continue
                else:
                    raise TransformError(rhs, "invalid token1")

                if lhs_value:
                    obj[prefix + lhs_value] = rhs_value
                else:
                    raise TransformError(lhs, "invalid token2")

            else:
                raise TransformError(child, "invalid token3")

        return obj

    def getStyles(self):
        """ return a list of style rules """
        return self.styles

    @staticmethod
    def generateUid(text):
        m = hashlib.sha256()
        m.update(text.encode('utf-8'))
        return m.hexdigest()[:8]

def main():


    from .parser import Parser

    text1 = """
    const style = {
        test: StyleSheet({
            padding: '.25em',
            display: 'flex',
            border-bottom: {width: '1px', color: '#000000', 'style-x': 'solid'},
            flex-direction: 'column',
            justify-content: 'flex-start',
            'align-items': 'flex-begin',
        }),
    };
    StyleSheet(`${style.test}:hover`, {background: 'blue'})
    """


    tokens = Lexer().lex(text1)
    mod = Parser().parse(tokens)
    tr = TransformExtractStyleSheet('example')
    tr.transform(mod)
    print(tr.named_styles)
    print(mod.toString())
    print("\n".join(tr.getStyles()))

if __name__ == '__main__':
    main()