import importlib.util
import math
from pathlib import Path
import unittest

import numpy as np

MODULE = Path(__file__).resolve().parents[1] / "smooth_pdf_curves.py"
spec = importlib.util.spec_from_file_location("smooth_pdf_curves", MODULE)
smooth = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smooth)


class SmoothCurveTests(unittest.TestCase):
    def test_circle_fragments_fit_one_arc_within_tolerance(self):
        angle = np.linspace(0.15, 2.1, 31)
        pts = np.column_stack((40 + 18*np.cos(angle), 25 + 18*np.sin(angle)))
        fit = smooth.fit_chain({"points": pts, "source_refs": [str(i) for i in range(30)]}, 0.35)
        self.assertIsNotNone(fit)
        self.assertEqual(fit["kind"], "arc")
        self.assertLessEqual(fit["error"], 0.35)

    def test_straight_fragments_are_not_converted_to_splines(self):
        pts = np.column_stack((np.linspace(0, 10, 20), np.zeros(20)))
        fit = smooth.fit_chain({"points": pts, "source_refs": [str(i) for i in range(19)]}, 0.35)
        self.assertIsNone(fit)

    def test_cubic_bezier_fragments_recover_as_cubic(self):
        ctrl = np.array([[0., 0.], [2., 8.], [9., 8.], [11., 0.]])
        pts = smooth.cubic_points(ctrl, 40)
        fit = smooth.fit_chain({"points": pts, "source_refs": [str(i) for i in range(40)]}, 0.35)
        self.assertIsNotNone(fit)
        self.assertEqual(fit["kind"], "cubic")
        self.assertLessEqual(fit["error"], 0.35)

    def test_fitted_curve_keeps_source_endpoints(self):
        angle = np.linspace(0.1, 1.7, 15)
        pts = np.column_stack((10*np.cos(angle), 10*np.sin(angle)))
        fit = smooth.fit_chain({"points": pts, "source_refs": [str(i) for i in range(14)]}, 0.35)
        self.assertIsNotNone(fit)
        self.assertTrue(np.allclose(pts[0], [10*np.cos(.1), 10*np.sin(.1)]))
        self.assertTrue(np.allclose(pts[-1], [10*np.cos(1.7), 10*np.sin(1.7)]))


if __name__ == "__main__":
    unittest.main()
