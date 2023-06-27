#! cd .. && python3 -m tests.formatter_test

# TODO: http://es6-features.org/#MethodProperties

import unittest
from tests.util import edit_distance

from daedalus.lexer import Lexer
from daedalus.parser import Parser, ParseError
from daedalus.formatter import Formatter, isalphanum
from daedalus.transform import TransformMinifyScope, TransformIdentityScope

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
        cls.parser.disable_all_warnings = True

    @classmethod
    def tearDownClass(cls):
        pass

    def setUp(self):
        self.formatter = Formatter()

    def tearDown(self):
        super().tearDown()

    def _chkeq(self, text, expected, lexer_attrs=None, parser_attrs=None, minify=True):
        lexer = Lexer()
        tokens = lexer.lex(text)
        parser = Parser()
        if parser_attrs:
            for k, v in parser_attrs.items():
                setattr(parser, k, v)
        ast = parser.parse(tokens)

        output = Formatter({"minify": minify}).format(ast)

        self.assertEqual(expected, output)

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

        self.assertEqual(expected, output)

    def test_001_number_separated(self):
        self._chkeq("""1_234.000_000""", "1234.000000")

    def test_001_regex(self):
        self._chkeq("""
            x = /ab+c/g
        """, "x=/ab+c/g")

    def test_001_grouping_hard(self):
        self._chkeq("{[0](){}}",
            "{[0](){}}")

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

    def test_001_named_function_def(self):
        self._chkeq("""
            void function iife() {
                console.log("test")
            }();
        """, "void function iife(){console.log(\"test\")}()")

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

    def test_001_number_string_raw(self):
        self._chkeq(""" String.raw`foo\\n` === "foo\\\\n" """,
            'String.raw`foo\\n`==="foo\\\\n"')

    def test_001_number_string_custom_format(self):
        self._chkeq("""
            let f=function() {return arguments}, a = {'b':{'c':f}}, x=0;
            let b = a.b.c`x${x}y`;
            // b[0] = [ "x", "y" ]
            // b[1] = 0
        """,
        """let f=function(){return arguments},a={'b':{'c':f}},x=0;let b=a.b.c`x${x}y`""")

    def test_001_object_compute_key(self):
        text = "{[1 + 2]: 0}"
        expected = '{[1+2]:0}'
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.formatter.format(ast)
        self.assertEqual(expected, output)

    def test_001_multiline_string(self):
        text = """const x = `a\n   b\n   c\n`"""
        expected = 'const x=`a\n   b\n   c\n`'
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.formatter.format(ast)
        self.assertEqual(expected, output)

    def test_001_expr_1(self):

        text = """
            const x = 0
        """
        expected = "const x=0"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.formatter.format(ast)

        self.assertEqual(expected, output)

    def test_001_expr_2(self):

        text = """
            const x = 0
            const y = 1
        """
        expected = "const x=0;const y=1"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.formatter.format(ast)

        self.assertEqual(expected, output)

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

        self.assertEqual(expected, output)

    def test_001_expr_4(self):

        text = """
            myfunc("abc", 123, 3.14)
        """
        expected = "myfunc(\"abc\",123,3.14)"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.formatter.format(ast)

        self.assertEqual(expected, output)

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

        self.assertEqual(expected, output)

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

        self.assertEqual(expected, output)

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

        self.assertEqual(expected, output)

    def test_001_prefix_1(self):

        text = """
            ++ x
        """
        expected = "++x"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.formatter.format(ast)

        self.assertEqual(expected, output)

    def test_001_prefix_2(self):

        text = """
            typeof(NaN)
        """
        expected = "typeof(NaN)"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.formatter.format(ast)

        self.assertEqual(expected, output)

    def test_001_postfix_1(self):

        text = """
            x ++
        """
        expected = "x++"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.formatter.format(ast)

        self.assertEqual(expected, output)

    def test_001_binary_1(self):

        text = """
            a < b
        """
        expected = "a<b"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.formatter.format(ast)

        self.assertEqual(expected, output)

    def test_001_binary_2(self):

        text = """
            a in b
        """
        expected = "a in b"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.formatter.format(ast)

        self.assertEqual(expected, output)

    def test_001_binary_unsigned_rightshit(self):

        text = """
            a >>> b
        """
        expected = "a>>>b"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.formatter.format(ast)

        self.assertEqual(expected, output)

    def test_001_binary_nullish_coalescing(self):

        text = """
            c = a ?? b
        """
        expected = "c=a??b"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.formatter.format(ast)

        self.assertEqual(expected, output)

    def test_001_binary_null_assign(self):

        text = """
            a ??= b
        """
        expected = "a??=b"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.formatter.format(ast)

        self.assertEqual(expected, output)

    def test_001_get_attr(self):

        text = """
            x.y
        """
        expected = "x.y"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.formatter.format(ast)

        self.assertEqual(expected, output)

    def test_001_return_undefined(self):

        text = """
            return undefined;
        """
        expected = "return undefined"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.formatter.format(ast)

        self.assertEqual(expected, output)

    def test_001_ternary_1(self):

        text = """
            a ? b : c
        """
        expected = "a?b:c"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.formatter.format(ast)

        self.assertEqual(expected, output)

    def test_001_function_1(self):

        text = """
            function name() {}
        """
        expected = "function name(){}"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.formatter.format(ast)

        self.assertEqual(expected, output)

    def test_001_function_2(self):

        text = """
            x = function () {}
        """
        expected = "x=function(){}"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.formatter.format(ast)

        self.assertEqual(expected, output)

    def test_001_subscr_1(self):

        text = """
            map[key]
        """
        expected = "map[key]"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.formatter.format(ast)

        self.assertEqual(expected, output)

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

        self.assertEqual(expected, output)

    def test_001_for_in_2(self):

        text = """
            for (const property in object) {}
        """
        expected = "for(const property in object){}"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.formatter.format(ast)

        self.assertEqual(expected, output)

    def test_001_for_of_1(self):

        text = """
            for (item of iterable) {}
        """
        expected = "for(item of iterable){}"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.formatter.format(ast)

        self.assertEqual(expected, output)

    def test_001_for_of_2(self):

        text = """
            for (const item of iterable) {}
        """
        expected = "for(const item of iterable){}"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.formatter.format(ast)

        self.assertEqual(expected, output)

    def test_001_for_await(self):

        text = """
            for await (const ret of delays) {
              print("for loop await "+ret)
            }
        """
        expected = "for await(const ret of delays){print(\"for loop await \"+ret)}"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.formatter.format(ast)

        self.assertEqual(expected, output)

    def test_001_while_1(self):

        text = """
            while (true) {}
        """
        expected = "while(true){}"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.formatter.format(ast)

        self.assertEqual(expected, output)

    def test_001_dowhile_1(self):

        text = """
            do {console.log('')} while (false)
        """
        expected = "do{console.log('')}while(false)"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.formatter.format(ast)

        self.assertEqual(expected, output)

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
        expected = "switch(item){case 0:break;case 1:break;default:break;}"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.formatter.format(ast)

        self.assertEqual(expected, output)

    def test_001_switch_2(self):

        text = """
            switch(item){case 0:console.log(0);break;case 1:console.log(0);break;default:break}
        """
        expected = "switch(item){case 0:console.log(0);break;case 1:console.log(0);break;default:break;}"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.formatter.format(ast)

        self.assertEqual(expected, output)

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

        self.assertEqual(expected, output)

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

        self.assertEqual(expected, output)

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

        self.assertEqual(expected, output)

    def test_001_class_privates_a(self):

        text = """
        class A{#PRIVATE_FIELD#PRIVATE_FIELD_DEFAULT=0#privateMethod(){return 0}}
        """
        expected = "class A{#PRIVATE_FIELD#PRIVATE_FIELD_DEFAULT=0#privateMethod(){return 0}}"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.formatter.format(ast)

        self.assertEqual(expected, output)

    def test_001_class_privates_b(self):

        text = """
        class A {
          #PRIVATE_FIELD;
          #PRIVATE_FIELD_DEFAULT=0;
          #privateMethod() {
            return 0;
          }
        }
        """
        expected = "class A{#PRIVATE_FIELD#PRIVATE_FIELD_DEFAULT=0#privateMethod(){return 0}}"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.formatter.format(ast)

        self.assertEqual(expected, output)

    def test_001_class_static_privates_a(self):

        text = """
        class A{static #PRIVATE_STATIC_FIELD; static #PRIVATE_STATIC_FIELD_DEFAULT=0; static #privateStaticMethod(){return 0}}
        """
        expected = "class A{static #PRIVATE_STATIC_FIELD static #PRIVATE_STATIC_FIELD_DEFAULT=0 static#privateStaticMethod(){return 0}}"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.formatter.format(ast)

        self.assertEqual(expected, output)

    def test_001_class_static_privates_b(self):

        text = """
        class A {
          static #PRIVATE_STATIC_FIELD;
          static #PRIVATE_STATIC_FIELD_DEFAULT = 0;
          static #privateStaticMethod() {
            return 0;
          }
        }
        """
        expected = "class A{static #PRIVATE_STATIC_FIELD static #PRIVATE_STATIC_FIELD_DEFAULT=0 static#privateStaticMethod(){return 0}}"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.formatter.format(ast)

        self.assertEqual(expected, output)

    def test_001_comma_1(self):

        text = """
            const x = 0,
                f = () => {}
        """
        expected = "const x=0,f=()=>{}"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.formatter.format(ast)

        self.assertEqual(expected, output)

    def test_001_comma_2(self):
        self._chkeq("let a=1, b=2, c=3", "let a=1,b=2,c=3")

    def test_001_comma_3(self):
        self._chkeq("let a=f(), b=a.b, c=a.c", "let a=f(),b=a.b,c=a.c")

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

        self.assertEqual(expected, output)

    def test_001_trycatch_2(self):

        text = """

            function f() {
                try {
                    throw 0;
                } catch (ex) {
                    void 0;
                } finally {
                    void 1;
                }
            }
        """
        expected = "function f(){try{throw 0}catch(ex){void 0}finally{void 1}}"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.formatter.format(ast)

        self.assertEqual(expected, output)

    def test_001_new_1(self):

        text = """
            const x = new X
        """
        expected = "const x=new X"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.formatter.format(ast)

        self.assertEqual(expected, output)

    def test_001_new_2(self):

        text = """
            const x = new X()
        """
        expected = "const x=new X()"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.formatter.format(ast)

        self.assertEqual(expected, output)

    def test_001_optional_chaining_attr_a(self):
        self._chkeq("a ?. b", "((a)||{}).b")

    def test_001_optional_chaining_attr_b(self):
        self._chkeq("a ?. b", "a?.b",
            parser_attrs={'feat_xform_optional_chaining':0})

    def test_001_optional_chaining_call_a(self):
        self._chkeq("a?.()", "((a)||(()=>null))()")

    def test_001_optional_chaining_call_b(self):
        self._chkeq("a?.()", "a?.()",
            parser_attrs={'feat_xform_optional_chaining':0})

    def test_001_optional_chaining_subscr_a(self):
        self._chkeq("a?.[0]", "((a)||{})[0]")

    def test_001_optional_chaining_subscr_b(self):
        self._chkeq("a?.[0]", "a?.[0]",
            parser_attrs={'feat_xform_optional_chaining':0})

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
        """, 'class C{static f(){}f2(){}}')

    def test_001_static_props(self):
        self._chkeq("""
            class C {static p = 123}
        """, 'class C{static p=123}')

    def test_001_unpack_sequence(self):

        self._chkeq("""
            [a, b, ...rest] = [1,2,3,4,5]
        """, '[a,b,...rest]=[1,2,3,4,5]')

    def test_001_destructure_object(self):
        self._chkeq("""
            var a,b,c,d;
            var o = {a: 1, b:2, c:3, d:4};
            {a: a, b:b, c:c, d:d} = o
        """, 'var a,b,c,d;var o={a:1,b:2,c:3,d:4};{a:a,b:b,c:c,d:d}=o')

    def test_001_template_string(self):
        # should not insert white space
        self._chkeq("`${a}_${b}_${c}`", '`${a}_${b}_${c}`')
        self._chkeq("`${a}_${b}_${c}`", '`${a}_${b}_${c}`', minify=True)

    def test_001_tagged_template(self):
        self._chkeq("""
            myTag`width: ${width}px`
        """, 'myTag`width: ${width}px`')

    def test_001_tagged_template_attr(self):
        self._chkeq("""
            x.y`width: ${width}px`
        """, 'x.y`width: ${width}px`')

    def test_001_for_var_comma(self):
        self._chkeq("""
            for (let x=1,y=2,z=3; x<y,y<z; --x,z++) {}
        """, 'for(let x=1,y=2,z=3;x<y,y<z;--x,z++){}')

    def test_001_import_js_module(self):

        text = """
            import {a as b, c} from './module/module.js'
        """
        expected = "import {a as b, c} from './module/module.js'"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.formatter.format(ast)

        self.assertEqual(expected, output)

    def test_001_import_js_module(self):

        text = """
            import * as module from './module/module.js'
        """
        expected = "import * as module from './module/module.js'"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.formatter.format(ast)

        self.assertEqual(expected, output)

    def test_001_export(self):

        text = """
            export a = 1
        """
        expected = "export a=1"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.formatter.format(ast)

        self.assertEqual(expected, output)

    def test_001_export_default(self):

        text = """
            export default a = 1
        """
        expected = "export default a=1"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.formatter.format(ast)

        self.assertEqual(expected, output)

    @unittest.expectedFailure
    def test_001_export_from(self):

        text = """
            export a from b
        """
        expected = "export a from b"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.formatter.format(ast)

        self.assertEqual(expected, output)

    def test_001_computed_property(self):

        text = """
            {[1 + 2]: 3}
        """
        expected = "{[1+2]:3}"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.formatter.format(ast)

        self.assertEqual(expected, output)

    def test_001_method_property(self):
        text = """
            {
                add(a, b) {return a+b},
            }
        """
        expected = "{add(a,b){return a+b}}"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.formatter.format(ast)

        self.assertEqual(expected, output)

    def test_001_method_property_minify(self):
        text = """
            x = {
                add(a, b) {return a+b},
            }
            x.add(1,2)
        """
        expected = "a={add(c,b){return c+b}};a.add(1,2)"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        xform = TransformMinifyScope()
        xform.disable_warnings=True
        xform.transform(ast)
        output = self.formatter.format(ast)

        self.assertEqual(expected, output)

    def test_001_unicode_regex(self):
        text = """
            x = /./u
            "古い".match(x)
            "\u53e4"==="\\u{53e4}"
        """
        expected = "x=/./u;\"古い\".match(x);\"\u53e4\"===\"\\u{53e4}\""
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.formatter.format(ast)

        self.assertEqual(expected, output)

    def test_001_literals(self):
        text = """
            0b1010 === 0xA === 0o12
        """
        expected = "0b1010===0xA===0o12"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.formatter.format(ast)

        self.assertEqual(expected, output)

    def test_001_function_defaults(self):
        text = """
            function f(x=1, y=2) {return x + y}
        """
        expected = "function a(c=1,b=2){return c+b}"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        xform = TransformMinifyScope()
        xform.disable_warnings=True
        xform.transform(ast)
        output = self.formatter.format(ast)

        self.assertEqual(expected, output)

    def test_001_function_rest(self):
        text = """
            function f(x, y, ...z) {return [x,y,z]}
        """
        expected = "function a(d,c,...b){return[d,c,b]}"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        xform = TransformMinifyScope()
        xform.disable_warnings=True
        xform.transform(ast)
        output = self.formatter.format(ast)

        self.assertEqual(expected, output)

    def test_001_destructure_assignment(self):
        text = """
            foo=1
            bar=2
            [foo,bar] = [bar,foo]
        """
        expected = "a=1;b=2;[a,b]=[b,a]"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        xform = TransformMinifyScope()
        xform.disable_warnings=True
        xform.transform(ast)
        output = self.formatter.format(ast)

        self.assertEqual(expected, output)

    def test_001_destructure_object(self):
        text = """
            var {lhs, rhs} = getToken()
        """
        expected = "var{lhs,rhs}=getToken()"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        #TransformMinifyScope().transform(ast)
        output = self.formatter.format(ast)

        self.assertEqual(expected, output)

    def test_001_destructure_object(self):
        text = """
            var {lhs:x, rhs:y} = getToken()
        """
        #TODO: single quotes are not required
        expected = "var{'lhs':a,'rhs':b}=getToken()"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        xform = TransformMinifyScope()
        xform.disable_warnings=True
        xform.transform(ast)
        output = self.formatter.format(ast)

        self.assertEqual(expected, output)

    def test_001_destructure_object_deep(self):
        text = """
            var {lhs:{ op: x }, rhs:y} = getToken()
        """
        # equivalent to var a = tmp.lhs.op
        #TODO: single quotes are not required
        expected = "var{lhs:{op:x},rhs:y}=getToken()"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        #xform = TransformMinifyScope()
        #xform.disable_warnings=True
        #xform.transform(ast)
        output = self.formatter.format(ast)

        self.assertEqual(expected, output)

    def test_001_destructure_object_default(self):
        text = """
            var {x, y=1} = getToken()
        """
        expected = "var{x,y=1}=getToken()"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.formatter.format(ast)

        self.assertEqual(expected, output)

    def test_001_destructure_object_default_minify(self):
        text = """
            var {x, y=1} = getToken()
        """
        # TODO: this may accidentally do the right thing
        expected = "var a=getToken(),{x:b}=a,c=a?.y??1"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        xform = TransformMinifyScope()
        xform.disable_warnings=True
        xform.transform(ast)
        output = self.formatter.format(ast)

        self.assertEqual(expected, output)

    def test_001_destructure_object_deep_minify(self):
        text = """
            let [a, {b=1}] = getToken()
        """
        # equivalent to var a = tmp.lhs.op
        #TODO: single quotes are not required
        expected = "let a=getToken(),[b,c]=a,d=c?.b??1"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        xform = TransformMinifyScope()
        xform.disable_warnings=True
        xform.transform(ast)
        output = self.formatter.format(ast)

        self.assertEqual(expected, output)

    def test_001_destructure_object_deep_minify_2(self):
        text = """
            var {lhs:{ op=1 }, rhs:y} = getToken()
        """
        # equivalent to var a = tmp.lhs.op
        #TODO: single quotes are not required
        expected = "var a=getToken(),{'rhs':b}=a,c=a.lhs,d=c?.op??1"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        xform = TransformMinifyScope()
        xform.disable_warnings=True
        xform.transform(ast)
        output = self.formatter.format(ast)

        self.assertEqual(expected, output)

    def test_001_destructure_assignment_default(self):
        text = """
            var [a, b=1] = [0]
        """
        expected = "var[a,b=1]=[0]"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.formatter.format(ast)

        self.assertEqual(expected, output)

    def test_001_destructure_assignment_deep_minify(self):
        text = """
            var {lhs: [v0, v1]} = {'lhs': [123]}
        """
        # equivalent to var a = tmp.lhs.op
        #TODO: single quotes are not required
        expected = "var{'lhs':[a,b]}={'lhs':[123]}"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        xform = TransformMinifyScope()
        xform.disable_warnings=True
        xform.transform(ast)
        output = self.formatter.format(ast)

        self.assertEqual(expected, output)

    def test_001_destructure_assignment_deep_minify_2(self):
        text = """
            var [{x, y=3}] = [{'x':1,}];
        """
        # equivalent to var a = tmp.lhs.op
        #TODO: single quotes are not required
        expected = "var[{'x':a,'y':b}]=[{'x':1,'y':2}]"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        xform = TransformMinifyScope()
        xform.disable_warnings=True
        xform.transform(ast)
        output = self.formatter.format(ast)

        self.assertEqual(expected, output)

    def test_001_destructure_assignment_deep_minify_2(self):
        text = """
            var [x=[2][0]] = [];
        """
        # equivalent to var a = tmp.lhs.op
        #TODO: single quotes are not required
        expected = "var[a=[2][0]]=[]"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        xform = TransformMinifyScope()
        xform.disable_warnings=True
        xform.transform(ast)
        output = self.formatter.format(ast)

        self.assertEqual(expected, output)

    def test_001_destructure_assignment_deep_minify_3(self):
        text = """
            let [{x1=1, y1=2}, {x2=3, y2=4}] = [];
        """
        expected = "let a=[],[b,c]=a,d=b?.x1??1,e=b?.y1??2,f=c?.x2??3,g=c?.y2??4"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        xform = TransformMinifyScope()
        xform.disable_warnings=True
        xform.transform(ast)
        output = self.formatter.format(ast)

        self.assertEqual(expected, output)

    def test_001_destructure_list(self):
        text = "let [x, y, z] = [0,1,2]"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.formatter.format(ast)
        expected = "let[x,y,z]=[0,1,2]"
        self.assertEqual(expected, output)

    def test_001_destructure_list_empty(self):
        text = "let [x, ,z] = [0,1,2]"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.formatter.format(ast)
        expected = "let[x,,z]=[0,1,2]"
        self.assertEqual(expected, output)

    def test_001_destructure_list_reverse(self):
        text = """
            let [a, b] = 0
            [b, a] = [a, b]
        """
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.formatter.format(ast)
        expected = "let[a,b]=0;[b,a]=[a,b]"
        self.assertEqual(expected, output)

    def test_001_function_destructure_list(self):
        text = "function f([arg0, arg1]){}"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.formatter.format(ast)
        expected = "function f([arg0,arg1]){}"
        self.assertEqual(expected, output)

    def test_001_function_destructure_list_minify(self):
        text = "function f([arg0, arg1]){}"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        xform = TransformMinifyScope()
        xform.disable_warnings=True
        xform.transform(ast)
        output = self.formatter.format(ast)
        expected = "function a([b,c]){}"
        self.assertEqual(expected, output)

    def test_001_function_destructure_object(self):
        text = "function f({arg0, arg1}){}"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.formatter.format(ast)
        expected = "function f({arg0,arg1}){}"
        self.assertEqual(expected, output)

    def test_001_function_destructure_object_2(self):
        text = """
            function greet({name = "john", age = 42} = {}){
              print(name + " " +age)
            }
        """
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.formatter.format(ast)
        expected = "function greet({name=\"john\",age=42}={}){print(name+\" \"+age)}"
        self.assertEqual(expected, output)

    def test_001_function_destructure_object_minify(self):
        text = "function f({arg0, arg1}){}"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        xform = TransformMinifyScope()
        xform.disable_warnings=True
        xform.transform(ast)
        output = self.formatter.format(ast)
        expected = "function a({arg0:b,arg1:c}){}"
        self.assertEqual(expected, output)

    def test_001_function_destructure_object_rename_minify(self):
        text = "function f({arg0:n, arg1:v}){}"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        xform = TransformMinifyScope()
        xform.disable_warnings=True
        xform.transform(ast)
        output = self.formatter.format(ast)
        expected = "function a({arg0:b,arg1:c}){}"
        self.assertEqual(expected, output)

    def test_fail_function_destructure_object_with_global(self):
        # with SC_NO_MINIFY introduced, this construct does not work
        # instead when minifying convert to:
        #   input   : x=123;function f({b}){return x}
        #   literal : x=123;function f(arg0){b = arg0?.b; return x}
        #   minified: b=123;function a(c){d = c?.b; return b}
        text = """
            x = 123;function f({b}){return x}
        """
        # equivalent to var a = tmp.lhs.op
        #TODO: single quotes are not required
        expected = "b=123;function a({b:c}){return b}"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        xform = TransformMinifyScope()
        xform.disable_warnings=True
        xform.transform(ast)
        output = self.formatter.format(ast)

        self.assertEqual(expected, output)

    def test_001_destructure_sequence_lambda(self):
        text = """
            ([x,y]) => x + y
        """
        expected = "([a,b])=>a+b"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        xform = TransformMinifyScope()
        xform.disable_warnings=True
        xform.transform(ast)
        output = self.formatter.format(ast)

        self.assertEqual(expected, output)

    def test_001_destructure_object_lambda(self):
        text = """
            ({x,y}) => x + y
        """
        expected = "({x:a,y:b})=>a+b"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        xform = TransformMinifyScope()
        xform.disable_warnings=True
        xform.transform(ast)
        output = self.formatter.format(ast)

        self.assertEqual(expected, output)

    def test_001_destructure_object_default_lambda_v1(self):
        text = """
            ({x=1,y=2}) => x + y
        """
        expected = "(a)=>{let b=a,c=b?.x??1,d=b?.y??2;return c+d}"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        xform = TransformMinifyScope()
        xform.disable_warnings=True
        xform.transform(ast)
        output = self.formatter.format(ast)

        self.assertEqual(expected, output)

    def test_001_destructure_object_default_lambda_v2(self):
        text = """
            ({x=1,y=2}) => {return x + y}
        """
        expected = "(a)=>{let b=a,c=b?.x??1,d=b?.y??2;return c+d}"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        xform = TransformMinifyScope()
        xform.disable_warnings=True
        xform.transform(ast)
        output = self.formatter.format(ast)

        self.assertEqual(expected, output)

    def test_001_class_getter_setter(self):
        text = """
            class Rect {
                constructor(w, h) {
                    this.w = w;
                    this.h = h;
                }
                get width() {return this.w}
                set width(w) {this.w = w}
            }

        """
        expected = "class A{constructor(b,a){this.w=b;this.h=a}get width(){return this.w}set width(a){this.w=a}}"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        xform = TransformMinifyScope()
        xform.disable_warnings=True
        xform.transform(ast)
        output = self.formatter.format(ast)

        self.assertEqual(expected, output)

    def test_001_object_with_function(self):
        text = """
            let obj = {
                get_zero() {
                    return 0
                }
            }
        """
        expected = "let a={get_zero(){return 0}}"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        xform = TransformMinifyScope()
        xform.disable_warnings=True
        xform.transform(ast)
        output = self.formatter.format(ast)

        self.assertEqual(expected, output)

    def test_001_object_with_function_long(self):
        text = """
            let x = {
              long: function() {
                return
              }
            }
        """
        expected = "let a={long:function(){return}}"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        xform = TransformMinifyScope()
        xform.disable_warnings=True
        xform.transform(ast)
        output = self.formatter.format(ast)

        self.assertEqual(expected, output)

    def test_001_computed_function_name_2(self):
        text = """
            let obj = {
                ["get_zero"]() {
                    return 0
                }
            }
        """
        expected = 'let a={["get_zero"](){return 0}}'
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        xform = TransformMinifyScope()
        xform.disable_warnings=True
        xform.transform(ast)
        output = self.formatter.format(ast)

        self.assertEqual(expected, output)

    def test_001_custom_iterator(self):

        text = """
            let iter = {
                [Symbol.iterator]() {
                    let done = false
                    let value = -1
                    return {
                        next() {
                            value += 1
                            done = value+1 < 10
                            return {done, value}
                        }
                    }
                }
            }

            for (let v of iter) {
                console.log(v)
            }

        """
        expected = """let a={[Symbol.iterator](){let c=false;let d=-1;return{next(){d+=1;c=d+1<10;return{'done':c,'value':d}}}}};for(let b of a){console.log(b);}"""
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        xform = TransformMinifyScope()
        xform.disable_warnings=True
        xform.transform(ast)
        output = self.formatter.format(ast)

        self.assertEqual(expected, output)

    def test_001_tuple(self):
        self._chkeq("""
            x = #[1,,3]
        """, "x=#[1,,3]")

    def test_001_record(self):
        self._chkeq("""
            x = #{'x':1}
        """, "x=#{'x':1}")

    def test_001_labeled_block(self):
        self._chkeq("""
            ident: {
                break ident;
            }
        """, "ident:{break ident}")

    def test_001_labeled_block_2(self):
        self._chkeq("""
            ()=>{
                ident: {
                    break ident;
                }
            }
        """, "()=>{ident:{break ident}}")

    def test_001_labeled_block_3(self):
        self._chkeq("""
            label:
            while (True) {
                break label;
            }
        """, "label:while(True){break label}")

    def test_const_scope_identity(self):
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
        expected = "function f(){const x=1;{const x=2;}return x};result=f()"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        xform = TransformIdentityScope()
        xform.disable_warnings=True
        xform.transform(ast)
        output = self.formatter.format(ast)

        self.assertEqual(expected, output)

    def test_const_scope_minify(self):
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
        expected = "function a(){const c=1;{const c=2;}return c};b=a()"
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        xform = TransformMinifyScope()
        xform.disable_warnings=True
        xform.transform(ast)
        output = self.formatter.format(ast)

        self.assertEqual(expected, output)

    def test_001_expect_comma_a(self):
        # python -m  tests.formatter_test -v FormatterTestCase.test_001_expect_comma

        #  TODO: expect an error for a missing comma inside the arglist
        text = """
            f(1,
              2 3)
        """
        tokens = self.lexer.lex(text)
        with self.assertRaises(ParseError) as cm:
            ast = self.parser.parse(tokens)

    def test_001_expect_comma_b(self):
        # python -m  tests.formatter_test -v FormatterTestCase.test_001_expect_comma

        #  TODO: expect an error for a missing comma inside the arglist
        text = """
            f(1
              2,
              3)
        """
        tokens = self.lexer.lex(text)
        with self.assertRaises(ParseError) as cm:
            ast = self.parser.parse(tokens)

    @unittest.expectedFailure
    def test_001_expect_brace(self):

        # python -m tests.formatter_test FormatterTestCase.test_001_expect_brace
        text = """
            function f() {
                if (window)
                    let x = 1
                } // TODO: require a better error for missing brace
            }
        """
        tokens = Lexer().lex(text)

        ast = Parser().parse(tokens)
        output = self.formatter.format(ast)

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
        # the lexer / parser / formatter should
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

    def test_002_deep_3(self):
        # alternating attribute access with nested parenthesis
        # there is a significant slowdown for large N
        N = 500
        prefix = "(x["
        suffix = "])"
        terminal = "(x[0])"
        parts = [prefix] * N + [terminal] + [suffix] * N
        text = "".join(parts)
        tokens = self.lexer.lex(text)
        ast = self.parser.parse(tokens)
        output = self.formatter.format(ast).replace("\n", "")

        self.assertEqual(output, text)

def main():
    unittest.main()


if __name__ == '__main__':
    main()
