#! cd .. && python3 -m tests.parser_test


import unittest
from tests.util import edit_distance, parsecmp, TOKEN

from daedalus.lexer import Token, Lexer
from daedalus.parser import Parser as ParserBase, ParseError

class Parser(ParserBase):
    def __init__(self):
        super(Parser, self).__init__()
        self.disable_all_warnings = True

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

    def test_001_parse_brace(self):

        with self.assertRaises(ParseError):
            text = "{{{ }}"
            Parser().parse(Lexer().lex(text))

    def test_001_parse_paren(self):

        with self.assertRaises(ParseError):
            text = "("
            Parser().parse(Lexer().lex(text))

    def test_001_parse_bracket(self):

        with self.assertRaises(ParseError):
            text = "["
            Parser().parse(Lexer().lex(text))

    def test_001_hard(self):

        text = """{[0](){}}"""
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_OBJECT', '{}',
                TOKEN('T_FUNCTION', '',
                    TOKEN('T_LIST', '[]',
                        TOKEN('T_NUMBER', '0')),
                    TOKEN('T_ARGLIST', '()'),
                    TOKEN('T_BLOCK', '{}'))))
        self.assertFalse(parsecmp(expected, ast, False))

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
            TOKEN('T_ASSIGN', '=',
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
            TOKEN('T_ASSIGN', '=',
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
                TOKEN('T_SPREAD', '...',
                    TOKEN('T_TEXT', 'a')))
        )

        self.assertFalse(parsecmp(expected, ast, False))

    def test_001_tagged_template(self):

        text = "myTag`b${c}a`"
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_TAGGED_TEMPLATE', '',
                TOKEN('T_TEXT', 'myTag'),
                TOKEN('T_TEMPLATE_STRING', '`b${c}a`',
                    TOKEN('T_STRING', 'b'),
                    TOKEN('T_TEMPLATE_EXPRESSION', 'c',
                        TOKEN('T_TEXT', 'c')),
                    TOKEN('T_STRING', 'a'))))

        self.assertFalse(parsecmp(expected, ast, False))

