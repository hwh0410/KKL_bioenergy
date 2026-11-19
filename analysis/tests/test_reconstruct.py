import importlib.util
import pathlib
import unittest

import fitz

MODULE = pathlib.Path(__file__).resolve().parents[1] / "c04_reconstruct.py"
spec = importlib.util.spec_from_file_location("c04_reconstruct", MODULE)
reconstruct = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reconstruct)
REGISTRATION = pathlib.Path(__file__).resolve().parents[1] / "register_pages.py"
reg_spec = importlib.util.spec_from_file_location("register_pages", REGISTRATION)
registration = importlib.util.module_from_spec(reg_spec)
reg_spec.loader.exec_module(registration)
ZONES = pathlib.Path(__file__).resolve().parents[1] / "classify_expansion_zones.py"
zones_spec = importlib.util.spec_from_file_location("classify_expansion_zones", ZONES)
zones = importlib.util.module_from_spec(zones_spec)
zones_spec.loader.exec_module(zones)


class TestSourceGeometry(unittest.TestCase):
    def test_scale_bar_calibration_matches_measured_vector_span(self):
        s = reconstruct.scale_data([[10, 20], [110, 20]], 60)
        self.assertAlmostEqual(s["measured_span_pt"], 100.0, places=4)
        self.assertAlmostEqual(s["metres_per_display_point"], 0.6, places=5)
        self.assertGreater(s["estimated_scale_uncertainty_percent"], 0)

    def test_rotation_and_y_axis_conversion(self):
        page = fitz.open()
        page.new_page(width=842, height=595)
        # The exported site coordinates are x-right, y-up, relative to page bottom-left.
        geom, coords = reconstruct.geometry_for_item(
            ("l", fitz.Point(100, 200), fitz.Point(120, 220)),
            fitz.Matrix(1, 0, 0, 1, 0, 0), (0, 595), 1, 4)
        self.assertEqual(geom, "LineString")
        self.assertEqual(coords, [[100, 395], [120, 375]])

    def test_bezier_export_preserves_control_points_in_svg(self):
        item = ("c", fitz.Point(0, 0), fitz.Point(1, 2), fitz.Point(3, 2), fitz.Point(4, 0))
        d = reconstruct.svg_path(item, fitz.Identity)
        self.assertEqual(d, "M 0.0000,0.0000 C 1.0000,2.0000 3.0000,2.0000 4.0000,0.0000")

    def test_reconstruction_never_promotes_unreviewed_features(self):
        # Unknown is the default; semantics require separate review/QA.
        self.assertIsNone(reconstruct.scale_data()["metres_per_display_point"])

    def test_registration_has_four_valid_manual_windows(self):
        self.assertEqual(len(registration.CONTROL_WINDOWS), 4)
        for x0, y0, x1, y1 in registration.CONTROL_WINDOWS:
            self.assertLess(x0, x1)
            self.assertLess(y0, y1)
            self.assertGreaterEqual(x0, 0)
            self.assertLessEqual(x1, 842)

    def test_expansion_color_keys_follow_legend_palette(self):
        self.assertTrue(zones.rgb_close(zones.A_GREEN, (0.0, 0.765, 0.0)))
        self.assertTrue(zones.rgb_close(zones.B_GRAY, (0.725, 0.725, 0.725)))
        self.assertTrue(zones.rgb_close(zones.C_RED, (1.0, 0.0, 0.0)))
        self.assertFalse(zones.rgb_close((0.1, 0.1, 0.1), zones.A_GREEN))


if __name__ == "__main__":
    unittest.main()
