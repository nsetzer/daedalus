

import unittest
from tests.util import edit_distance

from daedalus.lexer import Token, Lexer
from daedalus.parser import Parser, ParseError

def tokcmp(a, b):
    if a is None:
        return False
    if b is None:
        return False

    _, tok1 = a
    _, tok2 = b

    return tok1.type == tok2.type and tok1.value == tok2.value

def parsecmp(expected, actual, debug=False):

    a = actual.flatten()
    b = expected.flatten()

    seq, cor, sub, ins, del_ = edit_distance(a, b, tokcmp)

    error_count = sub + ins + del_
    if error_count > 0 or debug:
        print("\n--- %-50s | --- %-.50s" % ("    HYP", "    REF"))
        for a, b in seq:
            c = ' ' if tokcmp(a, b) else '|'
            if not a:
                a = (0, None)
            if not b:
                b = (0, None)
            print("%3d %-50r %s %3d %-.50r" % (a[0], a[1], c, b[0], b[1]))
        print(actual.toString(2))
    return error_count

def TOKEN(t,v,*children):
    return Token(getattr(Token,t), 1, 0, v, children)

class ParserTestCase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        pass

    @classmethod
    def tearDownClass(cls):
        pass

    def setUp(self):
        super().setUp()

    def tearDown(self):
        super().tearDown()

class ParserUnaryOpTestCase(unittest.TestCase):

    def test_001_unary_prefix(self):

        text = "++x"
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_PREFIX', '++',
                TOKEN('T_TEXT', 'x'))
        )

        self.assertFalse(parsecmp(expected, ast, False))

    def test_001_unary_postfix(self):

        text = "x++"
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_POSTFIX', '++',
                TOKEN('T_TEXT', 'x'))
        )

        self.assertFalse(parsecmp(expected, ast, False))

    def test_001_prefix_plus(self):

        text = "x=+1"
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_BINARY', '=',
                TOKEN('T_TEXT', 'x'),
                TOKEN('T_PREFIX', '+',
                    TOKEN('T_NUMBER', '1')))
        )

        self.assertFalse(parsecmp(expected, ast, False))

    def test_001_postfix_minus(self):

        text = "x=-1"
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_BINARY', '=',
                TOKEN('T_TEXT', 'x'),
                TOKEN('T_PREFIX', '-',
                    TOKEN('T_NUMBER', '1')))
        )

        self.assertFalse(parsecmp(expected, ast, False))

    def test_001_prefix_delete(self):

        text = "delete x"
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_PREFIX', 'delete',
                TOKEN('T_TEXT', 'x'))
        )

        self.assertFalse(parsecmp(expected, ast, False))

    def test_001_spread(self):

        text = "{...a}"
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_OBJECT', '{}',
                TOKEN('T_PREFIX', '...',
                    TOKEN('T_TEXT', 'a')))
        )

        self.assertFalse(parsecmp(expected, ast, False))

class ParserBinOpTestCase(unittest.TestCase):

    def test_001_assign(self):

        text = "x = 1"
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_BINARY', '=',
                TOKEN('T_TEXT', 'x'),
                TOKEN('T_NUMBER', '1'))
        )

        self.assertFalse(parsecmp(expected, ast, False))

    def test_001_add(self):

        text = "x + 1"
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_BINARY', '+',
                TOKEN('T_TEXT', 'x'),
                TOKEN('T_NUMBER', '1'))
        )

        self.assertFalse(parsecmp(expected, ast, False))

    def test_001_subtract(self):

        text = "x - 1"
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_BINARY', '-',
                TOKEN('T_TEXT', 'x'),
                TOKEN('T_NUMBER', '1'))
        )

        self.assertFalse(parsecmp(expected, ast, False))

    def test_001_divide(self):

        text = "x / 1"
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_BINARY', '/',
                TOKEN('T_TEXT', 'x'),
                TOKEN('T_NUMBER', '1'))
        )

        self.assertFalse(parsecmp(expected, ast, False))

    def test_001_attribute(self):

        text = "a.b"
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_BINARY', '.',
                TOKEN('T_TEXT', 'a'),
                TOKEN('T_ATTR', 'b'))
        )

        self.assertFalse(parsecmp(expected, ast, False))

    def test_001_maybe_attribute(self):

        text = "a?.b"
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_BINARY', '?.',
                TOKEN('T_TEXT', 'a'),
                TOKEN('T_ATTR', 'b'))
        )

        self.assertFalse(parsecmp(expected, ast, False))

    def test_001_ternary(self):

        text = "a?b:c"
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_TERNARY', '?',
                TOKEN('T_TEXT', 'a'),
                TOKEN('T_TEXT', 'b'),
                TOKEN('T_TEXT', 'c'))
        )

        self.assertFalse(parsecmp(expected, ast, False))

    def test_001_subscr_1(self):

        text = "x[]"
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_SUBSCR', '',
                TOKEN('T_TEXT', 'x'))
        )

        self.assertFalse(parsecmp(expected, ast, False))

    def test_001_subscr_2(self):

        text = "x[0]"
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_SUBSCR', '',
                TOKEN('T_TEXT', 'x'),
                TOKEN('T_NUMBER', '0'))
        )

        self.assertFalse(parsecmp(expected, ast, False))

    @unittest.skip("not implemented")
    def test_001_subscr_3(self):

        text = "x?.[0]"
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_SUBSCR', '',
                TOKEN('T_TEXT', 'x'))
        )

        self.assertFalse(parsecmp(expected, ast, False))

