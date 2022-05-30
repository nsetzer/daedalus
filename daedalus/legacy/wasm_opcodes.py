
def ispublic(cls, name):
    return not name.startswith("_") and name != 'type_id' and not callable(getattr(cls, name))

class EnumType(type):

    def __new__(metacls, name, bases, namespace):
        cls = super().__new__(metacls, name, bases, namespace)

        cls._value2name = {}
        cls._name2value = {}

        for name in dir(cls):
            if ispublic(cls, name):

                cls._value2name[getattr(cls, name)] = name
                cls._name2value[name] = getattr(cls, name)
                # wrap the value types as instances of enum
                setattr(cls, name, cls(getattr(cls, name)))
        return cls

class Enum(object, metaclass=EnumType):

    def __init__(self, value=None):
        if isinstance(value, Enum):
            self.value = value.value
        elif value in self.__class__._value2name:
            self.value = value
        elif value is None:
            self.value = value
        else:
            raise ValueError(value)

        if not isinstance(self.value, int):
            raise ValueError(value)

    def __repr__(self):
        return "%s.%s" % (self.__class__.__name__, self._value2name[self.value])

    def __str__(self):
        return "%s.%s" % (self.__class__.__name__, self._value2name[self.value])

    def name(self):
        return self.__class__._value2name[self.value]

    def __lt__(self, other):

        return self.value < other.value

    def __le__(self, other):
        return self.value <= other.value

    def __eq__(self, other):
        if isinstance(other, Enum):
          return self.value == other.value
        if isinstance(other, bytes):
          return self.value == ord(other)
        return self.value == other

    def __ne__(self, other):
        return self.value != other.value

    def __ge__(self, other):
        return self.value >= other.value

    def __gt__(self, other):
        return self.value > other.value

    def __hash__(self):
        return hash(self.value)

    def __bool__(self):
        return bool(self.value)

    def __setattr__(self, name, value):
        if name == value:
          raise RuntimeError()
        else:
          super().__setattr__(name, value)

class ArgType(Enum):

    I8s  = 0x01
    I8u  = 0x02

    I32s = 0x03
    I32u = 0x04
    I64s = 0x05
    I64u = 0x06

    F32  = 0x07
    F64  = 0x08

    MEM  = 0x09

class ResultType(Enum):

    NONE  = 0x00
    VOID  = 0x40
    I32 = 0x7F
    I64 = 0x7E
    F32 = 0x7D
    F64 = 0x7C

    NULL      = 0x1F
    UNDEFINED = 0x1E
    ANY       = 0x1D

    OBJECT    = 0x19
    LIST      = 0x18
    TUPLE     = 0x17
    SET       = 0x16
    FUNCTION  = 0x15

    TRUE      = 0x11
    FALSE     = 0x10

class mem(Enum):

  i32_LOAD =     0x28
  i64_LOAD =     0x29
  f32_LOAD =     0x2A
  f64_LOAD =     0x2B

  i32_LOAD8_s =  0x2C
  i32_LOAD8_u =  0x2D
  i32_LOAD16_s = 0x2E
  i32_LOAD16_u = 0x2F

  i64_LOAD8_s =  0x30
  i64_LOAD8_u =  0x31
  i64_LOAD16_s = 0x32
  i64_LOAD16_u = 0x33
  i64_LOAD32_s = 0x34
  i64_LOAD32_u = 0x35

  i32_STORE =    0x36
  i64_STORE =    0x37
  f32_STORE =    0x38
  f64_STORE =    0x39

  i32_STORE8 =   0x3A
  i32_STORE16 =  0x3B

  i64_STORE8 =   0x3C
  i64_STORE16 =  0x3D
  i64_STORE32 =  0x3E

  SIZE =         0x3F
  GROW =         0x40

