#! cd .. && python -m daedalus.vm

"""

TODO: transformations:
    - instance_of
    - super
    - anything that constructs a Token() in the compiler

TODO: update assignments and destructuring assignments must be transformed

    example:
        f()[0] +=1
    rewrite so that f() is called once and the result is placed on TOS
    then duplicate the TOS so that get_subscr followed by set_subscr
    can be used.

        TOS = f()
        DUP
        GET SUBSCR TOS
        LOAD RHS
        BINARY ADD
        SET SUBSCR TOS2 TOS1  // may require a rotate 2

    This may result in an AST that cannot be formatted as valid javascript

    example:
        {a, b} = f()
    rewrite into a more verbose form
        tos = f() // duplicate N times
        a = TOS.a
        b = TOS.b

    example:
        {a, b, ...rest} = {a:0, b:0, c:0, d:0,}

        TOS = {a:0, b:0, c:0, d:0,}
        TOS = shallow copy TOS      // prevent mutating original RHS value
        DUP
        a = TOS.a
        DUP
        delete TOS.a
        DUP
        b = TOS.b
        DUP
        delete TOS.b
        rest = TOS

    This may result in an AST that cannot be formatted as valid javascript


"""
import os
import io
import struct
import ctypes
import binascii
import operator
import ast as pyast
import math
import random
import re
import time

from . import vm_opcodes as opcodes

from .token import Token, TokenError
from .lexer import Lexer
from .parser import Parser, ParseError
from .transform import TransformBaseV2, TransformIdentityScope

class VmInstruction(object):
    __slots__ = ['opcode', 'args', 'target', 'line', 'index']

    def __init__(self, opcode, *args, target=None, token=None):
        super(VmInstruction, self).__init__()
        self.opcode = opcode
        self.args = args
        self.target = target

        if token is not None:
            self.line = token.line
            self.index = token.index
        else:
            self.line = 0
            self.index = 0

    def __repr__(self):
        if self.args:
            s = " " + " ".join([str(arg) for arg in self.args])
        else:
            s = ""
        if self.target is not None:
            s += ": %d" % target
        return "(%s%s)" % (self.opcode, s)

    def getArgString(self, globals, local_names, cell_names):

        if self.opcode in (opcodes.globalvar.GET, opcodes.globalvar.SET, opcodes.globalvar.DELETE):
            idx = self.args[0]
            extra = str(idx) +":" + globals.names[idx]
        elif self.opcode in (opcodes.localvar.GET, opcodes.localvar.SET, opcodes.localvar.DELETE):
            idx = self.args[0]
            extra = str(idx) +":" + local_names[idx]
        elif self.opcode in (opcodes.cellvar.GET, opcodes.cellvar.SET, opcodes.cellvar.DELETE, opcodes.cellvar.LOAD):
            idx = self.args[0]
            extra = str(idx) +":" + cell_names[idx]
        elif self.opcode in (opcodes.obj.GET_ATTR, opcodes.obj.SET_ATTR, opcodes.obj.DEL_ATTR):
            idx = self.args[0]
            extra = str(idx) +":" + local_names[idx]
        elif self.opcode == opcodes.const.STRING:
            idx = self.args[0]
            arg0 = globals.constdata[idx]
            extra = "%d:%s" % (self.args[0], arg0)
        else:
            extra = " ".join([str(arg) for arg in self.args])

        return extra

class VmCompileError(TokenError):
    pass

binop = {
    "+":  opcodes.math.ADD,
    "-":  opcodes.math.SUB,
    "*":  opcodes.math.MUL,
    "/":  opcodes.math.DIV,
    "%":  opcodes.math.REM,
    "**": opcodes.math.EXP,
    "<<": opcodes.math.SHIFTL,
    ">>": opcodes.math.SHIFTR,
    "&":  opcodes.math.BITWISE_AND,
    "^":  opcodes.math.BITWISE_XOR,
    "|":  opcodes.math.BITWISE_OR,

    "<":   opcodes.comp.LT,
    "<=":  opcodes.comp.LE,
    "==":  opcodes.comp.EQ,
    "!=":  opcodes.comp.NE,
    ">=":  opcodes.comp.GE,
    ">":   opcodes.comp.GT,
    "===": opcodes.comp.TEQ,
    "!==": opcodes.comp.TNE,
}

binop_store = {
    "+=":  opcodes.math.ADD,
    "-=":  opcodes.math.SUB,
    "*=":  opcodes.math.MUL,
    "/=":  opcodes.math.DIV,
    "%=":  opcodes.math.REM,
    "**=": opcodes.math.EXP,
    "<<=": opcodes.math.SHIFTL,
    ">>=": opcodes.math.SHIFTR,
    "&=":  opcodes.math.BITWISE_AND,
    "^=":  opcodes.math.BITWISE_XOR,
    "|=":  opcodes.math.BITWISE_OR,
}

class VmGlobals(object):
    def __init__(self):
        super(VmGlobals, self).__init__()
        self.names = []
        self.values = {}
        self.constdata = []

class VmFunctionDef(object):
    def __init__(self, ast, globals):
        super(VmFunctionDef, self).__init__()
        self.ast =ast
        self.instrs = []
        self.globals = globals
        self.local_names = []
        self.cell_names = []
        self.free_names = []
        self.arglabels = []
        self.rest_name = None
        self._name = "__main__"

class JsFunction(object):
    def __init__(self, module, fndef, args, kwargs, bind_target):
        super(JsFunction, self).__init__()
        self.module = module
        self.fndef = fndef
        self.args = args
        self.kwargs = kwargs
        self.bind_target = bind_target
        self.cells = None

        self.prototype = JsObject()

    def __repr__(self):

        return "<JsFunction(%s)>" % (",".join(self.fndef.arglabels))

    def bind(self, target):

        fn = JsFunction(self.module, self.fndef, self.args, self.kwargs, target)
        fn.cells = self.cells # TODO this seems like a hack
        return fn

class VmModule(object):
    def __init__(self):
        super(VmModule, self).__init__()
        self.path = None
        self.globals = None
        self.functions = []
        self.includes = []

    def dump(self):

        for idx, fn in enumerate(self.functions):

            print("--- %3d ---" % idx)
            print("globals:", " ".join(fn.globals.names))
            print("locals :", " ".join(fn.local_names))
            print("cell   :", " ".join(fn.cell_names))
            print("args   :", " ".join(fn.arglabels), fn.rest_name)
            print("const  :", " ".join([str(x) for x in fn.globals.constdata]))


            for idx, instr in enumerate(fn.instrs):
                extra = instr.getArgString(self.globals, fn.local_names, fn.cell_names)
                print("%4d %s %s" % (idx, instr.opcode, extra))

        print("---")

class VmReference(object):

    def __init__(self, name, value):
        super(VmReference, self).__init__()
        self.name = name
        self.value = value

class VmTransform(TransformBaseV2):

    def visit(self, parent, token, index):

        if token.type == Token.T_TEMPLATE_STRING:
            self._visit_template_string(parent, token, index)

        if token.type == Token.T_REGEX:
            self._visit_regex(parent, token, index)

        if token.type == Token.T_CLASS:
            self._visit_class(parent, token, index)

        if token.type == Token.T_INSTANCE_OF:
            self._visit_instance_of(parent, token, index)

        if token.type == Token.T_KEYWORD and token.value == "super":
            token.type = Token.T_LOCAL_VAR

        if token.type == Token.T_KEYWORD and token.value == "finally":
            token.type = Token.T_ATTR

    def _visit_template_string(self, parent, token, index):

        node = None
        for child in reversed(token.children):

            if child.type == Token.T_STRING:
                child = Token(Token.T_STRING, child.line, child.index, repr(child.value))

            if child.type == Token.T_TEMPLATE_EXPRESSION:
                child = Token(Token.T_ARGLIST, child.line, child.index, "()", child.children)

            if node is None:
                node = child

            else:
                node = Token(Token.T_BINARY, token.line, token.index, "+", [child, node])

        if len(token.children) > 0 and token.children[0].type == Token.T_TEMPLATE_EXPRESSION:

            temp = Token(Token.T_STRING, token.line, token.index, "''")
            node = Token(Token.T_BINARY, token.line, token.index, "+", [temp, node])

        parent.children[index] = node

    def _visit_regex(self, parent, token, index):

        expr, flag = token.value[1:].rsplit('/', 1)
        expr = repr(expr)
        flag = repr(flag)

        _regex = Token(Token.T_GLOBAL_VAR, token.line, token.index, 'RegExp')
        _expr = Token(Token.T_STRING, token.line, token.index, expr)
        _flag = Token(Token.T_STRING, token.line, token.index, flag)
        _arglist = Token(Token.T_ARGLIST, token.line, token.index, '()', [_expr, _flag])
        _call = Token(Token.T_FUNCTIONCALL, token.line, token.index, '', [_regex, _arglist])

        _new = Token(Token.T_NEW, token.line, token.index, 'new', [_call])
        parent.children[index] = _new

    def _visit_class(self, parent, token, index):


        name = token.children[0]
        parent_class = token.children[1]
        block1 = token.children[2]
        closure1 = token.children[3]

        constructor = None
        methods = []
        for meth in block1.children:

            if meth.children[0].value == "constructor":
                constructor = meth
            else:
                meth = meth.clone()
                meth.type = Token.T_LAMBDA

                #T_ASSIGN<6,23,'='>
                #T_GET_ATTR<6,20,'.'>
                #T_KEYWORD<6,16,'this'>
                #T_ATTR<6,21,'x'>
                _this = Token(Token.T_KEYWORD, token.line, token.index, "this")
                _attr = Token(Token.T_ATTR, token.line, token.index, meth.children[0].value)
                _getattr = Token(Token.T_GET_ATTR, token.line, token.index, ".", [_this, _attr])
                _assign = Token(Token.T_ASSIGN, token.line, token.index, "=", [_getattr, meth])
                methods.append(_assign)

        if constructor is not None:
            methods.extend(constructor.children[2].children)

        _this = Token(Token.T_KEYWORD, token.line, token.index, "this")
        _return = Token(Token.T_RETURN, token.line, token.index, "return", [_this])
        methods.append(_return)

        if parent_class.children:
        # if False:
            parent_class_name = parent_class.children[0].value

            _parent = Token(name.type, token.line, token.index, parent_class_name)
            _bind = Token(Token.T_ATTR, token.line, token.index, "bind")
            _this = Token(Token.T_KEYWORD, token.line, token.index, "this")
            _getattr = Token(Token.T_GET_ATTR, token.line, token.index, ".", [_parent, _bind])

            _arglist = Token(Token.T_ARGLIST, token.line, token.index, "()", [_this])
            _fncall = Token(Token.T_FUNCTIONCALL, token.line, token.index, "", [_getattr, _arglist])
            _super = Token(Token.T_LOCAL_VAR, token.line, token.index, "super")
            _assign = Token(Token.T_ASSIGN, token.line, token.index, "=", [_super, _fncall])

            # _super = Token("T_CREATE_SUPER", token.line, token.index, "super", [_parent, _this])
            methods.insert(0, _assign)

        # TODO: copy dict from PARENT_CLASS.prototype
        #       then update using CLASS.prototype
        #       -- may require a special python function
        _this = Token(Token.T_KEYWORD, token.line, token.index, "this")
        _proto = Token(Token.T_ATTR, token.line, token.index, "prototype")
        _getattr = Token(Token.T_GET_ATTR, token.line, token.index, ".", [_this, _proto])
        _object = Token(Token.T_OBJECT, token.line, token.index, "{}")
        _assign = Token(Token.T_ASSIGN, token.line, token.index, "=", [_getattr, _object])
        methods.insert(0, _assign)

        if constructor is None:

            _name = Token(Token.T_TEXT, token.line, token.index, 'constructor', [])
            _arglist = Token(Token.T_ARGLIST, token.line, token.index, '()', [])
            _block = Token(Token.T_BLOCK, token.line, token.index, '{}', [])
            _closure = Token(Token.T_CLOSURE, token.line, token.index, '', [])
            _meth = Token(Token.T_METHOD, token.line, token.index, '', [_name,_arglist, _block, _closure])

            constructor = _meth
        else:

            constructor = constructor.clone()

        constructor.children[2].children = methods

        constructor.type = Token.T_FUNCTION
        constructor.children[0] = name

        parent.children[index] = constructor

    def _visit_instance_of(self, parent, token, index):

        lhs, rhs = token.children
        _name = Token(Token.T_GLOBAL_VAR, token.line, token.index, '_x_daedalus_js_instance_of')
        _arglist = Token(Token.T_ARGLIST, token.line, token.index, '()', [lhs, rhs])
        _call = Token(Token.T_FUNCTIONCALL, token.line, token.index, '', [_name, _arglist])

        parent.children[index] = _call

    def _visit_super(self, parent, token, index):

        token.type = Token.T_LOCAL_VAR

