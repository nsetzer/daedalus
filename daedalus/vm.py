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
import operator

from . import vm_opcodes as opcodes

from .builder import findModule
from .formatter import Formatter

from .vm_compiler import VmCompiler
from .vm_primitive import vmGetAst, JsObject, VmFunction, JsUndefined, JsString, JsNumber, JsArray

from .vm_builtin import JsTimerFactory, populate_builtins


# ---

class VmReference(object):
    """ A Reference is used to implement closures
    """

    def __init__(self, name, value):
        super(VmReference, self).__init__()
        self.name = name
        self.value = value

    def __repr__(self):
        return "<Ref(%s, %s)>" % (self.name, self.value)

class VmStackFrame(object):

    def __init__(self, module, fndef, locals, cells):
        super(VmStackFrame, self).__init__()
        # a VmFunctionDef
        self.fndef = fndef
        # a VmModule
        self.module = module
        # a JsObject containing local variables for this frame
        self.locals = locals
        # a JsObject containing cell variables for this frame
        self.cells = cells
        # a JsObject containing global variables for this frame
        self.globals = fndef.globals
        # a table mapping an index to the name of a variable
        # used to implement certain certain opcodes
        self.local_names = fndef.local_names
        # sequence of VmTryBlock
        # used to implement the try/catch logic
        self.blocks = []
        # the stack contains values pushed and popped by opcodes
        self.stack = []
        # the current instruction pointer
        self.sp = 0

