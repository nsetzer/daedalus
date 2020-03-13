
import io
import unittest

from daedalus.lexer import Token, Lexer, TokenError, LexError
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

class LexerInputTestCase(unittest.TestCase):

    def test_001_stream(self):
        """lexer should accept input from a file-like object"""

        text = io.StringIO("3.14")
        expected = [
            Token(Token.T_NUMBER, 1, 0, '3.14'),
        ]
        tokens = list(Lexer().lex(text))

        self.assertFalse(lexcmp(expected, tokens, False))

    def test_002_string(self):
        """lexer should accept input from a string"""

        text = "3.14"
        expected = [
            Token(Token.T_NUMBER, 1, 0, '3.14'),
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

    def test_005_multiline_comment(self):

        text = " /* comment \n more text */ x "
        expected = [
            Token(Token.T_TEXT, 1, 0, 'x'),
        ]
        tokens = list(Lexer().lex(text))

        self.assertFalse(lexcmp(expected, tokens, False))

    def test_006_multiline_doc(self):

        text = " /** comment \n more text */ x "
        expected = [
            Token(Token.T_DOCUMENTATION, 1, 3, '/** comment \n more text */'),
            Token(Token.T_TEXT, 2, 14, 'x')
        ]
        tokens = list(Lexer({'preserve_documentation': True}).lex(text))

        self.assertFalse(lexcmp(expected, tokens, False))

class LexerInputErrorTestCase(unittest.TestCase):

    def test_001_illegal_esape(self):

        text = " x \\ b"
        with self.assertRaises(LexError):
            Lexer().lex(text)

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
            Token(Token.T_TEXT, 1, 5, '/a+/')
        ]
        tokens = list(Lexer().lex(text))

        self.assertFalse(lexcmp(expected, tokens, False))

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

class LexerBasicErrorTestCase(unittest.TestCase):

    def test_001_spread_final(self):
        text = ".."
        with self.assertRaises(LexError):
            Lexer().lex(text)

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

def main():
    unittest.main()


if __name__ == '__main__':
    main()
