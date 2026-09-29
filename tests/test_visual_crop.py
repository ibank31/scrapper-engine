#!/usr/bin/env python3
"""Face-tracked crop deadzone regression tests.

Without a deadzone, tiny detection jitter makes the crop wander every frame,
which screams "auto-crop". The deadzone holds the crop steady until the face
moves a meaningful distance, then follows.
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from core.visual_crop import _apply_deadzone


class DeadzoneTests(unittest.TestCase):
    def test_small_jitter_is_held_steady(self):
        centers = [(500.0, 400.0), (502.0, 401.0), (498.0, 399.0), (501.0, 400.5), (499.5, 400.0)]
        result = _apply_deadzone(centers, deadzone_px=20.0)
        for point in result:
            self.assertEqual(point, (500.0, 400.0))

    def test_large_move_is_followed(self):
        centers = [(500.0, 400.0), (502.0, 401.0), (650.0, 400.0), (652.0, 402.0)]
        result = _apply_deadzone(centers, deadzone_px=20.0)
        self.assertEqual(result[0], (500.0, 400.0))
        self.assertEqual(result[2], (650.0, 400.0))
        # small move after the jump stays held at the new anchor
        self.assertEqual(result[3], (650.0, 400.0))

    def test_exact_deadzone_boundary_moves(self):
        centers = [(0.0, 0.0), (20.0, 0.0)]
        result = _apply_deadzone(centers, deadzone_px=20.0)
        self.assertEqual(result[1], (20.0, 0.0))

    def test_vertical_and_horizontal_are_independent(self):
        centers = [(500.0, 400.0), (500.0, 450.0)]
        result = _apply_deadzone(centers, deadzone_px=20.0)
        self.assertEqual(result[1], (500.0, 450.0))

    def test_empty_input(self):
        self.assertEqual(_apply_deadzone([], deadzone_px=20.0), [])

    def test_zero_deadzone_passes_through(self):
        centers = [(500.0, 400.0), (502.0, 401.0)]
        self.assertEqual(_apply_deadzone(centers, deadzone_px=0.0), centers)


if __name__ == "__main__":
    unittest.main()
