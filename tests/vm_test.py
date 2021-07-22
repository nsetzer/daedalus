#! cd .. && python3 -m tests.vm_test -v

"""
warn when stack is not empty after function clal
"""

import unittest
from tests.util import edit_distance

from daedalus.lexer import Lexer
from daedalus.parser import Parser
from daedalus.transform import VariableScope, TransformIdentityScope, TransformReplaceIdentity, TransformClassToFunction
from daedalus.vm import VmCompiler, VmRuntime


VariableScope.disable_warnings = True

class VmTestCase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):

        cls.lexer = Lexer()
        cls.parser = Parser()
        cls.parser.disable_all_warnings = True

    @classmethod
    def tearDownClass(cls):
        pass

    def setUp(self):
        super().setUp()

    def tearDown(self):
        super().tearDown()

    def evaljs(self, text, diag=False):

        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)

        xform = TransformIdentityScope()
        xform.disable_warnings=True
        xform.transform(ast)

        if diag:
            print(ast.toString(1))

        compiler = VmCompiler()
        module = compiler.compile(ast)

        if diag:
            module.dump()

        runtime = VmRuntime()
        runtime.enable_diag = diag
        runtime.init(module)
        return runtime.run()

    def test_assign(self):

        text = """
            let x = "abc"
        """
        result, globals_ = self.evaljs(text, diag=False)
        self.assertEqual(globals_.values['x'].value, "abc")

    def test_branch_false(self):

        text = """
            var x = 0
            if (x) {
                x += 5
            } else {
                x += 7
            }
        """
        result, globals_ = self.evaljs(text, diag=False)
        self.assertEqual(globals_.values['x'], 7)

    def test_branch_true(self):

        text = """
            var x = 1
            if (x) {
                x += 5
            } else {
                x += 7
            }
        """
        result, globals_ = self.evaljs(text, diag=False)
        self.assertEqual(globals_.values['x'], 6)

    def test_function_while(self):
        text = """
            i  = 5

            while (i > 0) {
                i -= 1
            }
        """
        result, globals_ = self.evaljs(text, diag=False)
        self.assertEqual(globals_.values['i'], 0)

    def test_function_simple(self):

        text = """
            function mult(x=2,y=4) {
                return x * y
            }

            const a = mult()
            const b = mult(4)
            const c = mult(4, 5)
            const d = mult(1, 2, 3, 4)
        """
        result, globals_ = self.evaljs(text, diag=False)
        self.assertEqual(globals_.values['a'], 8)
        self.assertEqual(globals_.values['b'], 16)
        self.assertEqual(globals_.values['c'], 20)
        self.assertEqual(globals_.values['d'], 2)

    def test_function_factorial(self):

        text = """
            function factorial(i) {
                if (i < 1) {
                    return 1
                } else {
                    return i * factorial(i-1)
                }
            }

            const y = factorial(5)
        """
        result, globals_ = self.evaljs(text, diag=False)
        self.assertEqual(globals_.values['y'], 120)

    def test_lambda_simple(self):

        text = """
            add = (a=2,b=2) => {return a + b}
            let r1 = add()
            let r2 = add(1)
            let r3 = add(6,7)
        """
        result, globals_ = self.evaljs(text, diag=False)
        self.assertEqual(globals_.values['r1'],  4)
        self.assertEqual(globals_.values['r2'],  3)
        self.assertEqual(globals_.values['r3'], 13)

    def test_lambda_bind(self):

        text = """
            function f() {
                x = 5;
                return () => {this.x+=1; return this.x};
            }
            g = f()
            r1 = g()
            r2 = g()
            r3 = g()
        """
        result, globals_ = self.evaljs(text, diag=False)
        self.assertEqual(globals_.values['r1'], 6)
        self.assertEqual(globals_.values['r2'], 7)
        self.assertEqual(globals_.values['r3'], 8)

    def test_object_simple(self):
        text = """

            x = {"a": 1}
            y = x.a


            x.a = 2
            z = x.a

        """
        result, globals_ = self.evaljs(text, diag=False)
        self.assertEqual(globals_.values['y'], 1)
        self.assertEqual(globals_.values['z'], 2)

    def test_array_simple(self):
        text = """

            x = [4,5,6]
            x[2] = 12
            a = x[1]
            b = x[2]

        """
        result, globals_ = self.evaljs(text, diag=False)
        print(globals_.values)
        self.assertEqual(globals_.values['a'],  5)
        self.assertEqual(globals_.values['b'], 12)

    def test_try_catch_finally(self):
        text = """

            let g = 0
            function f() {
                try {
                    throw "error"
                } catch (ex) {
                    g |= 1
                } finally {
                    g |= 2
                }
            }
            f()

        """
        result, globals_ = self.evaljs(text, diag=False)
        self.assertEqual(globals_.values['g'], 3)

def main():
    unittest.main()

if __name__ == '__main__':
    main()
