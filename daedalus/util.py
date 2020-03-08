
import os
import struct

from .lexer import TokenError

def intBitsToFloat(b):
    """
    Type-Pun an integer into a float
    """
    s = struct.pack('>L', b)
    return struct.unpack('>f', s)[0]

def intBitsToDouble(b):
    """
    Type-Pun an integer into a double
    """
    s = struct.pack('>Q', b)
    return struct.unpack('>d', s)[0]

def floatBitsToInt(b):
    """
    Type-Pun a float into an integer
    """
    s = struct.pack('>f', b)
    return struct.unpack('>L', s)[0]

def doubleBitsToInt(b):
    """
    Type-Pun a double into an integer
    """
    s = struct.pack('>d', b)
    return struct.unpack('>Q', s)[0]

number_prefix = {"0x": 16, "0o": 8, "0n":4, "0b": 2, '0f': -1}
number_suffix = ["tb", "gb", "mb", "kb", "b", "t", "g", "m", "k", "b"]
number_factors = {
    "tb": 1024*1024*1024*1024,
    "gb": 1024*1024*1024,
    "mb": 1024*1024,
    "kb": 1024,
    "b" : 1,
    "t" : 1000*1000*1000*1000,
    "g" : 1000*1000*1000,
    "m":  1000*1000,
    "k":  1000,
}

def parseNumber(token):
    """
    parse string as a numerical value.
    produces either a int, float or complex number

    "_" can be used as a visual separator anywhere in the number

    """
    text = token.value

    text = text.replace("_", "")

    imaginary = False
    if text.endswith('j'):
        imaginary = True
        text = text[:-1]

    factor = None
    for fix in number_suffix:
        if text.endswith(fix):
            factor = number_factors[fix]
            text = text[:-len(fix)]

    base = 10
    for fix in number_prefix.keys():
        if text.startswith(fix):
            text = text[len(fix):]
            base = number_prefix[fix]
            break

    value = None
    if base == -1:
        text = text[2:]
        try:
            value = int(text, 16)
        except Exception as e:
            value = None

        if value and len(text) == 8:
            value = intBitsToFloat(value)
        elif value and len(text) == 16:
            value = intBitsToDouble(value)
        else:
            raise TokenError(token, "invalid numerical constant expected 8 or 16 digits")
    else:
        try:
            value = int(text, base)
        except Exception as e:
            value = None
    if not value and "." in text or 'e' in text:
        try:
            if base == 10:
                value = float(text)
        except Exception as e:
            value = None

    if value is None:
        raise TokenError(token, "invalid numerical constant")

    if value and factor:
        value *= factor

    if imaginary:
        value *= 1j

    return value