class ParserBinOpTestCase(unittest.TestCase):

    def test_001_assign(self):

        text = "x = 1"
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_ASSIGN', '=',
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

    def test_001_mul(self):

        text = "x * 1"
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_BINARY', '*',
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

    def test_001_divide_2(self):

        text = "x = ((1/2)/3)"
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_ASSIGN', '=',
                TOKEN('T_TEXT', 'x'),
                TOKEN('T_GROUPING', '()',
                    TOKEN('T_BINARY', '/',
                        TOKEN('T_GROUPING', '()',
                            TOKEN('T_BINARY', '/',
                                TOKEN('T_NUMBER', '1'),
                                TOKEN('T_NUMBER', '2'))),
                        TOKEN('T_NUMBER', '3'))))
        )

        self.assertFalse(parsecmp(expected, ast, False))

    def test_001_attribute(self):

        text = "a.b"
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_GET_ATTR', '.',
                TOKEN('T_TEXT', 'a'),
                TOKEN('T_ATTR', 'b'))
        )

        self.assertFalse(parsecmp(expected, ast, False))

    def test_001_sub_assign(self):

        text = "a -= b"
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_ASSIGN', '-=',
                TOKEN('T_TEXT', 'a'),
                TOKEN('T_TEXT', 'b'))
        )

        self.assertFalse(parsecmp(expected, ast, False))


    def test_001_add_assign(self):

        text = "a += b"
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_ASSIGN', '+=',
                TOKEN('T_TEXT', 'a'),
                TOKEN('T_TEXT', 'b'))
        )

        self.assertFalse(parsecmp(expected, ast, False))

    def test_001_multiply_assign(self):

        text = "a *= b"
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_ASSIGN', '*=',
                TOKEN('T_TEXT', 'a'),
                TOKEN('T_TEXT', 'b'))
        )

        self.assertFalse(parsecmp(expected, ast, False))

    def test_001_div_assign(self):

        text = "a /= b"
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_ASSIGN', '/=',
                TOKEN('T_TEXT', 'a'),
                TOKEN('T_TEXT', 'b'))
        )

        self.assertFalse(parsecmp(expected, ast, False))

    def test_001_exp_assign(self):

        text = "a **= b"
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_ASSIGN', '**=',
                TOKEN('T_TEXT', 'a'),
                TOKEN('T_TEXT', 'b'))
        )

        self.assertFalse(parsecmp(expected, ast, False))

    def test_001_null_assign(self):

        text = "a ??= b"
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_ASSIGN', '??=',
                TOKEN('T_TEXT', 'a'),
                TOKEN('T_TEXT', 'b'))
        )

        self.assertFalse(parsecmp(expected, ast, False))

    def test_001_or_assign(self):

        text = "a ||= b"
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_ASSIGN', '||=',
                TOKEN('T_TEXT', 'a'),
                TOKEN('T_TEXT', 'b'))
        )

        self.assertFalse(parsecmp(expected, ast, False))

    def test_001_and_assign(self):

        text = "a &&= b"
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_ASSIGN', '&&=',
                TOKEN('T_TEXT', 'a'),
                TOKEN('T_TEXT', 'b'))
        )

        self.assertFalse(parsecmp(expected, ast, False))

    def test_001_logical_or_assign(self):

        text = "a |= b"
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_ASSIGN', '|=',
                TOKEN('T_TEXT', 'a'),
                TOKEN('T_TEXT', 'b'))
        )

        self.assertFalse(parsecmp(expected, ast, False))

    def test_001_logical_and_assign(self):

        text = "a &= b"
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_ASSIGN', '&=',
                TOKEN('T_TEXT', 'a'),
                TOKEN('T_TEXT', 'b'))
        )

        self.assertFalse(parsecmp(expected, ast, False))

    def test_001_bitwise_not(self):

        text = "~ b"
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_PREFIX', '~',
                TOKEN('T_TEXT', 'b'))
        )

        self.assertFalse(parsecmp(expected, ast, False))

    def test_001_lshift_assign(self):

        text = "a <<= b"
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_ASSIGN', '<<=',
                TOKEN('T_TEXT', 'a'),
                TOKEN('T_TEXT', 'b'))
        )

        self.assertFalse(parsecmp(expected, ast, False))

    def test_001_rshift_assign(self):

        text = "a >>= b"
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_ASSIGN', '>>=',
                TOKEN('T_TEXT', 'a'),
                TOKEN('T_TEXT', 'b'))
        )

        self.assertFalse(parsecmp(expected, ast, False))

    def test_001_unsigned_rshift(self):

        text = "a >>> b"
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_BINARY', '>>>',
                TOKEN('T_TEXT', 'a'),
                TOKEN('T_TEXT', 'b'))
        )

        self.assertFalse(parsecmp(expected, ast, False))

    def test_001_unsigned_rshift_assign(self):

        text = "a >>>= b"
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_ASSIGN', '>>>=',
                TOKEN('T_TEXT', 'a'),
                TOKEN('T_TEXT', 'b'))
        )

        self.assertFalse(parsecmp(expected, ast, False))

    def test_001_null_coalescing_v1(self):

        text = "a??b"
        tokens = Lexer().lex(text)
        parser = Parser()

        ast = parser.parse(tokens)
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_BINARY', '??',
                TOKEN('T_TEXT', 'a'),
                TOKEN('T_TEXT', 'b')))

        self.assertFalse(parsecmp(expected, ast, False))


    def test_001_optional_chaining_v1(self):

        text = "a?.b"
        tokens = Lexer().lex(text)
        parser = Parser()
        parser.feat_xform_optional_chaining = False

        ast = parser.parse(tokens)
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_OPTIONAL_CHAINING', '?.',
                TOKEN('T_TEXT', 'a'),
                TOKEN('T_ATTR', 'b'))
        )

        self.assertFalse(parsecmp(expected, ast, False))

    def test_001_optional_chaining_v2(self):

        text = "a?.b"
        tokens = Lexer().lex(text)
        parser = Parser()
        parser.feat_xform_optional_chaining = True

        ast = parser.parse(tokens)
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_BINARY', '.',
                TOKEN('T_GROUPING', '()',
                    TOKEN('T_BINARY', '||',
                        TOKEN('T_GROUPING', '()',
                            TOKEN('T_TEXT', 'a')),
                        TOKEN('T_OBJECT', '{}'))),
                TOKEN('T_ATTR', 'b')))

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

    def test_001_subscr_3a(self):

        text = "x?.[0]"
        tokens = Lexer().lex(text)
        parser = Parser()
        parser.feat_xform_optional_chaining = True

        ast = parser.parse(tokens)
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_SUBSCR', '[]',
                TOKEN('T_GROUPING', '()',
                    TOKEN('T_BINARY', '||',
                        TOKEN('T_GROUPING', '()',
                            TOKEN('T_TEXT', 'x')),
                        TOKEN('T_OBJECT', '{}'))),
                TOKEN('T_NUMBER', '0')))

        self.assertFalse(parsecmp(expected, ast, False))

    def test_001_subscr_3b(self):

        text = "x?.[0]"
        tokens = Lexer().lex(text)
        parser = Parser()
        parser.feat_xform_optional_chaining = False

        ast = parser.parse(tokens)
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_OPTIONAL_CHAINING', '?.',
                TOKEN('T_SUBSCR', '[]',
                    TOKEN('T_TEXT', 'x'),
                    TOKEN('T_NUMBER', '0'))))

        self.assertFalse(parsecmp(expected, ast, False))

    def test_001_assign_newline(self):

        text = """a = b =
            f()"""
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        expected = TOKEN('T_MODULE', '',
                    TOKEN('T_ASSIGN', '=',
                        TOKEN('T_TEXT', 'a'),
                        TOKEN('T_ASSIGN', '=',
                            TOKEN('T_TEXT', 'b'),
                            TOKEN('T_FUNCTIONCALL', '',
                                TOKEN('T_TEXT', 'f'),
                                TOKEN('T_ARGLIST', '()')))))

        self.assertFalse(parsecmp(expected, ast, False))

    def test_001_destructure_assign(self):

        text = "var [a,b,c] = d"
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_VAR', 'var',
                TOKEN('T_ASSIGN', '=',
                    TOKEN('T_UNPACK_SEQUENCE', '[]',
                        TOKEN('T_TEXT', 'a'),
                        TOKEN('T_TEXT', 'b'),
                        TOKEN('T_TEXT', 'c')),
                    TOKEN('T_TEXT', 'd'))))

        self.assertFalse(parsecmp(expected, ast, False))

    def test_001_destructure_assign_2(self):
        text = """
            var [x=[2][0]] = [];
        """
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_VAR', 'var',
                TOKEN('T_ASSIGN', '=',
                    TOKEN('T_UNPACK_SEQUENCE', '[]',
                        TOKEN('T_TEXT', 'a'),
                        TOKEN('T_TEXT', 'b'),
                        TOKEN('T_TEXT', 'c')),
                    TOKEN('T_TEXT', 'd'))))

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
                TOKEN('T_TEXT', 'x'),
                TOKEN('T_ASSIGN', '=',
                    TOKEN('T_TEXT', 'y'),
                    TOKEN('T_NUMBER', '1'))))

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
                    TOKEN('T_ASSIGN', '=',
                        TOKEN('T_TEXT', 'x'),
                        TOKEN('T_NUMBER', '0')),
                    TOKEN('T_BREAK', 'break'),
                    TOKEN('T_DEFAULT', 'default'),
                    TOKEN('T_ASSIGN', '=',
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
                        TOKEN('T_ASSIGN', '=',
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
            TOKEN('T_EXPORT', 'export',
                TOKEN('T_VAR', 'const',
                    TOKEN('T_ASSIGN', '=',
                        TOKEN('T_TEXT', 'v1'),
                        TOKEN('T_KEYWORD', 'null'))),
                TOKEN('T_TEXT', 'v1')))

        self.assertFalse(parsecmp(expected, ast, False))

    def test_001_export_function(self):

        text = "export function a() {}"
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_EXPORT', 'export',
                TOKEN('T_FUNCTION', 'function',
                    TOKEN('T_TEXT', 'a'),
                    TOKEN('T_ARGLIST', '()'),
                    TOKEN('T_BLOCK', '{}')),
                TOKEN('T_TEXT', 'a')))

        self.assertFalse(parsecmp(expected, ast, False))

    def test_001_export_class(self):

        text = "export class A {}"
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_EXPORT', 'export',
                TOKEN('T_CLASS', 'class',
                    TOKEN('T_TEXT', 'A'),
                    TOKEN('T_KEYWORD', 'extends'),
                    TOKEN('T_CLASS_BLOCK', '{}')),
                TOKEN('T_TEXT', 'A')))

        self.assertFalse(parsecmp(expected, ast, False))

    def test_001_export_many(self):

        text = "export let v1, v2"
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_EXPORT', 'export',
                TOKEN('T_VAR', 'let',
                    TOKEN('T_TEXT', 'v1'),
                    TOKEN('T_TEXT', 'v2')),
                TOKEN('T_TEXT', 'v1'),
                TOKEN('T_TEXT', 'v2')))

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
                TOKEN('T_GET_ATTR', '.',
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
                    TOKEN('T_ARGLIST', '()',
                        TOKEN('T_TEXT', 'ex')),
                    TOKEN('T_BLOCK', '{}')),
                TOKEN('T_FINALLY', 'finally',
                    TOKEN('T_BLOCK', '{}')))
        )

        self.assertFalse(parsecmp(expected, ast, False))

    def test_001_lambda_assign(self):
        """
        this test can only pass if binary operators
        are collected right-to-left and the arrow
        operator is treated at the same precedence
        """
        text = """
            const f = (d,k,v) => d[k] = v
        """
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_VAR', 'const',
                TOKEN('T_ASSIGN', '=',
                    TOKEN('T_TEXT', 'f'),
                    TOKEN('T_LAMBDA', '=>',
                        TOKEN('T_TEXT', 'Anonymous'),
                        TOKEN('T_ARGLIST', '()',
                            TOKEN('T_TEXT', 'd'),
                            TOKEN('T_TEXT', 'k'),
                            TOKEN('T_TEXT', 'v')
                        ),
                        TOKEN('T_ASSIGN', '=',
                            TOKEN('T_SUBSCR', '',
                                TOKEN('T_TEXT', 'd'),
                                TOKEN('T_TEXT', 'k'))
                            ),
                            TOKEN('T_TEXT', 'v')
                        )
                    )
                )
            )

        self.assertFalse(parsecmp(expected, ast, False))