class ParserBinOpErrorTestCase(unittest.TestCase):

    def test_001_assign(self):

        text = "a ? b c d "
        tokens = Lexer().lex(text)
        with self.assertRaises(ParseError) as ctxt:
            Parser().parse(tokens)

class ParserKeywordTestCase(unittest.TestCase):

    def test_001_let(self):

        text = "let x, y=1"
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_VAR', 'let',
                TOKEN('T_COMMA', ',',
                    TOKEN('T_TEXT', 'x'),
                    TOKEN('T_BINARY', '=',
                        TOKEN('T_TEXT', 'y'),
                        TOKEN('T_NUMBER', '1'))))
        )

        self.assertFalse(parsecmp(expected, ast, False))

    def test_001_break(self):

        text = "break"
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        expected = TOKEN('T_MODULE', '', TOKEN('T_BREAK', 'break'))

        self.assertFalse(parsecmp(expected, ast, False))

    def test_001_continue(self):

        text = "continue"
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        expected = TOKEN('T_MODULE', '', TOKEN('T_CONTINUE', 'continue'))

        self.assertFalse(parsecmp(expected, ast, False))

    def test_001_switch(self):

        text = """
        switch (a) {
            case 0:
            x=0;
            break;
            default:
            x=1;
            break;
        }
        """
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_SWITCH', 'switch',
                TOKEN('T_GROUPING', '()',
                    TOKEN('T_TEXT', 'a')),
                TOKEN('T_BLOCK', '{}',
                    TOKEN('T_CASE', 'case',
                        TOKEN('T_NUMBER', '0')),
                    TOKEN('T_BINARY', '=',
                        TOKEN('T_TEXT', 'x'),
                        TOKEN('T_NUMBER', '0')),
                    TOKEN('T_BREAK', 'break'),
                    TOKEN('T_DEFAULT', 'default'),
                    TOKEN('T_BINARY', '=',
                        TOKEN('T_TEXT', 'x'),
                        TOKEN('T_NUMBER', '1')),
                    TOKEN('T_BREAK', 'break')))
        )

        self.assertFalse(parsecmp(expected, ast, False))

    def test_001_branch_1(self):

        text = "if (true) {}"
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_BRANCH', 'if',
                TOKEN('T_ARGLIST', '()',
                    TOKEN('T_KEYWORD', 'true')),
                TOKEN('T_BLOCK', '{}'))
        )

        self.assertFalse(parsecmp(expected, ast, False))

    def test_001_branch_2(self):

        text = "if (true) {} else {}"
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_BRANCH', 'if',
                TOKEN('T_ARGLIST', '()',
                    TOKEN('T_KEYWORD', 'true')),
                TOKEN('T_BLOCK', '{}'),
                TOKEN('T_BLOCK', '{}'))
        )

        self.assertFalse(parsecmp(expected, ast, False))

    def test_001_branch_3(self):

        text = "if (true) {} else if (false) {}"
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_BRANCH', 'if',
                TOKEN('T_ARGLIST', '()',
                    TOKEN('T_KEYWORD', 'true')),
                TOKEN('T_BLOCK', '{}'),
                TOKEN('T_BRANCH', 'if',
                    TOKEN('T_ARGLIST', '()',
                        TOKEN('T_KEYWORD', 'false')),
                    TOKEN('T_BLOCK', '{}')))
        )

        self.assertFalse(parsecmp(expected, ast, False))

    def test_001_branch_4(self):

        text = "if (true) {} else if (false) {} else {}"
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_BRANCH', 'if',
                TOKEN('T_ARGLIST', '()',
                    TOKEN('T_KEYWORD', 'true')),
                TOKEN('T_BLOCK', '{}'),
                TOKEN('T_BRANCH', 'if',
                    TOKEN('T_ARGLIST', '()',
                        TOKEN('T_KEYWORD', 'false')),
                    TOKEN('T_BLOCK', '{}'),
                    TOKEN('T_BLOCK', '{}')))
        )

        self.assertFalse(parsecmp(expected, ast, False))

    def test_001_new_1(self):

        text = "new A()"
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_NEW', 'new',
                TOKEN('T_FUNCTIONCALL', '',
                    TOKEN('T_TEXT', 'A'),
                    TOKEN('T_ARGLIST', '()')))
        )

        self.assertFalse(parsecmp(expected, ast, False))

    def test_001_new_2(self):

        text = "new A"
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_NEW', 'new',
                TOKEN('T_TEXT', 'A'))
        )

        self.assertFalse(parsecmp(expected, ast, False))

    def test_001_while_1(self):

        text = "while (true)  { x; }"
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_WHILE', 'while',
                TOKEN('T_ARGLIST', '()',
                    TOKEN('T_KEYWORD', 'true')),
                TOKEN('T_BLOCK', '{}',
                    TOKEN('T_TEXT', 'x')))
        )

        self.assertFalse(parsecmp(expected, ast, False))

    def test_001_dowhile_1(self):

        text = "do { x; } while (true);"
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_DOWHILE', 'do',
                TOKEN('T_BLOCK', '{}',
                    TOKEN('T_TEXT', 'x')),
                TOKEN('T_ARGLIST', '()',
                    TOKEN('T_KEYWORD', 'true')))
        )

        self.assertFalse(parsecmp(expected, ast, False))

    def test_001_for(self):

        text = "for (let x=0; x < 5; x++) {}"
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_FOR', 'for',
                TOKEN('T_ARGLIST', '()',
                    TOKEN('T_VAR', 'let',
                        TOKEN('T_BINARY', '=',
                            TOKEN('T_TEXT', 'x'),
                            TOKEN('T_NUMBER', '0'))),
                    TOKEN('T_BINARY', '<',
                        TOKEN('T_TEXT', 'x'),
                        TOKEN('T_NUMBER', '5')),
                    TOKEN('T_POSTFIX', '++',
                        TOKEN('T_TEXT', 'x'))),
                TOKEN('T_BLOCK', '{}'))
        )

        self.assertFalse(parsecmp(expected, ast, False))

    def test_001_import_js(self):

        text = "import './file.js'"
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_IMPORT', './file.js',
                TOKEN('T_OBJECT', '{}'))
        )

        self.assertFalse(parsecmp(expected, ast, False))

    def test_001_import_mod(self):

        text = "import mod with {NamedExport}"
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_IMPORT', 'mod',
                TOKEN('T_OBJECT', '{}',
                    TOKEN('T_TEXT', 'NamedExport')))
        )

        self.assertFalse(parsecmp(expected, ast, False))

    def test_001_import_mod_path(self):

        text = "import a.b.c with {NamedExport}"
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_IMPORT', 'a.b.c',
                TOKEN('T_OBJECT', '{}',
                    TOKEN('T_TEXT', 'NamedExport')))
        )

        self.assertFalse(parsecmp(expected, ast, False))

    def test_001_export_var(self):

        text = "export const v1=null"
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_EXPORT', 'v1',
                TOKEN('T_VAR', 'const',
                    TOKEN('T_BINARY', '=',
                        TOKEN('T_TEXT', 'v1'),
                        TOKEN('T_KEYWORD', 'null'))))
        )

        self.assertFalse(parsecmp(expected, ast, False))

    def test_001_export_function(self):

        text = "export function a() {}"
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_EXPORT', 'a',
                TOKEN('T_FUNCTION', 'function',
                    TOKEN('T_TEXT', 'a'),
                    TOKEN('T_ARGLIST', '()'),
                    TOKEN('T_BLOCK', '{}')))
        )

        self.assertFalse(parsecmp(expected, ast, False))

    def test_001_export_class(self):

        text = "export class A {}"
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_EXPORT', 'A',
                TOKEN('T_CLASS', 'class',
                    TOKEN('T_TEXT', 'A'),
                    TOKEN('T_KEYWORD', 'extends'),
                    TOKEN('T_BLOCK', '{}')))
        )

        self.assertFalse(parsecmp(expected, ast, False))

    @unittest.skip("not implemented")
    def test_001_export_many(self):

        text = "export let v1, v2"
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        expected = TOKEN('T_MODULE', '')

        self.assertFalse(parsecmp(expected, ast, False))

    def test_001_super_constructor_1(self):

        text = "super()"
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_FUNCTIONCALL', '',
                TOKEN('T_KEYWORD', 'super'),
                TOKEN('T_ARGLIST', '()'))
        )

        self.assertFalse(parsecmp(expected, ast, False))

    def test_001_super_function_1(self):

        text = "super.onClick()"
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_FUNCTIONCALL', '',
                TOKEN('T_BINARY', '.',
                    TOKEN('T_KEYWORD', 'super'),
                    TOKEN('T_ATTR', 'onClick')),
                TOKEN('T_ARGLIST', '()'))
        )

        self.assertFalse(parsecmp(expected, ast, False))

    def test_001_try_catch(self):

        text = """
            try {
                throw 0;
            } catch (ex) {

            } finally {

            }
        """
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_TRY', 'try',
                TOKEN('T_BLOCK', '{}',
                    TOKEN('T_THROW', 'throw',
                        TOKEN('T_NUMBER', '0'))),
                TOKEN('T_CATCH', 'catch',
                    TOKEN('T_GROUPING', '()',
                        TOKEN('T_TEXT', 'ex')),
                    TOKEN('T_BLOCK', '{}')),
                TOKEN('T_FINALLY', 'finally',
                    TOKEN('T_OBJECT', '{}')))
        )

        self.assertFalse(parsecmp(expected, ast, False))

