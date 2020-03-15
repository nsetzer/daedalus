import threading
import json
import sys
import time
import random
import inspect
import math
import types

from .lexer import Lexer, Token, TokenError

def _dumps_impl(obj):
    if isinstance(obj, types.FunctionType):
        return "<Function>"
    elif isinstance(obj, types.LambdaType):
        return "<Lambda>"
    elif isinstance(obj, JsObject):
        return obj._x_daedalus_js_attrs
    elif isinstance(obj, JsArray):
        return obj._x_daedalus_js_seq
    elif isinstance(obj, JsUndefined):
        return "undefined"

    # default Js Object
    elif isinstance(obj, JsObjectBase):
        return "[Object]"
    return obj

def dumps(obj, indent=None):
    return json.dumps(obj, default=_dumps_impl, indent=indent)

def jsstr(obj):
    if isinstance(obj, types.FunctionType):
        return "<Function>"
    elif isinstance(obj, types.LambdaType):
        return "<Lambda>"
    elif isinstance(obj, JsObject):
        text = "{"
        for key, val in obj._x_daedalus_js_attrs.items():
            text += dumps(key) + ":" + jsstr(val)
        text += "}"
        return dumps(obj._x_daedalus_js_attrs)
    elif isinstance(obj, JsArray):
        return dumps(obj._x_daedalus_js_seq)
    elif isinstance(obj, JsUndefined):
        return "undefined"

    # default Js Object
    elif isinstance(obj, JsObjectBase):
        return "[Object]"

    elif obj is None:
        return "null"
    elif obj is True:
        return "true"
    elif obj is False:
        return "false"
    return str(obj)

class JsObjectBase(object):
    def __init__(self):
        super(JsObjectBase, self).__init__()

class JsStr(str):

    def __add__(self, other):
        if not isinstance(other, str):
            other = str(other)
        return JsStr(super().__add__(other))

    def __radd__(self, other):
        if not isinstance(other, str):
            other = str(other)
        return JsStr(super().__radd__(other))

JsStr.Token = Token(Token.T_TEXT, 0, 0, "JsStr")

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
JsUndefined.Token = Token(Token.T_TEXT, 0, 0, "undefined")

class JsArray(JsObjectBase):
    def __init__(self, seq):
        super(JsArray, self).__init__()

        self._x_daedalus_js_seq = list(seq)

    def __str__(self):
        return dumps(self)

    def __repr__(self):
        return dumps(self)

    def __getitem__(self, index):
        return self._x_daedalus_js_seq[index]

    def __setitem__(self, index, value):
        self._x_daedalus_js_seq[index] = value

    @property
    def length(self):
        return len(self._x_daedalus_js_seq)

    def push(self, item):
        self._x_daedalus_js_seq.append(item)

    def pop(self):
        return self._x_daedalus_js_seq.pop()

    def shift(self):
        return self._x_daedalus_js_seq.pop(0)

    def unshift(self, item):
        self._x_daedalus_js_seq.insert(0, item)
        return len(self._x_daedalus_js_seq)

    def indexOf(self, item):
        return self._x_daedalus_js_seq.find(item)

    def splice(self, pos, count=0, item=JsUndefined._instance):
        end = pos + count
        rv = self._x_daedalus_js_seq[pos:end]
        if item is not JsUndefined._instance:
            self._x_daedalus_js_seq = self._x_daedalus_js_seq[:pos] + [item] + self._x_daedalus_js_seq[end:]
        else:
            self._x_daedalus_js_seq = self._x_daedalus_js_seq[:pos] + self._x_daedalus_js_seq[end:]
        return rv

    def slice(self, begin=JsUndefined._instance, end=JsUndefined._instance):
        if begin is JsUndefined._instance and end is JsUndefined._instance:
            return JsArray(self._x_daedalus_js_seq)
        elif end is JsUndefined._instance:
            return JsArray(self._x_daedalus_js_seq[begin:])
        elif begin is JsUndefined._instance:
            return JsArray(self._x_daedalus_js_seq[:end])
        return JsArray(self._x_daedalus_js_seq[begin:end])

    def forEach(self, fn):
        argcount = fn.__code__.co_argcount

        for index, item in enumerate(self._x_daedalus_js_seq):
            args = []
            if argcount >= 1:
                args.append(item)
            if argcount >= 2:
                args.append(index)
            if argcount >= 3:
                args.append(self)

            fn(*args)

    def filter(self, fn, this=JsUndefined._instance):
        # TODO: unused: this
        argcount = fn.__code__.co_argcount

        out = []
        for index, item in enumerate(self._x_daedalus_js_seq):
            args = []
            if argcount >= 1:
                args.append(item)
            if argcount >= 2:
                args.append(index)
            if argcount >= 3:
                args.append(self)

            if fn(*args):
                out.append(item)

        return JsArray(out)

    def join(self, sep):
        # TODO: stringify each element
        return sep.join(self._x_daedalus_js_seq)