class VmTryBlock(object):

    def __init__(self, catch_ip, finally_ip):
        super(VmTryBlock, self).__init__()
        # jump target when an exception is thrown
        self.catch_ip = catch_ip
        # jump target after an exception is handled
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

        self.warn_stack = True
        self.compiler = VmCompiler()

        # the module search path.
        # similar to environment variables PATH or PYTHON_PATH
        self.search_path = []

    def initfn(self, fn, args, kwargs):

        frame = self._new_frame(fn, len(args), args, kwargs)

        self.stack_frames = [frame]

        self._init_builtins()

    def init(self, module, builtins=True):

        cells =JsObject()

        locals = JsObject()
        locals.setAttr("this", JsUndefined.instance)

        self.stack_frames = [VmStackFrame(module, module.functions[0], locals, cells)]

        if builtins:
            self._init_builtins()

    def _init_builtins(self):

        if self.builtins is None:
            self.builtins = {}

            populate_builtins(self, self.builtins)
        # these must be unqiue to the runtime
        self.timer = JsTimerFactory(self)
        self.builtins['setTimeout'] = self.timer._setTimeout
        self.builtins['setInterval'] = self.timer._setInterval
        self.builtins['clearTimeout'] = self.timer._clearTimeout
        self.builtins['wait'] = self.timer._wait

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
        """ get stack frames """
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
        posargs = kwargs

        arguments = JsArray(args)
        for name, value in kwargs._data.items():
            arguments.push(value)

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
                del posargs._data[arglabel]

        # TODO: maybe remove the ref creation from the cellvar.LOAD instr
        for name in func.fndef.cell_names:
            if not func.cells._hasAttr(name):
                ref = VmReference(name, JsUndefined.instance)
                func.cells.setAttr(name, ref)

        # TODO: don't add arguments to lambdas,
        # TODO: don't override function kwargs with the same name
        posargs.setAttr("arguments", arguments)
        new_frame = VmStackFrame(func.module, func.fndef, posargs, func.cells)
        return new_frame

    def _run(self):

        frame = self.stack_frames[-1]
        instrs = frame.fndef.instrs
        return_value = None

        # cache of module names and absolute paths
        self._imports = []
        self._modules = {}

        history = []
        self.steps = 0
        while frame.sp < len(instrs):
            self.steps += 1

            tstack = self.timer.check()
            if tstack is not None:
                history.append((self.stack_frames, frame, instrs, return_value))
                self.stack_frames = tstack
                frame = tstack[-1]
                instrs = frame.fndef.instrs
                return_value = None

            instr = instrs[frame.sp]

            #if frame.stack and isinstance(frame.stack[-1], str):
            #    print("str", repr(frame.stack[-1]), instr.line, instr.opcode)
            #    raise VmRuntimeException(self._get_trace(), "found str on stack")

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

                if isinstance(func, VmFunction):

                    new_frame = self._new_frame(func, argc, args, kwargs)

                    self.stack_frames.append(new_frame)
                    frame.sp += 1
                    frame = self.stack_frames[-1]
                    instrs = frame.fndef.instrs
                    continue
                elif callable(func):
                    try:
                        _rv = func(*args, **kwargs._data)
                    except Exception as e:
                        print(func)
                        print("TODO: caught python exception", e)
                        _rv = e
                    frame.stack.append(_rv)
                else:
                    print("Error at line %d column %d (%s)" % (instr.line, instr.index, type(func)))
                    raise Exception("not callable")

            elif instr.opcode == opcodes.ctrl.CALL_KW:

                kwargs = frame.stack.pop()

                argc = instr.args[0]
                args = []
                for i in range(argc):
                    args.insert(0, frame.stack.pop())
                func = frame.stack.pop()

                if isinstance(func, VmFunction):

                    new_frame = self._new_frame(func, argc, args, kwargs)

                    self.stack_frames.append(new_frame)
                    frame.sp += 1
                    frame = self.stack_frames[-1]
                    instrs = frame.fndef.instrs
                    continue
                elif callable(func):
                    try:
                        _rv = func(*args, **kwargs.data)
                    except Exception as e:
                        print("TODO: caught python exception", e)
                    frame.stack.append(_rv)
                else:
                    print("Error at line %d column %d (%s)" % (instr.line, instr.index, type(func)))
                    raise Exception("not callable")

            elif instr.opcode == opcodes.ctrl.CALL_EX:
                kwargs = frame.stack.pop()
                posargs = frame.stack.pop()
                func = frame.stack.pop()

                if isinstance(func, VmFunction):

                    new_frame = self._new_frame(func, len(posargs.array), posargs.array, kwargs)

                    self.stack_frames.append(new_frame)
                    frame.sp += 1
                    frame = self.stack_frames[-1]
                    instrs = frame.fndef.instrs
                    continue
                elif callable(func):
                    try:
                        _rv = func(*posargs.array, **kwargs.data)
                    except Exception as e:
                        print("TODO: caught python exception", e)
                    frame.stack.append(_rv)
                else:
                    print("Error at line %d column %d" % (instr.line, instr.index))
                    raise Exception("not callable")

            elif instr.opcode == opcodes.ctrl.RETURN:
                rv = frame.stack.pop()
                if frame.stack and self.warn_stack:
                    print("warning: stack not empty", frame.stack)
                    #self._print_trace()
                    #traceback.print_stack()
                frame = self.stack_frames.pop()

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
                    raise RuntimeError("no exception")

                frame.stack.append(self.exception.value)
                self.exception.handled = True
                frame.blocks[-1].flag_catch = True
            elif instr.opcode == opcodes.ctrl.FINALLY:

                frame.blocks[-1].flag_finally = True
            elif instr.opcode == opcodes.ctrl.THROW:

                # TODO: if throw is in side of a catch block... jump to finally instead
                tos = frame.stack.pop()
                self.exception = VmExceptionContext(frame.sp, frame.fndef, tos, self.exception)

                trace = self._get_trace()
                frame_, block = self._unwind()
                if frame_ is None:
                    # TODO: when in a promise, this is ok
                    # no mechanism to detect that yet
                    print("unhandled exception", tos)
                    #raise VmRuntimeException(trace, "unhandled exception")
                else:
                    frame = frame_
                    instrs = frame.fndef.instrs
                    frame.sp = block.target()
                    continue
            elif instr.opcode == opcodes.ctrl.IMPORT:
                module_name = str(frame.stack.pop())
                if module_name.lower().endswith(".js"):
                    if not frame.module.path:
                        raise RuntimeError("relative import from module without a path")
                    dirpath, _ = os.path.split(frame.module.path)
                    path = os.path.normpath(os.path.join(dirpath, module_name))
                else:
                    path = findModule(str(module_name), self.search_path)

                #root = os.path.split(os.path.abspath(mod.path))[0]
                #os.path.normpath(os.path.join(root, mod.includes[i]))

                # TODO: findModule should be part of the loader
                #  + initialize with a search path
                #  + expand relative paths relative to the current module path
                # TODO: cache the execution result for the module
                #  + save time on multiple imports of the same file

                self._imports.append((str(module_name), path))
                #print("import", module_name, path)
                if path in self._modules:
                    frame.stack.append(self._modules[path])
                else:
                    text = open(path).read()
                    ast = vmGetAst(text)
                    module = self.compiler.compile(ast)
                    module.path = path
                    # execute the module as a function call with no arguments
                    prototype = JsObject()
                    fn = VmFunction(module, module.functions[0], None, None, None, None, prototype)
                    new_frame = self._new_frame(fn, 0, [], JsObject())
                    self.stack_frames.append(new_frame)
                    frame.sp += 1
                    frame = self.stack_frames[-1]
                    instrs = frame.fndef.instrs
                    continue
            elif instr.opcode == opcodes.ctrl.IMPORT2:
                module_name, module_path = self._imports.pop()
                module_namespace = frame.stack[-1] # peek
                self._modules[module_path] = module_namespace
                print(module_namespace)
            elif instr.opcode == opcodes.ctrl.IMPORTPY:
                module_name = frame.stack.pop()
                frame.stack.append(__import__(str(module_name)))

            elif instr.opcode == opcodes.ctrl.EXPORT:
                # this is a modified return where the return value
                # is all global values in the current frame
                if frame.stack and self.warn_stack:
                    print("warning: stack not empty", frame.stack)
                frame = self.stack_frames.pop()
                namespace = JsObject(frame.globals.values)

                if len(self.stack_frames) == 0:
                    return_value = namespace
                    break
                else:
                    frame = self.stack_frames[-1]
                    instrs = frame.fndef.instrs
                    frame.stack.append(namespace)
                    continue
            elif instr.opcode == opcodes.ctrl.INCLUDE:
                obj = frame.stack.pop()
                frame.globals.values.update(obj._data)
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
                elif isinstance(obj, VmFunction):
                    val = JsString("function")
                elif isinstance(obj, (JsNumber, int, float)):
                    val = JsString("number")
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

                # stack may contain a Tuple/Array of values for the closure
                # stack will always contain a Bool indicating autobind
                tos = frame.stack.pop()
                if isinstance(tos, JsArray):
                    cellvars = tos
                    autobind = frame.stack.pop()
                else: # else tos is the autobind bool value
                    cellvars = JsArray()
                    autobind = tos

                # stack contains a dictionary of kwargs and the
                # count of positional args
                kwargs = frame.stack.pop()
                argc = frame.stack.pop()

                if autobind:
                    bind_target = frame.locals
                else:
                    bind_target = None
                # print("Create function (this)", frame.locals)

                # pop all positional args off the stack
                args = []
                for i in range(argc):
                    args.insert(0, frame.stack.pop())

                fndef = frame.module.functions[fnidx]
                prototype = JsObject()

                cells = []
                for ref in cellvars.array:
                    cells.append((ref.name, ref))

                fn = VmFunction(frame.module, fndef, args, kwargs, bind_target, JsObject(cells), prototype)
                frame.stack.append(fn)

            elif instr.opcode == opcodes.obj.UPDATE_ARRAY:
                tos1 = frame.stack.pop()
                tos2 = frame.stack.pop()
                tos2.array.extend(tos1.array)
                frame.stack.append(tos2)
            elif instr.opcode == opcodes.obj.UPDATE_OBJECT:
                tos1 = frame.stack.pop()
                tos2 = frame.stack.pop()
                tos2._data.update(tos1._data)
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

                if self.stack_frames:
                    self.stack_frames.pop()
                else:
                    # TODO: when in a primise this is ok
                    # but im not sure why this is reached
                    # it is reached when the promise throws an exception
                    # but it should not be running additional instructions.
                    print("warning: no stack frame")

                if history:
                    self.stack_frames, frame, instrs, return_value = history.pop()
                else:

                    if self.timer._wait_zero():

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

    def run_text(self, text):

        ast = vmGetAst(text)
        module = self.compiler.compile(ast)
        module.path = "__main__"
        self.init(module)
        return self.run()

    def run_script(self, path):

        path = os.path.abspath(path)
        text = open(path).read()
        ast = vmGetAst(text)
        module = self.compiler.compile(ast)
        module.path = path
        self.init(module)
        return self.run()

