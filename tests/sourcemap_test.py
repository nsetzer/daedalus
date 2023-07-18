
import unittest
from tests.util import edit_distance

from daedalus.lexer import Lexer
from daedalus.parser import Parser
from daedalus.sourcemap import SourceMap

class SourceMapTestCase(unittest.TestCase):

    def test_001_b64decode(self):
        srcmap = SourceMap()

        self.assertEqual(srcmap.b64decode('uDt7D0TkuK'), [55, -1974, 314, 5346])
        self.assertEqual(srcmap.b64decode('gvDn1EilwhEQ4xDpo3vP'), [1776, -2387, 2121809, 8, 1820, -8121988])

    def test_001_b64encode(self):
        srcmap = SourceMap()

        self.assertEqual(srcmap.b64encode([55, -1974, 314, 5346]), 'uDt7D0TkuK')
        self.assertEqual(srcmap.b64encode([1776, -2387, 2121809, 8, 1820, -8121988]), 'gvDn1EilwhEQ4xDpo3vP')


    def test_001_decode(self):
        srcmap = SourceMap()

        text = "AAAA,OAAQ;EACP,KAAK,EAAE,KAAK"
        mappings = [s.split(",") for s in text.split(";")]

        vlqs = []
        for mapping in mappings:
            vlqs.append([srcmap.b64decode(vlq) for vlq in mapping])

        expected = [[[0, 0, 0, 0], [7, 0, 0, 8]], [[2, 0, 1, -7], [5, 0, 0, 5], [2, 0, 0, 2], [5, 0, 0, 5]]]

        self.assertEqual(expected, vlqs)
def main():
    unittest.main()


if __name__ == '__main__':
    main()

