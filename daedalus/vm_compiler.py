#! cd .. && python -m daedalus.vm

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
from .lexer import Lexer, LexError
from .parser import Parser, ParseError
from .transform import TransformBaseV2

class VmInstruction(object):
    __slots__ = ['opcode', 'args', 'target', 'line', 'index']

    def __init__(self, opcode, *args, target=None, token=None):
        super(VmInstruction, self).__init__()
        self.opcode = opcode
        self.args = args
        #self.target = target


        #if len(args) != opcode.argcount:
        #    if opcode.value > 0x0F:
        #        raise Exception("%d %d" % (opcode.argcount, len(args)))

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
        #if self.target is not None:
        #    s += ": %d" % target
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

class VmModule(object):
    def __init__(self):
        super(VmModule, self).__init__()
        self.path = None
        self.globals = None
        self.functions = []

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

class VmClassTransform2(TransformBaseV2):

    def __init__(self):
        super().__init__()

        lexer = Lexer()
        parser = Parser()
        parser.disable_all_warnings = True

        template_string = """

        const CLASS_NAME = (function() {
            PROTOTYPE_X_Y = {}
            // TODO: super should be a magic variable or instance
            // either replace `super` with `JsSuper(this)`, or
            // have super reach in to the current stack frame.
            // when the instance is called or an attribute is retrieved
            // it must look up the correct constructor or attribute using
            // the __proto__ chain
            SUPER_X_Y = (CLASS_PARENT ?? (()=>{}))
            for (let name in SUPER_X_Y.prototype) {
                PROTOTYPE_X_Y[name] = SUPER_X_Y.prototype[name]
            }
            CLASS_METHODS
            function CLASS_NAME(CONSTRUCTOR_ARGS) {
                this.__proto__ ??= PROTOTYPE_X_Y
                this.constructor ??= CLASS_NAME
                this._super ??= SUPER_X_Y.bind(this)
                let _x_daedalus_prop;
                for (let name in this.__proto__) {
                    // TODO: continue in here does not work
                    _x_daedalus_prop = this.__proto__[name]
                    if (typeof(_x_daedalus_prop) === "function") {
                        _x_daedalus_prop = _x_daedalus_prop.bind(this)
                    }
                    if (name != '__proto__') {
                        this[name] = _x_daedalus_prop
                    }
                }
                delete _x_daedalus_prop;
                CLASS_CONSTRUCTOR
                return this
            }
            // these lines fix one test and break super()
            PROTOTYPE_X_Y['__proto__'] = SUPER_X_Y.prototype
            PROTOTYPE_X_Y['constructor'] = CLASS_NAME
            CLASS_NAME.name = CLASS_NAME_STRING
            CLASS_NAME.prototype = PROTOTYPE_X_Y
            //CLASS_NAME.parent = CLASS_PARENT
            return CLASS_NAME
        })()

        """

        tokens = lexer.lex(template_string)
        self.template = parser.parse(tokens).children[0]

    def _apply(self, cfg):

        cls = self.template.clone()

        stack = [cls]
        while stack:
            node = stack.pop()
            stack.extend(node.children)
            for i, child in enumerate(node.children):

                if child.value == 'CONSTRUCTOR_ARGS':
                    node.children = cfg['CONSTRUCTOR_ARGS']

                elif child.value in cfg:
                    node.children[i] = cfg[child.value].clone()

        return cls

    def visit(self, parent, token, index):

        # TODO: instance of keyword super must be replaced with this.super

        if token.type == Token.T_CLASS:
            self._visit_class(parent, token, index)

        if token.type == Token.T_KEYWORD and token.value == "super":

            parent.children[index] = Token(Token.T_GET_ATTR, token.line, token.index, ".", [
                Token(Token.T_KEYWORD, token.line, token.index, "this"),
                Token(Token.T_ATTR, token.line, token.index, "_super"),
            ])

    def _visit_class(self, parent, token, index):

        class_name = token.children[0]
        parent_class = token.children[1]
        block1 = token.children[2]

        class_name_string = Token(Token.T_STRING, 0, 0, repr(class_name.value))

        if parent_class.children:
            parent_token = parent_class.children[0]
            #class_parent_string = Token(Token.T_STRING, 0, 0, repr(parent_token.value))
        else:
            parent_token = Token(Token.T_KEYWORD, 0, 0, "undefined")
            #class_parent_string = Token(Token.T_STRING, 0, 0, repr(""))

        prototype = Token(Token.T_TEXT, 0, 0, "prototype_%d_%d" % (token.line, token.index))
        super_token = Token(Token.T_TEXT, 0, 0, "super_%d_%d" % (token.line, token.index))

        constructor = Token(Token.T_BLOCK, 0, 0, "{}")
        constructor_args = []
        methods = Token(Token.T_BLOCK, 0, 0, "{}")

        for meth in block1.children:

            if meth.children[0].value == "constructor":
                constructor_args = meth.children[1].children
                constructor = meth.children[2]
            else:
                meth.type = Token.T_ANONYMOUS_FUNCTION

                _attr =Token(Token.T_ATTR, token.line, token.index, meth.children[0].value)
                _getattr = Token(Token.T_GET_ATTR, token.line, token.index, ".", [prototype, _attr])
                _assign = Token(Token.T_ASSIGN, token.line, token.index, "=", [_getattr, meth])

                methods.children.append(_assign)

        cfg = {
            "CLASS_NAME": class_name,
            "CLASS_NAME_STRING": class_name_string,
            "CLASS_PARENT": parent_token,
            #"CLASS_PARENT_STRING": class_parent_string,
            "PROTOTYPE_X_Y": prototype,
            "SUPER_X_Y": super_token,
            "CLASS_CONSTRUCTOR": constructor,
            "CLASS_METHODS": methods,
            "CONSTRUCTOR_ARGS": constructor_args,
        }

        parent.children[index] = self._apply(cfg)

