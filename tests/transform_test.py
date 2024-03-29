#! cd .. && python3 -m tests.transform_test


import unittest
from tests.util import parsecmp, TOKEN

from daedalus.lexer import Lexer
from daedalus.parser import Parser as ParserBase
from daedalus.formatter import Formatter
from daedalus.transform import TransformIdentityScope, \
    TransformMinifyScope, getModuleImportExport, TransformIdentityBlockScope, \
    TransformExtractStyleSheet, TransformError

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
        xform.transform(ast)

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
                TOKEN('T_EXPORT_ARGS', '()',
                    TOKEN('T_GLOBAL_VAR', 'a'),
                    TOKEN('T_GLOBAL_VAR', 'b'),
                    TOKEN('T_GLOBAL_VAR', 'c')),
                TOKEN('T_EXPORT_ARGS', '()',
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

        self.assertEqual(exports, ['name'])

        expected = TOKEN('T_MODULE', '')

        self.assertFalse(parsecmp(expected, ast, False))

class TransformExtractStyleSheetTestCase(unittest.TestCase):

    def test_001_style1(self):

        text = """
        const styles = {
            body: StyleSheet({background: '#000000'}),
        }

        """

        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        uid = TransformExtractStyleSheet.generateUid("__test__")
        xform = TransformExtractStyleSheet(uid)
        xform.transform(ast)
        styles = xform.getStyles()

        expected = TOKEN('T_MODULE', '',
            TOKEN('T_VAR', 'const',
                TOKEN('T_ASSIGN', '=',
                    TOKEN('T_TEXT', 'styles'),
                    TOKEN('T_OBJECT', '{}',
                        TOKEN('T_BINARY', ':',
                            TOKEN('T_TEXT', 'body'),
                            TOKEN('T_STRING', "'dcs-573d2c00-0'"))))))

        expected_styles = ['.dcs-573d2c00-0 {background:#000000}']

        self.assertFalse(parsecmp(expected, ast, False))
        self.assertEqual(styles, expected_styles)

    def test_001_style2(self):

        text = """
        const styles = {
            fraction: StyleSheet({}),
        }
        StyleSheet(`.${styles.fraction} sup`, {font-size: '.8em'})
        StyleSheet(`.${styles.fraction} sub`, {font-size: '.8em'})

        """

        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        uid = TransformExtractStyleSheet.generateUid("__test__")
        xform = TransformExtractStyleSheet(uid)
        xform.transform(ast)
        styles = xform.getStyles()

        expected = TOKEN('T_MODULE', '',
            TOKEN('T_VAR', 'const',
                TOKEN('T_ASSIGN', '=',
                    TOKEN('T_TEXT', 'styles'),
                    TOKEN('T_OBJECT', '{}',
                        TOKEN('T_BINARY', ':',
                            TOKEN('T_TEXT', 'fraction'),
                            TOKEN('T_STRING', "'dcs-573d2c00-0'"))))),
            TOKEN('T_EMPTY_TOKEN', "'.dcs-573d2c00-0 sup'"),
            TOKEN('T_EMPTY_TOKEN', "'.dcs-573d2c00-0 sub'"))

        expected_styles = ['.dcs-573d2c00-0 {}',
                           '.dcs-573d2c00-0 sup {font-size:.8em}',
                           '.dcs-573d2c00-0 sub {font-size:.8em}']

        self.assertFalse(parsecmp(expected, ast, False))
        self.assertEqual(styles, expected_styles)

    def test_001_style3(self):

        text = """
        const styles = {
            header: StyleSheet({flex-direction: 'row'}),
        }
        StyleSheet(1, `@media only screen and (max-width: 768px)`, {
            'body': {
                background: '#000000',
            },
            `.${styles.header}`: {
                "flex-direction": "column",
            },
        })


        """

        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        uid = TransformExtractStyleSheet.generateUid("__test__")
        xform = TransformExtractStyleSheet(uid)
        xform.transform(ast)
        styles = xform.getStyles()

        expected = TOKEN('T_MODULE', '',
            TOKEN('T_VAR', 'const',
                TOKEN('T_ASSIGN', '=',
                    TOKEN('T_TEXT', 'styles'),
                    TOKEN('T_OBJECT', '{}',
                        TOKEN('T_BINARY', ':',
                            TOKEN('T_TEXT', 'header'),
                            TOKEN('T_STRING', "'dcs-573d2c00-0'"))))),
            TOKEN('T_EMPTY_TOKEN', ''))

        expected_styles = [
            '.dcs-573d2c00-0 {flex-direction:row}',
            '@media only screen and (max-width: 768px) ' +
                '{\nbody {background:#000000}\n' +
                '.dcs-573d2c00-0 {flex-direction:column}\n' +
                '}'
        ]

        self.assertFalse(parsecmp(expected, ast, False))
        self.assertEqual(styles, expected_styles)

    def test_001_style_name(self):

        text = """
        const styles = {
            header: StyleSheet({flex-direction: 'row'}),
            more: {x:StyleSheet({flex-direction: 'row'})}
        }
        """

        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        uid = TransformExtractStyleSheet.generateUid("__test__")
        xform = TransformExtractStyleSheet(uid)
        xform.transform(ast)
        self.assertTrue('styles.header' in xform.named_styles)

class TransformIdentityTestCase(unittest.TestCase):

    def test_001_identity_deletevar_block(self):

        text = """
        function f() {
            if (false) {
                let unit = 0
            } else {
                let unit = 1
            }
        }
        """

        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        xform = TransformIdentityScope()
        xform.disable_warnings = True
        xform.transform(ast)

        expected = TOKEN('T_MODULE', '',
            TOKEN('T_FUNCTION', 'function',
                TOKEN('T_GLOBAL_VAR', 'f'),
                TOKEN('T_ARGLIST', '()'),
                TOKEN('T_BLOCK', '{}',
                    TOKEN('T_BRANCH', 'if',
                        TOKEN('T_ARGLIST', '()',
                            TOKEN('T_KEYWORD', 'false')),
                        TOKEN('T_BLOCK', '{}',
                            TOKEN('T_VAR', 'let',
                                TOKEN('T_ASSIGN', '=',
                                    TOKEN('T_LOCAL_VAR', 'unit'),
                                    TOKEN('T_NUMBER', '0'))),
                            TOKEN('T_DELETE_VAR', '',
                                TOKEN('T_LOCAL_VAR', 'unit'))),
                        TOKEN('T_BLOCK', '{}',
                            TOKEN('T_VAR', 'let',
                                TOKEN('T_ASSIGN', '=',
                                    TOKEN('T_LOCAL_VAR', 'unit'),
                                    TOKEN('T_NUMBER', '1'))),
                            TOKEN('T_DELETE_VAR', '',
                                TOKEN('T_LOCAL_VAR', 'unit'))))),
                TOKEN('T_CLOSURE', '')))

        self.assertFalse(parsecmp(expected, ast, False))

    def test_001_identity_deletevar_for(self):

        text = """
        for (i=0; i < 10; i++) {
            console.log(i)
        }
        """

        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        xform = TransformIdentityScope()
        xform.disable_warnings = True
        xform.transform(ast)

        expected = TOKEN('T_MODULE', '',
            TOKEN('T_FOR', 'for',
                TOKEN('T_ARGLIST', '()',
                    TOKEN('T_ASSIGN', '=',
                        TOKEN('T_GLOBAL_VAR', 'i'),
                        TOKEN('T_NUMBER', '0')),
                    TOKEN('T_BINARY', '<',
                        TOKEN('T_GLOBAL_VAR', 'i'),
                        TOKEN('T_NUMBER', '10')),
                    TOKEN('T_POSTFIX', '++',
                        TOKEN('T_GLOBAL_VAR', 'i'))),
                TOKEN('T_BLOCK', '{}',
                    TOKEN('T_FUNCTIONCALL', '',
                        TOKEN('T_GET_ATTR', '.',
                            TOKEN('T_GLOBAL_VAR', 'console'),
                            TOKEN('T_ATTR', 'log')),
                        TOKEN('T_ARGLIST', '()',
                            TOKEN('T_GLOBAL_VAR', 'i'))))),
            TOKEN('T_DELETE_VAR', '',
                TOKEN('T_GLOBAL_VAR', 'i')))

        self.assertFalse(parsecmp(expected, ast, False))

    def test_001_identity_restorevar_block(self):

        text = """
        function f() {

            let x = 1;
            {
                let x = 2;
            }

            return x;
        }
        """

        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        xform = TransformIdentityBlockScope()
        xform.disable_warnings = True
        xform.transform(ast)

        expected = TOKEN('T_MODULE', '',
            TOKEN('T_FUNCTION', 'function',
                TOKEN('T_GLOBAL_VAR', 'f'),
                TOKEN('T_ARGLIST', '()'),
                TOKEN('T_BLOCK', '{}',
                    TOKEN('T_VAR', 'let',
                        TOKEN('T_ASSIGN', '=',
                            TOKEN('T_LOCAL_VAR', 'x'),
                            TOKEN('T_NUMBER', '1'))),
                    TOKEN('T_BLOCK', '{}',
                        TOKEN('T_VAR', 'let',
                            TOKEN('T_ASSIGN', '=',
                                TOKEN('T_LOCAL_VAR', 'x#b2'),
                                TOKEN('T_NUMBER', '2'))),
                        TOKEN('T_DELETE_VAR', '',
                            TOKEN('T_LOCAL_VAR', 'x#b2'))),
                    TOKEN('T_RETURN', 'return',
                        TOKEN('T_LOCAL_VAR', 'x'))),
                TOKEN('T_CLOSURE', '')))

        self.assertFalse(parsecmp(expected, ast, False))

    @unittest.skip("not implemented")
    def test_001_import(self):

        text = """
        import { name } from "module"
        import { name as alias } from "module"
        import name from "module"
        """

        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        xform = TransformIdentityBlockScope()
        xform.disable_warnings = True
        xform.transform(ast)

        expected = TOKEN('T_MODULE', '',
            TOKEN('T_IMPORT_JS_MODULE', '"module"',
                TOKEN('T_GLOBAL_VAR', 'name')),
            TOKEN('T_IMPORT_JS_MODULE', '"module"',
                TOKEN('T_KEYWORD', 'as',
                    TOKEN('T_GLOBAL_VAR', 'name'),
                    TOKEN('T_GLOBAL_VAR', 'alias'))),
            TOKEN('T_IMPORT', 'name',
                TOKEN('T_OBJECT', '{}')),
            TOKEN('T_GLOBAL_VAR', 'from'),
            TOKEN('T_STRING', '"module"'))

        self.assertFalse(parsecmp(expected, ast, False))

    @unittest.skip("not implemented")
    def test_001_import_module(self):

        text = """
        from module modname import {name as alias, name2}
        from modname import {name as alias, name2}
        """

        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        xform = TransformIdentityBlockScope()
        xform.disable_warnings = True
        xform.transform(ast)

        expected = TOKEN('T_MODULE', '',
            TOKEN('T_IMPORT_MODULE', 'modname',
                TOKEN('T_ARGLIST', '{}',
                    TOKEN('T_ASSIGN', '=',
                        TOKEN('T_ATTR', 'name'),
                        TOKEN('T_GLOBAL_VAR', 'name')),
                    TOKEN('T_ASSIGN', '=',
                        TOKEN('T_ATTR', 'as'),
                        TOKEN('T_GLOBAL_VAR', 'as')),
                    TOKEN('T_ASSIGN', '=',
                        TOKEN('T_ATTR', 'alias'),
                        TOKEN('T_GLOBAL_VAR', 'alias')),
                    TOKEN('T_ASSIGN', '=',
                        TOKEN('T_ATTR', 'name2'),
                        TOKEN('T_GLOBAL_VAR', 'name2')))),
            TOKEN('T_IMPORT', 'modname',
                TOKEN('T_OBJECT', '{}',
                    TOKEN('T_BINARY', ':',
                        TOKEN('T_STRING', "'name'"),
                        TOKEN('T_GLOBAL_VAR', 'name')),
                    TOKEN('T_BINARY', ':',
                        TOKEN('T_STRING', "'as'"),
                        TOKEN('T_GLOBAL_VAR', 'as')),
                    TOKEN('T_BINARY', ':',
                        TOKEN('T_STRING', "'alias'"),
                        TOKEN('T_GLOBAL_VAR', 'alias')),
                    TOKEN('T_BINARY', ':',
                        TOKEN('T_STRING', "'name2'"),
                        TOKEN('T_GLOBAL_VAR', 'name2')))))

        self.assertFalse(parsecmp(expected, ast, False))

    def test_001_pyimport(self):

        text = """pyimport math {a=b,c}"""

        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        xform = TransformIdentityBlockScope()
        xform.disable_warnings = True
        xform.transform(ast)

        expected = TOKEN('T_MODULE', '',
            TOKEN('T_PYIMPORT', 'math',
                TOKEN('T_GLOBAL_VAR', 'math'),
                TOKEN('T_NUMBER', '0'),
                TOKEN('T_ARGLIST', '{}',
                    TOKEN('T_ASSIGN', '=',
                        TOKEN('T_ATTR', 'a'),
                        TOKEN('T_GLOBAL_VAR', 'b')),
                    TOKEN('T_ASSIGN', '=',
                        TOKEN('T_ATTR', 'c'),
                        TOKEN('T_GLOBAL_VAR', 'c')))))

        self.assertFalse(parsecmp(expected, ast, False))

    @unittest.expectedFailure
    def test_001_identity_restorevar_block_2(self):

        text = """
        function f() {

            let x = 1;
            while (true) {
                let x = 2; // TODO block scope not deleted correctly
                {
                    break
                    let x = 3;

                }
            }

            return x;
        }
        """

        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        xform = TransformIdentityBlockScope()
        xform.disable_warnings = True
        xform.transform(ast)

        self.assertFail("not implemented")
        expected = TOKEN('T_MODULE', '', 
            TOKEN('T_FUNCTION', 'function', 
                TOKEN('T_GLOBAL_VAR', 'f'), 
                TOKEN('T_ARGLIST', '()'), 
                TOKEN('T_BLOCK', '{}', 
                    TOKEN('T_VAR', 'let', 
                        TOKEN('T_ASSIGN', '=', 
                            TOKEN('T_LOCAL_VAR', 'x'), 
                            TOKEN('T_NUMBER', '1'))), 
                    TOKEN('T_WHILE', 'while', 
                        TOKEN('T_ARGLIST', '()', 
                            TOKEN('T_KEYWORD', 'true')), 
                        TOKEN('T_BLOCK', '{}', 
                            TOKEN('T_VAR', 'let', 
                                TOKEN('T_ASSIGN', '=', 
                                    TOKEN('T_LOCAL_VAR', 'x#b2'), 
                                    TOKEN('T_NUMBER', '2'))), 
                            TOKEN('T_BLOCK', '{}', 
                                TOKEN('T_BREAK', 'break'), 
                                TOKEN('T_VAR', 'let', 
                                    TOKEN('T_ASSIGN', '=', 
                                        TOKEN('T_LOCAL_VAR', 'x#b3'), 
                                        TOKEN('T_NUMBER', '3'))), 
                                TOKEN('T_DELETE_VAR', '', 
                                    TOKEN('T_LOCAL_VAR', 'x#b3'))),
                            TOKEN('T_DELETE_VAR', '', 
                                TOKEN('T_LOCAL_VAR', 'x#b2')))), 
                    TOKEN('T_RETURN', 'return', 
                        TOKEN('T_LOCAL_VAR', 'x'))), 
                TOKEN('T_CLOSURE', '')))

        self.assertFalse(parsecmp(expected, ast, False))

    def test_001_unused_var_lambda(self):
        text = """

        # a variable ina block scope is not used
        # but it is used inside a lambda, which is defered
        function f() {
            while (true) {
                const flag=true;
                g(()=>h(flag));
            }
        }
        export f
        """
        tokens = Lexer().lex(text)
        parser =  Parser()
        ast = parser.parse(tokens)

        xform = TransformMinifyScope()
        xform.warnings_as_errors = True
        xform.transform(ast)

    def test_001_unused_var(self):

        # a variable in a block scope is not used
        text = """
        function f() {
            while (true) {
                const flag_error = false;
                g(()=>h());
            }
        }
        export f
        """
        tokens = Lexer().lex(text)
        parser =  Parser()
        ast = parser.parse(tokens)

        xform = TransformMinifyScope()
        xform.warnings_as_errors = True

        with self.assertRaises(TransformError):
            xform.transform(ast)

class TransformImportExport(unittest.TestCase):

    # https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Statements/import
    # https://developer.mozilla.org/en-US/docs/web/javascript/reference/statements/export
    # https://www.typescriptlang.org/docs/handbook/2/everyday-types.html

    def parse(self, text):
        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        xform = TransformIdentityScope()
        xform.disable_warnings = True
        xform.transform(ast)
        return ast

    def test_001_index_js(self):

        text1 = """
            $include("./daedalus.js")
        """

        text2 = """
            //export {a as b, c as d} from "./daedalus.js"
            export * from "./daedalus.js"
        """

        ast1 = self.parse(text1)
        ast1, imports1, modimports1, exports1 = getModuleImportExport(ast1)

        ast2 = self.parse(text2)
        ast2, imports2, modimports2, exports2 = getModuleImportExport(ast2)

        self.assertEqual(imports1, imports2)
        self.assertEqual(modimports1, modimports2)
        self.assertEqual(exports1, exports2)

        self.assertFalse(parsecmp(ast1, ast2, False))

    def test_001_include(self):

        text1 = """
            $include("./daedalus.js")
            //$import("./daedalus.js", {a,b,c})
        """

        text2 = """
            import {a,b,c} from "./daedalus.js"
        """

        ast1 = self.parse(text1)
        ast2 = self.parse(text2)

        ast1, imports1, modimports1, exports1 = getModuleImportExport(ast1)
        ast2, imports2, modimports2, exports2 = getModuleImportExport(ast2)

        # include no requires the list of names to include
        self.assertEqual(imports1.keys(), imports2.keys())
        self.assertEqual(modimports1, modimports2)
        self.assertEqual(exports1, exports2)

        self.assertFalse(parsecmp(ast1, ast2, False))

    def test_001_import_module(self):

        text1 = """
            $import("axertc_common", {a,b,c})
        """

        text2 = """
            import {a,b,c} from "@axertc/axertc_common"
        """

        ast1 = self.parse(text1)
        ast2 = self.parse(text2)

        #print(ast1.toString(2))
        #print(ast2.toString(2))

        ast1, imports1, modimports1, exports1 = getModuleImportExport(ast1)
        ast2, imports2, modimports2, exports2 = getModuleImportExport(ast2)

        #print(ast1.toString(2))
        #print(ast2.toString(2))
        #print("imports", imports1)
        #print("imports", imports2)
        #print("modimports", modimports1)
        #print("modimports", modimports2)
        #print("exprots", exports1)
        #print("exprots", exports2)

        self.assertEqual(imports1, imports2)
        self.assertEqual(modimports1, modimports2)
        self.assertEqual(exports1, exports2)

        self.assertFalse(parsecmp(ast1, ast2, False))

    def test_001_export_type(self):

        text1 = """
            export type Point = {x: number, y:number}
        """

        ast1 = self.parse(text1)

        ast1, imports1, modimports1, exports1 = getModuleImportExport(ast1)

        expected_ast = TOKEN('T_MODULE', '', 
            TOKEN('T_TYPE', 'type', 
                TOKEN('T_ASSIGN', '=', 
                    TOKEN('T_GLOBAL_VAR', 'Point'), 
                    TOKEN('T_OBJECT', '{}', 
                        TOKEN('T_BINARY', ':', 
                            TOKEN('T_STRING', "'x'"), 
                            TOKEN('T_GLOBAL_VAR', 'number')), 
                        TOKEN('T_BINARY', ':', 
                            TOKEN('T_STRING', "'y'"), 
                            TOKEN('T_GLOBAL_VAR', 'number'))))))

        self.assertFalse(parsecmp(ast1, expected_ast, False))
        self.assertEqual(exports1, ['Point'])

        text = Formatter().format(ast1)
        expected_text = "const Point=undefined"
        self.assertEqual(text, expected_text)

def main():
    unittest.main()


if __name__ == '__main__':
    main()
