import unittest
import importlib.util
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / "visitor_position_review.py"
spec = importlib.util.spec_from_file_location("visitor_position_review", MODULE)
review = importlib.util.module_from_spec(spec)
spec.loader.exec_module(review)

point_segment_distance = review.point_segment_distance
sample_edge = review.sample_edge
source_px_to_display_pt = review.source_px_to_display_pt


class VisitorPositionReviewTests(unittest.TestCase):
    def test_crop_pixel_to_rotated_display_point(self):
        self.assertEqual(source_px_to_display_pt([0, 0]), [112.0, 52.0])
        self.assertEqual(source_px_to_display_pt([100, 80]), [162.0, 92.0])

    def test_point_segment_distance_projects_to_segment(self):
        self.assertAlmostEqual(point_segment_distance((2, 3), (0, 0), (4, 0)), 3.0)

    def test_point_segment_distance_clamps_to_endpoint(self):
        self.assertAlmostEqual(point_segment_distance((5, 0), (0, 0), (4, 0)), 1.0)

    def test_zero_length_segment(self):
        self.assertAlmostEqual(point_segment_distance((3, 4), (0, 0), (0, 0)), 5.0)

    def test_edge_sampling_includes_both_endpoints(self):
        self.assertEqual(sample_edge((0, 0), (1, 0), step=0.4),
                         [(0.0, 0.0), (1 / 3, 0.0), (2 / 3, 0.0), (1.0, 0.0)])


if __name__ == "__main__":
    unittest.main()