class VmCompiler(object):

    C_INSTRUCTION = 0x01
    C_LOOP_END    = 0x02
    C_VISIT       = 0x04

    C_STORE       = 0x10
    C_LOAD        = 0x20
    C_LOAD_STORE  = 0x30

    def __init__(self):
        super(VmCompiler, self).__init__()

        self.visit_actions = {
            Token.T_VAR: self._visit_var,
            Token.T_MODULE: self._visit_module,
            Token.T_ASSIGN: self._visit_assign,
            Token.T_TEXT: self._visit_text,
            Token.T_GLOBAL_VAR: self._visit_text,
            Token.T_LOCAL_VAR: self._visit_text,
            Token.T_NUMBER: self._visit_number,
            Token.T_BINARY: self._visit_binary,
            Token.T_BRANCH: self._visit_branch,
            Token.T_LOGICAL_AND: self._visit_logical_and,
            Token.T_LOGICAL_OR: self._visit_logical_or,
            Token.T_NULLISH_COALESCING: self._visit_nullish_coalescing,
            Token.T_TERNARY: self._visit_ternary,
            Token.T_POSTFIX: self._visit_postfix,
            Token.T_PREFIX: self._visit_prefix,
            Token.T_WHILE: self._visit_while,
            Token.T_DOWHILE: self._visit_dowhile,
            Token.T_FOR: self._visit_for,
            Token.T_FOR_IN: self._visit_for_in,
            Token.T_CONTINUE: self._visit_continue,
            Token.T_BREAK: self._visit_break,
            Token.T_ARGLIST: self._visit_arglist,
            Token.T_BLOCK: self._visit_block,
            Token.T_GROUPING: self._visit_grouping,
            Token.T_STRING: self._visit_string,
            Token.T_OBJECT: self._visit_object,
            Token.T_LIST: self._visit_list,
            Token.T_GET_ATTR: self._visit_get_attr,
            Token.T_SUBSCR: self._visit_subscr,
            Token.T_ATTR: self._visit_attr,
            Token.T_KEYWORD: self._visit_keyword,
            Token.T_OPTIONAL_CHAINING: self._visit_optional_chaining,
            Token.T_FUNCTION: self._visit_function,
            Token.T_ANONYMOUS_FUNCTION: self._visit_anonymous_function,
            Token.T_LAMBDA: self._visit_lambda,
            Token.T_RETURN: self._visit_return,
            Token.T_FUNCTIONCALL: self._visit_functioncall,
            Token.T_TRY: self._visit_try,
            Token.T_CATCH: self._visit_catch,
            Token.T_FINALLY: self._visit_finally,
            Token.T_THROW: self._visit_throw,
            Token.T_DELETE_VAR: self._visit_delete_var,
            Token.T_FREE_VAR: self._visit_free_var,
            Token.T_CELL_VAR: self._visit_cell_var,
            Token.T_NEW: self._visit_new,
            Token.T_INCLUDE: self._visit_include,
            Token.T_EXPORT: self._visit_export,
            Token.T_EXPORT_DEFAULT: self._visit_export_default,
            Token.T_EXPORT_ARGS: self._visit_export_args,
        }

        self.functions = []
        self.includes = []

    def compile(self, ast, path=None):

        self.module = VmModule()
        self.module.path = path
        self.module.globals = VmGlobals()
        self.module.functions = [VmFunctionDef(ast, self.module.globals)]

        fnidx = 0

        while fnidx < len(self.module.functions):
            self.fn = self.module.functions[fnidx]
            self.seq = [(0,  VmCompiler.C_VISIT, self.fn.ast)]
            self.fn_jumps = {}

            self.target_continue = []
            self.target_break = []

            while self.seq:
                depth, state, obj = self.seq.pop()

                if state & VmCompiler.C_INSTRUCTION:
                    self._push_instruction(obj)

                elif state & VmCompiler.C_VISIT:

                    fn = self.visit_actions.get(obj.type, None)
                    if fn is not None:
                        fn(depth, state, obj)
                    else:
                        raise VmCompileError(obj, "token not supported for visit")

                elif state & VmCompiler.C_LOOP_END:
                    self.target_continue.pop()
                    self.target_break.pop()

                else:
                    raise VmCompileError(obj, "unexpected state %X" % state)

            self._finalize(self.fn, self.fn_jumps)

            fnidx += 1

        self.module.includes = self.includes

        return self.module

    def _finalize(self, fn, jumps):

        idxmap = {}
        for idx, instr in enumerate(fn.instrs):
            idxmap[instr] = idx

        for  instr1 in fn.instrs:

            if instr1 in jumps:
                for instr2 in jumps[instr1]:
                    idx_dst = idxmap[instr1]
                    idx_src = idxmap[instr2]
                    delta = idx_dst - idx_src
                    if instr1.opcode == opcodes.ctrl.ELSE:
                        delta += 1
                    instr2.args = [delta]

    def _visit_branch(self, depth, state, token):

        if len(token.children) == 2:
            arglist, branch_true = token.children

            instr1 = VmInstruction(opcodes.ctrl.END, token=token)
            instr2 = VmInstruction(opcodes.ctrl.IF, token=token)

            self.fn_jumps[instr1] = [instr2]  # target, list[source]

            self._push_token(depth, VmCompiler.C_INSTRUCTION, instr1)
            self._push_token(depth+1, VmCompiler.C_VISIT, branch_true)
            self._push_token(depth, VmCompiler.C_INSTRUCTION, instr2)
            self._push_token(depth, VmCompiler.C_VISIT, arglist)

        elif len(token.children) == 3:
            arglist, branch_true, branch_false = token.children

            instr1 = VmInstruction(opcodes.ctrl.END, token=token)
            instr2 = VmInstruction(opcodes.ctrl.ELSE, token=token)
            instr3 = VmInstruction(opcodes.ctrl.IF, token=token)

            self.fn_jumps[instr1] = [instr2]  # target, list[source]
            self.fn_jumps[instr2] = [instr3]  # target, list[source]

            self._push_token(depth, VmCompiler.C_INSTRUCTION, instr1)
            self._push_token(depth, VmCompiler.C_VISIT, branch_false)
            self._push_token(depth, VmCompiler.C_INSTRUCTION, instr2)
            self._push_token(depth, VmCompiler.C_VISIT, branch_true)
            self._push_token(depth, VmCompiler.C_INSTRUCTION, instr3)
            self._push_token(depth, VmCompiler.C_VISIT, arglist)

        else:
            raise VmCompileError(token, "invalid child count")

    def _visit_logical_and(self, depth, state, token):

        lhs, rhs = token.children

        dup = VmInstruction(opcodes.stack.DUP, token=token)
        pop = VmInstruction(opcodes.stack.POP, token=token)

        instr1 = VmInstruction(opcodes.ctrl.END, token=token)
        instr2 = VmInstruction(opcodes.ctrl.IF, token=token)

        self.fn_jumps[instr1] = [instr2]  # target, list[source]

        self._push_token(depth, VmCompiler.C_INSTRUCTION, instr1)
        self._push_token(depth, VmCompiler.C_VISIT|VmCompiler.C_LOAD, rhs)
        self._push_token(depth, VmCompiler.C_INSTRUCTION, pop)
        self._push_token(depth, VmCompiler.C_INSTRUCTION, instr2)
        self._push_token(depth, VmCompiler.C_INSTRUCTION, dup)
        self._push_token(depth, VmCompiler.C_VISIT|VmCompiler.C_LOAD, lhs)

    def _visit_logical_or(self, depth, state, token):
        lhs, rhs = token.children

        dup = VmInstruction(opcodes.stack.DUP, token=token)
        pop = VmInstruction(opcodes.stack.POP, token=token)

        instr1 = VmInstruction(opcodes.ctrl.END, token=token)
        instr2 = VmInstruction(opcodes.ctrl.ELSE, token=token)
        instr3 = VmInstruction(opcodes.ctrl.IF, token=token)

        self.fn_jumps[instr1] = [instr2]  # target, list[source]
        self.fn_jumps[instr2] = [instr3]  # target, list[source]

        self._push_token(depth, VmCompiler.C_INSTRUCTION, instr1)
        self._push_token(depth, VmCompiler.C_VISIT|VmCompiler.C_LOAD, rhs)
        self._push_token(depth, VmCompiler.C_INSTRUCTION, pop)
        self._push_token(depth, VmCompiler.C_INSTRUCTION, instr2)
        self._push_token(depth, VmCompiler.C_INSTRUCTION, instr3)
        self._push_token(depth, VmCompiler.C_INSTRUCTION, dup)
        self._push_token(depth, VmCompiler.C_VISIT|VmCompiler.C_LOAD, lhs)

    def _visit_nullish_coalescing(self, depth, state, token):

        lhs, rhs = token.children

        dup = VmInstruction(opcodes.stack.DUP, token=token)
        pop = VmInstruction(opcodes.stack.POP, token=token)

        instr1 = VmInstruction(opcodes.ctrl.END, token=token)
        instr2 = VmInstruction(opcodes.ctrl.ELSE, token=token)
        instr3 = VmInstruction(opcodes.ctrl.IFNULL, token=token)

        self.fn_jumps[instr1] = [instr2]  # target, list[source]
        self.fn_jumps[instr2] = [instr3]  # target, list[source]

        self._push_token(depth, VmCompiler.C_INSTRUCTION, instr1)
        self._push_token(depth, VmCompiler.C_VISIT|VmCompiler.C_LOAD, rhs)
        self._push_token(depth, VmCompiler.C_INSTRUCTION, pop)
        self._push_token(depth, VmCompiler.C_INSTRUCTION, instr2)
        self._push_token(depth, VmCompiler.C_INSTRUCTION, instr3)
        self._push_token(depth, VmCompiler.C_INSTRUCTION, dup)
        self._push_token(depth, VmCompiler.C_VISIT|VmCompiler.C_LOAD, lhs)

    def _visit_ternary(self, depth, state, token):

        arglist, branch_true, branch_false = token.children

        instr1 = VmInstruction(opcodes.ctrl.END, token=token)
        instr2 = VmInstruction(opcodes.ctrl.ELSE, token=token)
        instr3 = VmInstruction(opcodes.ctrl.IF, token=token)

        self.fn_jumps[instr1] = [instr2]  # target, list[source]
        self.fn_jumps[instr2] = [instr3]  # target, list[source]

        self._push_token(depth, VmCompiler.C_INSTRUCTION, instr1)
        self._push_token(depth, VmCompiler.C_VISIT, branch_false)
        self._push_token(depth, VmCompiler.C_INSTRUCTION, instr2)
        self._push_token(depth, VmCompiler.C_VISIT, branch_true)
        self._push_token(depth, VmCompiler.C_INSTRUCTION, instr3)
        self._push_token(depth, VmCompiler.C_VISIT, arglist)

    def _visit_while(self, depth, state, token):
        arglist, block = token.children

        instr_e = VmInstruction(opcodes.ctrl.END, token=token)
        instr_j = VmInstruction(opcodes.ctrl.JUMP, token=token)
        instr_b = VmInstruction(opcodes.ctrl.IF, token=token)
        instr_l = VmInstruction(opcodes.ctrl.LOOP, token=token)

        self.fn_jumps[instr_e] = [instr_b]  # target, list[source]
        self.fn_jumps[instr_l] = [instr_j]  # target, list[source]

        self.target_continue.append(instr_l)
        self.target_break.append(instr_e)

        self._push_token(depth, VmCompiler.C_LOOP_END, None)
        self._push_token(depth, VmCompiler.C_INSTRUCTION, instr_e)
        self._push_token(depth, VmCompiler.C_INSTRUCTION, instr_j)
        self._push_token(depth, VmCompiler.C_VISIT, block)
        self._push_token(depth, VmCompiler.C_INSTRUCTION, instr_b)
        self._push_token(depth, VmCompiler.C_VISIT, arglist)
        self._push_token(depth, VmCompiler.C_INSTRUCTION, instr_l)

    def _visit_dowhile(self, depth, state, token):
        block, arglist = token.children


        instr_e = VmInstruction(opcodes.ctrl.END, token=token)
        instr_j = VmInstruction(opcodes.ctrl.JUMP, token=token)
        instr_b = VmInstruction(opcodes.ctrl.IF, token=token)
        instr_l = VmInstruction(opcodes.ctrl.LOOP, token=token)

        self.fn_jumps[instr_e] = [instr_b]  # target, list[source]
        self.fn_jumps[instr_l] = [instr_j]  # target, list[source]

        self.target_continue.append(instr_l)
        self.target_break.append(instr_e)

        self._push_token(depth, VmCompiler.C_LOOP_END, None)
        self._push_token(depth, VmCompiler.C_INSTRUCTION, instr_e)
        self._push_token(depth, VmCompiler.C_INSTRUCTION, instr_j)
        self._push_token(depth, VmCompiler.C_INSTRUCTION, instr_b)
        self._push_token(depth, VmCompiler.C_VISIT, arglist)
        self._push_token(depth, VmCompiler.C_VISIT, block)
        self._push_token(depth, VmCompiler.C_INSTRUCTION, instr_l)

    def _visit_for(self, depth, state, token):

        arglist, block, *deletevars = token.children

        arg_init, arg_loop, arg_incr = arglist.children

        instr_e = VmInstruction(opcodes.ctrl.END, token=token)
        instr_j = VmInstruction(opcodes.ctrl.JUMP, token=token)
        instr_b = VmInstruction(opcodes.ctrl.IF, token=token)
        instr_l = VmInstruction(opcodes.ctrl.LOOP, token=token)

        self.fn_jumps[instr_l] = [instr_j]  # target, list[source]

        self.target_continue.append(instr_l)
        self.target_break.append(instr_e)

        # TODO: support deleting the iterator var
        #for child in reversed(deletevars):
        #    self._push_token(depth, VmCompiler.C_VISIT, child)

        self._push_token(depth, VmCompiler.C_INSTRUCTION, instr_e)
        self._push_token(depth, VmCompiler.C_INSTRUCTION, instr_j)

        if arg_incr.type != Token.T_EMPTY_TOKEN:
            self._push_token(depth, VmCompiler.C_VISIT, arg_incr)

        self._push_token(depth, VmCompiler.C_VISIT, block)

        if arg_loop.type != Token.T_EMPTY_TOKEN:
            self._push_token(depth, VmCompiler.C_INSTRUCTION, instr_b)
            self._push_token(depth, VmCompiler.C_VISIT, arg_loop)

            self.fn_jumps[instr_e] = [instr_b]

        self._push_token(depth, VmCompiler.C_INSTRUCTION, instr_l)

        if arg_init.type != Token.T_EMPTY_TOKEN:
            self._push_token(depth, VmCompiler.C_VISIT, arg_init)

    def _visit_for_in(self, depth, state, token):
        pass

    def _visit_postfix(self, depth, state, token):

        const_int = VmInstruction(opcodes.const.INT, 1, token=token)
        dup = VmInstruction(opcodes.stack.DUP, token=token)

        if token.value == "++":
            add = VmInstruction(opcodes.math.ADD, token=token)
            if state & VmCompiler.C_LOAD == 0:
                self._push_token(depth, VmCompiler.C_INSTRUCTION, VmInstruction(opcodes.stack.POP, token=token))
            #TODO: this has side effects that need to be fixed
            #      f()++  => no write back, cannot assign to function call
            #      a.b++  => duplicate the reference to a
            #      a[x]++  => duplicate the reference to a and x
            self._push_token(depth, VmCompiler.C_VISIT | VmCompiler.C_STORE, token.children[0])
            self._push_token(depth, VmCompiler.C_INSTRUCTION, add)
            self._push_token(depth, VmCompiler.C_INSTRUCTION, const_int)
            self._push_token(depth, VmCompiler.C_INSTRUCTION, dup)
            self._push_token(depth, VmCompiler.C_VISIT | VmCompiler.C_LOAD, token.children[0])
        elif token.value == "--":
            sub = VmInstruction(opcodes.math.ADD, token=token)
            if state & VmCompiler.C_LOAD == 0:
                self._push_token(depth, VmCompiler.C_INSTRUCTION, VmInstruction(opcodes.stack.POP, token=token))
            #TODO: this has side effects that need to be fixed
            self._push_token(depth, VmCompiler.C_VISIT | VmCompiler.C_STORE, token.children[0])
            self._push_token(depth, VmCompiler.C_INSTRUCTION, sub)
            self._push_token(depth, VmCompiler.C_INSTRUCTION, const_int)
            self._push_token(depth, VmCompiler.C_INSTRUCTION, dup)
            self._push_token(depth, VmCompiler.C_VISIT | VmCompiler.C_LOAD, token.children[0])

        else:
            raise NotImplementedError(str(token))

    def _visit_prefix(self, depth, state, token):

        if token.value == "!":
            inst = VmInstruction(opcodes.math.NOT, token=token)
            self._push_token(depth, VmCompiler.C_INSTRUCTION, inst)
            self._push_token(depth, VmCompiler.C_VISIT | VmCompiler.C_LOAD, token.children[0])
        elif token.value == "~":
            inst = VmInstruction(opcodes.math.BITWISE_NOT, token=token)
            self._push_token(depth, VmCompiler.C_INSTRUCTION, inst)
            self._push_token(depth, VmCompiler.C_VISIT | VmCompiler.C_LOAD, token.children[0])
        elif token.value == "+":
            inst = VmInstruction(opcodes.math.POSITIVE, token=token)
            self._push_token(depth, VmCompiler.C_INSTRUCTION, inst)
            self._push_token(depth, VmCompiler.C_VISIT | VmCompiler.C_LOAD, token.children[0])
        elif token.value == "-":
            inst = VmInstruction(opcodes.math.NEGATIVE, token=token)
            self._push_token(depth, VmCompiler.C_INSTRUCTION, inst)
            self._push_token(depth, VmCompiler.C_VISIT | VmCompiler.C_LOAD, token.children[0])
        elif token.value == "typeof":
            inst = VmInstruction(opcodes.obj.GET_TYPENAME, token=token)
            self._push_token(depth, VmCompiler.C_INSTRUCTION, inst)
            self._push_token(depth, VmCompiler.C_VISIT | VmCompiler.C_LOAD, token.children[0])
        elif token.value == "delete":
            child = token.children[0]
            if child.type == Token.T_SUBSCR:
                opcode = opcodes.obj.DEL_INDEX
                index = 0
                lhs, rhs = child.children
                inst = VmInstruction(opcode, token=token)
                self._push_token(depth, VmCompiler.C_INSTRUCTION, inst)
                self._push_token(depth, VmCompiler.C_VISIT | VmCompiler.C_LOAD, lhs)
                self._push_token(depth, VmCompiler.C_VISIT | VmCompiler.C_LOAD, rhs)
            elif child.type == Token.T_GET_ATTR:
                lhs, rhs = child.children
                opcode = opcodes.obj.DEL_ATTR
                name = rhs.value
                try:
                    index = self.fn.local_names.index(name)
                except ValueError:
                    index = len(self.fn.local_names)
                    self.fn.local_names.append(name)
                inst = VmInstruction(opcode, index, token=token)
                self._push_token(depth, VmCompiler.C_INSTRUCTION, inst)
                self._push_token(depth, VmCompiler.C_VISIT | VmCompiler.C_LOAD, lhs)
            else:
                raise VmCompileError(child, "invalid child for prefix delete")





        else:
            raise NotImplementedError(str(token))

    def _visit_break(self, depth, state, token):
        instr0 = VmInstruction(opcodes.ctrl.JUMP, token=token)
        self.fn_jumps[self.target_break[-1]].append(instr0)
        self._push_instruction(instr0)

    def _visit_continue(self, depth, state, token):
        instr0 = VmInstruction(opcodes.ctrl.JUMP, token=token)
        self.fn_jumps[self.target_continue[-1]].append(instr0)
        self._push_instruction(instr0)

    def _visit_object(self, depth, state, token):

        unpack = any(child.type == Token.T_SPREAD for child in token.children)
        if unpack:
            # This can be optimized in the future

            # unpack the children into a set of distinct dictionaries
            seq = []
            for child in reversed(token.children):
                if child.type == Token.T_SPREAD:
                    seq.append(child)
                else:
                    if len(seq) == 0 or isinstance(seq[-1], Token):
                        seq.append([])
                    seq[-1].append(child)

            # create an initial, empty object
            # then update this object with every dict encountered
            for obj in seq:
                if isinstance(obj, Token):
                    child = obj.children[0]
                    instr = VmInstruction(opcodes.obj.UPDATE_OBJECT, token=token)
                    self._push_token(depth, VmCompiler.C_INSTRUCTION, instr)
                    self._push_token(depth, VmCompiler.C_VISIT | VmCompiler.C_LOAD, child)
                else:
                    nprops = len(obj)

                    instr = VmInstruction(opcodes.obj.UPDATE_OBJECT, token=token)
                    self._push_token(depth, VmCompiler.C_INSTRUCTION, instr)

                    instr = VmInstruction(opcodes.obj.CREATE_OBJECT, nprops, token=token)
                    self._push_token(depth, VmCompiler.C_INSTRUCTION, instr)

                    for child in obj:
                        self._push_token(depth, VmCompiler.C_VISIT | VmCompiler.C_LOAD, child)

            instr = VmInstruction(opcodes.obj.CREATE_OBJECT, 0, token=token)
            self._push_token(depth, VmCompiler.C_INSTRUCTION, instr)


        else:
            nprops = len(token.children)
            instr = VmInstruction(opcodes.obj.CREATE_OBJECT, nprops, token=token)
            self._push_token(depth, VmCompiler.C_INSTRUCTION, instr)

            for child in reversed(token.children):
                self._push_token(depth, VmCompiler.C_VISIT | VmCompiler.C_LOAD, child)

    def _visit_list(self, depth, state, token):
        unpack = any(child.type == Token.T_SPREAD for child in token.children)
        if unpack:
            # This can be optimized in the future

            # unpack the children into a set of distinct dictionaries
            seq = []
            for child in reversed(token.children):
                if child.type == Token.T_SPREAD:
                    seq.append(child)
                else:
                    if len(seq) == 0 or isinstance(seq[-1], Token):
                        seq.append([])
                    seq[-1].append(child)

            # create an initial, empty object
            # then update this object with every dict encountered
            for obj in seq:
                if isinstance(obj, Token):
                    child = obj.children[0]
                    instr = VmInstruction(opcodes.obj.UPDATE_ARRAY, token=token)
                    self._push_token(depth, VmCompiler.C_INSTRUCTION, instr)
                    self._push_token(depth, VmCompiler.C_VISIT | VmCompiler.C_LOAD, child)
                else:
                    nprops = len(obj)

                    instr = VmInstruction(opcodes.obj.UPDATE_ARRAY, token=token)
                    self._push_token(depth, VmCompiler.C_INSTRUCTION, instr)

                    instr = VmInstruction(opcodes.obj.CREATE_ARRAY, nprops, token=token)
                    self._push_token(depth, VmCompiler.C_INSTRUCTION, instr)

                    for child in obj:
                        self._push_token(depth, VmCompiler.C_VISIT | VmCompiler.C_LOAD, child)

            instr = VmInstruction(opcodes.obj.CREATE_ARRAY, 0, token=token)
            self._push_token(depth, VmCompiler.C_INSTRUCTION, instr)

        else:
            nprops = len(token.children)
            instr = VmInstruction(opcodes.obj.CREATE_ARRAY, nprops, token=token)
            self._push_token(depth, VmCompiler.C_INSTRUCTION, instr)

            for child in reversed(token.children):
                self._push_token(depth, VmCompiler.C_VISIT | VmCompiler.C_LOAD, child)

    def _visit_get_attr(self, depth, state, token):

        flag0 = VmCompiler.C_VISIT | VmCompiler.C_LOAD

        flag1 = VmCompiler.C_VISIT
        if token.value == "." and state & VmCompiler.C_STORE:
            flag1 |= VmCompiler.C_STORE
        else:
            flag1 |= VmCompiler.C_LOAD

        self._push_token(depth, flag1, token.children[1])
        self._push_token(depth, flag0, token.children[0])

    def _visit_subscr(self, depth, state, token):

        if state&VmCompiler.C_STORE:
            opcode = opcodes.obj.SET_INDEX
        else:
            opcode = opcodes.obj.GET_INDEX

        self._push_token(depth, VmCompiler.C_INSTRUCTION, VmInstruction(opcode, token=token))
        self._push_token(depth, VmCompiler.C_VISIT|VmCompiler.C_LOAD, token.children[0])
        self._push_token(depth, VmCompiler.C_VISIT|VmCompiler.C_LOAD, token.children[1])

    def _visit_attr(self, depth, state, token):

        name = token.value

        try:
            index = self.fn.local_names.index(name)
        except ValueError:
            index = len(self.fn.local_names)
            self.fn.local_names.append(name)

        if state & VmCompiler.C_STORE:
            opcode = opcodes.obj.SET_ATTR
        else:
            opcode = opcodes.obj.GET_ATTR

        self._push_instruction(VmInstruction(opcode, index, token=token))

    def _visit_arglist(self, depth, state, token):

        flag0 = VmCompiler.C_VISIT | VmCompiler.C_LOAD
        for child in reversed(token.children):
            self._push_token(depth, flag0, child)

    def _visit_block(self, depth, state, token):

        flag0 = VmCompiler.C_VISIT
        for child in reversed(token.children):
            self._push_token(depth, flag0, child)

    def _visit_grouping(self, depth, state, token):

        for child in reversed(token.children):
            self._push_token(depth, state, child)

    def _visit_module(self, depth, state, token):

        for child in reversed(token.children):
            self._push_token(depth, VmCompiler.C_VISIT, child)

    def _visit_var(self, depth, state, token):

        for child in reversed(token.children):

            if child.type == Token.T_ASSIGN:
                #self._push_token(depth, VmCompiler.C_VISIT, child)
                self._push_token(depth, VmCompiler.C_VISIT|VmCompiler.C_STORE, child.children[0])
                self._push_token(depth, VmCompiler.C_VISIT|VmCompiler.C_LOAD, child.children[1])

            else:
                self._push_token(depth, VmCompiler.C_VISIT|VmCompiler.C_STORE, token.children[0])
                self._push_token(depth, VmCompiler.C_INSTRUCTION, VmInstruction(opcodes.const.UNDEFINED, token=token))

        # for const and let, implement block scoping by saving the current value of
        # the variable to the stack. later, DELETE_VAR can pop the old value
        # TODO: order of operations

        if token.value == "const" or token.value == "let":

            for child in reversed(token.children):

                if child.type == Token.T_ASSIGN:
                    var = child.children[0]
                else:
                    var = child

                if var.type == Token.T_LOCAL_VAR:

                    # if already defined, save the current value on the stack
                    if var.value in self.fn.local_names:
                        opcode, index = self._token2index(var, True)
                        #print("push", token.value, "local", var.value)
                        self._push_token(depth, VmCompiler.C_INSTRUCTION,
                            VmInstruction(opcode, index, token=token))


                elif var.type == Token.T_GLOBAL_VAR:

                    # if already defined, save the current value on the stack
                    if var.value in self.fn.globals.names:
                        opcode, index = self._token2index(var, True)
                        #print("push", token.value, "global", var.value)
                        self._push_token(depth, VmCompiler.C_INSTRUCTION,
                            VmInstruction(opcode, index, token=token))
                else:
                    raise VmCompileError(var, "illegal variable def")

    def _visit_delete_var(self, depth, state, token):
        child = token.children[0]
        opcode, index = self._token2index(child, False, delete=True)
        self._push_token(depth, VmCompiler.C_INSTRUCTION, VmInstruction(opcode, index, token=child))

    def _visit_binary(self, depth, state, token):

        #flag0 = VmCompiler.C_VISIT
        #if token.value == "=":
        #    flag0 |= VmCompiler.C_STORE
        #else:
        #    flag0 |= VmCompiler.C_LOAD
        #flag1 = VmCompiler.C_VISIT

        if token.value == ":":
            # as part of a objectkey value pair
            self._push_token(depth, VmCompiler.C_VISIT|VmCompiler.C_LOAD, token.children[1])
            self._push_token(depth, VmCompiler.C_VISIT|VmCompiler.C_LOAD, token.children[0])
        elif token.value == "in":
            # TODO: may remove HAS_ATTR in the future for better python interoperability
            opcode = opcodes.obj.HAS_ATTR
            self._push_token(depth, VmCompiler.C_INSTRUCTION, VmInstruction(opcode, token=token))
            self._push_token(depth, VmCompiler.C_VISIT|VmCompiler.C_LOAD, token.children[1])
            self._push_token(depth, VmCompiler.C_VISIT|VmCompiler.C_LOAD, token.children[0])

        else:
            opcode = binop.get(token.value, None)
            if opcode is None:
                raise VmCompileError(token, "illegal binary operator")
            self._push_token(depth, VmCompiler.C_INSTRUCTION, VmInstruction(opcode, token=token))
            self._push_token(depth, VmCompiler.C_VISIT|VmCompiler.C_LOAD, token.children[1])
            self._push_token(depth, VmCompiler.C_VISIT|VmCompiler.C_LOAD, token.children[0])

    def _visit_assign(self, depth, state, token):

        if token.value == "=":



            self._push_token(depth, VmCompiler.C_VISIT|VmCompiler.C_STORE, token.children[0])

            if state & VmCompiler.C_LOAD:
                self._push_token(depth, VmCompiler.C_INSTRUCTION, VmInstruction(opcodes.stack.DUP, token=token))

            self._push_token(depth, VmCompiler.C_VISIT|VmCompiler.C_LOAD, token.children[1])



        else:

            if token.value in binop_store:
                self._push_token(depth, VmCompiler.C_VISIT | VmCompiler.C_STORE, token.children[0])
                self._push_token(depth, VmCompiler.C_INSTRUCTION, VmInstruction(binop_store[token.value], token=token))

            lhs, rhs = token.children
            if lhs.type == Token.T_GET_ATTR:
                self._push_token(depth, VmCompiler.C_VISIT, token.children[1])
                self._push_token(depth, VmCompiler.C_VISIT | VmCompiler.C_LOAD, token.children[0])
            elif lhs.type == Token.T_SUBSCR:
                raise NotImplementedError()
            else:
                #self._push_token(depth, VmCompiler.C_VISIT | (state & (VmCompiler.C_LOAD_STORE)), token)
                self._push_token(depth, VmCompiler.C_VISIT | VmCompiler.C_LOAD, token.children[1])
                self._push_token(depth, VmCompiler.C_VISIT | VmCompiler.C_LOAD, token.children[0])

    def _visit_free_var(self, depth, state, token):

        opcode, index = self._token2index(token, state & VmCompiler.C_LOAD)

        self._push_instruction(VmInstruction(opcode, index, token=token))

    def _visit_cell_var(self, depth, state, token):

        opcode, index = self._token2index(token, state & VmCompiler.C_LOAD)

        self._push_instruction(VmInstruction(opcode, index, token=token))

    def _visit_text(self, depth, state, token):

        opcode, index = self._token2index(token, state & VmCompiler.C_LOAD)

        self._push_instruction(VmInstruction(opcode, index, token=token))

    def _build_instr_string(self, state, token, value):
        index = -1
        try:
            index = self.fn.globals.constdata.index(value)
        except ValueError:
            if state & VmCompiler.C_LOAD:
                index = len(self.fn.globals.constdata)
                self.fn.globals.constdata.append(value)

        if index == -1:
            raise VmCompileError(token, "unable to load undefined string (%0X)" % state)

        return VmInstruction(opcodes.const.STRING, index, token=token)

    def _visit_string(self, depth, state, token):

        try:
            value = JsString(pyast.literal_eval(token.value))
        except SyntaxError as e:
            raise VmCompileError(token, "unable to load undefined string (%0X)" % state)
        except Exception as e:
            raise VmCompileError(token, "unable to load undefined string (%0X)" % state)
        self._push_instruction(self._build_instr_string(state, token, value))

    def _visit_number(self, depth, state, token):

        try:
            val = int(token.value)
            op = opcodes.const.INT
        except:
            val = float(token.value)
            op = opcodes.const.FLOAT32

        self._push_instruction(VmInstruction(op, val, token=token))

    def _visit_keyword(self, depth, state, token):

        if token.value == "true":
            self._push_instruction(VmInstruction(opcodes.const.BOOL, 1, token=token))
        elif token.value == "false":
            self._push_instruction(VmInstruction(opcodes.const.BOOL, 0, token=token))
        elif token.value == "null":
            self._push_instruction(VmInstruction(opcodes.const.NULL, token=token))
        elif token.value == "undefined":
            self._push_instruction(VmInstruction(opcodes.const.UNDEFINED, token=token))
        elif token.value == "this":
            opcode, index = self._token2index(token, state & VmCompiler.C_LOAD)
            self._push_instruction(VmInstruction(opcode, index, token=token))
        else:
            raise VmCompileError(token, "not implemented")

    def _visit_optional_chaining(self, depth, state, token):

        # TODO: apply TransformOptionalChaining.visit to the token

        if token.children[0].type == Token.T_FUNCTIONCALL:
            pass
        elif token.children[0].type == Token.T_SUBSCR:
            pass
        else:
            pass

    def _visit_function(self, depth, state, token):

        name = token.children[0]
        arglist = token.children[1]
        block = token.children[2]
        closure = token.children[3]

        opcode, index = self._token2index(name, False)
        self._push_token(depth, VmCompiler.C_INSTRUCTION, VmInstruction(opcode, index, token=token))

        self._build_function(state|VmCompiler.C_LOAD, token, name, arglist, block, closure, autobind=False)

    def _visit_anonymous_function(self, depth, state, token):

        name = token.children[0]
        arglist = token.children[1]
        block = token.children[2]
        closure = token.children[3]

        #opcode, index = self._token2index(name, False)
        #self._push_token(depth, VmCompiler.C_INSTRUCTION, VmInstruction(opcode, index, token=token))

        self._build_function(state|VmCompiler.C_LOAD, token, name, arglist, block, closure, autobind=False)

    def _visit_lambda(self, depth, state, token):

        if len(token.children) != 4:
            raise VmCompileError(token,"invalid")
        name = token.children[0]
        arglist = token.children[1]
        block = token.children[2]
        closure = token.children[3]

        self._build_function(state|VmCompiler.C_LOAD, token, name, arglist, block, closure, autobind=True)

    def _visit_functioncall(self, depth, state, token):

        expr_call, expr_args = token.children
        unpack = any(child.type == Token.T_SPREAD for child in expr_args.children)
        if unpack:
            if state & VmCompiler.C_LOAD == 0:
                self._push_token(depth, VmCompiler.C_INSTRUCTION, VmInstruction(opcodes.stack.POP, token=token))

                        # This can be optimized in the future
            self._push_token(depth, VmCompiler.C_INSTRUCTION, VmInstruction(opcodes.ctrl.CALL_EX, 0, token=token))
            self._push_token(0, VmCompiler.C_INSTRUCTION, VmInstruction(opcodes.obj.CREATE_OBJECT, 0, token=token))

            # unpack the children into a set of distinct dictionaries
            seq = []
            for child in reversed(expr_args.children):
                if child.type == Token.T_ASSIGN:
                    # nned to pop these first
                    raise VmCompileError(expr_args, "not implemented")
                elif child.type == Token.T_SPREAD:
                    seq.append(child)
                else:
                    if len(seq) == 0 or isinstance(seq[-1], Token):
                        seq.append([])
                    seq[-1].append(child)

            # create an initial, empty object
            # then update this object with every dict encountered
            for obj in seq:
                if isinstance(obj, Token):
                    child = obj.children[0]
                    instr = VmInstruction(opcodes.obj.UPDATE_ARRAY, token=expr_args)
                    self._push_token(depth, VmCompiler.C_INSTRUCTION, instr)
                    self._push_token(depth, VmCompiler.C_VISIT | VmCompiler.C_LOAD, child)
                else:
                    nprops = len(obj)

                    instr = VmInstruction(opcodes.obj.UPDATE_ARRAY, token=expr_args)
                    self._push_token(depth, VmCompiler.C_INSTRUCTION, instr)

                    instr = VmInstruction(opcodes.obj.CREATE_ARRAY, nprops, token=expr_args)
                    self._push_token(depth, VmCompiler.C_INSTRUCTION, instr)

                    for child in obj:
                        self._push_token(depth, VmCompiler.C_VISIT | VmCompiler.C_LOAD, child)

            instr = VmInstruction(opcodes.obj.CREATE_ARRAY, 0, token=expr_args)
            self._push_token(depth, VmCompiler.C_INSTRUCTION, instr)

            flag0 = VmCompiler.C_VISIT | VmCompiler.C_LOAD
            self._push_token(depth, flag0, expr_call)

        else:
            if state & VmCompiler.C_LOAD == 0:
                self._push_token(depth, VmCompiler.C_INSTRUCTION, VmInstruction(opcodes.stack.POP, token=token))

            flag0 = VmCompiler.C_VISIT | VmCompiler.C_LOAD

            allow_positional = True
            pos_count = 0
            kwarg_count = 0


            seq = []
            for child in reversed(expr_args.children):
                if child.type == Token.T_ASSIGN:
                    allow_positional = False

                    seq.append((depth, flag0, child.children[1]))
                    seq.append((depth, VmCompiler.C_INSTRUCTION, self._build_instr_string(flag0, token, child.children[0].value)))
                    kwarg_count += 1
                elif allow_positional:
                    pos_count += 1
                    seq.append((depth, flag0, child))
                else:
                    raise VmCompileError(child, "syntax error: pos after kwarg")

            self._push_token(depth, VmCompiler.C_INSTRUCTION, VmInstruction(opcodes.ctrl.CALL, pos_count, token=token))
            self._push_token(0, VmCompiler.C_INSTRUCTION, VmInstruction(opcodes.obj.CREATE_OBJECT, kwarg_count, token=token))
            self.seq.extend(seq)

            flag0 = VmCompiler.C_VISIT | VmCompiler.C_LOAD
            self._push_token(depth, flag0, expr_call)

    def _visit_new(self, depth, state, token):

        flag0 = VmCompiler.C_VISIT | VmCompiler.C_LOAD
        self._push_token(depth, flag0, token.children[0])

    def _visit_return(self, depth, state, token):
        self._push_token(depth, VmCompiler.C_INSTRUCTION, VmInstruction(opcodes.ctrl.RETURN, len(token.children), token=token))
        flag0 = VmCompiler.C_VISIT | VmCompiler.C_LOAD
        for child in reversed(token.children):
            self._push_token(depth, flag0, child)

    def _visit_try(self, depth, state, token):
        flag0 = VmCompiler.C_VISIT

        count = len(token.children)

        instr_e = VmInstruction(opcodes.ctrl.TRYEND, token=token)
        instr_jf = VmInstruction(opcodes.ctrl.JUMP, token=token)
        instr_f = VmInstruction(opcodes.ctrl.FINALLY, token=token)
        instr_c = VmInstruction(opcodes.ctrl.CATCH, token=token)
        instr_t = VmInstruction(opcodes.ctrl.TRY, token=token)
        instr_if = VmInstruction(opcodes.const.INT, token=token)
        instr_ic = VmInstruction(opcodes.const.INT, token=token)

        self.fn_jumps[instr_f] = [instr_jf]  # target, list[source]
        self.fn_jumps[instr_c] = []  # target, list[source]

        block = None
        catch = None
        final = None
        tryarg = 0

        block = token.children[0]

        if count == 2:
            if token.children[1].type == Token.T_CATCH:
                catch = token.children[1]
            else:
                final = token.children[1]

        elif count == 3:
            catch = token.children[1]
            final = token.children[2]

        if catch is None and final is None:
            pass
        elif catch is None:
            self.fn_jumps[instr_f].append(instr_ic)
            self.fn_jumps[instr_f].append(instr_if)
        elif final is None:
            self.fn_jumps[instr_c].append(instr_ic)
            self.fn_jumps[instr_c].append(instr_if)
        else:
            self.fn_jumps[instr_c].append(instr_ic)
            self.fn_jumps[instr_f].append(instr_if)


        self._push_token(depth, VmCompiler.C_INSTRUCTION, instr_e)

        if final is not None:
            self._push_token(depth, flag0, final)

        self._push_token(depth, VmCompiler.C_INSTRUCTION, instr_f)

        if catch is not None:
            self._push_token(depth, flag0, catch)

        self._push_token(depth, VmCompiler.C_INSTRUCTION, instr_c)
        self._push_token(depth, VmCompiler.C_INSTRUCTION, instr_jf)

        if block is not None:
            self._push_token(depth, flag0, block)

        self._push_token(depth, VmCompiler.C_INSTRUCTION, instr_t)

        self._push_token(depth, VmCompiler.C_INSTRUCTION, instr_if)
        self._push_token(depth, VmCompiler.C_INSTRUCTION, instr_ic)

        #self._push_token(depth, VmCompiler.C_INSTRUCTION, instr_b)

    def _visit_catch(self, depth, state, token):
        """assuming the exception is on the top of the stack...
           maybe not a good place for it?
        """

        flag0 = VmCompiler.C_VISIT

        # TODO: third child deletes block variables
        arglist, block, _ = token.children
        self._push_token(depth, flag0, block)
        self._push_token(depth, flag0|VmCompiler.C_STORE, arglist.children[0])

    def _visit_finally(self, depth, state, token):

        flag0 = VmCompiler.C_VISIT
        for child in reversed(token.children):
            self._push_token(depth, flag0, child)

    def _visit_throw(self, depth, state, token):
        self._push_token(depth, VmCompiler.C_INSTRUCTION, VmInstruction(opcodes.ctrl.THROW, token=token))
        flag0 = VmCompiler.C_VISIT | VmCompiler.C_LOAD
        for child in reversed(token.children):
            self._push_token(depth, flag0, child)

    def _visit_include(self, depth, state, token):
        path = pyast.literal_eval(token.children[0].value)
        self.includes.append(path)
        pass

    def _visit_export(self, depth, state, token):
        node = token.children[1]
        self._push_token(depth, state, node)

    def _visit_export_default(self, depth, state, token):
        node = token.children[1]
        self._push_token(depth, state, node)

    def _visit_export_args(self, depth, state, token):

        flag0 = VmCompiler.C_VISIT | VmCompiler.C_LOAD
        for child in reversed(token.children):
            self._push_token(depth, flag0, child)

    def _build_function(self, state, token, name, arglist, block, closure, autobind=True):

        if token.type == Token.T_LAMBDA and block.type != token.T_BLOCK:
            # TODO: move to transform step?
            block = Token(Token.T_RETURN, block.line, block.index, "{}", [block])

        fndef = VmFunctionDef(block, self.module.globals)
        fndef._name = token.children[0].value
        fnidx = len(self.module.functions)
        self.module.functions.append(fndef)

        rest_name = "_x_daedalus_js_args"
        arglabels = []
        argdefaults = []
        # determine the arguments to this function
        vartypes= (Token.T_LOCAL_VAR, Token.T_GLOBAL_VAR, Token.T_FREE_VAR)
        if arglist.type in vartypes:
            # for one argument, mutate to multiple
            arglist = Token(Token.T_ARGLIST, arglist.line, arglist.index, '', [arglist])

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


        self._push_token(0, VmCompiler.C_INSTRUCTION, VmInstruction(opcodes.obj.CREATE_FUNCTION, fnidx, token=token))

        if closure and closure.children:

            seq = []
            for child in closure.children:

                if child.type == Token.T_FREE_VAR:
                    # argument is always a local variable, make a reference to it
                    #_, index = self._token2index(child, True)
                    # index = self.fn.local_names.index(child.value)
                    index = self.fn.cell_names.index(child.value)
                    seq.append((0, VmCompiler.C_INSTRUCTION, VmInstruction(opcodes.cellvar.LOAD, index, token=token)))
                    pass
                elif child.type == Token.T_CELL_VAR:
                    pass
                else:
                    raise VmCompileError(child, "expected cell or free var")

            self._push_token(0, VmCompiler.C_INSTRUCTION, VmInstruction(opcodes.obj.CREATE_TUPLE, len(seq), token=token))
            self.seq.extend(seq)

        if autobind:
            #this = Token(Token.T_KEYWORD, token.line, token.index, "this")
            #opcode, index = self._token2index(this, True)
            #self._push_token(0, VmCompiler.C_INSTRUCTION, VmInstruction(opcode, index, token=this))
            self._push_token(0, VmCompiler.C_INSTRUCTION, VmInstruction(opcodes.const.BOOL, 1, token=token))
        else:
            self._push_token(0, VmCompiler.C_INSTRUCTION, VmInstruction(opcodes.const.BOOL, 0, token=token))

        self._push_token(0, VmCompiler.C_INSTRUCTION, VmInstruction(opcodes.obj.CREATE_OBJECT, 0, token=token))

        self._push_token(0, VmCompiler.C_INSTRUCTION, VmInstruction(opcodes.const.INT, len(arglabels), token=token))

        for arglabel, argdefault in reversed(list(zip(arglabels, argdefaults))):

            if argdefault is None:
                self._push_token(0, VmCompiler.C_INSTRUCTION, VmInstruction(opcodes.const.UNDEFINED, token=token))
            else:
                self._push_token(0, VmCompiler.C_VISIT|VmCompiler.C_LOAD, argdefault)

        fndef.local_names = list(arglabels) + [rest_name]
        fndef.arglabels = list(arglabels)
        fndef.rest_name = rest_name

        fndef.cell_names = []
        fndef.free_names = []
        for var in closure.children:
            if var.type == Token.T_CELL_VAR:
                fndef.cell_names.append(var.value)
            elif var.type == Token.T_FREE_VAR:
                # TODO: fix duplication in cell_names
                fndef.cell_names.append(var.value)
                fndef.free_names.append(var.value)
            else:
                raise VmCompileError(var, "expected closure")

    def _token2index(self, token, load, delete=False):

        enum = None
        index = -1

        if token.type == Token.T_GLOBAL_VAR:
            name = token.value
            enum = opcodes.globalvar

            try:
                index = self.fn.globals.names.index(name)
            except ValueError:
                index = len(self.fn.globals.names)
                self.fn.globals.names.append(name)

        elif token.type == Token.T_LOCAL_VAR:
            name = token.value
            enum = opcodes.localvar

            try:
                index1 = self.fn.cell_names.index(name)

                #print("cell var", bool(load), name, index1,  self.fn.cell_names)
                if load:
                    return opcodes.cellvar.GET, index1
                else:
                    return opcodes.cellvar.SET, index1
            except ValueError:
                pass

            try:
                index = self.fn.local_names.index(name)
            except ValueError:
                if not load:
                    index = len(self.fn.local_names)
                    self.fn.local_names.append(name)

        elif token.type == Token.T_FREE_VAR:
            name = token.value
            enum = opcodes.cellvar
            #print("_token2index", token.type, bool(load), name, self.fn.cell_names)

            try:
                index = self.fn.cell_names.index(name)
            except ValueError:
                if not load:
                    index = len(self.fn.cell_names)
                    self.fn.cell_names.append(name)

            if index == -1:
                raise VmCompileError(token, "unable to load undefined identifier")

            if load:
                return enum.GET, index
            else:
                return enum.SET, index

        elif token.type == Token.T_CELL_VAR:
            name = token.value
            enum = opcodes.cellvar
            #print("_token2index", token.type, load, name, self.fn.cell_names)

            try:
                index = self.fn.cell_names.index(name)
            except ValueError:
                if not load:
                    index = len(self.fn.cell_names)
                    self.fn.cell_names.append(name)

            if index == -1:
                raise VmCompileError(token, "unable to load undefined identifier")

            if load:
                return enum.LOAD, index
            else:
                #return enum.SET, index
                raise NotImplementedError()

        elif token.type == Token.T_KEYWORD and token.value in ("this",):
            name = token.value
            enum = opcodes.localvar

            try:
                index = self.fn.local_names.index(name)
            except ValueError:
                index = len(self.fn.local_names)
                self.fn.local_names.append(name)

        if index == -1:
            if load:
                raise VmCompileError(token, "unable to load undefined identifier")
            else:
                raise VmCompileError(token, "unable to store undefined identifier")

        if delete:
            return enum.DELETE, index
        elif load:
            return enum.GET, index
        else:
            return enum.SET, index

    def _push_token(self, depth, state, token):
        self.seq.append((depth, state, token))

    def _push_instruction(self, instr):
        self.fn.instrs.append(instr)