class num(Enum):

  # num
  i32_CONST =  0x41
  i64_CONST =  0x42
  f32_CONST =  0x43
  f64_CONST =  0x44

  i32_EQZ =    0x45
  i32_EQ =     0x46
  i32_NE =     0x47
  i32_LT_s =   0x48
  i32_LT_u =   0x49
  i32_GT_s =   0x4A
  i32_GT_u =   0x4B
  i32_LE_s =   0x4C
  i32_LE_u =   0x4D
  i32_GE_s =   0x4E
  i32_GE_u =   0x4F

  i64_EQZ =    0x50
  i64_EQ =     0x51
  i64_NE =     0x52
  i64_LT_s =   0x53
  i64_LT_u =   0x54
  i64_GT_s =   0x55
  i64_GT_u =   0x56
  i64_LE_s =   0x57
  i64_LE_u =   0x58
  i64_GE_s =   0x59
  i64_GE_u =   0x5A

  f32_EQ =     0x5B
  f32_NE =     0x5C
  f32_LT =     0x5D
  f32_GT =     0x5E
  f32_LE =     0x5F
  f32_GE =     0x60

  f64_EQ =     0x61
  f64_NE =     0x62
  f64_LT =     0x63
  f64_GT =     0x64
  f64_LE =     0x65
  f64_GE =     0x66

  i32_CLZ =    0x67
  i32_CTZ =    0x68
  i32_POPCNT = 0x69
  i32_ADD =    0x6A
  i32_SUB =    0x6B
  i32_MUL =    0x6C
  i32_DIV_s =  0x6D
  i32_DIV_u =  0x6E
  i32_REM_s =  0x6F
  i32_REM_u =  0x70
  i32_AND =    0x71
  i32_OR =     0x72
  i32_XOR =    0x73
  i32_SHL =    0x74
  i32_SHR_s =  0x75
  i32_SHR_u =  0x76
  i32_ROTL =   0x77
  i32_ROTR =   0x78

  i64_CLZ =    0x79
  i64_CTZ =    0x7A
  i64_POPCNT = 0x7B
  i64_ADD =    0x7C
  i64_SUB =    0x7D
  i64_MUL =    0x7E
  i64_DIV_s =  0x7F
  i64_DIV_u =  0x80
  i64_REM_s =  0x81
  i64_REM_u =  0x82
  i64_AND =    0x83
  i64_OR =     0x84
  i64_XOR =    0x85
  i64_SHL =    0x86
  i64_SHR_s =  0x87
  i64_SHR_u =  0x88
  i64_ROTL =   0x89
  i64_ROTR =   0x8A

  f32_ABS =      0x8B
  f32_NEG =      0x8C
  f32_CEIL =     0x8D
  f32_FLOOR =    0x8E
  f32_TRUNC =    0x8F
  f32_NEAREST =  0x90
  f32_SQRT =     0x91
  f32_ADD =      0x92
  f32_SUB =      0x93
  f32_MUL =      0x94
  f32_DIV =      0x95
  f32_MIN =      0x96
  f32_MAX =      0x97
  f32_COPYSIGN = 0x98

  f64_ABS =      0x99
  f64_NEG =      0x9A
  f64_CEIL =     0x9B
  f64_FLOOR =    0x9C
  f64_TRUNC =    0x9D
  f64_NEAREST =  0x9E
  f64_SQRT =     0x9F
  f64_ADD =      0xA0
  f64_SUB =      0xA1
  f64_MUL =      0xA2
  f64_DIV =      0xA3
  f64_MIN =      0xA4
  f64_MAX =      0xA5
  f64_COPYSIGN = 0xA6

  i32_WRAP_i64 =     0xA7
  i32_TRUNC_f32_s =  0xA8
  i32_TRUNC_f32_u =  0xA9
  i32_TRUNC_f64_s =  0xAA
  i32_TRUNC_f64_u =  0xAB

  i64_EXTEND_i32_s = 0xAC
  i64_EXTEND_i32_u = 0xAD
  i64_TRUNC_f32_s =  0xAE
  i64_TRUNC_f32_u =  0xAF
  i64_TRUNC_f64_s =  0xB0
  i64_TRUNC_f64_u =  0xB1

  f32_CONVERT_i32_s =  0xB2
  f32_CONVERT_i32_u =  0xB3
  f32_CONVERT_i64_s =  0xB4
  f32_CONVERT_i64_u =  0xB5
  f32_DEMOTE_f64 =     0xB6

  f64_CONVERT_i32_s =  0xB7
  f64_CONVERT_i32_u =  0xB8
  f64_CONVERT_i64_s =  0xB9
  f64_CONVERT_i64_u =  0xBA
  f64_PROMOTE_f32 =    0xBB

  i32_REINTERPRET_f32 =  0xBC
  i64_REINTERPRET_f64 =  0xBD
  f32_REINTERPRET_i32 =  0xBE
  f64_REINTERPRET_i64 =  0xBF

