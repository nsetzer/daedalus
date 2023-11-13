#! cd .. && python3 -m tests.vm_test
#! cd .. && python3 -m tests.vm_test VmLogicTestCase.test_switch_1

"""
warn when stack is not empty after function clal
"""

import time
import unittest
import math
import io

from daedalus.lexer import Lexer
from daedalus.parser import Parser
from daedalus.transform import VariableScope, TransformIdentityBlockScope
from daedalus.vm import VmCompiler, VmRuntime, VmRuntimeException
from daedalus.vm_compiler import VmCompileError, VmTransform, VmClassTransform2, VmGlobals, VmInstruction
from daedalus.vm_primitive import JsUndefined
from daedalus import vm_opcodes as opcodes


VariableScope.disable_warnings = True

def disjs(text, index=0):

    lexer = Lexer()
    parser = Parser()
    parser.disable_all_warnings = True

    tokens = lexer.lex(text)
    ast = parser.parse(tokens)

    xform = VmClassTransform2()
    xform.transform(ast)

    xform = TransformIdentityBlockScope()
    xform.disable_warnings=True
    xform.transform(ast)

    xform = VmTransform()
    xform.transform(ast)

    compiler = VmCompiler()
    module = compiler.compile(ast)

    instrs = module.functions[index].instrs

    instrs = [(b.opcode, b.args) for b in instrs]

    return instrs

def make_runtime(text, diag=False):

    lexer = Lexer()
    parser = Parser()
    parser.disable_all_warnings = True

    tokens = lexer.lex(text)
    ast = parser.parse(tokens)

    xform = VmClassTransform2()
    xform.transform(ast)

    xform = TransformIdentityBlockScope()
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

    return runtime

def evaljs(text, diag=False):

    lexer = Lexer()
    parser = Parser()
    parser.disable_all_warnings = True

    tokens = lexer.lex(text)
    ast = parser.parse(tokens)

    xform = VmClassTransform2()
    xform.transform(ast)

    xform = TransformIdentityBlockScope()
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

class VmUtilsTestCase(unittest.TestCase):

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

    def test_lebu(self):
        expected=0xAA<<8|0xBB
        out = opcodes.LEB128u(expected)
        self.assertEqual(out, b'\xbb\xd5\x02')
        value = opcodes.read_LEB128u(io.BytesIO(out))
        self.assertEqual(value, expected)

    def test_lebs_pos(self):
        expected=0xAA<<8|0xBB
        out = opcodes.LEB128s(expected)
        self.assertEqual(out, b'\xbb\xd5\x02')
        value = opcodes.read_LEB128s(io.BytesIO(out))
        self.assertEqual(value, expected)


    def test_lebs_neg(self):
        expected = -(0xAA<<8|0xBB)
        out = opcodes.LEB128s(expected)
        self.assertEqual(out, b'\xc5\xaa}')
        value = opcodes.read_LEB128s(io.BytesIO(out))
        self.assertEqual(value, expected)


    def test_isntr_fmt(self):
        """ demonstrate how instructions are formatted
        """

        globals_ = VmGlobals()
        globals_.names.append('global0')
        globals_.constdata.append('str0')
        locals_ = ['local0', 'attr1']
        cells_ = ['cell0']

        instr0 = VmInstruction(opcodes.globalvar.GET, 0)
        self.assertEqual(instr0.getArgString(globals_, locals_, cells_), "0:global0")

        instr0 = VmInstruction(opcodes.localvar.GET, 0)
        self.assertEqual(instr0.getArgString(globals_, locals_, cells_), "0:local0")

        instr0 = VmInstruction(opcodes.cellvar.GET, 0)
        self.assertEqual(instr0.getArgString(globals_, locals_, cells_), "0:cell0")

        instr0 = VmInstruction(opcodes.obj.GET_ATTR, 1)
        self.assertEqual(instr0.getArgString(globals_, locals_, cells_), "1:attr1")

        instr0 = VmInstruction(opcodes.const.STRING, 0)
        self.assertEqual(instr0.getArgString(globals_, locals_, cells_), "0:str0")

        instr0 = VmInstruction(opcodes.const.FLOAT32, 3.14)
        self.assertEqual(instr0.getArgString(globals_, locals_, cells_), "3.14")

        self.assertEqual(repr(VmInstruction(opcodes.const.STRING, 0)), "(const.STRING 0)")

        self.assertEqual(repr(VmInstruction(opcodes.comp.LT)), "(comp.LT)")

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

    def test_empty_stack(self):
        # the stack frame should be empty when the function exits
        text = """
            "abc";
            123;
        """
        runtime = make_runtime(text, diag=False)
        runtime.run()
        self.assertEqual(runtime.stack_frames, [])


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

    def test_function_dowhile_break(self):
        text = """
            let x =0;
            do {
                x += 2;
                {
                    break
                    let x = 3
                }
            }    while (x < 5);
        """
        result, globals_ = evaljs(text, diag=False)
        self.assertEqual(globals_.values['x'], 2)


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