# ---

operands = [
    '__lt__',
    '__le__',
    '__eq__',
    '__ne__',
    '__ge__',
    '__gt__',
    '__add__',
    '__sub__',
    '__mul__',
    '__truediv__',
    '__floordiv__',
    '__mod__',
    '__pow__',
    '__lshift__',
    '__rshift__',
    '__and__',
    '__xor__',
    '__or__',
]

operandsr = [

    ('__radd__'     , '__add__'),
    ('__rsub__'     , '__sub__'),
    ('__rmul__'     , '__mul__'),
    ('__rtruediv__' , '__truediv__'),
    ('__rfloordiv__', '__floordiv__'),
    ('__rmod__'     , '__mod__'),
    ('__rpow__'     , '__pow__'),
    ('__rlshift__'  , '__lshift__'),
    ('__rrshift__'  , '__rshift__'),
    ('__rand__'     , '__and__'),
    ('__rxor__'     , '__xor__'),
    ('__ror__'      , '__or__')
]

def jsc(f):

    text = f(None)

    tokens = Lexer().lex(text)
    parser = Parser()
    parser.feat_xform_optional_chaining = True
    parser.python = True
    ast = parser.parse(tokens)

    xform = TransformIdentityScope()
    xform.disable_warnings=True
    xform.transform(ast)

    xform = VmTransform()
    xform.transform(ast)

    compiler = VmCompiler()
    module = compiler.compile(ast)

    #if debug:
    #    print(ast.toString(1))
    #    module.dump()

    fn = JsFunction(module, module.functions[1], None, None, None)

    return fn

