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
                   (token.type == Token.T_ANONYMOUS_FUNCTION) or \
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

SC_GLOBAL   = 0x001
SC_FUNCTION = 0x002
SC_BLOCK    = 0x004
SC_CONST    = 0x100

def scope2str(flags):
    text = ""

    if flags&SC_CONST:
        text += "const "

    if flags&SC_GLOBAL:
        text += "global"

    elif flags&SC_FUNCTION:
        text += "function"

    else:
        text += "block"

    return text

class Ref(object):

    def __init__(self, flags, label):
        super(Ref, self).__init__()

        self.flags = flags
        self.label = label
        self._identity = 0

    def identity(self):
        #if self._identity > 0:
        s = 'f' if self.flags&SC_FUNCTION else 'b'

        return "%s#%s%d" % (self.label, s, self._identity)
        #return self.label

    def type(self):
        return Token.T_GLOBAL_VAR if self.flags&SC_GLOBAL else Token.T_LOCAL_VAR

    def isGlobal(self):
        return self.flags&SC_GLOBAL

    def __str__(self):
        return "<*%s>" % (self.identity())

    def __repr__(self):
        return "<*%s>" % (self.identity())

    def clone(self, scflags):
        ref = Ref(scflags, self.label)
        ref._identity = self._identity + 1
        return ref

class UndefinedRef(Ref):
    def identity(self):
        return self.label

class VariableScope(object):
    # require three scope instances, for global, function and block scope
    def __init__(self, parent=None):
        super(VariableScope, self).__init__()
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
        self.fnscope = {}
        self.blscope = [{}]
        self.all_labels = set()

        if parent:
            self.depth = parent.depth + 1
        else:
            self.depth = 0

    def _getScope(self, scflags):

        if scflags&SC_GLOBAL:
            scope = self
            while scope.parent is not None:
                scope = scope.parent
            return scope.fnscope, None
        elif scflags&SC_FUNCTION:
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

    def _define_block(self, label):

        if label in self.blscope[-1]:
            raise TokenError(token, "already defined at this scope")

        for bl in reversed(self.blscope):
            if label in bl:
                return bl[label]

        return None

    def _define_function(self, label):

        if label in self.fnscope:
            return self.fnscope[label]

        return None

    def define(self, scflags, token):

        label = token.value

        if scflags&SC_FUNCTION:
            ref = self._define_function(label)
        else:
            ref = self._define_block(label)

        if self.parent is None:
            scflags |= SC_GLOBAL

        if ref is not None:
            # define, but give a new identity
            new_ref = ref.clone(scflags)
        else:
            new_ref = Ref(scflags, label)

        identifier = new_ref.identity()

        self.all_labels.add(label)

        self.vars.add(identifier)

        if scflags&SC_FUNCTION:
            self.fnscope[label] = new_ref
        else:
            if len(self.blscope) == 0:
                raise TokenError(token, "block scope not defined")
            self.blscope[-1][label] = new_ref

        token.value = identifier
        if token.type == Token.T_TEXT:
            token.type = new_ref.type()

        print("define name", self.depth, token.value, scope2str(scflags))

        return new_ref

    def _load_store(self, token, load):

        label = token.value
        ref = None

        # search for the scope the defines this label
        scopes = [self]
        while scopes[-1]:

            if label in scopes[-1].fnscope:
                break

            if any([label in bl for bl in scopes[-1].blscope]):
                break

            scopes.append(scopes[-1].parent)

        if scopes[-1] is None:
            # not found in an existing scope
            if load:
                # attempting to load an undefined reference
                if label in self.all_labels:
                    raise TokenError(token, "read from deleted var")

                ref = UndefinedRef(0, label)
                token.type = Token.T_GLOBAL_VAR
            else:
                # define this reference in this scope
                ref = self.define(SC_BLOCK, token)

        elif scopes[-1] is not self:
            # found in a parent scope
            scope = scopes[-1]

            ref = self._getRef(scope, label)

            if not ref.isGlobal():
                token.type = Token.T_FREE_VAR
                scope.cellvars.add(ref.identity())
                for scope2 in scopes[:-1]:
                    scope2.freevars.add(ref.identity())

        else:
            ref = self._getRef(self, label)

        if ref is None:
            raise TokenError(token, "identity error")

        token.value = ref.identity()
        if token.type == Token.T_TEXT:
            token.type = ref.type()

        print("load__" if load else "store_", "name", self.depth, token.value, scope2str(ref.flags))

        return ref

    def load(self, token):
        return self._load_store(token, True)

    def store(self, token):
        return self._load_store(token, False)

    def pushBlockScope(self):
        self.blscope.append({})

    def popBlockScope(self):
        return self.blscope.pop()

    def _diag(self, token):
        print("%10s" % token.type, list(self.vars), list(self.freevars), list(self.cellvars))