JsArray.Token = Token(Token.T_TEXT, 0, 0, "JsArray")

class JsObject(JsObjectBase):
    def __init__(self, attrs=None):
        super(JsObject, self).__init__()

        if attrs is None:
            attrs = {}

        super(JsObject, self).__setattr__('_x_daedalus_js_attrs', attrs)

    def __str__(self):
        return dumps(self)

    def __repr__(self):
        return dumps(self)

    def __getattr__(self, name):
        try:
            return self._x_daedalus_js_attrs[name]
        except KeyError:
            return JsUndefined._instance

    def __setattr__(self, name, value):
        self._x_daedalus_js_attrs[name] = value

    def __getitem__(self, key):
        return self._x_daedalus_js_attrs[key]

    def __setitem__(self, key, value):
        self._x_daedalus_js_attrs[key] = value

    @property
    def length(self):
        return len(self._x_daedalus_js_attrs)

    @staticmethod
    def keys(inst):
        return JsArray([key
            for key in inst._x_daedalus_js_attrs.keys()
            if isinstance(key, str)])

    @staticmethod
    def values(inst):
        return JsArray([inst._x_daedalus_js_attrs[key]
            for key in inst._x_daedalus_js_attrs.keys()
            if isinstance(key, str)])


# workaround the 'is' keyword by setting the attribute directly
setattr(JsObject, 'is', lambda a, b: a is b)

JsObject.Token = Token(Token.T_TEXT, 0, 0, "JsObject")

def JsNew(constructor, *args):

    if isinstance(constructor, JsFunction):
        obj = JsObject()
        constructor.fn(*args, this=obj)
        return obj
    else:
        return constructor(*args)


JsNew.Token = Token(Token.T_TEXT, 0, 0, "JsNew")

class JsFunction(JsObjectBase):
    def __init__(self, fn, this=None):
        super(JsFunction, self).__init__()
        self.fn = fn
        self.this = this

    def __call__(self, *args):
        return self.fn(*args, this=self.this)

    def bind(self, obj):
        return JsFunction(self.fn, obj)

JsFunction.Token = Token(Token.T_TEXT, 0, 0, "JsFunction")

class JsArguments(JsObjectBase):
    """ Access function arguments through array-like syntax

    In Javascript the built-in variable 'arguments' can access
    the arguments of the current function. Using stack
    inspection this can be implemented in python without
    needing to modify the creation of functions

    """

    def __init__(self):
        super(JsArguments, self).__init__()

    def __getitem__(self, index=0):
        """ inspect the previous stack frame and retrieve the value
        of the argument for the given index. return undefined if the
        index does not exist
        """
        rv = JsUndefined._instance

        if index < 0:
            return rv

        frame = inspect.currentframe()
        try:
            code = frame.f_back.f_code
            code_locals = frame.f_back.f_locals
            nvars = code.co_argcount

            if index < nvars:
                rv = code_locals[code.co_varnames[index]]
            else:
                # javascript functions store extra arguments inside
                # this magic variable
                if '_x_daedalus_js_args' in code_locals:
                    values = code_locals['_x_daedalus_js_args']
                    i = index - nvars
                    if i < len(values):
                        rv = values[i]

        finally:
            del frame

        return rv

    @property
    def length(self):
        """ inspect the previous stack frame and count the number of
        positional arguments passed in to that function

        """

        nvars = 0
        frame = inspect.currentframe()
        try:
            code = frame.f_back.f_code
            code_locals = frame.f_back.f_locals
            nvars = code.co_argcount

            if '_x_daedalus_js_args' in code_locals:
                nvars += len(code_locals['_x_daedalus_js_args'])

        finally:
            del frame

        return nvars

class JsConsole(JsObject):
    def __init__(self):
        super(JsConsole, self).__init__({})

    def log(self, *args):
        sys.stdout.write(' '.join(jsstr(arg) for arg in args) + "\n")

    def info(self, *args):
        sys.stderr.write('I: ' + ' '.join(jsstr(arg) for arg in args) + "\n")

    def warn(self, *args):
        sys.stderr.write('W: ' + ' '.join(jsstr(arg) for arg in args) + "\n")

    def error(self, *args):
        sys.stderr.write('E: ' + ' '.join(jsstr(arg) for arg in args) + "\n")