class JsObject(object):

    type_name = "object"

    def __init__(self, args=None):
        super(JsObject, self).__init__()

        if args:
            self.data = dict(args)
        else:
            self.data = {}

    def __repr__(self):
        # s = ",".join(["%r: %r" % (key, value) for key, value in self.data.items()])
        s = ",".join([str(s)+":"+str(self.data[s]) for s in self.data.keys()])
        return "<%s(%s)>" % (self.__class__.__name__, s)

    def _hasAttr(self, name):
        if isinstance(name, JsString):
            name = name.value
        return name in self.data

    def getAttr(self, name):
        if isinstance(name, JsString):
            name = name.value

        if hasattr(self, name):
            attr = getattr(self, name)
            if isinstance(attr, JsFunction):
                attr = attr.bind(self)
            return attr

        elif name in self.data:
            return self.data[name]

        print("get undefined attribute %s" % name)
        return JsUndefined.instance

    def setAttr(self, name, value):
        if isinstance(name, JsString):
            name = name.value
        self.data[name] = value

    def delAttr(self, name):
        if isinstance(name, JsString):
            name = name.value
        del self.data[name]

    def getIndex(self, index):
        if index in self.data:
            return self.data[index]
        print("get undefined index %s" % index)
        return JsUndefined.instance

    def setIndex(self, index, value):
        self.data[index] = value

    def delIndex(self, index):
        del self.data[index]

    @staticmethod
    def keys(inst):
        x = JsArray(inst.data.keys())
        return x

