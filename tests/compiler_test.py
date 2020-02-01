

import unittest
from tests.util import edit_distance
import time, math

from daedalus.lexer import Lexer
from daedalus.parser import Parser
from daedalus.compiler import Compiler, SourceMap, isalphanum

class SourceMapTestCase(unittest.TestCase):

    def test_001_b64decode(self):
        srcmap = SourceMap()

        self.assertEqual(srcmap.b64decode('uDt7D0TkuK'), [55, -1974, 314, 5346])
        self.assertEqual(srcmap.b64decode('gvDn1EilwhEQ4xDpo3vP'), [1776, -2387, 2121809, 8, 1820, -8121988])

    def test_001_b64encode(self):
        srcmap = SourceMap()

        self.assertEqual(srcmap.b64encode([55, -1974, 314, 5346]), 'uDt7D0TkuK')
        self.assertEqual(srcmap.b64encode([1776, -2387, 2121809, 8, 1820, -8121988]), 'gvDn1EilwhEQ4xDpo3vP')

class CompilerUtilTestCase(unittest.TestCase):

    def test_001_expr_1(self):

        self.assertTrue(isalphanum("abc", "123"))
        self.assertTrue(isalphanum("\u263A", "\u263A"))
        self.assertTrue(isalphanum("function", "_name"))

class CompilerTestCase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):

        cls.lexer = Lexer()
        cls.parser = Parser()

    @classmethod
    def tearDownClass(cls):
        pass

    def setUp(self):
        self.compiler = Compiler()

    def tearDown(self):
        super().tearDown()

    def test_001_expr_1(self):

        text = """
            const x = 0
        """
        expected = "const x=0"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.compiler.compile(ast)

        self.assertEqual(output, expected)

    def test_001_expr_2(self):

        text = """
            const x = 0
            const y = 1
        """
        expected = "const x=0;const y=1"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.compiler.compile(ast)

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
        output = self.compiler.compile(ast)

        self.assertEqual(output, expected)

    def test_001_expr_4(self):

        text = """
            myfunc("abc", 123, 3.14)
        """
        expected = "myfunc(\"abc\",123,3.14)"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.compiler.compile(ast)

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
        output = self.compiler.compile(ast)

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
        output = self.compiler.compile(ast)

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
        output = self.compiler.compile(ast)

        self.assertEqual(output, expected)

    def test_001_prefix_1(self):

        text = """
            ++ x
        """
        expected = "++x"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.compiler.compile(ast)

        self.assertEqual(output, expected)

    def test_001_prefix_2(self):

        text = """
            typeof(NaN)
        """
        expected = "typeof(NaN)"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.compiler.compile(ast)

        self.assertEqual(output, expected)

    def test_001_postfix_1(self):

        text = """
            x ++
        """
        expected = "x++"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.compiler.compile(ast)

        self.assertEqual(output, expected)

    def test_001_binary_1(self):

        text = """
            a < b
        """
        expected = "a<b"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.compiler.compile(ast)

        self.assertEqual(output, expected)

    def test_001_binary_2(self):

        text = """
            a in b
        """
        expected = "a in b"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.compiler.compile(ast)

        self.assertEqual(output, expected)

    def test_001_ternary_1(self):

        text = """
            a ? b : c
        """
        expected = "a?b:c"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.compiler.compile(ast)

        self.assertEqual(output, expected)

    def test_001_function_1(self):

        text = """
            function name() {}
        """
        expected = "function name(){}"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.compiler.compile(ast)

        self.assertEqual(output, expected)

    def test_001_function_2(self):

        text = """
            x = function () {}
        """
        expected = "x=function(){}"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.compiler.compile(ast)

        self.assertEqual(output, expected)

    def test_001_subscr_1(self):

        text = """
            map[key]
        """
        expected = "map[key]"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.compiler.compile(ast)

        self.assertEqual(output, expected)

    def test_001_for_1(self):

        text = """
            for (let x=1; x < 10; x++) {}
        """
        expected = "for(let x=1;x<10;x++){}"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.compiler.compile(ast)

        self.assertEqual(output, expected)

    def test_001_for_2(self):

        text = """
            for (const property in object) {}
        """
        expected = "for(const property in object){}"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.compiler.compile(ast)

        self.assertEqual(output, expected)

    def test_001_for_3(self):

        text = """
            for (const item of iterable) {}
        """
        expected = "for(const item of iterable){}"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.compiler.compile(ast)

        self.assertEqual(output, expected)

    def test_001_while_1(self):

        text = """
            while (true) {}
        """
        expected = "while(true){}"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.compiler.compile(ast)

        self.assertEqual(output, expected)

    def test_001_dowhile_1(self):

        text = """
            do {console.log('')} while (false)
        """
        expected = "do{console.log('')}while(false)"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.compiler.compile(ast)

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
        output = self.compiler.compile(ast)

        self.assertEqual(output, expected)

    def test_001_switch_2(self):

        text = """
            switch(item){case 0:console.log(0);break;case 1:console.log(0);break;default:break}
        """
        expected = "switch(item){case 0:console.log(0);break;case 1:console.log(0);break;default:break}"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.compiler.compile(ast)

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
        output = self.compiler.compile(ast)

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
        output = self.compiler.compile(ast)

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
        output = self.compiler.compile(ast)

        self.assertEqual(output, expected)

    def test_001_comma_1(self):

        text = """
            const x = 0,
                f = () => {}
        """
        expected = "const x=0,f=()=>{}"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.compiler.compile(ast)

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
        output = self.compiler.compile(ast)

        self.assertEqual(output, expected)

    def test_001_new_1(self):

        text = """
            const x = new X
        """
        expected = "const x=new X"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.compiler.compile(ast)

        self.assertEqual(output, expected)

    def test_001_new_2(self):

        text = """
            const x = new X()
        """
        expected = "const x=new X()"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.compiler.compile(ast)

        self.assertEqual(output, expected)

