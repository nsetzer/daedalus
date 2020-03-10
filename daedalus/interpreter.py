#! cd .. && python3 -m daedalus.interpreter

import threading
import json
import ast
import dis
import types
import sys
import inspect
from collections import defaultdict

from .lexer import Lexer, Token, TokenError
from .parser import Parser, ParseError
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

class InterpreterError(TokenError):
    pass

ST_TRAVERSE = 0x001 # the token has not yet been visited
                # literals will be committed immediatley
ST_COMPILE = 0x002  # the token has been visited, commit to the output stream
ST_LOAD = 0x004 # compiling this token should push a value on the stack
ST_STORE = 0x008 # compiling this token will pop an item from the stack

# states starting at 0x100 are used to count the compilation phase
# and can be reused between token types.
ST_BRANCH_TRUE = 0x100
ST_BRANCH_FALSE = 0x200

ST_WHILE = 0x100

def _dumps_impl(obj):
    if isinstance(obj, types.FunctionType):
        return "<Function>"
    elif isinstance(obj, types.LambdaType):
        return "<Lambda>"
    elif isinstance(obj, JsObject):
        return  obj._x_daedalus_js_attrs
    elif isinstance(obj, JsArray):
        return  obj._x_daedalus_js_seq
    elif isinstance(obj, JsUndefined):
        return "undefined"

    # default Js Object
    elif isinstance(obj, JsObjectBase):
        return  "[Object]"
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
        return  dumps(obj._x_daedalus_js_attrs)
    elif isinstance(obj, JsArray):
        return  dumps(obj._x_daedalus_js_seq)
    elif isinstance(obj, JsUndefined):
        return "undefined"

    # default Js Object
    elif isinstance(obj, JsObjectBase):
        return  "[Object]"

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
        #TODO: unused: this
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

        #TODO: using threads for now to quickly implement a parity feature
        #This should be revisited
        #An event queue could be implemented to eliminate threads
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
            #TODO: design Js Exception
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


