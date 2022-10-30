#! cd .. && python3 -m tests.server_test


import unittest
from tests.util import edit_distance

from daedalus.server import Router, Response, JsonResponse

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

class ResponseTestCase(unittest.TestCase):

    def test_001_json(self):
        resp = JsonResponse({"result": "ok"})
        self.assertEqual(resp.payload, b'{"result": "ok"}\n')

    def test_001_compress(self):
        resp = Response(200, "1"*16, compress=True)
        # first  bytes are the gzip header: magic number + variable time stamp
        self.assertEqual(resp.payload[8:],
             b'\x02\xff34D\x05\x00\x86\x08\x1b\x1c\x10\x00\x00\x00')

class RouterTestCase(unittest.TestCase):

    def test_001_compile_pattern_many(self):
        regex, tokens = Router().patternToRegex("/:path+")
        self.assertEqual(regex.pattern, "^\\/?(.+)\\/?$")

    def test_001_compile_pattern_star(self):
        regex, tokens = Router().patternToRegex("/:path*")
        self.assertEqual(regex.pattern, "^(?:\\/(.*)|\\/)?\\/?$")

    def test_001_compile_pattern_optional(self):
        regex, tokens = Router().patternToRegex("/:path?")
        self.assertEqual(regex.pattern, "^(?:\\/([^\\/]*)|\\/)?\\/?$")

    def test_001_compile_pattern_one(self):
        regex, tokens = Router().patternToRegex("/:path")
        self.assertEqual(regex.pattern, "^\\/([^\\/]+)\\/?$")

    def test_001_compile_pattern_static(self):
        regex, tokens = Router().patternToRegex("/path")
        self.assertEqual(regex.pattern, "^\\/path\\/?$")

    def test_001_router(self):
        router = Router()

        endpoints = [
            ('GET', '/a', lambda: 1),
            ('PUT', '/a/:b*', lambda: 2),
        ]
        router.registerEndpoints(endpoints)

        route = router.getRoute('GET', '/a')
        self.assertTrue(route is not None)
        callback, match = route
        self.assertEqual(match, {})

        route = router.getRoute('PUT', '/a/c/d')
        self.assertTrue(route is not None)
        callback, match = route
        self.assertEqual(match, {'b': 'c/d'})

def main():
    unittest.main()


if __name__ == '__main__':
    main()