class JsObjectCtor(JsObject):

    def __call__(self, *args, **kwargs):
        return JsObject(*args, **kwargs)

class PyProp(object):
    def __init__(self, target, func):
        super(PyProp, self).__init__()
        self.target = target
        self.func = func

    def invoke(self, *args, **kwargs):
        return self.func(self.target, *args, **kwargs)

    def bind(self, target):
        return PyProp(target, self.func)

class PyCallable(object):
    def __init__(self, target, func):
        super(PyCallable, self).__init__()
        self.target = target
        self.func = func

    def __call__(self, *args, **kwargs):
        return self.func(self.target, *args, **kwargs)

    def bind(self, target):
        return PyCallable(target, self.func)

class JsArray(JsObject):

    type_name = "Array"

    def __init__(self, args=None):
        super(JsArray, self).__init__(None)
        if args:
            self.array = list(args)
        else:
            self.array = []

    def __repr__(self):
        s = ",".join([repr(s) for s in self.array])
        return "<%s(%s)>" % (self.__class__.__name__, s)

    def getIndex(self, index):
        if isinstance(index, int):
            return self.array[index]
        return self.getAttr(index)

    def setIndex(self, index, value):
        if isinstance(index, int):
            self.array[index] = value
        else:
            self.setAttr(index, value)

    def delIndex(self, index):
        if isinstance(index, int):
            del self.array[index]
        else:
            self.delAttr(index)

    def push(self, item):
        self.array.append(item)

    @property
    def length(self):
        return len(self.array)

    @jsc
    def map(self):
        return """
            function map(fn) {
                out = []
                for (let i=0; i < this.length; i++) {
                    let v = fn(this[i])
                    out.push(v)
                }
                return out
            }
        """

    def concat(self, *sequences):

        for seq in sequences:
            self.array.extend(seq.array)

        return self

    def join(self, string):

        seq = [str(s) for s in self.array]
        return JsString(string.value.join(seq))

class JsSet(JsObject):
    type_name = "Set"

    def __init__(self, args=None):
        super(JsSet, self).__init__(None)

        if args:
            self.seq = set(args)
        else:
            self.seq = set()

def _apply_value_operation(cls, op, a, b):
    if not isinstance(b, JsObject):
        b = cls(b)

    if isinstance(a, JsString) or isinstance(b, JsString):
        if isinstance(a, (int, float)):
            a = JsString(a)
        if isinstance(b, (int, float)):
            b = JsString(b)
        return JsString(op(a.value, b.value))
    else:
        return JsNumber(op(a.value, b.value))

class JsNumberType(type):
    def __new__(metacls, name, bases, namespace):
        cls = super().__new__(metacls, name, bases, namespace)

        for name in operands:
            if not hasattr(cls, name):
                op = getattr(operator, name)
                setattr(cls, name, lambda a, b, op=op: _apply_value_operation(cls, op, a, b))

        for name, key in operandsr:
            if not hasattr(cls, name):
                op = getattr(operator, key)
                setattr(cls, name, lambda b, a, op=op: _apply_value_operation(cls, op, a, b))

        return cls

class JsNumber(JsObject, metaclass=JsNumberType):
    def __init__(self, value=0):
        super(JsNumber, self).__init__()

        self.value = value

    def __repr__(self):
        return "<JsNumber(%s)>" % self.value

    def serialize(self, stream):
        pass

    def deserialize(self, stream):
        pass

class JsStringType(type):
    def __new__(metacls, name, bases, namespace):
        cls = super().__new__(metacls, name, bases, namespace)

        for name in operands:
            if not hasattr(cls, name):
                op = getattr(operator, name)
                setattr(cls, name, lambda a, b, op=op: _apply_value_operation(cls, op, a, b))

        for name, key in operandsr:
            if not hasattr(cls, name):
                op = getattr(operator, key)
                setattr(cls, name, lambda b, a, op=op: _apply_value_operation(cls, op, a, b))

        return cls

class JsString(JsObject, metaclass=JsStringType):

    def __init__(self, value=''):
        super(JsString, self).__init__(None)
        if isinstance(value, JsString):
            value = value.value
        self.value = str(value)

    def __repr__(self):
        return "<JsString(%r)>" % self.value

    def __str__(self):
        # "<JsString(%s)>" %
        return self.value

    def serialize(self, stream):
        data = self.value.encode("utf-8")
        stream.write(opcodes.LEB128u(len(data) + 1))
        stream.write(data)
        stream.write(b"\x00")

    def deserialize(self, stream):
        length = opcodes.read_LEB128u(stream)
        data = stream.read(length - 1)
        stream.read(1) # discard zero byte
        return JsString(data.decode("utf-8"))

    def getIndex(self, index):
        if index < len(self.value):
            return self.value[index]
        print("get undefined index %s" % index)
        return JsUndefined.instance

    def __eq__(self, other):
        if isinstance(other, JsString):
            other = other.value
        return self.value == other

    def __bool__(self):
        return bool(self.value)

    def __hash__(self):
        return self.value.__hash__()


    @property
    def length(self):
        return len(self.value)


    def indexOf(self, substr):
        try:
            return self.value.index(substr.value)
        except ValueError as e:
            return -1

    def lastIndexOf(self, substr):
        try:
            return self.value.rindex(substr.value)
        except ValueError as e:
            return -1

    def match(self, regex):
        return bool(regex.reg.match(self.value))

