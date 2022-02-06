#! cd .. && python3 -m tests.vm_test

"""
warn when stack is not empty after function clal
"""

import time
import unittest
from tests.util import edit_distance

from daedalus.lexer import Lexer
from daedalus.parser import Parser
from daedalus.transform import VariableScope, TransformIdentityScope, TransformReplaceIdentity, TransformClassToFunction
from daedalus.vm import VmCompiler, VmRuntime, VmTransform, VmRuntimeException


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
        print("evaljs diag", ast.toString(1))

    compiler = VmCompiler()
    module = compiler.compile(ast)

    if diag:
        module.dump()

    runtime = VmRuntime()
    runtime.enable_diag = diag
    runtime.init(module)

    # throws VmRuntimeException
    result = runtime.run()

    return result

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

    def test_function_dowhile(self):
        text = """
            i  = 5

            do {
                i -= 1
            } while (i > 0);
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
            function fn_try_catch_finally() {
                try {
                    throw "error"
                } catch (ex) {
                    g |= 1
                } finally {
                    g |= 2
                }
            }

            fn_try_catch_finally()

        """
        result, globals_ = evaljs(text, diag=False)
        self.assertEqual(globals_.values['g'], 3)

    def test_try_finally_throw_2(self):
        text = """
            let g = 0;

            function fn_throw() {
                throw "error"
            }

            function fn_try_finally() {
                try {
                    fn_throw()
                } finally {
                    // unhandled exception
                    g |= 2
                }
            }

            fn_try_finally()
        """

        with self.assertRaises(VmRuntimeException) as e:
            result, globals_ = evaljs(text, diag=False)

        # check that the finally block was run, even though
        # the exception is unhandled.
        self.assertEqual(e.exception.frames[0].globals.values['g'], 2)

    def test_try_catch_finally_throw_3(self):
        text = """
            let g = 0;

            function fn_throw() {
                throw "error"
            }

            function fn_try_catch_finally() {
                try {
                    fn_throw()
                } catch (ex) {
                    g |= 2
                } finally {
                    g |= 4
                }
            }

            fn_try_catch_finally()
        """
        result, globals_ = evaljs(text, diag=False)
        self.assertEqual(globals_.values['g'], 6)

    def test_try_catch_finally_throw_4(self):
        text = """
            let g = 0;

            function fn_throw() {
                throw "error"
            }

            function fn_try_finally() {
                try {
                    fn_throw()
                } finally {
                    // unhandled exception
                    g |= 1
                }
            }


            function fn_try_catch_finally_2() {
                try {
                    fn_try_finally()
                } catch (ex) {
                    g |= 2
                } finally {
                    g |= 4
                }
            }

            fn_try_catch_finally_2()
        """
        result, globals_ = evaljs(text, diag=False)
        self.assertEqual(globals_.values['g'], 7)

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

    def test_regex_match(self):

        text = """
            x = "abc".match(/A/i)
        """
        result, globals_ = evaljs(text, diag=False)
        self.assertEqual(globals_.values['x'], True)

    def test_fix_incr(self):

        text = """
            a = 0;
            b = ++a;
            c = a++;
            d = a
            e = --a;
            f = a--;
            g = a
        """
        result, globals_ = evaljs(text, diag=False)
        self.assertEqual(globals_.values['b'], 1)
        self.assertEqual(globals_.values['c'], 1)
        self.assertEqual(globals_.values['d'], 2)
        self.assertEqual(globals_.values['e'], 1)
        self.assertEqual(globals_.values['f'], 1)
        self.assertEqual(globals_.values['g'], 0)
        self.assertEqual(globals_.values['a'], 0)

    def test_null_assign(self):

        text = """
            a ??= 4

            b = null
            b ??= 4

            c = 1
            c ??= 4

        """
        result, globals_ = evaljs(text, diag=False)
        self.assertEqual(globals_.values['a'], 4)
        self.assertEqual(globals_.values['b'], 4)
        self.assertEqual(globals_.values['c'], 1)

    def test_var_scope(self):

        text = """
            function g() {
                var x = 1;
                {
                    var x = 2;
                }
                return x;
            }
            result=g() // 2
        """
        result, globals_ = evaljs(text, diag=False)
        self.assertEqual(globals_.values['result'], 2)

    def test_let_scope(self):

        text = """
            function f() {
                let x = 1;
                {
                    let x = 2;
                }
                return x;
            }
            result=f() // 1
        """
        result, globals_ = evaljs(text, diag=False)
        self.assertEqual(globals_.values['result'], 1)

    def test_const_scope(self):

        text = """
            function f() {
                const x = 1;
                {
                    const x = 2;
                }
                return x;
            }
            result=f() // 1
        """
        result, globals_ = evaljs(text, diag=False)
        self.assertEqual(globals_.values['result'], 1)

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

    def test_template_string_1(self):
        text = """
            let height = 1
            let s = `{height: ${height+1}em}`
        """
        result, globals_ = evaljs(text, diag=False)
        self.assertEqual(globals_.values['s'], "{height: 2em}")

    def test_template_string_2(self):
        text = """
            let height = 1
            let s = `${height+1}`
        """
        result, globals_ = evaljs(text, diag=False)
        self.assertEqual(globals_.values['s'], "2")

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

    def test_while_break_continue(self):

        text = """
            // Collatz conjecture
            n = 11

            b = 0
            c = 0

            while (n > 0) {

                if (n%2 == 0) {
                    n = n / 2
                    c += 1
                    continue;
                } else if (n == 1) {
                    b += 1
                    break
                } else {
                    n = 3 * n + 1
                }
            }
        """
        result, globals_ = evaljs(text, diag=False)
        self.assertEqual(globals_.values['n'], 1)
        self.assertEqual(globals_.values['b'], 1)
        self.assertEqual(globals_.values['c'], 10)

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

    def test_spread_call(self):

        text = """

            function spread(a, ...args) {return [a, args]}
            a = [1,2,3]
            x = spread(...a)
        """
        result, globals_ = evaljs(text, diag=False)
        a = globals_.values['x'].array[0]
        b = globals_.values['x'].array[1]
        self.assertEqual(a, 1)
        self.assertEqual(b.array, [2, 3])

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
        self.assertEqual(globals_.values['result'], "a_x1=y1,b_x2=y2")

    def test_reflective_object(self):

        text = """
            mymodule = (function() {
                const obj = {
                    a: function(){return 1},
                    b: function(){return obj.a()}
                }
                return {obj}
            })()
            let result = mymodule.obj.b()
        """
        result, globals_ = evaljs(text, diag=False)
        self.assertEqual(globals_.values['result'], 1)


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

class VmArrayTestCase(unittest.TestCase):

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

    def test_array_construct(self):

        text = """
            x = [4,8,12]
            l = x.length
        """
        result, globals_ = evaljs(text, diag=False)
        self.assertEqual(globals_.values['x'].array, [4,8,12])
        self.assertEqual(globals_.values['l'], 3)

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

    def test_promise_simple(self):

        text = """

        let x = 0;
        const p = new Promise((resolve, reject) => {
            resolve(2);
        })

        p.then(res=>{x=res})
        """
        result, globals_ = evaljs(text, diag=False)
        self.assertEqual(globals_.values['x'], 2)

    def test_promise_timeout(self):

        text = """

        let x = 0;
        const p = new Promise((resolve, reject) => {
            setTimeout(()=>{resolve(4);}, 66)
        })

        p.then(res=>{x=res})
        """
        t0= time.time()
        result, globals_ = evaljs(text, diag=False)
        self.assertEqual(globals_.values['x'], 4)
        t1= time.time()
        self.assertTrue((t1 - t0) > 0.066)

def main():
    unittest.main()

if __name__ == '__main__':
    main()