class ParserFunctionTestCase(unittest.TestCase):

    def test_001_anonymous_function(self):

        text = "function (x) {return x;}"
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_FUNCTIONDEF', '',
                TOKEN('T_KEYWORD', 'function'),
                TOKEN('T_ARGLIST', '()',
                    TOKEN('T_TEXT', 'x')),
                TOKEN('T_BLOCK', '{}',
                    TOKEN('T_RETURN', 'return',
                        TOKEN('T_TEXT', 'x'))))
        )

        self.assertFalse(parsecmp(expected, ast, False))

    def test_001_named_function(self):

        text = "function example(x) {return x;}"
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_FUNCTION', 'function',
                TOKEN('T_TEXT', 'example'),
                TOKEN('T_ARGLIST', '()',
                    TOKEN('T_TEXT', 'x')),
                TOKEN('T_BLOCK', '{}',
                    TOKEN('T_RETURN', 'return',
                        TOKEN('T_TEXT', 'x'))))
        )

        self.assertFalse(parsecmp(expected, ast, False))

    def test_001_lambda_1(self):

        text = "() => {}"
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_BINARY', '=>',
                TOKEN('T_ARGLIST', '()'),
                TOKEN('T_OBJECT', '{}'))
        )

        self.assertFalse(parsecmp(expected, ast, False))

    def test_001_lambda_2(self):

        text = "(a, b, c) => {}"
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_BINARY', '=>',
                TOKEN('T_ARGLIST', '()',
                    TOKEN('T_TEXT', 'a'),
                    TOKEN('T_TEXT', 'b'),
                    TOKEN('T_TEXT', 'c')),
                TOKEN('T_OBJECT', '{}'))
        )

        self.assertFalse(parsecmp(expected, ast, False))

    def test_001_lambda_3(self):

        text = "a => b"
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_BINARY', '=>',
                TOKEN('T_TEXT', 'a'),
                TOKEN('T_TEXT', 'b'))
        )

        self.assertFalse(parsecmp(expected, ast, False))

