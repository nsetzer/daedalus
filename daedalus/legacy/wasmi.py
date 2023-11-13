#! cd .. && python -m daedalus.wasmi
# https://pengowray.github.io/wasm-ops/
# https://github.com/shmishtopher/wasm-opcodes
# https://www.w3.org/TR/wasm-core-1/#numeric-instructions%E2%91%A0
# https://www.w3.org/TR/wasm-core-1/#stack%E2%91%A0

# https://github.com/mdn/webassembly-examples/tree/master/understanding-text-format

# https://richardanaya.medium.com/lets-write-a-web-assembly-interpreter-part-1-287298201d75
# https://richardanaya.medium.com/lets-write-a-web-assembly-interpreter-part-2-6c430f3f4bfd
# https://blog.scottlogic.com/2019/05/17/webassembly-compiler.html


# git clone --recursive https://github.com/WebAssembly/wabt
# cd wabt
# mkdir build
# cd build
# cmake ..
# cmake --build .

# WAT samples
# https://webassembly.github.io/wabt/demo/wat2wasm/
# https://wasdk.github.io/WasmFiddle/

# Test cases
# WAST format test cases
# https://github.com/WebAssembly/spec/tree/master/test/core
#

# sudo apt-get install emscripten
# cd emsdk
# source venv/bin/activate
# source ./emsdk_env.sh
# emcc ../simple.c -s WASM=1 -o ../simple.html

# load const 32bit number:
# 41 ef fd b6 f5

# classes:
#   WastParser
#       - wast to WasmSource
#   WasmInterpretter
#       - wasm to WasmSource
#   WasmEmitter
#       - js ast to WasmSource
#   WasmSource
#       - in memory bytecode representation of a wasm file
#       - serialize to wasm
#       - environment should support appending new structures and
#         executing only the new unit. e.g. compile and run one line of js at a time
#   WasmRuntime
#       - run a WasmSource class by excuting the default export
#         - e.g. main
#

import io
import struct
import ctypes
import binascii


from . import wasm_opcodes as opcodes

WASM_HEADER = b"\x00\x61\x73\x6d"
WASM_VERSION = b"\x01\x00\x00\x00"

def UINT2LEB128(value):
    out = value & 0b0111_1111
    value >>= 7
    n = 1
    while value:
        out |= 0b1000_0000
        out <<= 8
        lsb = (value & 0b0111_1111)
        value >>= 7
        out |= lsb
        n += 1
    return out.to_bytes(n, 'big')

def LEB1282UINT(b):
    out = 0
    for idx, val in enumerate(b):
        out |= ((val & 0x7f) << (idx * 7))
    return out

def read_LEB128u(stream):
    out = 0
    idx = 0
    val = ord(stream.read(1))
    while val&0x80:
        out |= ((val & 0x7f) << (idx * 7))
        idx += 1
        val = ord(stream.read(1))
    out |= ((val & 0x7f) << (idx * 7))
    return out

def SINT2LEB128(val):
    out = []
    idx = 0
    while True:
        byte = val & 0x7f
        idx = idx >> 7
        if (idx == 0 and byte & 0x40 == 0) or (idx == -1 and byte & 0x40 != 0):
            out.append(byte)
            break
        out.append(0x80 | byte)
    return bytearray(out)

def LEB1282SINT(bytes):
    out = 0
    for idx, val in enumerate(bytes):
        out = out + ((val & 0x7f) << (idx * 7))
    if val & 0x40 != 0:
        out |= - (1 << (idx * 7) + 7)
    return out

def read_LEB128s(stream):
    out = 0
    idx = 0
    val = ord(stream.read(1))
    while val&0x80:
        out = out + ((val & 0x7f) << (idx * 7))
        idx += 1
        val = ord(stream.read(1))
    out = out + ((val & 0x7f) << (idx * 7))
    if val & 0x40 != 0:
        out |= - (1 << (idx * 7) + 7)
    return out

# TODO: decoder for signed and unsigned LEB128
# return value and count of bytes read

class SectionType(opcodes.Enum):
    CUSTOM    = 0
    TYPE      = 1
    IMPORT    = 2
    FUNCTION  = 3
    TABLE     = 4
    MEMORY    = 5
    GLOBAL    = 6
    EXPORT    = 7
    START     = 8
    ELEMENT   = 9
    CODE      = 10
    DATA      = 11

class WasmInstruction(object):
    __slots__ = ['opcode', 'args', 'tgt']

    def __init__(self, opcode, *args):
        super(WasmInstruction, self).__init__()
        self.opcode = opcode
        self.args = args

    def __repr__(self):
        if self.args:
            s = " " + " ".join([str(arg) for arg in self.args])
        else:
            s = ""
        return "(%s%s)" % (self.opcode, s)

