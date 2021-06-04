#! cd .. && python3 -m tests.builder_test

import unittest
from tests.util import edit_distance, parsecmp, TOKEN

from daedalus.lexer import Token, Lexer
from daedalus.parser import Parser, ParseError
from daedalus.builder import buildFileIIFI, buildModuleIIFI, Builder

class FileIIFIOpTestCase(unittest.TestCase):

    def test_001_iifi(self):

        text = "x = 1"
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)

        mod = buildFileIIFI(ast, ["x"])
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_VAR', 'const',
                TOKEN('T_ASSIGN', '=',
                    TOKEN('T_UNPACK_SEQUENCE', '[]',
                        TOKEN('T_TEXT', 'x')),
                    TOKEN('T_FUNCTIONCALL', '',
                        TOKEN('T_GROUPING', '()',
                            TOKEN('T_ANONYMOUS_FUNCTION', 'function',
                                TOKEN('T_TEXT', 'Anonymous'),
                                TOKEN('T_ARGLIST', '()'),
                                TOKEN('T_BLOCK', '{}',
                                    TOKEN('T_ASSIGN', '=',
                                        TOKEN('T_TEXT', 'x'),
                                        TOKEN('T_NUMBER', '1')),
                                    TOKEN('T_RETURN', 'return',
                                        TOKEN('T_LIST', '[]',
                                            TOKEN('T_TEXT', 'x')))))),
                    TOKEN('T_ARGLIST', '()'))))
        )

        self.assertFalse(parsecmp(expected, mod, False))

class ModuleIIFIOpTestCase(unittest.TestCase):

    def test_001_iifi(self):

        text = "x = 1"
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)

        imports = {'daedalus': {'foo': 'bar'}}
        exports = ['x']
        mod = buildModuleIIFI('text', ast, imports, exports, True)
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_FUNCTIONCALL', '',
                TOKEN('T_GET_ATTR', '.',
                    TOKEN('T_TEXT', 'Object'),
                    TOKEN('T_TEXT', 'assign')),
                TOKEN('T_ARGLIST', '()',
                    TOKEN('T_TEXT', 'text'),
                    TOKEN('T_FUNCTIONCALL', '',
                        TOKEN('T_GROUPING', '()',
                            TOKEN('T_ANONYMOUS_FUNCTION', 'function',
                                TOKEN('T_TEXT', 'Anonymous'),
                                TOKEN('T_ARGLIST', '()',
                                    TOKEN('T_TEXT', 'daedalus')),
                                TOKEN('T_BLOCK', '{}',
                                    TOKEN('T_STRING', '"use strict"'),
                                    TOKEN('T_ASSIGN', '=',
                                        TOKEN('T_VAR', 'const',
                                            TOKEN('T_TEXT', 'bar')),
                                        TOKEN('T_GET_ATTR', '.',
                                            TOKEN('T_TEXT', 'daedalus'),
                                            TOKEN('T_ATTR', 'foo'))),
                                    TOKEN('T_ASSIGN', '=',
                                        TOKEN('T_TEXT', 'x'),
                                        TOKEN('T_NUMBER', '1')),
                                    TOKEN('T_RETURN', 'return',
                                        TOKEN('T_OBJECT', '{}',
                                            TOKEN('T_TEXT', 'x')))))),
                        TOKEN('T_ARGLIST', '()',
                            TOKEN('T_TEXT', 'daedalus'))))))

        self.assertFalse(parsecmp(expected, mod, False))

    def test_002_iifi(self):

        text = "x = 1"
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)

        imports = {'daedalus': {'foo': 'bar'}}
        exports = ['x']
        mod = buildModuleIIFI('text', ast, imports, exports, False)
        expected = TOKEN('T_MODULE', '',
            TOKEN('T_ASSIGN', '=',
                TOKEN('T_TEXT', 'text'),
                TOKEN('T_FUNCTIONCALL', '',
                    TOKEN('T_GROUPING', '()',
                        TOKEN('T_ANONYMOUS_FUNCTION', 'function',
                            TOKEN('T_TEXT', 'Anonymous'),
                            TOKEN('T_ARGLIST', '()',
                                TOKEN('T_TEXT', 'daedalus')),
                            TOKEN('T_BLOCK', '{}',
                                TOKEN('T_STRING', '"use strict"'),
                                TOKEN('T_ASSIGN', '=',
                                    TOKEN('T_VAR', 'const',
                                        TOKEN('T_TEXT', 'bar')),
                                    TOKEN('T_GET_ATTR', '.',
                                        TOKEN('T_TEXT', 'daedalus'),
                                        TOKEN('T_ATTR', 'foo'))),
                                TOKEN('T_ASSIGN', '=',
                                    TOKEN('T_TEXT', 'x'),
                                    TOKEN('T_NUMBER', '1')),
                                TOKEN('T_RETURN', 'return',
                                    TOKEN('T_OBJECT', '{}',
                                        TOKEN('T_TEXT', 'x')))))),
                    TOKEN('T_ARGLIST', '()',
                        TOKEN('T_TEXT', 'daedalus')))))

        self.assertFalse(parsecmp(expected, mod, False))

class BuilderTestTestCase(unittest.TestCase):

    def test_001_build(self):

        # TODO: expand on this test
        path = "res/template.js"

        static_data = {"daedalus": {"env": {}}}
        builder = Builder([], static_data, platform=None)
        builder.disable_warnings = True
        css, js, html = builder.build(path, minify=True, onefile=True)

        #print(css)
        #print(js)
        #print(html)

        return
def main():
    unittest.main()


if __name__ == '__main__':
    main()