class ParserClassTestCase(unittest.TestCase):

    def test_001_class_1(self):

        text = "class {}"
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_CLASS', 'class',
                TOKEN('T_TEXT', ''),
                TOKEN('T_KEYWORD', 'extends'),
                TOKEN('T_BLOCK', '{}'))
        )

        self.assertFalse(parsecmp(expected, ast, False))

    def test_001_class_2(self):

        text = "class A {}"
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_CLASS', 'class',
                TOKEN('T_TEXT', 'A'),
                TOKEN('T_KEYWORD', 'extends'),
                TOKEN('T_BLOCK', '{}'))
        )

        self.assertFalse(parsecmp(expected, ast, False))

    def test_001_class_3(self):

        text = "class A extends B {}"
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_CLASS', 'class',
                TOKEN('T_TEXT', 'A'),
                TOKEN('T_KEYWORD', 'extends',
                    TOKEN('T_TEXT', 'B')),
                TOKEN('T_BLOCK', '{}'))
        )

        self.assertFalse(parsecmp(expected, ast, False))

    def test_001_class_4(self):

        text = """
            class A extends B {
                onClick(event) {

                }
            }
        """
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_CLASS', 'class',
                TOKEN('T_TEXT', 'A'),
                TOKEN('T_KEYWORD', 'extends',
                    TOKEN('T_TEXT', 'B')),
                TOKEN('T_BLOCK', '{}',
                    TOKEN('T_FUNCTIONDEF', '',
                        TOKEN('T_TEXT', 'onClick'),
                        TOKEN('T_ARGLIST', '()',
                            TOKEN('T_TEXT', 'event')),
                        TOKEN('T_OBJECT', '{}'))))
        )

        self.assertFalse(parsecmp(expected, ast, False))

def main():
    unittest.main()

if __name__ == '__main__':
    main()
