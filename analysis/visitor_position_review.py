#!/usr/bin/env python3
"""Create a private photo-to-plan position review from C04.PDF page 7.

This tool overlays existing *candidate* polygons on the source page for local
review. It never promotes them to engineering geometry and its outputs must
remain private while source reproduction rights are unresolved.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import fitz
from PIL import Image, ImageDraw, ImageFont


PAGE = 7
FIGURE = "4.2.2-1"
CROP_X0, CROP_Y0 = 112.0, 52.0
SOURCE_PX_PER_POINT = 2.0
SELECTED = {
    "福利大樓": ("#8e44ad", "plan_label"),
    "行政大樓": ("#1565c0", "plan_label"),
    "酒史館": ("#d84315", "plan_label"),
    "小型酒瓶展示設施": ("#455a64", "low_confidence_candidate"),
    "行政景觀廣場": ("#2e7d32", "landscape_candidate"),
    "迎賓水池圓形區": ("#ef6c00", "landmark_candidate"),
    "廠區大門": ("#6d4c41", "gate_candidate"),
}


def source_px_to_display_pt(point: list[float]) -> list[float]:
    """Invert V0.9.4's rendered crop: Rect(112,52,665,452), 2 px/point."""
    return [CROP_X0 + point[0] / SOURCE_PX_PER_POINT,
            CROP_Y0 + point[1] / SOURCE_PX_PER_POINT]


def iter_points(geometry: dict[str, Any]):
    def walk(value):
        if isinstance(value, list) and value and isinstance(value[0], (int, float)):
            yield value
        elif isinstance(value, list):
            for child in value:
                yield from walk(child)
    yield from walk(geometry.get("coordinates", []))


def feature_center(geometry: dict[str, Any]) -> list[float]:
    pts = [source_px_to_display_pt(p) for p in iter_points(geometry)]
    return [sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)]


def bezier(p: list[fitz.Point], t: float) -> fitz.Point:
    u = 1.0 - t
    return fitz.Point(
        u**3*p[0].x + 3*u*u*t*p[1].x + 3*u*t*t*p[2].x + t**3*p[3].x,
        u**3*p[0].y + 3*u*u*t*p[1].y + 3*u*t*t*p[2].y + t**3*p[3].y,
    )


def source_segments(page: fitz.Page, roi: tuple[float, float, float, float]):
    x0, y0, x1, y1 = roi
    for drawing_index, drawing in enumerate(page.get_drawings()):
        for item_index, item in enumerate(drawing["items"]):
            kind = item[0]
            points: list[fitz.Point] = []
            if kind == "l":
                points = [item[1] * page.rotation_matrix,
                          item[2] * page.rotation_matrix]
            elif kind == "c":
                points = [p * page.rotation_matrix for p in item[1:5]]
                points = [bezier(points, i / 24) for i in range(25)]
            elif kind == "qu":
                quad = item[1]
                points = [p * page.rotation_matrix
                          for p in (quad.ul, quad.ur, quad.lr, quad.ll, quad.ul)]
            elif kind == "re":
                rect = item[1] * page.rotation_matrix
                corners = [rect.tl, rect.tr, rect.br, rect.bl, rect.tl]
                points = corners
            for a, b in zip(points, points[1:]):
                if max(a.x, b.x) < x0 or min(a.x, b.x) > x1:
                    continue
                if max(a.y, b.y) < y0 or min(a.y, b.y) > y1:
                    continue
                yield (a.x, a.y), (b.x, b.y), f"{PAGE}:{drawing_index}:{item_index}"


def point_segment_distance(p, a, b) -> float:
    vx, vy = b[0] - a[0], b[1] - a[1]
    wx, wy = p[0] - a[0], p[1] - a[1]
    denom = vx * vx + vy * vy
    t = max(0.0, min(1.0, (wx * vx + wy * vy) / denom)) if denom else 0.0
    return math.hypot(p[0] - a[0] - t * vx, p[1] - a[1] - t * vy)


def sample_edge(a, b, step: float = 0.25):
    length = math.hypot(b[0] - a[0], b[1] - a[1])
    n = max(1, math.ceil(length / step))
    return [(a[0] + (b[0] - a[0]) * i / n,
             a[1] + (b[1] - a[1]) * i / n) for i in range(n + 1)]


