#! cd .. && python3 -m tests.compiler_test -v

import unittest
from tests.util import edit_distance

from daedalus.lexer import Lexer
from daedalus.parser import Parser
from daedalus.transform import VariableScope

try:

    from daedalus.compiler import Compiler
    from daedalus.builtins import JsObject, JsArray, JsUndefined

    VariableScope.disable_warnings = True

    class CompilerTestCase(unittest.TestCase):

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

            interpreter = Compiler()
            interpreter.compile(ast)
            if diag:
                print(ast.toString(3))
            if diag:
                interpreter.dump()
            return interpreter.execute()

        def test_evaljs_lambda_simple_expr(self):

            text = """
                x = () => 0
                return x()
            """
            result = self.evaljs(text)
            self.assertEqual(result, 0)

        def test_evaljs_lambda_simple_block(self):

            text = """
                x = () => {return 0}
                return x()
            """
            result = self.evaljs(text)
            self.assertEqual(result, 0)

        def test_evaljs_lambda_1arg_v1(self):

            text = """
                x = value => {return value}
                return x(42)
            """
            result = self.evaljs(text)
            self.assertEqual(result, 42)

        def test_evaljs_lambda_1arg_v2(self):

            text = """
                x = (value) => {return value}
                return x(42)
            """
            result = self.evaljs(text)
            self.assertEqual(result, 42)

        def test_evaljs_lambda_empty_object(self):

            text = """
                x = () => {}
                return x()
            """
            result = self.evaljs(text)
            self.assertEqual(type(result), JsObject)

        def test_evaljs_object_build(self):

            text = """
                return {width: 123}
            """
            result = self.evaljs(text)
            self.assertEqual(type(result), JsObject)
            self.assertEqual(result.width, 123)

        def test_evaljs_object_setattr(self):

            text = """
                x = {width: 123}
                x.width = 42
                return x
            """
            result = self.evaljs(text)
            self.assertEqual(type(result), JsObject)
            self.assertEqual(result.width, 42)

        def test_evaljs_list_build(self):

            text = """
                return [1,2,3]
            """
            result = self.evaljs(text)
            self.assertEqual(type(result), JsArray)
            self.assertEqual(result.length, 3)
            self.assertEqual(result[0], 1)
            self.assertEqual(result[1], 2)
            self.assertEqual(result[2], 3)

        def test_evaljs_list_setindex(self):

            text = """
                x = [1,2,3]
                x[0] = 4
                return x
            """
            result = self.evaljs(text)
            self.assertEqual(type(result), JsArray)
            self.assertEqual(result.length, 3)
            self.assertEqual(result[0], 4)
            self.assertEqual(result[1], 2)
            self.assertEqual(result[2], 3)

        def test_evaljs_list_length(self):

            text = """
                x = [1,2,3]
                return x.length
            """
            result = self.evaljs(text)
            self.assertEqual(result, 3)

        def test_evaljs_branch_true(self):

            text = """
                if (1) {
                    return 2
                } else {
                    return 3
                }
            """
            result = self.evaljs(text)
            self.assertEqual(result, 2)

        def test_evaljs_branch_false(self):

            text = """
                if (0) {
                    return 2
                } else {
                    return 3
                }
            """
            result = self.evaljs(text)
            self.assertEqual(result, 3)

        def test_evaljs_while_loop(self):

            text = """
                i = 0
                while (i < 5) {
                    i += 1
                }
                return i
            """
            result = self.evaljs(text)
            self.assertEqual(result, 5)

        def test_evaljs_dowhile_loop(self):

            text = """
                i = 0
                do {
                    i++
                } while (i < 5)
                return i
            """
            result = self.evaljs(text)
            self.assertEqual(result, 5)

        def test_evaljs_arguments(self):

            text = """
                function f(arg0) {
                    return [arguments.length, arguments[0], arguments[1]]
                }
                return f(10,20)
            """
            result = self.evaljs(text)
            self.assertEqual(type(result), JsArray)
            self.assertEqual(result.length, 3)
            self.assertEqual(result[0], 2)
            self.assertEqual(result[1], 10)
            self.assertEqual(result[2], 20)

        def test_evaljs_arguments_undefined(self):

            text = """
                function f(arg0) {
                    return [arguments.length, arguments[0], arguments[1]]
                }
                return f(10)
            """
            result = self.evaljs(text)
            self.assertEqual(type(result), JsArray)
            self.assertEqual(result.length, 3)
            self.assertEqual(result[0], 1)
            self.assertEqual(result[1], 10)
            self.assertEqual(result[2], JsUndefined._instance)

        def test_evaljs_anonymous_function(self):

            text = """
                fn = function () {
                    return 123
                }
                return fn()
            """
            result = self.evaljs(text)
            self.assertEqual(result, 123)

        def test_evaljs_new_function_constructor(self):

            text = """
                function Shape() {
                    this.width = 5;
                    this.height = 10;
                }
                return new Shape()
            """
            result = self.evaljs(text)
            self.assertEqual(type(result), JsObject)
            # TODO: 'prototype' now shows up in the result
            # self.assertEqual(result.length, 2, str(result))
            self.assertEqual(result.width, 5)
            self.assertEqual(result.height, 10)

        def test_evaljs_new_function_constructor_fn(self):

            text = """
                function Shape() {
                    this.width = 5;
                    this.height = 10;
                    this.area = () => this.width * this.height
                }
                return (new Shape()).area()
            """
            result = self.evaljs(text)
            self.assertEqual(result, 50)

        def test_evaljs_fib_global(self):

            text = """
                function fibonacci(num) {
                    if (num <= 1)
                        return 1;
                    return fibonacci(num - 1) + fibonacci(num - 2);
                }
                return fibonacci(5);
            """
            result = self.evaljs(text)
            self.assertEqual(result, 8)

        def test_evaljs_fib_closure(self):

            text = """
                function main() {
                    function fibonacci(num) {
                        if (num <= 1)
                            return 1;
                        return fibonacci(num - 1) + fibonacci(num - 2);
                    }
                    return fibonacci(5);
                }
                return main();
            """
            result = self.evaljs(text)
            self.assertEqual(result, 8)

        def test_evaljs_closure2(self):
            """
            this test only works if the closure is properly identified
            and the STORE_DEREF is used for both assignments to x
            """

            text = """
                function main() {
                    x = 1

                    function f() { return x }

                    x = 2

                    return f()
                }

                return main();
            """
            result = self.evaljs(text)
            self.assertEqual(result, 2)

        def test_evaljs_closure3(self):
            """
            this only works if the function scope is deferred until
            after the current function scope is fully evaluated
            """

            text = """
                function f() {
                    let a = []
                    {
                        function f1(){return x}
                        let x = 4
                        a.push(f1)
                    }

                    {
                        function f1(){return x}
                        let x = 8
                        a.push(f1)
                    }
                    return a
                }

                a = f()
                return [a.length, a[0](), a[1]()]
            """
            result = self.evaljs(text)
            self.assertEqual(result.length, 3)
            self.assertEqual(result[0], 2)
            self.assertEqual(result[1], 4)
            self.assertEqual(result[2], 8)

        def test_evaljs_closure4(self):
            """
            this only works if the function scope is deferred until
            after the current function scope is fully evaluated
            """

            text = """

                function f1() { return f3() } // f3 not yet defined
                function f2() { return 1234 }
                function f3() { return f2() }

                return f1()
            """
            result = self.evaljs(text)
            self.assertEqual(result, 1234)

        def test_spread_fn_call(self):

            text = """
                x = [2,3,4]
                function fn() {
                    return arguments.length
                }
                return fn(1, ...x, 5)
            """
            result = self.evaljs(text)
            self.assertEqual(result, 5)

        def test_spread_list(self):

            text = """
                x = [2,3,4]
                y = [1, ...x, 5]
                return y.length
            """
            result = self.evaljs(text)
            self.assertEqual(result, 5)

        def test_spread_object(self):

            text = """
                x = {b: 2}
                y = {a:1, b:5, ...x, c:3}
                return y
            """
            result = self.evaljs(text)
            self.assertEqual(result.a, 1)
            self.assertEqual(result.b, 2)
            self.assertEqual(result.c, 3)

        def test_prefix_incr(self):

            text = """
                x = 0;
                return ++x;
            """
            result = self.evaljs(text)
            self.assertEqual(result, 1)

        def test_logical_and_00(self):

            text = """
                return false && false
            """
            result = self.evaljs(text)
            self.assertEqual(result, False)

        def test_logical_and_01(self):

            text = """
                return false && true
            """
            result = self.evaljs(text)
            self.assertEqual(result, False)

        def test_logical_and_10(self):

            text = """
                return true && false
            """
            result = self.evaljs(text)
            self.assertEqual(result, False)

        def test_logical_and_11(self):

            text = """
                return true && true
            """
            result = self.evaljs(text)
            self.assertEqual(result, True)

        def test_logical_or_00(self):

            text = """
                return false || false
            """
            result = self.evaljs(text)
            self.assertEqual(result, False)

        def test_logical_or_01(self):

            text = """
                return false || true
            """
            result = self.evaljs(text)
            self.assertEqual(result, True)

        def test_logical_or_10(self):

            text = """
                return true || false
            """
            result = self.evaljs(text)
            self.assertEqual(result, True)

        def test_logical_or_11(self):

            text = """
                return true || true
            """
            result = self.evaljs(text)
            self.assertEqual(result, True)

        def test_var_let(self):

            text = """
                let x = 1
                return x
            """
            result = self.evaljs(text)
            self.assertEqual(result, 1)

        def test_var_const(self):

            text = """
                const x = 1
                return x
            """
            result = self.evaljs(text)
            self.assertEqual(result, 1)

        def test_var_var(self):

            text = """
                var x = 1
                return x
            """
            result = self.evaljs(text)
            self.assertEqual(result, 1)

        def test_var_multiple(self):

            text = """
                var x = 1, y=2, z=3
                return [x,y,z]
            """
            result = self.evaljs(text)
            self.assertEqual(result.length, 3)
            self.assertEqual(result[0], 1)
            self.assertEqual(result[1], 2)
            self.assertEqual(result[2], 3)

        def test_for_111(self):

            text = """
                result = []
                for (const x=0; x<5; x++) {
                    result.push(x)
                }
                return result
            """
            result = self.evaljs(text)
            self.assertEqual(result.length, 5)

        def test_for_011(self):

            text = """
                result = []
                const x=0
                for (; x<5; x++) {
                    result.push(x)
                }
                return result
            """
            result = self.evaljs(text)
            self.assertEqual(result.length, 5)

        def test_for_010(self):

            text = """
                result = []
                const x=0
                for (;x<5;) {
                    result.push(x++)
                }
                return result
            """
            result = self.evaljs(text)
            self.assertEqual(result.length, 5)

        def test_unpack(self):

            text = """
                let a=5
                let b=10
                [a, b] = [b, a]

                return [a, b]
            """
            result = self.evaljs(text)
            self.assertEqual(result.length, 2)
            self.assertEqual(result[0], 10)
            self.assertEqual(result[1], 5)

        def test_unpack_rest(self):

            text = """
                [a,b,...rest]=[1,2,3,4,5]
                return rest
            """
            result = self.evaljs(text)
            self.assertEqual(result.length, 3)

        def test_break_nested_2(self):
            # This test will segfault or otherwise crash
            # on linux and windows if the stack is not properly maintained
            # loads stores, function calls all need to pop the value
            # when not being used

            text = """
                sum = 0
                for (let i =0; i < 10; i++) {
                    for (let j=0; j < 10; j++) {
                        if (j >= i) {
                            break
                        }
                        sum += i * j
                    }
                    if (sum > 50) {
                        break
                    }
                }
                return sum
            """

            result = self.evaljs(text)
            self.assertEqual(result, 85)

        def test_static_method(self):

            text = """
                class C { static m() { return 123 } }
                return C.m()
            """
            result = self.evaljs(text, False)
            self.assertEqual(result, 123)

        def test_evaljs_class(self):

            text = """
                class Shape {
                    constructor() {
                        this.width = 5
                        this.height = 10
                    }
                    area() {
                        return this.width * this.height;
                    }
                }

                return ((new Shape()).area())
            """
            result = self.evaljs(text)
            self.assertEqual(result, 50)

        def test_evaljs_class_prototype(self):

            # this is taken straight from the documentation
            # https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Classes#Class_body_and_method_definitions

            text = """
                function Animal (name) {
                  this.name = name;
                }

                Animal.prototype.speak = function () {
                  console.log(`${this.name} makes a noise.`);
                }

                class Dog extends Animal {
                  speak() {
                    console.log(`${this.name} barks.`);
                  }
                }

                let d = new Dog('Mitzie');
                d.speak(); // Mitzie barks.
            """
            result = self.evaljs(text)

        @unittest.skip("not implemented")
        def test_evaljs_class_prototype(self):
            """
            this test demonstrates how named functions are hosted

            - functions are defined at the top of the current block
            - default arguments can be modified after defining the function
            - functions are available after a block scope ends
            """
            text = """

                main = function() {
                  // B is undefined
                  console.log("result 1", B) // B is undefined
                  {
                    console.log("result 2", B()) // prints undefined
                    function B(arg=x) {
                      return arg;
                    }
                    var x = 1
                    console.log("result 3", B()) // prints 1
                    var x = 2;
                    console.log("result 4", B()) // prints 2
                  }
                  console.log("result 5", B) // B is defined
                }
                main()
            """
            result = self.evaljs(text)

        @unittest.skip("not implemented")
        def test_evaljs_function_arg_scope(self):
            """
            this test demonstrates how named functions are hosted

            - functions are defined at the top of the current block
            - default arguments can be modified after defining the function
            - functions are available after a block scope ends
            """
            text = """

                var main = function() {
                  let a = []
                  let x = 1
                    function A(arg0=x) {
                    return arg0
                  }
                  a.push(A())
                  x = 2
                  a.push(A())
                  return a
                }
                return main()
            """
            result = self.evaljs(text)
            self.assertEqual(result[0], 1)
            self.assertEqual(result[1], 2)

        def test_scope_delete(self):
            text = """

                var main = function() {
                    let x=0
                    {
                        let x=2
                    }
                    x += 1
                    return x
                }
                return main()
            """
            result = self.evaljs(text, True)
            self.assertEqual(result, 1)

except ImportError as e:
    pass

def main():
    unittest.main()


if __name__ == '__main__':
    main()
