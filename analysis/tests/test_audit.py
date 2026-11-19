import importlib.util
import pathlib
import unittest
import fitz

PATH = pathlib.Path(__file__).resolve().parents[1] / "c04_audit.py"
spec = importlib.util.spec_from_file_location("c04_audit", PATH)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)

class TestCoordinateAndScale(unittest.TestCase):
    def test_display_rotation(self):
        matrix = fitz.Matrix(0, 1, -1, 0, 842, 0)
        self.assertEqual(audit.transform((0, 0), matrix), [842, 0])
        self.assertEqual(audit.transform((100, 200), matrix), [642, 100])
    def test_missing_scale_never_invented(self):
        class A: pass
        args = A()
        for key in ("scale_x0", "scale_y0", "scale_x1", "scale_y1", "scale_m"):
            setattr(args, key, None)
        self.assertEqual(audit.scale_calibration(args)["status"], "not_measured")
    def test_scale_requires_endpoints(self):
        class A: pass
        args=A()
        args.scale_x0=0
        args.scale_y0=0
        args.scale_x1=100
        args.scale_y1=0
        args.scale_m=50
        self.assertAlmostEqual(audit.scale_calibration(args)["metres_per_display_point"], 0.5)

if __name__ == "__main__":
    unittest.main()
