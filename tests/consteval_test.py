#! cd .. && python3 -m tests.consteval_test

import unittest
from tests.util import edit_distance, parsecmp, TOKEN

from daedalus.lexer import Token, Lexer
from daedalus.parser import Parser, ParseError
from daedalus.transform import TransformIdentityScope, TransformConstEval

text1 = """
    const a = "hello" + ' world'
"""

text2 = """
    const a = 6
    const b = a * 7
"""


text7 = """
    const a = 124
    const b = "px"
    const c = a*.5 + b
"""


texta = """
    function test() {

        {
            const x = 7;
        }

        {
            let x;
            let y = x + 1;
        }

    }
"""

class ConstEvalTestCase(unittest.TestCase):

    def test_001_add_str(self):

        text = """const a = "hello" + ' world'"""
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)

        xform = TransformIdentityScope()
        xform.disable_warnings = True
        xform.transform(ast)
        TransformConstEval().transform(ast)

        expected = TOKEN('T_MODULE', '',
            TOKEN('T_VAR', 'const',
                TOKEN('T_ASSIGN', '=',
                    TOKEN('T_GLOBAL_VAR', 'a'),
                    TOKEN('T_STRING', "'hello world'"))))

        self.assertFalse(parsecmp(expected, ast, False))

    def test_001_add_int(self):

        text = """
            const a = 6
            const b = a * 7
        """
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)

        xform = TransformIdentityScope()
        xform.disable_warnings = True
        xform.transform(ast)
        TransformConstEval().transform(ast)

        expected = TOKEN('T_MODULE', '',
            TOKEN('T_VAR', 'const',
                TOKEN('T_ASSIGN', '=',
                    TOKEN('T_GLOBAL_VAR', 'a'),
                    TOKEN('T_NUMBER', '6'))),
            TOKEN('T_VAR', 'const',
                TOKEN('T_ASSIGN', '=',
                    TOKEN('T_GLOBAL_VAR', 'b'),
                    TOKEN('T_NUMBER', '42'))))

        self.assertFalse(parsecmp(expected, ast, False))

    def test_001_add_int_str(self):

        text = """
            const a = 124
            const b = "px"
            const c = a*.5 + b
        """
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)

        xform = TransformIdentityScope()
        xform.disable_warnings = True
        xform.transform(ast)
        TransformConstEval().transform(ast)

        expected = TOKEN('T_MODULE', '',
            TOKEN('T_VAR', 'const',
                TOKEN('T_ASSIGN', '=',
                    TOKEN('T_GLOBAL_VAR', 'a'),
                    TOKEN('T_NUMBER', '124'))),
            TOKEN('T_VAR', 'const',
                TOKEN('T_ASSIGN', '=',
                    TOKEN('T_GLOBAL_VAR', 'b'),
                    TOKEN('T_STRING', '"px"'))),
            TOKEN('T_VAR', 'const',
                TOKEN('T_ASSIGN', '=',
                    TOKEN('T_GLOBAL_VAR', 'c'),
                    TOKEN('T_NUMBER', "'62.0px'"))))

        self.assertFalse(parsecmp(expected, ast, False))

    def test_002_block_scope(self):

        text = """
            function test() {

                {
                    const x = 7;
                }

                {
                    let x;
                    let y = x + 1;
                }
            }
        """
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)

        xform = TransformIdentityScope()
        xform.disable_warnings = True
        xform.transform(ast)
        TransformConstEval().transform(ast)

        expected = TOKEN('T_MODULE', '',
            TOKEN('T_FUNCTION', 'function',
                TOKEN('T_GLOBAL_VAR', 'test'),
                TOKEN('T_ARGLIST', '()'),
                TOKEN('T_BLOCK', '{}',
                    TOKEN('T_BLOCK', '{}',
                        TOKEN('T_VAR', 'const',
                            TOKEN('T_ASSIGN', '=',
                                TOKEN('T_LOCAL_VAR', 'x'),
                                TOKEN('T_NUMBER', '7'))),
                        TOKEN('T_DELETE_VAR', '',
                            TOKEN('T_LOCAL_VAR', 'x'))),
                    TOKEN('T_BLOCK', '{}',
                        TOKEN('T_VAR', 'let',
                            TOKEN('T_LOCAL_VAR', 'x')),
                        TOKEN('T_VAR', 'let',
                            TOKEN('T_ASSIGN', '=',
                                TOKEN('T_LOCAL_VAR', 'y'),
                                TOKEN('T_NUMBER', '8'))),
                        TOKEN('T_DELETE_VAR', '',
                            TOKEN('T_LOCAL_VAR', 'x')),
                        TOKEN('T_DELETE_VAR', '',
                            TOKEN('T_LOCAL_VAR', 'y')))),
                TOKEN('T_CLOSURE', '')))

        self.assertFalse(parsecmp(expected, ast, False))

def main():
    unittest.main()


if __name__ == '__main__':
    main()