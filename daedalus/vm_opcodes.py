
def LEB128u(value):
    out = value & 0b0111_1111
    value >>= 7;
    n = 1
    while value:
        out |= 0b1000_0000
        out <<= 8;
        lsb = (value & 0b0111_1111)
        value >>= 7;
        out |= lsb
        n += 1
    return out.to_bytes(n, 'big')

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

def LEB128s(val):
    out = []
    while True:
        byte = val & 0x7f
        idx = idx >> 7
        if (idx == 0 and byte & 0x40 == 0) or (idx == -1 and byte & 0x40 != 0):
            out.append(byte)
            break
        out.append(0x80 | byte)
    return bytearray(out)

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

class IntEnumType(type):

    def __new__(metacls, name, bases, namespace):
        cls = super().__new__(metacls, name, bases, namespace)

        cls._value2name = {}
        cls._name2value = {}

        for name in dir(cls):
            if not name.startswith("_") and name != 'type_id' and not callable(getattr(cls, name)):

                val = getattr(cls, name)
                if isinstance(val, tuple):
                    val, argcount = val
                else:
                    argcount = 0

                cls._name2value[name] = val
                cls._value2name[val] = name
                inst = cls(val)
                inst.argcount = argcount

                # wrap the value types as instances of enum
                setattr(cls, name, inst)
        return cls

class IntEnum(object, metaclass=IntEnumType):

    def __init__(self, value=None):
        if isinstance(value, IntEnumType):
            self.value = value.value
        elif value in self.__class__._value2name:
            self.value = value
        elif value is None:
            self.value = value
        elif not isinstance(value, int):
            raise ValueError(value)
        else:
            self.value = value


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

class ResultType(object):

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
    STRING    = 0x09
    NUMBER    = 0x08

class ctrl(IntEnum):
    NOP =            0x00, 0  # NOP
    #BLOCK =          0x01, 0  #
    LOOP =           0x01, 0  #        ; start of loop construct
    IF =             0x02, 1  #        ; conditional jump
    ELSE =           0x03, 1  #        ; unconditional jump
    END =            0x04, 0  #        ; end of a block, loop, if
    JUMP =           0x05, 1  #        ; unconditional jump
    RETURN =         0x06, 1  # numargs;
    TRY =            0x07, 0
    CATCH =          0x08, 0
    FINALLY =        0x09, 0
    TRYEND =         0x0A, 0
    THROW =          0x0B, 0

    CALL    =        0x0C, 1
    CALL_EX =        0x0D, 1

    _RESERVED =        0x0E, 0
    _RESERVED =        0x0F, 0
    _RESERVED =        0x10, 0
    _RESERVED =        0x11, 0

class stack(IntEnum):
    ROT2 = 0x12
    ROT3 = 0x13
    ROT4 = 0x14
    DUP  = 0x15
    POP  = 0x16

class localvar(IntEnum):
    GET    = 0x17, 1  # varindex
    SET    = 0x18, 1  # varindex
    DELETE = 0x19, 1  # varindex

class globalvar(IntEnum):
    GET    = 0x1A, 1  # globalindex
    SET    = 0x1B, 1  # globalindex
    DELETE = 0x1C, 1  # globalindex

class cellvar(IntEnum):
    LOAD_REF      =  0x20, 1  # cellindex
    STORE_REF     =  0x21, 1  # cellindex
    LOAD_DEREF    =  0x22, 1  # cellindex
    STORE_DEREF   =  0x23, 1  # cellindex
    DELETE_DEREF  =  0x24, 1  # cellindex


class const(IntEnum):

    INT       = 0x77, 1  # signed leb 128
    FLOAT32   = 0x78, 1  # 4 byte float
    FLOAT64   = 0x7A, 1  # 8 byte float
    STRING    = 0x7B, 1  # dataindex
    BYTES     = 0x7C, 1  # dataindex
    BOOL      = 0x7D, 0
    UNDEFINED = 0x7E, 0
    NULL      = 0x7F, 0


class comp(IntEnum):
    LT  = 0x31
    LE  = 0x32
    EQ  = 0x33
    NE  = 0x34
    GE  = 0x35
    GT  = 0x36
    TEQ = 0x37
    TNE = 0x38

class math(IntEnum):
  POSITIVE     = 0x39  # TOS = +TOS
  NEGATIVE     = 0x3A  # TOS = -TOS
  BITWISE_NOT  = 0x3B  # TOS = ~TOS

  AND          = 0x3C  # TOS = TOS1 && TOS2
  OR           = 0x3D  # TOS = TOS1 || TOS2
  NOT          = 0x3E  # TOS = !TOS1

  ADD          = 0x40  # TOS = TOS1 + TOS2
  SUB          = 0x41  # TOS = TOS1 - TOS2
  MUL          = 0x42  # TOS = TOS1 * TOS2
  DIV          = 0x43  # TOS = TOS1 / TOS2
  REM          = 0x44  # TOS = TOS1 % TOS2
  EXP          = 0x45  # TOS = TOS1 ** TOS2
  BITWISE_AND  = 0x46  # TOS = TOS1 && TOS2
  BITWISE_OR   = 0x47  # TOS = TOS1 || TOS2
  BITWISE_XOR  = 0x48  # TOS = TOS1 ^ TOS2
  SHIFTL       = 0x49  # TOS = TOS1 << TOS2
  SHIFTR       = 0x4A  # TOS = TOS1 >> TOS2


class obj(IntEnum):

    GET_ATTR  = 0x50, 1  # TOS = TOS1?.name[i]
    SET_ATTR  = 0x51, 1  # TOS1?.name[i] = TOS2
    DEL_ATTR  = 0x52, 1  # delete TOS1?.name[i]

    GET_INDEX = 0x53 # TOS = TOS1[TOS2]
    SET_INDEX = 0x54 # TOS1[TOS2] = TOS3
    DEL_INDEX = 0x55 # del TOS1[TOS2]

    CREATE_OBJECT   = 0x5A
    CREATE_ARRAY    = 0x5B
    CREATE_TUPLE    = 0x5C
    CREATE_SET      = 0x5D

    # fnidx, argcount
    # arg is number of function arguments
    # default values are popped from the stack
    CREATE_FUNCTION = 0x6D, 1

    CREATE_CLASS    = 0x6F

value2enum = {}

def getEnum(val):

    if len(value2enum) == 0:
        lookup = lambda e: {val: getattr(e, nam) for val, nam in e._value2name.items()}
        value2enum.update(lookup(ctrl))
        value2enum.update(lookup(localvar))
        value2enum.update(lookup(globalvar))
        value2enum.update(lookup(cellvar))
        value2enum.update(lookup(const))
        value2enum.update(lookup(comp))
        value2enum.update(lookup(stack))
        value2enum.update(lookup(math))
        value2enum.update(lookup(obj))

    return value2enum[val]


def main():

    print(localvar.GET)
    print(localvar.GET.argcount)

    print(getEnum(0x50))
    print(getEnum(0x50).argcount)

if __name__ == '__main__':
    main()