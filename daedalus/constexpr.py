#! cd .. && python3 -m daedalus.constexpr

from .token import Token, TokenError
from .lexer import Lexer, LexError
from .parser import Parser, ParseError

from .transform import TransformIdentityScope, TransformBaseV3

from .compiler import Compiler
from .formatter import Formatter
from .builtins import JsArray, JsObject, JsObjectType
from tests.util import parsecmp

class TransformScope(TransformIdentityScope):

    def visit_lambda(self, flags, scope, token, parent):

        if self.python:

            if token.children[1].type == Token.T_TEXT:
                tok = token.children[1]
                token.children[1] = Token(Token.T_ARGLIST, tok.line, tok.index, '()', [tok])
            if token.children[2].type != Token.T_BLOCK:
                tok = token.children[2]

                token.children[2] = Token(Token.T_BLOCK, tok.line, tok.index, '{}',
                    [Token(Token.T_RETURN, tok.line, tok.index, 'return', [tok])])

        scope.defer(token)

    def finalize_function(self, flags, scope, token, parent):

        scope.popScope()

        closure = Token(Token.T_CLOSURE, 0, 0, "")

        for name in sorted(scope.cellvars):
            closure.children.append(Token(Token.T_CELL_VAR, 0, 0, name))

        for name in sorted(scope.freevars):
            closure.children.append(Token(Token.T_FREE_VAR, 0, 0, name))

        token.children.append(closure)

class TransformConstExpr(TransformBaseV3):
    """
      T_VAR<2,8,'constexpr'>
        T_ASSIGN<2,20,'='>
          T_TEXT<2,18,'a'>
          T_BINARY<2,24,'*'>
            T_NUMBER<2,22,'6'>
            T_NUMBER<2,26,'7'>
      T_ASSIGN<3,11,'='>
        T_TEXT<3,9,'b'>
        T_FUNCTIONCALL<3,22,''>
          T_TEXT<3,13,'constexpr'>
          T_ARGLIST<3,22,'()'>
            T_BINARY<3,25,'+'>
              T_TEXT<3,23,'a'>
              T_NUMBER<3,27,'2'>

    """
    def __init__(self):
        super().__init__()

        self.globals = {}

    def visit(self, token, parent):

        if token.type == Token.T_ASSIGN:
            self.defer(token, parent)

    def finalize(self, token, parent):

        if token.type == Token.T_ASSIGN:
            self.visit_assign(token, parent)

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

    def literalToToken(self, parent, value):

        if isinstance(value, (int, float)):
            return Token(Token.T_NUMBER, parent.line, parent.index, repr(value))

        if isinstance(value, (str)):
            return Token(Token.T_STRING, parent.line, parent.index, repr(value))

        if isinstance(value, (list, JsArray)):
            tok = Token(Token.T_LIST, parent.line, parent.index, "[]")
            for item in value:
                child = self.literalToToken(parent, item)
                if child:
                    tok.children.append(child)
            return tok

        if isinstance(value, (dict, JsObject, JsObjectType)):

            tok = Token(Token.T_OBJECT, parent.line, parent.index, "{}")
            for key, val in value.items():
                lhs = self.literalToToken(parent, key)
                rhs = self.literalToToken(parent, val)
                if lhs and rhs:

                    bin_op = Token(Token.T_BINARY, parent.line, parent.index, ":")
                    bin_op.children = [lhs, rhs]
                    tok.children.append(bin_op)
            return tok

        # JsUndefined

        return None

    def visit_assign(self, token, parent):


        if parent.type != Token.T_VAR or parent.value != "constexpr":
            return

        lhs, rhs = token.children

        target = Token(Token.T_GLOBAL_VAR, lhs.line, lhs.index, lhs.ref.name)
        children = [target, rhs]
        ast = Token(token.type, token.line, token.index, token.value, children)

        cc = Compiler(filename="<string>",
                globals=self.globals,
                flags=Compiler.CF_REPL|Compiler.CF_USE_REF)
        cc._do_compile(ast)

        #cc.dump()
        result = cc.function_body()

        result_value = cc.globals[lhs.ref.name]
        #self.globals[lhs.ref.name] = result_value
        self.globals = cc.globals

        result_token = self.literalToToken(token, result_value)
        print("<", type(result_value))
        print("<", result_token)
        if result_token:
            token.children[1] = result_token

        print("!%s=%s" % (lhs.ref.name, result_value))

def main():  # pragma: no cover
    """
    T_MODULE<''>
      T_VAR<'constexpr'>
        T_ASSIGN<'='>
          T_GLOBAL_VAR<'e'>
          T_LAMBDA<'=>'>
            T_TEXT<'Anonymous'>
            T_ARGLIST<'()'>
              T_LOCAL_VAR<'x'>
            T_BLOCK<'{}'>
              T_RETURN<'return'>
                T_BINARY<'+'>
                  T_LOCAL_VAR<'x'>
                  T_NUMBER<'1'>
            T_CLOSURE<''>
      T_VAR<'constexpr'>
        T_ASSIGN<'='>
          T_GLOBAL_VAR<'f'>
          T_FUNCTIONCALL<''>
            T_GLOBAL_VAR<'e'>
            T_ARGLIST<'()'>
              T_NUMBER<'5'>

    """
    text = """
        //constexpr x = {1:2,3:4}
        //constexpr y = x[1]
        //constexpr e = x => x / 2
        //constexpr f = Math.ceil(e(5))

        constexpr f = () => {
            let y = 0;
            for (let x=0; x < 10; x++) {
                y += x;
            }
            return y;
        }

        constexpr g = f();


    """

    tokens = Lexer().lex(text)
    parser = Parser()
    ast = parser.parse(tokens)
    xform = TransformScope()
    xform.python = False
    xform.transform(ast)
    print(ast.toString(1))

    #parsecmp(ast2, ast)

    TransformConstExpr().transform(ast)
    print(ast.toString(3))
    text_out = Formatter({'minify': False}).format(ast)
    print(text_out)

if __name__ == '__main__':
    main()