class JsUndefined(JsObject):
    instance = None
    def __init__(self):
        super(JsUndefined, self).__init__()
        if JsUndefined.instance is not None:
            raise RunTimeError("cannot construct singleton")

    def __repr__(self):
        return "<JsUndefined()>"

    def __str__(self):
        return "undefined"

    def __bool__(self):
        return False

    def serialize(self, stream):
        pass

    def deserialize(self, stream):
        pass

JsUndefined.instance = JsUndefined()

class JsTimerFactory(object):
    def __init__(self, runtime):
        super(JsTimerFactory, self).__init__()
        self.runtime = runtime

        self.nextTimerId = 1
        self.timers = {}
        self.intervals = {}
        self.queue = []

    def _setInterval(self, fn, delay, *args):

        timerId = self.nextTimerId
        self.nextTimerId += 1

        timeout = time.time() + delay/1000.0

        posargs = JsObject()

        frame = self.runtime._new_frame(fn, len(args), args, JsObject())
        stack = [frame]

        self.intervals[timerId] = (timeout, delay, stack)

        self.queue.append((timeout, timerId))

        return timerId

    def _setTimeout(self, fn, delay, *args):

        timerId = self.nextTimerId
        self.nextTimerId += 1

        timeout = time.time() + delay/1000.0

        frame = self.runtime._new_frame(fn, len(args), args, JsObject())
        stack = [frame]

        self.timers[timerId] = (timeout, delay, stack)

        self.queue.append((timeout, timerId))

        return timerId

    def _clearTimeout(self, fn, delay, *args):
        pass

    def _wait(self):
        """
         wait up to 5 seconds for any timer to expire
        """

        if len(self.timers) == 0:
            return False

        now = time.time()

        expires_in = 5
        for _, (timeout, delay, stack) in self.timers.items():
            expires_in = min(timeout - now, expires_in)

        if expires_in > 0:
            time.sleep(expires_in)

            # TODO: this pushes a value on the stack for every call
            #frame = self.stack_frames[-1]
            #frame.sp -= 3

        return len(self.timers)

    def check(self):

        if self.queue:

            now = time.time()
            if now > self.queue[0][0]:
                timeout, timerId = self.queue.pop(0)

                if timerId in self.timers:
                    stack = self.timers[timerId][2]
                    del self.timers[timerId]
                    return stack
        return None

class JsPromiseFactory(object):
    def __init__(self, runtime):
        super(JsPromiseFactory, self).__init__()
        self.runtime = runtime

    def __call__(self, callback=None):
        return JsPromise(callback)

class JsPromise(JsObject):

    PENDING = 1
    FULFILLED = 2
    REJECTED = 3

    def __init__(self, callback=None):
        # callback: (resolve, reject) => {}
        super(JsPromise, self).__init__()
        self.callback = callback
        self._state = JsPromise.PENDING
        self._result = None
        self._error = None

        setattr(self, "then", self._then)
        setattr(self, "catch", self._catch)
        setattr(self, "finally", self._finally)

        self._invoke()

    def _invoke(self):

        if isinstance(self.callback, JsFunction):
            runtime = VmRuntime()
            runtime.initfn(self.callback, [self._resolve, self._reject], JsObject())
            rv, _ = runtime.run()
        else:
            try:
                rv = self.callback()
                self._resolve(rv)
            except Exception as e:
                self._reject(e)

        if self._state == JsPromise.PENDING:
            self._state = JsPromise.REJECTED

        return

    def _resolve(self, res):
        print("resolve promise", res)
        self._state = JsPromise.FULFILLED
        self._result = res

    def _reject(self, err):
        print("reject promise", res)
        self._state = JsPromise.REJECTED
        self._error = err

    @jsc
    def _then(self):
        return """
            function _then(onFulfilled, onRejected) {
                // onFulfilled : value => {}
                // onRejected : reason => {}

                // TODO: wait for state to be 2 or 3

                console.log(this._state)
                if (this._state === 2) {
                    console.log(this._state, "accept", this, this._result)
                    if (onFulfilled) {
                        onFulfilled(this._result)
                    }
                } else {
                    console.log(this._state, "reject", this._error)
                    if (onRejected) {
                        onRejected(this._error)
                    }
                }

                return this
            }
        """

    @jsc
    def _catch(self):
         return """
            function _catch(onRejected) {
                return this._then(undefined, onRejected)
            }
        """

    @jsc
    def _finally(self):
         return """
            function _finally(onFinally) {
                return this._then(onFinally, onFinally)
            }
        """

def fetch(url, parameters):

    return JsPromise(lambda: "<html/>")

class JsDocument(JsObject):

    def __init__(self):
        super(JsDocument, self).__init__()

        self.head = JsElement()

    @staticmethod
    def createElement(name):

        elem = JsElement()

        elem.sheet = JsElement()

        return elem

class JsElement(JsObject):

    def __init__(self):
        super(JsElement, self).__init__(None)

        self.rules = JsArray()
        self.children = []

    def appendChild(self, child):
        self.children.append(child)
        print("children", self.children)

    def insertRule(self, text, index=0):
        self.rules.push(text)

    def addRule(self, selector, text):
        self.insertRule(selector + " {" + text + "}", self.rules.length)

class JsWindow(JsObject):

    def __init__(self):
        super(JsWindow, self).__init__()



    def addEventListener(self, event, callback):
        pass

    def requestIdleCallback(self, callback, options):
        pass

class JsNavigator(JsObject):

    def __init__(self):
        super(JsNavigator, self).__init__()

        self.appVersion = JsString("0")
        self.userAgent = JsString("daedalus")
        self.appName = JsString("daedalus")

class JsRegExp(object):
    def __init__(self, expr, flags):
        super(JsRegExp, self).__init__()

        iflags = 0

        cflags = {
            "i": re.IGNORECASE,
        }

        for c in flags.value:
            if c in cflags:
                iflags |= cflags[c]

        self.reg = re.compile(expr.value, iflags)

# ---

class VmStackFrame(object):

    def __init__(self, module, fndef, locals, cells):
        super(VmStackFrame, self).__init__()
        self.fndef = fndef
        self.module = module
        self.locals = locals
        self.cells = cells
        self.local_names = fndef.local_names
        self.globals = fndef.globals
        #self.cells = {} if cells is None else cells
        self.blocks = []
        self.stack = []
        self.sp = 0

class VmTryBlock(object):

    def __init__(self, catch_ip, finally_ip):
        super(VmTryBlock, self).__init__()
        self.catch_ip = catch_ip
        self.finally_ip = finally_ip
        self.flag_catch = False
        self.flag_finally = False

    def target(self):
        # returns the target instruction pointer when an exception is thrown
        # the first time an exception is thrown in a block, go to the
        # catch block. an exception thrown inside the catch handler will
        # instead jump to the finally block
        if self.flag_catch:
            return self.finally_ip
        else:
            return self.catch_ip

class VmExceptionContext(object):

    def __init__(self, ip, fndef, value, other):
        super(VmExceptionContext, self).__init__()
        self.ip = ip
        self.fndef = fndef
        self.value = value
        self.handled = False
        self.other = other  # previous exception

binary_op = {
    opcodes.math.ADD: operator.__add__,
    opcodes.math.SUB: operator.__sub__,
    opcodes.math.MUL: operator.__mul__,
    opcodes.math.DIV: operator.__truediv__,
    opcodes.math.REM: operator.__mod__,
    opcodes.math.EXP: operator.__pow__,
    opcodes.math.SHIFTL: operator.__lshift__,
    opcodes.math.SHIFTR: operator.__rshift__,
    opcodes.math.BITWISE_AND: operator.__and__,
    opcodes.math.BITWISE_XOR: operator.__xor__,
    opcodes.math.BITWISE_OR: operator.__or__,

    opcodes.comp.LT: operator.__lt__,
    opcodes.comp.LE: operator.__le__,
    opcodes.comp.EQ: operator.__eq__,
    opcodes.comp.NE: operator.__ne__,
    opcodes.comp.GE: operator.__ge__,
    opcodes.comp.GT: operator.__gt__,

    opcodes.comp.TEQ: operator.__eq__,
    opcodes.comp.TNE: operator.__ne__,

    opcodes.math.AND: lambda a, b: (a and b),
    opcodes.math.OR: lambda a, b: (a or b),

}

unary_op = {
    opcodes.math.NEGATIVE: operator.__neg__,
    opcodes.math.POSITIVE: operator.__pos__,
    opcodes.math.BITWISE_NOT: operator.__invert__,

    opcodes.math.NOT: lambda a: (not a),

}