class VmCodeFormatTestCase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):

        cls.lexer = Lexer()
        cls.parser = Parser()
        cls.parser.disable_all_warnings = True

    def test_multiline_comment(self):
        text = """
            /**
            comment
            **/
            x='\\p\\U0001f441'
            y='\\p\\U00000000'
        """
        result, globals_ = evaljs(text, diag=False)
        self.assertEqual(globals_.values['x'], '\\p\ud83d\udc41')
        self.assertEqual(globals_.values['y'], '\\p\x00')

    def test_multistring(self):
        text = """
            x='a' 'b' 'c'
        """
        result, globals_ = evaljs(text, diag=False)
        self.assertEqual(globals_.values['x'], 'abc')


    def test_multiline_expr(self):
        text = """
            let x = 1 + \\
            2
        """
        result, globals_ = evaljs(text, diag=False)
        self.assertEqual(globals_.values['x'], 3)

    def test_numbers(self):
        text = """
            let x = 1 + .5 + 1.0
        """
        result, globals_ = evaljs(text, diag=False)
        self.assertEqual(globals_.values['x'], 2.5)

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


    def test_number_bin(self):
        text = """
            let x1 = 0b0001_0001
        """
        result, globals_ = evaljs(text, diag=False)
        self.assertEqual(globals_.values['x1'], 17)

    def test_number_oct(self):
        text = """
            let x1 = 0777
            let x2 = 0888
            let x3 = 0o123
        """
        result, globals_ = evaljs(text, diag=False)
        self.assertEqual(globals_.values['x1'], 511)
        self.assertEqual(globals_.values['x2'], 888)
        self.assertEqual(globals_.values['x3'], 83)

    def test_number_hex(self):
        text = """
            let x1 = 0x777
            let x2 = 0x888
        """
        result, globals_ = evaljs(text, diag=False)
        self.assertEqual(globals_.values['x1'], 1911)
        self.assertEqual(globals_.values['x2'], 2184)

    def test_number_float(self):
        text = """
            let x1 = 3.14
            let x2a = 1e-3
            let x2b = 1E-3
            let x2c = 1E+3
            let x3 = 2e6
            let x4 = 0.1e2
        """
        result, globals_ = evaljs(text, diag=False)
        self.assertEqual(globals_.values['x1'], 3.14)
        self.assertEqual(globals_.values['x2a'], 0.001)
        self.assertEqual(globals_.values['x2b'], 0.001)
        self.assertEqual(globals_.values['x2c'], 1000.0)
        self.assertEqual(globals_.values['x3'], 2000000.0)
        self.assertEqual(globals_.values['x4'], 10.0)

    def test_number_float_error(self):
        text = """
            let x1 = 0x123.456
        """
        with self.assertRaises(VmCompileError):
            result, globals_ = evaljs(text, diag=False)

    def test_number_object(self):
        text = """
            //let x1 = Number.MAX_VALUE
            //let x2 = Number.MIN_VALUE
            let x3 = Number.POSITIVE_INFINITY
            let x4 = Number.NEGATIVE_INFINITY
            let x5 = Number.NaN

            let t = [
                Number.isInteger(3.0),
                Number.isNaN(Number.NaN),
            ]

            let f = [
                Number.isInteger(Math.PI),
                Number.isNaN(Math.PI),
            ]

        """
        result, globals_ = evaljs(text, diag=False)
        self.assertTrue(math.isnan(globals_.values['x5']))
        self.assertEqual(globals_.values['t'].array, [True]*2)
        self.assertEqual(globals_.values['f'].array, [False]*2)

    def test_math_object(self):
        text = """
            let x1 = Math.PI
        """
        result, globals_ = evaljs(text, diag=False)
        self.assertEqual(globals_.values['x1'], math.pi)


    def test_string_access(self):
        text = """
            let x1 = "abc"[1]
            let x2 = "abc".charAt(1)
        """
        result, globals_ = evaljs(text, diag=False)
        self.assertEqual(globals_.values['x1'], "b")
        self.assertEqual(globals_.values['x2'], "b")

    def test_string_case(self):
        text = """
            let x1 = "Aa".toUpperCase()
            let x2 = "Aa".toLowerCase()
        """
        result, globals_ = evaljs(text, diag=False)
        self.assertEqual(globals_.values['x1'], "AA")
        self.assertEqual(globals_.values['x2'], "aa")

    def test_unpack(self):
        text = """
            let [a,b,c] = [1,2,3]
        """
        result, globals_ = evaljs(text, diag=False)
        self.assertEqual(globals_.values['a'], 1)
        self.assertEqual(globals_.values['b'], 2)
        self.assertEqual(globals_.values['c'], 3)

    def test_list_spread(self):
        text = """
            let a = [1,2,3]
            let b = [5,6,7]

            let c = [0, ...a, 4, ...b]
        """
        result, globals_ = evaljs(text, diag=False)
        self.assertEqual(globals_.values['c'].array, list(range(8)))

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

    def test_custom_iterator(self):
        text = """
            let iter = {
                [Symbol.iterator]() {
                    let done = false
                    let value = 4
                    return {
                        next() {
                            value += 1
                            done = value > 10
                            return {done, value}
                        }
                    }
                }
            }

            let sum = 0
            for (let v of iter) {
                sum += v
            }
        """
        result, globals_ = evaljs(text, diag=False)
        self.assertEqual(globals_.values['sum'], 45)

    def test_for_in_iter_twice(self):
        text = """
            o1 = {'a':1, 'b': 2}
            o2 = {}
            o3 = {}

            for (const name in o1) {
                o2[name] = o1[name]*2
            }

            for (const name in o2) {
                o3[name] = o2[name]*2
            }

        """
        result, globals_ = evaljs(text, diag=False)
        self.assertEqual(globals_.values['o3'].getIndex('a'), 4)

    def test_for_of_iter_twice(self):
        text = """
            o1 = [0,1,2]
            o2 = [0,0,0]
            o3 = [0,0,0]
            n = 0
            for (const idx of o1) {
                o2[idx] = idx
                n += 1
            }

            for (const idx of o2) {
                o3[idx] = idx
                n += 1
            }

        """
        result, globals_ = evaljs(text, diag=False)
        self.assertEqual(globals_.values['o3'].getIndex(1), 1)
        self.assertEqual(globals_.values['n'], 6)

    def test_optional_chaining_attr(self):
        text = """
            o1 = {a: 1};
            v1 = o1?.a;
            v2 = o1?.b;
        """
        result, globals_ = evaljs(text, diag=False)
        self.assertEqual(globals_.values['v1'], 1)
        self.assertEqual(globals_.values['v2'], JsUndefined.instance)

    @unittest.skip("fixme")
    def test_optional_chaining_func(self):
        text = """
            o1 = {a: ()=>{}};
            v1 = o1.a?.();
        """
        result, globals_ = evaljs(text, diag=False)
        self.assertEqual(globals_.values['v1'].__class__.__name__, "JsObject")

    @unittest.skip("broken")
    def test_optional_chaining_list(self):
        text = """
            o1 = {a: [1,2,3]};
            v1 = o1.a?.[2];
            v2 = o1.a?.[4];
        """
        result, globals_ = evaljs(text, diag=False)
        self.assertEqual(globals_.values['v1'], 2)
        self.assertEqual(globals_.values['v2'], JsUndefined.instance)

    def test_switch_1(self):

        text = """
            function test(item) {
                let value = 0;
                switch (item) {
                    case 0:
                        value = 1;
                        break;
                    case 1:
                        value = 2;
                        break;
                    default:
                        value = 3;
                        break;
                }
                return value;
            }
            let x1 = test(0);
            let x2 = test(1);
            let x3 = test(2);
        """
        result, globals_ = evaljs(text, diag=False)
        self.assertEqual(globals_.values['x1'], 1)
        self.assertEqual(globals_.values['x2'], 2)
        self.assertEqual(globals_.values['x3'], 3)

    def test_division_1(self):

        text = """
            let n = 10;
            let d = 5
            n /= d;
        """
        result, globals_ = evaljs(text, diag=False)
        self.assertEqual(globals_.values['n'], 2)

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

    def test_extra_args(self):

        text = """

            function extra(a) {return arguments.length}
            x1 = extra(1)
            x2 = extra(1,2)
            x3 = extra(kwarg=0)
        """
        result, globals_ = evaljs(text, diag=False)
        self.assertEqual(globals_.values['x1'], 1)
        self.assertEqual(globals_.values['x2'], 2)
        self.assertEqual(globals_.values['x3'], 1)

    @unittest.skip("fixme")
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
                // this works easily when obj is in a global scope
                // but is challenging when using cell/free vars
                // the cell reference must be created before
                // the obj is instantiated and before the function b
                // is defined.
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

    @unittest.skip("not implemented")
    def test_function_typed(self):

        text = """
            function add(x: number, y: number): number {
                return x + y;
            }
            let result = add(2, 3)
        """
        result, globals_ = evaljs(text, diag=False)
        self.assertEqual(globals_.values['result'], 5)

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

    def test_class_ctor(self):
        text = """
            class A {
                constructor(v) {
                    this.a = v
                }
            }
            class B extends A {
                constructor() {
                    super(2)
                }
            }
            let b = B().a
        """
        result, globals_ = evaljs(text, diag=False)
        self.assertEqual(globals_.values['b'], 2)

    def test_nested_module(self):
        # this test is the reason for the per-identity transform
        text = """
            mymodule = (function() {
                class a {

                }

                class b extends a {

                }

                return {a, b}
            })()
        """
        runtime = make_runtime(text, diag=False)
        result, globals_ = runtime.run()
        self.assertEqual(globals_.values['mymodule'].getAttr('a').name, "a")
        self.assertEqual(globals_.values['mymodule'].getAttr('b').name, "b")

    def test_class_prototype(self):
        # this test is the reason for the per-identity transform
        text = """
            class A {
            constructor() {this.a=1}
            }
            A.prototype.va='a'
            class B extends A {
                constructor() {super(); this.b=2}
            }
            B.prototype.vb='b'

            let b = new B()
            let n1 = b.__proto__.constructor.name;
            let n2 = b.__proto__.__proto__.constructor.name;
            let v1 = b.va
            let v2 = b.vb

        """
        runtime = make_runtime(text, diag=False)
        result, globals_ = runtime.run()
        self.assertEqual(globals_.values['n1'], "B")
        self.assertEqual(globals_.values['n2'], "A")
        self.assertEqual(globals_.values['v1'], "a")
        self.assertEqual(globals_.values['v2'], "b")

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