class CompilerStressTestCase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):

        cls.lexer = Lexer()
        cls.parser = Parser()

    @classmethod
    def tearDownClass(cls):
        pass

    def setUp(self):
        self.compiler = Compiler()

    def tearDown(self):
        super().tearDown()

    def test_001_wide_1(self):
        # the lexer / parser / compiler should
        # support a line that is longer than 4096 characters

        text = "const %s=1" % ("x" * 8192)
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.compiler.compile(ast)

        self.assertEqual(output, text)

    def test_001_wide_2(self):
        # the lexer / parser / compiler should
        # support a line that is longer than 4096 characters
        N = 819
        text = "abc01" + ("+abc01"*N)
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.compiler.compile(ast)

        self.assertEqual(output, text)

    def test_002_deep(self):
        # the lexer / parser / compiler should
        # support an expression with a nesting depth
        # deeper than 1000 tokens

        # using a recursive compiler strategy
        # at N == 973 maximum recursion depth is reached

        # using a non-recursive strategy in the compiler
        # pushes the problem onto the parser
        # at N == 974 maximum recursion depth is reached

        # switching to non-recursive parsing strategy opens
        # up greater tree depth

        N = 2000
        text = "2" + ("+2"*N)
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.compiler.compile(ast)

        self.assertEqual(output, text)

    @unittest.skip("skip bench")
    def test_002_deep_bench(self):


        X = [250, 1000]
        Y = []

        td1 = time.perf_counter()
        for N in X:
            t1 = time.perf_counter()
            text = ("(" * N) + (")" * N)
            tokens = self.lexer.lex(text)
            ast = self.parser.parse(tokens)
            output = self.compiler.compile(ast).replace("\n", "")
            self.assertEqual(output, text)
            t2 = time.perf_counter()
            Y.append(t2 - t1)
        td2 = time.perf_counter()

        m = (Y[1] - Y[0]) / (X[1] - X[0])
        b = Y[0] - m * X[0]

        eq1 = lambda n: m*n + b
        eq2 = lambda n: m*n*n + b
        eq3 = lambda n: m*n*math.log(n) + b

        names = [
            "n",
            "n*n",
            "nlogn",
        ]

        error = [
            abs(Y[0] - eq1(X[0])),
            abs(Y[0] - eq2(X[0])),
            abs(Y[0] - eq3(X[0]))
        ]

        def imin(seq):
            j = 0
            v1 = seq[0]
            for i, v in enumerate(seq):
                if v < v1:
                    v1 = v
                    j = i
            return j

        # total duration needs to be above some minimum to be valid
        td = td2 - td1
        index = imin(error)
        print(error)
        print(error[index])
        print(td)
        print(" eq = %.6f * %s %s %.6f" % (
            m, names[index], "-" if b < 0 else "+" ,abs(b)))

def main():
    unittest.main()

if __name__ == '__main__':
    main()
