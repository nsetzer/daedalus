#! cd .. && python3 -m tests.lexer_test

import io
import unittest

from daedalus.lexer import Token, LexerBase, Lexer, TokenError, LexError
from tests.util import edit_distance

def tokcmp(a, b):
    if a is None:
        return False
    if b is None:
        return False
    return a.type == b.type and a.value == b.value

def lexcmp(expected, actual, debug=False):

    seq, cor, sub, ins, del_ = edit_distance(actual, expected, tokcmp)
    error_count = sub + ins + del_
    if error_count > 0 or debug:
        print("\ncor: %d sub: %d ins: %d del: %d" % (cor, sub, ins, del_))
        print("token error rate:", error_count / (1 + len(expected)))
        print("\n%-50s | %-.50s" % ("    HYP", "    REF"))
        for a, b in seq:
            c = ' ' if tokcmp(a, b) else '|'
            print("%-50r %s %-.50r" % (a, c, b))
    return error_count

class TokenTestCase(unittest.TestCase):

    def test_001_toString(self):
        token = Token(Token.T_NUMBER, 1, 0, '3.14')
        self.assertEqual(token.toString(), "T_NUMBER<1,0,'3.14'>\n")

class LexerBaseTestCase(unittest.TestCase):

    def test_001_getstr(self):
        """lexer should accept input from a file-like object"""

        lexer = LexerBase()
        lexer._init("1234567890", Token.T_TEXT)
        s = lexer._getstr(3)
        self.assertEqual(s, "123")

    def test_001_getstr_stop_iteration(self):
        """lexer should accept input from a file-like object"""

        lexer = LexerBase()
        lexer._init("12", Token.T_TEXT)

        with self.assertRaises(StopIteration):
            lexer._getstr(3)

class LexerInputTestCase(unittest.TestCase):

    def test_001_stream(self):
        """lexer should accept input from a file-like object"""

        text = io.StringIO("3.14")
        expected = [
            Token(Token.T_NUMBER, 1, 0, '3.14'),
        ]
        tokens = list(Lexer().lex(text))

        self.assertFalse(lexcmp(expected, tokens, False))

    def test_002_int(self):
        """lexer should accept input from a string"""

        text = "3.14"
        expected = [
            Token(Token.T_NUMBER, 1, 0, '3.14'),
        ]
        tokens = list(Lexer().lex(text))

        self.assertFalse(lexcmp(expected, tokens, False))


    def test_002_str_1(self):
        """lexer should accept input from a string"""

        text = "'3.14'"
        expected = [
            Token(Token.T_STRING, 1, 0, "'3.14'"),
        ]
        tokens = list(Lexer().lex(text))

        self.assertFalse(lexcmp(expected, tokens, False))

    def test_002_str_2(self):
        """lexer should accept input from a string"""

        text = "'abc' \n 'def'"
        expected = [
            Token(Token.T_STRING, 1, 0, "'abcdef'"),
            Token(Token.T_NEWLINE, 1, 0, ""),
        ]
        tokens = list(Lexer().lex(text))

        self.assertFalse(lexcmp(expected, tokens, False))

    def test_002_str_3(self):
        """lexer should convert utf32 sequences to utf16"""

        text = "'\\U0001f441'"
        expected = [
            Token(Token.T_STRING, 1, 0, "'\\uD83D\\uDC41'"),
        ]
        tokens = list(Lexer().lex(text))

        self.assertFalse(lexcmp(expected, tokens, False))

    def test_003_multiline(self):

        text = "x;\ny;\n\na + \\\n b; "
        expected = [
            Token(Token.T_TEXT, 1, 0, 'x'),
            Token(Token.T_SPECIAL, 1, 1, ';'),
            Token(Token.T_NEWLINE, 2, 0, ''),
            Token(Token.T_TEXT, 2, 0, 'y'),
            Token(Token.T_SPECIAL, 2, 1, ';'),
            Token(Token.T_NEWLINE, 3, 0, ''),
            Token(Token.T_TEXT, 3, 1, 'a'),
            Token(Token.T_SPECIAL, 3, 3, '+'),
            Token(Token.T_TEXT, 4, 1, 'b'),
            Token(Token.T_SPECIAL, 4, 2, ';'),
        ]
        tokens = list(Lexer().lex(text))

        self.assertFalse(lexcmp(expected, tokens, False))

    def test_004_comment(self):

        text = "// comment \n x "
        expected = [
            Token(Token.T_NEWLINE, 2, 0, ''),
            Token(Token.T_TEXT, 1, 0, 'x'),
        ]
        tokens = list(Lexer().lex(text))

        self.assertFalse(lexcmp(expected, tokens, False))

    def test_004_comment_v2(self):
        # triggers a StopIteration while parsing
        text = "// comment"
        expected = [
        ]
        tokens = list(Lexer().lex(text))

        self.assertFalse(lexcmp(expected, tokens, False))

    def test_005_multiline_comment(self):

        text = " /* comment \n more text */ x "
        expected = [
            Token(Token.T_TEXT, 1, 0, 'x'),
        ]
        tokens = list(Lexer().lex(text))

        self.assertFalse(lexcmp(expected, tokens, False))

    def test_005_multiline_comment_stop_iteration_v1(self):

        text = " /* comment"

        with self.assertRaises(LexError) as e:
            Lexer().lex(text)

    def test_005_multiline_comment_stop_iteration_v2(self):

        text = " /* comment *"
        with self.assertRaises(LexError) as e:
            Lexer().lex(text)

    def test_006_multiline_doc(self):

        text = " /** comment \n more text */ x "
        expected = [
            Token(Token.T_DOCUMENTATION, 1, 3, '/** comment \n more text */'),
            Token(Token.T_TEXT, 2, 14, 'x')
        ]
        tokens = list(Lexer({'preserve_documentation': True}).lex(text))

        self.assertFalse(lexcmp(expected, tokens, False))

    def test_006_multiline_doc_stop_iteration_v1(self):
        text = " /** comment \n more text"
        with self.assertRaises(LexError) as e:
            Lexer({'preserve_documentation': True}).lex(text)

    def test_006_multiline_doc_stop_iteration_v2(self):
        text = " /** comment \n more text *"
        with self.assertRaises(LexError) as e:
            Lexer({'preserve_documentation': True}).lex(text)

