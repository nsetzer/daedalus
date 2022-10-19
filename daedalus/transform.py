#! cd .. && python3 -m daedalus.transform
import os
import sys
import io
import ast as py_ast
import operator
import hashlib
from .lexer import Lexer
from .token import Token, TokenError

class TransformError(TokenError):
    pass

def literal_eval(token):
    try:
        return py_ast.literal_eval(token.value)
    except SyntaxError as e:
        pass
    raise TransformError(token, "syntax error")

class TransformBase(object):
    def __init__(self):
        super(TransformBase, self).__init__()
        self.tokens = []

    def transform(self, ast):

        self.scan(ast)

    def scan(self, token):

        self.tokens = [(token, token)]

        while self.tokens:
            # process tokens from in the order they are discovered. (DFS)
            token, parent = self.tokens.pop()

            self.visit(token, parent)

            for child in reversed(token.children):
                self.tokens.append((child, token))

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


        for i, child in enumerate(token.children):

            if child.type == Token.T_GROUPING and child.value == "{}":
                if (token.type == Token.T_MODULE) or \
                   (token.type == Token.T_ASYNC_FUNCTION) or \
                   (token.type == Token.T_ANONYMOUS_FUNCTION) or \
                   (token.type == Token.T_ANONYMOUS_GENERATOR) or \
                   (token.type == Token.T_ASYNC_GENERATOR) or \
                   (token.type == Token.T_ASYNC_ANONYMOUS_FUNCTION) or \
                   (token.type == Token.T_ASYNC_ANONYMOUS_GENERATOR) or \
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
                        # in some cases convert the invalid object
                        # into a block label.
                        if token.type == Token.T_BINARY and token.value == ":" and len(token.children) == 2:

                            lhs, rhs = token.children

                            if parent.type == Token.T_OBJECT:
                                parent.type = Token.T_BLOCK

                            if parent.type == Token.T_BLOCK or parent.type == Token.T_MODULE:
                                if rhs.type == Token.T_GROUPING:
                                    rhs.type = Token.T_BLOCK

                                index = parent.children.index(token)
                                parent.children.insert(index+1, rhs)

                                token.type = Token.T_BLOCK_LABEL
                                token.value = lhs.value
                                token.children = []

                                continue

                        print("\n%s:"%ref)
                        print("parent", parent.type, parent.value)
                        print("token", token.type, token.value)
                        print("parent", parent.toString(3))
                        raise ref
                    child.type = Token.T_OBJECT

            elif child.type == Token.T_CASE or child.type == Token.T_DEFAULT:
                j = i + 1
                while j < len(token.children):
                    tmp = token.children[j]
                    if tmp.type == Token.T_CASE or tmp.type == Token.T_DEFAULT:
                        break
                    child.children.append(token.children.pop(j))

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
            while child.type == Token.T_COMMA or \
              (child.type == Token.T_BINARY and child.value == ':'):
                child = child.children[0]
            return TransformError(child, "malformed object. maybe a comma is missing?")

        if len(token.children) == 0:
            return None

        child = token.children[0]
        t = child.type
        v = child.value

        if (t == Token.T_TEXT) or \
           (t == Token.T_FUNCTION) or \
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
           token.type == Token.T_RECORD or \
           token.type == Token.T_ARGLIST or \
           token.type == Token.T_LIST or \
           token.type == Token.T_TUPLE or \
           token.type == Token.T_UNPACK_SEQUENCE or \
           token.type == Token.T_UNPACK_OBJECT or \
           token.type == Token.T_GROUPING or \
           token.type == Token.T_VAR:

            if (parent and parent.type == Token.T_FOR):
                return

            chlst = token.children
            index = 0
            while index < len(chlst):
                if chlst[index].type == Token.T_COMMA:
                    child = chlst.pop(index)
                    for j in range(len(child.children)):
                        chlst.insert(index + j, child.children[j])
                else:
                    index += 1

            if token.type in (Token.T_OBJECT, Token.T_UNPACK_OBJECT, Token.T_RECORD):
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

            token.type = Token.T_GET_ATTR
            token.value = "."
            lhs, rhs = token.children
            ln = token.line
            idx = token.index

            token.children = [
                Token(Token.T_GROUPING, ln, idx, "()",
                [Token(Token.T_LOGICAL_OR, ln, idx, "||",
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
                [Token(Token.T_LOGICAL_OR, ln, idx, "||",
                    [
                        Token(Token.T_GROUPING, ln, idx, "()", [lhs]),
                        Token(Token.T_GROUPING, ln, idx, "()", [
                                Token(Token.T_LAMBDA, ln, idx, "=>", [
                                    Token(Token.T_TEXT, ln, idx, "Optional"),
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
            if len(token.children[0].children) != 2:
                raise TransformError(token, "requires 2 children")
                return
            lhs, rhs = token.children[0].children
            ln = token.line
            idx = token.index

            token.children = [
                Token(Token.T_GROUPING, ln, idx, "()",
                [Token(Token.T_LOGICAL_OR, ln, idx, "||",
                    [
                        Token(Token.T_GROUPING, ln, idx, "()", [lhs]),
                        Token(Token.T_OBJECT, ln, idx, "{}")
                    ]
                )]
                ), rhs]

class TransformMagicConstants(TransformBase):

    def visit(self, token, parent):
        """

        transform
            __LINE__
            __COLUMN__
            __FILENAME__

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
                token.value = repr(os.path.split(token.file)[1])
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
                    print("TransformExtractStyleSheet", token)
                    sys.stderr.write("warning: failed to convert style sheet\n")

    def _extract(self, token, parent):

        arglist = token.children[1]

        style_name = None
        if parent and parent.type == Token.T_BINARY and parent.value == ':':
            key = parent.children[0]
            if key.type == Token.T_STRING:
                style_name = 'style.' + literal_eval(key)
            elif key.type == Token.T_TEXT:
                style_name = 'style.' + key.value

        if len(arglist.children) == 1:
            arg0 = arglist.children[0]

            if arg0.type not in (Token.T_OBJECT, Token.T_RECORD):
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

        elif len(arglist.children) == 3:
            # extract a multi media style sheet
            # the first argument is not currently used
            # the second argument is the media query
            # the third argument is a dictionary of selector => stylesheet
            arg0 = arglist.children[1]
            arg1 = arglist.children[2]
            # prevent writing the resulting token to javascript
            # if it does not have any side effects. usually the side
            # effect is simply writing to the style sheet
            keep = parent.type in (Token.T_MODULE, Token.T_BLOCK)

            selector = arg0
            selector_text = None
            if selector.type == Token.T_STRING:
                selector_text = literal_eval(selector)
            elif selector.type == Token.T_TEMPLATE_STRING:
                selector_text = py_ast.literal_eval('"' + selector.value[1:-1] + '"')
                selector_text = shell_format(selector_text, self.named_styles)

            if not selector_text:
                return False

            _style = [selector_text + " {"]
            for child in arg1.children:

                selector = child.children[0]

                selector_text = None
                if selector.type == Token.T_STRING:
                    selector_text = literal_eval(selector)
                elif selector.type == Token.T_TEMPLATE_STRING:
                    selector_text = py_ast.literal_eval('"' + selector.value[1:-1] + '"')
                    selector_text = shell_format(selector_text, self.named_styles)

                if not selector_text:
                    return False

                style = self._object2style(selector_text, child.children[1])
                _style.append(style)
            _style.append("}")

            self.styles.append("\n".join(_style))

            token.type = Token.T_EMPTY_TOKEN
            token.value = ""
            token.children = []

            return True

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
            selector_text = literal_eval(selector)
        elif selector.type == Token.T_TEMPLATE_STRING:
            selector_text = py_ast.literal_eval('"' + selector.value[1:-1] + '"')
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
        minify = True
        if not minify:
            arr = ["  %s: %s;" % (k, v) for k, v in obj.items()]
            body = "\n".join(arr)
            return "%s {\n%s\n}" % (selector, body)
        else:
            arr = ["%s:%s" % (k, v) for k, v in obj.items()]
            body = ";".join(arr)
            return "%s {%s}" % (selector, body)

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
                    lhs_value = literal_eval(lhs)

                rhs_value = None
                if rhs.type == Token.T_TEXT:
                    rhs_value = rhs.value
                elif rhs.type == Token.T_STRING:
                    rhs_value = literal_eval(rhs)
                elif rhs.type == Token.T_NUMBER:
                    rhs_value = rhs.value
                elif rhs.type == Token.T_OBJECT or rhs.type == Token.T_RECORD:

                    if lhs_value is not None:
                        obj.update(self._object2style_helper(prefix + lhs_value + "-", rhs))
                    else:
                        raise TransformError(lhs.type, "invalid lhs")
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

class DeferedToken(object):
    def __init__(self, token):
        super(DeferedToken, self).__init__()
        self.blrefs = {}
        self.fnrefs = {}
        self.token = token

SC_GLOBAL    = 0x001
SC_FUNCTION  = 0x002
SC_BLOCK     = 0x004
SC_CONST     = 0x100
# SC_NO_MINIFY = 0x200 -- mis-feature see: formatter_test.test_fail_function_destructure_object_with_global

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

    def __init__(self, scname, flags, label, counter=1):
        super(Ref, self).__init__()
        # scope flags, logical or of SC_*
        self.flags = flags
        # the variable/function/class name
        self.label = label
        # counts the number of times this reference is read
        # if the value is zero, the variable is never used.
        self.load_count = 0
        # the token which generated this regerence
        self.token = None
        # the scope name, e.g. __main__.__anonymous__
        self.scname = scname
        # counts which clone this ref is. clones are generated
        # whenever a new reference is defined. e.g.
        #    const x = 123; // new const ref, counter = 0
        #    {
        #       const x = 456; // new const ref, counter = 0
        #    }
        #    console.log(x) // prints 123 (reg counter = 0)
        # the initial value should be 1
        self.counter = counter
        # the full scope name for this ref
        s = 'f' if self.flags & SC_FUNCTION else 'b'
        self.name = "%s.%s@%s%d" % (scname, label, s, counter)

    def short_name(self):
        s = 'f' if self.flags & SC_FUNCTION else 'b'
        return "%s$%s%d" % (self.identity(), s, self.counter)

    def long_name(self):
        return "%s.%s" % (self.scname, self.short_name())

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
    def __init__(self, scname, scflags, label, counter):
        super(PythonRef, self).__init__(scname, scflags, label, counter)

    def identity(self):
        if self.counter > 1:
            s = 'f' if self.flags & SC_FUNCTION else 'b'
            return "%s#%s%d" % (self.label, s, self.counter)
        return self.label

    def clone(self, scflags):
        return PythonRef(self.scname, scflags, self.label, self.counter+1)

class IdentityRef(Ref):

    def __init__(self, scname, scflags, label, counter):
        super(IdentityRef, self).__init__(scname, scflags, label, counter)
        #print("construct ref:", self.name)

    def identity(self):
        return self.label

    def clone(self, scflags):
        return IdentityRef(self.scname, scflags, self.label, self.counter+1)

class MinifyRef(Ref):
    def __init__(self, scname, scflags, label, outLabel, counter):
        super(MinifyRef, self).__init__(scname, scflags, label, counter)
        self.outLabel = outLabel
        s = 'f' if self.flags & SC_FUNCTION else 'b'
        self.name = "%s.%s@%s%d" % (scname, outLabel, s, counter)
        #print("construct ref:", self.name)

    def identity(self):
        return self.outLabel

    def clone(self, scflags):
        return MinifyRef(self.scname, scflags, self.label, self.outLabel, self.counter+1)

class UndefinedRef(Ref):
    def __init__(self, scname, scflags, label, counter):
        super(UndefinedRef, self).__init__(scname, scflags, label, counter)
        s = 'f' if self.flags & SC_FUNCTION else 'b'
        self.name = "%s.undefined.%s@%s%d" % (scname, label, s, counter)

    def identity(self):
        return self.label

DF_IDENTIFIER = 1
DF_FUNCTION   = 2  # unused
DF_CLASS      = 3

class VariableScope(object):
    # require three scope instances, for global, function and block scope
    disable_warnings = False

    def __init__(self, name, parent=None):
        super(VariableScope, self).__init__()
        self.name = name
        self.parent = parent

        # freevars, and cellvars are all mappings of:
        #   identifier -> ref

        # freevars are identifiers defined in a parent scope
        # that are used in this or a child scope
        self.freevars = {}
        # cellvars are identifiers defined in this scope used
        # by a child scope
        self.cellvars = {}

        # vars are identifiers defined in this scope
        self.vars = set()

        # mappings of identifier -> ref, of variables defined
        # in this scope but split into their correct function
        # or block scope.
        self.gscope = {}        # undefined global vars that are read / updated
        self.fnscope = {}
        self.blscope = [{}]
        self.blscope_stale = {}
        self.blscope_tags = [""]
        self.blscope_jump_tokens = [[]]

        self.blscope_ids = [0,]
        self.blscope_next_id = 1

        self.all_labels = set()
        self.all_identifiers = set()

        self.defered_functions = []

        self.disable_warnings = False

    def _getRef(self, label):
        """
        returns the reference if it exists for a label in the given scope
        search the current, then parent block scopes before searching
        in the function scope
        """

        ref = None

        for mapping in reversed(self.blscope):
            if label in mapping:
                ref = mapping[label]
                break

        if ref is None and label in self.fnscope:
            ref = self.fnscope[label]

        return ref

    def _getScopeName(self):
        """
        returns the current name of the scope, taking into account
        the current block scope. Each block scope is given a unique
        name.

        This allows for tagging variables with the same identifier that
        are redefined in parallel or nested block scopes
        """
        return self.name # + "@b%d" % self.blscope_ids[-1]

    def _createRef(self, scflags, label, type_):

        return PythonRef(self._getScopeName(), scflags, label, 1)

    def _define_block(self, token):
        label = token.value

        if label in self.blscope[-1]:
            raise TokenError(token, "already defined at scope %s" % self.name)

        for bl in reversed(self.blscope):
            if label in bl:
                return bl[label]

        # two subsequent block scopes (not nested, but parallel)
        # may define the same variable identifier, but it will
        # have a different closure
        if label in self.blscope_stale:
            #print("found stale", label)
            #return self.blscope_stale[label]
            return None
        return None

    def _define_function(self, token):
        label = token.value

        if label in self.fnscope:
            return self.fnscope[label]

        return None

    def _define_impl(self, scflags, token, type_):
        #print("ref define", scope2str(scflags), token, type_)

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
            new_ref.counter = ref.counter + 1
        #elif scflags&SC_NO_MINIFY:
        #    new_ref = IdentityRef(self._getScopeName(), scflags, label, 1)
        else:
            new_ref = self._createRef(scflags, label, type_)

        identifier = new_ref.identity()

        #new_ref.name = self.name + "." + identifier + "@%d" % (new_ref.counter)

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

        new_ref.token = token

        return new_ref

    def _load_store(self, token, load):

        label = token.value
        ref = None

        # search for the scope the defines this label

        if label in self.fnscope:
            ref = self._getRef(label)

        elif any([label in bl for bl in self.blscope]):
            ref = self._getRef(label)

        elif token.value == 'arguments':
            ref = self.define(SC_FUNCTION, token)

        else:
            scopes = [self.parent]
            found = False
            while scopes[-1] is not None:

                if scopes[-1].contains(label):
                    found = True
                    break;

                scopes.append(scopes[-1].parent)

            if not found:
                # not found in an existing scope

                if load:
                    # attempting to load an undefined reference
                    if label in self.all_labels:
                        raise TokenError(token, "read from deleted var")

                    ref = UndefinedRef(self.name, 0, label, 1)
                    token.type = Token.T_GLOBAL_VAR
                    self.gscope[label] = ref
                else:
                    # define this reference in this scope
                    ref = self.define(SC_BLOCK, token)

                if ref is None:
                    raise TokenError(token, "identity error (1) in %s" % self.name)

            else:
                # found in a parent scope
                scope = scopes[-1]

                #ref = self._getRef(label)
                ref = scope.refs[label]

                if ref is None:
                    raise TokenError(token, "identity error (2) in %s" % self.name)

                if not ref.isGlobal():
                    token.type = Token.T_FREE_VAR
                    # here the identity is used to handle the special
                    # case where the same variable name could be used
                    # with different meanings in the same block context

                    # TODO: changed for VM: use label not identity
                    identity = ref.short_name()

                    identity = ref.label
                    #print("define", identity, ref.long_name())
                    scope.defineCellVar(identity, ref)
                    for scope2 in scopes[:-1]:
                        scope2.defineFreeVar(identity, ref)
                    self.freevars[identity] = ref
                    #print("transform._load_store", identity, ref.name, ref.label)

        token.value = ref.identity()
        if token.type == Token.T_TEXT:
            token.type = ref.type()

        # print("load__" if load else "store_", "name", self.depth, token.value, scope2str(ref.flags))

        if load:
            ref.load_count += 1


        return ref

    def define(self, scflags, token, type_=DF_IDENTIFIER):

        ref = self._define_impl(scflags, token, type_)
        token.ref_attr = 1
        token.ref = ref
        return ref

    def load(self, token):

        ref =  self._load_store(token, True)
        token.ref_attr = 4
        token.ref = ref
        return ref

    def store(self, token):

        ref =  self._load_store(token, False)
        token.ref_attr = 2
        token.ref = ref
        return ref

    def pushBlockScope(self, tag=None):
        self.blscope_ids.append(self.blscope_next_id)
        self.blscope_next_id += 1
        self.blscope.append({})
        self.blscope_tags.append(tag) # experimental
        self.blscope_jump_tokens.append([]) # experimental

    def _warn_def(self, key, ref):
        if ref.load_count == 0:
            if not self.disable_warnings:

                if ref.token:
                    file = ref.token.file
                    line = ref.token.line
                    index = ref.token.index
                else:
                    file = "???"
                    line = 0
                    index = 0

                sys.stderr.write("variable defined but never used: %s\n  %s:%s col %s\n" % (key, file, line, index))

    def popBlockScope(self):

        mapping = self.blscope.pop()
        self.blscope_tags.pop()
        self.blscope_jump_tokens.pop()

        for key, ref in mapping.items():
            self._warn_def(key, ref)

        self.blscope_stale.update(mapping)
        return mapping

    def popScope(self):

        # proof of concept
        for scope in [self.blscope[0], self.fnscope]:
            for key, ref in scope.items():
                self._warn_def(key, ref)

    def flattenBlockScope(self):
        out = {}
        for scope in self.blscope:
            out.update(scope)
        return out

    def defer(self, token):
        self.defered_functions.append(DeferedToken(token))

    def updateDefered(self):

        for key, ref in self.fnscope.items():
            for defered in self.defered_functions:
                if key not in defered.fnrefs:
                    defered.fnrefs[key] = ref

    def updateDeferedBlock(self):

        refs = self.flattenBlockScope()
        for key, ref in refs.items():
            for defered in self.defered_functions:
                if key not in defered.blrefs:
                    defered.blrefs[key] = ref

    def _diag(self, token):
        sys.stderr.write("%10s %s %s %s\n" % (token.type, list(self.vars), list(self.freevars.keys()), list(self.cellvars.keys())))

    def __hash__(self):
        return hash(self.name)

class VariableScopeReference(object):
    def __init__(self, scope, refs):
        super(VariableScopeReference, self).__init__()
        self.refs = refs
        self.scope = scope
        self.parent = scope.parent

        self.class_counter = 0

    def contains(self, label):
        return label in self.refs

    def defineCellVar(self, identity, ref):

        self.scope.cellvars[identity] = ref

    def defineFreeVar(self, identity, ref):

        self.scope.freevars[identity] = ref

    def containsIdentity(self, identity):
        return any(ref.identity()==identity for ref in self.refs.values())

alphabetL = 'abcdefghijklmnopqrstuvwxyz'
alphabetU = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
alphabetN = '0123456789'
# an alphabet that encodes with the following properties
#  using 4 bits is only lowercase
#  using 5 bits contains only lowercase and numbers
#  using 6 bits is a valid javascript identifier
alphabet64 = alphabetL + alphabetN + alphabetU + "_$"
# inverts the logic, so that 4 bits produce only uppercase
alphabet64i = alphabetU + alphabetN + alphabetL + "_$"

def encode_identifier(alphabet, n):
    """
    maps the first 16 unique variables to a single character
    maps the first 1024 unique variables to a 2 character string
    """
    c = alphabet[n & 0b1111]
    n>>=4
    while n > 0:
        c = c + alphabet[n & 0b111111]
        n>>=6
    return c

class IdentityScope(VariableScope):
    """
    A VariableScope that does not transform labels
    """

    def _createRef(self, scflags, label, type_):
        return IdentityRef(self._getScopeName(), scflags, label, 1)

class IdentityBlockScope(VariableScope):
    """
    A VariableScope that does not transform labels
    """

    def _createRef(self, scflags, label, type_):
        return PythonRef(self._getScopeName(), scflags, label, 1)

class MinifyVariableScope(VariableScope):

    def __init__(self, name, parent=None):
        super(MinifyVariableScope, self).__init__(name, parent)
        self.label_index = 0
        self.class_counter = 0

    def _createRef(self, scflags, label, type_):

        ident =  self.nextLabel(type_) # + '_' + label

        return MinifyRef(self._getScopeName(), scflags, label, ident, 1)

    def nextLabel(self, type_):
        c = ""
        if type_ == DF_CLASS:
            # closure compiler can detect duplicate class names even
            # in different scopes. use the parent scope to keep track
            # of unique names
            # class names always start with a capital letter
            scope = self
            while scope.parent is not None:
                scope = scope.parent

            n = scope.class_counter
            scope.class_counter += 1
            c = encode_identifier(alphabet64i, n)
            return c
        else:
            #identifiers for functions and variables are always lowercase
            # TODO: consider making functions always at least 2 characters
            while True:
                n = self.label_index
                self.label_index += 1
                c = encode_identifier(alphabet64, n)

                # prevent the identifier from being the same as a reserved word
                # 'do' is 0b111110 and comes up fairly frequently
                if c in Lexer.reserved_words:
                    continue
                # ensure this new label does not appear in a parent scope
                found = False
                scope = self.parent
                while scope is not None:
                    if scope.containsIdentity(c):
                        found = True
                        break
                    scope = scope.parent

                # this name is unique, use it!
                if not found:
                    break
            return c

ST_MASK     = 0x000FF
ST_SCOPE_MASK     = 0xFFF00
ST_VISIT    = 0x001
ST_FINALIZE = 0x002
ST_DEFERED  = 0x004
ST_STORE    = 0x100
ST_GLOBAL   = SC_GLOBAL << 12
ST_FUNCTION = SC_FUNCTION << 12
ST_BLOCK    = SC_BLOCK << 12
ST_CONST    = SC_CONST << 12

isConstructor = lambda token: token.type == Token.T_METHOD and token.children[0].value == "constructor"
isFunction = lambda token: token.type in (
            Token.T_FUNCTION,
            Token.T_ASYNC_FUNCTION,
            Token.T_GENERATOR,
            Token.T_ASYNC_GENERATOR,
            Token.T_METHOD,
            Token.T_ANONYMOUS_FUNCTION,
            Token.T_ASYNC_ANONYMOUS_FUNCTION,
            Token.T_ANONYMOUS_GENERATOR,
            Token.T_ASYNC_ANONYMOUS_GENERATOR,
            Token.T_LAMBDA,
    )
isNamedFunction = lambda token: token.type in (
            Token.T_FUNCTION,
            Token.T_ASYNC_FUNCTION,
            Token.T_GENERATOR,
            Token.T_ASYNC_GENERATOR,
            Token.T_METHOD,
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

    Visit Deferment:
        javascript allows for functions in a document to be called
        before they are defined. To implement this the entire document
        is scanned using BFS to discover function definitions, but the
        function body itself is not parsed until after the entire
        document at that level was processed.

        Example:
            const z = 123;
            console.log(test()); // prints 123
            function test() {
                return z;
            }

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
        = and variants must have a unique token type T_VARIABLE_ASSIGMENT

    """
    disable_warnings = False

    def __init__(self):
        super(TransformAssignScope, self).__init__()

        self.global_scope = None

        self.visit_mapping = {
            Token.T_FUNCTION: self.visit_function,
            Token.T_ASYNC_FUNCTION: self.visit_function,
            Token.T_GENERATOR: self.visit_function,
            Token.T_ASYNC_GENERATOR: self.visit_function,
            Token.T_METHOD: self.visit_function,

            Token.T_ANONYMOUS_FUNCTION: self.visit_function,
            Token.T_ASYNC_ANONYMOUS_FUNCTION: self.visit_function,
            Token.T_ANONYMOUS_GENERATOR: self.visit_function,
            Token.T_ASYNC_ANONYMOUS_GENERATOR: self.visit_function,

            Token.T_LAMBDA: self.visit_lambda,

            Token.T_ASSIGN: self.visit_assign,
            Token.T_BLOCK: self.visit_block,
            Token.T_MODULE: self.visit_module,
            Token.T_TEXT: self.visit_text,
            Token.T_VAR: self.visit_var,
            Token.T_OBJECT: self.visit_object,
            Token.T_RECORD: self.visit_object,
            Token.T_BINARY: self.visit_binary,
            Token.T_IMPORT_MODULE: self.visit_import_module,
            Token.T_PYIMPORT: self.visit_pyimport,
            Token.T_EXPORT: self.visit_export,
            Token.T_EXPORT_DEFAULT: self.visit_export,
            Token.T_UNPACK_SEQUENCE: self.visit_unpack_sequence,
            Token.T_UNPACK_OBJECT: self.visit_unpack_object,
            Token.T_FOR: self.visit_for,
            Token.T_FOR_IN: self.visit_for_in,
            Token.T_FOR_OF: self.visit_for_of,
            Token.T_DOWHILE: self.visit_dowhile,
            Token.T_WHILE: self.visit_while,
            Token.T_SWITCH: self.visit_switch,
            Token.T_GET_ATTR: self.visit_get_attr,
            Token.T_CATCH: self.visit_catch,

            # method and class are added, but when compiling a
            # python module we assume a transform has already been
            # run to remove methods and classes
            Token.T_CLASS: self.visit_class,

            Token.T_BREAK: self.visit_break,
            Token.T_CONTINUE: self.visit_continue,


            # Token.T_GROUPING: self.visit_error,
        }

        self.finalize_mapping = {

            Token.T_FUNCTION: self.finalize_function,
            Token.T_ASYNC_FUNCTION: self.finalize_function,
            Token.T_GENERATOR: self.finalize_function,
            Token.T_ASYNC_GENERATOR: self.finalize_function,
            Token.T_METHOD: self.finalize_function,

            Token.T_ANONYMOUS_FUNCTION: self.finalize_function,
            Token.T_ASYNC_ANONYMOUS_FUNCTION: self.finalize_function,
            Token.T_ANONYMOUS_GENERATOR: self.finalize_function,
            Token.T_ASYNC_ANONYMOUS_GENERATOR: self.finalize_function,

            Token.T_FOR: self.finalize_block,
            Token.T_FOR_IN: self.finalize_block,
            Token.T_FOR_OF: self.finalize_block,
            Token.T_WHILE: self.finalize_block,
            Token.T_DOWHILE: self.finalize_block,
            Token.T_CATCH: self.finalize_block,
            # TODO: missing finally block?

            Token.T_LAMBDA: self.finalize_function,

            Token.T_BLOCK: self.finalize_block,
            Token.T_MODULE: self.finalize_module,

            Token.T_BREAK: self.finalize_break,
            Token.T_CONTINUE: self.finalize_continue,

            Token.T_CLASS: self.finalize_class,

            Token.T_ASSIGN: self.finalize_assign,
            Token.T_BINARY: self.finalize_binary,

        }

        self.defered_mapping = {
            Token.T_FUNCTION: self.defered_function,
            Token.T_ASYNC_FUNCTION: self.defered_function,
            Token.T_GENERATOR: self.defered_function,
            Token.T_ASYNC_GENERATOR: self.defered_function,
            Token.T_METHOD: self.defered_function,

            Token.T_ANONYMOUS_FUNCTION: self.defered_function,
            Token.T_ASYNC_ANONYMOUS_FUNCTION: self.defered_function,
            Token.T_ANONYMOUS_GENERATOR: self.defered_function,
            Token.T_ASYNC_ANONYMOUS_GENERATOR: self.defered_function,

            Token.T_LAMBDA: self.defered_function,
            Token.T_MODULE: self.defered_function,

            Token.T_CLASS: self.defered_function,
        }

        self.states = {
            ST_VISIT: self.visit_mapping,
            ST_FINALIZE: self.finalize_mapping,
            ST_DEFERED: self.defered_mapping,
        }

        self.state_defaults = {
            ST_VISIT: self.visit_default,
            ST_FINALIZE: self.finalize_default,
            ST_DEFERED: self.defered_default,
        }

        # mapping identifier -> identifier
        # giving the original identifier for a global variable
        # and the new name after applying the transform
        self.globals = {}

    def newScope(self, name, parentScope=None):
        scope = VariableScope(name, parentScope)
        scope.disable_warnings = self.disable_warnings
        return scope

    def transform(self, ast):

        self.seq = [self.initialState(ast)]

        self._transform(ast)

        vars = dict(self.global_scope.fnscope)
        vars.update(self.global_scope.flattenBlockScope())

        return {label:ref.identity() for label,ref in vars.items()}

    def _transform(self, token):

        while self.seq:
            # process tokens from in the order they are discovered. (DFS)
            flags, scope, token, parent = self.seq.pop()

            fn = self.states[flags & ST_MASK].get(token.type, None)

            if not fn:
                fn = self.state_defaults[flags & ST_MASK]

            fn(flags, scope, token, parent)

    def initialState(self, token):
        self.global_scope = self.newScope('__main__', None)
        return (ST_VISIT, self.global_scope, token, None)

    # -------------------------------------------------------------------------

    def visit_default(self, flags, scope, token, parent):

        if token.type == Token.T_SUBSCR:
            self._push_finalize(scope, token, parent)

        self._push_children(scope, token, flags)

    def visit_error(self, flags, scope, token, parent):
        raise TokenError(token, "invalid token")

    def visit_module(self, flags, scope, token, parent):
        self._push_finalize(scope, token, parent)
        self._push_defered(scope, token, parent)

        self._hoist_functions(scope, token)

        self._push_children(scope, token, flags)

    def _hoist_functions(self, scope, token):
        # preprocess each block in order to hoist function definitions
        # this fixes function naming in block scopes for formatting
        # javascript, but does nothing to fix compiling javascript to python
        for child in token.children:
            if isNamedFunction(child):
                # TODO: is this valid to remove
                # if not (token.type == Token.T_METHOD and not self.python):
                # alt:?
                # if not token.type == Token.T_METHOD or self.python:
                scope.define(SC_FUNCTION, child.children[0])
            elif child.type in (Token.T_EXPORT, Token.T_EXPORT_DEFAULT):
                args = child.children[1]
                for gc in args.children:
                    if isNamedFunction(gc):
                        scope.define(SC_FUNCTION, gc.children[0])

                    elif gc.type == Token.T_CLASS:
                        scope.define(0, gc.children[0], DF_CLASS)
            elif child.type == Token.T_CLASS:
                scope.define(0, child.children[0], DF_CLASS)

    def visit_block(self, flags, scope, token, parent):

        if isFunction(parent):
            # this should never happen
            raise TransformError(parent, "visit block for function not allowed")

        scope.pushBlockScope()

        self._hoist_functions(scope, token)

        self._push_finalize(scope, token, parent)
        self._push_children(scope, token, flags)

    def visit_function(self, flags, scope, token, parent):

        if isNamedFunction(token):
            if parent.type not in (Token.T_BLOCK, Token.T_CLASS_BLOCK, Token.T_MODULE, Token.T_OBJECT, Token.T_EXPORT_ARGS):
                # this should never happen
                raise TransformError(parent, "visit function, parent node is not a block scope: %s>%s" % (parent.type, token.type))

        ### inside an object square brackets denote an expresion which
        ### will evaluate to the key value.
        if parent.type == Token.T_OBJECT:
            if token.children[0].type == Token.T_LIST:
                self._push_children(scope, token.children[0], flags)
            else:
                self._push_tokens(flags, scope, [token.children[0]], token)


        # define the name of the function when it is not an
        # anonymous function and not a class constructor.
        ##if not isAnonymousFunction(token) and not isConstructor(token):
        ##    scflags = (flags & ST_SCOPE_MASK) >> 12
        ##    # when processing for javascript output (opposed to compiling
        ##    # for python) don't define methods
        ##    if not (token.type == Token.T_METHOD and not self.python):
        ##        print("!!", hex(scflags))
        ##        scope.define(scflags, token.children[0])

        #self._handle_function(scope, token, {})
        scope.defer(token)

    def visit_lambda(self, flags, scope, token, parent):

        # lambdas allow for no arglist, but that makes compiling harder

        # fix some js-isms that are not really valid python
        #if self.python:
        #    #
        #    #   x => x
        #    #   (x) => x
        #    #
        #    if token.children[1].type == Token.T_TEXT:
        #        tok = token.children[1]
        #        token.children[1] = Token(Token.T_ARGLIST, tok.line, tok.index, '()', [tok])
        #    # lambdas can be a single expression if it returns a value
        #    # convert that expression into a block with a return
        #    #
        #    #   x => x
        #    #   x => { return x }
        #    #
        #    if token.children[2].type != Token.T_BLOCK:
        #        tok = token.children[2]
        #        token.children[2] = Token(Token.T_BLOCK, tok.line, tok.index, '{}',
        #            [Token(Token.T_RETURN, tok.line, tok.index, 'return', [tok])])

        #self._handle_function(scope, token, {})
        scope.defer(token)

    def visit_class(self, flags, scope, token, parent):

        """
        this method is implemented only for the case when minifying javascript
        """

        # define the class name in the current scope
        # see visit_block
        #scope.define(SC_FUNCTION, token.children[0])
        scope.defer(token)

    def visit_var(self, flags, scope, token, parent):
        flags = 0
        if token.value == 'var':
            flags = ST_FUNCTION
        if token.value == 'let':
            flags = ST_BLOCK
        if token.value == 'const':
            flags = ST_BLOCK | ST_CONST

        for child in reversed(token.children):

            if child.type == Token.T_TEXT:
                # define
                self._push_tokens(ST_VISIT | ST_STORE | (flags & ST_SCOPE_MASK), scope, [child], token)
            else:
                self._push_tokens(ST_VISIT | (flags & ST_SCOPE_MASK), scope, [child], token)

    def visit_assign(self, flags, scope, token, parent):

        # TODO: fix transform for UNPACK_*
        #        always process list or object, when done if the comma
        #        node only has one child, it can be hoisted
        #        process list and object in the same function
        # TODO: if token value is not '=', and LHS is not an identifier
        #       (parent is VAR, LET, CONST), raise an error
        if token.value == "=":

            if token.children and token.children[0].type in (
              Token.T_UNPACK_OBJECT, Token.T_UNPACK_SEQUENCE):
                self._visit_assign_unpack_fix(flags, scope, token, parent)
            else:
                self._push_finalize(scope, token, parent)

                self._push_tokens(ST_VISIT | ST_STORE | (flags & ST_SCOPE_MASK), scope, [token.children[0]], token)
                self._push_tokens(ST_VISIT, scope, [token.children[1]], token)

        else:
            self._push_children(scope, token, 0)


    def _h_get_attr(self, token, attr):
        # TODO: consider using the form `${token}?.${attr}`
        return Token(Token.T_GET_ATTR, token.line, token.index, ".",
            [token.clone(), Token(Token.T_ATTR, token.line, token.index, attr)])

    def _h_get_index(self, token, index):
        # TODO: consider using the form `${token}?.[${index}]`
        return Token(Token.T_SUBSCR, token.line, token.index, "[]",
            [token.clone(), Token(Token.T_NUMBER, token.line, token.index, str(index))])

    def _h_assign(self, lhs, rhs):

        return Token(Token.T_ASSIGN, lhs.line, lhs.index, "=",
            [lhs.clone(), rhs.clone()])

    def _h_get_attr_undefined(self, rhs, attr, default):
        """
            given:
                {attr=default} = rhs

            compute:
                ${attr} = ${rhs}?.${attr}??${default}

            where:
                rhs: Token: expression on rhs
                attr: str: attribute name
                default: Token: default value expression if attr is undefined
        """

        tok_attr_name = Token(Token.T_ATTR, rhs.line, rhs.index, attr)

        tok_attr = Token(Token.T_OPTIONAL_CHAINING, rhs.line, rhs.index, "?.",
            [rhs.clone(), tok_attr_name])

        tmpa = Token(Token.T_TEXT, rhs.line, rhs.index, attr)

        tmpb = Token(Token.T_BINARY, rhs.line, rhs.index, "??",
            [tok_attr, default.clone()])

        return Token(Token.T_ASSIGN, rhs.line, rhs.index, "=", [tmpa, tmpb])

    def _unpack_sequence_scan(self, name, tokens):

        nested = []
        index = 0
        while index < len(tokens):
            child = tokens[index]
            if child.type in (Token.T_UNPACK_OBJECT, Token.T_OBJECT):
                elem = tokens[index]
                placeholder = Token(Token.T_TEXT, elem.line, elem.index,
                    "%s$%d" % (name, index))
                tokens[index] = placeholder
                nested.append((index, placeholder, elem))
            else:
                index += 1
        return nested

    def _unpack_object_scan(self, name, tokens):

        extra = []
        nested = []
        index = 0
        while index < len(tokens):
            child = tokens[index]
            # FIXME: should never be T_OBJECT
            if child.type == Token.T_BINARY and child.value == ":" and \
              child.children[1].type in (Token.T_UNPACK_OBJECT, Token.T_OBJECT):
                nested.append((name, name + '$' + child.children[0].value,
                                tokens.pop(index)))
            elif child.type == Token.T_ASSIGN:
                extra.append(tokens.pop(index))
            else:
                index += 1

        return nested, extra

    def _unpack_fix(self, lhs, rhs):
        """
        given an expression of the form
            ${lhs} = ${rhs}
        where $lhs is a sequence or object unpacking syntax
        return a new expression which can be minified

        returns None if the lhs is already trivialbly minifiable

        objects unpacking where the object attribute is assigned a default
        value need to have the expression rewritten to a form where the
        object member can be accessed and assigned to a variable of
        a different name.
        """

        ln = lhs.line
        co = lhs.index
        name = "$js$unpack$%d$%d_" % (ln, co)

        ident = Token(Token.T_TEXT, ln, co, name)
        comma = Token(Token.T_COMMA, ln, co, ",")

        comma.children.append(
            self._h_assign(ident, rhs)
        )

        do_replace = False
        #to_define = []
        stack = [(ident, lhs.clone())]

        # TODO: prune children of comma that are not used once the stack is empty
        while stack:
            # ident is a token representing the T_TEXT variable name
            # tok is the left hand side expression
            # which may be a sequence or object to unpack ident into
            # together, they assume an expression of the form:
            #   `${tok} = ${ident}`
            # the expression will be re-written to support this minify
            ident, tok = stack.pop(0)

            if tok.type in (Token.T_UNPACK_SEQUENCE, Token.T_LIST):
                if tok.type == Token.T_LIST:
                    sys.stderr.write("warning: line: %d column: %d: found LIST expected T_UNPACK_SEQUENCE" %(
                        tok.line, tok.column))

                # when unpacking sequences pull out objects and assign those
                # indexes
                nested = self._unpack_sequence_scan(ident.value, tok.children)

                if tok.children:
                    node = self._h_assign(tok, ident)
                    comma.children.append(node)

                for idx, placeholder, elem in nested:
                    stack.append((placeholder, elem))

            # FIXME: should never be T_OBJECT
            elif tok.type in (Token.T_UNPACK_OBJECT, Token.T_OBJECT):
                if tok.type == Token.T_OBJECT:
                    sys.stderr.write("warning: line: %d column: %d: found OBJECT expected UNPACK_OBJECT" %(
                        tok.line, tok.column))

                nested, extra = self._unpack_object_scan(ident.value, tok.children)
                if tok.children:
                    node = self._h_assign(tok, ident)
                    comma.children.append(node)

                    for idx, child in enumerate(node.children[0].children):
                        if child.type == Token.T_TEXT:
                            tmp_a = Token(Token.T_ATTR, ln, co, child.value)
                            tmp_b = Token(Token.T_TEXT, ln, co, child.value)
                            node.children[0].children[idx] = Token(Token.T_BINARY, ln, co, ":", [tmp_a, tmp_b])
                        elif child.type == Token.T_BINARY and child.value == ":":
                            pass
                        else:
                            raise TransformError(child, "invalid token in object destructuring")
                for src, dst, child in nested:

                    attr, obj = child.children
                    lhs = Token(Token.T_TEXT, ln, co, dst)
                    rhs = self._h_get_attr(Token(Token.T_TEXT, ln, co, src), attr.value)
                    comma.children.append(self._h_assign(lhs, rhs))

                    stack.append((lhs, obj))

                for child in extra:

                    lhs, rhs = child.children
                    comma.children.append(self._h_get_attr_undefined(ident, lhs.value, rhs))
                    do_replace = True

        if do_replace:
            return comma

        return None

    def _unpack_fix_defs(self, token):
        # if _unpack_fix does not produce an interesting result
        # the AST still needs to be transformed into a form which
        # can be minified. make trivial modifications and return a reference
        # to every variable token that is defined

        to_define = []
        stack = [token]

        while stack:
            token = stack.pop()

            if token.type in (Token.T_UNPACK_SEQUENCE,):
                for child in token.children:
                    if child.type == Token.T_ASSIGN:
                        to_define.append(child.children[0])
                    else:
                        to_define.append(child)
            elif token.type in (Token.T_UNPACK_OBJECT,):
                for idx, child in enumerate(token.children):
                    if child.type == Token.T_TEXT:
                        tmp_a = Token(Token.T_ATTR, token.line, token.index, child.value)
                        tmp_b = Token(Token.T_TEXT, token.line, token.index, child.value)
                        token.children[idx] = Token(Token.T_BINARY, token.line, token.index, ":", [tmp_a, tmp_b])
                        to_define.append(tmp_b)
                    elif child.type == Token.T_BINARY and child.value == ":":
                        to_define.append(child.children[1])
                    else:
                        raise TransformError(child, "invalid token in object destructuring")
            else:
                continue

            stack.extend(token.children)
        return to_define

    def _visit_assign_unpack_fix(self, flags, scope, token, parent):

        # FIXME: the LHS should never have OBJECT instead of UNPACK_OBJECT
        #        check parents to confirm type during rename
        lhs, rhs = token.children

        node = self._unpack_fix(lhs, rhs)

        # only replace if a meaningful restructure took place
        if node:
            token.type = node.type
            token.value = node.value
            token.line = node.line
            token.index = node.index
            token.children = node.children

            # this causes a re-visit of all nodes starting at `token`
            # which may hit this function again, however subsequent calls
            # will result in do_replace not being set, because the lhs
            # has already been normalized
            self.visit_default(flags, scope, token, parent)

        else:
            # no meaningful changes were made to the ast,
            # process the token as a normal assignment
            self._push_finalize(scope, token, parent)
            self._push_tokens(ST_VISIT | ST_STORE | (flags & ST_SCOPE_MASK), scope, [token.children[0]], token)
            self._push_tokens(ST_VISIT, scope, [token.children[1]], token)

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

                # TODO: replace repr with a js string escape
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
        self._push_finalize(scope, token, parent)
        self._push_children(scope, token, flags)

        if token.value != ":":
            return

        if not parent or parent.type not in (Token.T_OBJECT, Token.T_UNPACK_OBJECT, Token.T_RECORD):
            return

        # handle the case where :: {foo: 0}
        if token.children[0].type == Token.T_TEXT:
            token.children[0].type = Token.T_STRING
            token.children[0].value = repr(token.children[0].value)

    def visit_import_module(self, flags, scope, token, parent):

        scflags = (flags & ST_SCOPE_MASK) >> 12

        # fix the list of import names. Instead of an object
        # it should be an argument list with pairs
        # each pair is an ATTR (from the module to import)
        # and the target Global or Local Variable
        # this allows for renaming of the variables
        token.children[0].type = Token.T_ARGLIST
        for idx, argtoken in enumerate(token.children[0].children):
            if argtoken.type == Token.T_ASSIGN:
                argtoken.children[0].type = Token.T_ATTR
                scope.define(scflags, argtoken.children[1])
            else:
                scope.define(scflags, argtoken)
                lhs = argtoken.clone(type=Token.T_ATTR)
                rhs = argtoken
                tok = token.clone(type=Token.T_ASSIGN, value="=")
                tok.children = [lhs, rhs]
                token.children[0].children[idx] = tok

    def visit_pyimport(self, flags, scope, token, parent):

        scflags = (flags & ST_SCOPE_MASK) >> 12

        # the imported variable name
        if token.children[0].value:
            scope.define(scflags, token.children[0])

        # fix the list of import names. Instead of an object
        # it should be an argument list with pairs
        # each pair is an ATTR (from the module to import)
        # and the target Global or Local Variable
        # this allows for renaming of the variables
        token.children[2].type = Token.T_ARGLIST
        for idx, argtoken in enumerate(token.children[2].children):
            if argtoken.type == Token.T_ASSIGN:
                argtoken.children[0].type = Token.T_ATTR
                scope.define(scflags, argtoken.children[1])
            else:
                scope.define(scflags, argtoken)
                lhs = argtoken.clone(type=Token.T_ATTR)
                rhs = argtoken
                tok = token.clone(type=Token.T_ASSIGN, value="=")
                tok.children = [lhs, rhs]
                token.children[2].children[idx] = tok


    def visit_export(self, flags, scope, token, parent):

        new_flags = (ST_VISIT | (flags & ST_SCOPE_MASK))
        for child in reversed(token.children):
            self.seq.append((new_flags, scope, child, token))

    def visit_unpack_sequence(self, flags, scope, token, parent):
        scflags = (flags & ST_SCOPE_MASK) >> 12
        self._push_children(scope, token, flags)

    def visit_unpack_object(self, flags, scope, token, parent):
        scflags = (flags & ST_SCOPE_MASK) >> 12
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

        # the extra block scope, and finalize, allows for declaring
        # variables inside of a for arg list
        scope.pushBlockScope("loop")
        self._push_finalize(scope, token, parent)

        self._push_children(scope, body, flags)
        self._push_children(scope, arglist, flags)

    def visit_for_in(self, flags, scope, token, parent):
        """
        for a C-Style for loop process the argument list
        as if it was inside the body of the loop.

        this allows for two consecutive loops to define the same
        iteration variable as const or with let
        """

        label, expr, body = token.children

        if body.type != Token.T_BLOCK:
            # the parser should be run in python mode
            raise TransformError(body, "expected block in for loop body")

        # the extra block scope, and finalize, allows for declaring
        # variables inside of a for arg list

        scope.pushBlockScope("loop")
        self._push_finalize(scope, token, parent)

        self._push_children(scope, body, flags)
        self._push_tokens(ST_VISIT | ST_STORE | (flags & ST_SCOPE_MASK), scope, [label], token)
        self._push_tokens(ST_VISIT, scope, [expr], token)

    def visit_for_of(self, flags, scope, token, parent):
        """
        for a C-Style for loop process the argument list
        as if it was inside the body of the loop.

        this allows for two consecutive loops to define the same
        iteration variable as const or with let
        """

        label, expr, body = token.children

        if body.type != Token.T_BLOCK:
            # the parser should be run in python mode
            raise TransformError(body, "expected block in for loop body")

        # the extra block scope, and finalize, allows for declaring
        # variables inside of a for arg list

        scope.pushBlockScope("loop")
        self._push_finalize(scope, token, parent)

        self._push_children(scope, body, flags)
        self._push_tokens(ST_VISIT | ST_STORE | (flags & ST_SCOPE_MASK), scope, [label], token)
        self._push_tokens(ST_VISIT, scope, [expr], token)

    def visit_dowhile(self, flags, scope, token, parent):

        body, expr = token.children

        if body.type != Token.T_BLOCK:
            # the parser should be run in python mode
            raise TransformError(body, "expected block in for loop body")

        scope.pushBlockScope("loop")
        self._push_finalize(scope, token, parent)

        self._push_children(scope, body, flags)
        self._push_tokens(ST_VISIT, scope, [expr], token)

    def visit_while(self, flags, scope, token, parent):

        expr, body = token.children

        if body.type != Token.T_BLOCK:
            # the parser should be run in python mode
            raise TransformError(body, "expected block in loop body")

        scope.pushBlockScope("loop")
        self._push_finalize(scope, token, parent)

        self._push_children(scope, body, flags)
        self._push_tokens(ST_VISIT, scope, [expr], token)

    def visit_switch(self, flags, scope, token, parent):

        expr, body = token.children

        if body.type != Token.T_BLOCK:
            # the parser should be run in python mode
            raise TransformError(body, "expected block in switch loop body")

        scope.pushBlockScope("switch")
        self._push_finalize(scope, token, parent)

        self._push_children(scope, body, flags)
        self._push_tokens(ST_VISIT, scope, [expr], token)

    def visit_break(self, flags, scope, token, parent):

        self._push_finalize(scope, token, parent)

        idx = -1
        for i, refs in reversed(list(enumerate(scope.blscope))):
            scope.blscope_jump_tokens[i].append(token)
            tag = scope.blscope_tags[i]

            if tag == "loop":
                idx = i
                break

            if tag == "switch":
                token.type = Token.T_SWITCH_BREAK;
                idx = i
                break

        if idx < 0:
            raise TransformError(token, "break found outside loop")


    def visit_continue(self, flags, scope, token, parent):
        self._push_finalize(scope, token, parent)

        idx = -1
        for i, refs in reversed(list(enumerate(scope.blscope))):
            scope.blscope_jump_tokens[i].append(token)
            tag = scope.blscope_tags[i]
            if tag == "loop":
                idx = i
                break

        if idx < 0:
            raise TransformError(token, "continue found outside loop")

    def visit_get_attr(self, flags, scope, token, parent):

        lhs, rhs = token.children

        self.seq.append((ST_VISIT, scope, rhs, token))
        self.seq.append((ST_VISIT, scope, lhs, token))

    def visit_catch(self, flags, scope, token, parent):

        # the extra block scope, and finalize, allows for declaring
        # variables inside of a catch arg list
        arglist, body = token.children

        if body.type != Token.T_BLOCK:
            # the parser should be run in python mode
            raise TransformError(body, "expected block in for loop body")

        scope.pushBlockScope()
        self._push_finalize(scope, token, parent)

        self._push_children(scope, body, flags)

        # arglist is always a parenthetical block with one text child
        # define that text node in the new block
        if arglist.children:
            scope.define(ST_BLOCK, arglist.children[0])

    #def visit_export(self, flags, scope, token, parent):
    #    print("tr export", token.children[0].toString(1))
    #    self._push_tokens(ST_VISIT | (flags & ST_SCOPE_MASK), scope, [token.children[0]], token)

    # -------------------------------------------------------------------------

    def finalize_default(self, flags, scope, token, parent):

        pass

    def finalize_module(self, flags, scope, token, parent):

        scope.popScope()

        if scope.cellvars or scope.freevars:
            raise TokenError(token, "unexpected closure")

        self.globals = {}
        for name, ref in scope.gscope.items():
            self.globals[name] = ref.identity()
        for name, ref in scope.fnscope.items():
            self.globals[name] = ref.identity()
        for name, ref in scope.blscope[0].items():
            self.globals[name] = ref.identity()

    def finalize_function(self, flags, scope, token, parent):

        #if self.python:

        # TODO: calling popScope here does discover defined but unused variables
        #       most of them are function arguments that are unused.
        #       disabling for now, because it has no side effect other than
        #       printing a large number of warnings.
        #scope.popScope()

        # append a token to represent the closure of the function block
        # this is not used for formating, but for meta-data used
        # by the compiler

        # conditionally create closure in case a different transform
        # has already generated the token.
        #if len(token.children) == 4:
        #    closure = token.children[3]
        #    closure.children = []
        #else:
        #    closure = Token(Token.T_CLOSURE, 0, 0, "")
        #    token.children.append(closure)

        closure = Token(Token.T_CLOSURE, token.line, token.index, "")
        token.children.append(closure)

        for name, ref in sorted(scope.cellvars.items()):
            tok = Token(Token.T_CELL_VAR, token.line, token.index, name)
            tok.ref = ref
            tok.ref_attr = 8
            closure.children.append(tok)

        for name, ref in sorted(scope.freevars.items()):
            tok = Token(Token.T_FREE_VAR, token.line, token.index, name)
            tok.ref = ref
            tok.ref_attr = 8
            closure.children.append(tok)

        #token.children.append(closure)

    def finalize_class(self, flags, scope, token, parent):
        closure = Token(Token.T_CLOSURE, 0, 0, "")
        token.children.append(closure)

        for name,ref in sorted(scope.cellvars.items()):
            tok = Token(Token.T_CELL_VAR, 0, 0, name)
            tok.ref = ref
            tok.ref_attr = 8
            closure.children.append(tok)

        for name,ref in sorted(scope.freevars.items()):
            tok = Token(Token.T_FREE_VAR, 0, 0, name)
            tok.ref = ref
            tok.ref_attr = 8
            closure.children.append(tok)

    def finalize_block(self, flags, scope, token, parent):

        # .defered_functions[{block_refs: {}, tokens: []}]
        # every time a block is popped add missing references to block scope vars
        # when the function finally pops take the function scope vars
        # overlay the flattened block scope vars and then push new scopes to handle the functions

        scope.updateDeferedBlock()

        refs = scope.popBlockScope()

        # TODO: certain scopes, like for_of, and for_in need a special case
        #       where the iteration label needs to be deleted
        #       if not already covered by save / restore

        # delete variables in the reverse order that they were defined
        # in this scope
        #if refs:
        #    for ref in reversed(refs.values()):
        #        tok = Token(Token.T_DELETE_VAR, token.line, token.index, "")
        #        tok.ref = ref
        #        tok.ref_attr = 8
        #        tok.children.append(ref.token.clone())
        #        token.children.append(tok)

        # print("jump refs", scope.blscope_jump_tokens[-1])
        # blscope_jump tokens can be used to work out if a variable
        # needs to be deleted prior to a break or continue.

        if refs:

            _save = []
            _restore = []
            _delete = []
            for ref in reversed(refs.values()):

                # for variable scopes, use a system where there
                # is a save and then a load to restore the original value
                # of a label after a block exits
                # ref counter checks to see if this is not the first time
                # that this variable was assigned
                #if self.save_vars:
                #if ref.token.type in [Token.T_LOCAL_VAR, Token.T_GLOBAL_VAR] and ref.counter > 1:
                #    tok = Token(Token.T_SAVE_VAR, token.line, token.index, "", [ref.token.clone()])
                #    tok.ref = ref
                #    tok.ref_attr = 8
                #    _save.append(tok)
                #    tok = Token(Token.T_RESTORE_VAR, token.line, token.index, "", [ref.token.clone()])
                #    tok.ref = ref
                #    tok.ref_attr = 8
                #    _restore.insert(0, tok) # reverse order
                #else:
                #print("ref delete", ref)
                tok = Token(Token.T_DELETE_VAR, token.line, token.index, "", [ref.token.clone()])
                tok.ref = ref
                tok.ref_attr = 8
                _delete.insert(0, tok) # reverse order


            if _save or _restore:
                # TODO: validate that parent is a block or module
                # its an error or behavior is undefined
                idx = parent.children.index(token)
                if token.type != Token.T_BLOCK:
                    parent.children = parent.children[:idx] + _save + parent.children[idx:idx+1] + _restore + parent.children[idx+1:]
                else:
                    if parent.type not in (Token.T_BLOCK, Token.T_MODULE):
                        #print(parent.toString(1))
                        #raise TransformError(token, "expected parent to be a module or block (found %s)" % parent.type)
                        print("<%s:%d:%d> expected parent to be a module or block (found %s)" % (token.type, token.line, token.index, parent.type))

                    token.children = _save + token.children + _restore

            if _delete:
                if token.type in (Token.T_FOR):
                    if parent.type not in (Token.T_BLOCK, Token.T_MODULE):
                        raise TransformError(token, "expected parent to be a module or block (found %s)" % parent.type)
                    #token.children[1].children.extend(_delete)
                    idx = parent.children.index(token)
                    for t in reversed(_delete):
                        parent.children.insert(idx+1, t)
                    pass
                elif token.type in (Token.T_FOR, Token.T_FOR_OF, Token.T_FOR_IN):
                    token.children[2].children.extend(_delete)
                elif token.type in (Token.T_BLOCK):
                    token.children.extend(_delete)


    def finalize_break(self, flags, scope, token, parent):

        #print(scope.blscope_jump_tokens[-1])
        #for tag, refs in reversed(list(zip(scope.blscope_tags, scope.blscope))):
        #    print("tag", tag, list(refs.values()))
        pass

    def finalize_continue(self, flags, scope, token, parent):
        pass

    # -------------------------------------------------------------------------


    def finalize_assign(self, flags, scope, token, parent):

        pass

    def finalize_binary(self, flags, scope, token, parent):

        pass

    # -------------------------------------------------------------------------

    def defered_default(self, flags, scope, token, parent):
        raise TransformError(token, "unexpected defered token")

    def defered_function(self, flags, scope, token, parent):

        scope.updateDeferedBlock()
        scope.updateDefered()

        for defered in scope.defered_functions:
            refs = {**defered.fnrefs, **defered.blrefs}
            if defered.token.type == Token.T_CLASS:
                self._handle_class(scope, defered.token, refs)
            else:
                self._handle_function(scope, defered.token, refs)

    # TODO: remove
    def _handle_function_arg_seq(self, scope, next_scope, token):
        # function argument sequence destructuring

        for pair in token.children:

            if pair.type == Token.T_ASSIGN and pair.value == "=":
                ident_, default_ = pair.children
                next_scope.define(SC_FUNCTION, ident_)
                # process the RHS as a default argument value
                self._push_tokens(ST_VISIT, scope, [default_], pair)
            elif pair.type == Token.T_TEXT:
                # argument with no default
                next_scope.define(SC_FUNCTION, pair)
            else:
                raise TransformError(pair, "not supported for parameter matching")

    # TODO: remove
    def _handle_function_arg_obj(self, scope, next_scope, token):
        # function argument object destructuring
        # identifiers are not minified because the identifier
        # acts as an attribute of an object.

        # to minify, the reference would need to be converted
        # first build a reference:
        #       next_scope.define(SC_NO_MINIFY|SC_FUNCTION, ident_)
        #       ref = next_scope.load(ident_)
        # then update the function body. add a line to unpack
        # the identifier into a new variable
        #       *ref = ident_.value
        # then replace the reference from an identity reference to a
        # minified reference

        for pair in token.children:

            if pair.type == Token.T_ASSIGN and pair.value == "=":
                ident_, default_ = pair.children
                next_scope.define(SC_NO_MINIFY|SC_FUNCTION, ident_)
                # process the RHS as a default argument value
                self._push_tokens(ST_VISIT, scope, [default_], pair)
            elif pair.type == Token.T_TEXT:
                # argument with no default
                next_scope.define(SC_NO_MINIFY|SC_FUNCTION, pair)
            else:
                raise TransformError(pair, "not supported for parameter matching")

    def _handle_function(self, scope, token, refs):

        name = scope.name + "." + token.children[0].value
        parent = VariableScopeReference(scope, refs)
        next_scope = self.newScope(name, parent)

        # finalize the function scope once all children have been processed
        self._push_finalize(next_scope, token, None)
        self._push_defered(next_scope, token, None)

        # define the arguments to the function in the next scope

        block = token.children[2]
        if block.type != Token.T_BLOCK:
            # this line is required to fix lambdas:
            # the block is only updated in the token
            # if a non-trivial transform is used
            if token.type == Token.T_LAMBDA:
                block = Token(Token.T_RETURN, block.line, block.index, "return", [block])
            block = Token(Token.T_BLOCK, block.line, block.index, "{}", [block])

        if token.children[1].type == Token.T_ARGLIST:
            # the arglist may need to be modified to support unpacking objects and lists

            arglist = token.children[1].children
            for index, child in reversed(list(enumerate(arglist))):
                if child.type == Token.T_ASSIGN:
                    # tricky, the rhs is a variable in THIS scope
                    # while the lhs is a variable in the NEXT scope
                    lhs, rhs = child.children
                    if lhs.type in (Token.T_LIST, Token.T_UNPACK_SEQUENCE, Token.T_OBJECT, Token.T_UNPACK_OBJECT, Token.T_GROUPING):
                        ident = Token(Token.T_TEXT, child.line, child.index, "$js$arg$%d" % index)
                        node = self._unpack_fix(lhs, ident)
                        if node:
                            token.children[2] = block
                            node = Token(Token.T_VAR, child.line, child.index, "let", [node])
                            next_scope.define(SC_FUNCTION, ident)
                            child.children[0] = ident
                            block.children.insert(0, node)
                        else:
                            defs = self._unpack_fix_defs(lhs)

                            for tok in defs:
                                next_scope.define(SC_FUNCTION, tok)

                    else:
                        next_scope.define(SC_FUNCTION, lhs)
                    # process the RHS as a default argument value
                    self._push_tokens(ST_VISIT, scope, [rhs], child)
                elif child.type in (Token.T_LIST, Token.T_UNPACK_SEQUENCE, Token.T_OBJECT, Token.T_UNPACK_OBJECT, Token.T_GROUPING):
                    ident = Token(Token.T_TEXT, child.line, child.index, "$js$arg$%d" % index)
                    node = self._unpack_fix(child, ident)
                    if node:
                        token.children[2] = block
                        node = Token(Token.T_VAR, child.line, child.index, "let", [node])
                        next_scope.define(SC_FUNCTION, ident)
                        arglist[index] = ident
                        block.children.insert(0, node)
                    else:
                        defs = self._unpack_fix_defs(child)
                        for tok in defs:
                            next_scope.define(SC_FUNCTION, tok)


                elif child.type == Token.T_SPREAD:
                    tok, = child.children
                    next_scope.define(SC_FUNCTION, tok)
                else:
                    next_scope.define(SC_FUNCTION, child)

        elif token.children[1].type == Token.T_TEXT:
            next_scope.define(SC_FUNCTION, token.children[1])
        else:
            raise TransformError(token, "unexpected token type for function arglist")

        # visit the body of the function in the next scope
        if token.type != Token.T_LAMBDA and token.children[2].type != Token.T_BLOCK:
            # the parser should be run in python mode
            raise TransformError(token.children[2], "expected block in function body")

        if token.children[2].type == Token.T_BLOCK:

            self._hoist_functions(next_scope, token.children[2])

            self._push_children(next_scope, token.children[2])
        else:
            # TODO: this is a hack to get the scoping right
            # for the case of:
            #   a => b => b+a
            block = Token(Token.T_BLOCK, 0, 0, "{}", [token.children[2]])
            self._hoist_functions(next_scope, block)
            self._push_children(next_scope, block)
            #raise TransformError(token.children[2], "expected block in function def")
            #self._push_children(next_scope, token.children[2])

    def _handle_class(self, scope, token, refs):

        name = scope.name + "." + token.children[0].value
        parent = VariableScopeReference(scope, refs)
        next_scope = self.newScope(name, parent)

        self._push_finalize(next_scope, token, None)
        self._push_defered(next_scope, token, None)

        # load the classes that this new class inherits from using the current scope
        self._push_children(scope, token.children[1])



        # load the class name(s) this class extends from
        #if len(token.children[1].children) > 0:
        #    self._push_tokens(0, scope, token.children[1].children, token.children[1])
            #for child in token.children[1].children:
            #    scope.load(child)



        #for child in token.children[2].children:
        #    next_scope.define(SC_FUNCTION, child)
        self._push_children(next_scope, token.children[2])

    # -------------------------------------------------------------------------

    def _push_finalize(self, scope, token, parent, flags=0):
        if parent is not None and not isinstance(parent, Token):
            raise TypeError(type(parent))
        self.seq.append((ST_FINALIZE | flags, scope, token, parent))

    def _push_defered(self, scope, token, parent, flags=0):
        self.seq.append((ST_DEFERED | flags, scope, token, parent))

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

class TransformIdentityScope(TransformAssignScope):
    """
    transform, but does not minify
    """

    def __init__(self):
        super(TransformIdentityScope, self).__init__()

    def newScope(self, name, parentScope=None):
        scope = IdentityScope(name, parentScope)
        scope.disable_warnings = self.disable_warnings
        return scope

class TransformIdentityBlockScope(TransformAssignScope):
    """
    transform, but does not minify
    """

    def __init__(self):
        super(TransformIdentityBlockScope, self).__init__()

    def newScope(self, name, parentScope=None):
        scope = IdentityBlockScope(name, parentScope)
        scope.disable_warnings = self.disable_warnings
        return scope

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

    def newScope(self, name, parentScope=None):
        scope = MinifyVariableScope(name, parentScope)
        scope.disable_warnings = self.disable_warnings
        return scope

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
                rv = self.visit(token, child, index)
                if rv is None:
                    index += 1
                elif isinstance(rv, int):
                    index += rv
                else:
                    raise RuntimeError("visit returned non-integer")

            # once every child has been visited push the available
            # children onto the stack to be processed

            for child in reversed(token.children):
                tokens.append(child)

    def visit(self, parent, token, index):
        raise NotImplementedError()

class TransformReplaceIdentity(TransformBaseV2):
    """
    mangle variable names for the python compiler
    """

    def __init__(self, use_short_name=True):

        super().__init__()

        self.use_short_name = use_short_name

    def visit(self, parent, token, index):

        if token.type == Token.T_GLOBAL_VAR:
            # Note: the old implementation used a mapping of
            #   mangled label -> original label
            # then, after the compiled code was executed, could
            # extract the globals and update the globals dictionary
            # by using the mapping to convert mangled names back to
            # the original name.
            # Now, instead global vars are assumed unique and not mangled.
            return

        if token.ref:
            if not isinstance(token.ref, UndefinedRef):
                if self.use_short_name:
                    token.value = token.ref.short_name()
                else:
                    token.value = token.ref.long_name()

class TransformClassToFunction(TransformBaseV2):
    # TODO: this class should be renamed to reflect new behavior
    #       it will now fix an ast so that it can be compiled.
    # TODO: this transform in mode2 could apply shortname/longname
    #       text transforms from reference to token value

    """

    this transform can be run before or after assiging variable scopes

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

    def visit(self, parent, token, index):

        if token.type == Token.T_LAMBDA:
            self.visit_lambda(parent, token, index)

        elif token.type == Token.T_CLASS:
            self.visit_class(parent, token, index)

    def visit_lambda(self, parent, token, index):

        arglist = token.children[1]
        block = token.children[2]

        # this test used to be performed in the scope transform
        if arglist.type != Token.T_ARGLIST:
            token.children[1] = Token(Token.T_ARGLIST, arglist.line, arglist.index, '()', [arglist])

        # this test used to be performed in the scope transform
        if block.type != Token.T_BLOCK:
            token.children[2] = Token(Token.T_BLOCK, block.line, block.index, '{}',
                [Token(Token.T_RETURN, block.line, block.index, 'return', [block])])

    def visit_class(self, parent, token, index):

        ln = token.line
        co = token.index

        name = token.children[0]
        extends = token.children[1]
        clsbody = token.children[2]

        # mode 1 is the default, for when this transform is run priorto AssignScope
        # mode 2 is used if AssignScope has been run, the Closures must be preserved
        #  -either order should produce identical output

        mode = 1
        if len(token.children) == 4 and token.children[3].type == Token.T_CLOSURE:
            mode = 2 # variable scope has already been run

        constructor = None
        methods = []
        static_methods = []
        static_props = []

        for child in clsbody.children:
            if child.children and child.children[0].value == 'constructor':
                constructor = child
            elif child.type == Token.T_STATIC_PROPERTY:

                if child.children and child.children[0]:
                    gc = child.children and child.children[0]

                    if gc.type == Token.T_ASSIGN and gc.value == "=":
                        static_props.append(gc)

            elif child.type == Token.T_METHOD and child.value == "static":

                static_methods.append(child)

                #raise TransformError(gc, "expected static method declaration or property")

            elif child.type == Token.T_ASSIGN and child.value == "=":
                raise TransformError(gc, "non static default property not supported")
            elif child.type == Token.T_METHOD:
                methods.append(child)

            else:
                raise TransformError(gc, "expected method declaration or property")

        if constructor is None:
            #TODO: for inheritance this will need to call super
            constructor = Token(Token.T_LAMBDA, ln, co, '=>',
                    [Token(Token.T_TEXT, ln, co, 'Anonymous'),
                    Token(Token.T_ARGLIST, ln, co, '()'),
                    Token(Token.T_BLOCK, ln, co, '{}'),
                    ]
                )

            if mode == 2:
                # constructor.append(Token(Token.T_CLOSURE, ln, co, ''))
                constructor.children.append(token.children[3])

        #conbody = constructor.children[2]

        #    constructor.children.append(Token(Token.T_CLOSURE, 0, 0, ""))

        # methods assign to the prototype
        # static methods assign to the class
        # both as functions

        #ln = name.line
        #co = name.index
        #lhs = Token(Token.T_TEXT, ln, co, name.value)
        #rhs = Token(Token.T_ATTR, ln, co, 'prototype')
        #getattr = Token(Token.T_GET_ATTR, ln, co, ".")
        #getattr.children = [lhs, rhs]


        # process all static methods.
        # after the class method is defined, define new methods on
        # the created object by inserting statements that add the attribute
        # TODO: consider an IIFI for inline classes with static methods

        for method in static_methods:
            var = Token(Token.T_GET_ATTR, ln, co, '.', [
                name,
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

            #if self.mode==2:
            #    anonfn.children.append(method.children[3])

            parent.children.insert(index+1, static)

        for prop in static_props:
            var = Token(Token.T_GET_ATTR, ln, co, '.', [
                name,
                Token(Token.T_ATTR, ln, co, prop.children[0].value)
            ])
            static = Token(Token.T_ASSIGN, ln, co, '=', [
                var,
                prop.children[1]
            ])
            parent.children.insert(index+1, static)

        token.type = Token.T_FUNCTION
        token.value = 'function'
        #token.children = []

        arglist = constructor.children[1]
        fnbody = constructor.children[2]

        closure = Token(Token.T_CLOSURE, token.line, token.index, "")

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

            if mode==2:
                anonfn.children.append(method.children[3])

        #token.children.append(name)
        #token.children.append(arglist)
        #token.children.append(fnbody)
        token.children[0] = name
        token.children[1] = arglist
        token.children[2] = fnbody
        # assigning in this way preserves any existing closure
        # token.children[3] = closure

        #if self.mode==2:
        #    token.children.append(closure)

class TransformBaseV3(object):
    def __init__(self):
        super(TransformBaseV3, self).__init__()
        self.tokens = []
        self.processed = 0

    def transform(self, ast):

        self.scan(ast)

    def scan(self, token):

        self.tokens = [(1, token, token)]

        while self.tokens:
            # process tokens from in the order they are discovered. (DFS)
            mode, token, parent = self.tokens.pop()
            self.processed += 1

            if mode==1:
                self.visit(token, parent)
                for child in reversed(token.children):
                    self.tokens.append((1, child, token))
            else:
                self.finalize(token, parent)

    def defer(self, token, parent):
        self.tokens.append((0, token, parent))

    def visit(self, token, parent):
        raise NotImplementedError()

    def finalize(self, token, parent):
        raise NotImplementedError()

is_str = lambda tok : tok.type == Token.T_STRING
is_num = lambda tok : tok.type == Token.T_NUMBER
js_vars = {Token.T_GLOBAL_VAR, Token.T_LOCAL_VAR,}

js_str_ops = {
    "+": operator.concat,
}

js_num_ops = {
    "+": operator.add,
    "-": operator.sub,
    "*": operator.mul,
    "/": operator.truediv,
    "%": operator.mod,
    "**": operator.pow,

    "<<": operator.lshift,
    ">>": operator.rshift,

    "&": operator.and_,
    "|": operator.or_,
    "^": operator.xor,
}

def js_seq_get_attr(obj, key):
    index = literal_eval(key)
    return obj.children[index]

def js_map_get_attr(obj, key):
    index = literal_eval(key)
    return obj.children[index]

class TransformConstEval(TransformBaseV3):

    def __init__(self):
        super().__init__()

        self.constexpr_values = {}

    def visit(self, token, parent):

        if token.type == Token.T_ASSIGN:
            self.defer(token, parent)

        if token.type == Token.T_BINARY:
            self.defer(token, parent)

    def finalize(self, token, parent):

        if token.type == Token.T_ASSIGN:
            self.visit_assign(token, parent)

        if token.type == Token.T_BINARY:
            self.visit_binary(token, parent)

    def resolve_reference(self, token):
        visited = set()
        while token.type in js_vars:
            visited.add(token)

            if not hasattr(token, "ref"):
                break

            ref = token.ref

            if not ref.name:
                raise ValueError("name error")

            if ref.name in self.constexpr_values:
                new_token = self.constexpr_values[ref.name]
                if new_token in visited:
                    break;
                token = new_token
            else:
                break;
        return token

    def visit_assign(self, token, parent):

        lhs, rhs = token.children

        if token.value == "=":

            if hasattr(lhs, "ref") and lhs.type in js_vars:

                ref = lhs.ref

                if parent.type != Token.T_VAR or parent.value != "const":
                    #print("assign failed", parent.type, parent.value)
                    if ref.name in self.constexpr_values:
                        del self.constexpr_values[ref.name]
                else:
                    self.constexpr_values[ref.name] = rhs
                    #print("assign", ref.name, " = ", rhs)
        else:
            # +=, etc not yet supported
            if hasattr(lhs, "ref") and lhs.type in js_vars:
                ref = lhs.ref
                if ref.name in self.constexpr_values:
                    del self.constexpr_values[ref.name]

    def visit_binary(self, token, parent):

        lhs, rhs = token.children

        lhs = self.resolve_reference(lhs)
        rhs = self.resolve_reference(rhs)

        if is_str(lhs) and is_str(rhs):
            lv = literal_eval(lhs)
            rv = literal_eval(rhs)

            if token.value in js_num_ops:
                #print("compute: %s:%d %r%s%r" % (token.file, token.line, lv, token.value, rv))
                token.type = Token.T_STRING
                token.value = repr(js_str_ops[token.value](lv, rv))
                token.children = []

        elif is_num(lhs) and is_num(rhs):
            lv = literal_eval(lhs)
            rv = literal_eval(rhs)

            if token.value in js_num_ops:
                token.type = Token.T_NUMBER
                #print("compute: %s:%d %r%s%r" % (token.file, token.line, lv, token.value, rv))
                token.value = repr(js_num_ops[token.value](lv, rv))
                token.children = []

        elif (is_num(lhs) and is_num(rhs)) or (is_num(lhs) and is_str(rhs)):
            lv = str(literal_eval(lhs))
            rv = str(literal_eval(rhs))
            if token.value == "+":
                #print("compute: %s:%d %r%s%r" % (token.file, token.line, lv, token.value, rv))
                token.type = Token.T_NUMBER
                token.value = repr(lv + rv)
                token.children = []

def getModuleImportExport(ast, warn_include=False):
    """
    returns:
        ast             - the modified ast
        imports         - a dictionary for file_path => list of included names
        module_imports  - a dictionary for module_name => list of included names
        exports         - list of exported names from this ast module
    """
    imports = {}
    module_imports = {}
    exports = []
    i = 0
    while i < len(ast.children):
        token = ast.children[i]

        if token.type == Token.T_INCLUDE:
            if warn_include:
                sys.stdout.write("warning: include found in file that is not a daedalus module\n")

            name = literal_eval(token.children[0])
            imports[name] = []

            ast.children.pop(0)

        elif token.type == Token.T_IMPORT_MODULE:

            fromlist = [] # list of (import_name, target_name)
            for child in token.children[0].children:
                if child.type == Token.T_TEXT:
                    # import name from module
                    fromlist.append((child.value, child.value))
                else:
                    # import name from module and rename
                    fromlist.append((child.children[0].value, child.children[1].value))

            ast.children.pop(0)

            if token.value in module_imports:
                module_imports[token.value].update(dict(fromlist))
            else:
                module_imports[token.value] = dict(fromlist)

        elif token.type == Token.T_IMPORT:
            i += 1

        elif token.type in (Token.T_EXPORT, Token.T_EXPORT_DEFAULT):
            if len(token.children) == 3:
                # export from may need to update includes and exports
                # the from source has not yet been defined.
                # it may be a filepath or an object - undecided
                 raise TransformError(token, "export from not implemented")

            for text in token.children[0].children:
                exports.append(text.value)

            child = token.children[1].children[0]
            # remove the token entirely if it does not have any side effects
            # otherwise remove the export keyword
            if child.type == Token.T_TEXT:
                ast.children.pop(i)
            else:
                ast.children = ast.children[:i] + token.children[1].children + ast.children[i+1:]
                i += len(token.children[1].children)

        else:
            i += 1

    return ast, imports, module_imports, exports

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

        var w = 2
        let z = 2
        {
            let y = 2
            {
                let x = 1
            }
        }
    """

    tokens = Lexer().lex(text)
    parser =  Parser()
    ast = parser.parse(tokens)

    tr = TransformMinifyScope()
    #tr = TransformAssignScope()
    tr.transform(ast)

    print(ast.toString(3))

def main_for():
    from .parser import Parser
    from .formatter import Formatter
    text = """

        class A {}
        class X {}

    """

    tokens = Lexer().lex(text)
    parser =  Parser()
    ast = parser.parse(tokens)

    tr = TransformMinifyScope()
    #tr = TransformAssignScope()
    tr.transform(ast)

    print(ast.toString(3))
    print(Formatter().format(ast))

def main_unpack():
    from .parser import Parser
    from .formatter import Formatter
    text = """

        //{a: {b, c=1}, d=2} = rhs
        //var {lhs:{ op=1 }, rhs:y} = getToken()
        //var {lhs: [x, y=1]} = [0]
        //var [{x, y=3}, z] = [{'x':1,}];
        //var [x=[2][0]] = [];

        //([x,y]) => x + y
        //function f([x,y]){return x + y}
        //function f({x,y}){return x + y}
        //function f({x,y:z}){return x + z}
        //function f([x,y=1]=[]){}
        //function f({x}){}
        //function f({x=1,}={}){}
        //function f({url, method='GET'}={}){return method}

        //x = 123;
        //function f({b}){return x}

        //let [{x1=1, y1=2}, {x2=3,y2=4}] = [{x1,y1}]
        // let [a,b,{d=1,}] = [1,2,{d}]

        //let [a, b] = 0
        //[b, a] = [a, b]

        ({x=1})=>({x,})

    """

    tokens = Lexer().lex(text)
    parser =  Parser()
    ast = parser.parse(tokens)

    print(ast.toString(3))

    tr = TransformMinifyScope()
    # tr = TransformIdentityScope()

    print(tr.transform(ast))

    print(ast.toString(3))
    print(Formatter().format(ast))
    print("--")

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

def main_unused():

    # prune dead code:
    #  use identity transform to detect load count of identifiers
    #  prune unused variables, functions, classes
    #  repeat until nothing is removed
    from .parser import Parser
    from .formatter import Formatter

    mod1_text = """

        let x=0;
        let y=0; // unused

        function f() {
            return x;
        }

        function g() { // unused
            return x;
        }

        export function h() {
            return f()
        }

        // todo:
        //function i() { // unused
        //    return g()
        //}

        h()

    """

    mod2_text = """
        include './mod1.js'
        import module daedalus
        export x = h()
    """

    mod2_text = """
        export function f() {
            try {
                throw "str"
            } catch (ex) {
                console.log(ex)
            }
        }
    """


    text = """
        function f() {
            let x = 1;
            while (true) {

                {
                    break

                    let x = 3
                }
                let x = 2;
            }
            return x;
        }
    """

    text = """

function f() {
                const x = 1;
                {
                    const x = 2;
                }
                return x;
            }
            result=f() // 1

    """

    text = """from module x import {a=b,c} """

    tokens = Lexer().lex(text)
    parser =  Parser()
    ast = parser.parse(tokens)

    xform = TransformIdentityBlockScope()
    xform.transform(ast)


    print(ast.toString(1))
    return

    # level 2 transform:
    #  compare imports and exports across multiple files and modules
    #  for imports and module imports which do not import names
    #  this will have to scan for all GET_ATTR tokens to decide which
    #  names are used and update the reference load count accordingly
    # - this can also be used to detect names that are used and not exported\
    print(ast.toString(1))
    ast, imports, module_imports, exports = getModuleImportExport(ast)
    print(imports)
    print(module_imports)
    print(exports)

    for i in range(1):


        # TODO: be able to run an ast multiple times through the transform
        tr = TransformMinifyScope()
        #tr = TransformIdentityScope()
        tr.transform(ast)

        candidates = set()
        for lbl, _ in tr.globals.items():
            ref = tr.global_scope._getRef(lbl)
            if ref:
                if ref.load_count == 0:
                    #candidates[lbl] = ref
                    candidates.add(ref.token)
                    print(lbl, ref, ref.load_count)
            else:
                ref = tr.global_scope.gscope[lbl]
                print("global:", lbl, ref)

        def fscan(node):
            if node in candidates:
                return True
            for child in node.children:
                if fscan(child):
                    return True
            return False

        i=0;
        while i < len(ast.children):
            node = ast.children[i]

            if fscan(node):
                print("pop", i)
                ast.children.pop(i)
            else:
                i += 1



    print(ast.toString(1))

if __name__ == '__main__':
    main_unused()