class localvar(Enum):
  GET =  0x20
  SET =  0x21
  TEE =  0x22

class globalvar(Enum):
  GET =  0x23
  SET =  0x24

class ctrl(Enum):
  UNREACHABLE =    0x00
  NOP =            0x01  # NOP
  BLOCK =          0x02  #
  LOOP =           0x03
  IF =             0x04
  ELSE =           0x05
  END =            0x0B
  BR =             0x0C
  BR_IF =          0x0D
  BR_TABLE =       0x0E
  RETURN =         0x0F
  CALL =           0x10
  CALL_INDIRECT =  0x11

class parametric(Enum):
  DROP =   0x1A
  SELECT = 0x1B

# ('<', '<=', '==', '!=', '>', '>=', 'in', 'not in', 'is', 'is not', 'exception match', 'BAD')

class i32(Enum):

  LOAD =     mem.i32_LOAD
  LOAD8_s =  mem.i32_LOAD8_s
  LOAD8_u =  mem.i32_LOAD8_u
  LOAD16_s = mem.i32_LOAD16_s
  LOAD16_u = mem.i32_LOAD16_u

  STORE =    mem.i32_STORE
  STORE8 =   mem.i32_STORE8
  STORE16 =  mem.i32_STORE16

  CONST =    num.i32_CONST # LOAD_CONST

  EQZ =      num.i32_EQZ   # equals zero
  EQ =       num.i32_EQ    # COMPARE_OP('==') -> int
  NE =       num.i32_NE    # COMPARE_OP('!=') -> int
  LT_s =     num.i32_LT_s  # COMPARE_OP('<') -> int
  LT_u =     num.i32_LT_u  # COMPARE_OP('<') -> int
  GT_s =     num.i32_GT_s  # COMPARE_OP('>') -> int
  GT_u =     num.i32_GT_u  # COMPARE_OP('>') -> int
  LE_s =     num.i32_LE_s  # COMPARE_OP('<=') -> int
  LE_u =     num.i32_LE_u  # COMPARE_OP('<=') -> int
  GE_s =     num.i32_GE_s  # COMPARE_OP('>=') -> int
  GE_u =     num.i32_GE_u  # COMPARE_OP('>=') -> int

  CLZ =      num.i32_CLZ     # count leading zeros
  CTZ =      num.i32_CTZ     # count trailing zeros
  POPCNT =   num.i32_POPCNT  # count non-zero
  ADD =      num.i32_ADD     # BINARY_ADD
  SUB =      num.i32_SUB     # BINARY_SUBTRACT
  MUL =      num.i32_MUL     # BINARY_MULTIPLY
  DIV_s =    num.i32_DIV_s   # BINARY_FLOOR_DIVIDE / BINARY_TRUE_DIVIDE
  DIV_u =    num.i32_DIV_u   # BINARY_FLOOR_DIVIDE / BINARY_TRUE_DIVIDE
  REM_s =    num.i32_REM_s   # BINARY_MODULO
  REM_u =    num.i32_REM_u   # BINARY_MODULO
  AND =      num.i32_AND     # BINARY_AND
  OR =       num.i32_OR      # BINARY_OR
  XOR =      num.i32_XOR     # BINARY_XOR
  SHL =      num.i32_SHL     # BINARY_LSHIFT
  SHR_s =    num.i32_SHR_s   # BINARY_RSHIFT
  SHR_u =    num.i32_SHR_u   # BINARY_RSHIFT
  ROTL =     num.i32_ROTL    # rotate left
  ROTR =     num.i32_ROTR    # rotate right

  WRAP_i64 =     num.i32_WRAP_i64     # i % 2**32
  TRUNC_f32_s =  num.i32_TRUNC_f32_s  # int(v)
  TRUNC_f32_u =  num.i32_TRUNC_f32_u  # int(v)
  TRUNC_f64_s =  num.i32_TRUNC_f64_s  # int(v)
  TRUNC_f64_u =  num.i32_TRUNC_f64_u  # int(v)

  REINTERPRET_f32 =  num.i32_REINTERPRET_f32  # reinterpret