class ParserFunctionTestCase(unittest.TestCase):

    def test_001_anonymous_function(self):

        text = "function (x) {return x;}"
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_ANONYMOUS_FUNCTION', 'function',
                TOKEN('T_TEXT', 'Anonymous'),
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
            TOKEN('T_LAMBDA', '=>',
                Token(Token.T_TEXT, 1, 3, 'Anonymous'),
                TOKEN('T_ARGLIST', '()'),
                TOKEN('T_OBJECT', '{}'))
        )

        self.assertFalse(parsecmp(expected, ast, False))

    def test_001_lambda_2(self):

        text = "(a, b, c) => {}"
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_LAMBDA', '=>',
                Token(Token.T_TEXT, 1, 3, 'Anonymous'),
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
            TOKEN('T_LAMBDA', '=>',
                Token(Token.T_TEXT, 1, 3, 'Anonymous'),
                TOKEN('T_TEXT', 'a'),
                TOKEN('T_TEXT', 'b'))
        )

        self.assertFalse(parsecmp(expected, ast, False))

    def test_001_void_iife(self):

        text = """
            void function iife() {
                console.log("test")
            }();
        """
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_PREFIX', 'void',
                TOKEN('T_FUNCTIONCALL', '',
                    TOKEN('T_FUNCTION', 'function',
                        TOKEN('T_TEXT', 'iife'),
                        TOKEN('T_ARGLIST', '()'),
                        TOKEN('T_BLOCK', '{}',
                            TOKEN('T_FUNCTIONCALL', '',
                                TOKEN('T_GET_ATTR', '.',
                                    TOKEN('T_TEXT', 'console'),
                                    TOKEN('T_ATTR', 'log')),
                                TOKEN('T_ARGLIST', '()',
                                    TOKEN('T_STRING', '"test"'))))),
                    TOKEN('T_ARGLIST', '()'))))

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
                TOKEN('T_CLASS_BLOCK', '{}'))
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
                TOKEN('T_CLASS_BLOCK', '{}'))
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
                TOKEN('T_CLASS_BLOCK', '{}'))
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
                TOKEN('T_CLASS_BLOCK', '{}',
                    TOKEN('T_METHOD', '',
                        TOKEN('T_TEXT', 'onClick'),
                        TOKEN('T_ARGLIST', '()',
                            TOKEN('T_TEXT', 'event')),
                        TOKEN('T_BLOCK', '{}'))))
        )

        self.assertFalse(parsecmp(expected, ast, False))

    def test_001_class_5(self):

        text = "class A extends X.Y {}"
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_CLASS', 'class',
                TOKEN('T_TEXT', 'A'),
                TOKEN('T_KEYWORD', 'extends',
                    TOKEN('T_GET_ATTR', '.',
                        TOKEN('T_TEXT', 'X'),
                        TOKEN('T_ATTR', 'Y'))),
                TOKEN('T_CLASS_BLOCK', '{}'))
        )

        self.assertFalse(parsecmp(expected, ast, False))