class VmRuntime(object):
    def __init__(self, builtins=None):
        super(VmRuntime, self).__init__()

        self.stack_frames = []
        self.exception = None

        self.enable_diag = False
        self.builtins = builtins

    def initfn(self, fn, args, kwargs):

        frame = self._new_frame(fn, len(args), args, kwargs)

        self.stack_frames = [frame]

        self._init_builtins()

    def init(self, module):

        cells =JsObject()

        locals = JsObject()
        locals.setAttr("this", JsUndefined.instance)

        self.stack_frames = [VmStackFrame(module, module.functions[0], locals, cells)]

        self._init_builtins()

    def _init_builtins(self):

        console = lambda: None
        console.log = print
        _math = lambda: None
        _math.floor = math.floor
        _math.ceil = math.ceil
        _math.random = random.random

        if self.builtins is None:
            self.builtins = {}
            self.builtins['console'] = console
            self.builtins['Math'] = _math
            self.builtins['document'] = JsDocument()
            self.builtins['Promise'] = JsPromiseFactory(self)
            self.builtins['fetch'] = fetch
            self.builtins['Set'] = JsSet
            self.builtins['Array'] = JsArray
            self.builtins['Object'] = JsObjectCtor()
            self.builtins['window'] = JsWindow()
            self.builtins['navigator'] = JsNavigator()
            self.builtins['parseFloat'] = lambda x: x
            self.builtins['parseInt'] = lambda x, base=10: x
            self.builtins['isNaN'] = lambda x: False
            self.builtins['RegExp'] = JsRegExp

        # these must be unqiue to the runtime
        self.timer = JsTimerFactory(self)
        self.builtins['setTimeout'] = self.timer._setTimeout
        self.builtins['setInterval'] = self.timer._setInterval
        self.builtins['clearTimeout'] = self.timer._clearTimeout
        self.builtins['wait'] = self.timer._wait

    def _compile_fn(self, text, debug=False):
        tokens = Lexer().lex(text)
        parser = Parser()
        parser.feat_xform_optional_chaining = True
        parser.python = True
        ast = parser.parse(tokens)

        xform = TransformIdentityScope()
        xform.disable_warnings=True
        xform.transform(ast)

        compiler = VmCompiler()
        module = compiler.compile(ast)
        if debug:
            print("ast", ast.toString(1))
            module.dump()

        fn = JsFunction(module, module.functions[1], None, None, None)
        return fn

    def _unwind(self):

        while self.stack_frames:
            frame = self.stack_frames[-1]
            # if this frame has an exception handler
            if frame.blocks:
                block = frame.blocks[-1]
                # if the finally block has not yet been entered
                if not block.flag_finally:
                    return frame, block
                else:
                    frame.blocks.pop()
            else:
                self.stack_frames.pop()

        return None, None

    def run(self):

        try:

            return self._run()

        except Exception as e:
            if self.stack_frames:
                print("***")
                print("a python error was caught while running javascript")
                for idx, frame in enumerate(reversed(self.stack_frames)):

                    print("frame", idx)
                    # print(frame.locals)
                    # print(frame.globals)
                    print("  path", frame.module.path)
                    instr = frame.fndef.instrs[frame.sp]
                    print("  sp", frame.sp, "line", instr.line, "column", instr.index)
                    print("***")
            raise e


    def _new_frame(self, func, argc, args, kwargs):
        posargs = kwargs #JsObject()

        if func.bind_target:
            posargs.setAttr("this", func.bind_target)
        else:
            posargs.setAttr("this", posargs)

        for i, lbl in enumerate(func.fndef.arglabels):

            if i < len(args):
                val = args[i] # given value
            elif not func.args:
                val = JsUndefined.instance
            else:
                val = func.args[i] # default value

            if not posargs._hasAttr(lbl):
                posargs.setAttr(lbl, val)

        # TODO: rest parameters
        rest = []
        if len(args) > len(func.fndef.arglabels):
            rest = args[len(func.fndef.arglabels):]
        rest = JsArray(rest)

        if func.fndef.rest_name is not None:
            posargs.setAttr(func.fndef.rest_name, rest)

        # cell var fix for when a function argument is also a cell var
        # store the positional argument as a cell var instead of a local var
        for arglabel in func.fndef.arglabels:
            if arglabel in func.fndef.cell_names:
                if not func.cells._hasAttr(arglabel):
                    ref = VmReference(arglabel, JsUndefined.instance)
                    func.cells.setAttr(arglabel, ref)
                ref = func.cells.getAttr(arglabel)
                ref.value = posargs.getAttr(arglabel)

        new_frame = VmStackFrame(func.module, func.fndef, posargs, func.cells)

        return new_frame

    def _run(self):

        frame = self.stack_frames[-1]
        instrs = frame.fndef.instrs
        return_value = None

        history = []

        while frame.sp < len(instrs):

            tstack = self.timer.check()
            if tstack != None:
                history.append((self.stack_frames, frame, instrs, return_value))
                self.stack_frames = tstack
                frame = tstack[-1]
                instrs = frame.fndef.instrs
                return_value = None

            instr = instrs[frame.sp]

            if self.enable_diag:
                #name = frame.local_names[instr.args[0]]
                extra = instr.getArgString(frame.fndef.globals, frame.local_names, frame.fndef.cell_names)
                print("%2d %4d %4d %s %s" % (len(self.stack_frames), frame.sp, instr.line, instr.opcode, extra))

            if instr.opcode == opcodes.ctrl.NOP:
                pass
            elif instr.opcode == opcodes.ctrl.IF:
                tos = frame.stack.pop()
                # TODO: check if 'falsey'
                if not tos:
                    frame.sp += instr.args[0]
                    continue
            elif instr.opcode == opcodes.ctrl.IFNULL:
                tos = frame.stack.pop()
                if tos is JsUndefined.instance or tos is None:
                    frame.sp += instr.args[0]
                    continue
            elif instr.opcode == opcodes.ctrl.END:

                pass
            elif instr.opcode == opcodes.ctrl.LOOP:

                pass
            elif instr.opcode == opcodes.ctrl.ELSE:
                frame.sp += instr.args[0]
                continue
            elif instr.opcode == opcodes.ctrl.JUMP:
                frame.sp += instr.args[0]
                continue
            elif instr.opcode == opcodes.ctrl.CALL:

                kwargs = frame.stack.pop()

                argc = instr.args[0]
                args = []
                for i in range(argc):
                    args.insert(0, frame.stack.pop())
                func = frame.stack.pop()

                if isinstance(func, JsFunction):

                    new_frame = self._new_frame(func, argc, args, kwargs)

                    self.stack_frames.append(new_frame)
                    frame.sp += 1
                    frame = self.stack_frames[-1]
                    instrs = frame.fndef.instrs
                    continue
                elif callable(func):
                    # TODO: python callable may return a JsFunction
                    #       derived Immediatley nvokable Function
                    #       which must be avaulated to get the true
                    #       return value
                    _rv = func(*args, **kwargs.data)
                    frame.stack.append(_rv)
                else:
                    print("Error at line %d column %d" % (instr.line, instr.index))
            elif instr.opcode == opcodes.ctrl.CALL_EX:
                kwargs = frame.stack.pop()
                posargs = frame.stack.pop()
                func = frame.stack.pop()
                print("CALL_EX not implemented")
                #print(func, posargs, kwargs)
                frame.stack.append(JsUndefined.instance)
            elif instr.opcode == opcodes.ctrl.RETURN:
                rv = frame.stack.pop()
                if frame.stack:
                    print("stack", frame.stack)
                    print("warning: stack not empty")
                self.stack_frames.pop()
                if len(self.stack_frames) == 0:
                    return_value = rv
                    break
                else:
                    frame = self.stack_frames[-1]
                    instrs = frame.fndef.instrs
                    frame.stack.append(rv)
                    continue
            elif instr.opcode == opcodes.ctrl.TRY:

                tgtif = (frame.sp + frame.stack.pop() - 1)
                #assert frame.fndef.instrs[tgtif].opcode == opcodes.ctrl.FINALLY

                tgtic = (frame.sp + frame.stack.pop() - 2)
                #assert frame.fndef.instrs[tgtic].opcode == opcodes.ctrl.CATCH

                frame.blocks.append(VmTryBlock(tgtic, tgtif))
            elif instr.opcode == opcodes.ctrl.TRYEND:
                frame.blocks.pop()

                if self.exception:
                    if self.exception.handled:
                        self.exception = None
                    else:
                        frame_, block = self._unwind()
                        if frame_ is None:
                            print("unhandled exception")
                            break
                        else:
                            frame = frame_
                            instrs = frame.fndef.instrs
                            frame.sp = block.target()
                            continue
            elif instr.opcode == opcodes.ctrl.CATCH:

                if self.exception is None:
                    raise RunTimeError("no exception")

                frame.stack.append(self.exception.value)
                self.exception.handled = True
                frame.blocks[-1].flag_catch = True
            elif instr.opcode == opcodes.ctrl.FINALLY:

                frame.blocks[-1].flag_finally = True
            elif instr.opcode == opcodes.ctrl.THROW:

                # TODO: if throw is in side of a catch block... jump to finally instead
                self.exception = VmExceptionContext(frame.sp, frame.fndef, frame.stack.pop(), self.exception)

                frame_, block = self._unwind()
                if frame is None:
                    print("unhandled exception")
                    break
                else:
                    frame = frame_
                    instrs = frame.fndef.instrs
                    frame.sp = block.target()
                    continue
            elif instr.opcode == opcodes.localvar.SET:
                name = frame.local_names[instr.args[0]]
                frame.locals.setAttr(name, frame.stack.pop())
            elif instr.opcode == opcodes.localvar.GET:
                name = frame.local_names[instr.args[0]]
                frame.stack.append(frame.locals.getAttr(name))
            elif instr.opcode == opcodes.localvar.DELETE:
                name = frame.local_names[instr.args[0]]
                frame.locals.delAttr(name)
            elif instr.opcode == opcodes.globalvar.SET:
                name = frame.globals.names[instr.args[0]]
                frame.globals.values[name] = frame.stack.pop()
            elif instr.opcode == opcodes.globalvar.GET:

                name = frame.globals.names[instr.args[0]]
                if name in frame.globals.values:
                    frame.stack.append(frame.globals.values[name])
                elif name in self.builtins:
                    frame.stack.append(self.builtins[name])
                else:
                    frame.stack.append(JsUndefined.instance)
            elif instr.opcode == opcodes.globalvar.DELETE:
                name = frame.globals.names[instr.args[0]]
                del frame.globals.values[name]
            elif instr.opcode == opcodes.cellvar.LOAD:
                name = frame.fndef.cell_names[instr.args[0]]
                if not frame.cells._hasAttr(name):
                    frame.cells.setAttr(name, VmReference(name, JsUndefined.instance))
                tos = frame.cells.getAttr(name)
                frame.stack.append(tos)
            elif instr.opcode == opcodes.cellvar.SET:
                name = frame.fndef.cell_names[instr.args[0]]
                if not frame.cells._hasAttr(name):
                    frame.cells.setAttr(name, VmReference(name, JsUndefined.instance))
                tos = frame.stack.pop()
                frame.cells.getAttr(name).value = tos
            elif instr.opcode == opcodes.cellvar.GET:
                name = frame.fndef.cell_names[instr.args[0]]
                if not frame.cells._hasAttr(name):
                    frame.cells.setAttr(name, VmReference(name, JsUndefined.instance))
                tos = frame.cells.getAttr(name).value
                frame.stack.append(tos)
            elif instr.opcode == opcodes.cellvar.DELETE:
                name = frame.fndef.cell_names[instr.args[0]]
                frame.cells.setAttr(name, VmReference(name, JsUndefined.instance))
            elif instr.opcode == opcodes.stack.ROT2:
                top1 = frame.stack.pop()
                top2 = frame.stack.pop()

                frame.stack.append(top1)
                frame.stack.append(top2)
            elif instr.opcode == opcodes.stack.ROT3:
                top1 = frame.stack.pop()
                top2 = frame.stack.pop()
                top3 = frame.stack.pop()

                frame.stack.append(top1)
                frame.stack.append(top3)
                frame.stack.append(top2)
            elif instr.opcode == opcodes.stack.ROT4:
                top1 = frame.stack.pop()
                top2 = frame.stack.pop()
                top3 = frame.stack.pop()
                top4 = frame.stack.pop()

                frame.stack.append(top1)
                frame.stack.append(top4)
                frame.stack.append(top3)
                frame.stack.append(top2)
            elif instr.opcode == opcodes.stack.DUP:

                frame.stack.append(frame.stack[-1])
            elif instr.opcode == opcodes.stack.POP:

                frame.stack.pop()
            elif instr.opcode == opcodes.obj.GET_ATTR:
                name = frame.local_names[instr.args[0]]
                obj = frame.stack.pop()
                if isinstance(obj, JsObject):
                    val = obj.getAttr(name)
                elif isinstance(obj, int):
                    val = lambda x: hex(obj)
                else:
                    val = getattr(obj, name)

                frame.stack.append(val)
            elif instr.opcode == opcodes.obj.SET_ATTR:

                name = frame.local_names[instr.args[0]]
                obj = frame.stack.pop()
                val = frame.stack.pop()
                if isinstance(obj, JsObject):
                    obj.setAttr(name, val)
                else:
                    setattr(obj, name, val)
            elif instr.opcode == opcodes.obj.DEL_ATTR:
                name = frame.local_names[instr.args[0]]
                obj = frame.stack.pop()
                if isinstance(obj, JsObject):
                    obj.delAttr(name)
                else:
                    delattr(obj, name)
            elif instr.opcode == opcodes.obj.HAS_ATTR:
                obj = frame.stack.pop()
                name = frame.stack.pop()
                frame.stack.append(int(obj._hasAttr(name)))
            elif instr.opcode == opcodes.obj.GET_TYPENAME:
                obj = frame.stack.pop()
                print("typename of", obj)
                if obj is JsUndefined.instance:
                    val = JsString("undefined")
                elif isinstance(obj, JsString):
                    val = JsString("string")
                elif isinstance(obj, JsObject):
                    print("typeaname of ", obj)
                    val = JsString(obj.type_name)
                else:
                    val = "<unknown>"
                frame.stack.append(val)
            elif instr.opcode == opcodes.obj.GET_INDEX:
                obj = frame.stack.pop()
                index = frame.stack.pop()
                if isinstance(obj, JsObject):
                    val = obj.getIndex(index)
                else:
                    val = obj[index]

                frame.stack.append(val)
            elif instr.opcode == opcodes.obj.SET_INDEX:

                obj = frame.stack.pop()
                index = frame.stack.pop()
                val = frame.stack.pop()
                if isinstance(obj, JsObject):
                    obj.setIndex(index, val)
                else:
                    obj[index] = val
            elif instr.opcode == opcodes.obj.DEL_INDEX:
                obj = frame.stack.pop()
                index = frame.stack.pop()
                if isinstance(obj, JsObject):
                    obj.delIndex(index)
                else:
                    del obj[index]
            elif instr.opcode == opcodes.obj.CREATE_FUNCTION:

                fnidx = instr.args[0]

                tos = frame.stack.pop()
                if isinstance(tos, JsArray):
                    cellvars = tos
                    bind = frame.stack.pop()
                else:
                    cellvars = JsArray()
                    bind = tos
                kwargs = frame.stack.pop()
                argc = frame.stack.pop()

                if bind:
                    bind_target = frame.locals
                else:
                    bind_target = None
                # print("Create function (this)", frame.locals)

                args = []
                for i in range(argc):
                    args.insert(0, frame.stack.pop())

                fndef = frame.module.functions[fnidx]
                fn = JsFunction(frame.module, fndef, args, kwargs, bind_target)

                cells = []
                for ref in cellvars.array:
                    if ref.name in fndef.free_names:
                        cells.append((ref.name, VmReference(ref.name, ref.value)))
                    else:
                        cells.append((ref.name, ref))
                fn.cells = JsObject(cells)
                frame.stack.append(fn)
            elif instr.opcode == opcodes.obj.UPDATE_ARRAY:
                tos1 = frame.stack.pop()
                tos2 = frame.stack.pop()
                tos2.array.extend(tos1.array)
                frame.stack.append(tos2)
            elif instr.opcode == opcodes.obj.UPDATE_OBJECT:
                tos1 = frame.stack.pop()
                tos2 = frame.stack.pop()
                tos2.data.update(tos1.data)
                frame.stack.append(tos2)
            elif instr.opcode == opcodes.obj.CREATE_OBJECT:

                args = []
                for i in range(instr.args[0]):
                    val = frame.stack.pop()
                    key = frame.stack.pop()
                    args.append((key, val))

                frame.stack.append(JsObject(args))
            elif instr.opcode == opcodes.obj.CREATE_CLASS:

                raise NotImplementedError()
            elif instr.opcode == opcodes.obj.CREATE_ARRAY:

                args = []
                for i in range(instr.args[0]):
                    val = frame.stack.pop()
                    args.insert(0, val)

                frame.stack.append(JsArray(args))
            elif instr.opcode == opcodes.obj.CREATE_TUPLE:

                args = []
                for i in range(instr.args[0]):
                    val = frame.stack.pop()
                    args.append(val)

                frame.stack.append(JsArray(args))
            elif instr.opcode == opcodes.obj.CREATE_SET:

                raise NotImplementedError()
            elif instr.opcode in unary_op:
                rhs = frame.stack.pop()
                frame.stack.append(unary_op[instr.opcode](rhs))
            elif instr.opcode in binary_op:
                rhs = frame.stack.pop()
                lhs = frame.stack.pop()
                frame.stack.append(binary_op[instr.opcode](lhs, rhs))
            elif instr.opcode == opcodes.const.INT:

                frame.stack.append(instr.args[0])
            elif instr.opcode == opcodes.const.FLOAT32:

                frame.stack.append(instr.args[0])
            elif instr.opcode == opcodes.const.FLOAT64:

                frame.stack.append(instr.args[0])
            elif instr.opcode == opcodes.const.STRING:

                frame.stack.append(frame.globals.constdata[instr.args[0]])
            elif instr.opcode == opcodes.const.BYTES:

                raise NotImplementedError()
            elif instr.opcode == opcodes.const.BOOL:
                if instr.args[0]:
                    frame.stack.append(True)
                else:
                    frame.stack.append(False)
            elif instr.opcode == opcodes.const.NULL:
                frame.stack.append(None)
            elif instr.opcode == opcodes.const.UNDEFINED:
                frame.stack.append(JsUndefined.instance)
            else:
                raise Exception("%r" % instr)

            frame.sp += 1

            if frame.sp >= len(frame.fndef.instrs):

                self.stack_frames.pop()

                if history:
                    self.stack_frames, frame, instrs, return_value = history.pop()
                else:

                    if self.timer._wait():

                        if len(self.stack_frames) == 0:
                            stack = self.timer.check()
                            if stack:
                                # TODO: this clobers the return value
                                # when switching to the timer function
                                self.stack_frames = stack
                                frame = self.stack_frames[-1]
                                instrs = frame.fndef.instrs
                                return_value = None
                                continue
                    if len(self.stack_frames) == 0:
                        break

                    frame = self.stack_frames[-1]
                    instrs = frame.fndef.instrs
                    frame.stack.append(None)

                continue
        print("runtime exit", self.timer.queue)

        return return_value, frame.globals