class i64(Enum):
  LOAD =     mem.i64_LOAD
  LOAD8_s =  mem.i64_LOAD8_s
  LOAD8_u =  mem.i64_LOAD8_u
  LOAD16_s = mem.i64_LOAD16_s
  LOAD16_u = mem.i64_LOAD16_u
  LOAD32_s = mem.i64_LOAD32_s
  LOAD32_U = mem.i64_LOAD32_u

  STORE =    mem.i64_STORE
  STORE8 =   mem.i64_STORE8
  STORE16 =  mem.i64_STORE16
  STORE32 =  mem.i64_STORE32

  CONST =    num.i64_CONST

  EQZ =      num.i64_EQZ
  EQ =       num.i64_EQ
  NE =       num.i64_NE
  LT_s =     num.i64_LT_s
  LT_u =     num.i64_LT_u
  GT_s =     num.i64_GT_s
  GT_u =     num.i64_GT_u
  LE_s =     num.i64_LE_s
  LE_u =     num.i64_LE_u
  GE_s =     num.i64_GE_s
  GE_u =     num.i64_GE_u

  CLZ =      num.i64_CLZ
  CTZ =      num.i64_CTZ
  POPCNT =   num.i64_POPCNT
  ADD =      num.i64_ADD
  SUB =      num.i64_SUB
  MUL =      num.i64_MUL
  DIV_s =    num.i64_DIV_s
  DIV_u =    num.i64_DIV_u
  REM_s =    num.i64_REM_s
  REM_u =    num.i64_REM_u
  AND =      num.i64_AND
  OR =       num.i64_OR
  XOR =      num.i64_XOR
  SHL =      num.i64_SHL
  SHR_s =    num.i64_SHR_s
  SHR_u =    num.i64_SHR_u
  ROTL =     num.i64_ROTL
  ROTR =     num.i64_ROTR

  EXTEND_i32_s = num.i64_EXTEND_i32_s
  EXTEND_i32_u = num.i64_EXTEND_i32_u
  TRUNC_f32_s =  num.i64_TRUNC_f32_s
  TRUNC_f32_u =  num.i64_TRUNC_f32_u
  TRUNC_f64_s =  num.i64_TRUNC_f64_s
  TRUNC_f64_u =  num.i64_TRUNC_f64_u

  REINTERPRET_f64 =  num.i64_REINTERPRET_f64

class f32(Enum):
  LOAD =   mem.f32_LOAD
  STORE =  mem.f32_STORE

  CONST =  num.f32_CONST

  EQ =     num.f32_EQ
  NE =     num.f32_NE
  LT =     num.f32_LT
  GT =     num.f32_GT
  LE =     num.f32_LE
  GE =     num.f32_GE

  ABS =      num.f32_ABS
  NEG =      num.f32_NEG
  FLOOR =    num.f32_FLOOR
  TRUNC =    num.f32_TRUNC
  NEAREST =  num.f32_NEAREST
  SQRT =     num.f32_SQRT
  ADD =      num.f32_ADD
  SUB =      num.f32_SUB
  MUL =      num.f32_MUL
  DIV =      num.f32_DIV
  MIN =      num.f32_MIN
  MAX =      num.f32_MAX
  COPYSIGN = num.f32_COPYSIGN

  CONVERT_i32_s =  num.f32_CONVERT_i32_s
  CONVERT_i32_u =  num.f32_CONVERT_i32_u
  CONVERT_i64_s =  num.f32_CONVERT_i64_s
  CONVERT_i64_u =  num.f32_CONVERT_i64_u
  DEMOTE_f64    =  num.f32_DEMOTE_f64

  REINTERPRET_i32 =  num.f32_REINTERPRET_i32

