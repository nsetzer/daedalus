#! cd .. && python3 -m tests.transform_test


import unittest
from tests.util import edit_distance, parsecmp, TOKEN

from daedalus.lexer import Token, Lexer
from daedalus.parser import Parser as ParserBase, ParseError
from daedalus.transform import TransformIdentityScope, TransformMinifyScope, getModuleImportExport

class Parser(ParserBase):
    def __init__(self):
        super(Parser, self).__init__()
        self.disable_all_warnings = True

class TransformTestCase(unittest.TestCase):

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

    def test_001_export1(self):
        text = """
            let var1 = 0, var2 = 1, var3 = 2;
            export var1, var2, var3
        """
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)

        xform = TransformMinifyScope()
        globals = xform.transform(ast)

        expected = TOKEN('T_MODULE', '',
            TOKEN('T_VAR', 'let',
                TOKEN('T_ASSIGN', '=',
                    TOKEN('T_GLOBAL_VAR', 'a'),
                    TOKEN('T_NUMBER', '0')),
                TOKEN('T_ASSIGN', '=',
                    TOKEN('T_GLOBAL_VAR', 'b'),
                    TOKEN('T_NUMBER', '1')),
                TOKEN('T_ASSIGN', '=',
                    TOKEN('T_GLOBAL_VAR', 'c'),
                    TOKEN('T_NUMBER', '2'))),
            TOKEN('T_EXPORT', 'export',
                TOKEN('T_ARGLIST', '()',
                    TOKEN('T_GLOBAL_VAR', 'a'),
                    TOKEN('T_GLOBAL_VAR', 'b'),
                    TOKEN('T_GLOBAL_VAR', 'c')),
                TOKEN('T_ARGLIST', '()',
                    TOKEN('T_GLOBAL_VAR', 'a'),
                    TOKEN('T_GLOBAL_VAR', 'b'),
                    TOKEN('T_GLOBAL_VAR', 'c'))))

        #print(globals)

        self.assertFalse(parsecmp(expected, ast, False))

    def test_001_export2(self):
        text = """
            export function f() {}, function g() {}
            export default function h() {}
        """
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)

        ast, imports, module_imports, exports = getModuleImportExport(ast)

        print(imports, module_imports)
        self.assertEqual(exports, ['f', 'g', 'h'])

        expected = TOKEN('T_MODULE', '',
            TOKEN('T_FUNCTION', 'function',
                TOKEN('T_TEXT', 'f'),
                TOKEN('T_ARGLIST', '()'),
                TOKEN('T_BLOCK', '{}')),
            TOKEN('T_FUNCTION', 'function',
                TOKEN('T_TEXT', 'g'),
                TOKEN('T_ARGLIST', '()'),
                TOKEN('T_BLOCK', '{}')),
            TOKEN('T_FUNCTION', 'function',
                TOKEN('T_TEXT', 'h'),
                TOKEN('T_ARGLIST', '()'),
                TOKEN('T_BLOCK', '{}')))

        self.assertFalse(parsecmp(expected, ast, False))

    @unittest.expectedFailure
    def test_001_export_from(self):
        text = """
            export name from './file'
        """
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)

        ast, imports, module_imports, exports = getModuleImportExport(ast)

        print(imports, module_imports)
        self.assertEqual(exports, ['name'])

        expected = TOKEN('T_MODULE', '',
            TOKEN('T_FUNCTION', 'function',
                TOKEN('T_TEXT', 'f'),
                TOKEN('T_ARGLIST', '()'),
                TOKEN('T_BLOCK', '{}')),
            TOKEN('T_FUNCTION', 'function',
                TOKEN('T_TEXT', 'g'),
                TOKEN('T_ARGLIST', '()'),
                TOKEN('T_BLOCK', '{}')),
            TOKEN('T_FUNCTION', 'function',
                TOKEN('T_TEXT', 'h'),
                TOKEN('T_ARGLIST', '()'),
                TOKEN('T_BLOCK', '{}')))

        self.assertFalse(parsecmp(expected, ast, False))

def main():
    unittest.main()


if __name__ == '__main__':
    main()