@unittest.skip("not working with defered jsc")
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

    def test_promise_resolve(self):

        text = """

        let x = 0;
        const p = new Promise((resolve, reject) => {
            resolve(2);
        })

        p.then(res=>{x=res})
        """
        result, globals_ = evaljs(text, diag=False)
        self.assertEqual(globals_.values['x'], 2)

    def test_promise_reject(self):

        text = """

        let x = 0;
        let y = 0;
        const p = new Promise((resolve, reject) => {
            reject(2);
        })

        p.then(res=>{x=res}, err=>{y=err})
        """
        result, globals_ = evaljs(text, diag=False)
        self.assertEqual(globals_.values['y'], 2)

    def test_promise_throw(self):

        text = """

        let x = 0;
        let y = 0;
        let z = 0;
        const p = new Promise((resolve, reject) => {
            throw 123
        })

        p.then(res=>{x=1}, err=>{y=err}).catch(err=>{z=err})
        """
        result, globals_ = evaljs(text, diag=False)
        self.assertEqual(globals_.values['x'], 0)
        self.assertEqual(globals_.values['y'], 123)
        self.assertEqual(globals_.values['z'], 123)

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
        self.assertTrue((t1 - t0) < 0.1)

    def test_timeout(self):

        text = """
        x=0;
        setTimeout(()=>{x+=1;}, 33);
        wait(500)
        """
        t0= time.time()
        result, globals_ = evaljs(text, diag=False)
        self.assertEqual(globals_.values['x'], 1)
        t1= time.time()
        self.assertTrue((t1 - t0) > 0.033)
        self.assertTrue((t1 - t0) < 0.1)

    def test_interval(self):

        text = """
        x=0;
        setInterval(()=>{x+=1;}, 33);
        wait(500)
        wait(500)
        """
        t0= time.time()
        result, globals_ = evaljs(text, diag=False)
        self.assertEqual(globals_.values['x'], 2)
        t1= time.time()
        self.assertTrue((t1 - t0) > 0.066)
        self.assertTrue((t1 - t0) < 0.1)