class ParserChallengeTestCase(unittest.TestCase):

    def _assert(self, expected, text, debug=False):
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        self.assertFalse(parsecmp(expected, ast, debug))

    def test_001_challenge_1(self):
        # a complicated unsafe true/false branch

        text = "if (true) a=b=c; else d=f;"
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_BRANCH', 'if',
                TOKEN('T_ARGLIST', '()',
                    TOKEN('T_KEYWORD', 'true')),
                TOKEN('T_ASSIGN', '=',
                    TOKEN('T_TEXT', 'a'),
                    TOKEN('T_ASSIGN', '=',
                        TOKEN('T_TEXT', 'b'),
                        TOKEN('T_TEXT', 'c'))),
                TOKEN('T_ASSIGN', '=',
                    TOKEN('T_TEXT', 'd'),
                    TOKEN('T_TEXT', 'f'))))
        self._assert(expected, text)

    def test_001_challenge_2(self):
        # a useless for loop

        text = "for(;!((t=o1).y1&&t.y2||t===o2););"
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_FOR', 'for',
                TOKEN('T_ARGLIST', '()',
                    TOKEN('T_EMPTY_TOKEN', ''),
                    TOKEN('T_PREFIX', '!',
                        TOKEN('T_GROUPING', '()',
                            TOKEN('T_LOGICAL_OR', '||',
                                TOKEN('T_LOGICAL_AND', '&&',
                                    TOKEN('T_GET_ATTR', '.',
                                        TOKEN('T_GROUPING', '()',
                                            TOKEN('T_ASSIGN', '=',
                                                TOKEN('T_TEXT', 't'),
                                                TOKEN('T_TEXT', 'o1'))),
                                        TOKEN('T_ATTR', 'y1')),
                                    TOKEN('T_GET_ATTR', '.',
                                        TOKEN('T_TEXT', 't'),
                                        TOKEN('T_ATTR', 'y2'))),
                                TOKEN('T_BINARY', '===',
                                    TOKEN('T_TEXT', 't'),
                                    TOKEN('T_TEXT', 'o2'))))),
                    TOKEN('T_EMPTY_TOKEN', '')),
                TOKEN('T_BLOCK', '{}')))
        self._assert(expected, text)

    def test_001_challenge_3(self):
        text = "a?b?c:d:e"
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_TERNARY', '?',
                TOKEN('T_TEXT', 'a'),
                TOKEN('T_TERNARY', '?',
                    TOKEN('T_TEXT', 'b'),
                    TOKEN('T_TEXT', 'c'),
                    TOKEN('T_TEXT', 'd')),
                TOKEN('T_TEXT', 'e')))
        self._assert(expected, text)

    def test_001_challenge_4(self):
        text = "a?b?c?c:c:b:a"
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_TERNARY', '?',
                TOKEN('T_TEXT', 'a'),
                TOKEN('T_TERNARY', '?',
                    TOKEN('T_TEXT', 'b'),
                    TOKEN('T_TERNARY', '?',
                        TOKEN('T_TEXT', 'c'),
                        TOKEN('T_TEXT', 'c'),
                        TOKEN('T_TEXT', 'c')),
                    TOKEN('T_TEXT', 'b')),
                TOKEN('T_TEXT', 'a')))
        self._assert(expected, text)

    def test_001_challenge_5(self):
        text = "a?b:a?a?b:a?b:c:c"
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_TERNARY', '?',
                TOKEN('T_TEXT', 'a'),
                TOKEN('T_TEXT', 'b'),
                TOKEN('T_TERNARY', '?',
                    TOKEN('T_TEXT', 'a'),
                    TOKEN('T_TERNARY', '?',
                        TOKEN('T_TEXT', 'a'),
                        TOKEN('T_TEXT', 'b'),
                        TOKEN('T_TERNARY', '?',
                            TOKEN('T_TEXT', 'a'),
                            TOKEN('T_TEXT', 'b'),
                            TOKEN('T_TEXT', 'c'))),
                    TOKEN('T_TEXT', 'c'))))
        self._assert(expected, text)

    def test_001_challenge_6(self):
        text = "a2?b2:c2?d2?e2:f2?g2:h2:i2;"
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_TERNARY', '?',
                TOKEN('T_TEXT', 'a2'),
                TOKEN('T_TEXT', 'b2'),
                TOKEN('T_TERNARY', '?',
                    TOKEN('T_TEXT', 'c2'),
                    TOKEN('T_TERNARY', '?',
                        TOKEN('T_TEXT', 'd2'),
                        TOKEN('T_TEXT', 'e2'),
                        TOKEN('T_TERNARY', '?',
                            TOKEN('T_TEXT', 'f2'),
                            TOKEN('T_TEXT', 'g2'),
                            TOKEN('T_TEXT', 'h2'))),
                    TOKEN('T_TEXT', 'i2'))))
        self._assert(expected, text)


    def test_001_challenge_7(self):
        # a for loop with unsafe block
        # confuses what is a arglist or function call
        text = "for(x in y)(a)[i]&&e[i].apply(x,f)"
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_FOR_IN', 'for',
                TOKEN('T_TEXT', 'x'),
                TOKEN('T_TEXT', 'y'),
                TOKEN('T_LOGICAL_AND', '&&',
                    TOKEN('T_SUBSCR', '',
                        TOKEN('T_GROUPING', '()',
                            TOKEN('T_TEXT', 'a')),
                        TOKEN('T_TEXT', 'i')),
                    TOKEN('T_FUNCTIONCALL', '',
                        TOKEN('T_GET_ATTR', '.',
                            TOKEN('T_SUBSCR', '',
                                TOKEN('T_TEXT', 'e'),
                                TOKEN('T_TEXT', 'i')),
                            TOKEN('T_ATTR', 'apply')),
                        TOKEN('T_ARGLIST', '()',
                            TOKEN('T_TEXT', 'x'),
                            TOKEN('T_TEXT', 'f'))))))
        self._assert(expected, text)

    def test_001_challenge_8(self):
        # inner for loop order of operations
        text = "for(a in b=c)d;"
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_FOR_IN', 'for',
                TOKEN('T_TEXT', 'a'),
                TOKEN('T_ASSIGN', '=',
                    TOKEN('T_TEXT', 'b'),
                    TOKEN('T_TEXT', 'c')),
                TOKEN('T_TEXT', 'd')))
        self._assert(expected, text)

    def test_001_challenge_9(self):
        # inner for loop order of operations
        text = "for(a=b,c=d;e<f;g++) h;"
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_FOR', 'for',
                TOKEN('T_ARGLIST', '()',
                    TOKEN('T_COMMA', ',',
                        TOKEN('T_ASSIGN', '=',
                            TOKEN('T_TEXT', 'a'),
                            TOKEN('T_TEXT', 'b')),
                        TOKEN('T_ASSIGN', '=',
                            TOKEN('T_TEXT', 'c'),
                            TOKEN('T_TEXT', 'd'))),
                    TOKEN('T_BINARY', '<',
                        TOKEN('T_TEXT', 'e'),
                        TOKEN('T_TEXT', 'f')),
                    TOKEN('T_POSTFIX', '++',
                        TOKEN('T_TEXT', 'g'))),
                TOKEN('T_TEXT', 'h')))
        self._assert(expected, text)

    def test_001_challenge_10(self):
        # inner for loop order of operations
        text = "var a;for(b=c;d<e;f++)for(g in h=i)j;"
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_VAR', 'var',
                TOKEN('T_TEXT', 'a')),
            TOKEN('T_FOR', 'for',
                TOKEN('T_ARGLIST', '()',
                    TOKEN('T_ASSIGN', '=',
                        TOKEN('T_TEXT', 'b'),
                        TOKEN('T_TEXT', 'c')),
                    TOKEN('T_BINARY', '<',
                        TOKEN('T_TEXT', 'd'),
                        TOKEN('T_TEXT', 'e')),
                    TOKEN('T_POSTFIX', '++',
                        TOKEN('T_TEXT', 'f'))),
                TOKEN('T_FOR_IN', 'for',
                    TOKEN('T_TEXT', 'g'),
                    TOKEN('T_ASSIGN', '=',
                        TOKEN('T_TEXT', 'h'),
                        TOKEN('T_TEXT', 'i')),
                    TOKEN('T_TEXT', 'j'))))
        self._assert(expected, text)

    def test_001_challenge_11(self):
        # inner for loop order of operations
        text = """
            if("object"==typeof t)for(var n in t)this._on(n,t[n],i)else for(var o=0,s=(
                          t=d(t)).length;o<s;o++)this._on(t[o],i,e);
            """
        expected = TOKEN('T_MODULE', '',
    TOKEN('T_BRANCH', 'if',
        TOKEN('T_ARGLIST', '()',
            TOKEN('T_BINARY', '==',
                TOKEN('T_STRING', '"object"'),
                TOKEN('T_PREFIX', 'typeof',
                    TOKEN('T_TEXT', 't')))),
        TOKEN('T_FOR_IN', 'for',
            TOKEN('T_VAR', 'var',
                TOKEN('T_TEXT', 'n')),
            TOKEN('T_TEXT', 't'),
            TOKEN('T_FUNCTIONCALL', '',
                TOKEN('T_GET_ATTR', '.',
                    TOKEN('T_KEYWORD', 'this'),
                    TOKEN('T_ATTR', '_on')),
                TOKEN('T_ARGLIST', '()',
                    TOKEN('T_TEXT', 'n'),
                    TOKEN('T_SUBSCR', '',
                        TOKEN('T_TEXT', 't'),
                        TOKEN('T_TEXT', 'n')),
                    TOKEN('T_TEXT', 'i')))),
        TOKEN('T_FOR', 'for',
            TOKEN('T_ARGLIST', '()',
                TOKEN('T_VAR', 'var',
                    TOKEN('T_COMMA', ',',
                        TOKEN('T_ASSIGN', '=',
                            TOKEN('T_TEXT', 'o'),
                            TOKEN('T_NUMBER', '0')),
                        TOKEN('T_ASSIGN', '=',
                            TOKEN('T_TEXT', 's'),
                            TOKEN('T_GET_ATTR', '.',
                                TOKEN('T_GROUPING', '()',
                                    TOKEN('T_ASSIGN', '=',
                                        TOKEN('T_TEXT', 't'),
                                        TOKEN('T_FUNCTIONCALL', '',
                                            TOKEN('T_TEXT', 'd'),
                                            TOKEN('T_ARGLIST', '()',
                                                TOKEN('T_TEXT', 't'))))),
                                TOKEN('T_ATTR', 'length'))))),
                TOKEN('T_BINARY', '<',
                    TOKEN('T_TEXT', 'o'),
                    TOKEN('T_TEXT', 's')),
                TOKEN('T_POSTFIX', '++',
                    TOKEN('T_TEXT', 'o'))),
            TOKEN('T_FUNCTIONCALL', '',
                TOKEN('T_GET_ATTR', '.',
                    TOKEN('T_KEYWORD', 'this'),
                    TOKEN('T_ATTR', '_on')),
                TOKEN('T_ARGLIST', '()',
                    TOKEN('T_SUBSCR', '',
                        TOKEN('T_TEXT', 't'),
                        TOKEN('T_TEXT', 'o')),
                    TOKEN('T_TEXT', 'i'),
                    TOKEN('T_TEXT', 'e'))))))
        self._assert(expected, text)

    def test_001_challenge_11(self):
        text = """ a?"str"in b:c """
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_TERNARY', '?',
                TOKEN('T_TEXT', 'a'),
                TOKEN('T_BINARY', 'in',
                    TOKEN('T_STRING', '"str"'),
                    TOKEN('T_TEXT', 'b')),
                TOKEN('T_TEXT', 'c')))
        self._assert(expected, text)

    def test_001_challenge_11(self):
        text = """ a=x?b=y:c=z """
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_ASSIGN', '=',
                TOKEN('T_TEXT', 'a'),
                TOKEN('T_TERNARY', '?',
                    TOKEN('T_TEXT', 'x'),
                    TOKEN('T_ASSIGN', '=',
                        TOKEN('T_TEXT', 'b'),
                        TOKEN('T_TEXT', 'y')),
                    TOKEN('T_ASSIGN', '=',
                        TOKEN('T_TEXT', 'c'),
                        TOKEN('T_TEXT', 'z')))))
        self._assert(expected, text)

