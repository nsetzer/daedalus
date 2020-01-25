

import unittest
from tests.util import edit_distance, parsecmp, TOKEN

from daedalus.lexer import Token, Lexer
from daedalus.parser import Parser, ParseError
from daedalus.builder import buildFileIIFI

class FileIIFIOpTestCase(unittest.TestCase):

    def test_001_unary_prefix(self):

        text = "x = 1"
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)

        mod = buildFileIIFI(ast, ["x"])
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_BINARY', '=',
                TOKEN('T_VAR', 'const',
                    TOKEN('T_LIST', '[]',
                        TOKEN('T_TEXT', 'x'))),
                TOKEN('T_FUNCTIONCALL', '',
                    TOKEN('T_GROUPING', '()',
                        TOKEN('T_FUNCTION', 'function',
                            TOKEN('T_TEXT', ''),
                            TOKEN('T_ARGLIST', '()'),
                            TOKEN('T_BLOCK', '{}',
                                TOKEN('T_BINARY', '=',
                                    TOKEN('T_TEXT', 'x'),
                                    TOKEN('T_NUMBER', '1')),
                                TOKEN('T_RETURN', 'return',
                                    TOKEN('T_LIST', '[]',
                                        TOKEN('T_TEXT', 'x')))))),
                    TOKEN('T_ARGLIST', '()')))
        )

        self.assertFalse(parsecmp(expected, mod, False))

def main():
    unittest.main()

if __name__ == '__main__':
    main()
