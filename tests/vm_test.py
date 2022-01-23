#! cd .. && python3 -m tests.vm_test -v

"""
warn when stack is not empty after function clal
"""

import unittest
from tests.util import edit_distance

from daedalus.lexer import Lexer
from daedalus.parser import Parser
from daedalus.transform import VariableScope, TransformIdentityScope, TransformReplaceIdentity, TransformClassToFunction
from daedalus.vm import VmCompiler, VmRuntime, VmTransform


VariableScope.disable_warnings = True

def evaljs(text, diag=False):

    lexer = Lexer()
    parser = Parser()
    parser.disable_all_warnings = True

    tokens = lexer.lex(text)
    ast = parser.parse(tokens)

    xform = TransformIdentityScope()
    xform.disable_warnings=True
    xform.transform(ast)

    xform = VmTransform()
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



    def test_assign(self):

        text = """
            let x = "abc"
        """
        result, globals_ = evaljs(text, diag=False)
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
        result, globals_ = evaljs(text, diag=False)
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
        result, globals_ = evaljs(text, diag=False)
        self.assertEqual(globals_.values['x'], 6)

    def test_math_unary_not(self):

        text = """
            var x = !false
        """
        result, globals_ = evaljs(text, diag=False)
        self.assertEqual(globals_.values['x'], 1)

    def test_function_while(self):
        text = """
            i  = 5

            while (i > 0) {
                i -= 1
            }
        """
        result, globals_ = evaljs(text, diag=False)
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
        result, globals_ = evaljs(text, diag=False)
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
        result, globals_ = evaljs(text, diag=False)
        self.assertEqual(globals_.values['y'], 120)

    def test_lambda_simple(self):

        text = """
            add = (a=2,b=2) => {return a + b}
            let r1 = add()
            let r2 = add(1)
            let r3 = add(6,7)
        """
        result, globals_ = evaljs(text, diag=False)
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
        result, globals_ = evaljs(text, diag=False)
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
        result, globals_ = evaljs(text, diag=False)
        self.assertEqual(globals_.values['y'], 1)
        self.assertEqual(globals_.values['z'], 2)

    def test_array_simple(self):
        text = """

            x = [4,5,6]
            a = x[0]
            b = x[1]
            c = x[2]

            x[2] = 12
            d = x[2]
        """
        result, globals_ = evaljs(text, diag=False)
        self.assertEqual(globals_.values['a'], 4)
        self.assertEqual(globals_.values['b'], 5)
        self.assertEqual(globals_.values['c'], 6)

        self.assertEqual(globals_.values['d'], 12)

    def test_try_catch_finally_throw_1(self):
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
        result, globals_ = evaljs(text, diag=False)
        self.assertEqual(globals_.values['g'], 3)

    def test_class_simple(self):
        text = """

            class Point {
                constructor(x, y) {

                    this.x = x
                    this.y = y
                }

                get_x() {
                    return this.x
                }
            }

            p = Point(6, 7)
            x = p.x
            y = p.y

            x2 = p.get_x()
        """
        result, globals_ = evaljs(text, diag=False)
        self.assertEqual(globals_.values['x'], 6)
        self.assertEqual(globals_.values['y'], 7)
        self.assertEqual(globals_.values['x2'], 6)

    def test_class_simple_inheritance(self):
        text = """

            class Point {
                constructor(x, y) {

                    this.x = x
                    this.y = y
                }

                get_x() {
                    return this.x
                }
            }

            class Point2 extends Point {
                constructor(x, y) {
                    super(x, y)
                }

                mul() {
                    return this.x * this.y
                }
            }

            p = Point2(6, 7)
            x = p.x
            y = p.y
            x2 = p.get_x()
            m = p.mul()
        """
        result, globals_ = evaljs(text, diag=False)
        self.assertEqual(globals_.values['x'], 6)
        self.assertEqual(globals_.values['y'], 7)
        self.assertEqual(globals_.values['x2'], 6)
        self.assertEqual(globals_.values['m'], 42)

    @unittest.expectedFailure
    def test_null_assign(self):

        text = """
            a ??= 4

            b = undefined
            b ??= 4

            c = 1
            c ??= 4

        """
        result, globals_ = evaljs(text, diag=False)
        self.assertEqual(globals_.values['a'], 4)
        self.assertEqual(globals_.values['b'], 4)
        self.assertEqual(globals_.values['c'], 1)

class VmBasicTypesTestCase(unittest.TestCase):

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

    def test_template_string(self):
        text = """
            let height = 1
            let s = `{height: ${height+1}em}`
        """
        result, globals_ = evaljs(text, diag=False)
        self.assertEqual(globals_.values['s'], "{height: 2em}")


