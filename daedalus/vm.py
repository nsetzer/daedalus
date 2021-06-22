#! cd .. && python -m daedalus.vm


import io
import struct
import ctypes
import binascii
import operator
import ast as pyast

from . import vm_opcodes as opcodes

from .token import Token, TokenError
from .lexer import Lexer
from .parser import Parser, ParseError
from .transform import TransformIdentityScope

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

class JsObject(object):

    prototype_instance = None

    def __init__(self, args=None, prototype=None):
        super(JsObject, self).__init__()

        if args:
            self.data = dict(args)
        else:
            self.data = {}

        if prototype is None:

            self.prototype = JsObject.prototype_instance
        else:
            self.prototype = prototype

    def __repr__(self):
        return "<JsObject()>"

    def _hasAttr(self, name):
        #if isinstance(name, JsString):
        #    name = name.value
        return name in self.data

    def getAttr(self, name):
        if isinstance(name, JsString):
            name = name.value

        if name == '__proto__':
            return self.prototype

        if self.prototype._hasAttr(name):
            attr = self.prototype.getAttr(name)

            if isinstance(attr, PyProp):
                attr = attr.bind(self).invoke()

        else:
            attr = self.data[name]

        return attr

    def setAttr(self, name, value):
        if isinstance(name, JsString):
            name = name.value
        self.data[name] = value

    def delAttr(self, name, value):
        if isinstance(name, JsString):
            name = name.value
        del self.data[name]

    def getIndex(self, index):
        return self.data[index]

    def setIndex(self, index, value):
        self.data[index] = value

    def delIndex(self, index):
        del self.data[index]


class PyProp(object):
    def __init__(self, target, func):
        super(PyProp, self).__init__()
        self.target = target
        self.func = func

    def invoke(self, *args, **kwargs):
        return self.func(self.target, *args, **kwargs)

    def bind(self, target):
        return PyProp(target, self.func)

class JsArray(JsObject):

    prototype_instance = None

    def __init__(self, args=None):
        super(JsArray, self).__init__(None, JsArray.prototype_instance)

        if args:
            self.array = list(args)
        else:
            self.array = []

    def __repr__(self):
        return "<JsArray()>"

    def getIndex(self, index):
        if isinstance(index, int):
            return self.array[index]
        return self.getAttr(index)

    def setIndex(self, index, value):
        print('setIndex', index, value)
        if isinstance(index, int):
            self.array[index] = value
        else:
            self.setAttr(index, value)

    def delIndex(self, index):
        if isinstance(index, int):
            del self.array[index]
        else:
            self.delAttr(index)

def _apply_value_operation(cls, op, a, b):
    if not isinstance(b, JsObject):
        b = cls(b)
    return op(a.value, b.value)

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
                setattr(cls, name, lambda a, b, op=op: _apply_value_operation(cls, op, a, b))

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
                setattr(cls, name, lambda a, b, op=op: _apply_value_operation(cls, op, a, b))

        return cls

class JsString(JsObject, metaclass=JsStringType):
    def __init__(self, value=''):
        super(JsString, self).__init__()
        if isinstance(value, JsString):
            value = value.value
        self.value = str(value)

    def __repr__(self):
        return "<JsString(%s)>" % self.value

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

    def __eq__(self, other):
        if isinstance(other, JsString):
            other = other.value
        return self.value == other

    def __hash__(self):
        return self.value.__hash__()

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

    def serialize(self, stream):
        pass

    def deserialize(self, stream):
        pass

JsObject.prototype_instance = JsObject()
JsArray.prototype_instance = JsObject()
JsArray.prototype_instance.setAttr('length', PyProp(None, lambda obj: len(obj.array)))

JsUndefined.instance = JsUndefined()

class VmInstruction(object):
    __slots__ = ['opcode', 'args', 'target']

    def __init__(self, opcode, *args, target=None):
        super(VmInstruction, self).__init__()
        self.opcode = opcode
        self.args = args
        self.target = target

    def __repr__(self):
        if self.args:
            s = " " + " ".join([str(arg) for arg in self.args])
        else:
            s = ""
        if self.target is not None:
            s += ": %d" % target
        return "(%s%s)" % (self.opcode, s)

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
        self.arglabels = []

