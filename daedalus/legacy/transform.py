

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


def main_var(): # pragma: no cover

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

def main_cls(): # pragma: no cover
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
