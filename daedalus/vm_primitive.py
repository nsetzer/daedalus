import os
import sys
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
import traceback
import urllib.request

from . import vm_opcodes as opcodes

from .token import Token, TokenError
from .lexer import Lexer
from .parser import Parser, ParseError
from .transform import TransformBaseV2, TransformIdentityBlockScope
from .builder import findModule

from .vm_compiler import VmCompiler, VmTransform, VmInstruction, \
    VmClassTransform2

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

def vmGetAst(text):

    tokens = Lexer().lex(text)
    parser = Parser()
    parser.feat_xform_optional_chaining = True
    parser.python = True
    ast = parser.parse(tokens)

    xform = VmClassTransform2()
    xform.transform(ast)

    xform = TransformIdentityBlockScope()
    xform.disable_warnings=True
    xform.transform(ast)

    xform = VmTransform()
    xform.transform(ast)

    return ast

class VmFunction(object):
    def __init__(self, module, fndef, args, kwargs, bind_target, cells=None, prototype=None):
        super(VmFunction, self).__init__()
        # the module this function belongs to
        # TODO: should this be part of the fndef?
        self.module = module
        # the VmFunctionDef
        self.fndef = fndef
        # a sequence of positional arguments
        self.args = args
        # an instance of JsObject
        # a mapping of keyword arguments
        self.kwargs = kwargs
        # the object pointed to by 'this'
        self.bind_target = bind_target
        # an instance of JsObject
        self.cells = cells
        # an instance of JsObject
        self.prototype = prototype

    def __repr__(self):

        return "<VmFunction(%s)>" % (",".join(self.fndef.arglabels))

    def bind(self, target):

        fn = VmFunction(self.module, self.fndef, self.args, self.kwargs, target, self.cells, self.prototype)
        return fn

class jsc_factory(object):
    # failed experiment trying to make jsc not execute on import
    def __init__(self, fn):
        super(jsc_factory, self).__init__()

        self.fn = fn

    def __call__(self, *args, **kwargs):
        attrs = self.fn.__qualname__.split(".")[:-1]
        module = sys.modules[self.fn.__module__]
        for attr in attrs:
            module = getattr(module, attr)
        text = self.fn(None)
        ast = vmGetAst(text)
        compiler = VmCompiler()
        module = compiler.compile(ast)
        fn = VmFunction(module, module.functions[1], None, None, None, None, None)
        setattr(module, self.fn.__name__, fn)
        return fn

def jsc(fn):
    """
    A Decorator function which compiles a class method as a javascript function
    the class method should be a instance method returning a string. That
    string will be parsed as javascript and compiled.
    """

    text = fn(None)

    ast = vmGetAst(text)

    compiler = VmCompiler()
    module = compiler.compile(ast)

    #if debug:
    #    print(ast.toString(1))
    #    module.dump()

    fn = VmFunction(module, module.functions[1], None, None, None, None, None)

    return fn

class JsObject(object):

    type_name = "object"

    def __init__(self, args=None):
        super(JsObject, self).__init__()

        if args:
            self._data = dict(args)
        else:
            self._data = {}

    def __repr__(self):
        # s = ",".join(["%r: %r" % (key, value) for key, value in self.data.items()])
        s = ",".join([str(s) for s in self._data.keys()])
        return "<%s(%s)>" % (self.__class__.__name__, s)

    def _hasAttr(self, name):
        if isinstance(name, JsString):
            name = name.value
        return name in self._data

    def getAttr(self, name):
        if isinstance(name, JsString):
            name = name.value

        if hasattr(self, name):
            attr = getattr(self, name)
            if isinstance(attr, VmFunction):
                attr = attr.bind(self)
            return attr

        elif name in self._data:
            return self._data[name]

        #print("get undefined attribute %s" % name)
        return JsUndefined.instance

    def setAttr(self, name, value):
        if isinstance(name, JsString):
            name = name.value
        self._data[name] = value

    def delAttr(self, name):
        if isinstance(name, JsString):
            name = name.value
        del self._data[name]

    def getIndex(self, index):
        if JsString(index).value == "_x_daedalus_js_prop_iterator":
            if "_x_daedalus_js_prop_iterator" in self._data:
                rv =self._data["_x_daedalus_js_prop_iterator"]
                return rv
            return JsObjectPropIterator(self)

        if index in self._data:
            return self._data[index]
        #print("get undefined index %s" % index, type(index))
        return JsUndefined.instance

    def setIndex(self, index, value):
        self._data[index] = value

    def delIndex(self, index):
        del self._data[index]

    @staticmethod
    def keys(inst):
        x = JsArray([JsString(s) for s in inst._data.keys()])
        return x

    @staticmethod
    def getOwnPropertyNames(object):
        return JsArray()

    def _x_update(self, other):
        self._data.update(other._data)

class JsObjectPropIterator(object):
    def __init__(self, obj):
        super(JsObjectPropIterator, self).__init__()
        self.obj = obj

        if isinstance(obj, JsArray):
            self.array = obj.array
        elif isinstance(obj, JsObject):
            self.array = JsObject.keys(obj).array

        self.index = 0

    def __call__(self):
        return self

    def next(self):

        result = lambda: None
        if self.index < len(self.array):
            result.value = self.array[self.index]
            result.done = False
            self.index += 1
        else:
            result.value = JsUndefined.instance
            result.done = True

        return result