ST_MASK     = 0x000FF
ST_SCOPE_MASK     = 0xFFF00
ST_VISIT    = 0x001
ST_FINALIZE = 0x002
ST_STORE    = 0x100
ST_GLOBAL   = SC_GLOBAL << 12
ST_FUNCTION = SC_FUNCTION << 12
ST_BLOCK    = SC_BLOCK << 12
ST_CONST    = SC_CONST << 12

def _diag(tag, token, flags=0):
    text1 = scope2str((flags&ST_SCOPE_MASK)>>12)
    print(tag, text1, token.type, token.value, token.line, token.index)

class TransformAssignScope(object):

    """
    Assign scoping rules to variables

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

    Variable Scoping

        No special transformation is needed in python to support var

        Variables defined using var are function scoped

        Example 1:

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

        self.global_scope = None

        self.visit_mapping = {
            Token.T_ASSIGN: self.visit_assign,
            Token.T_FUNCTION: self.visit_function,
            Token.T_ANONYMOUS_FUNCTION: self.visit_anonymous_function,
            Token.T_LAMBDA: self.visit_lambda,
            Token.T_BLOCK: self.visit_block,
            Token.T_MODULE: self.visit_module,
            Token.T_TEXT: self.visit_text,
            Token.T_VAR: self.visit_var,

            Token.T_GROUPING: self.visit_error,
        }

        self.finalize_mapping = {
            Token.T_BLOCK: self.finalize_block,
            Token.T_MODULE: self.finalize_module,

            Token.T_FUNCTION: self.finalize_function,
            Token.T_ANONYMOUS_FUNCTION: self.finalize_function,
            Token.T_LAMBDA: self.finalize_function,

        }

        self.states = {
            ST_VISIT: self.visit_mapping,
            ST_FINALIZE: self.finalize_mapping
        }

        self.state_defaults = {
            ST_VISIT: self.visit_default,
            ST_FINALIZE: self.finalize_default,
        }

    def transform(self, ast):

        self.seq = [self.initialState(ast)]

        self._transform(ast)

    def _transform(self, token):

        while self.seq:
            # process tokens from in the order they are discovered. (DFS)
            flags, scope, token, parent = self.seq.pop()

            fn = self.states[flags&ST_MASK].get(token.type, None)

            if fn:
                fn(flags, scope, token, parent)

            else:
                fn = self.state_defaults[flags&ST_MASK]
                fn(flags, scope, token, parent)

    def initialState(self, token):

        return (ST_VISIT, VariableScope(), token, None)

    # -------------------------------------------------------------------------

    def visit_default(self, flags, scope, token, parent):

        self._push_children(scope, token, flags)

    def visit_error(self, flags, scope, token, parent):
        raise TokenError(token, "invalid token")

    def visit_module(self, flags, scope, token, parent):
        self._push_finalize(scope, token, parent)
        self._push_children(scope, token, flags)

    def visit_block(self, flags, scope, token, parent):

        if parent and parent.type in [Token.T_LAMBDA, Token.T_FUNCTION, Token.T_ANONYMOUS_FUNCTION]:
            pass
        else:
            scope.pushBlockScope()

        self._push_finalize(scope, token, parent)
        self._push_children(scope, token, flags)

    def visit_function(self, flags, scope, token, parent):
        scflags = (flags&ST_SCOPE_MASK) >> 12
        scope.define(scflags, token.children[0])

        next_scope = VariableScope(scope)

        for child in token.children[1].children:
            next_scope.define(SC_FUNCTION, child)

        self._push_finalize(next_scope, token, parent)
        self._push_tokens((ST_VISIT|(flags&ST_SCOPE_MASK)), next_scope, token.children[1:], token)

    def visit_anonymous_function(self, flags, scope, token, parent):

        next_scope = VariableScope(scope)

        self._push_finalize(next_scope, token, parent)
        self._push_children(next_scope, token, flags)

    def visit_lambda(self, flags, scope, token, parent):

        next_scope = VariableScope(scope)

        self._push_finalize(next_scope, token, parent)
        self._push_children(next_scope, token, flags)

    def visit_var(self, flags, scope, token, parent):
        flags = 0
        if token.value == 'var':
            flags = ST_FUNCTION
        if token.value == 'let':
            flags = ST_BLOCK
        if token.value == 'const':
            flags = ST_BLOCK|ST_CONST
        self._push_children(scope, token, flags)

    def visit_assign(self, flags, scope, token, parent):

        # TODO: LHS can be more complicated that T_TEXT
        if token.value == "=":

           self._push_tokens(ST_VISIT|ST_STORE|(flags&ST_SCOPE_MASK), scope, [token.children[0]], parent)
           self._push_tokens(ST_VISIT|(flags&ST_SCOPE_MASK), scope, [token.children[1]], parent)

        else:
            self._push_children(scope, token, flags)

    def visit_text(self, flags, scope, token, parent):
        # note: this only works because the parser implementation of
        # let/var/const wonky. the keyword is parsed after the equals sign
        # and any commas
        scflags = (flags&ST_SCOPE_MASK) >> 12

        if scflags:
            scope.define(scflags, token)
        elif flags&ST_STORE:
            scope.store(token)
        else:
            scope.load(token)

    # -------------------------------------------------------------------------

    def finalize_default(self, flags, scope, token, parent):
        scope._diag(token)

    def finalize_module(self, flags, scope, token, parent):
        scope._diag(token)

        if scope.cellvars or scope.freevars:
            raise TokenError(token, "unexpected closure")

    def finalize_block(self, flags, scope, token, parent):
        scope._diag(token)

        if parent and parent.type in [Token.T_LAMBDA, Token.T_FUNCTION, Token.T_ANONYMOUS_FUNCTION]:
            pass
        else:
            vars = scope.popBlockScope()
            for var in vars.values():
                token.children.append(Token(Token.T_DELETE_VAR, token.line, token.index, var.identity()))

    def finalize_function(self, flags, scope, token, parent):

        closure = Token(Token.T_CLOSURE, 0, 0, "")

        for name in sorted(scope.cellvars):
            closure.children.append(Token(Token.T_CELL_VAR, 0, 0, name))

        for name in sorted(scope.freevars):
            closure.children.append(Token(Token.T_FREE_VAR, 0, 0, name))

        token.children.append(closure)

        scope._diag(token)

    # -------------------------------------------------------------------------

    def _push_finalize(self, scope, token, parent, flags=0):
        self.seq.append((ST_FINALIZE|flags, scope, token, parent))

    def _push_children(self, scope, token, flags):
        for child in reversed(token.children):
            self.seq.append((ST_VISIT|(flags&ST_SCOPE_MASK), scope, child, token))

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




class TransformClassToFunction(TransformBase):
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

    Transform:

        function Shape() {
            this.area = () => { return this.width * this.height }

            this.width = 5
            this.height = 5

        }

    Use the constructor as a function body and insert arrow functions
    into the body of the function
    """
    def visit(self, token, parent):

        pass

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
    function main() {
        function f1(x) {
            return f1(x-1)
        }
    }
    """


    tokens = Lexer().lex(text1)
    ast = Parser().parse(tokens)

    lines1 = ast.toString().split("\n")

    tr = TransformAssignScope()
    tr.transform(ast)

    lines2 = ast.toString().split("\n")


    seq, cor, sub, ins, del_ = edit_distance(lines1, lines2, lambda x,y: x==y)
    print("")
    print(len(lines1), len(lines2))
    print("")

    while len(lines1) < len(lines2):
        lines1.append("")

    while len(lines2) < len(lines1):
        lines2.append("")

    #for i, (l1, l2) in enumerate(zip(lines1, lines2)):
    for i, (l1, l2) in enumerate(seq):
        c = ' ' if l1 == l2 else '|'
        print("%3d: %-50s %s %-50s" % (i+1,l1, c, l2))

if __name__ == '__main__':
    main_var()