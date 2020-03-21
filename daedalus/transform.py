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

class TransformRemoveSemicolons(TransformBase):

    def visit(self, token, parent):

        i = 0
        while i < len(token.children):
            child = token.children[i]
            if child.type == Token.T_SPECIAL and child.value == ';':
                token.children.pop(i)
            else:
                i += 1

class TransformGrouping(TransformBase):

    def visit(self, token, parent):
        """
        transform any remaining instances of GROUPING{}
        many will be transformed as part of collecting various keywords

        """


        for child in token.children:

            if child.type == Token.T_GROUPING and child.value == "{}":
                if (token.type == Token.T_MODULE) or \
                   (token.type == Token.T_ANONYMOUS_FUNCTION) or \
                   (token.type == Token.T_ANONYMOUS_GENERATOR) or \
                   (token.type == Token.T_ASYNC_GENERATOR) or \
                   (token.type == Token.T_ASYNC_ANONYMOUS_GENERATOR) or \
                   (token.type == Token.T_STATIC_METHOD) or \
                   (token.type == Token.T_METHOD) or \
                   (token.type == Token.T_CLASS) or \
                   (token.type == Token.T_BLOCK) or \
                   (token.type == Token.T_FINALLY) or \
                   (token.type == Token.T_LAMBDA) or \
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
            return TransformError(token, "expected grouping")

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
           (t == Token.T_SPREAD) or \
           (t == Token.T_BINARY and (v == ':')) or \
           (t == Token.T_COMMA):
            return None

        return TransformError(token, "expected object")

