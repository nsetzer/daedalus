
import sys
import io
import base64
from .lexer import Lexer, Token, TokenError

class SourceMap(object):
    """
    this implements a restricted subset of the full version 3 spec
    only 4-field VLQs are supported

    5 fields: output column, file index, input line, input column, name index
    4 fields: output column, file index, input line, input column,
    1 fields: column
    """
    ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"

    def __init__(self):
        super(SourceMap, self).__init__()

        self.version = 3
        self.sources = {}
        self.names = {}
        # the first line is for the comment indicating
        # where the source map is located
        # effectively ones-based indexing
        self.mappings = [[],[]]
        self.line2file = [] # lineNumber to (fileIndex, originalLineNumber)
        self.sourceRoot = ""
        self.column = 0

        self.last_field = None

        self.debug_count = 0

    @staticmethod
    def _encode(value):

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

    @staticmethod
    def b64encode(seq):
        return ''.join(SourceMap._encode(i) for i in seq)

    @staticmethod
    def b64decode(text):

        seq = []

        pos = 0
        sign = 1
        value = 0
        for char in text:
            try:
                i = SourceMap.ALPHABET.index(char)
            except ValueError:
                raise ValueError(f"{char} not found in alphabet")
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

    @staticmethod
    def decode(mappings):
        fields = []
        last_field = [0,0,0,0]
        for line in mappings.split(";"):
            # the column index resets to zero for every line
            last_field = last_field[:]
            last_field[0] = 0
            fields.append([])
            if line:
                mapping = line.split(",")
                for field in [SourceMap.b64decode(vlq) for vlq in mapping]:

                    field = [(a+b) for a,b in zip(field, last_field)]
                    last_field = field
                    fields[-1].append(field)
        return fields

    def write_line(self):
        self.mappings.append([])
        self.line2file.append(None)
        self.column = 0
        if self.last_field:
            self.last_field[0] = 0

    def write(self, token):

        if token.type == Token.T_NEWLINE:
            self.write_line()

        else:

            if token.type == Token.T_DOCUMENTATION:
                return


            if token.file is not None:

                if token.file not in self.sources:
                    self.sources[token.file] = len(self.sources)
                file_index = self.sources[token.file]

                field = [self.column, file_index, token.line-1, token.index]
                # optional fifth field for symbol name
                #if token.original_value:
                #    field.append(self._getNameIndex(token.original_value))

                if self.last_field:
                    delta_field = [(a-b) for a,b in zip(field, self.last_field)]
                    vlq = SourceMap.b64encode(delta_field)
                else:
                    vlq = SourceMap.b64encode(field)

                self.last_field = field

                self.mappings[-1].append(vlq)

                if len(self.line2file) == 0:
                    self.line2file.append([])
                if self.line2file[-1] is None:
                    self.line2file[-1] = (file_index, token.line-1)

    def _getNameIndex(self, name):
        if name not in self.names:
            self.names[name] = len(self.names)
        return self.names[name]

    def getSourceMap(self):
        # https://sourcemaps.info/spec.html#h.lmz475t4mvbx
        mappings = ";".join([",".join(mapping) for mapping in self.mappings])
        return {
            "version" : self.version,
            # "file": "index.js",
            # "sourceRoot": "/static/sourcemap/src/",
            "sources": list(self.sources.keys()),
            #"sourcesContent": [null, null],
            "names": list(self.names.keys()),
            "mappings": mappings
        }

    def getServerMap(self):
        sources = list(self.sources.keys())
        mapping = self.line2file
        return sources, mapping