class VmLoader(object):
    def __init__(self,):
        super(VmLoader, self).__init__()

    def _load_path(self, path):
        text = open(path).read()

        return self._load_text(text)

    def _load_text(self, text):

        tokens = Lexer().lex(text)
        parser = Parser()
        parser.feat_xform_optional_chaining = True
        parser.python = True
        ast = parser.parse(tokens)

        xform = TransformIdentityScope()
        xform.disable_warnings=True
        xform.transform(ast)

        xform = VmTransform()
        xform.transform(ast)

        #print(ast.toString(1))

        compiler = VmCompiler()
        module = compiler.compile(ast)

        return module

    def _fix_mod(self, mod):

        root = os.path.split(os.path.abspath(mod.path))[0]

        for i in range(len(mod.includes)):
            mod.includes[i] = os.path.normpath(os.path.join(root, mod.includes[i]))

    def _load(self, root_mod, root_dir, root_name):

        root_mod.depth = 0

        self._fix_mod(root_mod)

        visited = {root_name: root_mod}
        includes = [(1, p) for p in root_mod.includes]

        while includes:
            depth, inc_path = includes.pop()

            if inc_path in visited:
                continue
            print("loading", depth, inc_path)

            dep_mod = self._load_path(inc_path)
            dep_mod.depth = depth
            dep_mod.path = inc_path
            self._fix_mod(dep_mod)

            visited[inc_path] = dep_mod

            includes.extend([(depth+1, p) for p in dep_mod.includes])

        mods = sorted(visited.values(), key=lambda m: m.depth, reverse=True)

        for mod in mods:
            print(mod.depth, mod.path)

            for inc_path in mod.includes:
                inc_path = os.path.normpath(os.path.join(root_dir, inc_path))

                mod2 = visited[inc_path]

                runtime = VmRuntime()
                #runtime.enable_diag = True
                runtime.init(mod2)
                try:
                    rv, mod2_globals = runtime.run()
                except Exception as e:
                    print("error in ", mod2.path)
                    raise e

                for name in mod.globals.names:
                    if name in mod2_globals.values and name not in mod.globals.values:
                        mod.globals.values[name] = mod2_globals.values[name]

        print("=*" + "="*68)
        runtime = VmRuntime()
        runtime.enable_diag = True
        runtime.init(root_mod)
        rv, mod_globals = runtime.run()

        print("return value", rv)
        print("globals", mod_globals.values)


    def run_path(self, path):

        path = os.path.abspath(path)
        root_mod = self._load_path(path)
        root_dir = os.path.split(path)[0]
        root_mod.path = path

        return self._load(root_mod, root_dir, path)

    def run_text(self, text):

        root_mod = self._load_text(text)
        root_dir = "./"
        root_name = "__main__"
        root_mod.path = root_name

        return self._load(root_mod, root_dir, root_name)

def main():

    text1 = """

    i = 0

    while (i < 100) {

        if (i%2 == 0) {
            i += 1
            continue;
        } else if (i > 10) {
            break;
        } else {
            i += 3
        }
    }
    """

    text1 = """
        console.log(1)
    """

    text1 = """

        x = [4,8,12]
        x[1] = 5
        console.log(x[1])
        console.log(x.length)

    """





    text1 = """

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

        function fn_try_catch_finally() {
            try {
                fn_throw()
            } catch (ex) {
                g |= 2
            } finally {
                g |= 4
            }
        }

        function fn_try_catch_finally_2() {
            try {
                fn_try_finally()
            } catch (ex) {
                g |= 8
            } finally {
                g |= 16
            }
        }

        //g = 0
        //fn_try_finally()
        //console.log("1:", g)

        //g = 0
        //fn_try_catch_finally()
        //console.log("2:", g)

        g = 0
        fn_try_catch_finally_2()
        console.log("3:", g.toString(16))

    """



    text1 = """

    function g() {
        var x = 1;
        {
            var x = 2;
        }
        return x;
    }
    result=g() // 2
    """

    text1 = """

    function f() {
        let x = 1;
        {
            let x = 2;
        }
        return x;
    }
    result=f() // 1
    """

    text1 = """

    function f() {
        const x = 1;
        {
            const x = 2;
        }
        return x;
    }
    result=f() // 1
    """

    text1 = """

    let x = 4
    let y = 5
    let z = 6

    {
        let z=10, x=12
        let y=11
    }


    """

    text_fclass1 = """

    function f() {
        x = 5;
        return () => {this.x+=1; return this.x};
    }
    g1 = f()
    g2 = f()

    r1 = g1()
    r2 = g2()
    r3 = g1()
    r4 = g2()
    """

    text1 = """
        function f() {
            x = 1

            function g() { return x }

            x = x + 1

            return g()
        }

        r1 = f(); // 2
        r2 = f(); // 2
    """

    text1 = """

    let sum = 0

    for (let i=0; i<10; i++) {
        sum += i;
    }
    """

    render1 = """

        console.log("<HTML><BODY>Hello World</BODY></HTML>")
    """

    class0 = """
        function App(x) {

            this.get_x = () => {
                return this.x
            }

            this.x = x

            return this
        }

        y = App(7).get_x()
        console.log(y)
    """
    # compiler trasforms class into the above example
    class1 = """

        // export
        class App {
            constructor(x) {
                this.x = x;
            }

            get_x() {
                return this.x
            }
        }

        y = App(7).get_x()
        console.log(y)
    """

    class2 = """

        class P {
            constructor(x, y) {
                this.x = x
                this.y = y
            }
        }

        class T extends P {
            constructor(x, y) {
                //super = P.bind(this)
                super(x, y)
            }

            mul() {
                return this.x * this.y
            }
        }

        console.log(T(6, 7).mul())
    """


    array1 = """

        let a = [1, 2, 3]
        console.log(a.length, a[1])
        a.push(4)
        console.log(a.length, a[1])
    """

    promise1 = """
        p = Promise(()=>{return 1})
        //console.log()
        //console.log(fetch("/root", {}))
    """


    export1 = """

        //export let v1
        //export let v1, v2

        // export function a() {}
        export default function a() {}

    """

    set1 = """
        let s = new Set()
    """

    not1 = """
        let a = !true
    """

    # ----------
    # add these as  tests

    logical1 = """
        /*
        let a1 = [
            true && true,
            true && false,
            false && true,
            false && false,
        ]
        console.log(a1[0], a1[1], a1[2], a1[3])
        */
        //console.log(0, true && true)
        //console.log(1, true && false)
        //console.log(2, false && true)
        //console.log(3, false && false)

        console.log(0, true  || true)
        console.log(1, true  || false)
        console.log(2, false || true)
        console.log(3, false || false)

        //let a = 0 || 2
    """


    lambd4 = """

    // test 1
    //const f = (a)=>a
    //x = f(1)

    // test 2
    //const f = a => { return b => { return b+a } }
    //let x = f(6)(7)

    // test 3
    //const f = a => { return b => b+a }
    //let x = f(6)(7)

    // test 4
    const f = a => b => b+a
    let x = f(6)(7)

    """

    ternary1 = """
        let a = true?4:8
        let b = false?4:8
    """

    constructobj1 = """
        let a = 1, b = 2;
        let o = {a:a, b:b}
    """

    objectin1 = """
        let o = {a:1}
        let a1 = "a" in o
        let a2 = "b" in o
    """

    typeof1 = """
        //console.log(typeof({})==='object')

        class A { constructor() {} }
        let a = new A()
        let b = typeof(a)
    """

    spread1 = """
        let t = {b:3}
        let o = {a: 1, ...t, c: 5}
        let sum = o.a + o.b + o.c
    """

    delete1 = """
        let t = {a:1, b:3}
        delete t.a
        delete t['b']
        let l = Object.keys(t).length // should be zero
    """

    export2 = """

        export class A {
            //constructor() {}
        }
    """

    text1 = """
        a = [1,2,3]
        b = [...a]
    """

    text1 = """
        // 4 tests for working with undefined values

        // should return 4
        //let x = undefined || 4

        //let event = {}
        //event?.touches

        //f = () => {return 5}
        //r = f?.()

        //f = [1,2,3]
        //r = f?.[0]
    """

    text1 = """
        let w = 1 ?? 4          // 1
        let x = 0 ?? 4          // 0
        let y = undefined ?? 4  // 4
        let z = null ?? 4       // 4

    """
    # ----------

    # todo
    # binop ?? Nullish coalescing operator
    # binop ?. optional chaining
    # template strings
    # spread function call
    # regex
    # anonymous functions

    template_string1 = """

        let a = 1

        let s = `a=${a}`
    """

    text1 = """
        sum(...a)
    """

    text1 = """
        zz ??= 4 // 4
    """

    regex1 = """
        //let r = new Regex(a, b)
        let r = /a+b/g
    """

    instanceof1 = """
        let x = 1
        let y = x instanceof Function
    """

    text1 = """
        function f(a, ...rest) {
            return rest
        }

        console.log(f(1,2,3))
    """

    text1 = """
        f = () => {}
        rest = [2,3]
        f(1, ...rest)
    """

    text1 = """
        let c = 0;
        do {
            c++
        } while (c < 5);
    """

    mapping1 = """

        //function f(...rest) {
        //    console.log(rest)
        //}
        //f()

        //x = [1,2,3]
        //console.log(x[2])

        fn = x => x*x

        console.log([1,2,3].map(fn))
        console.log([1,2,3,4].length)

        //o = {a: 1, b: 2}
        //console.log(Object.keys(o).map(k => o[k]*5))

        //chars= "abc"
        //console.log(chars.length, chars[0])

    """

    keys1 = """

        o = {a:1}
        x = Object.keys(o)
        y = o.keys(o)
    """

    export_func_default1 = """

        export function parse(text=undefined) {
            return text
        }
    """
    text1 = """

        x=[].concat([1,2,3]).join("+")
    """

    text1 = """

        obj = {"_key": "_val"}
        Object.keys(obj).map(x => console.log(x, obj[x]))
    """

    text1 = """
        obj = {"background": "blue"}
        x = typeof(obj['background'])
    """

    text1 = """
        a = "A"
        b = "B"
        c = "C"
        d = "D"
        x = a + b + c + d
    """

    text1 = """
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

    text1 = """
        let s = "abc"
        if ((x=s.indexOf("r"))!=-1) {
            console.log(x)
        }
    """




    text1 = """
        x = window.dne === undefined
        y = true === undefined
    """


    text1 = """
        class A {
            constructor() {
                this.x1= y
            }
        }
        p1 = A.prototype
        p2 = A().prototype

    """

    text1 = """

        a = 123

        pi = 3.1415
        r = 6

        //s = `a=${a} b=${pi*r*r}m^2`
        s = `${pi*r*r}`


    """


    text1 = """

        include "./res/daedalus/daedalus.js"

        //console.log(generateStyleSheetName())
        //console.log(randomInt(0,100))
    """

    text1 = """
        x="abc".match(/A/i)
        y="def".match(/A/i)
    """

    text1 = """


        //setTimeout((x)=>{console.log(x)}, 500)
        function f(x) {
            console.log("hello " + x)
        }
        setTimeout(f, 500, "world")

        wait()
        console.log("wait over")
    """

    text1 = """


        const p = new Promise((resolve, reject) => {
            resolve('world')
        })

        p.then(res=>{console.log("Hello " + res)}).finally(res=>{console.log("done")})
    """

    text1 = """


        fetch("", {}).then(res => {console.log(res)})
    """

    text1 = """


        const p = new Promise((resolve, reject) => {
            setTimeout(()=>{resolve(true);}, 500)
        })

        p.then(res=>{console.log("done")})
    """

    if False:
        tokens = Lexer().lex(text1)
        parser = Parser()
        parser.feat_xform_optional_chaining = True
        parser.python = True
        ast = parser.parse(tokens)
        xform = TransformIdentityScope()
        xform.disable_warnings=True
        xform.transform(ast)

        xform = VmTransform()
        xform.transform(ast)

        print(ast.toString(1))

    #text1 = open("./res/daedalus/daedalus_util.js").read()
    """
    tokens = Lexer().lex(text1)
    parser = Parser()
    parser.feat_xform_optional_chaining = True
    parser.python = True
    ast = parser.parse(tokens)
    xform = TransformIdentityScope()
    xform.disable_warnings=True
    xform.transform(ast)

    print(ast.toString(1))
    compiler = VmCompiler()
    module = compiler.compile(ast)
    print("="*60)
    module.dump()

    print("="*60)
    for path in module.includes:
        print(path)
        mod2 = compile_file(path)
        runtime = VmRuntime()
        runtime.init(mod2)
        rv, globals = runtime.run()
        print(globals.values)
        for name in module.globals.names:
            if name in globals.values:
                if name not in module.globals.values:
                    module.globals.values[name] = globals.values[name]
    print("="*60)
    """

    # T_ANONYMOUS_FUNCTION
    # T_FOR_IN
    loader = VmLoader()
    #loader.load("./res/daedalus/daedalus.js")
    loader.run_text(text1)
    return

    runtime = VmRuntime()
    runtime.enable_diag = True
    runtime.init(module)
    try:
        rv, globals = runtime.run()
    except Exception as e:
        for i, frame in enumerate(reversed(runtime.stack_frames)):
            print()
            print("-"*60)
        raise

if __name__ == '__main__':
    main()