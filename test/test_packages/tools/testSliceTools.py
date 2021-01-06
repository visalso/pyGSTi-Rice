from ..testutils import BaseTestCase, compare_files, temp_files
import unittest

from pygsti.tools.slicetools import *

N = 100
slices = []
for i in range(1, N):
    for j in range(1, N):
        for k in [1, 2]:
            slices.append(slice(i, j, k))

class SliceToolsBaseTestCase(BaseTestCase):
    def test_length(self):
        for s in slices:
            length(s)
        self.assertEqual(length(slice(10)), 0)
        self.assertEqual(length(slice(1, 10)), 9)

    def test_indices(self):
        for s in slices:
            indices(s)
        indices(slice(10))

    def test_intersect(self):
        intersect(slice(None, 10, 1), slice(1, 10, 1))
        intersect(slice(1, 10, 1),    slice(None, 10, 1))
        intersect(slice(1, None, 1),  slice(1, 10, 1))

    def test_list_to_slice(self):
        self.assertEqual(list_to_slice([]), slice(0, 0))
        self.assertEqual(list_to_slice([1, 2, 3, 4]), slice(1, 5))

if __name__ == '__main__':
    unittest.main(verbosity=2)
