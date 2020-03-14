#! cd .. && python3 -m daedalus.compiler


import ast
import dis
import types
import sys
import time
from collections import defaultdict

from .lexer import Lexer, Token, TokenError
from .parser import Parser, ParseError
from .builtins import defaultGlobals, \
    JsUndefined, JsStr, JsArray, JsObject, JsNew, \
    JsFunction
from .transform import TransformAssignScope, TransformClassToFunction
from .util import parseNumber
from .bytecode import dump, calcsize, \
    ConcreteBytecode2, \
    BytecodeInstr, BytecodeJumpInstr, \
    BytecodeRelJumpInstr, BytecodeContinueInstr, BytecodeBreakInstr

import requests

import faulthandler
faulthandler.enable()

import logging
log = logging.getLogger("daedalus.interpreter")

mod_dict = globals()
for val, key in dis.COMPILER_FLAG_NAMES.items():
    mod_dict['CO_' + key] = val

class CompileError(TokenError):
    pass

ST_TRAVERSE = 0x001  # the token has not yet been visited
# literals will be committed immediatley
ST_COMPILE = 0x002  # the token has been visited, commit to the output stream
ST_LOAD = 0x004  # compiling this token should push a value on the stack
ST_STORE = 0x008  # compiling this token will pop an item from the stack

# states starting at 0x100 are used to count the compilation phase
# and can be reused between token types.
ST_BRANCH_TRUE = 0x100
ST_BRANCH_FALSE = 0x200

ST_WHILE = 0x100