def polygon_source_proximity(ring, segments):
    edges = list(zip(ring, ring[1:]))
    per_edge = []
    all_distances = []
    for edge_index, (a, b) in enumerate(edges):
        samples = sample_edge(a, b)
        distances = [min((point_segment_distance(p, x, y) for x, y, _ in segments),
                         default=float("inf")) for p in samples]
        all_distances.extend(distances)
        per_edge.append({
            "edge_index": edge_index,
            "sample_count": len(samples),
            "supported_fraction_within_0_5_display_pt": round(
                sum(d <= 0.5 for d in distances) / len(distances), 4),
            "median_offset_display_pt": round(sorted(distances)[len(distances)//2], 4),
            "p95_offset_display_pt": round(sorted(distances)[int(len(distances)*0.95)], 4),
        })
    ordered = sorted(all_distances)
    return {
        "sample_spacing_display_pt": 0.25,
        "candidate_boundary_sample_count": len(ordered),
        "source_segment_count_in_local_window": len(segments),
        "supported_fraction_within_0_5_display_pt": round(
            sum(d <= 0.5 for d in ordered) / max(1, len(ordered)), 4),
        "median_offset_display_pt": round(ordered[len(ordered)//2], 4),
        "p95_offset_display_pt": round(ordered[int(len(ordered)*0.95)], 4),
        "edge_metrics": per_edge,
        "note": "Nearest-segment distance diagnostic; it does not identify a unique boundary or prove semantic identity.",
    }


def load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for candidate in (
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    ):
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size=size)
    return ImageFont.load_default()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pdf", required=True, type=Path)
    ap.add_argument("--candidates", required=True, type=Path,
                    help="V0.9.4 candidate GeoJSON in crop-pixel coordinates")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--axial-endpoint", nargs=2, required=True, type=float,
                    metavar=("DISPLAY_X", "DISPLAY_Y"),
                    help="private manual candidate point in rotated page display points")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    with args.pdf.open("rb") as stream:
        pdf = fitz.open(stream=stream.read(), filetype="pdf")
    page = pdf[PAGE - 1]
    scale = SOURCE_PX_PER_POINT
    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
    base = Image.frombytes("RGB", (pix.width, pix.height), pix.samples).convert("RGBA")
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    font = load_font(18)

    candidates = json.loads(args.candidates.read_text(encoding="utf-8"))
    by_name = {f["properties"].get("name"): f for f in candidates["features"]}
    output_features = []
    audit = []

    for name, (color, role) in SELECTED.items():
        feature = by_name.get(name)
        if not feature:
            audit.append({"name": name, "included": False, "reason": "candidate missing"})
            continue
        geo = feature["geometry"]
        props = feature["properties"]
        rgb = tuple(bytes.fromhex(color.lstrip("#")))
        converted = [source_px_to_display_pt(p) for p in iter_points(geo)]
        if geo["type"] == "Polygon":
            ring = geo["coordinates"][0]
            xy = [(round(SOURCE_PX_PER_POINT * x), round(SOURCE_PX_PER_POINT * y))
                  for x, y in (source_px_to_display_pt(p) for p in ring)]
            draw.line(xy + [xy[0]], fill=(*rgb, 235), width=4, joint="curve")
            center = feature_center(geo)
        elif geo["type"] == "Point":
            center = source_px_to_display_pt(geo["coordinates"])
            xy = (round(center[0] * scale), round(center[1] * scale))
            r = 12
            draw.ellipse((xy[0]-r, xy[1]-r, xy[0]+r, xy[1]+r),
                         outline=(*rgb, 245), width=4)
        else:
            center = feature_center(geo)
        display_label = "廠史館／酒史館" if name == "酒史館" else name
        x, y = round(center[0] * scale), round(center[1] * scale)
        draw.rounded_rectangle((x+8, y-26, x+220, y+2), radius=4,
                               fill=(255, 255, 255, 225))
        draw.text((x+12, y-25), display_label, font=font, fill=(*rgb, 255),
                  stroke_width=0)
        audit.append({
            "name": name,
            "included": True,
            "role": role,
            "candidate_status": props.get("status"),
            "review_required": props.get("review_required", True),
            "candidate_source": props.get("source_geometry_quality"),
            "center_page7_display_pt": [round(center[0], 3), round(center[1], 3)],
            "note": "Overlay only; candidate outline is not snapped or accepted.",
        })
        if geo["type"] == "Polygon":
            display_ring = [source_px_to_display_pt(p) for p in geo["coordinates"][0]]
            local_roi = (
                min(p[0] for p in display_ring) - 8,
                min(p[1] for p in display_ring) - 8,
                max(p[0] for p in display_ring) + 8,
                max(p[1] for p in display_ring) + 8,
            )
            local_segments = list(source_segments(page, local_roi))
            audit[-1]["vector_boundary_proximity"] = polygon_source_proximity(
                display_ring, local_segments)
        if geo["type"] == "Polygon":
            coords = [[source_px_to_display_pt(p) for p in ring]
                      for ring in geo["coordinates"]]
            output_geometry = {"type": "Polygon", "coordinates": coords}
        else:
            output_geometry = {
                "type": geo["type"],
                "coordinates": [source_px_to_display_pt(geo["coordinates"])]
                if geo["type"] == "Point"
                else geo["coordinates"],
            }
        output_features.append({
            "type": "Feature",
            "id": f"p7-candidate-{name}",
            "properties": {
                "name": name,
                "classification": "candidate",
                "source_page": PAGE,
                "source_figure": FIGURE,
                "source_coordinate_system": "V0.9.4 crop pixels; Rect(112,52,665,452), 2 px/pt",
                "output_coordinate_system": "C04 page 7 rotated display points",
                "source_feature_id": feature.get("id"),
                "review_required": True,
                "engineering_geometry": False,
            },
            "geometry": output_geometry,
        })

    # The lower circular node is identified from the source drawing and EIA
    # narrative as the axial endpoint; its center is a manual visual candidate.
    bao_yue = list(args.axial_endpoint)
    x, y = [round(v * scale) for v in bao_yue]
    orange = (239, 108, 0)
    draw.ellipse((x-12, y-12, x+12, y+12), outline=(*orange, 245), width=4)
    draw.rounded_rectangle((x+10, y+7, x+210, y+36), radius=4,
                           fill=(255, 255, 255, 225))
    draw.text((x+14, y+8), "寶月新泉？端點候選", font=font,
              fill=(*orange, 255))
    # Label the central S-shaped pedestrian feature without tracing it as
    # accepted geometry. Its centerline is only indicated by a callout.
    walkway_anchor = (round(330 * scale), round(295 * scale))
    label_anchor = (round(380 * scale), round(305 * scale))
    draw.line([walkway_anchor, label_anchor], fill=(30, 90, 160, 230), width=3)
    draw.rounded_rectangle((label_anchor[0], label_anchor[1] - 24,
                            label_anchor[0] + 230, label_anchor[1] + 6),
                           radius=4, fill=(255, 255, 255, 225))
    draw.text((label_anchor[0] + 6, label_anchor[1] - 23),
              "曲水流觴步道（使用者確認）", font=font,
              fill=(30, 90, 160, 255))
    output_features.append({
        "type": "Feature",
        "id": "p7-axial-endpoint-candidate",
        "properties": {
            "name": "寶月新泉",
            "classification": "candidate_visual_reference_only",
            "source_page": PAGE,
            "source_figure": FIGURE,
            "output_coordinate_system": "C04 page 7 rotated display points",
            "source_coordinate": "manual visual pick; source-path IDs not assigned",
            "review_required": True,
            "engineering_geometry": False,
        },
        "geometry": {"type": "Point", "coordinates": bao_yue},
    })
    audit.append({
        "name": "寶月新泉",
        "included": True,
        "role": "axial_endpoint_candidate",
        "center_page7_display_pt": bao_yue,
        "note": "Manual visual pick of lower circular node; not yet source-snapped.",
    })

    result = Image.alpha_composite(base, overlay).convert("RGB")
    result.save(args.out / "C04-p07-visitor-location-review-PRIVATE.png")
    (args.out / "visitor-location-candidates-PRIVATE.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "name": "Private page-7 location candidates",
                    "crs": {"type": "name", "properties": {"name": "C04 page-7 display points"}},
                    "features": output_features}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (args.out / "visitor-location-review-PRIVATE.json").write_text(
        json.dumps({
            "title": "金寧廠遊客設施位置初步對位",
            "source": {"pdf_page": PAGE, "figure": FIGURE,
                      "source_pdf_sha256": hashlib.sha256(args.pdf.read_bytes()).hexdigest()},
            "coordinate_system": {
                "type": "C04 page-7 rotated display points",
                "metres_per_point": 1.03199256,
                "not_georeferenced": True,
                "manual_pick_uncertainty": "not quantified; candidate only",
            },
            "photo_crosswalk": [
                {"photo_order": 1, "user_label": "迎賓水池", "plan_match": "upper circular focal basin", "status": "strong visual match"},
                {"photo_order": 2, "user_label": "寶月新泉", "plan_match": "lower circular axial endpoint", "status": "candidate; snapped control still required"},
                {"photo_order": 3, "user_label": "酒瓶公園", "plan_match": "landscape zone southeast of visitor axis near administration", "status": "candidate"},
                {"photo_order": 4, "user_label": "金酒生活館", "plan_match": "not explicitly named on figure 4.2.2-1", "status": "unmatched; footprint not assigned"},
                {"photo_order": 5, "user_label": "廠史館", "plan_match": "the small pavilion labeled 酒史館 on figure 4.2.2-1", "status": "user-confirmed same location; name variant"},
                {"photo_order": 6, "user_label": "行政大樓", "plan_match": "行政大樓 label and footprint on page 7", "status": "strong semantic match; candidate outline"},
                {"photo_order": 7, "user_label": "酒瓶地標", "plan_match": "near the south gate / bottle display candidate zone", "status": "candidate; exact symbol not confirmed on plan"},
            ],
            "checks": audit,
            "interpretation": {
                "S_shaped_feature": "walkway / 曲水流觴 per user clarification; do not classify as water contour",
                "source_status": "No candidate promoted to verified engineering geometry.",
                "S_walkway_note": "The S-shaped feature is labeled as 曲水流觴步道 by the user; the PDF and this pass do not prove a closed water contour.",
                "official_location_map": "User-supplied official site map confirms 廠史館 and 酒史館 refer to the same mapped location. Used for semantic/topological correspondence only; not used as a metric scale or coordinate transform.",
                "photo_method": "Photographs are used for feature identity and adjacency, not scale or footprint measurement.",
                "publication": "Private only; contains a source-page overlay.",
            },
        }, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
