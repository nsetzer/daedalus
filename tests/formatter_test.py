#! cd .. && python3 -m tests.formatter_test


import unittest
from tests.util import edit_distance

from daedalus.lexer import Lexer
from daedalus.parser import Parser
from daedalus.formatter import Formatter, isalphanum

class FormatterUtilTestCase(unittest.TestCase):

    def test_001_expr_1(self):

        self.assertTrue(isalphanum("abc", "123"))
        self.assertTrue(isalphanum("\u263A", "\u263A"))
        self.assertTrue(isalphanum("function", "_name"))

class FormatterTestCase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):

        cls.lexer = Lexer()
        cls.parser = Parser()

    @classmethod
    def tearDownClass(cls):
        pass

    def setUp(self):
        self.formatter = Formatter()

    def tearDown(self):
        super().tearDown()

    def _chkeq(self, text, expected):
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.formatter.format(ast)

        self.assertEqual(output, expected)

    def test_001_comment(self):
        self._chkeq("""
            x = 1 // comment
        """, "x=1")

    def test_001_comment_multiline(self):
        self._chkeq("""
            /*
            comment
            */
            x = 1
        """, "x=1")

    def test_001_comment_documentation(self):

        text = """
        /**
         * comment
         */
        x = 1
        """

        expected = "/**\n         * comment\n         */;x=1"
        tokens = Lexer({'preserve_documentation': True}).lex(text)
        ast = self.parser.parse(tokens)
        output = self.formatter.format(ast)

        self.assertEqual(output, expected)

    def test_001_regex(self):
        self._chkeq("""
            x = /ab+c/g
        """, "x=/ab+c/g")

    def test_001_escape_newline(self):
        self._chkeq("""
           x = a \
               + b
        """, "x=a+b")

    def test_001_generator_function(self):
        self._chkeq("""
           function* g() {
            yield 1
           }
        """, "function*g(){yield 1}")

    def test_001_anonymous_generator_function(self):
        self._chkeq("""
           g = function*() {
            yield 1
           }
        """, "g=function*(){yield 1}")

    def test_001_async_generator_function(self):
        self._chkeq("""
           async function* g() {
            yield 1
           }
        """, "async function*g(){yield 1}")

    def test_001_async_anonymous_generator_function(self):
        self._chkeq("""
           g = async function* () {
            yield 1
           }
        """, "g=async function*(){yield 1}")

    def test_001_async_function(self):
        self._chkeq("""
           async function f() {
            return 1
           }
        """, "async function f(){return 1}")

    def test_001_async_anonymous_function(self):
        self._chkeq("""
           f = async function () {
            return 1
           }
        """, "f=async function(){return 1}")

    def test_001_function(self):
        self._chkeq("""
           function f() {
            return 1
           }
        """, "function f(){return 1}")

    def test_001_anonymous_function(self):
        self._chkeq("""
           f = function () {
            return 1
           }
        """, "f=function(){return 1}")

    def test_001_number_int(self):
        self._chkeq("""
            x = 1234
        """, "x=1234")

    def test_001_number_int_neg(self):
        self._chkeq("""
            x=-1234
        """, "x=-1234")

    def test_001_number_float_1(self):
        self._chkeq("""
            x = 1.2
        """, "x=1.2")

    def test_001_number_float_2(self):
        self._chkeq("""
            x = .234
        """, "x=.234")

    def test_001_number_string_single(self):
        self._chkeq("""
            x = 'abc'
        """, "x='abc'")

    def test_001_number_string_double(self):
        self._chkeq("""
            x = "abc"
        """, "x=\"abc\"")

    def test_001_number_string_format(self):
        self._chkeq("""
            x = `abc ${def}`
        """, "x=`abc ${def}`")

    def test_001_number_string_escape(self):
        self._chkeq("""
            x = '\\x00'
        """, "x='\\x00'")

    def test_001_expr_1(self):

        text = """
            const x = 0
        """
        expected = "const x=0"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.formatter.format(ast)

        self.assertEqual(output, expected)

    def test_001_expr_2(self):

        text = """
            const x = 0
            const y = 1
        """
        expected = "const x=0;const y=1"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.formatter.format(ast)

        self.assertEqual(output, expected)

    def test_001_expr_3(self):

        text = """
            const x = {
                abc: 123,
                def
            }
        """
        expected = "const x={abc:123,def}"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.formatter.format(ast)

        self.assertEqual(output, expected)

    def test_001_expr_4(self):

        text = """
            myfunc("abc", 123, 3.14)
        """
        expected = "myfunc(\"abc\",123,3.14)"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.formatter.format(ast)

        self.assertEqual(output, expected)

    def test_001_branch_1(self):

        text = """
            if (x > 0) {
                x += 1
                console.log(x)
            }
        """
        expected = "if(x>0){x+=1;console.log(x)}"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.formatter.format(ast)

        self.assertEqual(output, expected)

    def test_001_branch_2(self):

        text = """
            if (x > 0) {
                x += 1
                console.log(x)
            } else {
                console.log(-x)
            }
        """
        expected = "if(x>0){x+=1;console.log(x)}else{console.log(-x)}"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.formatter.format(ast)

        self.assertEqual(output, expected)

    def test_001_branch_3(self):

        text = """
            if (x > 0) {
                x += 1
                console.log(x)
            } else
            if (false) {
                console.log(-x)
            }
        """
        expected = "if(x>0){x+=1;console.log(x)}else if(false){console.log(-x)}"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.formatter.format(ast)

        self.assertEqual(output, expected)

    def test_001_prefix_1(self):

        text = """
            ++ x
        """
        expected = "++x"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.formatter.format(ast)

        self.assertEqual(output, expected)

    def test_001_prefix_2(self):

        text = """
            typeof(NaN)
        """
        expected = "typeof(NaN)"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.formatter.format(ast)

        self.assertEqual(output, expected)

    def test_001_postfix_1(self):

        text = """
            x ++
        """
        expected = "x++"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.formatter.format(ast)

        self.assertEqual(output, expected)

    def test_001_binary_1(self):

        text = """
            a < b
        """
        expected = "a<b"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.formatter.format(ast)

        self.assertEqual(output, expected)

    def test_001_binary_2(self):

        text = """
            a in b
        """
        expected = "a in b"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.formatter.format(ast)

        self.assertEqual(output, expected)

    def test_001_ternary_1(self):

        text = """
            a ? b : c
        """
        expected = "a?b:c"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.formatter.format(ast)

        self.assertEqual(output, expected)

    def test_001_function_1(self):

        text = """
            function name() {}
        """
        expected = "function name(){}"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.formatter.format(ast)

        self.assertEqual(output, expected)

    def test_001_function_2(self):

        text = """
            x = function () {}
        """
        expected = "x=function(){}"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.formatter.format(ast)

        self.assertEqual(output, expected)

    def test_001_subscr_1(self):

        text = """
            map[key]
        """
        expected = "map[key]"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.formatter.format(ast)

        self.assertEqual(output, expected)

    def test_001_for_111(self):
        self._chkeq("for (let x=1; x < 10; x++) {}",
                    "for(let x=1;x<10;x++){}")

    def test_001_for_110(self):
        self._chkeq("for (let x=1; x < 10;) {}",
                    "for(let x=1;x<10;){}")

    def test_001_for_101(self):
        self._chkeq("for (let x=1;; x++) {}",
                    "for(let x=1;;x++){}")

    def test_001_for_100(self):
        self._chkeq("for (let x=1;;) {}",
                    "for(let x=1;;){}")

    def test_001_for_011(self):
        self._chkeq("for (; x < 10; x++) {}",
                    "for(;x<10;x++){}")

    def test_001_for_010(self):
        self._chkeq("for (; x < 10;) {}",
                    "for(;x<10;){}")

    def test_001_for_001(self):
        self._chkeq("for (;; x++) {}",
                    "for(;;x++){}")

    def test_001_for_000(self):
        self._chkeq("for (;;) {}",
                    "for(;;){}")

    def test_001_for_in_1(self):

        text = """
            for (property in object) {}
        """
        expected = "for(property in object){}"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.formatter.format(ast)

        self.assertEqual(output, expected)

    def test_001_for_in_2(self):

        text = """
            for (const property in object) {}
        """
        expected = "for(const property in object){}"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.formatter.format(ast)

        self.assertEqual(output, expected)

    def test_001_for_of_1(self):

        text = """
            for (item of iterable) {}
        """
        expected = "for(item of iterable){}"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.formatter.format(ast)

        self.assertEqual(output, expected)

    def test_001_for_of_2(self):

        text = """
            for (const item of iterable) {}
        """
        expected = "for(const item of iterable){}"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.formatter.format(ast)

        self.assertEqual(output, expected)

    def test_001_while_1(self):

        text = """
            while (true) {}
        """
        expected = "while(true){}"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.formatter.format(ast)

        self.assertEqual(output, expected)

    def test_001_dowhile_1(self):

        text = """
            do {console.log('')} while (false)
        """
        expected = "do{console.log('')}while(false)"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.formatter.format(ast)

        self.assertEqual(output, expected)

    def test_001_switch_1(self):

        text = """
            switch (item) {
                case 0:
                    break;
                case 1:
                    break;
                default:
                    break;
            }
        """
        expected = "switch(item){case 0:break;case 1:break;default:break}"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.formatter.format(ast)

        self.assertEqual(output, expected)

    def test_001_switch_2(self):

        text = """
            switch(item){case 0:console.log(0);break;case 1:console.log(0);break;default:break}
        """
        expected = "switch(item){case 0:console.log(0);break;case 1:console.log(0);break;default:break}"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.formatter.format(ast)

        self.assertEqual(output, expected)

    def test_001_class_1(self):

        text = """
            class A {
                onClick(event) {
                    return null;
                }
            }
        """
        expected = "class A{onClick(event){return null}}"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.formatter.format(ast)

        self.assertEqual(output, expected)

    def test_001_class_2(self):

        text = """
            class A extends B {
                constructor() {
                    super();
                }
            }
        """
        expected = "class A extends B{constructor(){super()}}"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.formatter.format(ast)

        self.assertEqual(output, expected)

    def test_001_class_2(self):

        text = """
            class A extends X.Y {
                constructor() {
                    super();
                }
            }
        """
        expected = "class A extends X.Y{constructor(){super()}}"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.formatter.format(ast)

        self.assertEqual(output, expected)

    def test_001_comma_1(self):

        text = """
            const x = 0,
                f = () => {}
        """
        expected = "const x=0,f=()=>{}"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.formatter.format(ast)

        self.assertEqual(output, expected)

    def test_001_trycatch_1(self):

        text = """
            try {
                throw 0;
            } catch (ex) {
                console.log(ex)
            } finally {
                console.log("done")
            }
        """
        expected = "try{throw 0}catch(ex){console.log(ex)}finally{console.log(\"done\")}"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.formatter.format(ast)

        self.assertEqual(output, expected)

    def test_001_new_1(self):

        text = """
            const x = new X
        """
        expected = "const x=new X"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.formatter.format(ast)

        self.assertEqual(output, expected)

    def test_001_new_2(self):

        text = """
            const x = new X()
        """
        expected = "const x=new X()"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.formatter.format(ast)

        self.assertEqual(output, expected)

    def test_001_optional_chaining_attr(self):
        #self._chkeq("a ?. b", "a?.b")
        self._chkeq("a ?. b", "((a)||{}).b")

    #def test_001_optional_chaining_call(self):
    #    self._chkeq("a?.()", "a?.()")

    #def test_001_optional_chaining_subscr(self):
    #    self._chkeq("a?.[]", "a?.[]")

    def test_001_spread_call(self):
        self._chkeq("f(...x, 1, 2, 3, ...y)", "f(...x,1,2,3,...y)")

    def test_001_spread_list(self):
        self._chkeq("y = [...x]", "y=[...x]")

    def test_001_spread_obj(self):
        self._chkeq("y = {...x}", "y={...x}")

    def test_001_yield(self):
        self._chkeq("yield value", 'yield value')

    def test_001_generator(self):
        self._chkeq("function* g() {yield 1}", 'function*g(){yield 1}')

    def test_001_anonymous_generator(self):
        self._chkeq("function* () {yield 1}", 'function*(){yield 1}')

    def test_001_list_newline(self):
        self._chkeq("""
            a = 0
            [b] = [a]
        """, 'a=0;[b]=[a]')

    def test_001_instanceof(self):
        self._chkeq("if (x instanceof y){}", 'if(x instanceof y){}')

    def test_001_logical_and(self):
        self._chkeq("if (x && y){}", 'if(x&&y){}')

    def test_001_logical_or(self):
        self._chkeq("if (x || y){}", 'if(x||y){}')

    def test_001_generator(self):
        self._chkeq("""
            function* g1() {
                yield 1
                yield* g2()
                yield 2
            }
        """, 'function*g1(){yield 1;yield*g2();yield 2}')

    def test_001_anonymous_generator(self):
        self._chkeq("""
            function*() {
                yield 1
            }
        """, 'function*(){yield 1}')

    def test_001_async_generator(self):
        self._chkeq("""
            async function* g1() {
                await f2()
            }
        """, 'async function*g1(){await f2()}')

    def test_001_async_anonymous_generator(self):
        self._chkeq("""
            async function* () {
                yield 1
            }
        """, 'async function*(){yield 1}')

    def test_001_static_method(self):
        self._chkeq("""
            class C {static f() {} f2(){}}
        """, 'class C{static f(){};f2(){}}')