class LexerInputErrorTestCase(unittest.TestCase):

    def test_001_expected_newline(self):

        text = " x \\ b"
        with self.assertRaises(LexError) as e:
            Lexer().lex(text)

        self.assertTrue("expected newline" in str(e.exception))

    def test_001_unterminated_string_v1(self):
        text = " x = 'abc"
        with self.assertRaises(LexError) as e:
            Lexer().lex(text)

        self.assertTrue("unterminated string" in str(e.exception))

    def test_001_unterminated_string_v2(self):
        text = " x = 'abc\ndef'"
        with self.assertRaises(LexError) as e:
            Lexer().lex(text)

        self.assertTrue("unterminated string" in str(e.exception))

    def test_001_expected_character(self):
        text = " x = '\\"
        with self.assertRaises(LexError) as e:
            Lexer().lex(text)

        self.assertTrue("expected character" in str(e.exception))

class LexerBasicTestCase(unittest.TestCase):

    def test_001_expr_assign_label(self):
        text = "x = a"
        expected = [
            Token(Token.T_TEXT, 1, 0, 'x'),
            Token(Token.T_SPECIAL, 1, 2, '='),
            Token(Token.T_TEXT, 1, 4, 'a'),
        ]
        tokens = list(Lexer().lex(text))

        self.assertFalse(lexcmp(expected, tokens, False))

    def test_002_expr_assign_number(self):
        text = "x = 123"
        expected = [
            Token(Token.T_TEXT, 1, 0, 'x'),
            Token(Token.T_SPECIAL, 1, 2, '='),
            Token(Token.T_NUMBER, 1, 4, '123'),
        ]
        tokens = list(Lexer().lex(text))

        self.assertFalse(lexcmp(expected, tokens, False))

    def test_003_expr_add(self):
        text = "x = a + b"
        expected = [
            Token(Token.T_TEXT, 1, 0, 'x'),
            Token(Token.T_SPECIAL, 1, 2, '='),
            Token(Token.T_TEXT, 1, 4, 'a'),
            Token(Token.T_SPECIAL, 1, 6, '+'),
            Token(Token.T_TEXT, 1, 8, 'b'),
        ]
        tokens = list(Lexer().lex(text))

        self.assertFalse(lexcmp(expected, tokens, False))

    def test_004_expr_multiply(self):
        text = "x = a * b"
        expected = [
            Token(Token.T_TEXT, 1, 0, 'x'),
            Token(Token.T_SPECIAL, 1, 2, '='),
            Token(Token.T_TEXT, 1, 4, 'a'),
            Token(Token.T_SPECIAL, 1, 6, '*'),
            Token(Token.T_TEXT, 1, 8, 'b'),
        ]
        tokens = list(Lexer().lex(text))

        self.assertFalse(lexcmp(expected, tokens, False))

    def test_005_expr_division(self):
        text = "x = a / b"
        expected = [
            Token(Token.T_TEXT, 1, 0, 'x'),
            Token(Token.T_SPECIAL, 1, 2, '='),
            Token(Token.T_TEXT, 1, 4, 'a'),
            Token(Token.T_SPECIAL, 1, 6, '/'),
            Token(Token.T_TEXT, 1, 8, 'b'),
        ]
        tokens = list(Lexer().lex(text))

        self.assertFalse(lexcmp(expected, tokens, False))

    def test_005_expr_division_2(self):
        text = "x = ((1/2)/3)"
        expected = [
            Token(Token.T_TEXT, 1, 0, 'x'),
            Token(Token.T_SPECIAL, 1, 2, '='),
            Token(Token.T_SPECIAL, 1, 4, '('),
            Token(Token.T_SPECIAL, 1, 5, '('),
            Token(Token.T_NUMBER, 1, 6, '1'),
            Token(Token.T_SPECIAL, 1, 8, '/'),
            Token(Token.T_NUMBER, 1, 8, '2'),
            Token(Token.T_SPECIAL, 1, 9, ')'),
            Token(Token.T_SPECIAL, 1, 11, '/'),
            Token(Token.T_NUMBER, 1, 11, '3'),
            Token(Token.T_SPECIAL, 1, 12, ')')
        ]
        tokens = list(Lexer().lex(text))

        self.assertFalse(lexcmp(expected, tokens, False))

    def test_006_expr_regex(self):
        text = "x = /a+/"
        expected = [
            Token(Token.T_TEXT, 1, 0, 'x'),
            Token(Token.T_SPECIAL, 1, 2, '='),
            Token(Token.T_REGEX, 1, 5, '/a+/')
        ]
        tokens = list(Lexer().lex(text))

        self.assertFalse(lexcmp(expected, tokens, False))

    def test_006_expr_regex_2(self):
        # while lexing the special tokens, recognise the start
        # of a regular expression and back out of the current token
        text = "x=/a+/"
        expected = [
            Token(Token.T_TEXT, 1, 0, 'x'),
            Token(Token.T_SPECIAL, 1, 2, '='),
            Token(Token.T_REGEX, 1, 5, '/a+/')
        ]
        tokens = list(Lexer().lex(text))

        self.assertFalse(lexcmp(expected, tokens, False))

    def test_006_expr_regex_3(self):
        text = "x = /a+\\x/"

        expected = [
            Token(Token.T_TEXT, 1, 0, 'x'),
            Token(Token.T_SPECIAL, 1, 2, '='),
            Token(Token.T_REGEX, 1, 5, '/a+\\x/')
        ]
        tokens = list(Lexer().lex(text))

        self.assertFalse(lexcmp(expected, tokens, False))

    def test_006_expr_regex_stop_iteration_1(self):
        text = "x = /a+"

        with self.assertRaises(LexError) as e:
            Lexer().lex(text)

    def test_006_expr_regex_stop_iteration_3(self):
        text = "x = /a+\\"

        with self.assertRaises(LexError) as e:
            Lexer().lex(text)
        self.assertTrue("Unexpected End of Sequence" in str(e.exception))

    def test_007_expr_async(self):
        text = "function* () {}"
        expected = [
            Token(Token.T_KEYWORD, 1, 0, 'function*'),
            Token(Token.T_SPECIAL, 1, 10, '('),
            Token(Token.T_SPECIAL, 1, 11, ')'),
            Token(Token.T_SPECIAL, 1, 13, '{'),
            Token(Token.T_SPECIAL, 1, 14, '}'),
        ]
        tokens = list(Lexer().lex(text))

        self.assertFalse(lexcmp(expected, tokens, False))

    def test_008_attr(self):
        text = "a.b"
        expected = [
            Token(Token.T_TEXT, 1, 4, 'a'),
            Token(Token.T_SPECIAL, 1, 6, '.'),
            Token(Token.T_TEXT, 1, 8, 'b'),
        ]
        tokens = list(Lexer().lex(text))

        self.assertFalse(lexcmp(expected, tokens, False))

    def test_009_attr_final(self):
        text = "a."
        expected = [
            Token(Token.T_TEXT, 1, 4, 'a'),
            Token(Token.T_SPECIAL, 1, 6, '.'),
        ]
        tokens = list(Lexer().lex(text))

        self.assertFalse(lexcmp(expected, tokens, False))

    def test_010_number(self):
        text = ".3"
        expected = [
            Token(Token.T_NUMBER, 1, 4, '.3'),
        ]
        tokens = list(Lexer().lex(text))

        self.assertFalse(lexcmp(expected, tokens, False))

    def test_011_spread(self):
        text = "{...a}"
        expected = [
            Token(Token.T_SPECIAL, 1, 0, '{'),
            Token(Token.T_SPECIAL, 1, 1, '...'),
            Token(Token.T_TEXT, 1, 4, 'a'),
            Token(Token.T_SPECIAL, 1, 5, '}')
        ]
        tokens = list(Lexer().lex(text))

        self.assertFalse(lexcmp(expected, tokens, False))

    def test_007_special2(self):

        text = "x += 1 "
        expected = [
            Token(Token.T_TEXT, 1, 0, 'x'),
            Token(Token.T_SPECIAL, 1, 2, '+='),
            Token(Token.T_NUMBER, 1, 5, '1')
        ]
        tokens = list(Lexer({'preserve_documentation': True}).lex(text))

        self.assertFalse(lexcmp(expected, tokens, False))

    def test_007_special2_break(self):

        text = "x==-1 "
        expected = [
            Token(Token.T_TEXT, 1, 0, 'x'),
            Token(Token.T_SPECIAL, 1, 2, '=='),
            Token(Token.T_SPECIAL, 1, 2, '-'),
            Token(Token.T_NUMBER, 1, 5, '1')
        ]
        tokens = list(Lexer({'preserve_documentation': True}).lex(text))

        self.assertFalse(lexcmp(expected, tokens, False))

    def test_007_special2_break(self):

        text = "x==-1 "
        expected = [
            Token(Token.T_TEXT, 1, 0, 'x'),
            Token(Token.T_SPECIAL, 1, 2, '=='),
            Token(Token.T_SPECIAL, 1, 2, '-'),
            Token(Token.T_NUMBER, 1, 5, '1')
        ]
        tokens = list(Lexer({'preserve_documentation': True}).lex(text))

        self.assertFalse(lexcmp(expected, tokens, False))