class JsPromise(JsObject):
    def __init__(self, fn):
        attrs = {
            'then': self._x_daedalus_js_then,
            'catch': self._x_daedalus_js_catch,
            'catch_': self._x_daedalus_js_catch
        }
        super(JsPromise, self).__init__(attrs)

        self.accepted = False
        self.value = None

        # TODO: using threads for now to quickly implement a parity feature
        # This should be revisited
        # An event queue could be implemented to eliminate threads
        lk = threading.Lock()
        cv = threading.Condition(lk)
        thread = threading.Thread(target=self._x_daedalus_js_resolve)

        super(JsObject, self).__setattr__('_x_daedalus_js_fn', fn)
        super(JsObject, self).__setattr__('_x_daedalus_js_thread', thread)
        super(JsObject, self).__setattr__('_x_daedalus_js_lk', lk)
        super(JsObject, self).__setattr__('_x_daedalus_js_cv', cv)
        super(JsObject, self).__setattr__('_x_daedalus_js_finished', False)

        thread.start()

    def __str__(self):
        return "Promise {}"

    def __repr__(self):
        return "Promise {}"

    def _x_daedalus_js_resolve(self):

        try:
            self._x_daedalus_js_fn(
                self._x_daedalus_js_accept,
                self._x_daedalus_js_reject)
        except Exception as e:
            # TODO: design Js Exception
            self._x_daedalus_js_reject(e)

    def _x_daedalus_js_accept(self, value):
        self._x_daedalus_js_finalize(value, True)

    def _x_daedalus_js_reject(self, value):
        self._x_daedalus_js_finalize(value, False)

    def _x_daedalus_js_finalize(self, value, accepted):

        with self._x_daedalus_js_lk:
            self.value = value
            self.accepted = accepted
            super(JsObject, self).__setattr__('_x_daedalus_js_finished', True)
            self._x_daedalus_js_cv.notify_all()

    def _x_daedalus_js_then(self, fnOnAccept, fnOnReject=None):

        return JsPromise(lambda fnAccept, fnReject:
            self._x_daedalus_js_then_impl(
                fnAccept, fnReject, fnOnAccept, fnOnReject))

    def _x_daedalus_js_then_impl(self, fnAccept, fnReject, fnOnAccept, fnOnReject):

        with self._x_daedalus_js_lk:
            while not self._x_daedalus_js_finished:
                self._x_daedalus_js_cv.wait()

            if self.accepted:
                if fnOnAccept:
                    fnAccept(fnOnAccept(self.value))
                else:
                    fnAccept(self.value)
            else:
                if fnOnReject:
                    fnReject(fnOnReject(self.value))
                else:
                    fnReject(self.value)

    def _x_daedalus_js_catch(self, fnOnReject):

        return JsPromise(lambda fnAccept, fnReject:
            self._x_daedalus_js_catch_impl(
                fnReject, fnOnReject))

    def _x_daedalus_js_catch_impl(self, fnReject, fnOnReject):
        with self._x_daedalus_js_lk:
            while not self._x_daedalus_js_finished:
                self._x_daedalus_js_cv.wait()

            if not self.accepted:
                if fnOnReject:
                    fnReject(fnOnReject(self.value))
                else:
                    fnReject(self.value)

class JsFetchResponse(JsObject):
    def __init__(self, response):
        super(JsFetchResponse, self).__init__({
            'status_code': 200,
            'text': lambda: response.text,
            'ok': 200 <= response.status_code <= 300
        })

def JsFetch(url, opts=None):

    def JsFetchImpl(accept, reject):
        try:
            response = requests.get(url)
            accept(JsFetchResponse(response))
        except Exception as e:
            reject(e)

    return JsPromise(JsFetchImpl)

class JsJSON(JsObjectBase):
    def __init__(self):
        super(JsJSON, self).__init__()

    @staticmethod
    def stringify(obj):
        return dumps(obj)

    @staticmethod
    def parse(string):
        # TODO: every array and map needs to be replaced
        # with the Js* type
        # this should be possible with a custom loader
        return json.loads(string)

class JsDate(JsObjectBase):
    def __init__(self):
        super(JsDate, self).__init__()

    @staticmethod
    def now():
        return int(time.time() * 1000)

class JsMath(JsObjectBase):
    def __init__(self):
        super(JsMath, self).__init__()

    @staticmethod
    def random():
        """ MDN and Python documentation agrees on the interval as [0, 1) """
        return random.random()

    @staticmethod
    def floor(value):
        return math.floor(value)

    @staticmethod
    def ceil(value):
        return math.ceil(value)

def JsTypeof(obj):
    raise NotImplementedError("javascript typeof")

JsTypeof.Token = Token(Token.T_TEXT, 0, 0, "JsTypeof")

def JsInstanceof(objValue, objType):
    return False

JsInstanceof.Token = Token(Token.T_TEXT, 0, 0, "JsInstanceof")

def defaultGlobals():
    names = {
        '__import__': __import__,
        '__builtins__': __builtins__, # for import
        'console': JsConsole(),
        'true': True,
        'false': False,
        'undefined': JsUndefined._instance,
        'null': None,
        'JsStr': JsStr,
        'JsObject': JsObject,
        'Object': JsObject,
        'JsArray': JsArray,
        'JsNew': JsNew,
        'Promise': JsPromise,
        'fetch': JsFetch,
        'arguments': JsArguments(),
        'JsFunction': JsFunction,
        'JSON': JsJSON,
        'Date': JsDate,
        'Math': JsMath,
        'JsTypeof': JsTypeof,
        'JsInstanceof': JsInstanceof,
    }
    return names