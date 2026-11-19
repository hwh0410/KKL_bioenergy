#!/usr/bin/env python3
"""C04 historical EIA vector inventory and PRIVATE source preview.

Coordinates: PyMuPDF get_drawings() uses the unrotated page coordinate
system. page.rotation_matrix converts to the displayed, rotated page.
This script NEVER assigns building/pool/road semantics automatically.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

import fitz

def xy(p):
    return [round(float(p.x), 5), round(float(p.y), 5)]

def transform(point, matrix):
    return xy(fitz.Point(*point) * matrix)

def inventory(pdf, page_numbers=(7, 8)):
    doc = fitz.open(pdf)
    result = {"source_sha256": hashlib.sha256(Path(pdf).read_bytes()).hexdigest(),
              "page_count": len(doc), "pages": []}
    for number in page_numbers:
        page = doc[number - 1]
        drawings = page.get_drawings()
        kinds = {}
        items = {}
        for drawing in drawings:
            kinds[drawing["type"]] = kinds.get(drawing["type"], 0) + 1
            for element in drawing["items"]:
                k = element[0]
                items[k] = items.get(k, 0) + 1
        result["pages"].append({
            "page": number,
            "figure": "4.2.2-1" if number == 7 else "4.2.2-2",
            "display_rect_pt": [round(float(t), 5) for t in page.rect],
            "unrotated_cropbox_pt": [round(float(t), 5) for t in page.cropbox],
            "rotation_degrees": page.rotation,
            "rotation_matrix": list(page.rotation_matrix),
            "drawing_groups": len(drawings),
            "drawing_types": dict(sorted(kinds.items())),
            "item_types": dict(sorted(items.items())),
            "drawing_items": sum(len(d["items"]) for d in drawings),
            "explicit_closepath_true_groups": sum(d.get("closePath") is True for d in drawings),
            "verified_semantic_closed_rings": 0,
            "classification": "unclassified_source_vectors",
            "registration": "not_georeferenced",
        })
    return result

def scale_calibration(args):
    points = [args.scale_x0, args.scale_y0, args.scale_x1, args.scale_y1]
    if all(v is None for v in points) and args.scale_m is None:
        return {"status": "not_measured", "metres_per_display_point": None}
    if any(v is None for v in points) or args.scale_m is None or args.scale_m <= 0:
        raise ValueError("Scale requires --scale-x0/y0/x1/y1 and positive --scale-m")
    dp = math.hypot(points[2] - points[0], points[3] - points[1])
    if dp <= 0:
        raise ValueError("Scale endpoints must differ")
    return {"status": "measured_endpoints_unverified", "endpoints_display_pt": points,
            "labelled_metres": args.scale_m,
            "display_points_per_metre": dp / args.scale_m,
            "metres_per_display_point": args.scale_m / dp,
            "uncertainty": "Requires independent endpoints and reproduction check"}

def export_private_preview(doc, page_number, out, dpi):
    """PRIVATE ONLY: source-derived SVG + bitmap, never commit to a public repo."""
    page = doc[page_number - 1]
    svg = page.get_svg_image(text_as_path=False)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"C04-p{page_number:02d}-PRIVATE.svg").write_text(svg, encoding="utf-8")
    pix = page.get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72), alpha=False)
    pix.save(str(out / f"C04-p{page_number:02d}-PRIVATE.png"))

def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--pdf", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--pages", type=int, nargs="+", default=[7, 8])
    p.add_argument("--scale-x0", type=float)
    p.add_argument("--scale-y0", type=float)
    p.add_argument("--scale-x1", type=float)
    p.add_argument("--scale-y1", type=float)
    p.add_argument("--scale-m", type=float)
    p.add_argument("--private-preview", action="store_true")
    p.add_argument("--dpi", type=int, default=144)
    args = p.parse_args(argv)
    if not args.pdf.is_file():
        p.error("C04.PDF not found. Provide private input via --pdf")
    if not all(1 <= n <= len(fitz.open(args.pdf)) for n in args.pages):
        p.error("Page outside PDF range")
    data = inventory(args.pdf, args.pages)
    data["scale_calibration"] = scale_calibration(args)
    data["qa_gate"] = {
        "geometry": "BLOCKED: no semantically verified footprints, roads, tanks or pool rings",
        "topology": "BLOCKED: PDF drawing groups are not original CAD entities",
        "historical_register": "EIA historical plan, NOT contemporary as-built",
        "publication": "Only aggregate counts approved here; source derivatives PRIVATE"
    }
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "inventory.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.private_preview:
        doc = fitz.open(args.pdf)
        for number in args.pages:
            export_private_preview(doc, number, args.out, args.dpi)
    print(json.dumps({"pages": args.pages, "qa": data["qa_gate"],
                      "output": str(args.out / "inventory.json")}, ensure_ascii=False))

if __name__ == "__main__":
    main()