class LexerCustomTestCase(unittest.TestCase):

    def test_001_pyimport_1(self):
        text = "pyimport .modname"
        expected = [
            Token(Token.T_TEXT, 1, 0, 'pyimport'),
            Token(Token.T_SPECIAL_IMPORT, 1, 9, '.'),
            Token(Token.T_TEXT, 1, 10, 'modname'),
        ]
        tokens = list(Lexer().lex(text))

        self.assertFalse(lexcmp(expected, tokens, False))

    def test_001_pyimport_2(self):
        text = "pyimport ..modname"
        expected = [
            Token(Token.T_TEXT, 1, 0, 'pyimport'),
            Token(Token.T_SPECIAL_IMPORT, 1, 9, '..'),
            Token(Token.T_TEXT, 1, 10, 'modname'),
        ]
        tokens = list(Lexer().lex(text))

        self.assertFalse(lexcmp(expected, tokens, False))

    def test_001_pyimport_3(self):
        text = "pyimport ...modname"
        expected = [
            Token(Token.T_TEXT, 1, 0, 'pyimport'),
            Token(Token.T_SPECIAL_IMPORT, 1, 9, '...'),
            Token(Token.T_TEXT, 1, 10, 'modname'),
        ]
        tokens = list(Lexer().lex(text))

        self.assertFalse(lexcmp(expected, tokens, False))

    def test_001_pyimport_4(self):
        text = "pyimport ....modname"
        expected = [
            Token(Token.T_TEXT, 1, 0, 'pyimport'),
            Token(Token.T_SPECIAL_IMPORT, 1, 9, '....'),
            Token(Token.T_TEXT, 1, 10, 'modname'),
        ]
        tokens = list(Lexer().lex(text))

        self.assertFalse(lexcmp(expected, tokens, False))