class FormatterStressTestCase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):

        cls.lexer = Lexer()
        cls.parser = Parser()

    @classmethod
    def tearDownClass(cls):
        pass

    def setUp(self):
        self.formatter = Formatter()

    def tearDown(self):
        super().tearDown()

    def test_001_wide_1(self):
        # the lexer / parser /.formatter should
        # support a line that is longer than 4096 characters

        text = "const %s=1" % ("x" * 8192)
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.formatter.format(ast).replace("\n", "")

        self.assertEqual(output, text)

    def test_001_wide_2(self):
        # the lexer / parser /.formatter should
        # support a line that is longer than 4096 characters
        N = 819
        text = "abc01" + ("+abc01" * N)
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.formatter.format(ast).replace("\n", "")

        self.assertEqual(output, text)

    def test_002_deep_1(self):
        # the lexer / parser /.formatter should
        # support an expression with a nesting depth
        # deeper than 1000 tokens

        # using a recursive.formatter strategy
        # at N == 973 maximum recursion depth is reached

        # using a non-recursive strategy in the.formatter
        # pushes the problem onto the parser
        # at N == 974 maximum recursion depth is reached

        # switching to non-recursive parsing strategy opens
        # up greater tree depth

        N = 2000
        text = "2" + ("+2" * N)
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.formatter.format(ast).replace("\n", "")

        self.assertEqual(output, text)

    def test_002_deep_2(self):

        # mutual recursion in the parser limits the depth
        # now there is no limit at least to N=2000
        # there is however significant slowdown for large N

        N = 500
        text = ("(" * N) + (")" * N)
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.formatter.format(ast).replace("\n", "")

        self.assertEqual(output, text)

def main():
    unittest.main()


if __name__ == '__main__':
    main()