class JsObjectCtor(JsObject):

    def __call__(self, *args, **kwargs):
        if args and isinstance(args[0], (int, float)):
            return args[0]
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
        if JsString(index).value == "_x_daedalus_js_prop_iterator":
            return JsObjectPropIterator(self)
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

    def pop(self):
        return self.array.pop()

    def slice(self, start=None, end=None):

        if start is None and end is None:
            return JsArray(self.array[:])
        elif end is None:
            return JsArray(self.array[start:])
        else:
            return JsArray(self.array[start:end])

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

    @staticmethod
    def isArray(other):
        return isinstance(other, JsArray)

    @jsc
    def filter(self):
        return """
            function filter(fn) {
                out = []
                for (let i=0; i < this.length; i++) {
                    const v = this[i]
                    if (fn(v)) {
                        out.push(v)
                    }
                }
                return out
            }
        """
    @jsc
    def forEach(self):
        return """
            function forEach(fn) {
                for (let i=0; i < this.length; i++) {
                    fn(this[i], i)
                }
            }
        """

class JsSet(JsObject):
    type_name = "Set"

    def __init__(self, args=None):
        super(JsSet, self).__init__(None)

        if args:
            self.seq = set(args)
        else:
            self.seq = set()

    @property
    def size(self):
        return len(self.seq)

def _apply_value_operation(cls, op, a, b):
    if not isinstance(b, JsObject):
        b = cls(b)

    if a is None:
        a = JsString("null")

    if b is None:
        b = JsString("null")

    if isinstance(a, JsUndefined):
        a = JsString("undefined")

    if isinstance(b, JsUndefined):
        b = JsString("undefined")

    if isinstance(a, JsString) or isinstance(b, JsString):
        if isinstance(a, (int, float, str)):
            a = JsString(a)
        if isinstance(b, (int, float, str)):
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

class JsNumberObject(JsObject):

    @property
    def MAX_VALUE(self):
        return 1.7976931348623157e+308

    @property
    def MIN_VALUE(self):
        return 5e-324

    @property
    def NaN(self):
        return math.nan

    @property
    def NEGATIVE_INFINITY(self):
        # TODO: bubbling of python exceptions isnt working correctly
        #       a real unrelated python attribute error is treated
        #       as if this property is undefined. the attribute error
        #       is being squashed
        #raise ValueError()
        #raise AttributeError()
        return -math.inf

    @property
    def POSITIVE_INFINITY(self):
        return math.inf

    @property
    def EPSILON(self):
        return 2.220446049250313e-16

    @property
    def MIN_SAFE_INTEGER(self):
        return -9007199254740991

    @property
    def MAX_SAFE_INTEGER(self):
        return 9007199254740991

    def parseFloat(self, string):
        pass

    def parseInt(self, string):
        pass

    def isFinite(self, value):
        return math.isFinite(value)

    def isInteger(self, value):
        return int(value)==value

    def isNaN(self, value):
        return math.isnan(value)

    def isSafeInteger(self, value):
        pass

    def toExpenential(self, value) -> str:
        pass

    def toFixed(self, value) -> str:
        pass

    def toPrecision(self, value) -> str:
        pass

class JsMath(JsObject):

    @property
    def E(self):
        return math.e

    @property
    def PI(self):
        return math.pi

    def abs(self, value):
        # https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Math/abs
        return abs(value)

    def acos(self, value):
        pass

    def acosh(self, value):
        pass

    def asin(self, value):
        pass

    def asinh(self, value):
        pass

    def atan(self, value):
        pass

    def atan2(self, value):
        pass

    def atanh(self, value):
        pass

    def cbrt(self, value):
        pass

    def ceil(self, value):
        return math.ceil(value)

    def clz32(self, value):
        pass

    def cos(self, value):
        pass

    def cosh(self, value):
        pass

    def exp(self, value):
        pass

    def expm1(self, value):
        pass

    def floor(self, value):
        return math.floor(value)

    def fround(self, value):
        pass

    def hypot(self, value):
        pass

    def imul(self, value):
        pass

    def log(self, value):
        pass

    def log10(self, value):
        pass

    def log1p(self, value):
        pass

    def log2(self, value):
        pass

    def max(self, *args):
        return max(args)

    def min(self, *args):
        return min(args)

    def pow(self, x, y):
        return x**y

    def random(self):
        return random.random()

    def round(self, value):
        return math.round(value)

    def sign(self, value):
        if value < 0:
            return -1
        elif value > 0:
            return 1
        return 0

    def sinh(self, value):
        pass

    def sqrt(self, value):
        return math.sqrt(value)

    def tan(self, value):
        pass

    def tanh(self, value):
        pass

    def trunc(self, value):
        return int(value)

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
            return JsString(self.value[index])
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

    def matchAll(self, regexp):
        pass

    def startsWith(self, substr):
        return bool(self.value.startswith(substr.value))

    def charAt(self, index):
        return self.value[index]

    def toUpperCase(self):
        return JsString(self.value.upper())

    def toLowerCase(self):
        return JsString(self.value.lower())

    def concat(self, *strings):
        arr = [self.value,] + [st.value for st in strings]
        return JsString("".join(arr))

    def includes(self, searchString):
        pass

    def endswith(self, searchString):
        pass

    def padEnd(self, targetLength, string):
        pass

    def padStart(self, targetLength, string):
        pass

    def repeat(self, count):
        pass

    def substring(self, index):
        return JsString(self.value[index:])

    @jsc
    def replace(self):
        """
        https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/String/replace

        :param pattern: string or object with Symbol.replace method, a regex.
                        or coerced to a string
        :param replacement: a string or a function that is invoked for every match
                            returning a string to replace with
        """

        return """
            function replace(pattern, replacement) {
                console.log(pattern, replacement)
            }
        """


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