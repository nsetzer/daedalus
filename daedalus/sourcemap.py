
import sys
import io
import base64

class SourceMap(object):
    """
    5 fields: output column, file index, input line, input column, name index
    4 fields: output column, file index, input line, input column,
    1 fields: column
    """
    ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"

    def __init__(self):
        super(SourceMap, self).__init__()

        self.version = "3"
        self.sources = []
        self.names = {}
        self.mappings = []
        self.sourceRoot = ""
        self.file = ""
        self.column = 0

    def toJsonObject(self):

        mappings = ";".join([",".join(m) for m in self.mappings])

        obj = {
            "version": self.version,
            "sources": self.sources,
            "names": self.names,
            "mappings": mappings,
        }

        return obj

    def _encode(self, value):

        text = ""
        # 456 : 1 1000 0 | 0 11100
        signed = 0
        if value < 0:
            signed = 1
            value *= -1

        first = True
        while first or value:

            if first:
                tmp = ((value & 0xF) << 1) | signed
                value >>= 4
                first = False
            else:
                tmp = value & 0x1F
                value >>= 5

            if value:
                tmp |= 1 << 5

            text += SourceMap.ALPHABET[tmp]

        return text

    def b64encode(self, seq):
        return ''.join(self._encode(i) for i in seq)

    def b64decode(self, text):

        seq = []

        pos = 0
        sign = 1
        value = 0
        for char in text:
            i = SourceMap.ALPHABET.index(char)
            if pos == 0:
                if i & 1:
                    sign = -1
                value = (i >> 1) & 0xF
                pos += 4
            else:
                value |= (i & 0x1F) << pos
                pos += 5

            if 0x20 & i == 0:
                seq.append(value * sign)
                sign = 1
                value = 0
                pos = 0
        return seq

    def write(self, token):

        if token.type == Token.T_NEWLINE:
            self.mappings.append([])
            self.column = 0

        elif token.type == Token.T_TEXT:
            fields = [self.column, token.file, token.line, token.column]
            if token.original_value:
                fields.append(self.getIndex(token.original_value))
            self.mappings[-1].append(self.b64encode(fields))
            self.column += len(token.value)
        else:
            self.column += len(token.value)

    def getIndex(self, name):
        if name not in self.names:
            self.names[name] = len(self.names)
        return self.names[name]