class VmTransform(TransformBaseV2):

    def visit(self, parent, token, index):

        if token.type == Token.T_TEMPLATE_STRING:
            self._visit_template_string(parent, token, index)

        if token.type == Token.T_REGEX:
            self._visit_regex(parent, token, index)

        if token.type == Token.T_INSTANCE_OF:
            self._visit_instance_of(parent, token, index)

        if token.type == Token.T_FOR_IN:
            self._visit_for_in(parent, token, index)

        if token.type == Token.T_FOR_OF:
            self._visit_for_of(parent, token, index)

        #if token.type == Token.T_KEYWORD and token.value == "super":
        #    token.type = Token.T_LOCAL_VAR

        if token.type == Token.T_KEYWORD and token.value == "finally":
            token.type = Token.T_ATTR

        if token.type == Token.T_VAR:
            return self._visit_var(parent, token, index)

        if token.type == Token.T_ASSIGN:
            self._visit_assign(parent, token, index)

        if token.type == Token.T_LAMBDA:
            return self._visit_lambda(parent, token, index)

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

    def _visit_instance_of(self, parent, token, index):

        lhs, rhs = token.children
        _name = Token(Token.T_GLOBAL_VAR, token.line, token.index, '_x_daedalus_js_instance_of')
        _arglist = Token(Token.T_ARGLIST, token.line, token.index, '()', [lhs, rhs])
        _call = Token(Token.T_FUNCTIONCALL, token.line, token.index, '', [_name, _arglist])

        parent.children[index] = _call

    def _visit_super(self, parent, token, index):

        token.type = Token.T_LOCAL_VAR

    def _visit_for_in(self, parent, token, index):
        """

        convert

            for (expr1 of expr2) {
                ...
            }

        Into:

            _iterator_$line_$index = Object.keys(expr2)[Symbol.iterator]()
            _iterator_result_$line_$index = _iterator_$line_$index.next()
            while (!_iterator_result_$line_$index.done) {
                expr1 = _iterator_result_$line_$index.value
                ...
                _iterator_result_$line_$index = _iterator_$line_$index.next()
            }

        """
        expr_var, expr_seq, body = token.children

        _object = Token(Token.T_GLOBAL_VAR, token.line, token.index, "Object")
        _attr = Token(Token.T_ATTR, token.line, token.index, "keys")
        _getattr = Token(Token.T_GET_ATTR, token.line, token.index, ".", [_object, _attr])
        _arglist =Token(Token.T_ARGLIST, token.line, token.index, "()", [expr_seq])
        _call = Token(Token.T_FUNCTIONCALL, token.line, token.index, "", [_getattr, _arglist])

        parent.children[index] = self._for_iter(token, expr_var, _call, body)

    def _visit_for_of(self, parent, token, index):
        """

        convert

            for (expr1 of expr2) {
                ...
            }

        Into:

            _iterator_$line_$index = expr2[Symbol.iterator]()
            _iterator_result_$line_$index = _iterator_$line_$index.next()
            while (!_iterator_result_$line_$index.done) {
                expr1 = _iterator_result_$line_$index.value
                ...
                _iterator_result_$line_$index = _iterator_$line_$index.next()
            }

        """
        expr_var, expr_seq, body = token.children
        parent.children[index] = self._for_iter(token, expr_var, expr_seq, body)

    def _visit_var(self, parent, token, index):
        # remove any  T_VAR node (var, let, const)

        for j, child in enumerate(token.children):

            if child.type != Token.T_ASSIGN:

                _undefined = Token(Token.T_KEYWORD, token.line, token.index, "undefined")
                _assign = Token(Token.T_ASSIGN, token.line, token.index, "=", [child, _undefined])

                token.children[j] = _assign

        if parent.type == Token.T_ARGLIST:
            if len(token.children) != 1:
                raise VmCompileError(token, "expected arglist var to contain a single child")

            parent.children[index] = token.children[0]

        elif parent.type not in (Token.T_MODULE, token.T_BLOCK, Token.T_EXPORT_ARGS):
            raise VmCompileError(token, "expected parent of let to be block not %s" % parent.type)

        else:
            parent.children = parent.children[:index] + token.children + parent.children[index+1:]
            return 0 # don't advance transform iterator
        return None

    def _visit_assign(self, parent, token, index):
        """
        let [a,b,c] = [1,2,3]

        transform an unpack sequence expression into a series of assignments
        """

        if token.value != "=":
            return

        lhs, rhs = token.children

        if lhs.type != Token.T_UNPACK_SEQUENCE:
            return

        # instead of deterministic names, can the compiler generate a unique
        # incrementing name?
        varname = "_unpack_%d_%d" % (token.line, token.index)
        _var = Token(Token.T_LOCAL_VAR, token.index, token.value, varname)

        token.children[0] = _var

        for i, child in enumerate(lhs.children):
            _index = Token(Token.T_NUMBER, token.line, token.index, str(i))
            _rhs = Token(Token.T_SUBSCR, token.line, token.index, "", [_var, _index])
            _assign = Token(Token.T_ASSIGN, token.line, token.index, "=", [child, _rhs])
            parent.children.insert(index+1, _assign)
        #_subscr = Token(Token.T_SUBSCR, token.line, token.index, "", [expr_seq, _getattr])

    def _visit_lambda(self, parent, token, index):
        block = token.children[2]

        if block.type != token.T_BLOCK:
            token.children[2] = Token(Token.T_RETURN, block.line, block.index, "return", [block])

    def _for_iter(self, token, expr_var, expr_seq, body):


        # _iterator_$line_$index = expr2[Symbol.iterator]()
        varname1 = "_iterator_%d_%d" % (token.line, token.index)
        _iterobj = Token(Token.T_LOCAL_VAR, token.line, token.index, varname1)
        _symbol = Token(Token.T_GLOBAL_VAR, token.line, token.index, "Symbol")
        _attr = Token(Token.T_ATTR, token.line, token.index, "iterator")
        _getattr = Token(Token.T_GET_ATTR, token.line, token.index, ".", [_symbol, _attr])
        _subscr = Token(Token.T_SUBSCR, token.line, token.index, "", [expr_seq, _getattr])
        _arglist =Token(Token.T_ARGLIST, token.line, token.index, "()")
        _rhs = Token(Token.T_FUNCTIONCALL, token.line, token.index, "", [_subscr, _arglist])
        _assign = Token(Token.T_ASSIGN, token.line, token.index, "=", [_iterobj, _rhs])
        _var = Token(Token.T_VAR, token.line, token.index, "const", [_assign])

        _delete_var1 = Token(Token.T_PREFIX, token.line, token.index, "delete", [Token(Token.T_LOCAL_VAR, token.line, token.index, varname1)])

        # _iterator_result_$line_$index = _iterator_$line_$index.next()
        varname2 = "_iterator_result_%d_%d" % (token.line, token.index)
        _iterresult = Token(Token.T_LOCAL_VAR, token.line, token.index, varname2)
        _iterator = Token(Token.T_LOCAL_VAR, token.line, token.index, varname1)
        _next = Token(Token.T_ATTR, token.line, token.index, "next")
        _getattr = Token(Token.T_GET_ATTR, token.line, token.index, ".", [_iterator, _next])
        _arglist =Token(Token.T_ARGLIST, token.line, token.index, "()")
        _rhs = Token(Token.T_FUNCTIONCALL, token.line, token.index, "", [_getattr, _arglist])
        _pre = Token(Token.T_ASSIGN, token.line, token.index, "=", [_iterresult, _rhs])

        _delete_var2 = Token(Token.T_PREFIX, token.line, token.index, "delete", [Token(Token.T_LOCAL_VAR, token.line, token.index, varname2)])

        # while (!_iterator_result_$line_$index.done) {
        # _iterator_result_$line_$index = _iterator_$line_$index.next()
        _done = Token(Token.T_ATTR, token.line, token.index, "done")
        _getattr = Token(Token.T_GET_ATTR, token.line, token.index, ".", [_iterresult, _done])
        _not = Token(Token.T_PREFIX, token.line, token.index, "!", [_getattr])
        _arglist =Token(Token.T_ARGLIST, token.line, token.index, "()", [_not])
        _value = Token(Token.T_ATTR, token.line, token.index, "value")
        _getattr = Token(Token.T_GET_ATTR, token.line, token.index, ".", [_iterresult, _value])
        # TODO: preserve const or let in some way
        if expr_var.type == Token.T_VAR:
            expr_var = expr_var.children[0]
        _assign = Token(Token.T_ASSIGN, token.line, token.index, "=", [expr_var, _getattr])
        _whilebody = Token(Token.T_BLOCK, token.line, token.index, "{}", [_assign, body, _pre.clone()])
        _while = Token(Token.T_WHILE, token.line, token.index, "", [_arglist, _whilebody])

        _block = Token(Token.T_BLOCK, token.line, token.index, "{}", [_var, _pre, _while, _delete_var1, _delete_var2])

        return _block

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
            Token.T_NULLISH_ASSIGN: self._visit_nullish_assign,
            Token.T_TERNARY: self._visit_ternary,
            Token.T_POSTFIX: self._visit_postfix,
            Token.T_PREFIX: self._visit_prefix,
            Token.T_WHILE: self._visit_while,
            Token.T_DOWHILE: self._visit_dowhile,
            Token.T_FOR: self._visit_for,
            Token.T_CONTINUE: self._visit_continue,
            Token.T_BREAK: self._visit_break,
            Token.T_SWITCH_BREAK: self._visit_break,
            Token.T_ARGLIST: self._visit_arglist,
            Token.T_BLOCK: self._visit_block,
            Token.T_GROUPING: self._visit_grouping,
            Token.T_SWITCH: self._visit_switch,
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
            Token.T_SAVE_VAR: self._visit_save_var,
            Token.T_RESTORE_VAR: self._visit_restore_var,
            Token.T_DELETE_VAR: self._visit_delete_var,
            Token.T_FREE_VAR: self._visit_free_var,
            Token.T_CELL_VAR: self._visit_cell_var,
            Token.T_NEW: self._visit_new,
            Token.T_INCLUDE: self._visit_include,
            Token.T_IMPORT_MODULE: self._visit_import_module,
            Token.T_PYIMPORT: self._visit_pyimport,
            Token.T_EXPORT: self._visit_export,
            Token.T_EXPORT_DEFAULT: self._visit_export_default,
            Token.T_EXPORT_ARGS: self._visit_export_args,
        }

        self.functions = []

        self._repl = False

    def compile(self, ast, path=None, globals_=None):

        self.module = VmModule()
        self.module.path = path
        self.module.globals = VmGlobals() if globals_ is None else globals_
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

        self._finalize_exports(self.module.functions[0])

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

    def _finalize_exports(self, fn):

        # for the top level module gather exported names into a object
        # the object will act as a namespace for the module
        # no jumps: this is currently called after _finalize

        # the issue with this is included files don't current re-export
        #for varname in fn.exports:
        #    instr = self._build_instr_string(VmCompiler.C_VISIT | VmCompiler.C_LOAD, varname, varname.value)
        #    fn.instrs.append(instr)
        #    opcode, index = self._token2index(varname, True)
        #    fn.instrs.append(VmInstruction(opcode, index))
        #fn.instrs.append(VmInstruction(opcodes.obj.CREATE_OBJECT, len(fn.exports)))
        #fn.instrs.append(VmInstruction(opcodes.ctrl.RETURN, 1))

        if not self._repl:
            fn.instrs.append(VmInstruction(opcodes.ctrl.EXPORT))

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

    def _visit_nullish_assign(self, depth, state, token):

        lhs, rhs = token.children

        instr1 = VmInstruction(opcodes.ctrl.END, token=token)
        instr2 = VmInstruction(opcodes.ctrl.ELSE, token=token)
        instr3 = VmInstruction(opcodes.ctrl.IFNULL, token=token)

        self.fn_jumps[instr1] = [instr2]  # target, list[source]
        self.fn_jumps[instr2] = [instr3]  # target, list[source]

        #TODO: this has side effects that need to be fixed
        #      a.b ??= x  => duplicate the reference to a
        #      a[x] ??= y  => duplicate the reference to a and x

        self._push_token(depth, VmCompiler.C_INSTRUCTION, instr1)
        self._push_token(depth, VmCompiler.C_VISIT|VmCompiler.C_STORE, lhs)
        self._push_token(depth, VmCompiler.C_VISIT|VmCompiler.C_LOAD, rhs)
        self._push_token(depth, VmCompiler.C_INSTRUCTION, instr2)
        self._push_token(depth, VmCompiler.C_INSTRUCTION, instr3)
        self._push_token(depth, VmCompiler.C_VISIT|VmCompiler.C_LOAD, lhs)

    def _visit_ternary(self, depth, state, token):

        arglist, branch_true, branch_false = token.children

        instr1 = VmInstruction(opcodes.ctrl.END, token=token)
        instr2 = VmInstruction(opcodes.ctrl.ELSE, token=token)
        instr3 = VmInstruction(opcodes.ctrl.IF, token=token)

        self.fn_jumps[instr1] = [instr2]  # target, list[source]
        self.fn_jumps[instr2] = [instr3]  # target, list[source]

        self._push_token(depth, VmCompiler.C_INSTRUCTION, instr1)
        self._push_token(depth, VmCompiler.C_VISIT|VmCompiler.C_LOAD, branch_false)
        self._push_token(depth, VmCompiler.C_INSTRUCTION, instr2)
        self._push_token(depth, VmCompiler.C_VISIT|VmCompiler.C_LOAD, branch_true)
        self._push_token(depth, VmCompiler.C_INSTRUCTION, instr3)
        self._push_token(depth, VmCompiler.C_VISIT|VmCompiler.C_LOAD, arglist)

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
            sub = VmInstruction(opcodes.math.SUB, token=token)
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
            elif child.type == Token.T_LOCAL_VAR:
                name = child.value
                opcode = opcodes.localvar.DELETE
                try:
                    index = self.fn.local_names.index(name)
                except ValueError:
                    index = len(self.fn.local_names)
                    self.fn.local_names.append(name)
                inst = VmInstruction(opcode, index, token=token)
                self._push_token(depth, VmCompiler.C_INSTRUCTION, inst)
            else:
                raise VmCompileError(child, "invalid child for prefix delete")
        elif token.value == "++":

            add = VmInstruction(opcodes.math.ADD, token=token)
            if state & VmCompiler.C_LOAD == 0:
                self._push_token(depth, VmCompiler.C_INSTRUCTION, VmInstruction(opcodes.stack.POP, token=token))
            #TODO: this has side effects that need to be fixed
            #      ++f()   => no write back, cannot assign to function call
            #      ++a.b   => duplicate the reference to a
            #      ++a[x]  => duplicate the reference to a and x
            self._push_token(depth, VmCompiler.C_VISIT | VmCompiler.C_STORE, token.children[0])
            self._push_token(depth, VmCompiler.C_INSTRUCTION, VmInstruction(opcodes.stack.DUP, token=token))
            self._push_token(depth, VmCompiler.C_INSTRUCTION, VmInstruction(opcodes.math.ADD, token=token))
            self._push_token(depth, VmCompiler.C_INSTRUCTION, VmInstruction(opcodes.const.INT, 1, token=token))
            self._push_token(depth, VmCompiler.C_VISIT | VmCompiler.C_LOAD, token.children[0])
        elif token.value == "--":

            add = VmInstruction(opcodes.math.ADD, token=token)
            if state & VmCompiler.C_LOAD == 0:
                self._push_token(depth, VmCompiler.C_INSTRUCTION, VmInstruction(opcodes.stack.POP, token=token))
            #TODO: this has side effects that need to be fixed
            self._push_token(depth, VmCompiler.C_VISIT | VmCompiler.C_STORE, token.children[0])
            self._push_token(depth, VmCompiler.C_INSTRUCTION, VmInstruction(opcodes.stack.DUP, token=token))
            self._push_token(depth, VmCompiler.C_INSTRUCTION, VmInstruction(opcodes.math.SUB, token=token))
            self._push_token(depth, VmCompiler.C_INSTRUCTION, VmInstruction(opcodes.const.INT, 1, token=token))
            self._push_token(depth, VmCompiler.C_VISIT | VmCompiler.C_LOAD, token.children[0])
        elif token.value == "void":
            # execute a load operation but return undefined

            if state & VmCompiler.C_LOAD:
                self._push_token(depth, VmCompiler.C_INSTRUCTION, VmInstruction(opcodes.const.UNDEFINED, token=token))

            self._push_token(depth, VmCompiler.C_INSTRUCTION, VmInstruction(opcodes.stack.POP, token=token))
            self._push_token(depth, VmCompiler.C_VISIT | VmCompiler.C_LOAD, token.children[0])

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

    def _handle_object_child(self, depth, state, token, child):
        """ push a <Value, Key> pair onto the stack for the child
        of an T_OBJECT.

        Javascript allows functions to de defined on objects, and for the
        keys (including function names) to be expressions when wrapped
        in square brackets.

        The default case is a binary expression `key:val`

        """

        if child.type == Token.T_FUNCTION:

            if child.children[0].type == Token.T_LIST:
                name = child.children[0].children[0]
            else:
                name = child.children[0].clone()
                name.type = Token.T_STRING
                name.value = repr(name.value)

            arglist = child.children[1]
            block = child.children[2]
            closure = child.children[3]
            self._build_function(state|VmCompiler.C_LOAD, child, name, arglist, block, closure, autobind=False)
            self._push_token(depth, VmCompiler.C_VISIT | VmCompiler.C_LOAD, name)

        elif child.type == Token.T_BINARY and child.children[0].type == Token.T_LIST:
            # support evaluating the lhs when the expression is wrapped in square brackets
            lhs, rhs = child.children
            if len(lhs.children) != 1:
                raise VmCompileError(lhs, "expected single expression")
            lhs = lhs.children[0]
            self._push_token(depth, VmCompiler.C_VISIT | VmCompiler.C_LOAD, rhs)
            self._push_token(depth, VmCompiler.C_VISIT | VmCompiler.C_LOAD, lhs)

        else:
            self._push_token(depth, VmCompiler.C_VISIT | VmCompiler.C_LOAD, child)

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
                        self._handle_object_child(depth, state, token, child)

            instr = VmInstruction(opcodes.obj.CREATE_OBJECT, 0, token=token)
            self._push_token(depth, VmCompiler.C_INSTRUCTION, instr)


        else:
            nprops = len(token.children)
            instr = VmInstruction(opcodes.obj.CREATE_OBJECT, nprops, token=token)
            self._push_token(depth, VmCompiler.C_INSTRUCTION, instr)

            for child in reversed(token.children):
                self._handle_object_child(depth, state, token, child)

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

        flag0 = VmCompiler.C_VISIT#|VmCompiler.C_LOAD
        for child in reversed(token.children):
            self._push_token(depth, flag0, child)

    def _visit_grouping(self, depth, state, token):

        for child in reversed(token.children):
            self._push_token(depth, state, child)

    def _visit_switch(self, depth, state, token):

        instr_e = VmInstruction(opcodes.ctrl.NOP, token=token)
        instr_dup = VmInstruction(opcodes.stack.DUP, token=token)

        self.fn_jumps[instr_e] = []  # target, list[source]
        self.target_break.append(instr_e)

        self._push_token(depth, VmCompiler.C_INSTRUCTION, instr_e)

        # body of each case
        targets = []
        for child in reversed(token.children[1].children):
            if child.type == Token.T_DEFAULT:
                instr_pop = VmInstruction(opcodes.stack.POP, token=token)
                targets.append(instr_pop)
                for gchild in reversed(child.children):
                    self._push_token(depth, VmCompiler.C_VISIT, gchild)
                self._push_token(depth, VmCompiler.C_INSTRUCTION, instr_pop)
            elif child.type == Token.T_CASE:
                instr_pop = VmInstruction(opcodes.stack.POP, token=token)
                targets.append(instr_pop)
                for gchild in reversed(child.children[1:]):
                    self._push_token(depth, VmCompiler.C_VISIT, gchild)
                self._push_token(depth, VmCompiler.C_INSTRUCTION, instr_pop)

        # evaluate test case : build jump table
        for child, target in zip(reversed(token.children[1].children), targets):
            if child.type == Token.T_DEFAULT:
                instr = VmInstruction(opcodes.ctrl.JUMP, token=token)
                self.fn_jumps[target] = [instr]  # target, list[source]
                self._push_token(depth, VmCompiler.C_INSTRUCTION, instr)
            elif child.type == Token.T_CASE:

                # jump if values are equal
                instr = VmInstruction(opcodes.ctrl.IF, token=token)
                self.fn_jumps[target] = [instr]  # target, list[source]
                self._push_token(depth, VmCompiler.C_INSTRUCTION, instr)

                # compare
                instr = VmInstruction(opcodes.comp.NE, token=token)
                self._push_token(depth, VmCompiler.C_INSTRUCTION, instr)

                # load the value to compare to
                self._push_token(depth, VmCompiler.C_VISIT|VmCompiler.C_LOAD, child.children[0])

                # duplicate the value
                self._push_token(depth, VmCompiler.C_INSTRUCTION, instr_dup)

        # load the value to switch over
        self._push_token(depth, VmCompiler.C_VISIT|VmCompiler.C_LOAD, token.children[0])

    def _visit_module(self, depth, state, token):

        # TODO: perhaps state should be load then the last expression should be loaded...
        # the last node in repl mode must be loaded
        first = self._repl

        for child in reversed(token.children):
            # a lone local/global var has no side effect
            # loading will push something on the stack, which is
            # valid only in the repl and otherwise should be an exception
            # consider a new C flag, for a conditional load

            # TODO: local/globals must be loaded then popped
            # except for the final one, if the load flag is set
            if first or child.type in (Token.T_LOCAL_VAR, Token.T_GLOBAL_VAR):
                flags = VmCompiler.C_VISIT|VmCompiler.C_LOAD
            else:
                flags = VmCompiler.C_VISIT
            self._push_token(depth, flags, child)
            first = False

    def _visit_save_var(self, depth, state, token):
        child = token.children[0]
        opcode, index = self._token2index(child, True, delete=False)
        print("vmc: save %s" % child, child.line, child.index)
        self._push_token(depth, VmCompiler.C_INSTRUCTION,
            VmInstruction(opcode, index, token=child))

    def _visit_restore_var(self, depth, state, token):
        child = token.children[0]
        opcode, index = self._token2index(child, False, delete=False)
        print("vmc: restore %s" % child, child.line, child.index)
        self._push_token(depth, VmCompiler.C_INSTRUCTION,
            VmInstruction(opcode, index, token=child))

    def _visit_delete_var(self, depth, state, token):
        child = token.children[0]
        opcode, index = self._token2index(child, False, delete=True)
        self._push_token(depth, VmCompiler.C_INSTRUCTION,
            VmInstruction(opcode, index, token=child))

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

            lhs, rhs = token.children
            self._push_token(depth, VmCompiler.C_VISIT|VmCompiler.C_STORE, lhs)

            if state & VmCompiler.C_LOAD:
                self._push_token(depth, VmCompiler.C_INSTRUCTION, VmInstruction(opcodes.stack.DUP, token=token))

            self._push_token(depth, VmCompiler.C_VISIT|VmCompiler.C_LOAD, rhs)

        else:

            if token.value in binop_store:
                self._push_token(depth, VmCompiler.C_VISIT | VmCompiler.C_STORE, token.children[0])
                self._push_token(depth, VmCompiler.C_INSTRUCTION, VmInstruction(binop_store[token.value], token=token))

            lhs, rhs = token.children
            if lhs.type == Token.T_GET_ATTR:
                self._push_token(depth, VmCompiler.C_VISIT | VmCompiler.C_LOAD, token.children[1])
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
            #if state & VmCompiler.C_LOAD:
            index = len(self.fn.globals.constdata)
            self.fn.globals.constdata.append(value)

        if index == -1:
            raise VmCompileError(token, "unable to load undefined string (%0X)" % state)

        return VmInstruction(opcodes.const.STRING, index, token=token)

    def _visit_string(self, depth, state, token):

        try:
            value = pyast.literal_eval(token.value)
        except SyntaxError as e:
            raise VmCompileError(token, "unable to load undefined string (%0X)" % state)
        except Exception as e:
            raise VmCompileError(token, "unable to load undefined string (%0X)" % state)
        instr = self._build_instr_string(state, token, value)

        self._push_instruction(instr)
        if not (state & VmCompiler.C_LOAD):
            self._push_instruction(VmInstruction(opcodes.stack.POP, token=token))

    def _visit_number(self, depth, state, token):

        try:
            value = token.value.replace("_", "")

            # bigint
            if value.endswith("n"):
                value = value[:1]

            op = opcodes.const.INT
            if value.startswith("0b"):
                val = int(value[2:], 2)
            elif value.startswith("0x"):
                val = int(value[2:], 16)
            elif value.startswith("0o"):
                val = int(value[2:], 8)
            elif "." in value or 'e' in value or 'E' in value:
                val = float(value)
                op = opcodes.const.FLOAT32
            elif len(value) > 1 and value.startswith("0"):
                try:
                    val = int(value[1:], 8)
                except ValueError:
                    val = int(value[1:], 10)
            else:
                val = int(value)
        except ValueError:
            raise VmCompileError(token, "invalid numeric literal")

        self._push_instruction(VmInstruction(op, val, token=token))
        if not (state & VmCompiler.C_LOAD):
            self._push_instruction(VmInstruction(opcodes.stack.POP, token=token))

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

            allow_kwargs = True
            pos_count = 0
            kwarg_count = 0

            seq = []
            for idx, child in enumerate(reversed(expr_args.children)):
                if child.type == Token.T_ASSIGN:

                    if not allow_kwargs:
                        raise VmCompileError(child, "syntax error: pos after kwarg")

                    allow_positional = False

                    seq.append((depth, flag0, child.children[1]))
                    seq.append((depth, VmCompiler.C_INSTRUCTION, self._build_instr_string(flag0, token, child.children[0].value)))
                    kwarg_count += 1
                else:
                    allow_kwargs = False
                    pos_count += 1
                    seq.append((depth, flag0, child))


            if kwarg_count > 0:
                self._push_token(depth, VmCompiler.C_INSTRUCTION, VmInstruction(opcodes.ctrl.CALL_KW, pos_count, token=token))
                self._push_token(0, VmCompiler.C_INSTRUCTION, VmInstruction(opcodes.obj.CREATE_OBJECT, kwarg_count, token=token))
            else:
                self._push_token(depth, VmCompiler.C_INSTRUCTION, VmInstruction(opcodes.ctrl.CALL, pos_count, token=token))

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
        # TODO: document why the jump targets are int and not NOP
        instr_if = VmInstruction(opcodes.const.INT, 0, token=token)
        instr_ic = VmInstruction(opcodes.const.INT, 0, token=token)

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
        arglist, block = token.children
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

        self._push_instruction(self._build_instr_string(state, token.children[0], path))
        self._push_instruction(VmInstruction(opcodes.ctrl.IMPORT, token=token))
        self._push_instruction(VmInstruction(opcodes.ctrl.IMPORT2, token=token))
        self._push_instruction(VmInstruction(opcodes.ctrl.INCLUDE, token=token))

    def _visit_import_module(self, depth, state, token):

        # the name of the module to load is stored as a string at the TOS
        #self._push_instruction(instr)

        # pop the module reference when it is no longer needed


        # for every named object to import into the current namespace:
        #   duplicate the module reference
        #   get the attribute
        #   set as a local or global variable
        arglist = token.children[0]
        if len(arglist.children) == 0:
            temp = Token(Token.T_GLOBAL_VAR, token.line, token.index, token.value)
            self._push_token(depth, VmCompiler.C_VISIT | VmCompiler.C_STORE, temp)

            if state&VmCompiler.C_LOAD:
                self._push_token(depth, VmCompiler.C_INSTRUCTION, VmInstruction(opcodes.stack.DUP, token=token))

        else:
            if not state&VmCompiler.C_LOAD:
                self._push_token(depth, VmCompiler.C_INSTRUCTION, VmInstruction(opcodes.stack.POP, token=token))

            for child in reversed(arglist.children):

                if child.type == Token.T_ASSIGN:
                    src, tgt = child.children
                else:
                    src = child
                    tgt = child

                flag0 = VmCompiler.C_VISIT | VmCompiler.C_LOAD

                flag1 = VmCompiler.C_VISIT
                if token.value == "." and state & VmCompiler.C_STORE:
                    flag1 |= VmCompiler.C_STORE
                else:
                    flag1 |= VmCompiler.C_LOAD

                self._push_token(depth, VmCompiler.C_VISIT | VmCompiler.C_STORE, tgt)
                self._push_token(depth, VmCompiler.C_VISIT | VmCompiler.C_LOAD , src)
                self._push_token(depth, VmCompiler.C_INSTRUCTION, VmInstruction(opcodes.stack.DUP, token=token))


        # import the module
        self._push_token(depth, VmCompiler.C_INSTRUCTION, VmInstruction(opcodes.ctrl.IMPORT2, token=token))
        self._push_token(depth, VmCompiler.C_INSTRUCTION, VmInstruction(opcodes.ctrl.IMPORT, token=token))
        self._push_token(depth, VmCompiler.C_INSTRUCTION, self._build_instr_string(state, token, token.value))

    def _visit_pyimport(self, depth, state, token):
        opcode, index = self._token2index(token.children[0], False)
        self._push_token(depth, VmCompiler.C_INSTRUCTION, VmInstruction(opcode, index, token=token))
        self._push_token(depth, VmCompiler.C_INSTRUCTION, VmInstruction(opcodes.ctrl.IMPORTPY, token=token))
        self._push_token(depth, VmCompiler.C_INSTRUCTION, self._build_instr_string(state, token.children[0], token.children[0].value))

    def _visit_export(self, depth, state, token):
        """
            Export:
                - list of names to export
                - list of expressions for each name

            _finalize_exports pushes the export opcode
            by default all global names are exported

            TODO: visit second list with a load flag
                  build a dictionary of all pairs

        """

        node = token.children[1]
        #self.fn.exports.extend(token.children[0].children)
        self._push_token(depth, VmCompiler.C_VISIT  | VmCompiler.C_LOAD, node)

    def _visit_export_default(self, depth, state, token):
        node = token.children[1]
        self._push_token(depth, state, node)

    def _visit_export_args(self, depth, state, token):
        for child in reversed(token.children):
            self._push_token(depth, state, child)

    def _build_function(self, state, token, name, arglist, block, closure, autobind=True):
        """
            :param state: meta flags for procsing this node
            :param token: the token which represents the root of this function
            :param name: a token containing the name of the function
            :param arglist: a token containing the argument list for the function
            :param block: a token containing the body of the function
            :param closure:a token containing the Free and Cell names of non local vars
            :param autobind: True if this function should automatically bind to the current object scope
                                  lambdas always bind to the current scope
        """

        if not block.children:
            # block must have at least one instruction otherwise the interpreter exits early
            _value =Token(Token.T_KEYWORD, block.line, block.index, "undefined")
            _return = Token(Token.T_RETURN, block.line, block.index, "return", [_value])
            block.children.append(_return)

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
            # TODO: move this to the transform layer
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

        self._push_token(0, VmCompiler.C_INSTRUCTION, VmInstruction(opcodes.const.BOOL, bool(autobind), token=token))
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
                if not load or name == 'arguments':
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



