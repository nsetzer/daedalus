#! cd .. && python3 -m daedalus.compiler

"""
version 2 compiler requirements:
    AssignScope Transform should have different versions between
        the output that is used as input into Formatter or Compiler
    Compiler needs to use one of two identities for variables
        short_name :: "a#f0"
        long_name :: "__main__@b0.a@0#f0"
    long_name is required for const_expr, while short_name is required
    to handle the default scoping case for python

    problem: short_name/long_name is an attribute on the refernce, not token
        each token has a pointer to the reference object
        unclear if this is a viable long term solution. (cloneing issues?)

TODO:
    pull required transforms (lambda) out of the compiler


Fixed bugs that need tests:

        -- binop setattr store
        //self = {index: 0}
        //self.index += 1
        //return self

        -- binop subscr store
        //self = [0]
        //self[0] += 1
        //return self


"""

import ast
import dis
import types
import sys
import time
from collections import defaultdict

from .token import Token, TokenError
from .lexer import Lexer
from .parser import Parser, ParseError
from .builtins import defaultGlobals, \
    JsUndefined, JsStr, JsArray, JsObject, JsNew, \
    JsFunction, JsTypeof, JsInstanceof
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
ST_COMPILE  = 0x002  # the token has been visited, commit to the output stream
ST_LOAD     = 0x004  # compiling this token should push a value on the stack
ST_STORE    = 0x008  # compiling this token will pop an item from the stack

# states starting at 0x100 are used to count the compilation phase
# and can be reused between token types.
ST_PHASE_1 = 0x100
ST_PHASE_2 = 0x200
ST_PHASE_3 = 0x400
ST_PHASE_4 = 0x800

ST_BRANCH_TRUE = 0x100
ST_BRANCH_FALSE = 0x200

ST_WHILE = 0x100

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