class LexerStringTestCase(unittest.TestCase):

    def test_001_single(self):

        text = " x = '123' "
        expected = [
            Token(Token.T_TEXT, 1, 1, 'x'),
            Token(Token.T_SPECIAL, 1, 3, '='),
            Token(Token.T_STRING, 1, 5, "'123'"),
        ]
        tokens = list(Lexer().lex(text))

        self.assertFalse(lexcmp(expected, tokens, False))

    def test_001_double(self):

        text = " x = \"123\" "
        expected = [
            Token(Token.T_TEXT, 1, 1, 'x'),
            Token(Token.T_SPECIAL, 1, 3, '='),
            Token(Token.T_STRING, 1, 5, "\"123\""),
        ]
        tokens = list(Lexer().lex(text))

        self.assertFalse(lexcmp(expected, tokens, False))

    def test_001_backtick(self):

        text = " x = `${a}` "
        expected = [
            Token(Token.T_TEXT, 1, 1, 'x'),
            Token(Token.T_SPECIAL, 1, 3, '='),
            Token(Token.T_TEMPLATE_STRING, 1, 5, "`${a}`"),
        ]
        tokens = list(Lexer().lex(text))

        self.assertFalse(lexcmp(expected, tokens, False))

    def test_001_join(self):

        text = " x = \"abc\" \"def\" "
        expected = [
            Token(Token.T_TEXT, 1, 1, 'x'),
            Token(Token.T_SPECIAL, 1, 3, '='),
            Token(Token.T_STRING, 1, 5, "\"abcdef\""),
        ]
        tokens = list(Lexer().lex(text))

        self.assertFalse(lexcmp(expected, tokens, False))

    def test_001_join_multiline(self):

        text = " x = \"abc\" \\\n" + \
               "\"def\" "
        expected = [
            Token(Token.T_TEXT, 1, 1, 'x'),
            Token(Token.T_SPECIAL, 1, 3, '='),
            Token(Token.T_STRING, 1, 5, "\"abcdef\""),
        ]
        tokens = list(Lexer().lex(text))

        self.assertFalse(lexcmp(expected, tokens, False))

class LexerLogicTestCase(unittest.TestCase):

    def test_001_ternary_1(self):

        text = "a ? b : c"
        expected = [
            Token(Token.T_TEXT, 1, 0, 'a'),
            Token(Token.T_SPECIAL, 1, 2, '?'),
            Token(Token.T_TEXT, 1, 4, 'b'),
            Token(Token.T_SPECIAL, 1, 6, ':'),
            Token(Token.T_TEXT, 1, 8, 'c')
        ]
        tokens = list(Lexer().lex(text))

        self.assertFalse(lexcmp(expected, tokens, False))

    def test_001_ternary_2(self):

        text = "a ?"
        expected = [
            Token(Token.T_TEXT, 1, 0, 'a'),
            Token(Token.T_SPECIAL, 1, 2, '?'),
        ]

        with self.assertRaises(LexError) as e:
            Lexer().lex(text)

        #tokens = list(Lexer().lex(text))

        #self.assertFalse(lexcmp(expected, tokens, False))

def main():
    unittest.main()


if __name__ == '__main__':
    main()