class JsFunction(object):
    def __init__(self, module, fndef, args, kwargs):
        super(JsFunction, self).__init__()
        self.module = module
        self.fndef = fndef
        self.args = args
        self.kwargs = kwargs

    def __repr__(self):


        return "<JsFunction(%s)>" % (",".join(self.fndef.arglabels))

class VmModule(object):
    def __init__(self):
        super(VmModule, self).__init__()

    def dump(self):

        for idx, fn in enumerate(self.functions):

            print("--- %3d ---" % idx)
            print("globals:", " ".join(fn.globals.names))
            print("locals :", " ".join(fn.local_names))
            print("args   :", " ".join(fn.arglabels))
            for idx, instr in enumerate(fn.instrs):
                if instr.opcode in (opcodes.globalvar.GET, opcodes.globalvar.SET, opcodes.globalvar.DELETE):
                    print("%4d (%s %s)" % (idx, instr.opcode, self.globals.names[instr.args[0]]))
                elif instr.opcode in (opcodes.localvar.GET, opcodes.localvar.SET, opcodes.localvar.DELETE):
                    print("%4d (%s %s)" % (idx, instr.opcode, fn.local_names[instr.args[0]]))
                elif instr.opcode in (opcodes.cellvar.GET, opcodes.cellvar.SET, opcodes.cellvar.DELETE):
                    print("%4d (%s %s)" % (idx, instr.opcode, fn.cell_names[instr.args[0]]))
                elif instr.opcode == opcodes.obj.GET_ATTR:
                    print("%4d (%s %s)" % (idx, instr.opcode, fn.local_names[instr.args[0]]))
                elif instr.opcode == opcodes.const.STRING:
                    print("%4d (%s %s)" % (idx, instr.opcode, self.globals.constdata[instr.args[0]]))
                else:
                    print("%4d" % idx, instr)
        print("---")

