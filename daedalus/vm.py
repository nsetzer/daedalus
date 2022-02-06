#! cd .. && python -m daedalus.vm

"""

TODO: transformations:
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
import traceback

from . import vm_opcodes as opcodes

from .token import Token, TokenError
from .lexer import Lexer
from .parser import Parser, ParseError
from .transform import TransformBaseV2, TransformIdentityScope

from .vm_compiler import VmCompiler, VmTransform, VmInstruction, VmClassTransform

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
        s = ",".join([str(s) for s in self.data.keys()])
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
        if JsString(index).value == "_x_daedalus_js_prop_iterator":
            if "_x_daedalus_js_prop_iterator" in self.data:
                rv =self.data["_x_daedalus_js_prop_iterator"]
                return rv
            return JsObjectPropIterator(self)

        if index in self.data:
            return self.data[index]
        print("get undefined index %s" % index, type(index))
        return JsUndefined.instance

    def setIndex(self, index, value):
        self.data[index] = value

    def delIndex(self, index):
        del self.data[index]

    @staticmethod
    def keys(inst):
        x = JsArray(inst.data.keys())
        return x

    @staticmethod
    def getOwnPropertyNames(object):
        return JsArray()

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
                    fn(this[i])
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
        #print("resolve promise", res)
        self._state = JsPromise.FULFILLED
        self._result = res

    def _reject(self, err):
        #print("reject promise", res)
        self._state = JsPromise.REJECTED
        self._error = err

    @jsc
    def _then(self):
        return """
            function _then(onFulfilled, onRejected) {
                // onFulfilled : value => {}
                // onRejected : reason => {}

                // TODO: wait for state to be 2 or 3

                if (this._state === 2) {
                    if (onFulfilled) {
                        onFulfilled(this._result)
                    }
                } else {
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
        self.body = JsElement()

    @staticmethod
    def createElement(name):

        elem = JsElement()

        elem.setAttr("sheet", JsElement())

        print("createElement:", id(elem), id(elem.getAttr("sheet")))

        return elem

class JsElement(JsObject):

    def __init__(self):
        super(JsElement, self).__init__(None)

        self.rules = JsArray()
        self.children = []

    #def __repr__(self):
    #    x = super().__repr__()
    #    return "<JsElement(" + str(self.rules) + "," + str(self.children) + ")>" + x

    def toString(self):
        print("!tostring", id(self))

        type_ = self.getAttr("type")
        if type_ == "text/css":
            elem = self.getAttr("sheet")
            for rule in elem.rules.array:
                print("!tostring", rule)
        else:
            print("--", self, type_)
            print("--", self.rules.array)
            for child in self.children:
                child.toString()

    def appendChild(self, child):
        self.children.append(child)
        print("appendChild:",  id(self), child)

    def insertRule(self, text, index=0):
        print("insertRule:", id(self), text)
        self.rules.push(text)

    def addRule(self, selector, text):
        self.insertRule(selector + " {" + text + "}", self.rules.length)

class JsWindow(JsObject):

    def __init__(self):
        super(JsWindow, self).__init__()



    def addEventListener(self, event, callback):
        pass

    def requestIdleCallback(self, callback, options):
        print("requestIdleCallback", callback, options)

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

class VmReference(object):

    def __init__(self, name, value):
        super(VmReference, self).__init__()
        self.name = name
        self.value = value

    def __repr__(self):
        return "<Ref(%s, %s)>" % (self.name, self.value)

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

class VmRuntimeException(Exception):
    def __init__(self, frames, message):
        super(VmRuntimeException, self).__init__(message)
        self.frames = frames



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
        _Symbol = lambda: None
        _Symbol.iterator = "_x_daedalus_js_prop_iterator"

        history = lambda: None
        history.pushState = lambda x: None

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
            self.builtins['Symbol'] = _Symbol
            self.builtins['history'] = history

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
                self._print_trace()
            raise e

    def _get_trace(self):
        return list(reversed(self.stack_frames))

    def _print_trace(self, frames=None):
        if frames is None:
            frames = reversed(self.stack_frames)
        for idx, frame in enumerate(frames):

            print("frame", idx)
            # print(frame.locals)
            # print(frame.globals)
            print("  path", frame.module.path)
            instr = frame.fndef.instrs[frame.sp]
            print("  sp", frame.sp, "line", instr.line, "column", instr.index)
            print("***")

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
            if arglabel in func.fndef.cell_names and arglabel not in func.fndef.free_names:
                ref = VmReference(arglabel, posargs.getAttr(arglabel))
                func.cells.setAttr(arglabel, ref)
                del posargs.data[arglabel]

        # TODO: maybe remove the ref creation from the cellvar.LOAD instr
        for name in func.fndef.cell_names:
            if not func.cells._hasAttr(name):
                ref = VmReference(name, JsUndefined.instance)
                func.cells.setAttr(name, ref)

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

                kwargs = JsObject()

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
                    _rv = func(*args, **kwargs.data)
                    frame.stack.append(_rv)
                else:
                    print("Error at line %d column %d (%s)" % (instr.line, instr.index, type(func)))

            elif instr.opcode == opcodes.ctrl.CALL_KW:

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
                    _rv = func(*args, **kwargs.data)
                    frame.stack.append(_rv)
                else:
                    print("Error at line %d column %d (%s)" % (instr.line, instr.index, type(func)))

            elif instr.opcode == opcodes.ctrl.CALL_EX:
                kwargs = frame.stack.pop()
                posargs = frame.stack.pop()
                func = frame.stack.pop()

                if isinstance(func, JsFunction):

                    new_frame = self._new_frame(func, len(posargs.array), posargs.array, kwargs)

                    self.stack_frames.append(new_frame)
                    frame.sp += 1
                    frame = self.stack_frames[-1]
                    instrs = frame.fndef.instrs
                    continue
                elif callable(func):
                    _rv = func(*posargs.array, **kwargs.data)
                    frame.stack.append(_rv)
                else:
                    print("Error at line %d column %d" % (instr.line, instr.index))

            elif instr.opcode == opcodes.ctrl.RETURN:
                rv = frame.stack.pop()
                if frame.stack:
                    print("warning: stack not empty", frame.stack)
                    #self._print_trace()
                    #traceback.print_stack()
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
                        trace = self._get_trace()
                        frame_, block = self._unwind()
                        if frame_ is None:
                            raise VmRuntimeException(trace, "unhandled exception")
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

                trace = self._get_trace()
                frame_, block = self._unwind()
                if frame is None:
                    raise VmRuntimeException(trace, "unhandled exception")
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
                    print("TODO: unreachable?")
                    frame.cells.setAttr(name, VmReference(name, JsUndefined.instance))
                tos = frame.cells.getAttr(name)
                frame.stack.append(tos)
            elif instr.opcode == opcodes.cellvar.SET:
                name = frame.fndef.cell_names[instr.args[0]]
                if not frame.cells._hasAttr(name):
                    print("TODO: unreachable?")
                    frame.cells.setAttr(name, VmReference(name, JsUndefined.instance))
                tos = frame.stack.pop()
                frame.cells.getAttr(name).value = tos
            elif instr.opcode == opcodes.cellvar.GET:
                name = frame.fndef.cell_names[instr.args[0]]
                if not frame.cells._hasAttr(name):
                    print("TODO: unreachable?")
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
                if obj is JsUndefined.instance:
                    val = JsString("undefined")
                elif isinstance(obj, JsString):
                    val = JsString("string")
                elif isinstance(obj, JsObject):
                    val = JsString(obj.type_name)
                else:
                    print("typename of", obj)
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
                    args.insert(0, (key, val))

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

                frame.stack.append(JsString(frame.globals.constdata[instr.args[0]]))
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

        return return_value, frame.globals

class VmLoader(object):
    def __init__(self,):
        super(VmLoader, self).__init__()

        self.runtime = VmRuntime()

    def _load_path(self, path):
        text = open(path).read()

        return self._load_text(text)

    def _load_text(self, text, debug=False):

        tokens = Lexer().lex(text)
        parser = Parser()
        parser.feat_xform_optional_chaining = True
        parser.python = True
        ast = parser.parse(tokens)

        xform = VmClassTransform()
        xform.transform(ast)

        xform = TransformIdentityScope()
        xform.disable_warnings=True
        xform.transform(ast)

        xform = VmTransform()
        xform.transform(ast)

        if debug:
            print(ast.toString(1))

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

            dep_mod = self._load_path(inc_path)
            dep_mod.depth = depth
            dep_mod.path = inc_path
            self._fix_mod(dep_mod)

            visited[inc_path] = dep_mod

            includes.extend([(depth+1, p) for p in dep_mod.includes])

        mods = sorted(visited.items(), key=lambda x: x[1].depth, reverse=True)
        for mod_path, mod in mods:
            print("load", mod.depth, mod.path)

            for inc_path in mod.includes:
                mod2 = visited[inc_path]
                for name, value in mod2.globals.values.items():
                    mod.globals.values[name] = value
                #for name in mod.globals.names:
                #    if name in mod2.globals.values and name not in mod.globals.values:
                #        print(mod_path, name)
                #        mod.globals.values[name] = mod2.globals.values[name]

            if mod is root_mod:
                break
            self.runtime.enable_diag = False
            self.runtime.init(mod)
            try:
                rv, _globals = self.runtime.run()
                #print(_globals.values)
            except Exception as e:
                print("error in ", mod.path)
                raise e


        print("=*" + "="*68)
        self.runtime.enable_diag = True
        self.runtime.init(root_mod)
        rv, mod_globals = self.runtime.run()

        print("return value", rv)
        print("globals", mod_globals.values)

        return rv, mod_globals


    def run_path(self, path):

        path = os.path.abspath(path)
        root_mod = self._load_path(path)
        root_dir = os.path.split(path)[0]
        root_mod.path = path

        return self._load(root_mod, root_dir, path)

    def run_text(self, text):

        root_mod = self._load_text(text, True)
        root_dir = "./"
        root_name = "__main__"
        root_mod.path = root_name

        return self._load(root_mod, root_dir, root_name)

def main():

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

    text1 = """

        //console.log(typeof({})==='object')

        class A { constructor() {} }
        let a = new A()
        let b = typeof(a)
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

    text1 = """
        obj = {a:0, b:1, c:2}

        s = ""
        for (const key in obj) {
            s += `${key}=>${obj[key]};`
        }

    """


    text1 = """

        include "./res/daedalus/daedalus.js"

        //console.log(generateStyleSheetName())
        //console.log(randomInt(0,100))
        //document.head.toString()
        //let e = new DomElement("div")
        //console.log(e.props.id)
    """
    text1 = """
        //(function() {
        //    "use strict";
        //})()
    """

    text1 = """

        //function randomInt(min, max) {
        //    rnd = Math.random()
        //    min = Math.ceil(min);
        //    max = Math.floor(max);
        //    return Math.floor(rnd * (max - min + 1)) + min;
        //}
        //console.log(randomInt(0, 100))

    """

    text1 = """
        let [a,b,c] = [1,2,3]
        console.log(a+b+c)
    """

    # this test is the reason for the per-identity transform
    text1 = """

        mymodule = (function() {
            class a {

            }

            class b extends a {

            }

            return {a, b}
        })()
    """

    # should not leave anything on the stack
    text1 = """
        "a";
        8;
    """

    text1 = """
        include "../morpgsite/frontend/build/static/index.js";
    """

    if False:
        tokens = Lexer().lex(text1)
        parser = Parser()
        parser.feat_xform_optional_chaining = True
        parser.python = True
        ast = parser.parse(tokens)
        print(ast.toString(1))
        xform = TransformIdentityScope()
        xform.disable_warnings=True
        xform.transform(ast)

        xform = VmTransform()
        xform.transform(ast)

        print(ast.toString(2))

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
    rv, globals_ = loader.run_text(text1)

    if 'obj' in globals_.values:
        print(JsObject.keys(globals_.values['obj']))
    return

if __name__ == '__main__':
    main()