#! cd .. && python3 -m daedalus.interpreter

import json
import ast
import dis
import types
import sys
from collections import defaultdict

from .lexer import Lexer, Token, TokenError
from .parser import Parser, ParseError

from .bytecode import dump, calcsize, \
    ConcreteBytecode2, \
    BytecodeInstr, BytecodeJumpInstr, \
    BytecodeRelJumpInstr, BytecodeContinueInstr, BytecodeBreakInstr

import faulthandler
faulthandler.enable()

import logging
log = logging.getLogger("daedalus.interpreter")

mod_dict = globals()
for val, key in dis.COMPILER_FLAG_NAMES.items():
    mod_dict['CO_' + key] = val

class InterpreterError(TokenError):
    pass

ST_TRAVERSE = 0x001 # the token has not yet been visited
                # literals will be committed immediatley
ST_COMPILE = 0x002  # the token has been visited, commit to the output stream
ST_LOAD = 0x004 # compiling this token should push a value on the stack
ST_STORE = 0x008 # compiling this token will pop an item from the stack
ST_BRANCH_TRUE = 0x100
ST_BRANCH_FALSE = 0x200

class JsObjectBase(object):
    def __init__(self):
        super(JsObjectBase, self).__init__()

class JsUndefined(JsObjectBase):
    _instance = None

    def __init__(self):
        super(JsUndefined, self).__init__()

        if JsUndefined._instance != None:
            raise Exception("singleton")

    def __repr__(self):
        return "undefined"

    def __str__(self):
        return "undefined"

JsUndefined._instance = JsUndefined()

class JsObject(JsObjectBase):
    def __init__(self, attrs):
        super(JsObject, self).__init__()

        super(JsObject, self).__setattr__('attrs', attrs)

    def __str__(self):
        return json.dumps(self.attrs)

    def __repr__(self):
        return json.dumps(self.attrs)

    def __getattr__(self, name):
        try:
            return self.attrs[name]
        except KeyError:
            raise AttributeError

    def __setattr__(self, name, value):
        self.attrs[name] = value

JsObject.Token = Token(Token.T_TEXT, 0, 0, "JsObject")

def JsNew(constructor, *args):
    print("found constructor", constructor, args)
    return None

JsNew.Token = Token(Token.T_TEXT, 0, 0, "JsNew")

class JsConsole(JsObject):
    def __init__(self):
        super(JsConsole, self).__init__({})

    def log(self, *args):
        sys.stdout.write(' '.join(str(arg) for arg in args) + "\n")

    def info(self, *args):
        sys.stderr.write('I: ' + ' '.join(str(arg) for arg in args) + "\n")

    def warn(self, *args):
        sys.stderr.write('W: ' + ' '.join(str(arg) for arg in args) + "\n")

    def error(self, *args):
        sys.stderr.write('E: ' + ' '.join(str(arg) for arg in args) + "\n")

class JsPromise(object):
    def __init__(self, fn):
        super(JsPromise, self).__init__({})
        self._fn = fn