class f64(Enum):
  LOAD =   mem.f64_LOAD
  STORE =  mem.f64_STORE

  CONST =  num.f64_CONST

  EQ =     num.f64_EQ
  NE =     num.f64_NE
  LT =     num.f64_LT
  GT =     num.f64_GT
  LE =     num.f64_LE
  GE =     num.f64_GE

  ABS =      num.f64_ABS
  NEG =      num.f64_NEG
  FLOOR =    num.f64_FLOOR
  TRUNC =    num.f64_TRUNC
  NEAREST =  num.f64_NEAREST
  SQRT =     num.f64_SQRT
  ADD =      num.f64_ADD
  SUB =      num.f64_SUB
  MUL =      num.f64_MUL
  DIV =      num.f64_DIV
  MIN =      num.f64_MIN
  MAX =      num.f64_MAX
  COPYSIGN = num.f64_COPYSIGN

  CONVERT_i32_s =  num.f64_CONVERT_i32_s
  CONVERT_i32_u =  num.f64_CONVERT_i32_u
  CONVERT_i64_s =  num.f64_CONVERT_i64_s
  CONVERT_i64_u =  num.f64_CONVERT_i64_u
  PROMOTE_f32   =  num.f64_PROMOTE_f32

  REINTERPRET_i64 =  num.f64_REINTERPRET_i64

class ext(Enum):
  PRINT = 0xFF01

  CREATE    = 0xFF02  # ResultType, N=number of stack elements to consume
                      # ResultType is one of OBJECT, LIST, TUPLE, SET
                      # e.g. ResultType.OBJECT, 4 creates an obj with 2 keys and 2 values
  GET_INDEX = 0xFF03
  SET_INDEX = 0xFF04
  GET_ATTR  = 0xFF05
  SET_ATTR  = 0xFF06

argtypes = {
    ctrl.BLOCK:         [ArgType.I8u],
    ctrl.LOOP:          [ArgType.I8u],
    ctrl.IF:            [ArgType.I8u],
    ctrl.BR_IF:         [ArgType.I32u],
    ctrl.BR_TABLE:      [ArgType.I32u, ArgType.I32u],
    ctrl.CALL:          [ArgType.I32u],
    ctrl.CALL_INDIRECT: [ArgType.I32u, ArgType.I8u],
    localvar.GET:       [ArgType.I32u],
    localvar.SET:       [ArgType.I32u],
    localvar.TEE:       [ArgType.I32u],
    globalvar.GET:      [ArgType.I32u],
    globalvar.SET:      [ArgType.I32u],
    mem.i32_LOAD:       [ArgType.MEM],
    mem.i64_LOAD:       [ArgType.MEM],
    mem.f32_LOAD:       [ArgType.MEM],
    mem.f64_LOAD:       [ArgType.MEM],
    mem.i32_LOAD8_s:    [ArgType.MEM],
    mem.i32_LOAD8_u:    [ArgType.MEM],
    mem.i32_LOAD16_s:   [ArgType.MEM],
    mem.i32_LOAD16_u:   [ArgType.MEM],
    mem.i64_LOAD8_s:    [ArgType.MEM],
    mem.i64_LOAD8_u:    [ArgType.MEM],
    mem.i64_LOAD16_s:   [ArgType.MEM],
    mem.i64_LOAD16_u:   [ArgType.MEM],
    mem.i64_LOAD32_s:   [ArgType.MEM],
    mem.i64_LOAD32_u:   [ArgType.MEM],
    mem.i32_STORE:      [ArgType.MEM],
    mem.i64_STORE:      [ArgType.MEM],
    mem.f32_STORE:      [ArgType.MEM],
    mem.f64_STORE:      [ArgType.MEM],
    mem.i32_STORE8:     [ArgType.MEM],
    mem.i32_STORE16:    [ArgType.MEM],
    mem.i64_STORE8:     [ArgType.MEM],
    mem.i64_STORE16:    [ArgType.MEM],
    mem.i64_STORE32:    [ArgType.MEM],
    num.i32_CONST:      [ArgType.I32s],
    num.i64_CONST:      [ArgType.I64s],
    num.f32_CONST:      [ArgType.F32],
    num.f64_CONST:      [ArgType.F64],
}

value2enum = {}
lookup = lambda e: {val: getattr(e, nam) for val, nam in e._value2name.items()}
value2enum.update(lookup(mem))
value2enum.update(lookup(num))
value2enum.update(lookup(localvar))
value2enum.update(lookup(globalvar))
value2enum.update(lookup(ctrl))
value2enum.update(lookup(parametric))

def main():

  print(ctrl.ELSE)

if __name__ == '__main__':
  main()