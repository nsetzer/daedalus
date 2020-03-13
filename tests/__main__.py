
import unittest

def main():
    verbose = 1
    pattern = '*'
    test_loader = unittest.defaultTestLoader
    test_runner = unittest.TextTestRunner(verbosity=verbose)
    pattern = pattern + "_test.py"
    test_suite = test_loader.discover("./tests", pattern=pattern)
    return test_runner.run(test_suite)


if __name__ == '__main__':
    main()
