

import unittest
from tests.util import edit_distance

from daedalus.server import Router

class ParserTestCase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        pass

    @classmethod
    def tearDownClass(cls):
        pass

    def setUp(self):
        super().setUp()

    def tearDown(self):
        super().tearDown()

class RouterTestCase(unittest.TestCase):

    def test_001_compile_pattern(self):
        regex, tokens = Router().patternToRegex("/:path*")
        self.assertEqual(regex.pattern, "^\\/?(.*)\\/?$")

def main():
    unittest.main()


if __name__ == '__main__':
    main()
