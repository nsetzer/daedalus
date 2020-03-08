
import dis
import types
from bytecode import ConcreteInstr, ConcreteBytecode
import opcode as _opcode

class ConcreteBytecode2(ConcreteBytecode):

    def append(self, arg):

        if not isinstance(arg, BytecodeInstr):
            raise ValueError(arg)

        super().append(arg)

    def extend(self, seq):

        for arg in seq:
            if not isinstance(arg, BytecodeInstr):
                raise ValueError(arg)

            super().append(arg)

class BytecodeInstr(ConcreteInstr):
    def __init__(self, *args, **kwargs):
        super(BytecodeInstr, self).__init__(*args, **kwargs)
        self._es_labels = []
        self._es_target = None

    def add_label(self, label):
        self._es_labels.append(label)

    def labels(self):
        return self._es_labels

class BytecodeJumpInstr(BytecodeInstr):
    def __init__(self, name, target=None, **kwargs):
        super(BytecodeJumpInstr, self).__init__(name, 0, **kwargs)
        self._es_target = target

    def add_label(self, label):
        self._es_labels.append(label)

    def labels(self):
        return self._es_labels

    def finalize(self, pos, arg):
        self.arg = arg

class BytecodeRelJumpInstr(BytecodeInstr):
    def __init__(self, name, target=None, **kwargs):
        super(BytecodeRelJumpInstr, self).__init__(name, 0, **kwargs)
        self._es_target = target

    def add_label(self, label):
        self._es_labels.append(label)

    def labels(self):
        return self._es_labels

    def finalize(self, pos, arg):
        if arg < pos:
            raise NotImplementedError("unsure if algorithm is correct")
        self.arg = arg - (pos + self.size)

class BytecodeContinueInstr(BytecodeJumpInstr):
    def __init__(self, token, counter, **kwargs):
        super(BytecodeContinueInstr, self).__init__('JUMP_ABSOLUTE', **kwargs)
        self.counter = counter
        self.token = token

    def update(self, c_label, b_label):
        self.counter = 0
        self._es_target = c_label

    def finalize(self, pos, arg):
        if self.counter != 0:
            raise CompilerError(self.token, "invalid numerical value")
        self.arg = arg

class BytecodeBreakInstr(BytecodeJumpInstr):
    def __init__(self, token, counter, **kwargs):
        super(BytecodeBreakInstr, self).__init__('JUMP_ABSOLUTE', **kwargs)
        self.counter = counter
        self.token = token

    def update(self, c_label, b_label):
        self.counter = 0
        self._es_target = b_label

    def finalize(self, pos, arg):
        if self.counter != 0:
            raise CompilerError(self.token, "invalid numerical value")
        self.arg = arg

def CellType(value):
    # python versions before 3.8 do not define a types.CellType
    # instead create a closure of a value and return the cell
    fn = (lambda x: lambda: x)(value)
    return fn.__closure__[0]

def _dump_bytecode(bc):

    pos = 0
    for instr in bc:

        tag = ''
        target = ""
        if instr.name == "IMPORT_NAME" or instr.name == "IMPORT_FROM":
            tag = " import: "
            target = repr(bc.names[instr.arg])
        elif instr.name == 'LOAD_BUILD_CLASS':
            target = ""
        elif instr.name.startswith("LOAD_") or instr.name.startswith("STORE_") or instr.name.startswith("DELETE_"):
            try:
                kind = instr.name.split("_")[-1]

                if kind == "CONST":
                    tag = "  const: "
                    target = bc.consts[instr.arg]
                elif kind == "DEREF" or kind == 'CLOSURE':
                    if instr.arg >= len(bc.cellvars):
                        tag = 'freevar: '
                        target = bc.freevars[instr.arg - len(bc.cellvars)]
                    else:
                        tag = 'cellvar: '
                        target = bc.cellvars[instr.arg]
                elif kind == "FAST":
                    tag = "varname: "
                    target = bc.varnames[instr.arg]
                elif kind == "NAME":
                    tag = "   name: "
                    target = bc.names[instr.arg]
                elif kind == "GLOBAL":
                    tag = " global: "
                    target = bc.names[instr.arg]
                elif kind == "ATTR":
                    tag = "   attr: "
                    target = bc.names[instr.arg]
            except IndexError:
                target = ""

            if isinstance(target, types.CodeType):
                target = "<%s:%s>" % (target.co_name, target.co_filename)
            else:
                target = repr(target)

        elif instr.has_jump():
            if instr.opcode in _opcode.hasjrel:
                target = "goto %d" % (pos + instr.size + instr.arg)
            elif instr.opcode in _opcode.hasjabs:
                target = "goto %d" % (instr.arg)

        if instr.require_arg():
            arg = instr.arg
        else:
            arg = ""

        name = instr.name
        if len(name) > 17:
            name = name[:17] + '...'
        print(" %5s %-20s %4s | %s%s" % (pos, name, arg, tag, target))
        pos += instr.size

def dump(bc):

    for const in bc.consts:
        if isinstance(const, types.CodeType):
            child = ConcreteBytecode.from_code(const)
            dump(child)

    print("")
    for name in dir(bc):
        if name.startswith("_"):
            continue
        s = getattr(bc, name)
        if isinstance(s, list):
            s = list(s) # copy to not modify bc
            for index, item in enumerate(s):
                if isinstance(item, types.CodeType):
                    s[index] = "<code:%s>" % item.co_name
                else:
                    s[index] = repr(item)
            s = ", ".join(s)
        else:
            s = str(s)

        if '<function' in s:
            continue
        if '<built-in method' in s:
            continue
        if '<bound method' in s:
            continue

        print("%20s: %s" % (name, s))

    # dump_bytecode(bc)
    _dump_bytecode(bc)

    print("%20s: %s" % ("stacksize", calcsize(bc)))

    # print("stack effect", bc.compute_stacksize(), stacksize)

def calcsize(bc):
    """
    calculate the stack size two ways,
    sometimes bytecode computes a zero size which throws an exception
    """

    stacksize = 0
    for instr in bc:
        arg = instr.arg if instr.require_arg() else None
        if instr.name != "NOP":
            stacksize += dis.stack_effect(instr.opcode, arg)

    try:
        othersize = bc.compute_stacksize()
    except RuntimeError as e:
        if hasattr(e, 'stacksize'):
            othersize = e.stacksize
        else:
            othersize = 0

    return max(stacksize, othersize)
