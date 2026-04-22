import unittest
import test._test_multiprocessing

from test import support

if support.PGO:
    raise unittest.SkipTest("test is not helpful for PGO")

if support.is_apple_mobile:
    raise unittest.SkipTest("Can't use fork on Apple mobile")

test._test_multiprocessing.install_tests_in_module_dict(globals(), 'spawn')

if __name__ == '__main__':
    unittest.main()