class Interpreter(object):

    CF_MODULE    = 1
    CF_REPL      = 2
    CF_NO_FAST   = 4

    def __init__(self, name="__main__", filename="<string>", globals=None, flags=0):
        super(Interpreter, self).__init__()

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
            Token.T_FUNCTIONCALL: self._traverse_functioncall,
            Token.T_ARGLIST: self._traverse_arglist,
            Token.T_BLOCK: self._traverse_block,
            Token.T_LAMBDA: self._traverse_lambda,
            Token.T_FUNCTION: self._traverse_function,
            Token.T_GROUPING: self._traverse_grouping,
            Token.T_BRANCH: self._traverse_branch,
            Token.T_WHILE: self._traverse_while,
            Token.T_OBJECT: self._traverse_object,
            Token.T_LIST: self._traverse_list,
            Token.T_NEW: self._traverse_new,
            Token.T_RETURN: self._traverse_return,
            Token.T_SUBSCR: self._traverse_subscr,

            Token.T_NUMBER: self._compile_literal_number,
            Token.T_STRING: self._compile_literal_string,
            Token.T_TEXT: self._compile_text,
            Token.T_ATTR: self._compile_attr,
            Token.T_KEYWORD: self._compile_keyword,
        }

        # compile methods produce opcodes after the token has
        # been traversed
        self.compile_mapping = {
            Token.T_BINARY: self._compile_binary,
            Token.T_FUNCTIONCALL: self._compile_functioncall,
            Token.T_BRANCH: self._compile_branch,
            Token.T_WHILE: self._compile_while,
            Token.T_OBJECT: self._compile_object,
            Token.T_LIST: self._compile_list,
            Token.T_NEW: self._compile_new,
            Token.T_RETURN: self._compile_return,
            Token.T_SUBSCR: self._compile_subscr,

            Token.T_NUMBER: self._compile_literal_number,
            Token.T_STRING: self._compile_literal_string,
            Token.T_TEXT: self._compile_text,
            Token.T_ATTR: self._compile_attr,
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
            'true': True,
            'false': False,
            'undefined': JsUndefined._instance,
            'null': None,
            'JsObject': JsObject,
            'Object': JsObject,
            'JsArray': JsArray,
            'JsNew': JsNew,
            'Promise': JsPromise,
            'fetch': JsFetch,
            'arguments': JsArguments(),
            'JsFunction': JsFunction,
            'JSON': JsJSON,
        }
        if globals:
            self.globals.update(globals)

        self.module_globals = set()

        self.next_label = 0

    def execute(self):
        return self.function_body()

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
                    raise InterpreterError(token, "token not supported")
            else:
                # traverse the AST to produce a linear sequence
                fn = self.traverse_mapping.get(token.type, None)
                if fn is not None:
                    fn(depth, state, token)
                else:
                    raise InterpreterError(token, "token not supported")

        if self.flags&Interpreter.CF_REPL or self.flags&Interpreter.CF_MODULE:
            instr = []
            for name in sorted(self.module_globals):
                tok1 = Token(Token.T_STRING, 0, 0, repr(name))
                kind1, index1 = self._token2index(tok1, load=True)
                tok2 = Token(Token.T_TEXT, 0, 0, name)
                kind2, index2 = self._token2index(tok2, load=True)
                self.bc.append(BytecodeInstr('LOAD_' + kind1, index1))
                self.bc.append(BytecodeInstr('LOAD_' + kind2, index2))
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


        flag0 = ST_TRAVERSE
        if token.value == "=":
            flag0 |= ST_STORE
        else:
            flag0 |= ST_LOAD

        flag1 = ST_TRAVERSE
        if token.value == "." and state&ST_STORE:
            flag1 |= ST_STORE
        else:
            flag1 |= ST_LOAD

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

        self._build_function(token, lambda_qualified_name, arglist, block)

    def _traverse_function(self, depth, state, token):

        name = token.children[0].value
        arglist = token.children[1]
        block = token.children[2]

        self._build_function(token, name, arglist, block, autobind=False)


        kind, index = self._token2index(Token(Token.T_TEXT, token.line, token.index, name), False)
        self.bc.append(BytecodeInstr('STORE_' + kind, index, lineno=token.line))

    def _build_function(self, token, name, arglist, block, autobind=True):
        """ Create a new function

        Use a new Interpreter to compile the function. the name and code
        object are stored as constants inside the current scope
        """
        flags = 0
        sub = Interpreter(name, self.bc.filename, flags)


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


        # finally compile the function, get the code object
        sub.compile(block)
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
        self.bc.consts.append(name)

        # flag indicating positional args have a default value
        flg = 0x01
        # flag indicating a dictionary is being passed for keyword
        # only arguments
        flg |= 0x02

        self.bc.append(BytecodeInstr('LOAD_CONST', index_code, lineno=token.line))
        self.bc.append(BytecodeInstr('LOAD_CONST', index_name, lineno=token.line))

        self.bc.append(BytecodeInstr('MAKE_FUNCTION', flg, lineno=token.line))

        argcount = 1
        if autobind:
            kind, index = self._token2index(Token(Token.T_TEXT, 0, 0, 'this'), True)
            self.bc.append(BytecodeInstr('LOAD_' + kind, index, lineno=token.line))
            argcount += 1

        #TODO: pop top if state&ST_LOAD is false
        self.bc.append(BytecodeInstr('CALL_FUNCTION', argcount, lineno=token.line))

    def _traverse_grouping(self, depth, state, token):
        for child in reversed(token.children):
            self._push(depth+1, ST_TRAVERSE, child)

    def _traverse_branch(self, depth, state, token):

        arglist = token.children[0]
        self._push(depth, ST_COMPILE|ST_BRANCH_TRUE, token)
        self._push(depth+1, ST_TRAVERSE|ST_LOAD, arglist)

    def _traverse_while(self, depth, state, token):

        token.label_begin = self._make_label()
        token.label_end = self._make_label()

        nop = BytecodeInstr('NOP')
        self.bc.append(nop)
        nop.add_label(token.label_begin)

        arglist = token.children[0]
        self._push(depth, ST_COMPILE|ST_WHILE, token)
        self._push(depth+1, ST_TRAVERSE|ST_LOAD, arglist)

    def _traverse_object(self, depth, state, token):

        kind, index = self._token2index(JsObject.Token, True)
        self.bc.append(BytecodeInstr('LOAD_' + kind, index, lineno=token.line))

        self._push(depth, ST_COMPILE, token)
        for child in reversed(token.children):
            self._push(depth+1, ST_TRAVERSE|ST_LOAD, child)

    def _traverse_list(self, depth, state, token):

        kind, index = self._token2index(JsArray.Token, True)
        self.bc.append(BytecodeInstr('LOAD_' + kind, index, lineno=token.line))

        self._push(depth, ST_COMPILE, token)
        for child in reversed(token.children):
            self._push(depth+1, ST_TRAVERSE|ST_LOAD, child)

    def _traverse_new(self, depth, state, token):

        kind, index = self._token2index(JsNew.Token, True)
        self.bc.append(BytecodeInstr('LOAD_' + kind, index, lineno=token.line))

        child = token.children[0]
        self._push(depth, ST_COMPILE, token)

        if child.type == Token.T_FUNCTIONCALL:
            for child in reversed(child.children):
                self._push(depth+1, ST_TRAVERSE, child)
        else:
            self._push(depth+1, ST_TRAVERSE, child)

    def _traverse_return(self, depth, state, token):

        self._push(depth, ST_COMPILE, token)
        for child in reversed(token.children):
            self._push(depth+1, ST_TRAVERSE|ST_LOAD, child)

    def _traverse_subscr(self, depth, state, token):

        flg = ST_COMPILE|((ST_LOAD|ST_STORE)&state)
        self._push(depth, flg, token)
        for child in reversed(token.children):
            self._push(depth+1, ST_TRAVERSE|ST_LOAD, child)

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
        elif token.value in binop_store:
            self.bc.append(BytecodeInstr(binop_store[token.value], lineno=token.line))

            # TODO: this has side effects if LHS is complicated
            self._push(depth, ST_COMPILE|ST_STORE, token.children[0])
        else:
            raise InterpreterError(token, "not supported")

    def _compile_text(self, depth, state, token):
        kind, index = self._token2index(token, state&ST_LOAD)

        if state & ST_STORE:
            mode = 'STORE_'
        else:
            mode = 'LOAD_'

        self.bc.append(BytecodeInstr(mode + kind, index, lineno=token.line))

    def _compile_attr(self, depth, state, token):
        _, index = self._token2index_name(token, load=True)

        opcode = "STORE_ATTR" if state&ST_STORE else "LOAD_ATTR"
        self.bc.append(BytecodeInstr(opcode, index, lineno=token.line))

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
        #TODO: pop top if state&ST_LOAD is false
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
        #TODO: pop top if state&ST_LOAD is false
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
        #TODO: pop top if state&ST_LOAD is false
        self.bc.append(BytecodeInstr('CALL_FUNCTION', N))

    def _compile_return(self, depth, state, token):

        self.bc.append(BytecodeInstr('RETURN_VALUE'))

    def _compile_subscr(self, depth, state, token):
        opcode = "BINARY_SUBSCR" if state&ST_LOAD else "STORE_SUBSCR"
        self.bc.append(BytecodeInstr(opcode, lineno=token.line))

    def _compile_keyword(self, depth, state, token):

        if token.value in ['this',]:
            return self._compile_text(depth, state, token)
        else:
            raise InterpreterError(token, "Unsupported keyword")

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
            value = ast.literal_eval(tok.value)
            if tok.value not in self.bc.consts:
                self.bc.consts.append(value)
            index = self.bc.consts.index(value)
            return 'CONST', index

        elif tok.type == Token.T_TEXT or tok.type == Token.T_KEYWORD:

            if not load and (self.flags&Interpreter.CF_REPL or self.flags&Interpreter.CF_MODULE):
                self.module_globals.add(tok.value)

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

        raise InterpreterError(token, "unable to map token")

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

        function Shape() {
            this.width = 5;
            this.height = 5;
            this.area = () => this.width * this.height
            //console.log("init", this)
        }
        shape = new Shape()
        console.log(shape.area())

    """

    tokens = Lexer().lex(text1)
    ast = Parser().parse(tokens)

    print(ast.toString())

    interp = Interpreter(flags=Interpreter.CF_REPL)

    interp.compile(ast)

    interp.dump()

    print(interp.execute())

if __name__ == '__main__':  # pragma: no cover
    main()