class VmReference(object):
    def __init__(self, value=None):
        super(VmReference, self).__init__()
        self.value = value

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
            Token.T_WHILE: self._visit_while,
            Token.T_CONTINUE: self._visit_continue,
            Token.T_BREAK: self._visit_break,
            Token.T_ARGLIST: self._visit_arglist,
            Token.T_BLOCK: self._visit_block,
            Token.T_STRING: self._visit_string,
            Token.T_OBJECT: self._visit_object,
            Token.T_LIST: self._visit_list,
            Token.T_GET_ATTR: self._visit_get_attr,
            Token.T_SUBSCR: self._visit_subscr,
            Token.T_ATTR: self._visit_attr,
            Token.T_KEYWORD: self._visit_keyword,
            Token.T_FUNCTION: self._visit_function,
            Token.T_RETURN: self._visit_return,
            Token.T_FUNCTIONCALL: self._visit_functioncall,
            Token.T_TRY: self._visit_try,
            Token.T_CATCH: self._visit_catch,
            Token.T_FINALLY: self._visit_finally,
            Token.T_THROW: self._visit_throw,
        }

        self.compile_actions = {
        }

        self.functions = []

    def compile(self, ast):

        self.module = VmModule()
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

            instr1 = VmInstruction(opcodes.ctrl.END)
            instr2 = VmInstruction(opcodes.ctrl.IF)

            self.fn_jumps[instr1] = [instr2]  # target, list[source]

            self._push_token(depth, VmCompiler.C_INSTRUCTION, instr1)
            self._push_token(depth+1, VmCompiler.C_VISIT, branch_true)
            self._push_token(depth, VmCompiler.C_INSTRUCTION, instr2)
            self._push_token(depth, VmCompiler.C_VISIT, arglist)

        elif len(token.children) == 3:
            arglist, branch_true, branch_false = token.children

            instr1 = VmInstruction(opcodes.ctrl.END)
            instr2 = VmInstruction(opcodes.ctrl.ELSE)
            instr3 = VmInstruction(opcodes.ctrl.IF)

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

    def _visit_while(self, depth, state, token):
        arglist, block = token.children

        instr1 = VmInstruction(opcodes.ctrl.END)
        instr2 = VmInstruction(opcodes.ctrl.JUMP)
        instr3 = VmInstruction(opcodes.ctrl.IF)
        instr4 = VmInstruction(opcodes.ctrl.LOOP)

        self.fn_jumps[instr1] = [instr3]  # target, list[source]
        self.fn_jumps[instr4] = [instr2]  # target, list[source]

        self.target_continue.append(instr4)
        self.target_break.append(instr1)

        self._push_token(depth, VmCompiler.C_LOOP_END, None)
        self._push_token(depth, VmCompiler.C_INSTRUCTION, instr1)
        self._push_token(depth, VmCompiler.C_INSTRUCTION, instr2)
        self._push_token(depth, VmCompiler.C_VISIT, block)
        self._push_token(depth, VmCompiler.C_INSTRUCTION, instr3)
        self._push_token(depth, VmCompiler.C_VISIT, arglist)
        self._push_token(depth, VmCompiler.C_INSTRUCTION, instr4)

    def _visit_break(self, depth, state, token):
        instr0 = VmInstruction(opcodes.ctrl.JUMP)
        self.fn_jumps[self.target_break[-1]].append(instr0)
        self._push_instruction(instr0)

    def _visit_continue(self, depth, state, token):
        instr0 = VmInstruction(opcodes.ctrl.JUMP)
        self.fn_jumps[self.target_continue[-1]].append(instr0)
        self._push_instruction(instr0)

    def _visit_object(self, depth, state, token):

        unpack = any(child.type == Token.T_SPREAD for child in token.children)
        if unpack:
            raise NotImplementedError()
        else:
            nprops = len(token.children)

            self._push_token(depth, VmCompiler.C_INSTRUCTION, VmInstruction(opcodes.obj.CREATE_OBJECT, nprops))

            for child in reversed(token.children):
                self._push_token(depth, VmCompiler.C_VISIT | VmCompiler.C_LOAD, child)

    def _visit_list(self, depth, state, token):
        unpack = any(child.type == Token.T_SPREAD for child in token.children)
        if unpack:
            raise NotImplementedError()
        else:
            nprops = len(token.children)

            self._push_token(depth, VmCompiler.C_INSTRUCTION, VmInstruction(opcodes.obj.CREATE_ARRAY, nprops))

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

        self._push_token(depth, VmCompiler.C_INSTRUCTION, VmInstruction(opcode))
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

        self._push_instruction(VmInstruction(opcode, index))

    def _visit_arglist(self, depth, state, token):

        flag0 = VmCompiler.C_VISIT | VmCompiler.C_LOAD
        for child in reversed(token.children):
            self._push_token(depth, flag0, child)

    def _visit_block(self, depth, state, token):

        flag0 = VmCompiler.C_VISIT
        for child in reversed(token.children):
            self._push_token(depth, flag0, child)

    def _visit_module(self, depth, state, token):

        for child in reversed(token.children):
            self._push_token(depth, VmCompiler.C_VISIT, child)

    def _visit_var(self, depth, state, token):

        for child in reversed(token.children):
            self._push_token(depth, VmCompiler.C_VISIT, child)

    def _visit_binary(self, depth, state, token):

        flag0 = VmCompiler.C_VISIT
        if token.value == "=":
            flag0 |= VmCompiler.C_STORE
        else:
            flag0 |= VmCompiler.C_LOAD

        flag1 = VmCompiler.C_VISIT

        if token.value == ":":
            pass
        else:
            opcode = binop.get(token.value, None)
            if opcode is None:
                raise VmCompileError(token, "illegal binary operator")
            self._push_token(depth, VmCompiler.C_INSTRUCTION, VmInstruction(opcode))

        self._push_token(depth, VmCompiler.C_VISIT|VmCompiler.C_LOAD, token.children[1])
        self._push_token(depth, VmCompiler.C_VISIT|VmCompiler.C_LOAD, token.children[0])

    def _visit_assign(self, depth, state, token):

        if token.value == "=":

            if state & VmCompiler.C_LOAD:
                self._push_token(depth, VmCompiler.C_INSTRUCTION, VmInstruction(opcodes.stack.DUP))

            self._push_token(depth, VmCompiler.C_VISIT|VmCompiler.C_STORE, token.children[0])
            self._push_token(depth, VmCompiler.C_VISIT|VmCompiler.C_LOAD, token.children[1])

        else:

            if token.value in binop_store:
                self._push_token(depth, VmCompiler.C_VISIT | VmCompiler.C_STORE, token.children[0])
                self._push_token(depth, VmCompiler.C_INSTRUCTION, VmInstruction(binop_store[token.value]))

            lhs, rhs = token.children
            if lhs.type == Token.T_GET_ATTR:
                raise NotImplementedError()
            elif lhs.type == Token.T_SUBSCR:
                raise NotImplementedError()
            else:
                #self._push_token(depth, VmCompiler.C_VISIT | (state & (VmCompiler.C_LOAD_STORE)), token)
                self._push_token(depth, VmCompiler.C_VISIT, token.children[1])
                self._push_token(depth, VmCompiler.C_VISIT | VmCompiler.C_LOAD, token.children[0])

    def _visit_text(self, depth, state, token):

        opcode, index = self._token2index(token, state & VmCompiler.C_LOAD)

        self._push_instruction(VmInstruction(opcode, index))

    def _visit_string(self, depth, state, token):

        value = JsString(pyast.literal_eval(token.value))

        index = -1
        try:
            index = self.fn.globals.constdata.index(value)
        except ValueError:
            if state & VmCompiler.C_LOAD:
                index = len(self.fn.globals.constdata)
                self.fn.globals.constdata.append(value)

        if index == -1:
            raise VmCompileError(token, "unable to load undefined string")

        self._push_instruction(VmInstruction(opcodes.const.STRING, index))

    def _visit_number(self, depth, state, token):

        self._push_instruction(VmInstruction(opcodes.const.INT, int(token.value)))

    def _visit_keyword(self, depth, state, token):

        if token.value == "true":
            self._push_instruction(VmInstruction(opcodes.const.TRUE))
        elif token.value == "false":
            self._push_instruction(VmInstruction(opcodes.const.FALSE))
        elif token.value == "null":
            self._push_instruction(VmInstruction(opcodes.const.NULL))
        elif token.value == "undefined":
            self._push_instruction(VmInstruction(opcodes.const.UNDEFINED))
        else:
            raise VmCompileError(token, "not implemented")

    def _visit_function(self, depth, state, token):

        name = token.children[0]
        arglist = token.children[1]
        block = token.children[2]
        closure = token.children[3]

        opcode, index = self._token2index(name, False)
        self._push_token(depth, VmCompiler.C_INSTRUCTION, VmInstruction(opcode, index))

        self._build_function(state|VmCompiler.C_LOAD, token, name, arglist, block, closure, autobind=False)

    def _visit_functioncall(self, depth, state, token):

        expr_call, expr_args = token.children
        unpack = any(child.type == Token.T_SPREAD for child in expr_args.children)
        if unpack:
            raise NotImplementedError()
        else:
            if state & VmCompiler.C_LOAD == 0:
                self._push_token(depth, VmCompiler.C_INSTRUCTION, VmInstruction(opcodes.stack.POP))
            self._push_token(depth, VmCompiler.C_INSTRUCTION, VmInstruction(opcodes.ctrl.CALL, len(expr_args.children)))

            flag0 = VmCompiler.C_VISIT | VmCompiler.C_LOAD
            self._push_token(depth, flag0, expr_args)
            self._push_token(depth, flag0, expr_call)

    def _visit_return(self, depth, state, token):
        self._push_token(depth, VmCompiler.C_INSTRUCTION, VmInstruction(opcodes.ctrl.RETURN, len(token.children)))
        flag0 = VmCompiler.C_VISIT | VmCompiler.C_LOAD
        for child in reversed(token.children):
            self._push_token(depth, flag0, child)

    def _visit_try(self, depth, state, token):
        flag0 = VmCompiler.C_VISIT

        count = len(token.children)

        block = None
        catch = None
        final = None
        if count >= 1:
            block = token.children[0]
        if count >= 2:
            catch = token.children[1]
        if count == 3:
            final = token.children[2]

        instr_jf = VmInstruction(opcodes.ctrl.JUMP)
        instr_f = VmInstruction(opcodes.ctrl.FINALLY)
        instr_c = VmInstruction(opcodes.ctrl.CATCH)
        instr_t = VmInstruction(opcodes.ctrl.TRY)
        instr_e = VmInstruction(opcodes.ctrl.END)
        #instr_b = VmInstruction(opcodes.ctrl.BLOCK)

        self.fn_jumps[instr_f] = [instr_jf]  # target, list[source]
        self.fn_jumps[instr_c] = [instr_t]  # target, list[source]

        self._push_token(depth, VmCompiler.C_INSTRUCTION, instr_e)

        if final:
            self._push_token(depth, flag0, final)

        self._push_token(depth, VmCompiler.C_INSTRUCTION, instr_f)

        if catch:
            self._push_token(depth, flag0, catch)

        self._push_token(depth, VmCompiler.C_INSTRUCTION, instr_c)
        self._push_token(depth, VmCompiler.C_INSTRUCTION, instr_jf)

        if block:
            self._push_token(depth, flag0, block)

        self._push_token(depth, VmCompiler.C_INSTRUCTION, instr_t)

        #self._push_token(depth, VmCompiler.C_INSTRUCTION, instr_b)

    def _visit_catch(self, depth, state, token):
        """assuming the exception is on the top of the stack...
           maybe not a good place for it?
        """

        flag0 = VmCompiler.C_VISIT

        if len(token.children) == 2:
            arglist, block = token.children

            self._push_token(depth, flag0, block)
            self._push_token(depth, flag0|VmCompiler.C_STORE, arglist.children[0])

        if len(token.children) == 1:
            block = token.children[0]

            self._push_token(depth, flag0, block)
            self._push_token(depth, VmCompiler.C_INSTRUCTION, VmInstruction(opcodes.stack.POP))

    def _visit_finally(self, depth, state, token):

        flag0 = VmCompiler.C_VISIT
        for child in reversed(token.children):
            self._push_token(depth, flag0, child)

    def _visit_throw(self, depth, state, token):
        self._push_token(depth, VmCompiler.C_INSTRUCTION, VmInstruction(opcodes.ctrl.THROW))
        flag0 = VmCompiler.C_VISIT | VmCompiler.C_LOAD
        for child in reversed(token.children):
            self._push_token(depth, flag0, child)

    def _build_function(self, state, token, name, arglist, block, closure, autobind=True):

        fndef = VmFunctionDef(block, self.module.globals)
        fnidx = len(self.module.functions)
        self.module.functions.append(fndef)

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

        self._push_token(0, VmCompiler.C_INSTRUCTION, VmInstruction(opcodes.obj.CREATE_FUNCTION, fnidx, len(arglabels)))

        for arglabel, argdefault in reversed(list(zip(arglabels, argdefaults))):

            if argdefault is None:
                self._push_token(0, VmCompiler.C_INSTRUCTION, VmInstruction(opcodes.const.UNDEFINED))
            else:
                self._push_token(0, VmCompiler.C_VISIT|VmCompiler.C_LOAD, argdefault)

        fndef.local_names = arglabels
        fndef.arglabels = arglabels

    def _token2index(self, token, load):

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
                index = self.fn.local_names.index(name)
            except ValueError:
                if not load:
                    index = len(self.fn.local_names)
                    self.fn.local_names.append(name)

        elif token.type == Token.T_FREE_VAR or token.type == Token.T_CELL_VAR:
            name = token.value
            enum = opcodes.cellvar

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

    def _push_token(self, depth, state, token):
        self.seq.append((depth, state, token))

    def _push_instruction(self, instr):
        self.fn.instrs.append(instr)