class Compiler(object):

    CF_MODULE  = 1
    CF_REPL    = 2
    CF_NO_FAST = 4
    CF_USE_REF = 8

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
            Token.T_GET_ATTR: self._traverse_binary,
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
            Token.T_DOWHILE: self._traverse_dowhile,
            Token.T_OBJECT: self._traverse_object,
            Token.T_LIST: self._traverse_list,
            Token.T_NEW: self._traverse_new,
            Token.T_SUBSCR: self._traverse_subscr,
            Token.T_RETURN: self._traverse_return,
            Token.T_POSTFIX: self._traverse_postfix,
            Token.T_PREFIX: self._traverse_prefix,
            Token.T_EXPORT: self._traverse_export,
            Token.T_LOGICAL_AND: self._traverse_logical_and,
            Token.T_LOGICAL_OR: self._traverse_logical_or,
            Token.T_FOR: self._traverse_for,
            Token.T_COMMA: self._traverse_comma,
            Token.T_TERNARY: self._traverse_ternary,
            Token.T_INSTANCE_OF: self._traverse_instance_of,


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
            Token.T_BREAK: self._compile_break,
            Token.T_CONTINUE: self._compile_continue,

            # do nothing
            Token.T_EMPTY_TOKEN: lambda *args: None,
            Token.T_CLOSURE: lambda *args: None,

            # do nothing for these nodes until an implementation can be written
            Token.T_FOR_IN: lambda *args: print("T_FOR_IN not implemeted"),
            Token.T_TRY: lambda *args: print("T_TRY not implemeted"),
            Token.T_THROW: lambda *args: print("T_THROW not implemeted"),
            Token.T_TEMPLATE_STRING : lambda *args: print("T_TEMPLATE_STRING not implemeted"),
            Token.T_SWITCH : lambda *args: print("T_SWITCH not implemeted")
        }

        # compile methods produce opcodes after the token has
        # been traversed
        self.compile_mapping = {
            Token.T_BINARY: self._compile_binary,
            Token.T_GET_ATTR: self._compile_binary,
            Token.T_ASSIGN: self._compile_assign,
            Token.T_FUNCTIONCALL: self._compile_functioncall,
            Token.T_BRANCH: self._compile_branch,
            Token.T_WHILE: self._compile_while,
            Token.T_DOWHILE: self._compile_dowhile,
            Token.T_OBJECT: self._compile_object,
            Token.T_LIST: self._compile_list,
            Token.T_NEW: self._compile_new,
            Token.T_RETURN: self._compile_return,
            Token.T_SUBSCR: self._compile_subscr,
            Token.T_POSTFIX: self._compile_postfix,
            Token.T_PREFIX: self._compile_prefix,
            Token.T_LOGICAL_AND: self._compile_logical_and,
            Token.T_LOGICAL_OR: self._compile_logical_or,
            Token.T_FOR: self._compile_for,
            Token.T_TERNARY: self._compile_ternary,
            Token.T_INSTANCE_OF: self._compile_instance_of,

            Token.T_NUMBER: self._compile_literal_number,
            Token.T_STRING: self._compile_literal_string,
            Token.T_TEXT: self._compile_text,
            Token.T_LOCAL_VAR: self._compile_text,
            Token.T_GLOBAL_VAR: self._compile_text,
            Token.T_FREE_VAR: self._compile_text,
            Token.T_ATTR: self._compile_attr,
            Token.T_DELETE_VAR: self._compile_delete_var,
            Token.T_UNPACK_SEQUENCE: self._compile_unpack_sequence,

            # python specific helper methods
            'T_BUILD_TUPLE_UNPACK_WITH_CALL': self._compile_build_tuple_unpack_with_call,
            'T_BUILD_TUPLE_UNPACK': self._compile_build_tuple_unpack,
            'T_BUILD_TUPLE': self._compile_build_tuple,

            'T_BUILD_MAP_UNPACK': self._compile_build_map_unpack,
            'T_BUILD_MAP': self._compile_build_map,
        }

        self.bc = ConcreteBytecode2()
        self.bc.name = name
        self.bc.filename = filename
        self.bc.names = []
        self.bc.varnames = []
        self.bc.consts = [None]

        self.function_body = None

        self.flags = flags

        self.globals = Compiler.defaultGlobals()

        if globals:
            self.globals.update(globals)

        self.module_globals = {}

        self.break_sources = []
        self.continue_sources = []

        self.next_label = 0

    @staticmethod
    def defaultGlobals():
        return defaultGlobals();

    def execute(self):
        if self.function_body is not None:
            return self.function_body()

    def compile(self, ast):

        self.function_body = None
        #transform = TransformClassToFunction()
        #transform.transform(ast)

        #transform = TransformAssignScope()
        #if self.flags & Compiler.CF_REPL:
        #    transform.disable_warnings = True
        #transform.transform(ast)

        # TODO: this was removed because the new transform can infer this state
        #   TransformReplaceIdentity can check if the variable is Undefined
        #if self.flags & Compiler.CF_REPL:
        #    self.module_globals.update(transform.globals)

        self._compile(ast)
        self._finalize()

        stacksize = calcsize(self.bc)
        code = self.bc.to_code(stacksize)
        self.function_body = types.FunctionType(code, self.globals, self.bc.name)

    def dump(self):
        if self.function_body is not None:
            dump(self.bc)

    # -------------------------------------------------------------------------

    def _compile_sequence(self, flag, token):
        """
        sub-tree compilition is a work around for the tricky case
        of compiling function arguments -- and should be used sparingly

        """

        seq_save = self.seq

        self.seq = [(0, flag, token)]

        while self.seq:
            depth, state, token = self.seq.pop()

            if isinstance(token, BytecodeInstr):
                self.bc.append(token)
                continue

            if state & ST_COMPILE == ST_COMPILE:
                fn = self.compile_mapping.get(token.type, None)
                if fn is not None:
                    fn(depth, state, token)
                else:
                    raise CompileError(token, "token not supported for compile")
            else:
                # traverse the AST to produce a linear sequence
                fn = self.traverse_mapping.get(token.type, None)
                if fn is not None:
                    fn(depth, state, token)
                else:
                    raise CompileError(token, "token not supported for traverse")

        self.seq = seq_save

    def _compile(self, ast):
        """ non-recursive implementation of _compile

        for each node process the children in reverse order
        """

        # init the JS runtime

        # create a default 'this' so that arrow functions have something
        # to inherit

        # compile userland code

        flg = ST_TRAVERSE
        if ast.type not in (Token.T_MODULE, Token.T_GROUPING, Token.T_BLOCK):
            flg |= ST_LOAD

        # initialize the return value for REPL mode
        # not all expressions produce a value this ensures there is something
        # on the stack that can be assigned to '_'
        if self.flags & Compiler.CF_REPL:
            self.bc.append(BytecodeInstr('LOAD_CONST', 0))

        # TODO: refactor to be independant of ast type or flags
        if ast.type == Token.T_MODULE or self.flags & Compiler.CF_USE_REF:
            # this is required for top level lambda functions
            kind, index = self._token2index(JsUndefined.Token, load=True)
            self.bc.append(BytecodeInstr('LOAD_' + kind, index))
            kind, index = self._token2index(Token(Token.T_TEXT, 0, 0, 'this'), load=False)
            self.bc.append(BytecodeInstr('STORE_' + kind, index))

        self.seq = []
        self._compile_sequence(flg, ast)

        if self.flags & Compiler.CF_REPL:
            tok = Token(Token.T_GLOBAL_VAR, 0, 0, "_")
            kind, index = self._token2index(tok, load=False)
            self.bc.append(BytecodeInstr('STORE_' + kind, index))
            self.module_globals["_"] = "_"


        if not len(self.bc) or self.bc[-1].name != 'RETURN_VALUE':

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

            else:
                self.bc.append(BytecodeInstr('LOAD_CONST', 0))
                self.bc.append(BytecodeInstr('RETURN_VALUE'))

    def _finalize(self):

        retry = True
        again = False
        attempts = 0
        while retry:
            attempts += 1
            if attempts > 10:
                sys.stderr.write("compiler warning: finalize attempt %d\n" % attempts)
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

        if len(token.children) == 0:
            return

        last = token.children[-1]
        rest = token.children[:-1]

        flg = ST_LOAD if self.flags&Compiler.CF_REPL else 0
        self._push(depth + 1, ST_TRAVERSE|flg, last)
        for child in reversed(rest):
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

        # hack to fix LHS of object property
        if token.value == ':':
            if token.children[0].type == Token.T_TEXT:
                token.children[0].type = Token.T_STRING
                token.children[0].value = repr(token.children[0].value)

        self._push(depth, flag1, token.children[1])
        self._push(depth, flag0, token.children[0])

    def _traverse_assign(self, depth, state, token):
        """
        >>> def f(this):          | () => {
        ...   this.index = 0      |   this.index = 0
        ...   this.index += 1     |   this.index += 1
        ...                       | }
        >>> dis.dis(f)
          2           0 LOAD_CONST               1 (0)
                      2 LOAD_FAST                0 (this)
                      4 STORE_ATTR               0 (index)

          3           6 LOAD_FAST                0 (this)
                      8 DUP_TOP
                     10 LOAD_ATTR                0 (index)
                     12 LOAD_CONST               2 (1)
                     14 INPLACE_ADD
                     16 ROT_TWO
                     18 STORE_ATTR               0 (index)
                     20 LOAD_CONST               0 (None)
                     22 RETURN_VALUE


        >>> def f(self):          | () => {
        ...   self = [0]          |   self = [0]
        ...   self[0] += 1        |   self[0] += 1
        ...                       | }
        >>> dis.dis(f)
          2           0 LOAD_CONST               1 (0)
                      2 BUILD_LIST               1
                      4 STORE_FAST               0 (self)

          3           6 LOAD_FAST                0 (self)
                      8 LOAD_CONST               1 (0)
                     10 DUP_TOP_TWO
                     12 BINARY_SUBSCR
                     14 LOAD_CONST               2 (1)
                     16 INPLACE_ADD
                     18 ROT_THREE
                     20 STORE_SUBSCR
                     22 LOAD_CONST               0 (None)
                     24 RETURN_VALUE

        """
        if token.value == "=":
            self._push(depth, ST_TRAVERSE | ST_STORE, token.children[0])
            self._push(depth, ST_COMPILE | (state & (ST_STORE | ST_LOAD)), token)
            self._push(depth, ST_TRAVERSE | ST_LOAD, token.children[1])
        else:
            lhs, rhs = token.children

            """
            self.bc.append(BytecodeInstr(binop_store[token.value], lineno=token.line))
            if state & ST_PHASE_3:
                self.bc.append(BytecodeInstr('ROT_THREE'))
            self._push(depth, ST_COMPILE | ST_STORE, token.children[0])

            """
            if lhs.type == Token.T_GET_ATTR:
                clhs, crhs = lhs.children
                self._push(depth, ST_TRAVERSE | ST_STORE, crhs)
                self._push(depth, 0, BytecodeInstr('ROT_TWO'))
                #self._push(depth, ST_COMPILE | (state & (ST_STORE | ST_LOAD)), token)
                self._push(depth, ST_COMPILE | ST_STORE, token.children[0])
                self._push(depth, 0, BytecodeInstr(binop_store[token.value], lineno=token.line))
                self._push(depth, ST_COMPILE | ST_STORE, lhs)
                self._push(depth, ST_TRAVERSE | ST_LOAD, rhs)
                self._push(depth+1, ST_TRAVERSE | ST_LOAD, crhs)
                self._push(depth, 0, BytecodeInstr('DUP_TOP'))
                self._push(depth+1, ST_TRAVERSE | ST_LOAD, clhs)
            elif lhs.type == Token.T_SUBSCR:
                clhs, crhs = lhs.children
                #self._push(depth, ST_COMPILE | (state & (ST_STORE | ST_LOAD)) | ST_PHASE_3, token)
                self._push(depth, ST_COMPILE | ST_STORE, token.children[0])
                self._push(depth, 0, BytecodeInstr('ROT_THREE'))
                self._push(depth, 0, BytecodeInstr(binop_store[token.value], lineno=token.line))
                self._push(depth, ST_TRAVERSE | ST_LOAD, rhs)
                self._push(depth, 0, BytecodeInstr('BINARY_SUBSCR'))
                self._push(depth, 0, BytecodeInstr('DUP_TOP_TWO'))
                self._push(depth+1, ST_TRAVERSE | ST_LOAD, crhs)
                self._push(depth+1, ST_TRAVERSE | ST_LOAD, clhs)
            else:
                self._push(depth, ST_COMPILE | (state & (ST_STORE | ST_LOAD)), token)
                self._push(depth, ST_TRAVERSE | ST_LOAD, lhs)
                self._push(depth, ST_TRAVERSE | ST_LOAD, rhs)

    def _build_spread(self, type_, expr_args):

        tuple_count = 0
        count = 0
        children = []
        for child in expr_args.children:
            if child.type == Token.T_SPREAD:
                if count > 0:
                    tmp = Token(type_,0,0, str(count))
                    children.append((ST_COMPILE, tmp))
                    tuple_count += 1

                children.append((ST_TRAVERSE, child.children[0]))
                tuple_count += 1
                count = 0
            else:
                children.append((ST_TRAVERSE|ST_LOAD, child))
                count += 1
        if count > 0:
            tmp = Token(type_,0,0, str(count))
            children.append((ST_COMPILE, tmp))
            tuple_count += 1

        return tuple_count, children

    def _traverse_functioncall(self, depth, state, token):

        expr_call, expr_args = token.children
        unpack = any(child.type == Token.T_SPREAD for child in expr_args.children)

        if unpack:

            tuple_count, children = self._build_spread('T_BUILD_TUPLE', expr_args)

            tmp = Token('T_BUILD_TUPLE_UNPACK_WITH_CALL',0,0, str(tuple_count))
            self._push(depth, ST_COMPILE, tmp)

            for new_state, child in reversed(children):
                self._push(depth + 1, new_state, child)
            self._push(depth, ST_TRAVERSE|ST_LOAD, expr_call)

        else:
            self._push(depth, ST_COMPILE | (state&ST_LOAD), token)

            flag0 = ST_TRAVERSE | ST_LOAD
            self._push(depth, flag0, expr_args)
            self._push(depth, flag0, expr_call)

    def _traverse_arglist(self, depth, state, token):

        flag0 = ST_TRAVERSE | ST_LOAD
        for child in reversed(token.children):
            self._push(depth, flag0, child)

    def _traverse_block(self, depth, state, token):

        flag0 = ST_TRAVERSE #| ST_LOAD
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
        # this test used to be performed in the scope transform
        if arglist.type == Token.T_TEXT:
            arglist = Token(Token.T_ARGLIST, arglist.line, arglist.index, '()', [arglist])

        block = token.children[2]
        # this test used to be performed in the scope transform
        if block.type != Token.T_BLOCK:
            block = Token(Token.T_BLOCK, block.line, block.index, '{}',
                [Token(Token.T_RETURN, block.line, block.index, 'return', [block])])

        closure = token.children[3]

        self._build_function(state, token, name, arglist, block, closure)

    def _traverse_function(self, depth, state, token):

        name = token.children[0]
        arglist = token.children[1]
        block = token.children[2]
        closure = token.children[3]

        self._build_function(state|ST_LOAD, token, name, arglist, block, closure, autobind=False)

        kind, index = self._token2index(name, False)
        self.bc.append(BytecodeInstr('STORE_' + kind, index, lineno=token.line))

        if state&ST_LOAD:
            self.bc.append(BytecodeInstr('LOAD_CONST', 0))

    def _traverse_anonymous_function(self, depth, state, token):

        name = token.children[0]
        name.value = 'Anonymous_%d_%d_%d' % (
                token.line, token.index, depth)

        arglist = token.children[1]
        block = token.children[2]
        closure = token.children[3]

        self._build_function(state, token, name, arglist, block, closure, autobind=False)

    def _build_function(self, state, token, name, arglist, block, closure, autobind=True):
        """ Create a new function

        Use a new Compiler to compile the function. the name and code
        object are stored as constants inside the current scope

        All Javascript AST nodes for a function call have the same form

            T_FUNCTION
                T_TEXT<name>
                T_ARGLIST<name>
                T_BLOCK<name>
                T_CLOSURE<name>

        All Javascript functions have the same python function signature
            - all arguments are positional arguments with default values
              the default value is undefined if not specified
            - any number of arguments can be passed and extra arguments
              are collected into a magic variable
            - the 'this' variable is implemented as a keyword only argument
              and is inaccessible from the javascript code definition
            - the spread operator can be used to denote the last argument
              should collect all extra positional arguments. this will
              then replace the default magic argument


        Given:
            function f(arg0) {}

        Produce:

            def f(arg0=undefined, *_x_daedalus_js_args, this=undefined)

        In order to implement function binding ever Javascript Function is
        wrapped by a JsFunction instance which will automatically pass in
        the correct instance for 'this' when the function is called

        arrow functions automatically bind to the 'this' in the current scope

        anonymous functions automatically bind to undefined, and must
        be manually bound by the user

        constructors must have 'this' passed in -- which is implement in JsNew

        """
        flags = 0
        sub = Compiler(self.bc.name + '.' + name.value, self.bc.filename, flags)

        pos_kwarg_count = 0

        kind, index = self._token2index(JsFunction.Token, True)
        self.bc.append(BytecodeInstr('LOAD_' + kind, index, lineno=token.line))

        # get user defined positional arguments
        rest_name = "_x_daedalus_js_args"
        arglabels = []
        argdefaults = []
        vartypes= (Token.T_LOCAL_VAR, Token.T_GLOBAL_VAR, Token.T_FREE_VAR)
        if arglist.type in vartypes:
            arglabels.append(arglist.value)
            argdefaults.append(None)
        else:
            for arg in arglist.children:
                if arg.type in vartypes:
                    arglabels.append(arg.value)
                    argdefaults.append(None)
                elif arg.type == Token.T_SPREAD:
                    rest_name = arg.children[0].value
                elif arg.type == Token.T_ASSIGN:
                    lhs = arg.children[0]
                    if lhs.type in vartypes:
                        arglabels.append(arg.children[0].value)
                        argdefaults.append(arg.children[1])
                    else:
                        raise CompileError(arg, "invalid argument")
                else:
                    raise CompileError(arg, "unexpected argument")

        argcount = len(arglabels)

        # set the default value of user defined arguments to be JS `undefined`
        undef_kind, undef_index = self._token2index(JsUndefined.Token, True)

        for arglabel, argdefault in zip(arglabels, argdefaults):

            if argdefault is None:
                self.bc.append(BytecodeInstr('LOAD_' + undef_kind, undef_index, lineno=token.line))
            else:
                self._compile_sequence(ST_LOAD, argdefault)

            sub.bc.varnames.append(arglabel)

        # add 'this' as an optional keyword argument defaulting to 'undefined'
        # add '_x_daedalus_js_args' to collect all extra positional arguments
        # if the function is called with too many arguments they get dumped
        # into the magic variable.

        sub.bc.flags |= CO_VARARGS
        sub.bc.varnames.append("this")
        sub.bc.varnames.append(rest_name)
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

        # when the user supplies a rest parameter use that name
        # and convert the default python tuple into a javascript array
        if rest_name != "_x_daedalus_js_args":
            rest_node = Token(Token.T_ASSIGN, 1, 0, '=', [
                Token(Token.T_LOCAL_VAR, 1, 0, rest_name),
                Token(Token.T_FUNCTIONCALL, 1, 0, "", [
                    JsArray.Token,
                    Token(Token.T_ARGLIST, 1, 0, "()", [
                        Token(Token.T_LOCAL_VAR, 1, 0, rest_name),
                    ])
                ])
            ])

            if block.type == Token.T_BLOCK:
                block.children.insert(0, rest_node)
            else:
                raise CompileError(block, "unexpected function body type when using a spread argument")

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

        self.bc.append(BytecodeInstr('CALL_FUNCTION', argcount, lineno=token.line))

        if state&ST_LOAD == 0:
            self.bc.append(BytecodeInstr('POP_TOP'))

    def _traverse_grouping(self, depth, state, token):
        flag0 = ST_TRAVERSE | state&(ST_LOAD|ST_STORE)
        for child in reversed(token.children):
            self._push(depth + 1, flag0, child)

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
        token.continue_target = nop

        self.break_sources.append([])
        self.continue_sources.append([])

        expr_test, expr_block = token.children
        self._push(depth, ST_COMPILE | ST_WHILE, token)
        self._push(depth + 1, ST_TRAVERSE | ST_LOAD, expr_test)

    def _traverse_dowhile(self, depth, state, token):

        token.label_begin = self._make_label()

        nop = BytecodeInstr('NOP')
        self.bc.append(nop)
        nop.add_label(token.label_begin)
        token.continue_target = nop

        self.break_sources.append([])
        self.continue_sources.append([])

        expr_block, expr_test = token.children
        self._push(depth, ST_COMPILE, token)
        self._push(depth + 1, ST_TRAVERSE | ST_LOAD, expr_test)
        self._push(depth + 1, ST_TRAVERSE, expr_block)

    def _traverse_object(self, depth, state, token):

        unpack = any(child.type == Token.T_SPREAD for child in token.children)

        if unpack:

            tuple_count, children = self._build_spread('T_BUILD_MAP', token)

            kind, index = self._token2index(JsObject.Token, True)
            self.bc.append(BytecodeInstr('LOAD_' + kind, index))

            token = Token('T_BUILD_MAP_UNPACK',0,0, str(tuple_count))
            self._push(depth, ST_COMPILE, token)

            for new_state, child in reversed(children):
                self._push(depth + 1, new_state, child)

        else:
            kind, index = self._token2index(JsObject.Token, True)
            self.bc.append(BytecodeInstr('LOAD_' + kind, index, lineno=token.line))

            self._push(depth, ST_COMPILE, token)
            for child in reversed(token.children):
                self._push(depth + 1, ST_TRAVERSE | ST_LOAD, child)

    def _traverse_list(self, depth, state, token):

        unpack = any(child.type == Token.T_SPREAD for child in token.children)

        if unpack:

            tuple_count, children = self._build_spread('T_BUILD_TUPLE', token)

            kind, index = self._token2index(JsArray.Token, True)
            self.bc.append(BytecodeInstr('LOAD_' + kind, index))

            tmp = Token('T_BUILD_TUPLE_UNPACK',0,0, str(tuple_count))
            self._push(depth, ST_COMPILE, tmp)

            for new_state, child in reversed(children):
                self._push(depth + 1, new_state, child)
        else:

            kind, index = self._token2index(JsArray.Token, True)
            self.bc.append(BytecodeInstr('LOAD_' + kind, index, lineno=token.line))

            self._push(depth, ST_COMPILE, token)
            for child in reversed(token.children):
                self._push(depth + 1, ST_TRAVERSE | ST_LOAD, child)

    def _traverse_new(self, depth, state, token):

        kind, index = self._token2index(JsNew.Token, True)
        self.bc.append(BytecodeInstr('LOAD_' + kind, index, lineno=token.line))

        child = token.children[0]
        self._push(depth, ST_COMPILE | (state&ST_LOAD), token)

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

        # TODO: this can be done better to minimize side effects
        #      x[n++]++  :: increments n twice

        self._push(depth + 1, ST_TRAVERSE | ST_STORE, token.children[0])
        self._push(depth, ST_COMPILE| (state&ST_LOAD), token)
        self._push(depth + 1, ST_TRAVERSE | ST_LOAD, token.children[0])

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

        self._push(depth + 1, ST_TRAVERSE | ST_STORE, token.children[0])
        self._push(depth, ST_COMPILE|(state&ST_LOAD), token)
        self._push(depth + 1, ST_TRAVERSE | ST_LOAD, token.children[0])
        if token.value == 'typeof':
            kind, index = self._token2index(JsTypeof.Token, load=True)
            self.bc.append(BytecodeInstr('LOAD_' + kind, index))

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

        for child in token.children[1:]:
            self.module_globals[token.value] = child.value

        self._push(depth + 1, ST_TRAVERSE, token.children[0])

    def _traverse_var(self, depth, state, token):
        """assume that variables have been taken care of by now
        by the various transform functions

        allow:
            let x;  -- declare a variable and set undefined
            let x=<>; -- declare a variable and initialize to <>


        """
        for child in reversed(token.children):

            if child.type != Token.T_ASSIGN:
                kind, index = self._token2index(JsUndefined.Token, load=True)
                self.bc.append(BytecodeInstr('LOAD_' + kind, index))
                kind, index = self._token2index(child, load=False)
                self.bc.append(BytecodeInstr('STORE_' + kind, index))
            else:
                self._push(depth + 1, ST_TRAVERSE, child)

    def _traverse_logical_and(self, depth, state, token):

        self._push(depth + 1, ST_COMPILE | ST_PHASE_2, token)
        self._push(depth + 1, ST_TRAVERSE | ST_LOAD, token.children[1])
        self._push(depth + 1, ST_COMPILE | ST_PHASE_1, token)
        self._push(depth + 1, ST_TRAVERSE | ST_LOAD, token.children[0])

    def _traverse_logical_or(self, depth, state, token):

        self._push(depth + 1, ST_COMPILE | ST_PHASE_2, token)
        self._push(depth + 1, ST_TRAVERSE | ST_LOAD, token.children[1])
        self._push(depth + 1, ST_COMPILE | ST_PHASE_1, token)
        self._push(depth + 1, ST_TRAVERSE | ST_LOAD, token.children[0])

    def _traverse_for(self, depth, state, token):

        arglist = token.children[0]

        token.label_begin = self._make_label()
        token.label_end = self._make_label()

        self.break_sources.append([])
        self.continue_sources.append([])

        self._push(depth, ST_COMPILE | ST_PHASE_1, token)
        self._push(depth, ST_TRAVERSE, arglist.children[0])

    def _traverse_comma(self, depth, state, token):
        """
        let x=1, y=2
        """
        for child in reversed(token.children):
            self._push(depth + 1, ST_TRAVERSE, child)

    def _traverse_ternary(self, depth, state, token):

        # in reverse:
        # 1. load the test expression,
        # 2. insert jump
        # 3. load the true condition
        # 4. insert jump
        # 5. load the false condition
        # 6. insert a jump target

        self._push(depth + 1, ST_COMPILE | ST_PHASE_3, token)
        self._push(depth + 1, ST_TRAVERSE | ST_LOAD, token.children[2])
        self._push(depth + 1, ST_COMPILE | ST_PHASE_2, token)
        self._push(depth + 1, ST_TRAVERSE | ST_LOAD, token.children[1])
        self._push(depth + 1, ST_COMPILE | ST_PHASE_1, token)
        self._push(depth + 1, ST_TRAVERSE | ST_LOAD, token.children[0])

    def _traverse_instance_of(self, depth, state, token):

        self._push(depth + 1, ST_COMPILE, token)
        for child in reversed(token.children):
            self._push(depth + 1, ST_TRAVERSE, child)
        kind, index = self._token2index(JsInstanceof.Token, load=True)
        self.bc.append(BytecodeInstr('LOAD_' + kind, index))

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

        if token.value == '=':
            if state&ST_LOAD:
                self.bc.append(BytecodeInstr('DUP_TOP'))

        if token.value in binop_store:
            self.bc.append(BytecodeInstr(binop_store[token.value], lineno=token.line))
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

        if state & ST_LOAD == 0:
            self.bc.append(BytecodeInstr("POP_TOP"))

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
            expr_test, expr_block = token.children

            token.label_false = self._make_label()
            instr = BytecodeJumpInstr('POP_JUMP_IF_FALSE', token.label_end)
            self.bc.append(instr)

            self._push(depth, ST_COMPILE, token)
            self._push(depth, ST_TRAVERSE, expr_block)

        else:
            self.bc.append(BytecodeJumpInstr('JUMP_ABSOLUTE', token.label_begin))

            nop = BytecodeInstr('NOP')
            self.bc.append(nop)
            nop.add_label(token.label_end)

            token.break_target = nop
            self._finalize_break_continue(token)

    def _compile_dowhile(self, depth, state, token):

        self.bc.append(BytecodeJumpInstr('POP_JUMP_IF_TRUE', token.label_begin))

        nop = BytecodeInstr("NOP")
        self.bc.append(nop)
        token.break_target = nop

        self._finalize_break_continue(token)

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
            N += len(child.children[1].children)
        # TODO: pop top if state&ST_LOAD is false
        self.bc.append(BytecodeInstr('CALL_FUNCTION', N))

        if state & ST_LOAD == 0:
            self.bc.append(BytecodeInstr("POP_TOP"))

    def _compile_return(self, depth, state, token):

        self.bc.append(BytecodeInstr('RETURN_VALUE'))

    def _compile_subscr(self, depth, state, token):
        opcode = "BINARY_SUBSCR" if state & ST_LOAD else "STORE_SUBSCR"
        self.bc.append(BytecodeInstr(opcode, lineno=token.line))

    def _compile_keyword(self, depth, state, token):

        if token.value in ['this', 'null', 'false', 'true', 'super']:
            return self._compile_text(depth, state, token)
        else:
            raise CompileError(token, "Unsupported keyword")

    def _compile_delete_var(self, depth, state, token):
        # TODO: not implemented
        pass

    def _compile_postfix(self, depth, state, token):

        unop2 = {
            "++": "BINARY_ADD",
            "--": "BINARY_SUBTRACT"
        }

        valuetok = Token(Token.T_NUMBER, 0, 0, "1")
        kind, index = self._token2index(valuetok, True)
        if state&ST_LOAD:
            self.bc.append(BytecodeInstr('DUP_TOP'))
        self.bc.append(BytecodeInstr('LOAD_' + kind, index))
        self.bc.append(BytecodeInstr(unop2[token.value]))

    def _compile_prefix(self, depth, state, token):

        if token.value == 'typeof':
            self.bc.append(BytecodeInstr('CALL_FUNCTION', 1))
        else:
            unop1 = {
                "+": "UNARY_POSITIVE",
                "-": "UNARY_NEGATIVE",
                "!": "UNARY_NOT",
                "~": "UNARY_INVERT",
            }
            unop2 = {
                "++": "BINARY_ADD",
                "--": "BINARY_SUBTRACT"
            }

            if token.value in unop1:
                if state&ST_LOAD:
                    self.bc.append(BytecodeInstr('DUP_TOP'))
                self.bc.append(BytecodeInstr(unop1[token.value]))
            elif token.value in unop2:
                valuetok = Token(Token.T_NUMBER, 0, 0, "1")
                kind, index = self._token2index(valuetok, True)
                self.bc.append(BytecodeInstr('LOAD_' + kind, index))
                self.bc.append(BytecodeInstr(unop2[token.value]))
                if state&ST_LOAD:
                    self.bc.append(BytecodeInstr('DUP_TOP'))
            else:
                raise CompileError(token, "not supported")

    def _compile_logical_and(self, depth, state, token):

        if state&ST_PHASE_1:
            token.label = self._make_label()
            self.bc.append(BytecodeJumpInstr('JUMP_IF_FALSE_OR_POP', token.label))
        if state&ST_PHASE_2:
            nop = BytecodeInstr('NOP')
            nop.add_label(token.label)
            self.bc.append(nop)

    def _compile_logical_or(self, depth, state, token):

        if state&ST_PHASE_1:
            token.label = self._make_label()
            self.bc.append(BytecodeJumpInstr('JUMP_IF_TRUE_OR_POP', token.label))
        if state&ST_PHASE_2:
            nop = BytecodeInstr('NOP')
            nop.add_label(token.label)
            self.bc.append(nop)

    def _compile_for(self, depth, state, token):

        body =  token.children[1]
        arglist = token.children[0]

        if state & ST_PHASE_1:
            nop = BytecodeInstr('NOP')
            nop.add_label(token.label_begin)
            self.bc.append(nop)

            #token.continue_target = nop

            self._push(depth, ST_COMPILE | ST_PHASE_2, token)
            self._push(depth, ST_TRAVERSE, arglist.children[1])

        elif state & ST_PHASE_2:

            instr = BytecodeJumpInstr('POP_JUMP_IF_FALSE', token.label_end)
            self.bc.append(instr)

            self._push(depth, ST_COMPILE | ST_PHASE_3, token)
            self._push(depth, ST_TRAVERSE, body)

        elif state & ST_PHASE_3:

            nop = BytecodeInstr('NOP')
            self.bc.append(nop)

            token.continue_target = nop
            self._push(depth, ST_COMPILE | ST_PHASE_4, token)
            self._push(depth, ST_TRAVERSE, arglist.children[2])

        elif state & ST_PHASE_4:

            self.bc.append(BytecodeJumpInstr('JUMP_ABSOLUTE', token.label_begin))

            nop = BytecodeInstr('NOP')
            self.bc.append(nop)

            nop.add_label(token.label_end)

            token.break_target = nop

            self._finalize_break_continue(token)


    def _compile_ternary(self, depth, state, token):

        if state&ST_PHASE_1:
            token.label = self._make_label()
            self.bc.append(BytecodeJumpInstr('JUMP_IF_FALSE_OR_POP', token.label))
        elif state&ST_PHASE_2:
            self.bc.append(BytecodeJumpInstr('JUMP_ABSOLUTE', token.label))
        elif state&ST_PHASE_3:
            nop = BytecodeInstr('NOP')
            nop.add_label(token.label)
            self.bc.append(nop)

    def _compile_instance_of(self, depth, state, token):

        self.bc.append(BytecodeInstr('CALL_FUNCTION', 2))

    def _compile_build_tuple_unpack_with_call(self, depth, state, token):

        self.bc.append(BytecodeInstr('BUILD_TUPLE_UNPACK_WITH_CALL', int(token.value)))
        self.bc.append(BytecodeInstr('CALL_FUNCTION_EX', 0))

    def _compile_build_tuple_unpack(self, depth, state, token):

        self.bc.append(BytecodeInstr('BUILD_TUPLE_UNPACK', int(token.value)))
        self.bc.append(BytecodeInstr('CALL_FUNCTION', 1))

    def _compile_build_tuple(self, depth, state, token):

        self.bc.append(BytecodeInstr('BUILD_TUPLE', int(token.value)))

    def _compile_build_map_unpack(self, depth, state, token):

        self.bc.append(BytecodeInstr('BUILD_MAP_UNPACK', int(token.value)))
        self.bc.append(BytecodeInstr('CALL_FUNCTION', 1))

    def _compile_build_map(self, depth, state, token):

        self.bc.append(BytecodeInstr('BUILD_MAP', int(token.value)))

    def _compile_break(self, depth, state, token):
        tgt = self._make_label()
        self.bc.append(BytecodeJumpInstr('JUMP_ABSOLUTE', tgt))
        self.break_sources[-1].append(tgt)

    def _compile_continue(self, depth, state, token):
        tgt = self._make_label()
        self.bc.append(BytecodeJumpInstr('JUMP_ABSOLUTE', tgt))
        self.continue_sources[-1].append(tgt)

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

            name = tok.value
            #if self.flags&Compiler.CF_USE_REF and tok.ref:
            #    name = tok.ref.name

            if tok.value in self.bc.cellvars:
                index = self.bc.cellvars.index(name)
                #index = self.bc.cellvars.index(tok.value)
                return 'DEREF', index

            try:
                index = self.bc.varnames.index(name)
                #index = self.bc.varnames.index(tok.value)
                return 'FAST', index
            except ValueError:
                pass

            index = len(self.bc.varnames)
            self.bc.varnames.append(name)
            #self.bc.varnames.append(tok.value)
            return 'FAST', index

        elif tok.type == Token.T_GLOBAL_VAR:
            name = tok.value

            try:

                index = self.bc.names.index(name)
                #index = self.bc.names.index(tok.value)
                return 'GLOBAL', index
            except ValueError:
                pass

            index = len(self.bc.names)
            #self.bc.names.append(tok.value)
            self.bc.names.append(name)
            return 'GLOBAL', index

        elif tok.type == Token.T_FREE_VAR:

            name = tok.value
            #if self.flags&Compiler.CF_USE_REF and tok.ref:
            #    name = tok.ref.name

            if tok.value in self.bc.freevars:
                index = len(self.bc.cellvars) + self.bc.freevars.index(name)
                return "DEREF", index

            if tok.value in self.bc.cellvars:
                index = self.bc.cellvars.index(name)
                return "DEREF", index

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

        print(self.bc.freevars)
        print(self.bc.cellvars)
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

        use_spread = any(child.type == Token.T_SPREAD for child in token.children)

        # unpack the rest parameter and convert the python tuple into a js array
        if use_spread:
            kind, index = self._token2index(JsArray.Token, True)
            self.bc.append(BytecodeInstr('LOAD_' + kind, index))
            self.bc.append(BytecodeInstr('ROT_TWO', lineno=token.line))
            self.bc.append(BytecodeInstr('UNPACK_EX', len(token.children)-1, lineno=token.line))

        else:
            self.bc.append(BytecodeInstr('UNPACK_SEQUENCE', len(token.children), lineno=token.line))

        finished = False
        for child in token.children:
            if child.type == Token.T_SPREAD:
                child = child.children[0]
                kind, index = self._token2index(child, False)
                self.bc.append(BytecodeInstr('CALL_FUNCTION', 1, lineno=token.line))
                self.bc.append(BytecodeInstr('STORE_' + kind, index, lineno=token.line))

                finished = True
            else:
                if finished:
                    raise CompileError(child, "variable after rest parameter in sequence unpack")
                kind, index = self._token2index(child, False)
                self.bc.append(BytecodeInstr('STORE_' + kind, index, lineno=token.line))

    def _finalize_break_continue(self, token):
        sources = self.break_sources.pop()
        for lbl in sources:
            token.break_target.add_label(lbl)

        sources = self.continue_sources.pop()
        for lbl in sources:
            token.continue_target.add_label(lbl)

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
            function Shape() {
                this.width = 5;
                this.height = 10;
                this.area = () => this.width * this.height
            }
            console.log(">>>")
            const s = new Shape()
            console.log(">>>")
            //return s.area()
    """

    text1 = """
        x = () => {}
        return x()
    """

    from daedalus.transform import TransformIdentityScope


    tokens = Lexer().lex(text1)
    parser = Parser()
    parser.python = True
    ast = parser.parse(tokens)

    #xform = TransformMinifyScope()
    xform = TransformIdentityScope()
    xform.disable_warnings=True
    xform.transform(ast)

    print(ast.toString(3))

    #interp = Compiler(flags=Compiler.CF_REPL)
    interp = Compiler()

    try:
        interp.compile(ast)

    except Exception as e:
        logging.exception(str(e))
        return
    finally:
        print(ast.toString(3))

    interp.dump()

    result = interp.function_body()
    print(result)
    print(type(result))

if __name__ == '__main__':  # pragma: no cover
    main()