class Compiler(object):

    CF_MODULE    = 1
    CF_REPL      = 2
    CF_NO_FAST   = 4

    def __init__(self, name="__main__", filename="<string>", globals=None, flags=1):
        super(Compiler, self).__init__()

        if not isinstance(name, str):
            raise TypeError(name)
        if not isinstance(filename, str):
            raise TypeError(filename)

        # the token stack
        self.seq = []

        # traversal methods are called the first time a Token
        # is visited. Trivial Tokens can be directly 'compiled'
        # to produce opcodes

        self.traverse_mapping = {
            Token.T_MODULE: self._traverse_module,
            Token.T_BINARY: self._traverse_binary,
            Token.T_ASSIGN: self._traverse_assign,
            Token.T_FUNCTIONCALL: self._traverse_functioncall,
            Token.T_ARGLIST: self._traverse_arglist,
            Token.T_BLOCK: self._traverse_block,
            Token.T_LAMBDA: self._traverse_lambda,
            Token.T_FUNCTION: self._traverse_function,
            Token.T_ANONYMOUS_FUNCTION: self._traverse_anonymous_function,
            Token.T_GROUPING: self._traverse_grouping,
            Token.T_BRANCH: self._traverse_branch,
            Token.T_WHILE: self._traverse_while,
            Token.T_OBJECT: self._traverse_object,
            Token.T_LIST: self._traverse_list,
            Token.T_NEW: self._traverse_new,
            Token.T_SUBSCR: self._traverse_subscr,
            Token.T_RETURN: self._traverse_return,
            Token.T_POSTFIX: self._traverse_postfix,
            Token.T_PREFIX: self._traverse_prefix,
            Token.T_EXPORT: self._traverse_export,

            Token.T_VAR: self._traverse_var,

            Token.T_PYIMPORT: self._traverse_pyimport,

            Token.T_NUMBER: self._compile_literal_number,
            Token.T_STRING: self._compile_literal_string,
            Token.T_TEXT: self._compile_text,
            Token.T_LOCAL_VAR: self._compile_text,
            Token.T_GLOBAL_VAR: self._compile_text,
            Token.T_FREE_VAR: self._compile_text,
            Token.T_ATTR: self._compile_attr,
            Token.T_KEYWORD: self._compile_keyword,
            Token.T_DELETE_VAR: self._compile_delete_var,
            Token.T_UNPACK_SEQUENCE: self._compile_unpack_sequence,

            # do nothing
            Token.T_CLOSURE: lambda *args: None
        }

        # compile methods produce opcodes after the token has
        # been traversed
        self.compile_mapping = {
            Token.T_BINARY: self._compile_binary,
            Token.T_ASSIGN: self._compile_assign,
            Token.T_FUNCTIONCALL: self._compile_functioncall,
            Token.T_BRANCH: self._compile_branch,
            Token.T_WHILE: self._compile_while,
            Token.T_OBJECT: self._compile_object,
            Token.T_LIST: self._compile_list,
            Token.T_NEW: self._compile_new,
            Token.T_RETURN: self._compile_return,
            Token.T_SUBSCR: self._compile_subscr,
            Token.T_POSTFIX: self._compile_postfix,
            Token.T_PREFIX: self._compile_prefix,

            Token.T_NUMBER: self._compile_literal_number,
            Token.T_STRING: self._compile_literal_string,
            Token.T_TEXT: self._compile_text,
            Token.T_LOCAL_VAR: self._compile_text,
            Token.T_GLOBAL_VAR: self._compile_text,
            Token.T_FREE_VAR: self._compile_text,
            Token.T_ATTR: self._compile_attr,
            Token.T_DELETE_VAR: self._compile_delete_var,
            Token.T_UNPACK_SEQUENCE: self._compile_unpack_sequence,
        }

        self.bc = ConcreteBytecode2()
        self.bc.name = name
        self.bc.filename = filename
        self.bc.names = []
        self.bc.varnames = []
        self.bc.consts = [None]

        self.flags = flags

        self.globals = self.defaultGlobals()

        if globals:
            self.globals.update(globals)

        self.module_globals = {}

        self.next_label = 0

    @staticmethod
    def defaultGlobals():
        return defaultGlobals();

    def execute(self):
        return self.function_body()

    def compile(self, ast):

        TransformClassToFunction().transform(ast)
        TransformAssignScope().transform(ast)

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

        # init the JS runtime

        # create a default 'this' so that arrow functions have something
        # to inherit

        if ast.type == Token.T_MODULE:
            kind, index = self._token2index(JsUndefined.Token, load=True)
            self.bc.append(BytecodeInstr('LOAD_' + kind, index))
            kind, index = self._token2index(Token(Token.T_TEXT, 0, 0, 'this'), load=False)
            self.bc.append(BytecodeInstr('STORE_' + kind, index))

        # compile userland code

        flg = ST_TRAVERSE
        if ast.type not in (Token.T_MODULE, Token.T_GROUPING, Token.T_BLOCK):
            flg |= ST_LOAD

        self.seq = [(0, flg, ast)]

        while self.seq:
            depth, state, token = self.seq.pop()

            if state & ST_COMPILE == ST_COMPILE:
                fn = self.compile_mapping.get(token.type, None)
                if fn is not None:
                    fn(depth, state, token)
                else:
                    raise CompileError(token, "token not supported")
            else:
                # traverse the AST to produce a linear sequence
                fn = self.traverse_mapping.get(token.type, None)
                if fn is not None:
                    fn(depth, state, token)
                else:
                    raise CompileError(token, "token not supported")

        if self.flags & Compiler.CF_REPL or self.flags & Compiler.CF_MODULE:
            instr = []
            for name, identifier in sorted(self.module_globals.items()):
                tok1 = Token(Token.T_STRING, 0, 0, repr(name))
                kind1, index1 = self._token2index(tok1, load=True)
                self.bc.append(BytecodeInstr('LOAD_' + kind1, index1))

                tok2 = Token(Token.T_TEXT, 0, 0, identifier)
                if identifier in self.bc.names:
                    opcode = 'LOAD_GLOBAL'
                    index2 = self.bc.names.index(identifier)
                else:
                    raise CompileError(tok1, "export error")
                self.bc.append(BytecodeInstr(opcode, index2))
            self.bc.append(BytecodeInstr('BUILD_MAP', len(self.module_globals)))
            self.bc.append(BytecodeInstr('RETURN_VALUE'))

        elif flg & ST_LOAD:
            if len(self.bc) > 0:
                self.bc.append(BytecodeInstr('RETURN_VALUE'))

        # --------

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
            map = [0] * len(self.bc)

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

        lineno = 1
        for op in self.bc:
            if op.lineno and op.lineno > lineno:
                lineno = op.lineno
            elif op.lineno is None or op.lineno < lineno:
                op.lineno = lineno
    # -------------------------------------------------------------------------

    def _traverse_module(self, depth, state, token):

        for child in reversed(token.children):
            self._push(depth + 1, ST_TRAVERSE, child)

    def _traverse_binary(self, depth, state, token):

        flag0 = ST_TRAVERSE
        if token.value == "=":
            flag0 |= ST_STORE
        else:
            flag0 |= ST_LOAD

        flag1 = ST_TRAVERSE
        if token.value == "." and state & ST_STORE:
            flag1 |= ST_STORE
        else:
            flag1 |= ST_LOAD

        self._push(depth, ST_COMPILE | (state & (ST_STORE | ST_LOAD)), token)

        if token.value == ':':
            if token.children[0].type == Token.T_TEXT:
                token.children[0].type = Token.T_STRING
                token.children[0].value = repr(token.children[0].value)

        self._push(depth, flag1, token.children[1])
        self._push(depth, flag0, token.children[0])

    def _traverse_assign(self, depth, state, token):

        self._push(depth, ST_COMPILE | (state & (ST_STORE | ST_LOAD)), token)
        if token.value == "=":
            self._push(depth, ST_TRAVERSE | ST_STORE, token.children[0])
            self._push(depth, ST_TRAVERSE | ST_LOAD, token.children[1])
        else:
            self._push(depth, ST_TRAVERSE | ST_LOAD, token.children[0])
            self._push(depth, ST_TRAVERSE | ST_LOAD, token.children[1])

    def _traverse_functioncall(self, depth, state, token):
        self._push(depth, ST_COMPILE, token)

        flag0 = ST_TRAVERSE | ST_LOAD
        for child in reversed(token.children):
            self._push(depth, flag0, child)

    def _traverse_arglist(self, depth, state, token):

        flag0 = ST_TRAVERSE | ST_LOAD
        for child in reversed(token.children):
            self._push(depth, flag0, child)

    def _traverse_block(self, depth, state, token):

        flag0 = ST_TRAVERSE | ST_LOAD
        for child in reversed(token.children):
            self._push(depth, flag0, child)

    def _traverse_lambda(self, depth, state, token):
        """ JS functions are essentially python functions where
        every argument to the function is a positional 'keyword' argument

        the author may define a default value, but if not given the
        default value should be force to JsUndefined
        """

        name = token.children[0]
        name.value = 'Lambda_%d_%d_%d' % (
                token.line, token.index, depth)

        arglist = token.children[1]
        block = token.children[2]
        closure = token.children[3]

        self._build_function(token, name, arglist, block, closure)

    def _traverse_function(self, depth, state, token):

        name = token.children[0]
        arglist = token.children[1]
        block = token.children[2]
        closure = token.children[3]

        self._build_function(token, name, arglist, block, closure, autobind=False)

        kind, index = self._token2index(name, False)
        self.bc.append(BytecodeInstr('STORE_' + kind, index, lineno=token.line))

    def _traverse_anonymous_function(self, depth, state, token):

        name = token.children[0]
        name.value = 'Anonymous_%d_%d_%d' % (
                token.line, token.index, depth)

        arglist = token.children[1]
        block = token.children[2]
        closure = token.children[3]

        self._build_function(token, name, arglist, block, closure, autobind=False)

    def _build_function(self, token, name, arglist, block, closure, autobind=True):
        """ Create a new function

        Use a new Compiler to compile the function. the name and code
        object are stored as constants inside the current scope
        """
        flags = 0
        sub = Compiler(name.value, self.bc.filename, flags)

        pos_kwarg_count = 0

        kind, index = self._token2index(JsFunction.Token, True)
        self.bc.append(BytecodeInstr('LOAD_' + kind, index, lineno=token.line))

        # get user defined positional arguments
        arglabels = []
        if arglist.type == Token.T_TEXT:
            arglabels.append(arglist.value)
        else:
            for arg in arglist.children:
                arglabels.append(arg.value)

        argcount = len(arglabels)

        # set the default value of user defined arguments to be JS `undefined`
        undef_kind, undef_index = self._token2index(JsUndefined.Token, True)
        for arglabel in arglabels:
            self.bc.append(BytecodeInstr('LOAD_' + undef_kind, undef_index, lineno=token.line))
            sub.bc.varnames.append(arglabel)

        # add 'this' as an optional keyword argument defaulting to 'undefined'
        # add '_x_daedalus_js_args' to collect all extra positional arguments
        # if the function is called with too many arguments they get dumped
        # into the magic variable.

        sub.bc.flags |= CO_VARARGS
        sub.bc.varnames.append("this")
        sub.bc.varnames.append("_x_daedalus_js_args")
        pos_kwarg_count += 1
        #argcount += 1

        # argcount is 1 less so that 'this' gets set to undefined
        # and so that _x_daedalus_js_args collects all extra positional args
        #self.bc.append(BytecodeInstr('LOAD_' + undef_kind, undef_index, lineno=token.line))
        self.bc.append(BytecodeInstr('BUILD_TUPLE', argcount, lineno=token.line))

        kind, index = self._token2index(Token(Token.T_TEXT, 0, 0, 'this'), True)
        self.bc.append(BytecodeInstr('LOAD_' + kind, index, lineno=token.line))
        self.bc.append(BytecodeInstr('LOAD_' + undef_kind, undef_index, lineno=token.line))
        self.bc.append(BytecodeInstr('BUILD_MAP', 1, lineno=token.line))

        # flag indicating positional args have a default value
        flg = 0x01
        # flag indicating a dictionary is being passed for keyword
        # only arguments
        flg |= 0x02

        if closure.children:
            flg |= 0x08

            closure_count = 0
            for child in closure.children:
                if child.type == Token.T_FREE_VAR:
                    sub.bc.freevars.append(child.value)
                    kind, index = self._token2index(child, True)
                    self.bc.append(BytecodeInstr('LOAD_CLOSURE', index, lineno=token.line))
                    closure_count += 1
                elif child.type == Token.T_CELL_VAR:
                    sub.bc.cellvars.append(child.value)
                else:
                    raise TokenError(child, "expected cell or free var")

            self.bc.append(BytecodeInstr('BUILD_TUPLE', closure_count, lineno=token.line))

        # finally compile the function, get the code object
        sub._compile(block)
        sub._finalize()

        sub.bc.argcount = argcount
        sub.bc.kwonlyargcount = 1

        stacksize = calcsize(sub.bc)
        try:
            code = sub.bc.to_code(stacksize)
        except Exception as e:
            sub.dump()
            raise e

        index_code = len(self.bc.consts)
        self.bc.consts.append(code)
        index_name = len(self.bc.consts)
        self.bc.consts.append(name.value)

        self.bc.append(BytecodeInstr('LOAD_CONST', index_code, lineno=token.line))
        self.bc.append(BytecodeInstr('LOAD_CONST', index_name, lineno=token.line))

        self.bc.append(BytecodeInstr('MAKE_FUNCTION', flg, lineno=token.line))

        argcount = 1
        if autobind:
            kind, index = self._token2index(Token(Token.T_TEXT, 0, 0, 'this'), True)
            self.bc.append(BytecodeInstr('LOAD_' + kind, index, lineno=token.line))
            argcount += 1

        # TODO: pop top if state&ST_LOAD is false
        self.bc.append(BytecodeInstr('CALL_FUNCTION', argcount, lineno=token.line))

    def _traverse_grouping(self, depth, state, token):
        for child in reversed(token.children):
            self._push(depth + 1, ST_TRAVERSE, child)

    def _traverse_branch(self, depth, state, token):

        arglist = token.children[0]
        self._push(depth, ST_COMPILE | ST_BRANCH_TRUE, token)
        self._push(depth + 1, ST_TRAVERSE | ST_LOAD, arglist)

    def _traverse_while(self, depth, state, token):

        token.label_begin = self._make_label()
        token.label_end = self._make_label()

        nop = BytecodeInstr('NOP')
        self.bc.append(nop)
        nop.add_label(token.label_begin)

        arglist = token.children[0]
        self._push(depth, ST_COMPILE | ST_WHILE, token)
        self._push(depth + 1, ST_TRAVERSE | ST_LOAD, arglist)

    def _traverse_object(self, depth, state, token):

        kind, index = self._token2index(JsObject.Token, True)
        self.bc.append(BytecodeInstr('LOAD_' + kind, index, lineno=token.line))

        self._push(depth, ST_COMPILE, token)
        for child in reversed(token.children):
            self._push(depth + 1, ST_TRAVERSE | ST_LOAD, child)

    def _traverse_list(self, depth, state, token):

        kind, index = self._token2index(JsArray.Token, True)
        self.bc.append(BytecodeInstr('LOAD_' + kind, index, lineno=token.line))

        self._push(depth, ST_COMPILE, token)
        for child in reversed(token.children):
            self._push(depth + 1, ST_TRAVERSE | ST_LOAD, child)

    def _traverse_new(self, depth, state, token):

        kind, index = self._token2index(JsNew.Token, True)
        self.bc.append(BytecodeInstr('LOAD_' + kind, index, lineno=token.line))

        child = token.children[0]
        self._push(depth, ST_COMPILE, token)

        if child.type == Token.T_FUNCTIONCALL:
            for child in reversed(child.children):
                self._push(depth + 1, ST_TRAVERSE, child)
        else:
            self._push(depth + 1, ST_TRAVERSE, child)

    def _traverse_subscr(self, depth, state, token):

        flg = ST_COMPILE | ((ST_LOAD | ST_STORE) & state)
        self._push(depth, flg, token)
        for child in reversed(token.children):
            self._push(depth + 1, ST_TRAVERSE | ST_LOAD, child)

    def _traverse_return(self, depth, state, token):

        flg = ST_COMPILE | ((ST_LOAD | ST_STORE) & state)
        self._push(depth, flg, token)
        for child in reversed(token.children):
            self._push(depth + 1, ST_TRAVERSE | ST_LOAD, child)

    def _traverse_postfix(self, depth, state, token):
        """
        Python has no postfix operator
        instead:
            load value
            duplicate top
            increment/decrement top by 1
            store value

        duplicating top is conditional on a ld flag being set
        """

        self._push(depth, ST_COMPILE | ST_LOAD, token)
        self._push(depth + 1, ST_TRAVERSE | ST_LOAD, child)

    def _traverse_prefix(self, depth, state, token):
        """
        Python has no prefix operator
        instead:
            load value
            increment/decrement top by 1
            duplicate top
            store value

        duplicating top is conditional on a ld flag being set
        """
        pass

    def _traverse_pyimport(self, depth, state, token):

        tok_name, tok_level, tok_fromlist = token.children

        self._compile_literal_number(depth+1, ST_LOAD, tok_level)

        if len(tok_fromlist.children) == 0:
            self.bc.append(BytecodeInstr('LOAD_CONST', 0))
        else:
            raise TokenError(token, "from list")


        _, index = self._token2index(Token(Token.T_GLOBAL_VAR, 0, 0, token.value))
        self.bc.append(BytecodeInstr('IMPORT_NAME', index))
        kind, index = self._token2index(tok_name, load=False)
        self.bc.append(BytecodeInstr('STORE_' + kind, index))

    def _traverse_export(self, depth, state, token):

        self.module_globals[token.value] = token.children[0].value

        self._push(depth + 1, ST_TRAVERSE, token.children[1])

    def _traverse_var(self, depth, state, token):
        """assume that variables have been taken care of by now
        by the various transform functions
        """
        for child in reversed(token.children):
            self._push(depth + 1, ST_TRAVERSE | ST_LOAD, child)




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

        if token.value == '.':
            pass

        elif token.value == ':':
            pass

        elif token.value == "===":
            # TODO: define correct behavior for === and ==
            self.bc.append(BytecodeInstr('COMPARE_OP', dis.cmp_op.index("=="), lineno=token.line))

        elif token.value == "!==":
            # TODO: define correct behavior for !== and !=
            self.bc.append(BytecodeInstr('COMPARE_OP', dis.cmp_op.index("!="), lineno=token.line))

        elif token.value in dis.cmp_op:
            self.bc.append(BytecodeInstr('COMPARE_OP', dis.cmp_op.index(token.value), lineno=token.line))

        elif token.value in binop:
            self.bc.append(BytecodeInstr(binop[token.value]))

        else:
            raise CompileError(token, "not supported")

    def _compile_assign(self, depth, state, token):

        binop_store = {
            "+=": "INPLACE_ADD",
            "*=": "INPLACE_MULTIPLY",
            "@=": "INPLACE_MATRIX_MULTIPLY",
            "//=": "INPLACE_FLOOR_DIVIDE",
            "/=": "INPLACE_TRUE_DIVIDE",
            "%=": "INPLACE_MODULO",
            "-=": "INPLACE_SUBTRACT",
            "**=": "INPLACE_POWER",
            "<<=": "INPLACE_LSHIFT",
            ">>=": "INPLACE_RSHIFT",
            "&=": "INPLACE_AND",
            "^=": "INPLACE_XOR",
            "|=": "INPLACE_OR",
        }

        if token.value == '=':
            pass

        if token.value in binop_store:
            self.bc.append(BytecodeInstr(binop_store[token.value], lineno=token.line))

            # TODO: this has side effects if LHS is complicated
            self._push(depth, ST_COMPILE | ST_STORE, token.children[0])

    def _compile_text(self, depth, state, token):
        kind, index = self._token2index(token, state & ST_LOAD)

        if state & ST_STORE:
            mode = 'STORE_'
        else:
            mode = 'LOAD_'

        self.bc.append(BytecodeInstr(mode + kind, index, lineno=token.line))

    def _compile_attr(self, depth, state, token):
        _, index = self._token2index_name(token, load=True)

        opcode = "STORE_ATTR" if state & ST_STORE else "LOAD_ATTR"
        self.bc.append(BytecodeInstr(opcode, index, lineno=token.line))

    def _compile_literal_number(self, depth, state, token):
        kind, index = self._token2index(token, True)
        instr = [BytecodeInstr('LOAD_' + kind, index, lineno=token.line)]
        if state & ST_LOAD == 0:
            instr.append(BytecodeInstr("POP_TOP"))
        self.bc.extend(instr)

    def _compile_literal_string(self, depth, state, token):
        kind, index = self._token2index(JsStr.Token, True)
        self.bc.append(BytecodeInstr('LOAD_' + kind, index, lineno=token.line))
        kind, index = self._token2index(token, True)
        self.bc.append(BytecodeInstr('LOAD_' + kind, index, lineno=token.line))
        self.bc.append(BytecodeInstr('CALL_FUNCTION', 1, lineno=token.line))

        if state & ST_LOAD == 0:
            self.bc.append(BytecodeInstr("POP_TOP"))

    def _compile_functioncall(self, depth, state, token):

        arglist = token.children[1]
        argcount = len(arglist.children)
        # TODO: pop top if state&ST_LOAD is false
        self.bc.append(BytecodeInstr('CALL_FUNCTION', argcount))

    def _compile_branch(self, depth, state, token):
        """
        The branch node will be visited several times to handle
        initialization, running the true branch, and then conditionally
        running the false branch

        the state flag controls which opcodes will be produced
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

    def _compile_while(self, depth, state, token):

        if state & ST_WHILE:

            token.label_false = self._make_label()
            instr = BytecodeJumpInstr('POP_JUMP_IF_FALSE', token.label_end)
            self.bc.append(instr)

            self._push(depth, ST_COMPILE, token)
            self._push(depth, ST_TRAVERSE, token.children[1])

        else:
            self.bc.append(BytecodeJumpInstr('JUMP_ABSOLUTE', token.label_begin))

            nop = BytecodeInstr('NOP')
            self.bc.append(nop)
            nop.add_label(token.label_end)

    def _compile_object(self, depth, state, token):
        """
        build the object as a native python type then call JsObject to
        wrap the list in a type that mimics the array api
        """
        self.bc.append(BytecodeInstr("BUILD_MAP", len(token.children), lineno=token.line))
        # TODO: pop top if state&ST_LOAD is false
        self.bc.append(BytecodeInstr('CALL_FUNCTION', 1))

    def _compile_list(self, depth, state, token):
        """
        build the list as a native python type then call JsArray to
        wrap the list in a type that mimics the array api
        """
        self.bc.append(BytecodeInstr("BUILD_LIST", len(token.children), lineno=token.line))
        self.bc.append(BytecodeInstr('CALL_FUNCTION', 1))

    def _compile_new(self, depth, state, token):

        N = 1
        child = token.children[0]
        if child.type == Token.T_FUNCTIONCALL:
            N = len(child.children) - 1
        # TODO: pop top if state&ST_LOAD is false
        self.bc.append(BytecodeInstr('CALL_FUNCTION', N))

    def _compile_return(self, depth, state, token):

        self.bc.append(BytecodeInstr('RETURN_VALUE'))

    def _compile_subscr(self, depth, state, token):
        opcode = "BINARY_SUBSCR" if state & ST_LOAD else "STORE_SUBSCR"
        self.bc.append(BytecodeInstr(opcode, lineno=token.line))

    def _compile_keyword(self, depth, state, token):

        if token.value in ['this', 'null']:
            return self._compile_text(depth, state, token)
        else:
            raise CompileError(token, "Unsupported keyword")

    def _compile_delete_var(self, depth, state, token):
        pass

    def _compile_postfix(self, depth, state, token):
        pass

    def _compile_prefix(self, depth, state, token):
        pass

    # -------------------------------------------------------------------------

    def _push(self, depth, state, token):
        self.seq.append((depth, state, token))

    def _make_label(self):
        self.next_label += 1
        return self.next_label

    def _token2index(self, tok, load=False):
        """ get the index for a token in the constants table for the code object

        each token may be stored in one of the global/name/fast tables

        """

        if tok.type == Token.T_NUMBER:
            value = parseNumber(tok)
            if value not in self.bc.consts:
                self.bc.consts.append(value)
            index = self.bc.consts.index(value)
            return 'CONST', index

        elif tok.type == Token.T_STRING:
            #value = JsStr(ast.literal_eval(tok.value))
            value = ast.literal_eval(tok.value)
            if tok.value not in self.bc.consts:
                self.bc.consts.append(value)
            index = self.bc.consts.index(value)
            return 'CONST', index

        elif tok.type == Token.T_LOCAL_VAR:
            if tok.value in self.bc.cellvars:
                index = self.bc.cellvars.index(tok.value)
                return 'DEREF', index

            try:
                index = self.bc.varnames.index(tok.value)
                return 'FAST', index
            except ValueError:
                pass

            index = len(self.bc.varnames)
            self.bc.varnames.append(tok.value)
            return 'FAST', index

        elif tok.type == Token.T_GLOBAL_VAR:
            try:
                index = self.bc.names.index(tok.value)
                return 'GLOBAL', index
            except ValueError:
                pass

            index = len(self.bc.names)
            self.bc.names.append(tok.value)
            return 'GLOBAL', index

        elif tok.type == Token.T_FREE_VAR:

            if tok.value in self.bc.freevars:
                return "DEREF", len(self.bc.cellvars) + self.bc.freevars.index(tok.value)

            if tok.value in self.bc.cellvars:
                return "DEREF", self.bc.cellvars.index(tok.value)

        elif tok.type == Token.T_TEXT or tok.type == Token.T_KEYWORD:

            #if not load and (self.flags & Compiler.CF_REPL or self.flags & Compiler.CF_MODULE):
            #    self.module_globals.add(tok.value)

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

        raise CompileError(tok, "unable to map token")

    def _token2index_name(self, tok, load=False):

        try:
            index = self.bc.names.index(tok.value)
            return 'NAME', index
        except ValueError:
            index = len(self.bc.names)
            self.bc.names.append(tok.value)
            return 'NAME', index

    def _compile_unpack_sequence(self, depth, state, token):

        self.bc.append(BytecodeInstr('UNPACK_SEQUENCE', len(token.children), lineno=token.line))

        for child in token.children:
            kind, index = self._token2index(child, False)
            self.bc.append(BytecodeInstr('STORE_' + kind, index, lineno=token.line))

def main():  # pragma: no cover

    text1 = """
        //console.log((() => 5)())
        //console.warn(((a,b)=>a+b)(1,2))
        //fetch('https://www.example.com')
        //    .then(response => {
        //        console.log('on then1', response)
        //        return response.text()
        //    })
        //    .then(text => {
        //        console.log('on then2', text.__len__())
        //        return text
        //    })

        //get_text = (url, parameters) => {
        //    if (parameters === undefined) {
        //        parameters = {}
        //    }
        //    parameters.method = "GET"
        //    return fetch(url, parameters).then((response) => {
        //        return response.text()
        //    })
        //}
        //get_text("www.example.com")
        //    .then(text => console.log(text))
        //    .catch_(error => console.error(error))

        //function f(arg0) {
        //    console.log('arg', arguments.length)
        //    console.log('arg', arguments[0])
        //    console.log('arg', arguments[1])
        //    console.log('arg', arguments[2])
        //    console.log('arg', arguments[3])
        //}

        // console.log(f(1,2,3))
        //x = (a) => {
        //    i = 0;
        //    while (i < arguments.length) {
        //        console.info(i, arguments[i])
        //        i+=1
        //    }
        //    console.log("this", this)
        //}
        //x(100, 200)

        //class Shape() {
        //    constructor() {
        //        this.width = 5
        //        this.height = 10
        //    }
        //    area() {
        //        return this.width * this.height
        //    }
        //}

    """

    text1 = """
        "use strict";
        const[A,B,f1,f2]=(function(){
            function f1(){};
            function f2(){};
            function A(){};
            function B(){};
            return[A,B,f1,f2]
        })();
        const[fibonacci]=(function(){
            function fibonacci(num){
                if(num<=1){return 1};
                return fibonacci(num-1)+fibonacci(num-2)
            };
            console.log("derp");
            return[fibonacci]
        })();
        return{A,B,f1,f2,fibonacci}
    """

    tokens = Lexer().lex(text1)
    ast = Parser().parse(tokens)

    interp = Compiler()

    try:
        interp.compile(ast)

    finally:
        print(ast.toString())

    interp.dump()

    print(interp.execute())

if __name__ == '__main__':  # pragma: no cover
    main()