class VmStackFrame(object):
    def __init__(self, module, fndef, locals=None, cells=None):
        super(VmStackFrame, self).__init__()
        self.fndef = fndef
        self.module = module
        self.locals = {} if locals is None else locals
        self.local_names = fndef.local_names
        self.globals = fndef.globals
        self.cells = {} if cells is None else cells
        self.blocks = []
        self.stack = []
        self.sp = 0

class VmBlock(object):
    def __init__(self, ip, instr):
        super(VmBlock, self).__init__()
        self.ip = ip
        self.instr = instr

class VmTryBlock(object):
    def __init__(self, ip, instr):
        super(VmTryBlock, self).__init__()
        self.ip = ip
        self.instr = instr
        self.exception = None

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

    opcodes.math.AND: lambda a, b: (a and b),
    opcodes.math.OR: lambda a, b: (a or b),

}

unary_op = {
    opcodes.math.NEGATIVE: operator.__neg__,
    opcodes.math.POSITIVE: operator.__pos__,
    opcodes.math.BITWISE_NOT: operator.__invert__,

    opcodes.math.NOT: lambda a: (not a),

}

def _get_exception_frame(frames, index):

    j = index
    while j >= 0:
        frame = frames[j]
        i = len(frame.blocks)
        while i > 0:
            i -= 1
            block = frame.blocks[i]
            if isinstance(block, VmTryBlock):
                return j, i
        j -= 1
    return 0, 0