class ParserModuleTestCase(unittest.TestCase):
    """

            import {name} from './modules/module.js';
            import {name as foo} from './modules/module.js';
            import {name1, name2} from './modules/module.js';
            import {name1 as foo, name2 as bar} from './modules/module.js';
            import * as Module from './modules/module.js';
    """

    def test_001_import_export(self):

        # test that all import/export combinations can
        # be parsed without any issues

        # TODO: remove support for
        #   'import foo'
        #   'import foo.bar'
        # TODO: add support for import module as:
        #
        # daedalus import modes:
        #   from module <name> import {<names>}
        #   import module <name>
        #   import module <name> as <name>
        #   include <path>

        text = """
            from module foo import {bar}
            from module foo.bar import {baz}
            import module foo.bar
            from foo import {bar}
            from foo.bar import {baz}
            import foo
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
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)

    def test_001_module(self):
        text = "import { name } from './module/module.js'"
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_IMPORT_JS_MODULE', "'./module/module.js'",
                TOKEN('T_TEXT', 'name')))

        self.assertFalse(parsecmp(expected, ast, False))

    def test_002_module(self):
        text = "import { name1, name2 } from './module/module.js'"
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_IMPORT_JS_MODULE', "'./module/module.js'",
                TOKEN('T_TEXT', 'name1'),
                TOKEN('T_TEXT', 'name2')))
        self.assertFalse(parsecmp(expected, ast, False))

    def test_003_module(self):
        text = "import {a as b} from './module/module.js'"
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_IMPORT_JS_MODULE', "'./module/module.js'",
                TOKEN('T_KEYWORD', 'as',
                    TOKEN('T_TEXT', 'a'),
                    TOKEN('T_TEXT', 'b'))))

        self.assertFalse(parsecmp(expected, ast, False))

    def test_004_module(self):
        text = "import {a as b, c as d} from './module/module.js'"
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_IMPORT_JS_MODULE', "'./module/module.js'",
                TOKEN('T_KEYWORD', 'as',
                    TOKEN('T_TEXT', 'a'),
                    TOKEN('T_TEXT', 'b')),
                TOKEN('T_KEYWORD', 'as',
                    TOKEN('T_TEXT', 'c'),
                    TOKEN('T_TEXT', 'd'))))

        self.assertFalse(parsecmp(expected, ast, False))

    def test_005_module(self):
        text = "import * as module from './module/module.js'"
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_IMPORT_JS_MODULE_AS', "'./module/module.js'",
                TOKEN('T_TEXT', 'module')))

        self.assertFalse(parsecmp(expected, ast, False))

def main():
    unittest.main()


if __name__ == '__main__':
    main()