class VmLogicTestCase(unittest.TestCase):

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

    def test_logical_and(self):
        text = """
            let a = [
                true && true,
                true && false,
                false && true,
                false && false,
            ]
        """
        result, globals_ = evaljs(text, diag=False)
        self.assertEqual(globals_.values['a'].array, [True, False, False, False])

    def test_logical_or(self):
        text = """
            let a = [
                true || true,
                true || false,
                false || true,
                false || false,
            ]
        """
        result, globals_ = evaljs(text, diag=False)
        self.assertEqual(globals_.values['a'].array, [True, True, True, False])

    def test_ternary(self):

        text = """
            let a = true?4:8
            let b = false?4:8
        """
        result, globals_ = evaljs(text, diag=False)
        self.assertEqual(globals_.values['a'], 4)
        self.assertEqual(globals_.values['b'], 8)

    def test_null_coalescing(self):

        text = """
            let w = 1 ?? 4          // 1
            let x = 0 ?? 4          // 0
            let y = undefined ?? 4  // 4
            let z = null ?? 4       // 4
        """
        result, globals_ = evaljs(text, diag=False)
        self.assertEqual(globals_.values['w'], 1)
        self.assertEqual(globals_.values['x'], 0)
        self.assertEqual(globals_.values['y'], 4)
        self.assertEqual(globals_.values['z'], 4)

class VmFunctionTestCase(unittest.TestCase):

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

    def test_lambda1(self):

        text = """
            const f = (x)=>x
            x = f(1)
        """
        result, globals_ = evaljs(text, diag=False)
        self.assertEqual(globals_.values['x'], 1)

    def test_lambda2(self):

        text = """
            const f = a => { return b => { return b+a } }
            let x = f(6)(7)
        """
        result, globals_ = evaljs(text, diag=False)
        self.assertEqual(globals_.values['x'], 13)

    def test_lambda3(self):

        text = """
            const f = a => { return b => b+a }
            let x = f(6)(7)
        """
        result, globals_ = evaljs(text, diag=False)
        self.assertEqual(globals_.values['x'], 13)

    def test_lambda4(self):

        text = """
            const f = a => b => b+a
            let x = f(6)(7)
        """
        result, globals_ = evaljs(text, diag=False)
        self.assertEqual(globals_.values['x'], 13)

    @unittest.expectedFailure
    def test_spread_call(self):

        text = """

            function sum(a,b,c) {return a+b+c}
            a = [1,2,3]
            x = sum(...a)
        """
        result, globals_ = evaljs(text, diag=False)
        self.assertEqual(globals_.values['x'], 13)

    def test_cell_lambda_recursion(self):

        text = """
            //obj2 is a cell variable, and a function argument
            // it requires special handling when building the stack frame

            function r1(obj2) {

                let result = Object.keys(obj2).map(key => {
                    let val = obj2[key]
                    if (typeof(val) === 'object') {
                        return key + "_" + r1(val)
                    } else {
                        return key+"="+val
                    }
                })
                return result.join(",")
            }

            let obj = {"a": {"x1": "y1"}, "b": {"x2": "y2"}}
            let result = r1(obj)

        """
        result, globals_ = evaljs(text, diag=False)
        self.assertEqual(globals_.values['result'], "b_x2=y2,a_x1=y1")

class VmObjectTestCase(unittest.TestCase):

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

    def test_object_construct(self):

        text = """
            let a = 1, b = 2;
            let o = {a, b}
            let t1 = "a" in o
            let t2 = "c" in o
        """
        result, globals_ = evaljs(text, diag=False)
        obj = globals_.values['o']
        a = obj.getAttr('a')
        b = obj.getAttr('b')
        self.assertEqual(a, 1)
        self.assertEqual(b, 2)
        self.assertEqual(globals_.values['t1'], True)
        self.assertEqual(globals_.values['t2'], False)

    def test_object_construct_spread(self):

        text = """
            let o1 = {a:0, b:2}
            let o2 = {a:1, ...o1, c:3}
        """
        result, globals_ = evaljs(text, diag=False)
        obj = globals_.values['o2']
        a = obj.getAttr('a')
        b = obj.getAttr('b')
        c = obj.getAttr('c')
        self.assertEqual(a, 0)
        self.assertEqual(b, 2)
        self.assertEqual(c, 3)

    def test_object_delete(self):

        text = """
            let o = {a:1, b:2}
            delete o.a
            delete o['b']

            let t1 = 'a' in o
            let t2 = 'b' in o
        """
        result, globals_ = evaljs(text, diag=False)
        self.assertEqual(globals_.values['t1'], False)
        self.assertEqual(globals_.values['t2'], False)


class VmTimerTestCase(unittest.TestCase):
    # test for setTimeout, setInterval, and Promises

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



def main():
    unittest.main()

if __name__ == '__main__':
    main()
