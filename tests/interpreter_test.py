import unittest
from tests.util import edit_distance

from daedalus.lexer import Lexer
from daedalus.parser import Parser
from daedalus.interpreter import Interpreter, \
    JsObject, JsArray, JsUndefined

class InterpreterTestCase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):

        cls.lexer = Lexer()
        cls.parser = Parser()

    @classmethod
    def tearDownClass(cls):
        pass

    def setUp(self):
        super().setUp()

    def tearDown(self):
        super().tearDown()

    def evaljs(self, text):
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)

        interpreter = Interpreter()
        interpreter.compile(ast)
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
        self.assertEqual(result.length, 2)
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

def main():
    unittest.main()

if __name__ == '__main__':
    main()