class TransformFlatten(TransformBase):

    def visit(self, token, parent):
        # TODO: remove square bracket type from this and add T_UNPACK_SEQUENCE
        if token.type == Token.T_GROUPING and not (token.value == "()" or token.value == "[]"):
            # either a {} block was incorrectly parsed
            # or a [] block was not labeled list of subscr
            raise TokenError(token, "invalid grouping node: " + token.value)

        if token.type == Token.T_OBJECT or \
           token.type == Token.T_ARGLIST or \
           token.type == Token.T_LIST or \
           token.type == Token.T_UNPACK_SEQUENCE or \
           token.type == Token.T_GROUPING:

            chlst = token.children
            index = 0
            while index < len(chlst):
                if chlst[index].type == Token.T_COMMA:
                    child = chlst.pop(index)
                    for j in range(len(child.children)):
                        chlst.insert(index + j, child.children[j])
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
                                Token(Token.T_LAMBDA, ln, idx, "=>", [
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
        varname = text[s + 2:e]

        if varname not in vars:
            sys.stderr.write("warning: unable to find stylesheet variable: %s\n" % varname)
            return None

        text = text[:s] + vars[varname] + text[e + 1:]

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
            # prevent writing the resulting token to javascript
            # if it does not have any side effects. usually the side
            # effect is simply writing to the style sheet
            keep = parent.type in (Token.T_MODULE, Token.T_BLOCK)
            return self._extract_stylesheet_with_selector(style_name, token, arg0, arg1, keep)

        else:
            return False

    def _extract_stylesheet_with_selector(self, style_name, token, selector, obj, keep):
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
            selector_text = ast.literal_eval('"' + selector.value[1:-1] + '"')
            selector_text = shell_format(selector_text, self.named_styles)

        if not selector_text:
            return False

        style = self._object2style(selector_text, obj)
        self.styles.append(style)

        name = "dcs-%s-%d" % (self.uid, self.style_count)
        self.style_count += 1

        token.type = Token.T_EMPTY_TOKEN if keep else Token.T_STRING
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


SC_GLOBAL   = 0x001
SC_FUNCTION = 0x002
SC_BLOCK    = 0x004
SC_CONST    = 0x100

def scope2str(flags):
    text = ""

    if flags & SC_CONST:
        text += "const "

    if flags & SC_GLOBAL:
        text += "global"

    elif flags & SC_FUNCTION:
        text += "function"

    else:
        text += "block"

    return text

class Ref(object):

    def __init__(self, flags, label):
        super(Ref, self).__init__()
        self.flags = flags
        self.label = label

    def identity(self):
        raise NotImplementedError()

    def clone(self, scflags):
        raise NotImplementedError()

    def type(self):
        return Token.T_GLOBAL_VAR if self.flags & SC_GLOBAL else Token.T_LOCAL_VAR

    def isGlobal(self):
        return self.flags & SC_GLOBAL

    def __str__(self):
        return "<*%s>" % (self.identity())

    def __repr__(self):
        return "<*%s>" % (self.identity())


class PythonRef(Ref):
    def __init__(self, scflags, label):
        super(PythonRef, self).__init__(scflags, label)
        self._identity = 0

    def identity(self):
        s = 'f' if self.flags & SC_FUNCTION else 'b'
        return "%s#%s%d" % (self.label, s, self._identity)

    def clone(self, scflags):
        ref = PythonRef(scflags, self.label)
        ref._identity = self._identity + 1
        return ref

class MinifyRef(Ref):
    def __init__(self, scflags, label, outLabel):
        super(MinifyRef, self).__init__(scflags, label)
        self.outLabel = outLabel

    def identity(self):
        return self.outLabel

    def clone(self, scflags):
        return MinifyRef(scflags, self.label, self.outLabel)

class UndefinedRef(Ref):
    def identity(self):
        return self.label

DF_IDENTIFIER = 1
DF_FUNCTION   = 2
DF_CLASS      = 3

class VariableScope(object):
    # require three scope instances, for global, function and block scope
    def __init__(self, name, parent=None):
        super(VariableScope, self).__init__()
        self.name = name
        self.parent = parent

        # freevars, and cellvars are all mappings of:
        #   identifier -> ref

        # freevars are identifiers defined in a parent scope
        # that are used in this or a child scope
        self.freevars = set()
        # cellvars are identifiers defined in this scope used
        # by a child scope
        self.cellvars = set()

        # vars are identifiers defined in this scope
        self.vars = set()

        # mappings of identifier -> ref, of variables defined
        # in this scope but split into their correct function
        # or block scope.
        self.gscope = {}        # undefined global vars that are read / updated
        self.fnscope = {}
        self.blscope = [{}]
        self.all_labels = set()
        self.all_identifiers = set()

        if parent:
            self.depth = parent.depth + 1
        else:
            self.depth = 0

    def _getScope(self, scflags):

        if scflags & SC_GLOBAL:
            scope = self
            while scope.parent is not None:
                scope = scope.parent
            return scope.fnscope, None
        elif scflags & SC_FUNCTION:
            return self.fnscope, None
        else:
            if not self.blscope:
                return self.fnscope, None
            return self.blscope[-1], self.fnscope

    def _getRef(self, scope, label):

        ref = None

        if not scope:
            return ref

        for mapping in reversed(scope.blscope):
            if label in mapping:
                ref = mapping[label]
                break

        if ref is None and label in scope.fnscope:
            ref = scope.fnscope[label]

        return ref

    def _createRef(self, scflags, label, type_):
        return PythonRef(scflags, label)

    def _define_block(self, token):
        label = token.value

        if label in self.blscope[-1]:
            raise TokenError(token, "already defined at scope %s" % self.name)

        for bl in reversed(self.blscope):
            if label in bl:
                return bl[label]

        return None

    def _define_function(self, token):
        label = token.value

        if label in self.fnscope:
            return self.fnscope[label]

        return None

    def _define_impl(self, scflags, token, type_):

        if token.type not in (Token.T_TEXT, ):
            raise TokenError(token, "unexpected token type %s" % token.type)
        if not token.value:
            raise TokenError(token, "empty identifier for %s %d %s" % (token.type, token.line, token.file))
        label = token.value

        if scflags & SC_FUNCTION:
            ref = self._define_function(token)
        else:
            ref = self._define_block(token)

        if self.parent is None:
            scflags |= SC_GLOBAL

        if ref is not None:
            # define, but give a new identity
            new_ref = ref.clone(scflags)
        else:
            new_ref = self._createRef(scflags, label, type_)

        identifier = new_ref.identity()

        self.all_labels.add(label)
        self.all_identifiers.add(identifier)

        self.vars.add(identifier)

        if scflags & SC_FUNCTION:
            self.fnscope[label] = new_ref
        else:
            if len(self.blscope) == 0:
                raise TokenError(token, "block scope not defined")
            self.blscope[-1][label] = new_ref

        token.value = identifier
        if token.type == Token.T_TEXT:
            token.type = new_ref.type()

        # print("define name", self.depth, token.value, token.line, scope2str(scflags), self.name)


        return new_ref

    def _load_store(self, token, load):

        label = token.value
        ref = None

        # search for the scope the defines this label
        scopes = [self]
        while scopes[-1] is not None:
            if label in scopes[-1].fnscope:
                break

            if any([label in bl for bl in scopes[-1].blscope]):
                break

            # TODO: maybe replace above with this?
            #if label in scopes[-1].all_labels:
            #    break

            scopes.append(scopes[-1].parent)

        if scopes[-1] is None:
            # not found in an existing scope
            if load:
                # attempting to load an undefined reference
                if label in self.all_labels:
                    raise TokenError(token, "read from deleted var")

                ref = UndefinedRef(0, label)
                token.type = Token.T_GLOBAL_VAR
                self.gscope[label] = ref
            else:
                # define this reference in this scope
                ref = self.define(SC_BLOCK, token)

            if ref is None:
                raise TokenError(token, "identity error (1) in %s" % self.name)

        elif scopes[-1] is not self:
            # found in a parent scope
            scope = scopes[-1]

            ref = self._getRef(scope, label)

            if not ref.isGlobal():
                token.type = Token.T_FREE_VAR
                scope.cellvars.add(ref.identity())
                for scope2 in scopes[:-1]:
                    scope2.freevars.add(ref.identity())

            if ref is None:
                raise TokenError(token, "identity error (2) in %s" % self.name)
        else:
            ref = self._getRef(self, label)

            if ref is None:
                raise TokenError(token, "identity error (3) in %s" % self.name)

        token.value = ref.identity()
        if token.type == Token.T_TEXT:
            token.type = ref.type()

        # print("load__" if load else "store_", "name", self.depth, token.value, scope2str(ref.flags))

        return ref

    def define(self, scflags, token, type_=DF_IDENTIFIER):

        try:
            return self._define_impl(scflags, token, type_)
        except TokenError as e:
            scope = self
            while scope:
                print("-" * 50)
                print(scope.name)
                print(scope.all_labels)
                print(scope.freevars)
                print(scope.cellvars)
                print(scope.fnscope.keys())
                print([list(bl.keys()) for bl in scope.blscope])
                scope = scope.parent

            raise e

    def load(self, token):

        try:
            return self._load_store(token, True)
        except TokenError as e:
            scope = self
            while scope:
                print("-" * 50)
                print(scope.name)
                print(scope.all_labels)
                print(scope.freevars)
                print(scope.cellvars)
                print(scope.fnscope.keys())
                print([list(bl.keys()) for bl in scope.blscope])
                scope = scope.parent
            raise e

    def store(self, token):

        try:
            return self._load_store(token, False)
        except TokenError as e:
            scope = self
            while scope:
                print("-" * 50)
                print(scope.name)
                print(scope.all_labels)
                print(scope.freevars)
                print(scope.cellvars)
                print(scope.fnscope.keys())
                print([list(bl.keys()) for bl in scope.blscope])
                scope = scope.parent
            raise e

    def pushBlockScope(self):
        self.blscope.append({})

    def popBlockScope(self):
        return self.blscope.pop()

    def flattenBlockScope(self):
        out = {}
        for scope in self.blscope:
            out.update(scope)
        return out

    def _diag(self, token):
        print("%10s" % token.type, list(self.vars), list(self.freevars), list(self.cellvars))

class MinifyVariableScope(VariableScope):

    def __init__(self, name, parent=None):
        super(MinifyVariableScope, self).__init__(name, parent)
        self.label_index = 0
        self.class_counter = 0
        self.alphabetL = 'abcdefghijklmnopqrstuvwxyz'
        self.alphabetU = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
        self.alphabet1 = self.alphabetL + self.alphabetU + '0123456789'

    def _createRef(self, scflags, label, type_):
        return MinifyRef(scflags, label, self.nextLabel(type_))

    def nextLabel(self, type_):
        c = ""

        if type_ == DF_CLASS:
            # closure compiler can detect duplicate class names even
            # in different scopes. use the parent scope to keep track
            # of unique names
            scope = self.parent
            while scope.parent is not None:
                scope = scope.parent
            c = 'C' + str(scope.class_counter)
            scope.class_counter += 1
            return c
        else:
            while True:
                n = self.label_index
                self.label_index += 1

                c = 'i' + str(n)

                # ensure this new label does not appear in a parent scope
                found = False
                scope = self.parent
                while scope is not None:
                    if c in scope.all_identifiers:
                        found = True
                        break
                    scope = scope.parent

                if not found:
                    break
            return c

ST_MASK     = 0x000FF
ST_SCOPE_MASK     = 0xFFF00
ST_VISIT    = 0x001
ST_FINALIZE = 0x002
ST_STORE    = 0x100
ST_GLOBAL   = SC_GLOBAL << 12
ST_FUNCTION = SC_FUNCTION << 12
ST_BLOCK    = SC_BLOCK << 12
ST_CONST    = SC_CONST << 12


isConstructor = lambda token: token.type == Token.T_METHOD and token.children[0].value == "constructor"
isFunction = lambda token: token.type in (
            Token.T_FUNCTION,
            Token.T_GENERATOR,
            Token.T_ASYNC_GENERATOR,
            Token.T_METHOD,
            Token.T_STATIC_METHOD,
            Token.T_ANONYMOUS_FUNCTION,
            Token.T_ASYNC_ANONYMOUS_FUNCTION,
            Token.T_ANONYMOUS_GENERATOR,
            Token.T_ASYNC_ANONYMOUS_GENERATOR,
            Token.T_LAMBDA,
    )
isAnonymousFunction = lambda token: token.type in (
            Token.T_ANONYMOUS_FUNCTION,
            Token.T_ASYNC_ANONYMOUS_FUNCTION,
            Token.T_ANONYMOUS_GENERATOR,
            Token.T_ASYNC_ANONYMOUS_GENERATOR,
            Token.T_LAMBDA,
    )
class TransformAssignScope(object):

    """
    Assign scoping rules to variables

    this performs all necessary transformations for converting an
    acceptable JS AST into a Python AST.

    var: function scoped
    let: block scoped
    const: block scoped

    Variable Hoisting

        Hoisting can be implemented by automatically detecting variables
        used before they are defined and inserting a node at the top
        of the scope that initializes the variable to undefined

        Hoisting variables contradicts the variable resolution rules of
        python.

        Example:

            globals()['foo'] = 123
            print(foo)  # prints 123

        Note:
            modifying locals() directly has undefined behavior

        Hoisting to the top of the scope can only done if within that
        scope a var/let/const keyword is found otherwise the compiler
        must assume that the variable has global scope. At runtime
        python will determine if the variable is defined

    Name Mangling

        variables declared with let are block scoped. To allow for
        overlapping definitions in sub blocks of the same module or function
        scope the variables must be tagged. Python variables can contain
        any string. The tag is a pound sign followed by a counter
        for the block depth.

        Any attempt at loading or storing a variable after the definition
        will replace the token value with a tagged token value

        Example 1:

            Javascript source   => Transformed JS      => Python
            let x = 1           =>  let x = 1          => x = 1
            {                   =>  {                  => x#1 = 2
              let x = 2;        =>    let x#1 = 2;     => print(x#1)
              console.log(x)    =>    console.log(x#1) => del x#1
            }                   =>  }                  => print(x)
            console.log(x)      =>  console.log(x)     =>

        Output:
            > 2
            > 1

        Example 2:

            var x = 1;          =>      var x = 1;                // GLOBAL
            function main() {   =>      function main() {
              var x = 2         =>        var x = 2               // FAST
              console.log(x);   =>        console.log(x);         // FAST
            }                   =>      }
            main()              =>      main()
            console.log(x)      =>      console.log(x)            // GLOBAL

        Output:
            > 2
            > 1

        Note:
            deleting the local variable may not be required.
            it cannot be done in an exception safe way.

    Block Scoping

        At the end of a block a node is inserted to delete any variable
        defined within that block

        Variables defined using let or const are block scoped

        Example 1:
            {                   =>      {
              let x = 2;        =>        let x = 2;
                                =>        del x
            }                   =>      }
            console.log(x)      =>      console.log(x)  // x is undefined here

    Function Scoping

        a variable that is function scope means it is available in any
        child scope of that function. To support this any function def
        should be explored after the current function scope is completed.

        Todo: this is currently broken by the transform engine

        Example 1:
            function f1() {
              return f2() + 1
            }
            function f2() {
              return 2
            }
            console.log(f1())

        Example 2
            {

              function f1() {
                return x
              }
              let x= 1

            }

            console.log(f1())


    Variable Scoping

        No special transformation is needed in python to support var

        Variables defined using var are function scoped



    Misc:

        legal:
            var x=1;
            {
                let x=2
            }

            var x=1;
            {
                var x=2
            }

        illegal:
            let x=1;
            {
                var x=2
            }

            let x=1;
            {
                let x=2
            }

        illegal:
            const x = 1
            const x = 2

            const x = 1
            x = 2

    TODO:
        = and variants must have a unique token type T_VARIALE_ASSIGMENT

    """

    def __init__(self):
        super(TransformAssignScope, self).__init__()

        # discover the variable scope if a mode friendly
        # to python (true) or javascript (false)
        self.python = True

        self.global_scope = None

        self.visit_mapping = {
            Token.T_FUNCTION: self.visit_function,
            Token.T_GENERATOR: self.visit_function,
            Token.T_ASYNC_GENERATOR: self.visit_function,
            Token.T_METHOD: self.visit_function,
            Token.T_STATIC_METHOD: self.visit_function,

            Token.T_ANONYMOUS_FUNCTION: self.visit_anonymous_function,
            Token.T_ASYNC_ANONYMOUS_FUNCTION: self.visit_anonymous_function,
            Token.T_ANONYMOUS_GENERATOR: self.visit_anonymous_function,
            Token.T_ASYNC_ANONYMOUS_GENERATOR: self.visit_anonymous_function,

            Token.T_LAMBDA: self.visit_lambda,

            Token.T_ASSIGN: self.visit_assign,
            Token.T_BLOCK: self.visit_block,
            Token.T_MODULE: self.visit_module,
            Token.T_TEXT: self.visit_text,
            Token.T_VAR: self.visit_var,
            Token.T_OBJECT: self.visit_object,
            Token.T_BINARY: self.visit_binary,
            Token.T_PYIMPORT: self.visit_pyimport,
            Token.T_EXPORT: self.visit_export,
            Token.T_UNPACK_SEQUENCE: self.visit_unpack_sequence,
            Token.T_FOR: self.visit_for,

            # method and class are added, but when compiling a
            # python module we assume a transform has already been
            # run to remove methods and classes
            Token.T_CLASS: self.visit_class,


            # Token.T_GROUPING: self.visit_error,
        }

        self.finalize_mapping = {

            Token.T_FUNCTION: self.finalize_function,
            Token.T_GENERATOR: self.finalize_function,
            Token.T_ASYNC_GENERATOR: self.finalize_function,
            Token.T_METHOD: self.finalize_function,
            Token.T_STATIC_METHOD: self.finalize_function,

            Token.T_ANONYMOUS_FUNCTION: self.finalize_function,
            Token.T_ASYNC_ANONYMOUS_FUNCTION: self.finalize_function,
            Token.T_ANONYMOUS_GENERATOR: self.finalize_function,
            Token.T_ASYNC_ANONYMOUS_GENERATOR: self.finalize_function,

            Token.T_LAMBDA: self.finalize_function,

            Token.T_BLOCK: self.finalize_block,
            Token.T_MODULE: self.finalize_module,

        }

        self.states = {
            ST_VISIT: self.visit_mapping,
            ST_FINALIZE: self.finalize_mapping
        }

        self.state_defaults = {
            ST_VISIT: self.visit_default,
            ST_FINALIZE: self.finalize_default,
        }

        # mapping identifier -> identifier
        # giving the original identifier for a global variable
        # and the new name after applying the transform
        self.globals = {}

    def newScope(self, name, parentScope=None):
        return VariableScope(name, parentScope)

    def transform(self, ast):

        self.seq = [self.initialState(ast)]

        self._transform(ast)

    def _transform(self, token):

        while self.seq:
            # process tokens from in the order they are discovered. (DFS)
            flags, scope, token, parent = self.seq.pop()

            fn = self.states[flags & ST_MASK].get(token.type, None)

            if fn:
                fn(flags, scope, token, parent)

            else:
                fn = self.state_defaults[flags & ST_MASK]
                fn(flags, scope, token, parent)

    def initialState(self, token):

        return (ST_VISIT, self.newScope('__main__'), token, None)

    # -------------------------------------------------------------------------

    def visit_default(self, flags, scope, token, parent):

        self._push_children(scope, token, flags)

    def visit_error(self, flags, scope, token, parent):
        raise TokenError(token, "invalid token")

    def visit_module(self, flags, scope, token, parent):
        self._push_finalize(scope, token, parent)
        self._push_children(scope, token, flags)

    def visit_block(self, flags, scope, token, parent):

        if isFunction(parent):
            # this should never happen
            raise TransformError(parent, "visit block for function not allowed")

        scope.pushBlockScope()

        self._push_finalize(scope, token, parent)
        self._push_children(scope, token, flags)

    def _handle_function(self, flags, scope, token, parent):

        scflags = (flags & ST_SCOPE_MASK) >> 12

        # define the name of the function when it is not an
        # anonymous function and not a class constructor.
        if not isAnonymousFunction(token) and not isConstructor(token):
            scope.define(scflags, token.children[0])

        name = scope.name + "." + token.children[0].value
        next_scope = self.newScope(name, scope)

        # finalize the function scope once all children have been processed
        self._push_finalize(next_scope, token, parent)

        if token.children[2].type != Token.T_BLOCK:
            # the parser should be run in python mode
            raise TransformError(token.children[2], "expected block in for loop body")

        self._push_children(next_scope, token.children[2])

        for child in reversed(token.children[1].children):
            if child.type == Token.T_ASSIGN:
                # tricky, the rhs is a variable in THIS scope
                # while the lhs is a variable in the NEXT scope
                lhs, rhs = child.children
                next_scope.define(SC_FUNCTION, lhs)
                self._push_tokens(ST_VISIT, scope, [rhs], child)
            elif child.type == Token.T_SPREAD:
                tok, = child.children
                next_scope.define(SC_FUNCTION, tok)
            else:
                next_scope.define(SC_FUNCTION, child)

    def visit_function(self, flags, scope, token, parent):

        self._handle_function(flags, scope, token, parent)

    def visit_anonymous_function(self, flags, scope, token, parent):

        self._handle_function(flags, scope, token, parent)

    def visit_lambda(self, flags, scope, token, parent):


        # lambdas allow for no arglist, but that makes compiling harder

        # fix some js-isms that are not really valid python
        if self.python:
            if token.children[1].type == Token.T_TEXT:
                tok = token.children[1]
                token.children[1] = Token(Token.T_ARGLIST, tok.line, tok.index, '()', [tok])

            # lambdas can be a single expression if it returns a value
            if token.children[2].type != Token.T_BLOCK:
                tok = token.children[2]

                token.children[2] = Token(Token.T_BLOCK, tok.line, tok.index, '{}',
                    [Token(Token.T_RETURN, tok.line, tok.index, 'return', [tok])])

        self._handle_function(flags, scope, token, parent)

    def visit_class(self, flags, scope, token, parent):

        """
        this method is implemented only for the case when minifying javascript
        """
        scflags = (flags & ST_SCOPE_MASK) >> 12
        scope.define(scflags, token.children[0], DF_CLASS)

        # load the class name(s) this class extends from
        if len(token.children[1].children) > 0:
            self._push_tokens(flags, scope, token.children[1].children, token.children[1])
            #for child in token.children[1].children:
            #    scope.load(child)

        name = scope.name + "." + token.children[0].value
        next_scope = self.newScope(name, scope)

        #for child in token.children[2].children:
        #    next_scope.define(SC_FUNCTION, child)
        self._push_children(next_scope, token.children[2], flags)

    def visit_var(self, flags, scope, token, parent):
        flags = 0
        if token.value == 'var':
            flags = ST_FUNCTION
        if token.value == 'let':
            flags = ST_BLOCK
        if token.value == 'const':
            flags = ST_BLOCK | ST_CONST
        self._push_children(scope, token, flags)

    def visit_assign(self, flags, scope, token, parent):

        # TODO: LHS can be more complicated that T_TEXT
        if token.value == "=":
            self._push_tokens(ST_VISIT | ST_STORE | (flags & ST_SCOPE_MASK), scope, [token.children[0]], parent)
            self._push_tokens(ST_VISIT, scope, [token.children[1]], parent)

        else:
            self._push_children(scope, token, 0)

    def visit_text(self, flags, scope, token, parent):
        # note: this only works because the parser implementation of
        # let/var/const wonky. the keyword is parsed after the equals sign
        # and any commas

        scflags = (flags & ST_SCOPE_MASK) >> 12

        if scflags:
            scope.define(scflags, token)
        elif flags & ST_STORE:
            scope.store(token)
        else:
            scope.load(token)

    def visit_object(self, flags, scope, token, parent):

        # fix the js-ism for non key-value pairs
        # convert {foo} into {"foo": foo}
        # before the name mangling can take effect
        for i, child in enumerate(token.children):

            if child.type == Token.T_TEXT:

                key = Token(Token.T_STRING, child.line, child.index, repr(child.value))
                val = child

                tok = Token(Token.T_BINARY, child.line, child.index, ":",
                    [key, val])

                token.children[i] = tok

        self._push_children(scope, token, flags)

    def visit_binary(self, flags, scope, token, parent):
        """
        The LHS of a slice operator inside an object definition
        can be a identifier. convert the value into a string
        """
        self._push_children(scope, token, flags)

        if token.value != ":":
            return

        if not parent or parent.type != Token.T_OBJECT:
            return

        # handle the case where :: {foo: 0}
        if token.children[0].type == Token.T_TEXT:
            token.children[0].type = Token.T_STRING
            token.children[0].value = repr(token.children[0].value)

    def visit_pyimport(self, flags, scope, token, parent):

        scflags = (flags & ST_SCOPE_MASK) >> 12

        # the imported variable name
        if token.children[0].value:
            scope.define(scflags, token.children[0])

        # for each value in the fromlist
        for argtoken in token.children[2].children:
            scope.define(scflags, argtoken)

    def visit_export(self, flags, scope, token, parent):

        # don't reverse
        new_flags = (ST_VISIT | (flags & ST_SCOPE_MASK))
        for child in token.children:
            self.seq.append((new_flags, scope, child, token))

    def visit_unpack_sequence(self, flags, scope, token, parent):
        scflags = (flags & ST_SCOPE_MASK) >> 12

        #for child in token.children:
        #    scope.store(child)
        self._push_children(scope, token, flags)

    def visit_for(self, flags, scope, token, parent):
        """
        for a C-Style for loop process the argument list
        as if it was inside the body of the loop.

        this allows for two consecutive loops to define the same
        iteration variable as const or with let
        """

        arglist, body = token.children

        if body.type != Token.T_BLOCK:
            # the parser should be run in python mode
            raise TransformError(body, "expected block in for loop body")

        scope.pushBlockScope()

        self._push_children(scope, body, flags)
        self._push_children(scope, arglist, flags)

    # -------------------------------------------------------------------------

    def finalize_default(self, flags, scope, token, parent):
        pass

    def finalize_module(self, flags, scope, token, parent):

        if scope.cellvars or scope.freevars:
            raise TokenError(token, "unexpected closure")

        self.globals = {}
        for name, ref in scope.gscope.items():
            self.globals[name] = ref.identity()
        for name, ref in scope.fnscope.items():
            self.globals[name] = ref.identity()
        for name, ref in scope.blscope[0].items():
            self.globals[name] = ref.identity()

    def finalize_block(self, flags, scope, token, parent):

        print(scope.flattenBlockScope())

        vars = scope.popBlockScope()

        if self.python:
            for var in vars.values():
                token.children.append(Token(Token.T_DELETE_VAR, token.line, token.index, var.identity()))

    def finalize_function(self, flags, scope, token, parent):

        if self.python:
            closure = Token(Token.T_CLOSURE, 0, 0, "")

            for name in sorted(scope.cellvars):
                closure.children.append(Token(Token.T_CELL_VAR, 0, 0, name))

            for name in sorted(scope.freevars):
                closure.children.append(Token(Token.T_FREE_VAR, 0, 0, name))

            token.children.append(closure)

    # -------------------------------------------------------------------------

    def _push_finalize(self, scope, token, parent, flags=0):
        self.seq.append((ST_FINALIZE | flags, scope, token, parent))

    def _push_children(self, scope, token, flags=0):
        for child in reversed(token.children):
            self.seq.append((ST_VISIT | (flags & ST_SCOPE_MASK), scope, child, token))

    def _push_tokens(self, flags, scope, tokens, parent):

        for token in reversed(tokens):
            self.seq.append((flags, scope, token, parent))
    # -------------------------------------------------------------------------

    def _define(self, scope, token, flag):
        # flag: ST_BLOCK, ST_FUNCTION, ST_GLOBAL
        pass

    def _load(self, scope, token):
        pass

    def _store(self, scope, token):
        pass

class TransformMinifyScope(TransformAssignScope):
    """
    Minify javascript by intelligently renaming variables to shorter identifiers

    This is largely an experiment and does the renaming in a single pass.
    There could be a significant number of improvements

    - come up with better ways to encode the names in a single pass fashion
    - keep track of all scopes and wait to assign until the end
    - keep track of al references and sort by frequency
    - assign names based on frequency of store/load counts


    """
    def __init__(self):
        super(TransformMinifyScope, self).__init__()

        self.python = False

    def newScope(self, name, parentScope=None):
        return MinifyVariableScope(name, parentScope)

class TransformBaseV2(object):
    def __init__(self):
        super(TransformBaseV2, self).__init__()

    def transform(self, ast):

        self.scan(ast)

    def scan(self, token):

        tmp = Token(Token.T_SPECIAL, 0, 0, "", [token])
        tokens = [tmp]

        while tokens:
            # process tokens from in the order they are discovered. (DFS)
            token = tokens.pop()

            # visit each child in the order they appear
            # allow for the visit method to alter token.children
            index = 0
            while index < len(token.children):
                child = token.children[index]
                self.visit(token, child, index)
                index += 1

            # once every child has been visited push the available
            # children onto the stack to be processed

            for child in reversed(token.children):
                tokens.append(child)

    def visit(self, token, child, index):
        raise NotImplementedError()

class TransformClassToFunction(TransformBaseV2):
    """

    Given:
        class Shape() {
            constructor() {
                this.width = 5
                this.height = 5
            }

            area() {
                return this.width * this.height
            }
        }

    Transform into:

        function Shape() {
            this.area = () => { return this.width * this.height }

            this.width = 5
            this.height = 5

        }

    Use the constructor as a function body and insert arrow functions
    into the body of the function
    """

    def visit(self, token, child, index):

        if child.type == Token.T_CLASS:
            self.visit_class(token, child, index)

    def visit_class(self, parent, token, index):
        # TODO: implement inheritance

        name = token.children[0]
        extends = token.children[1]
        clsbody = token.children[2]

        constructor = None

        methods = []
        static_methods = []

        for child in clsbody.children:
            if child.type == Token.T_METHOD and child.children[0].value == 'constructor':
                constructor = child
            elif child.type == Token.T_STATIC_METHOD:
                static_methods.append(child)

            else:
                methods.append(child)

        if constructor is None:
            constructor = Token(Token.T_LAMBDA, 0, 0, '=>',
                    [Token(Token.T_TEXT, 0, 0, 'Anonymous'),
                    Token(Token.T_ARGLIST, 0, 0, '()'),
                    Token(Token.T_BLOCK, 0, 0, '{}')]
                )


        # process all static methods.
        # after the class method is defined, define new methods on
        # the created object by inserting statements that add the attribute
        # TODO: consider an IIFI for inline classes with static methods
        ln = token.line
        co = token.index
        for method in static_methods:
            var = Token(Token.T_BINARY, ln, co, '.', [
                Token(Token.T_TEXT, ln, co, name.value),
                Token(Token.T_ATTR, ln, co, method.children[0].value)
            ])
            # TODO: this function has a name, and probably shouldnt
            # be an anonymous function. the compiler would need to
            # support the ST_LOAD flag when creating a function otherwise.
            method.type = Token.T_ANONYMOUS_FUNCTION
            static = Token(Token.T_ASSIGN, ln, co, '=', [
                var,
                method
            ])
            parent.children.insert(index+1, static)
        print(static_methods)

        token.type = Token.T_FUNCTION
        token.value = 'function'
        token.children = []

        arglist = constructor.children[1]
        fnbody = constructor.children[2]

        for method in methods:
            anonfn = Token(Token.T_LAMBDA, token.line, token.index, "=>",
                [Token(Token.T_TEXT, token.line, token.index, 'Anonymous'),
                 method.children[1], method.children[2]])
            attr = Token(Token.T_BINARY, token.line, token.index, ".",
                [Token(Token.T_KEYWORD, token.line, token.index, "this"),
                 Token(Token.T_ATTR, token.line, token.index, method.children[0].value)])

            tok = Token(Token.T_ASSIGN, token.line, token.index, '=',
                [attr, anonfn])
            fnbody.children.insert(0, tok)

        token.children.append(name)
        token.children.append(arglist)
        token.children.append(fnbody)

def main_css():

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

def main_var():

    from .parser import Parser
    from tests.util import edit_distance
    text1 = """
    class Shape {
        constructor() {
            this.width = 5
            this.height = 10
        }
        area() {
            return this.width * this.height;
        }
    }
    """
    text2 = """

    function Shape() {
        this.area = () => {return this.width * this.height}
        this.width = 5
        this.height = 10
    }
    """

    tokens = Lexer().lex(text1)
    ast = Parser().parse(tokens)

    tokens = Lexer().lex(text2)
    ast2 = Parser().parse(tokens)

    lines1 = ast2.toString(3).split("\n")

    tr = TransformClassToFunction()
    tr.transform(ast)

    lines2 = ast.toString(3).split("\n")

    seq, cor, sub, ins, del_ = edit_distance(lines1, lines2, lambda x, y: x == y)
    print("")
    print("")
    print(len(lines1), len(lines2))
    print("")

    while len(lines1) < len(lines2):
        lines1.append("")

    while len(lines2) < len(lines1):
        lines2.append("")

    # for i, (l1, l2) in enumerate(zip(lines1, lines2)):
    for i, (l1, l2) in enumerate(seq):
        c = '=' if l1 == l2 else ' '
        print("%3d: %-40s %s %-40s" % (i + 1, l1, c, l2))

def main_var2():
    from .parser import Parser
    text = """

        {
            {

              function f1() {
                return x + y
              }

              let x= 1

              console.log(f1())
            }

            let y = 2;
        }
    """


    tokens = Lexer().lex(text)
    parser =  Parser()
    parser.python = True
    ast = parser.parse(tokens)

    #tr = TransformMinifyScope()
    tr = TransformAssignScope()
    tr.transform(ast)

    print(ast.toString(3))

def main_cls():
    from .parser import Parser
    text = """

    class C { static m() { return 123 } }
    return C.m()

    """

    tokens = Lexer().lex(text)
    ast = Parser().parse(tokens)


    tr = TransformClassToFunction()
    tr.transform(ast)

    print(ast.toString(3))

def labels():
    alphabetL = 'abcdefghijklmnopqrstuvwxyz'
    alphabetU = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    alphabet1 = alphabetL + alphabetU + '0123456789'


    for n in range(256):

        c = ""

        j = n & 0b1111
        c += alphabetL[j]

        n>>=4

        while n > 0:
            j = n & 0b11111
            c = alphabet1[j] + c
            n>>=5

        print(c)


if __name__ == '__main__':
    main_var2()