class Interpreter(object):

    CF_MODULE    = 1
    CF_REPL      = 2
    CF_NO_FAST   = 4

    def __init__(self, name="__main__", filename="<string>", flags=0):
        super(Interpreter, self).__init__()

        if not isinstance(name, str):
            raise TypeError(name)
        if not isinstance(filename, str):
            raise TypeError(filename)

        self.seq = []

        self.traverse_mapping = {
            Token.T_MODULE: self._traverse_module,
            Token.T_BINARY: self._traverse_binary,
            Token.T_FUNCTIONCALL: self._traverse_functioncall,
            Token.T_ARGLIST: self._traverse_arglist,
            Token.T_BLOCK: self._traverse_block,
            Token.T_LAMBDA: self._traverse_lambda,
            Token.T_GROUPING: self._traverse_grouping,
            Token.T_BRANCH: self._traverse_branch,
            Token.T_OBJECT: self._traverse_object,
            Token.T_NEW: self._traverse_new,

            Token.T_NUMBER: self._compile_literal_number,
            Token.T_STRING: self._compile_literal_string,
            Token.T_TEXT: self._compile_text,
            Token.T_ATTR: self._compile_attr,
        }

        self.compile_mapping = {
            Token.T_BINARY: self._compile_binary,
            Token.T_FUNCTIONCALL: self._compile_functioncall,
            Token.T_BRANCH: self._compile_branch,
            Token.T_OBJECT: self._compile_object,
            Token.T_NEW: self._compile_new,
        }

        self.bc = ConcreteBytecode2()
        self.bc.name = name
        self.bc.filename = filename
        self.bc.names = []
        self.bc.varnames = []
        self.bc.consts = [None]

        self.flags = flags
        self.globals = {
            'console': JsConsole(),
            'undefined': JsUndefined._instance,
            'JsObject': JsObject,
            'JsNew': JsNew,
        }
        self.module_globals = set()

        self.next_label = 0

    def execute(self):
        rv = self.function_body()

    def compile(self, ast):

        self._compile(ast)
        self._finalize()

        stacksize = calcsize(self.bc)
        code = self.bc.to_code(stacksize)

        self.function_body = types.FunctionType(code, self.globals, self.bc.name)

    def dump(self):
        if self.bc:
            dump(self.bc)

    # -------------------------------------------------------------------------

    def _compile(self, ast):
        """ non-recursive implementation of _compile

        for each node process the children in reverse order
        """

        flg = ST_TRAVERSE
        if ast.type not in (Token.T_MODULE, Token.T_GROUPING):
            flg |= ST_LOAD

        self.seq = [(0, flg, ast)]

        while self.seq:
            depth, state, token = self.seq.pop()

            if state & ST_COMPILE == ST_COMPILE:
                fn = self.compile_mapping.get(token.type, None)
                if fn is not None:
                    fn(depth, state, token)
                else:
                    raise InterpreterError(token, "token not supported")
            else:
                # traverse the AST to produce a linear sequence
                fn = self.traverse_mapping.get(token.type, None)
                if fn is not None:
                    fn(depth, state, token)
                else:
                    raise InterpreterError(token, "token not supported")

        if flg & ST_LOAD:
            if len(self.bc) > 0:
                self.bc.append(BytecodeInstr('RETURN_VALUE'))

        if not len(self.bc) or self.bc[-1].name != 'RETURN_VALUE':
            self.bc.append(BytecodeInstr('LOAD_CONST', 0))
            self.bc.append(BytecodeInstr('RETURN_VALUE'))

    def _finalize(self):

        retry = True
        again = False
        attempts = 0
        while retry:
            attempts += 1
            if attempts > 10:
                sys.stderr.write("ekanscrypt compiler warning: finalize attempt %d\n" % attempts)
            if attempts > 20:
                raise CompilerError(Token("", 1, 0, ""), "failed to finalize")

            # walk the list of instructions, build the map
            # for computing the absolute jumps
            # lbl -> pos
            src = {}
            # lbl -> list-of-index
            tgt = defaultdict(list)
            # index -> pos
            map = [0]*len(self.bc)

            pos = 0
            for index, op in enumerate(self.bc):
                if not isinstance(op, BytecodeInstr):
                    raise TypeError(op)
                if op._es_target:
                    tgt[op._es_target].append(index)
                for lbl in op._es_labels:
                    src[lbl] = pos
                map[index] = pos
                pos += op.size

            retry = False
            for lbl, tgts in tgt.items():
                for index in tgts:
                    op = self.bc[index]
                    size = op.size
                    op.finalize(map[index], src[lbl])
                    new_size = op.size
                    # if the size is different the jump targets
                    # will need to be recalculated
                    # keep processing the whole list since
                    # it is possible that will minimize the number
                    # of loops
                    if size != new_size:
                        retry = True

            if again is False and retry is False:
                again = True
                retry = True

    # -------------------------------------------------------------------------

    def _traverse_module(self, depth, state, token):
        for child in reversed(token.children):
            self._push(depth+1, ST_TRAVERSE, child)

    def _traverse_binary(self, depth, state, token):

        flag1 = ST_TRAVERSE|ST_LOAD

        flag0 = ST_TRAVERSE
        if token.value == "=":
            flag0 |= ST_STORE
        else:
            flag0 |= ST_LOAD

        self._push(depth, ST_COMPILE, token)

        if token.value == ':':
            if token.children[0].type == Token.T_TEXT:
                token.children[0].type = Token.T_STRING
                token.children[0].value = repr(token.children[0].value)

        if flag0&ST_STORE:
            self._push(depth, flag0, token.children[0])
            self._push(depth, flag1, token.children[1])
        else:
            self._push(depth, flag1, token.children[1])
            self._push(depth, flag0, token.children[0])

    def _traverse_functioncall(self, depth, state, token):
        self._push(depth, ST_COMPILE, token)

        flag0 = ST_TRAVERSE|ST_LOAD
        for child in reversed(token.children):
            self._push(depth, flag0, child)

    def _traverse_arglist(self, depth, state, token):

        flag0 = ST_TRAVERSE|ST_LOAD
        for child in reversed(token.children):
            self._push(depth, flag0, child)

    def _traverse_block(self, depth, state, token):

        flag0 = ST_TRAVERSE|ST_LOAD
        for child in reversed(token.children):
            self._push(depth, flag0, child)

    def _traverse_lambda(self, depth, state, token):
        """ JS functions are essentially python functions where
        every argument to the function is a positional 'keyword' argument

        the author may define a default value, but if not given the
        default value should be force to JsUndefined
        """

        lambda_qualified_name = 'Anonymous_%d_%d_%d' % (
                token.line, token.index, depth)

        arglist = token.children[0]
        block = token.children[1]

        flags = 0
        sub = Interpreter(lambda_qualified_name, self.bc.filename, flags)

        disable_positional = False
        disable_keyword = False
        pos_kwarg_instr = []
        pos_kwarg_count = 0
        extra_args = [] # *args or **kwargs
        argcount = 0
        for arg in arglist.children:
            if arg.type == Token.T_TEXT:
                if disable_positional:
                    raise CompilerError(arg, "positional after keyword argument")
                sub.bc.varnames.append(arg.value)
                argcount += 1
        sub.bc.varnames.extend(extra_args)

        sub.compile(block)
        sub.bc.argcount = argcount

        stacksize = calcsize(sub.bc)
        try:
            code = sub.bc.to_code(stacksize)
        except Exception as e:
            sub.dump()
            raise e

        index_code = len(self.bc.consts)
        self.bc.consts.append(code)
        index_name = len(self.bc.consts)
        self.bc.consts.append(lambda_qualified_name)

        flg = 0

        if pos_kwarg_count:
            # TODO
            flg |= 0x01

        if False:
            # push kwarg only arguments tuple
            flg |= 0x02

        if False:
            # push annotated dictionary
            flg |= 0x04

        self.bc.append(BytecodeInstr('LOAD_CONST', index_code, lineno=token.line))
        self.bc.append(BytecodeInstr('LOAD_CONST', index_name, lineno=token.line))

        self.bc.append(BytecodeInstr('MAKE_FUNCTION', flg, lineno=token.line))

    def _traverse_grouping(self, depth, state, token):
        for child in reversed(token.children):
            self._push(depth+1, ST_TRAVERSE, child)

    def _traverse_branch(self, depth, state, token):

        arglist = token.children[0]
        self._push(depth, ST_COMPILE|ST_BRANCH_TRUE, token)
        self._push(depth, ST_TRAVERSE|ST_LOAD, arglist)

    def _traverse_object(self, depth, state, token):

        kind, index = self._token2index(JsObject.Token, True)
        self.bc.append(BytecodeInstr('LOAD_' + kind, index, lineno=token.line))

        self._push(depth, ST_COMPILE, token)
        for child in reversed(token.children):
            self._push(depth+1, ST_TRAVERSE, child)

    def _traverse_new(self, depth, state, token):

        kind, index = self._token2index(JsNew.Token, True)
        self.bc.append(BytecodeInstr('LOAD_' + kind, index, lineno=token.line))

        self._push(depth, ST_COMPILE, token)
        for child in reversed(token.children):
            self._push(depth+1, ST_TRAVERSE, child)

    # -------------------------------------------------------------------------

    def _compile_binary(self, depth, state, token):
        binop = {
            "+": "BINARY_ADD",
            "*": "BINARY_MULTIPLY",
            "@": "BINARY_MATRIX_MULTIPLY",
            "//": "BINARY_FLOOR_DIVIDE",
            "/": "BINARY_TRUE_DIVIDE",
            "%": "BINARY_MODULO",
            "-": "BINARY_SUBTRACT",
            "**": "BINARY_POWER",
            "<<": "BINARY_LSHIFT",
            ">>": "BINARY_RSHIFT",
            "&": "BINARY_AND",
            "^": "BINARY_XOR",
            "|": "BINARY_OR",
        }

        binop_store = {
            "+=": "BINARY_ADD",
            "*=": "BINARY_MULTIPLY",
            "@=": "BINARY_MATRIX_MULTIPLY",
            "//=": "BINARY_FLOOR_DIVIDE",
            "/=": "BINARY_TRUE_DIVIDE",
            "%=": "BINARY_MODULO",
            "-=": "BINARY_SUBTRACT",
            "**=": "BINARY_POWER",
            "<<=": "BINARY_LSHIFT",
            ">>=": "BINARY_RSHIFT",
            "&=": "BINARY_AND",
            "^=": "BINARY_XOR",
            "|=": "BINARY_OR",
        }

        if token.value == '.':
            pass
        elif token.value == '=':
            pass
        elif token.value == ':':
            pass
        elif token.value in dis.cmp_op:
            self.bc.append(BytecodeInstr('COMPARE_OP', dis.cmp_op.index(token.value), lineno=token.line))

        elif token.value in binop:
            self.bc.append(BytecodeInstr(binop[token.value]))
        else:
            raise InterpreterError(token, "not supported")

    def _compile_text(self, depth, state, token):
        kind, index = self._token2index(token, True)

        if state & ST_STORE:
            mode = 'STORE_'
        else:
            mode = 'LOAD_'

        self.bc.append(BytecodeInstr(mode + kind, index, lineno=token.line))

    def _compile_attr(self, depth, state, token):
        _, index = self._token2index_name(token, load=True)
        self.bc.append(BytecodeInstr('LOAD_ATTR', index, lineno=token.line))

    def _compile_literal_number(self, depth, state, token):
        kind, index = self._token2index(token, True)
        instr = [BytecodeInstr('LOAD_' + kind, index, lineno=token.line)]
        if state & ST_LOAD == 0:
            instr.append(BytecodeInstr("POP_TOP"))
        self.bc.extend(instr)

    def _compile_literal_string(self, depth, state, token):
        kind, index = self._token2index(token, True)
        instr = [BytecodeInstr('LOAD_' + kind, index, lineno=token.line)]
        if state & ST_LOAD == 0:
            instr.append(BytecodeInstr("POP_TOP"))
        self.bc.extend(instr)

    def _compile_functioncall(self, depth, state, token):

        arglist = token.children[1]
        argcount = len(arglist.children)
        self.bc.append(BytecodeInstr('CALL_FUNCTION', argcount))

    def _compile_branch(self, depth, state, token):
        """
        The branch node will be visited several times to handle
        initialization, running the true branch, and then conditionally
        running the false branch
        """
        if state & ST_BRANCH_TRUE:

            lbl = self._make_label()
            instr = BytecodeJumpInstr('POP_JUMP_IF_FALSE', lbl)
            self.bc.append(instr)

            flg0 = ST_COMPILE
            if len(token.children) > 2:
                flg0 |= ST_BRANCH_FALSE
            self._push(depth, flg0, token)

            self._push(depth, ST_TRAVERSE, token.children[1])

            token.label_false = lbl

        elif state & ST_BRANCH_FALSE:

            lbl = self._make_label()
            token.label_true = token.label_false
            token.label_false = lbl

            self.bc.append(BytecodeJumpInstr('JUMP_ABSOLUTE', token.label_false))

            nop = BytecodeInstr('NOP')
            self.bc.append(nop)
            nop.add_label(token.label_true)

            self._push(depth, ST_COMPILE, token)
            self._push(depth, ST_TRAVERSE, token.children[2])
        else:
            nop = BytecodeInstr('NOP')
            self.bc.append(nop)
            nop.add_label(token.label_false)

    def _compile_object(self, depth, state, token):
        self.bc.append(BytecodeInstr("BUILD_MAP", len(token.children), lineno=token.line))
        self.bc.append(BytecodeInstr('CALL_FUNCTION', 1))

    def _compile_new(self, depth, state, token):
        self.bc.append(BytecodeInstr('CALL_FUNCTION', 1))

    # -------------------------------------------------------------------------

    def _push(self, depth, state, token):
        self.seq.append((depth, state, token))

    def _make_label(self):
        self.next_label += 1
        return self.next_label

    def _token2index(self, tok, load=False):

        if tok.type == Token.T_NUMBER:
            # value = parseNumber(tok)
            value = int(tok.value)
            if value not in self.bc.consts:
                self.bc.consts.append(value)
            index = self.bc.consts.index(value)
            return 'CONST', index

        elif tok.type == Token.T_STRING:
            value = ast.literal_eval(tok.value)
            if tok.value not in self.bc.consts:
                self.bc.consts.append(value)
            index = self.bc.consts.index(value)
            return 'CONST', index

        elif tok.type == Token.T_TEXT:

            if tok.value in self.globals:

                try:
                    index = self.bc.names.index(tok.value)
                    return 'GLOBAL', index
                except ValueError:
                    index = len(self.bc.names)
                    if load:
                        log.debug('read from unassigned global: %s' % tok.value)
                    self.bc.names.append(tok.value)
                    return 'GLOBAL', index

            try:
                index = self.bc.varnames.index(tok.value)
                return 'FAST', index
            except ValueError:
                pass

            index = len(self.bc.varnames)
            self.bc.varnames.append(tok.value)
            return 'FAST', index

    def _token2index_name(self, tok, load=False):

        try:
            index = self.bc.names.index(tok.value)
            return 'NAME', index
        except ValueError:
            index = len(self.bc.names)
            self.bc.names.append(tok.value)
            return 'NAME', index

def main():  # pragma: no cover

    text1 = """
       //console.log((() => 5)())
       //console.warn(((a,b)=>a+b)(1,2))
       Object = () => {}
       x = new Object

    """

    tokens = Lexer().lex(text1)
    ast = Parser().parse(tokens)

    print(ast.toString())

    interp = Interpreter()

    interp.compile(ast)

    interp.dump()

    interp.execute()


if __name__ == '__main__':  # pragma: no cover
    main()