class VmImportTestCase(unittest.TestCase):
    # test for setTimeout, setInterval, and Promises

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

    def test_dis_import(self):

        text = """
        import module daedalus
        """
        instrs = disjs(text)
        expected = [
            (opcodes.const.STRING, (0,)),
            (opcodes.ctrl.IMPORT, ()),
            (opcodes.ctrl.IMPORT2, ()),
            (opcodes.globalvar.SET, (0,)),
            (opcodes.ctrl.EXPORT, ())
        ]
        self.assertEqual(expected, instrs)

    def test_dis_import_name(self):

        text = """
        import module a.b.c
        """
        instrs = disjs(text)
        expected = [
            (opcodes.const.STRING, (0,)),
            (opcodes.ctrl.IMPORT, ()),
            (opcodes.ctrl.IMPORT2, ()),
            (opcodes.globalvar.SET, (0,)),
            (opcodes.ctrl.EXPORT, ())
        ]
        self.assertEqual(expected, instrs)

    def test_dis_import_path(self):

        text = """
        import module "./foo.js"
        """
        instrs = disjs(text)
        expected = [
            (opcodes.const.STRING, (0,)),
            (opcodes.ctrl.IMPORT, ()),
            (opcodes.ctrl.IMPORT2, ()),
            (opcodes.globalvar.SET, (0,)),
            (opcodes.ctrl.EXPORT, ())
        ]
        self.assertEqual(expected, instrs)

    def test_pyimport(self):

        text = """
        pyimport math
        const x = math.sqrt(16)
        """
        result, globals_ = evaljs(text, diag=False)
        self.assertEqual(globals_.values['x'], 4)

class VmExportTestCase(unittest.TestCase):
    # test for setTimeout, setInterval, and Promises

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

    @unittest.skip("not implemented")
    def test_dis_export(self):

        text = """
        let value1 = 1
        export value1, value2=2;
        """
        instrs = disjs(text)
        expected = [
            (opcodes.const.INT, (1,)),
            (opcodes.globalvar.SET, (0,)),
            (opcodes.ctrl.EXPORT, ())
        ]
        print(expected)
        print(instrs)
        self.assertEqual(expected, instrs)

class VmWebDocumentTestCase(unittest.TestCase):

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

    def test_array_construct(self):

        text = """
            //let style = document.createElement("style")
            let div = document.createElement("div")

            let str = div.toString()
        """
        result, globals_ = evaljs(text, diag=False)
        self.assertEqual(globals_.values['str'].value, '<div>\n</div>')

def main():
    unittest.main()

if __name__ == '__main__':
    main()