class VmRuntime(object):
    def __init__(self):
        super(VmRuntime, self).__init__()

        self.stack_frames = []

        self.enable_diag = False

    def init(self, module):

        self.stack_frames = [VmStackFrame(module, module.functions[0])]

        g = self.stack_frames[-1].globals

        console = lambda: None
        console.log = print
        g.values['console'] = console

    def run(self):

        frame = self.stack_frames[-1]
        instrs = frame.fndef.instrs
        return_value = None

        while frame.sp < len(instrs):

            instr = instrs[frame.sp]

            if self.enable_diag:
                print(len(self.stack_frames), frame.sp, instr)

            if instr.opcode == opcodes.ctrl.NOP:
                pass
            elif instr.opcode == opcodes.ctrl.IF:
                frame.blocks.append(VmBlock(frame.sp, instr))
                tos = frame.stack.pop()
                # TODO: check if 'falsey'
                if not tos:
                    frame.sp += instr.args[0]
                    continue
            elif instr.opcode == opcodes.ctrl.END:

                block_ = frame.blocks.pop()
                # if this is a tryblock, with an active exception
                # find the next exception handler
            elif instr.opcode == opcodes.ctrl.LOOP:

                frame.blocks.append(VmBlock(frame.sp, instr))
            elif instr.opcode == opcodes.ctrl.ELSE:
                frame.sp += instr.args[0]
                continue
            elif instr.opcode == opcodes.ctrl.JUMP:
                frame.sp += instr.args[0]
                continue
            elif instr.opcode == opcodes.ctrl.CALL:
                argc = instr.args[0]
                args = []
                for i in range(argc):
                    args.insert(0, frame.stack.pop())
                func = frame.stack.pop()

                # TODO: get dict from TOS for given kwargs
                #kwargs = dict(func.kwargs)
                #kwargs.update(stack_kwargs)
                kwargs = {}

                #print("call", func, args, kwargs)

                if isinstance(func, JsFunction):
                    posargs = {}
                    for i, lbl in enumerate(func.fndef.arglabels):

                        if i < len(args):
                            val = args[i] # given value
                        else:
                            val = func.args[i] # default value

                        posargs[lbl] = val

                    # TODO: rest parameters
                    rest = []
                    if len(args) > len(func.fndef.arglabels):
                        rest = args[len(func.fndef.arglabels):]

                    new_frame = VmStackFrame(func.module, func.fndef)
                    new_frame.locals = posargs
                    self.stack_frames.append(new_frame)
                    frame.sp += 1
                    frame = self.stack_frames[-1]
                    instrs = frame.fndef.instrs
                    continue
                else:
                    frame.stack.append(func(*args, **kwargs))
            elif instr.opcode == opcodes.ctrl.RETURN:
                rv = frame.stack.pop()
                if frame.stack:
                    print(frame.stack)
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
            elif instr.opcode == opcodes.localvar.SET:
                name = frame.local_names[instr.args[0]]
                frame.locals[name] = frame.stack.pop()
            elif instr.opcode == opcodes.localvar.GET:
                name = frame.local_names[instr.args[0]]
                frame.stack.append(frame.locals[name])
            elif instr.opcode == opcodes.localvar.DELETE:
                name = frame.local_names[instr.args[0]]
                del frame.locals[name]
            elif instr.opcode == opcodes.globalvar.SET:
                name = frame.globals.names[instr.args[0]]
                frame.globals.values[name] = frame.stack.pop()
            elif instr.opcode == opcodes.globalvar.GET:
                name = frame.globals.names[instr.args[0]]
                frame.stack.append(frame.globals.values[name])
            elif instr.opcode == opcodes.globalvar.DELETE:
                name = frame.globals.names[instr.args[0]]
                del frame.globals.values[name]
            elif instr.opcode == opcodes.cellvar.SET:

                raise NotImplementedError()
            elif instr.opcode == opcodes.cellvar.GET:

                raise NotImplementedError()
            elif instr.opcode == opcodes.cellvar.DELETE:

                raise NotImplementedError()
            elif instr.opcode == opcodes.ctrl.TRY:

                frame.blocks.append(VmTryBlock(frame.sp, instr))
            elif instr.opcode == opcodes.ctrl.CATCH:

                pass
            elif instr.opcode == opcodes.ctrl.FINALLY:

                pass
            elif instr.opcode == opcodes.ctrl.THROW:

                fidx_, bidx_ = _get_exception_frame(self.stack_frames, len(self.stack_frames)-1)

                if fidx_ == 0 and bidx_ == 0:
                    print("unhandled exception")
                else:
                    frame_ = self.stack_frames[fidx_]
                    block_ = frame_.blocks[bidx_]
                    print(frame_)
                    print(block_)


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
            elif instr.opcode == opcodes.obj.GET_INDEX:
                obj = frame.stack.pop()
                index = frame.stack.pop()
                print("GET_INDEX", obj, index)
                if isinstance(obj, JsObject):
                    val = obj.getIndex(index)
                else:
                    val = obj[index]

                frame.stack.append(val)
            elif instr.opcode == opcodes.obj.SET_INDEX:

                obj = frame.stack.pop()
                index = frame.stack.pop()
                val = frame.stack.pop()
                print("SET_INDEX", obj, index, val)
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

                fnidx, argc = instr.args

                args = []
                for i in range(argc):
                    args.insert(0, frame.stack.pop())

                fn = JsFunction(frame.module, frame.module.functions[fnidx], args, {})
                frame.stack.append(fn)
            elif instr.opcode == opcodes.obj.CREATE_FUNCTION_KWARG:

                raise NotImplementedError()
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
                    args.append(val)

                frame.stack.append(JsArray(args))
            elif instr.opcode in unary_op:
                rhs = frame.stack.pop()
                frame.stack.append(unary_op[instr.opcode](lhs, rhs))
            elif instr.opcode in binary_op:
                rhs = frame.stack.pop()
                lhs = frame.stack.pop()
                #print(binary_op[instr.opcode], lhs, rhs)
                frame.stack.append(binary_op[instr.opcode](lhs, rhs))
            elif instr.opcode == opcodes.const.STRING:
                frame.stack.append(frame.globals.constdata[instr.args[0]])
            elif instr.opcode == opcodes.const.INT:
                frame.stack.append(instr.args[0])
            elif instr.opcode == opcodes.const.UNDEFINED:
                frame.stack.append(JsUndefined.instance)

            else:
                raise Exception("%r" % instr)

            frame.sp += 1

        return return_value, frame.globals


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

        try {
            throw "error"
        } catch (ex) {
            console.log(ex)
        } finally {
            console.log("done")
        }


    """

    tokens = Lexer().lex(text1)
    parser = Parser()
    parser.python = True
    ast = parser.parse(tokens)

    xform = TransformIdentityScope()
    xform.disable_warnings=True
    xform.transform(ast)
    print(ast.toString(1))

    compiler = VmCompiler()
    module = compiler.compile(ast)
    module.dump()

    runtime = VmRuntime()
    runtime.init(module)
    runtime.run()




if __name__ == '__main__':
    main()