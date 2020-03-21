
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