def main():  # pragma: no cover


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

    # compiler trasforms class into the above example









    # ----------
    # add these as  tests

    text1 = """

        //console.log(typeof({})==='object')

        class A { constructor() {} }
        let a = new A()
        let b = typeof(a)
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


    text1 = """
        sum(...a)
    """

    text1 = """
        zz ??= 4 // 4
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




    text1 = """

        class A{
            constructor(x,y){ this.x=x; this.y=y}
            area() { return this.x * this.y }
        }

        class B extends A {
            constructor(){super(6,7)}
        }

        let b = B()
        console.log(b.area)
        let r = b.area()
    """

    text1 = """

        class A { constructor() {this.x=4}}
        A.prototype.y = 8
        A.prototype.f = function(){return this.x} // returned 4
        A.prototype.g = ()=>{return this.x} // returns undefined
        a = new A()

        result1 = a.x
        result2 = a.y
        result3 = a.f()
        result4 = a.g() // doesnt work yet (can't differentiate lambda / function)
    """

    text1 = """
        // this should not trigger save/restore
        seq = [1,2,3]
        function f(arg) {
            if (arg) {
                while (seq.length>0) {
                    let unit = seq.pop()
                }
            } else {
                while (seq.length>0) {
                    let unit = seq.pop()
                }
            }
        }
        result0 = f(0)
        console.log(seq)
    """






    text1 = """
        class A {
            constructor(v) {
                this.a = v
            }
        }
        class B extends A {
            constructor() {
                super(2)
            }
        }
        let b = B().a

    """
    # current bugs:
    #   - do not bind of already bound functions om the prototype
    #   - popping a block scope must delete vars not saved/restored
    #   -

    if True:
        ast = vmGetAst(text1)
        print(ast.toString(3))
        print(Formatter({"minify": False}).format(ast))

        compiler = VmCompiler()
        mod = compiler.compile(ast)
        mod.dump()
        #return

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
    runtime = VmRuntime()
    runtime.enable_diag=True
    #loader.load("./res/daedalus/daedalus.js")
    rv, globals_ = runtime.run_text(text1)

    return

def main2(): # pragma: no cover
    # test for cli

    #ast = vmGetAst("x = x + 1 function f() { return 0 } ")
    ast = vmGetAst("console.log(123)")
    print(ast.toString(1))
    compiler = VmCompiler()
    mod = compiler.compile(ast)
    mod.dump()
    runtime = VmRuntime()
    runtime.init(mod)
    rv, _ = runtime.run()
    print(rv)

    # repl test

if __name__ == '__main__': # pragma: no cover
    main()