class WasmMemory(object):
    """
        random access memory for wasm

        block_size: size of bytearrays to construct
        mem: start_address -> block
    """
    def __init__(self, mode=0):
        super(WasmMemory, self).__init__()

        # 8 byte block size
        if mode == 2:
            self.block_size        = 0x0000_0008
            self.block_addr_mask   = 0xFFFF_FFF8
            self.block_offset_mask = 0x0000_0007
            self.memory_max        = 0xFFFF_FFFF

        # 4k byte block size
        if mode == 1:
            self.block_size        = 0x0000_1000
            self.block_addr_mask   = 0xFFFF_F000
            self.block_offset_mask = 0x0000_1FFF
            self.memory_max        = 0xFFFF_FFFF

        # 64k byte block size
        if mode == 0:
            self.block_size        = 0x0001_0000
            self.block_addr_mask   = 0xFFFF_0000
            self.block_offset_mask = 0x0000_FFFF
            self.memory_max        = 0xFFFF_FFFF

        self.mem = {}

    def _load(self, addr, length):

        s = addr & self.block_addr_mask
        e = (addr + length) & self.block_addr_mask
        o = addr & self.block_offset_mask
        if s == e:
            if s not in self.mem:
                self.mem[s] = bytearray(self.block_size)
            return self.mem[s][o:o+length]
        else:
            parts = []

            for i in range(s, e+1, self.block_size):
                if i not in self.mem:
                    self.mem[i] = bytearray(self.block_size)
                _len = min(self.block_size, o + length)
                parts.append(self.mem[i][o:_len])
                o = 0
                length -= _len
            return bytearray().join(parts)

    def _store(self, addr, data, length):

        s = addr & self.block_addr_mask
        e = (addr + length) & self.block_addr_mask
        o = addr & self.block_offset_mask
        p=0
        if s == e:
            if s not in self.mem:
                self.mem[s] = bytearray(self.block_size)

            self.mem[s][o:o+length] = data[p:p+length]
        else:

            for i in range(s, e+1, self.block_size):
                if i not in self.mem:
                    self.mem[i] = bytearray(self.block_size)
                _len = min(self.block_size, o + length)
                self.mem[i][o:_len] = data[p:p+_len-o]
                o = 0
                p += _len
                length -= _len

    def store_i8(self, addr, value):
        encoded = (value&0xFF).to_bytes(1, 'little')
        self._store(addr, encoded, 1)

    def store_i16(self, addr, value):
        encoded = (value&0xFFFF).to_bytes(2, 'little')
        self._store(addr, encoded, 2)

    def store_i32(self, addr, value):
        encoded = (value&0xFFFF_FFFF).to_bytes(4, 'little')
        self._store(addr, encoded, 4)

    def store_i64(self, addr, value):
        encoded = (value&0xFFFF_FFFF_FFFF_FFFF).to_bytes(8, 'little')
        self._store(addr, encoded, 8)

    def store_f32(self, addr, value):
        self._store(addr, struct.pack("<f", value), 4)

    def store_f64(self, addr, value):
        self._store(addr, struct.pack("<d", value), 8)

    def load_i8s(self, addr):
        encoded = self._load(addr, 1)
        int.from_bytes(encoded, "little", signed=1)

    def load_i16s(self, addr):
        encoded = self._load(addr, 2)
        int.from_bytes(encoded, "little", signed=1)

    def load_i32s(self, addr):
        encoded = self._load(addr, 4)
        int.from_bytes(encoded, "little", signed=1)

    def load_i64s(self, addr):
        encoded = self._load(addr, 8)
        int.from_bytes(encoded, "little", signed=1)

    def load_i8u(self, addr):
        encoded = self._load(addr, 1)
        int.from_bytes(encoded, "little", signed=0)

    def load_i16u(self, addr):
        encoded = self._load(addr, 2)
        int.from_bytes(encoded, "little", signed=0)

    def load_i32u(self, addr):
        encoded = self._load(addr, 4)
        int.from_bytes(encoded, "little", signed=0)

    def load_i64u(self, addr):
        encoded = self._load(addr, 8)
        int.from_bytes(encoded, "little", signed=0)

    def load_f32(self, addr):
        return struct.unpack("<f", self._load(addr, 4))[0]

    def load_f64(self, addr):
        return struct.unpack("<d", self._load(addr, 8))[0]

    def load(self, addr, length):
        return self._load(addr, length)

    def store(self, addr, data):
        return self._store(addr, data, len(data))

    def size(self):
        # todo: return number of contiguous segments
        # empty segments may not exist in mem but should still
        # be counted. starting at index zero
        if self.block_size == 0x0001_0000:
            return len(self.mem)

class int32(ctypes.c_int32):

    def __add__(self, other):
        return int32(self.value + other.value)

    def __sub__(self, other):
        return int32(self.value - other.value)

    def __mul__(self, other):
        return int32(self.value * other.value)

    def __truediv__(self, other):
        return int32(self.value / other.value)

    def __floordiv__(self, other):
        return int32(self.value // other.value)

    def __lshift__(self, other):
        return int32(self.value << other.value)

    def __rshift__(self, other):
        return int32(self.value >> other.value)

    def __and__(self, other):
        return int32(self.value & other.value)

    def __xor__(self, other):
        return int32(self.value ^ other.value)

    def __or__(self, other):
        return int32(self.value | other.value)

    def __lt__(self, other):
        return int32(self.value < other.value)

    def __le__(self, other):
        return int32(self.value <= other.value)

    def __eq__(self, other):
        return int32(self.value == other.value)

    def __ge__(self, other):
        return int32(self.value >= other.value)

    def __gt__(self, other):
        return int32(self.value > other.value)

    def __repr__(self):
        return "i32(%d)" % self.value

class int64(ctypes.c_int64):

    def __add__(self, other):
        print(self, other)
        return int64(self.value + other.value)

    def __sub__(self, other):
        return int64(self.value - other.value)

    def __mul__(self, other):
        return int64(self.value * other.value)

    def __truediv__(self, other):
        return int64(self.value / other.value)

    def __floordiv__(self, other):
        return int64(self.value // other.value)

    def __lshift__(self, other):
        return int64(self.value << other.value)

    def __rshift__(self, other):
        return int64(self.value >> other.value)

    def __and__(self, other):
        return int64(self.value & other.value)

    def __xor__(self, other):
        return int64(self.value ^ other.value)

    def __or__(self, other):
        return int64(self.value | other.value)

    def __lt__(self, other):
        return int64(self.value < other.value)

    def __le__(self, other):
        return int64(self.value <= other.value)

    def __eq__(self, other):
        return int64(self.value == other.value)

    def __ge__(self, other):
        return int64(self.value >= other.value)

    def __gt__(self, other):
        return int64(self.value > other.value)

    def __repr__(self):
        return "i64(%d)" % self.value

class uint32(ctypes.c_uint32):

    def __add__(self, other):
        return uint32(self.value + other.value)

    def __sub__(self, other):
        return uint32(self.value - other.value)

    def __mul__(self, other):
        return uint32(self.value * other.value)

    def __truediv__(self, other):
        return uint32(self.value / other.value)

    def __floordiv__(self, other):
        return uint32(self.value // other.value)

    def __lshift__(self, other):
        return uint32(self.value << other.value)

    def __rshift__(self, other):
        return uint32(self.value >> other.value)

    def __and__(self, other):
        return uint32(self.value & other.value)

    def __xor__(self, other):
        return uint32(self.value ^ other.value)

    def __or__(self, other):
        return uint32(self.value | other.value)

    def __lt__(self, other):
        return uint32(self.value < other.value)

    def __le__(self, other):
        return uint32(self.value <= other.value)

    def __eq__(self, other):
        return uint32(self.value == other.value)

    def __ge__(self, other):
        return uint32(self.value >= other.value)

    def __gt__(self, other):
        return uint32(self.value > other.value)

    def __repr__(self):
        return "u32(%d)" % (self.value&0xFFFF_FFFF)

class uint64(ctypes.c_uint64):

    def __add__(self, other):
        return uint64(self.value + other.value)

    def __sub__(self, other):
        return uint64(self.value - other.value)

    def __mul__(self, other):
        return uint64(self.value * other.value)

    def __truediv__(self, other):
        return uint64(self.value / other.value)

    def __floordiv__(self, other):
        return uint64(self.value // other.value)

    def __lshift__(self, other):
        return uint64(self.value << other.value)

    def __rshift__(self, other):
        return uint64(self.value >> other.value)

    def __and__(self, other):
        return uint64(self.value & other.value)

    def __xor__(self, other):
        return uint64(self.value ^ other.value)

    def __or__(self, other):
        return uint64(self.value | other.value)

    def __lt__(self, other):
        return uint64(self.value < other.value)

    def __le__(self, other):
        return uint64(self.value <= other.value)

    def __eq__(self, other):
        return uint64(self.value == other.value)

    def __ge__(self, other):
        return uint64(self.value >= other.value)

    def __gt__(self, other):
        return uint64(self.value > other.value)

    def __repr__(self):
        return "u64(%d)" % (self.value&0xFFFF_FFFF_FFFF_FFFF)

class float32(ctypes.c_float):

    def __add__(self, other):
        return float32(self.value + other.value)

    def __sub__(self, other):
        return float32(self.value - other.value)

    def __mul__(self, other):
        return float32(self.value * other.value)

    def __truediv__(self, other):
        return float32(self.value / other.value)

    def __floordiv__(self, other):
        return float32(self.value // other.value)

    def __lshift__(self, other):
        return float32(self.value << other.value)

    def __rshift__(self, other):
        return float32(self.value >> other.value)

    def __and__(self, other):
        return float32(self.value & other.value)

    def __xor__(self, other):
        return float32(self.value ^ other.value)

    def __or__(self, other):
        return float32(self.value | other.value)

    def __lt__(self, other):
        return float32(self.value < other.value)

    def __le__(self, other):
        return float32(self.value <= other.value)

    def __eq__(self, other):
        return float32(self.value == other.value)

    def __ge__(self, other):
        return float32(self.value >= other.value)

    def __gt__(self, other):
        return float32(self.value > other.value)

    def __repr__(self):
        return "f32(%f)" % self.value

class float64(ctypes.c_double):

    def __add__(self, other):
        return float64(self.value + other.value)

    def __sub__(self, other):
        return float64(self.value - other.value)

    def __mul__(self, other):
        return float64(self.value * other.value)

    def __truediv__(self, other):
        return float64(self.value / other.value)

    def __floordiv__(self, other):
        return float64(self.value // other.value)

    def __lshift__(self, other):
        return float64(self.value << other.value)

    def __rshift__(self, other):
        return float64(self.value >> other.value)

    def __and__(self, other):
        return float64(self.value & other.value)

    def __xor__(self, other):
        return float64(self.value ^ other.value)

    def __or__(self, other):
        return float64(self.value | other.value)

    def __lt__(self, other):
        return float64(self.value < other.value)

    def __le__(self, other):
        return float64(self.value <= other.value)

    def __eq__(self, other):
        return float64(self.value == other.value)

    def __ge__(self, other):
        return float64(self.value >= other.value)

    def __gt__(self, other):
        return float64(self.value > other.value)

    def __repr__(self):
        return "f64(%f)" % self.value

class WasmFunction(object):
    def __init__(self, instrs=None, params=None, results=None, name=None):
        super(WasmFunction, self).__init__()
        self.instrs = [] if instrs is None else instrs
        self.params = [] if params is None else params  # list of opcode.ResultType
        self.results = [] if results is None else results  # list of opcode.ResultType
        self.name = "anonymous" if name is None else name

        self.block_parent = {}
        self.block_end_index = {} # parent index => END index
        self.block_else_index = {} # parent index => END index
        self.analyzed = False

    def analyze(self):

        # TODO: precompute jump targets and store as an argument in the instr

        i = 0
        blocks = []
        self.block_parent = {}
        self.block_end_index = {} # parent index => END index
        self.block_else_index = {} # parent index => END index
        while i < len(self.instrs):
            instr = self.instrs[i]
            if instr.opcode == opcodes.ctrl.BLOCK:
                blocks.append(i)
            elif instr.opcode == opcodes.ctrl.LOOP:
                blocks.append(i)
            elif instr.opcode == opcodes.ctrl.IF:
                blocks.append(i)
            elif instr.opcode == opcodes.ctrl.ELSE:
                self.block_parent[i] = blocks[-1]
                self.block_else_index[blocks[-1]] = i # + 1
            elif instr.opcode == opcodes.ctrl.END:
                if len(blocks) > 0:
                    self.block_end_index[blocks[-1]] = i # + 1
                    blocks.pop()
            elif instr.opcode == opcodes.ctrl.BR:
                self.block_parent[i] = blocks[-1]
            elif instr.opcode == opcodes.ctrl.BR_IF:
                # TODO: is this needed?
                self.block_parent[i] = blocks[-1]
            elif instr.opcode == opcodes.ctrl.BR_TABLE:
                # dynamic jump by reading jump target from a vector
                # labelidx = vec[index]
                # ctxt.sp = ctxt.fn.block_end_index[ctxt.blocks[-labelidx]]
                raise NotImplementedError()
            i+=1

        #for src, tgt in self.block_parent.items():
        #    print(src, self.instrs[src], "=>", tgt, self.instrs[tgt])
        #for src, tgt in self.block_end_index.items():
        #    print(src, self.instrs[src], "->", tgt, self.instrs[tgt])

        self.analyzed = True

class WasmStackContext(object):
    def __init__(self, fn, locals=None):
        super(WasmStackContext, self).__init__()

        if not fn.analyzed:
            fn.analyze()

        self.fn = fn
        self.stack = []
        if locals is None:
            self.locals = [int32(0)] * len(fn.params)
        else:
            self.locals = locals
        self.blocks = []
        self.sp = 0

class WasmExport(object):
    def __init__(self, index, kind, name):
        super(WasmExport, self).__init__()
        self.index = index
        self.kind = kind
        self.name = name

class WasmImport(object):
    def __init__(self, module, field, kind, type, mutable):
        super(WasmImport, self).__init__()
        self.module = module
        self.field = field
        self.kind = kind
        self.type = type
        self.mutable = mutable

class WasmModule(object):
    def __init__(self):
        super(WasmModule, self).__init__()

        self.types = []
        self.fnsig_index = []
        self.fn_code = []
        self.exports = {}
        self.imports = []
        self.functions = []
        self._export_functions = {}
        self.start_fnidx = -1

    def read_function_body(self, stream):
        # read until an unmatched end \x0b is found
        instrs = []

        function_size = read_LEB128u(stream)

        if function_size > 0:
            i = stream.tell()
            print("--", binascii.hexlify(stream.getvalue()[i:i+function_size]))


        offset0 = stream.tell()

        stream.read(1)

        depth = 0
        while True:
            op = ord(stream.read(1))
            op = opcodes.value2enum[op]

            argtypes = opcodes.argtypes.get(op, None)
            if argtypes:
                args = []
                for argtype in argtypes:
                    if argtype == opcodes.ArgType.I8s:
                        args.append(read_LEB128s(stream))
                        #args.append(struct.unpack("<b", stream.read(1))[0])
                    elif argtype == opcodes.ArgType.I8u:
                        args.append(read_LEB128u(stream))
                        #args.append(struct.unpack("<B", stream.read(1))[0])
                    elif argtype == opcodes.ArgType.I32s:
                        args.append(read_LEB128s(stream))
                    elif argtype == opcodes.ArgType.I32u:
                        args.append(read_LEB128u(stream))
                    elif argtype == opcodes.ArgType.I64s:
                        args.append(read_LEB128s(stream))
                    elif argtype == opcodes.ArgType.I64u:
                        args.append(read_LEB128u(stream))
                    elif argtype == opcodes.ArgType.F32:
                        args.append(struct.unpack("<f", stream.read(4))[0])
                    elif argtype == opcodes.ArgType.F64:
                        args.append(struct.unpack("<d", stream.read(8))[0])
                    elif argtype == opcodes.ArgType.MEM:
                        args.append(read_LEB128u(stream))
                        args.append(read_LEB128u(stream))

                instrs.append(WasmInstruction(op, *args))
            else:
                instrs.append(WasmInstruction(op))

            if op == opcodes.ctrl.BLOCK:
                depth += 1
            elif op == opcodes.ctrl.LOOP:
                depth += 1
            elif op == opcodes.ctrl.IF:
                depth += 1
            elif op == opcodes.ctrl.END:
                if depth == 0:
                    break
                else:
                    depth -= 1

            print(depth, instrs[-1])

        #code = stream.read(function_size)

        if function_size == 0:
            function_size = read_LEB128u(stream)

        offset1 = stream.tell()

        if offset1 - offset0 != function_size:
            raise RuntimeError("size %d != %d" % ((offset1 - offset0), function_size))

        return instrs

    def read_section(self, stream):

        #i = stream.tell()
        #print("--", binascii.hexlify(stream.getvalue()[i:i+32]))
        section_type = SectionType(ord(stream.read(1)))
        section_size = ord(stream.read(1))
        print(section_type, section_size)

        offset0 = stream.tell()

        if section_type == SectionType.CUSTOM:
            raise NotImplementedError()
        elif section_type == SectionType.TYPE:

            num_types = read_LEB128u(stream)
            for i in range(num_types):
                function_type = ord(stream.read(1))

                if function_type != 0x60:
                    raise ValueError("unknown function type %X" % function_type)

                num_params = read_LEB128u(stream)
                params = []
                for i in range(num_params):
                    params.append(opcodes.ResultType(ord(stream.read(1))))

                num_results = read_LEB128u(stream)
                results = []
                for i in range(num_results):
                    results.append(opcodes.ResultType(ord(stream.read(1))))

                self.types.append((params, results))

        elif section_type == SectionType.IMPORT:
            num_imports = read_LEB128u(stream)
            for i in range(num_imports):
                strlen1 = read_LEB128u(stream)
                modname = stream.read(strlen1)

                strlen2 = read_LEB128u(stream)
                fieldname = stream.read(strlen2)

                impkind = read_LEB128u(stream)
                if impkind != 3:
                    raise ValueError("unsupported import kind")
                imptype = opcodes.ResultType(ord(stream.read(1)))
                mutable  = read_LEB128u(stream)

                imp = WasmImport(modname, fieldname, impkind, imptype, mutable)
                self.imports.append(imp)

        elif section_type == SectionType.FUNCTION:
            num_functions = read_LEB128u(stream)
            for i in range(num_functions):
                self.fnsig_index.append(read_LEB128u(stream))
        elif section_type == SectionType.TABLE:
            raise NotImplementedError()
        elif section_type == SectionType.MEMORY:
            read_LEB128u(stream)
            raise NotImplementedError()
        elif section_type == SectionType.GLOBAL:
            raise NotImplementedError()
        elif section_type == SectionType.EXPORT:
            num_exports = read_LEB128u(stream)
            for i in range(num_exports):
                str_len = read_LEB128u(stream)
                export_name = stream.read(str_len)
                export_kind = ord(stream.read(1))
                export_index = read_LEB128u(stream)
                export = WasmExport(export_index, export_kind, export_name)
                self.exports[export_index] = export
        elif section_type == SectionType.START:
            self.start_fnidx = read_LEB128u(stream)
        elif section_type == SectionType.ELEMENT:
            raise NotImplementedError()
        elif section_type == SectionType.CODE:
            num_functions = read_LEB128u(stream)
            for i in range(num_functions):
                instrs = self.read_function_body(stream)
                self.fn_code.append(instrs)

        elif section_type == SectionType.DATA:
            raise NotImplementedError()
        else:
            raise Exception("invalid section type %s" % section_type)

        if section_size == 0:
            read_LEB128u(stream)

        offset1 = stream.tell()

        return offset1 - offset0

    def parse(self, path):

        self.types = []
        self.fnsig_index = []
        self.fn_code = []
        self.exports = {}
        self.imports = []
        self.functions = []
        self.export_functions = {}

        with open(path, "rb") as rf:
            stream = io.BytesIO(rf.read())
        stream.seek(0)
        # ------------

        magic = stream.read(4)
        if magic != b'\x00asm':
            raise ValueError(magic)
        version = stream.read(4)
        if version != b'\x01\x00\x00\x00':
            raise ValueError(version)

        bytes_remaining = len(stream.getvalue())

        while (len(stream.getvalue()) - stream.tell()) > 0:
            n = self.read_section(stream)
            bytes_remaining -= n

        for fnidx, (sigidx, instrs) in enumerate(zip(self.fnsig_index, self.fn_code)):
            params, results = self.types[sigidx]

            if fnidx in self.exports:
                export = self.exports[fnidx]
                name = export.name
            else:
                name = "function_%d" % fnidx

            fn = WasmFunction(instrs, params, results, name)

            self.functions.append(fn)

            if fnidx in self.exports:
                self._export_functions[name.decode("utf-8")] = fn

    def getFunctionByName(self, name):
        return self._export_functions[name]

    def getExportNames():
        return list(sorted(self._export_functions.keys()))

class PythonBackend(object):
    def __init__(self):
        super(PythonBackend, self).__init__()

        self.mem = WasmMemory()
        self.labels = {}
        self.globals = [] # index to value
        self.functions = []
        self.tables = []

        self.contexts = []

        self.module = None

    def init(self, module):

        self.functions = module.functions

        self.globals = []
        for imp in module.imports:
            if imp.kind == 3:
                if imp.type == opcodes.ResultType.I32:
                    self.globals.append(int32(0))
                elif imp.type == opcodes.ResultType.I64:
                    self.globals.append(int64(0))
                elif imp.type == opcodes.ResultType.F32:
                    self.globals.append(float32(0))
                elif imp.type == opcodes.ResultType.F64:
                    self.globals.append(float64(0))
                else:
                    raise ValueError("unsupported import type")

        self.module = module

    def call(self, name, locals=None):

        fn = self.module.getFunctionByName(name)
        self.contexts = [WasmStackContext(fn, locals)]

        return self.run()

    def run(self):

        ctxt = self.contexts[-1]
        return_value = None
        nresults = len(ctxt.fn.results)

        while ctxt.sp < len(ctxt.fn.instrs):

            instr = ctxt.fn.instrs[ctxt.sp]

            print(len(self.contexts), ctxt.sp, instr)

            if instr.opcode == opcodes.ctrl.UNREACHABLE:
                raise RuntimeError("unreachable code reached")
            elif instr.opcode == opcodes.ctrl.NOP:
                pass
            elif instr.opcode == opcodes.ctrl.BLOCK:
                ctxt.blocks.append(ctxt.sp)
            elif instr.opcode == opcodes.ctrl.LOOP:
                ctxt.blocks.append(ctxt.sp)
            elif instr.opcode == opcodes.ctrl.IF:
                # pop from stack
                # if one continue until else is found then skip until end
                # if zero go to else
                ctxt.blocks.append(ctxt.sp)
                val = ctxt.stack.pop()
                if val.value == 0:
                    ctxt.sp = ctxt.fn.block_else_index[ctxt.sp] + 1
                    continue
            elif instr.opcode == opcodes.ctrl.ELSE:
                # the true branch of an if statement has completed
                # skip to the end of the if block
                ctxt.sp = ctxt.fn.block_end_index[ctxt.fn.block_parent[ctxt.sp]]
                continue
            elif instr.opcode == opcodes.ctrl.END:
                # pop the current block
                if len(ctxt.blocks) > 0:
                    ctxt.blocks.pop()
            elif instr.opcode == opcodes.ctrl.BR:
                # a continue if block_indexes[-1] is a loop instruction
                # a break if block_indexes[-1] is a block or if

                parent = ctxt.fn.instrs[ctxt.fn.block_parent[ctxt.sp]]
                if parent.opcode == opcodes.ctrl.BLOCK:
                    ctxt.sp = ctxt.fn.block_end_index[ctxt.fn.block_parent[ctxt.sp]]
                    continue
                elif parent.opcode == opcodes.ctrl.LOOP:
                    ctxt.sp= ctxt.fn.block_parent[ctxt.sp]
                    continue
                elif parent.opcode == opcodes.ctrl.IF:
                    ctxt.sp = ctxt.fn.block_end_index[ctxt.fn.block_parent[ctxt.sp]]
                    continue
                else:
                    raise RuntimeError("invalid loop parent: %s" % parent)

                raise NotImplementedError()
            elif instr.opcode == opcodes.ctrl.BR_IF:
                labelidx = instr.args[0]
                ctxt.sp = ctxt.fn.block_end_index[ctxt.blocks[-labelidx]]
                continue
            elif instr.opcode == opcodes.ctrl.BR_TABLE:
                raise NotImplementedError()
            elif instr.opcode == opcodes.ctrl.RETURN:
                argcount = ctxt.stack.pop()
                args = []
                for i in range(argcount.value):
                    args.insert(0, ctxt.stack.pop())
                self.contexts.pop()
                if len(self.contexts) == 0:
                    return_value = args
                    break
                else:
                    ctxt = self.contexts[-1]
                    for arg in args:
                        ctxt.stack.append(arg)
                    continue

            elif instr.opcode == opcodes.ctrl.CALL:
                fnidx = instr.args[0]
                fn = self.functions[fnidx]
                # TODO: order?
                locals = []
                for i in range(len(fn.params)):
                    locals.insert(0, ctxt.stack.pop())
                ctxt.sp += 1
                tmp = WasmStackContext(self.functions[fnidx], locals)
                self.contexts.append(tmp)
                ctxt = tmp
                continue

            elif instr.opcode == opcodes.ctrl.CALL_INDIRECT:
                raise NotImplementedError()
            elif instr.opcode == opcodes.localvar.GET:
                index = instr.args[0]
                if index >= len(ctxt.locals):
                    raise RuntimeError("local index out of range")
                ctxt.stack.append(ctxt.locals[index])
            elif instr.opcode == opcodes.localvar.SET:
                index = instr.args[0]
                if index >= len(ctxt.locals):
                    raise RuntimeError("local index out of range")
                ctxt.locals[index] = ctxt.stack.pop()
            elif instr.opcode == opcodes.localvar.TEE:
                # like set, but does not consume the top of stack
                index = instr.args[0]
                if index >= len(ctxt.locals[-1]):
                    raise RuntimeError("local index out of range")
                ctxt.locals[index] = ctxt.stack
            elif instr.opcode == opcodes.globalvar.GET:
                ctxt.stack.append(self.globals[instr.args[0]])
            elif instr.opcode == opcodes.globalvar.SET:
                self.globals[instr.args[0]] = ctxt.stack.pop()
            elif instr.opcode == opcodes.parametric.DROP:
                ctxt.stack.pop()
            elif instr.opcode == opcodes.parametric.SELECT:
                raise NotImplementedError()
            elif instr.opcode == opcodes.mem.i32_LOAD:
                raise NotImplementedError()
            elif instr.opcode == opcodes.mem.i64_LOAD:
                raise NotImplementedError()
            elif instr.opcode == opcodes.mem.f32_LOAD:
                raise NotImplementedError()
            elif instr.opcode == opcodes.mem.f64_LOAD:
                raise NotImplementedError()
            elif instr.opcode == opcodes.mem.i32_LOAD8_s:
                offset, align = instr.args
                address = offset + ctxt.stack.pop()
                ctxt.stack.append(self.mem.load_i8s(address))
            elif instr.opcode == opcodes.mem.i32_LOAD8_u:
                offset, align = instr.args
                address = offset + ctxt.stack.pop()
                ctxt.stack.append(self.mem.load_i8u(address))
            elif instr.opcode == opcodes.mem.i32_LOAD16_s:
                raise NotImplementedError()
            elif instr.opcode == opcodes.mem.i32_LOAD16_u:
                raise NotImplementedError()
            elif instr.opcode == opcodes.mem.i64_LOAD8_s:
                raise NotImplementedError()
            elif instr.opcode == opcodes.mem.i64_LOAD8_u:
                raise NotImplementedError()
            elif instr.opcode == opcodes.mem.i64_LOAD16_s:
                raise NotImplementedError()
            elif instr.opcode == opcodes.mem.i64_LOAD16_u:
                raise NotImplementedError()
            elif instr.opcode == opcodes.mem.i64_LOAD32_s:
                raise NotImplementedError()
            elif instr.opcode == opcodes.mem.i64_LOAD32_u:
                raise NotImplementedError()
            elif instr.opcode == opcodes.mem.i32_STORE:
                raise NotImplementedError()
            elif instr.opcode == opcodes.mem.i64_STORE:
                raise NotImplementedError()
            elif instr.opcode == opcodes.mem.f32_STORE:
                raise NotImplementedError()
            elif instr.opcode == opcodes.mem.f64_STORE:
                raise NotImplementedError()
            elif instr.opcode == opcodes.mem.i32_STORE8:
                raise NotImplementedError()
            elif instr.opcode == opcodes.mem.i32_STORE16:
                raise NotImplementedError()
            elif instr.opcode == opcodes.mem.i64_STORE8:
                raise NotImplementedError()
            elif instr.opcode == opcodes.mem.i64_STORE16:
                raise NotImplementedError()
            elif instr.opcode == opcodes.mem.i64_STORE32:
                raise NotImplementedError()
            elif instr.opcode == opcodes.mem.SIZE:
                # push count of 64k pages
                raise NotImplementedError()
            elif instr.opcode == opcodes.mem.GROW:
                # use TOS to add or remove pages
                # return previous size
                raise NotImplementedError()
            elif instr.opcode == opcodes.num.i32_CONST:
                ctxt.stack.append(int32(instr.args[0]))
            elif instr.opcode == opcodes.num.i64_CONST:
                ctxt.stack.append(int64(instr.args[0]))
            elif instr.opcode == opcodes.num.f32_CONST:
                ctxt.stack.append(float32(instr.args[0]))
            elif instr.opcode == opcodes.num.f64_CONST:
                ctxt.stack.append(float64(instr.args[0]))
            elif instr.opcode in (opcodes.num.i32_EQZ, opcodes.num.i64_EQZ):
                ctxt.stack.append(int(ctxt.stack.pop() == 0))
            elif instr.opcode in (opcodes.num.i32_EQ, opcodes.num.i64_EQ):
                rhs = ctxt.stack.pop()
                lhs = ctxt.stack.pop()
                ctxt.stack.append(lhs == rhs)
            elif instr.opcode in (opcodes.num.i32_NE, opcodes.num.i64_NE):
                rhs = ctxt.stack.pop()
                lhs = ctxt.stack.pop()
                ctxt.stack.append(lhs != rhs)
            elif instr.opcode in (opcodes.num.i32_LT_s, opcodes.num.i64_LT_s):
                rhs = ctxt.stack.pop()
                lhs = ctxt.stack.pop()
                ctxt.stack.append(lhs < rhs)
            elif instr.opcode in (opcodes.num.i32_LT_u, opcodes.num.i64_LT_u):
                rhs = ctxt.stack.pop()
                lhs = ctxt.stack.pop()
                ctxt.stack.append(lhs < rhs)
            elif instr.opcode in (opcodes.num.i32_GT_s, opcodes.num.i64_GT_s):
                lhs = ctxt.stack.pop()
                rhs = ctxt.stack.pop()
                ctxt.stack.append(lhs > rhs)
            elif instr.opcode in (opcodes.num.i32_GT_u, opcodes.num.i64_GT_u):
                rhs = ctxt.stack.pop()
                lhs = ctxt.stack.pop()
                ctxt.stack.append(lhs > rhs)
            elif instr.opcode in (opcodes.num.i32_LE_s, opcodes.num.i64_LE_s):
                rhs = ctxt.stack.pop()
                lhs = ctxt.stack.pop()
                ctxt.stack.append(lhs <= rhs)
            elif instr.opcode in (opcodes.num.i32_LE_u, opcodes.num.i64_LE_u):
                rhs = ctxt.stack.pop()
                lhs = ctxt.stack.pop()
                ctxt.stack.append(lhs <= rhs)
            elif instr.opcode in (opcodes.num.i32_GE_s, opcodes.num.i64_GE_s):
                rhs = ctxt.stack.pop()
                lhs = ctxt.stack.pop()
                ctxt.stack.append(lhs >= rhs)
            elif instr.opcode in (opcodes.num.i32_GE_u, opcodes.num.i64_GE_u):
                rhs = ctxt.stack.pop()
                lhs = ctxt.stack.pop()
                ctxt.stack.append(lhs >= rhs)
            elif instr.opcode in (opcodes.num.f32_EQ, opcodes.num.f64_EQ):
                rhs = ctxt.stack.pop()
                lhs = ctxt.stack.pop()
                ctxt.stack.append(lhs == rhs)
            elif instr.opcode in (opcodes.num.f32_NE, opcodes.num.f64_NE):
                rhs = ctxt.stack.pop()
                lhs = ctxt.stack.pop()
                ctxt.stack.append(lhs != rhs)
            elif instr.opcode in (opcodes.num.f32_LT, opcodes.num.f64_LT):
                rhs = ctxt.stack.pop()
                lhs = ctxt.stack.pop()
                ctxt.stack.append(lhs < rhs)
            elif instr.opcode in (opcodes.num.f32_GT, opcodes.num.f64_GT):
                rhs = ctxt.stack.pop()
                lhs = ctxt.stack.pop()
                ctxt.stack.append(lhs > rhs)
            elif instr.opcode in (opcodes.num.f32_LE, opcodes.num.f64_LE):
                rhs = ctxt.stack.pop()
                lhs = ctxt.stack.pop()
                ctxt.stack.append(lhs <= rhs)
            elif instr.opcode in (opcodes.num.f32_GE, opcodes.num.f64_GE):
                rhs = ctxt.stack.pop()
                lhs = ctxt.stack.pop()
                ctxt.stack.append(lhs >= rhs)
            elif instr.opcode == opcodes.num.i32_CLZ:
                raise NotImplementedError()
            elif instr.opcode == opcodes.num.i32_CTZ:
                raise NotImplementedError()
            elif instr.opcode == opcodes.num.i32_POPCNT:
                ctxt.stack.append((ctxt.stack.pop()&0xFFFF_FFFF).count('1'))
            elif instr.opcode in (opcodes.num.i32_ADD, opcodes.num.i64_ADD):
                rhs = ctxt.stack.pop()
                lhs = ctxt.stack.pop()
                ctxt.stack.append((lhs + rhs))
            elif instr.opcode in (opcodes.num.i32_SUB, opcodes.num.i64_SUB):
                rhs = ctxt.stack.pop()
                lhs = ctxt.stack.pop()
                ctxt.stack.append((lhs - rhs))
            elif instr.opcode in (opcodes.num.i32_MUL, opcodes.num.i64_MUL):
                rhs = ctxt.stack.pop()
                lhs = ctxt.stack.pop()
                ctxt.stack.append((lhs * rhs))
            elif instr.opcode in (opcodes.num.i32_DIV_s, opcodes.num.i64_DIV_s):
                rhs = ctxt.stack.pop()
                lhs = ctxt.stack.pop()
                ctxt.stack.append((lhs // rhs))
            elif instr.opcode in (opcodes.num.i32_DIV_u, opcodes.num.i64_DIV_u):
                rhs = ctxt.stack.pop()
                lhs = ctxt.stack.pop()
                ctxt.stack.append((lhs // rhs))
            elif instr.opcode in (opcodes.num.i32_REM_s, opcodes.num.i64_REM_s):
                rhs = ctxt.stack.pop()
                lhs = ctxt.stack.pop()
                ctxt.stack.append((lhs % rhs))
            elif instr.opcode in (opcodes.num.i32_REM_u, opcodes.num.i64_REM_u):
                rhs = ctxt.stack.pop()
                lhs = ctxt.stack.pop()
                ctxt.stack.append((lhs % rhs))
            elif instr.opcode in (opcodes.num.i32_AND, opcodes.num.i64_AND):
                rhs = ctxt.stack.pop()
                lhs = ctxt.stack.pop()
                ctxt.stack.append(lhs & rhs)
            elif instr.opcode in (opcodes.num.i32_OR, opcodes.num.i64_OR):
                rhs = ctxt.stack.pop()
                lhs = ctxt.stack.pop()
                ctxt.stack.append(lhs | rhs)
            elif instr.opcode in (opcodes.num.i32_XOR, opcodes.num.i64_XOR):
                rhs = ctxt.stack.pop()
                lhs = ctxt.stack.pop()
                ctxt.stack.append(lhs ^ rhs)
            elif instr.opcode == opcodes.num.i32_SHL:
                i = ctxt.stack.pop()
                k = ctxt.stack.pop()
                ctxt.stack.append((i<<k)&0xFFFF_FFFF)
            elif instr.opcode == opcodes.num.i32_SHR_s:
                i = ctxt.stack.pop()
                k = ctxt.stack.pop()
                ctxt.stack.append((i>>k)&0xFFFF_FFFF)
            elif instr.opcode == opcodes.num.i32_SHR_u:
                i = ctxt.stack.pop()
                k = ctxt.stack.pop()
                ctxt.stack.append((i&0xFFFF_FFFF)>>k)
            elif instr.opcode == opcodes.num.i32_ROTL:
                raise NotImplementedError()
            elif instr.opcode == opcodes.num.i32_ROTR:
                raise NotImplementedError()
            elif instr.opcode == opcodes.num.i64_CLZ:
                raise NotImplementedError()
            elif instr.opcode == opcodes.num.i64_CTZ:
                raise NotImplementedError()
            elif instr.opcode == opcodes.num.i64_POPCNT:
                ctxt.stack.append((ctxt.stack.pop()&0xFFFF_FFFF_FFFF_FFFF).count('1'))
            elif instr.opcode == opcodes.num.i64_SHL:
                i = ctxt.stack.pop()
                k = ctxt.stack.pop()
                ctxt.stack.append((i<<k)&0xFFFF_FFFF_FFFF_FFFF)
            elif instr.opcode == opcodes.num.i64_SHR_s:
                i = ctxt.stack.pop()
                k = ctxt.stack.pop()
                ctxt.stack.append((i>>k)&0xFFFF_FFFF_FFFF_FFFF)
            elif instr.opcode == opcodes.num.i64_SHR_u:
                i = ctxt.stack.pop()
                k = ctxt.stack.pop()
                ctxt.stack.append((i&0xFFFF_FFFF_FFFF_FFFF)>>k)
            elif instr.opcode == opcodes.num.i64_ROTL:
                raise NotImplementedError()
            elif instr.opcode == opcodes.num.i64_ROTR:
                raise NotImplementedError()
            elif instr.opcode == opcodes.num.f32_ABS:
                raise NotImplementedError()
            elif instr.opcode == opcodes.num.f32_NEG:
                raise NotImplementedError()
            elif instr.opcode == opcodes.num.f32_CEIL:
                raise NotImplementedError()
            elif instr.opcode == opcodes.num.f32_FLOOR:
                raise NotImplementedError()
            elif instr.opcode == opcodes.num.f32_TRUNC:
                raise NotImplementedError()
            elif instr.opcode == opcodes.num.f32_NEAREST:
                raise NotImplementedError()
            elif instr.opcode == opcodes.num.f32_SQRT:
                raise NotImplementedError()
            elif instr.opcode == opcodes.num.f32_ADD:
                lhs = ctxt.stack.pop()
                rhs = ctxt.stack.pop()
                ctxt.stack.append(lhs + rhs)
            elif instr.opcode == opcodes.num.f32_SUB:
                raise NotImplementedError()
            elif instr.opcode == opcodes.num.f32_MUL:
                raise NotImplementedError()
            elif instr.opcode == opcodes.num.f32_DIV:
                raise NotImplementedError()
            elif instr.opcode == opcodes.num.f32_MIN:
                raise NotImplementedError()
            elif instr.opcode == opcodes.num.f32_MAX:
                raise NotImplementedError()
            elif instr.opcode == opcodes.num.f32_COPYSIGN:
                raise NotImplementedError()
            elif instr.opcode == opcodes.num.f64_ABS:
                raise NotImplementedError()
            elif instr.opcode == opcodes.num.f64_NEG:
                raise NotImplementedError()
            elif instr.opcode == opcodes.num.f64_CEIL:
                raise NotImplementedError()
            elif instr.opcode == opcodes.num.f64_FLOOR:
                raise NotImplementedError()
            elif instr.opcode == opcodes.num.f64_TRUNC:
                raise NotImplementedError()
            elif instr.opcode == opcodes.num.f64_NEAREST:
                raise NotImplementedError()
            elif instr.opcode == opcodes.num.f64_SQRT:
                raise NotImplementedError()
            elif instr.opcode == opcodes.num.f64_ADD:
                rhs = ctxt.stack.pop()
                lhs = ctxt.stack.pop()
                ctxt.stack.append(lhs + rhs)
            elif instr.opcode == opcodes.num.f64_SUB:
                rhs = ctxt.stack.pop()
                lhs = ctxt.stack.pop()
                ctxt.stack.append(lhs - rhs)
            elif instr.opcode == opcodes.num.f64_MUL:
                rhs = ctxt.stack.pop()
                lhs = ctxt.stack.pop()
                ctxt.stack.append(lhs * rhs)
            elif instr.opcode == opcodes.num.f64_DIV:
                raise NotImplementedError()
            elif instr.opcode == opcodes.num.f64_MIN:
                raise NotImplementedError()
            elif instr.opcode == opcodes.num.f64_MAX:
                raise NotImplementedError()
            elif instr.opcode == opcodes.num.f64_COPYSIGN:
                raise NotImplementedError()
            elif instr.opcode == opcodes.num.i32_WRAP_i64:
                raise NotImplementedError()
            elif instr.opcode == opcodes.num.i32_TRUNC_f32_s:
                raise NotImplementedError()
            elif instr.opcode == opcodes.num.i32_TRUNC_f32_u:
                raise NotImplementedError()
            elif instr.opcode == opcodes.num.i32_TRUNC_f64_s:
                raise NotImplementedError()
            elif instr.opcode == opcodes.num.i32_TRUNC_f64_u:
                raise NotImplementedError()
            elif instr.opcode == opcodes.num.i64_EXTEND_i32_s:
                raise NotImplementedError()
            elif instr.opcode == opcodes.num.i64_EXTEND_i32_u:
                raise NotImplementedError()
            elif instr.opcode == opcodes.num.i64_TRUNC_f32_s:
                raise NotImplementedError()
            elif instr.opcode == opcodes.num.i64_TRUNC_f32_u:
                raise NotImplementedError()
            elif instr.opcode == opcodes.num.i64_TRUNC_f64_s:
                raise NotImplementedError()
            elif instr.opcode == opcodes.num.i64_TRUNC_f64_u:
                raise NotImplementedError()
            elif instr.opcode == opcodes.num.f32_CONVERT_i32_s:
                raise NotImplementedError()
            elif instr.opcode == opcodes.num.f32_CONVERT_i32_u:
                raise NotImplementedError()
            elif instr.opcode == opcodes.num.f32_CONVERT_i64_s:
                raise NotImplementedError()
            elif instr.opcode == opcodes.num.f32_CONVERT_i64_u:
                raise NotImplementedError()
            elif instr.opcode == opcodes.num.f32_DEMOTE_f64:
                raise NotImplementedError()
            elif instr.opcode == opcodes.num.f64_CONVERT_i32_s:
                raise NotImplementedError()
            elif instr.opcode == opcodes.num.f64_CONVERT_i32_u:
                raise NotImplementedError()
            elif instr.opcode == opcodes.num.f64_CONVERT_i64_s:
                raise NotImplementedError()
            elif instr.opcode == opcodes.num.f64_CONVERT_i64_u:
                raise NotImplementedError()
            elif instr.opcode == opcodes.num.f64_PROMOTE_f32:
                raise NotImplementedError()
            elif instr.opcode == opcodes.num.i32_REINTERPRET_f32:
                raise NotImplementedError()
            elif instr.opcode == opcodes.num.i64_REINTERPRET_f64:
                raise NotImplementedError()
            elif instr.opcode == opcodes.num.f32_REINTERPRET_i32:
                raise NotImplementedError()
            elif instr.opcode == opcodes.num.f64_REINTERPRET_i64:
                raise NotImplementedError()
            elif instr.opcode == opcodes.ext.PRINT:
                argcount = instr.args[0]
                args = []
                while len(ctxt.stack) > 0 and argcount > 0:
                    args.insert(0, ctxt.stack.pop())
                    argcount -= 1
                while argcount > 0:
                    args.insert(0, None)
                    argcount -= 1
                print("output:", *args)
            else:
                raise RuntimeError("%r" % instr)

            #if ctxt.stack:
            #    print(" " * 40, instr.opcode, ctxt.stack[-1])

            ctxt.sp += 1

            if ctxt.sp >= len(ctxt.fn.instrs):
                argcount = len(ctxt.fn.results)
                args = []

                self.contexts.pop()
                if len(self.contexts) == 0:
                    break
                for i in range(argcount):
                    args.insert(0, ctxt.stack.pop())
                ctxt = self.contexts[-1]
                for arg in args:
                    ctxt.stack.append(arg)
                continue

        if return_value is None and nresults > 0:
            return_value = []
            for i in range(nresults):
                return_value.insert(0, ctxt.stack.pop())

        return return_value

def main():
    """

    While Loop:
    (block
     (loop
       [loop condition]
       i32.eqz
       [nested statements]
       br_if 1
       br 0)
     )

    (module
      (func (export "addTwo") (param i32 i32) (result i32)
        local.get 0
        local.get 1
        i32.add
      )
      (func (export "callTwo") (param i32 i32) (result i32)
        i32.const 1
        i32.const 2
        call 0)
    )

    (module
      (func (export "singular") (param i32) (result i32)
        (if (result i32) (local.get 0) (then (i32.const 7)) (else (i32.const 8)))
      )
    )

    (module
      (func (export "addTwo") (param i32 i32) (result i32)
        (block
          local.get 0
          local.get 1
          i32.eq
          br_if 0
          i32.const 1
          return)
        i32.const 0
        return))


    (block
        local.get 0
        i32.eqz
        br_if 0
        i32.const 42
        local.set 1)

    (module
      (import "env" "jsprint" (func $jsprint (param i32)))
      (memory $0 1)
      (data (i32.const 0) "Hello World!\00")
      (export "pagememory" (memory $0))
      (func $helloworld
        (call $jsprint (i32.const 0))
      )
      (export "helloworld" (func $helloworld))
    )

    """

    #value = 0b_1001_1000_0111_0110_0101
    #print(value.to_bytes(3, 'big').hex())
    #print(UINT2LEB128(value).hex())
    #value = 123456
    #print(value.to_bytes(3, 'big').hex())
    #print("---")
    #print(SINT2LEB128(0xDEADBEEF).hex())
    #print(UINT2LEB128(0xDEADBEEF).hex())

    backend = PythonBackend()

    backend.mem.store(0, b"hello world\x00")
    print(backend.mem.load(0, 16))

    [
        WasmInstruction(opcodes.ctrl.BLOCK, opcodes.ResultType.VOID),
        WasmInstruction(opcodes.i32.CONST, 4),
        WasmInstruction(opcodes.i32.CONST, 5),
        WasmInstruction(opcodes.i32.ADD),
        WasmInstruction(opcodes.i32.CONST, 9),
        WasmInstruction(opcodes.i32.EQ),
        WasmInstruction(opcodes.ctrl.BR_IF, 0),
        WasmInstruction(opcodes.i32.CONST, 123),
        WasmInstruction(opcodes.ctrl.END),
        WasmInstruction(opcodes.i32.CONST, 456),
    ]

    instrs0 = [
        WasmInstruction(opcodes.i32.CONST, 0),
        WasmInstruction(opcodes.ctrl.CALL, 1),
        WasmInstruction(opcodes.ext.PRINT, 1),
    ]

    instrs1 = [
        WasmInstruction(opcodes.localvar.GET, 0),
        WasmInstruction(opcodes.ctrl.IF, opcodes.ResultType.I32),
        WasmInstruction(opcodes.i32.CONST, 7),
        WasmInstruction(opcodes.ctrl.ELSE),
        WasmInstruction(opcodes.i32.CONST, 8),
        WasmInstruction(opcodes.ctrl.END),
    ]

    fn0 = WasmFunction(instrs0, params=[opcodes.ResultType.I32])
    fn1 = WasmFunction(instrs1, params=[opcodes.ResultType.I32], results=[opcodes.ResultType.I32])

    backend.functions = [fn0, fn1]

    backend.contexts = [WasmStackContext(fn0)]

    rv = backend.run()
    print(rv)

    #print(backend.stack)


def main2():

    #b = UINT2LEB128(12345678)
    #print(b)
    #print(LEB1282UINT(b))
    #print(read_LEB128u(io.BytesIO(b)))

    #b = SINT2LEB128(12345678)
    #print(b)
    #print(LEB1282SINT(b))
    #print(read_LEB128s(io.BytesIO(b)))

    #b = SINT2LEB128(-12345678)
    #print(b)
    #print(LEB1282SINT(b))
    #print(read_LEB128s(io.BytesIO(b)))

    """
    (module
      (func (export "addTwo") (param i32 i32) (result i32)
        local.get 0
        local.get 1
        i32.add
      )
      (func (export "callAddTwo") (result i32)
        i32.const 1
        i32.const 2
        call 0)
    )

    """
    module = WasmModule()

    # module.parse("./simple.wasm")
    # module.parse("./tests/wasm/factorial.wasm")
    module.parse("./tests/wasm/globals.wasm")
    print(module._export_functions)
    backend = PythonBackend()
    backend.init(module)

    #backend.call("callAddTwo")
    #backend.call("fac", [float64(5)])
    backend.call("f", [])
    print(backend.globals)

       #backend.contexts = [WasmStackContext(module.getFunctionByName("callAddTwo"))]
    #fn = module.getFunctionByName("fac");
    #backend.contexts = [WasmStackContext(fn, locals=[float64(5)])]

    #rv = backend.run()
    #print(rv)

if __name__ == '__main__':
    main2()