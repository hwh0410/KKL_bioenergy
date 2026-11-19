#!/usr/bin/env python3
"""Private, source-indexed reconstruction of C04 PDF vector primitives.

This tool exports drawing primitives as editable SVG, GeoJSON and DXF, but
does not infer engineering semantics from PDF drawing groups. All exported
features remain ``unknown`` until reviewed against the page image.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from pathlib import Path

import fitz

try:
    from shapely.geometry import LineString, Polygon
except ImportError:  # optional geometry topology checks
    LineString = Polygon = None

def pt(p, matrix):
    q = fitz.Point(p) * matrix
    return float(q.x), float(q.y)


def item_points(item, matrix):
    kind = item[0]
    if kind == "l":
        return [pt(item[1], matrix), pt(item[2], matrix)]
    if kind == "c":
        return [pt(p, matrix) for p in item[1:5]]
    if kind == "re":
        r = item[1]
        corners = [(r.x0, r.y0), (r.x1, r.y0), (r.x1, r.y1), (r.x0, r.y1)]
        return [pt(p, matrix) for p in corners]
    if kind == "qu":
        q = item[1]
        return [pt(p, matrix) for p in (q.ul, q.ur, q.lr, q.ll)]
    return []


def scale_data(endpoints=None, labelled_length_m=None, endpoint_uncertainty_pt_each=0.10):
    if endpoints is None or labelled_length_m is None:
        return {"status":"not_measured","metres_per_display_point":None,
                "note":"Supply graphic-scale endpoints after private source inspection."}
    a, b = endpoints
    span = math.dist(a, b)
    m_per_pt = labelled_length_m / span
    # Conservative propagation of independent endpoint placement uncertainty.
    u = endpoint_uncertainty_pt_each
    span_uncertainty = math.sqrt(2) * u
    rel_u = span_uncertainty / span
    return {
        "status":"measured_endpoints_user_supplied",
        "display_endpoints_pt":endpoints,
        "labelled_length_m":labelled_length_m,
        "endpoint_uncertainty_pt_each":endpoint_uncertainty_pt_each,
        "measured_span_pt": span,
        "metres_per_display_point": m_per_pt,
        "metres_per_pixel_at_2px_per_point": m_per_pt / 2,
        "estimated_scale_uncertainty_fraction": rel_u,
        "estimated_scale_uncertainty_percent": rel_u * 100,
        "estimated_metres_per_point_interval": [m_per_pt * (1-rel_u), m_per_pt * (1+rel_u)],
        "basis": "PDF vector segment, page.rotation_matrix applied; 60 m graphic scale bar",
        "limitations": "Endpoint uncertainty is a conservative manual/vector-stroke bound; not survey accuracy or legal engineering tolerance.",
        "comparison_to_previous_provisional_m_per_pixel_0_51724": {
            "difference_m_per_pixel": m_per_pt / 2 - 0.51724,
            "relative_difference_percent": ((m_per_pt / 2) / 0.51724 - 1) * 100,
        },
    }


def geometry_for_item(item, matrix, origin, m_per_pt, curve_steps=16):
    kind = item[0]
    coords = item_points(item, matrix)
    def conv(p):
        # CAD-style local coordinates: x right, y up; no geodetic datum.
        return [(p[0] - origin[0]) * m_per_pt, (origin[1] - p[1]) * m_per_pt]
    if kind == "l":
        return "LineString", [conv(p) for p in coords]
    if kind == "c":
        p0, p1, p2, p3 = coords
        sampled = []
        for i in range(curve_steps + 1):
            t = i / curve_steps
            mt = 1-t
            sampled.append((mt**3*p0[0] + 3*mt**2*t*p1[0] + 3*mt*t**2*p2[0] + t**3*p3[0],
                            mt**3*p0[1] + 3*mt**2*t*p1[1] + 3*mt*t**2*p2[1] + t**3*p3[1]))
        return "LineString", [conv(p) for p in sampled]
    if kind in ("re", "qu"):
        return "Polygon", [[conv(p) for p in coords + [coords[0]]]]
    return None, None


def svg_path(item, matrix):
    kind = item[0]
    p = item_points(item, matrix)
    f = lambda q: f"{q[0]:.4f},{q[1]:.4f}"
    if kind == "l":
        return f"M {f(p[0])} L {f(p[1])}"
    if kind == "c":
        return f"M {f(p[0])} C {f(p[1])} {f(p[2])} {f(p[3])}"
    if kind in ("re", "qu"):
        return "M " + " L ".join(f(q) for q in p) + " Z"
    return ""


def cubic_error_pt(ctrl, steps):
    """Estimate maximum curve-to-chord error using 8x denser independent samples."""
    p0,p1,p2,p3=ctrl
    def value(t):
        mt=1-t
        return (mt**3*p0[0]+3*mt**2*t*p1[0]+3*mt*t*t*p2[0]+t**3*p3[0],
                mt**3*p0[1]+3*mt**2*t*p1[1]+3*mt*t*t*p2[1]+t**3*p3[1])
    def point_segment_distance(p,a,b):
        dx=b[0]-a[0];dy=b[1]-a[1]
        if dx==dy==0:return math.dist(p,a)
        f=max(0,min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/(dx*dx+dy*dy)))
        return math.hypot(p[0]-a[0]-f*dx,p[1]-a[1]-f*dy)
    maximum=0.0
    dense=steps*8
    for i in range(dense+1):
        t=i/dense; p=value(t); j=min(steps-1,int(t*steps)); maximum=max(maximum,point_segment_distance(p,value(j/steps),value((j+1)/steps)))
    return maximum


def build_page(page, page_number, scale, out_dir, curve_steps, endpoint_tol_pt, pdf_sha):
    drawings = page.get_drawings()
    rot = page.rotation_matrix
    display = page.rect
    origin = (float(display.x0), float(display.y1))
    m_per_pt=scale.get("metres_per_display_point") or 1.0
    coord_unit="metre_scaled_from_page_bar" if scale.get("metres_per_display_point") else "display_point"
    features, path_svg = [], []
    type_counts, group_stats = Counter(), []
    topology={"shapely_available":LineString is not None,"closed_continuous_line_curve_chains":0,
              "simple_closed_line_curve_chains":0,"self_intersecting_closed_line_curve_chains":0,
              "closed_primitive_polygons":0,"valid_closed_primitive_polygons":0,
              "self_intersecting_or_invalid_primitive_polygons":0}
    curve_errors_pt=[]
    endpoints = []
    minx=miny=float("inf"); maxx=maxy=float("-inf")
    for di, drawing in enumerate(drawings):
        starts_ends=[]; chain_coords=[]; chain_kinds=[]
        for ii, item in enumerate(drawing["items"]):
            kind=item[0]; type_counts[kind]+=1
            coords=item_points(item,rot)
            if not coords: continue
            minx=min(minx,*(q[0] for q in coords)); maxx=max(maxx,*(q[0] for q in coords))
            miny=min(miny,*(q[1] for q in coords)); maxy=max(maxy,*(q[1] for q in coords))
            if kind in ("l","c"):
                starts_ends.append((coords[0],coords[-1],ii))
                chain_kinds.append(kind)
                if kind=="l": chain_coords.extend(coords if not chain_coords else coords[1:])
                else:
                    sampled=[]
                    p0,p1,p2,p3=coords
                    for sj in range(curve_steps+1):
                        t=sj/curve_steps;mt=1-t
                        sampled.append((mt**3*p0[0]+3*mt**2*t*p1[0]+3*mt*t*t*p2[0]+t**3*p3[0],mt**3*p0[1]+3*mt**2*t*p1[1]+3*mt*t*t*p2[1]+t**3*p3[1]))
                    chain_coords.extend(sampled if not chain_coords else sampled[1:])
                    curve_errors_pt.append(cubic_error_pt(coords,curve_steps))
            elif kind in ("re","qu"):
                starts_ends.append((coords[0],coords[0],ii))
                if Polygon is not None:
                    ring=Polygon(coords)
                    topology["closed_primitive_polygons"]+=1
                    topology["valid_closed_primitive_polygons"]+=int(ring.is_valid)
                    topology["self_intersecting_or_invalid_primitive_polygons"]+=int(not ring.is_valid)
            gtype,gcoords=geometry_for_item(item,rot,origin,m_per_pt,curve_steps)
            ref=f"{page_number}:{di}:{ii}"
            if gtype:
                features.append({"type":"Feature","id":ref,"geometry":{"type":gtype,"coordinates":gcoords},"properties":{
                    "source_ref":ref,"page":page_number,"figure":"4.2.2-1" if page_number==7 else "4.2.2-2",
                    "drawing_index":di,"item_index":ii,"primitive":kind,"classification":"unknown",
                    "accuracy":"source_vector_geometry; semantic_identity_unverified",
                    "coordinate_unit":coord_unit,"crs":None,
                    "source_control":{"pdf_sha256":pdf_sha,"drawing_closepath":drawing.get("closePath")},
                    "display_points":coords,"curve_control_points_display":coords if kind=="c" else None,
                    "tessellation_steps":curve_steps if kind=="c" else None,
                }})
            path_svg.append(f'<path id="src-{page_number}-{di}-{ii}" data-source-ref="{ref}" data-classification="unknown" d="{svg_path(item,rot)}"/>')
        # Endpoint continuity is assessed only within one original drawing group.
        gaps=[]
        for left,right in zip(starts_ends,starts_ends[1:]):
            gap=math.dist(left[1],right[0])
            if gap > endpoint_tol_pt: gaps.append({"after_item":left[2],"before_item":right[2],"gap_display_pt":gap})
        closed=bool(starts_ends) and math.dist(starts_ends[0][0],starts_ends[-1][1]) <= endpoint_tol_pt
        if len(chain_coords)>=4 and len(chain_kinds)>=3 and not gaps and math.dist(chain_coords[0],chain_coords[-1])<=endpoint_tol_pt:
            topology["closed_continuous_line_curve_chains"]+=1
            if LineString is not None:
                simple=LineString(chain_coords).is_simple
                topology["simple_closed_line_curve_chains"]+=int(simple)
                topology["self_intersecting_closed_line_curve_chains"]+=int(not simple)
        group_stats.append({"drawing_index":di,"item_count":len(drawing["items"]),"explicit_closepath":drawing.get("closePath") is True,
                            "endpoint_chain_closed_by_tolerance":closed,"inter_item_gaps_over_tolerance":len(gaps),"largest_reported_gaps_pt":sorted((g["gap_display_pt"] for g in gaps),reverse=True)[:5]})
        endpoints.extend([e[0] for e in starts_ends]+[e[1] for e in starts_ends])
    safe = out_dir / f"C04-p{page_number:02d}-PRIVATE"
    safe.mkdir(parents=True,exist_ok=True)
    width,height=float(display.width),float(display.height)
    svg=(f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" '
         f'width="{width:.3f}pt" height="{height:.3f}pt" viewBox="0 0 {width:.5f} {height:.5f}">\n'
         '<metadata>PRIVATE source-derived PDF vector extraction. All features semantically unknown; not an accepted engineering drawing.</metadata>\n'
         '<g id="source-vectors" fill="none" stroke="#202020" stroke-width="0.25" stroke-linecap="round" stroke-linejoin="round">\n'
         +"\n".join(path_svg)+"\n</g></svg>\n")
    (safe/f"page-{page_number}.svg").write_text(svg,encoding="utf-8")
    geo={"type":"FeatureCollection","name":f"C04 page {page_number} source geometry private",
         "metadata":{"source":"C04.PDF historical EIA","page":page_number,"sha256":pdf_sha,"scale":scale,
                     "coordinate_system":"local scaled drawing coordinates; x right / y up; not georeferenced",
                     "release_status":"PRIVATE; publication/reproduction permission unverified","all_semantics":"unknown"},"features":features}
    (safe/f"page-{page_number}.geojson").write_text(json.dumps(geo,ensure_ascii=False,separators=(",",":"))+"\n",encoding="utf-8")
    dxf_path=safe/f"page-{page_number}.dxf"
    try:
        import ezdxf
        from ezdxf.enums import TextEntityAlignment
        doc=ezdxf.new("R2013"); msp=doc.modelspace()
        layers={"l":"SOURCE_LINE_UNKNOWN","c":"SOURCE_CURVE_UNKNOWN","re":"SOURCE_RECT_UNKNOWN","qu":"SOURCE_QUAD_UNKNOWN"}
        for name in layers.values(): doc.layers.new(name)
        for di,drawing in enumerate(drawings):
            for ii,item in enumerate(drawing["items"]):
                kind=item[0]; coords=item_points(item,rot)
                if not coords: continue
                xycoords=[((p[0]-origin[0])*m_per_pt,(origin[1]-p[1])*m_per_pt) for p in coords]
                layer=layers.get(kind,"SOURCE_UNKNOWN")
                if kind=="l": msp.add_line(xycoords[0],xycoords[1],dxfattribs={"layer":layer})
                elif kind=="c":
                    pts=[]
                    p0,p1,p2,p3=xycoords
                    for j in range(curve_steps+1):
                        t=j/curve_steps; mt=1-t
                        pts.append((mt**3*p0[0]+3*mt**2*t*p1[0]+3*mt*t**2*p2[0]+t**3*p3[0],mt**3*p0[1]+3*mt**2*t*p1[1]+3*mt*t**2*p2[1]+t**3*p3[1]))
                    msp.add_lwpolyline(pts,dxfattribs={"layer":layer})
                elif kind in ("re","qu"):
                    msp.add_lwpolyline(xycoords,close=True,dxfattribs={"layer":layer})
        doc.header["$INSUNITS"]=6 if scale.get("metres_per_display_point") else 0
        doc.saveas(dxf_path)
    except ImportError:
        dxf_path=None
    report={"page":page_number,"figure":"4.2.2-1" if page_number==7 else "4.2.2-2","rotation_degrees":page.rotation,
        "rotation_matrix":list(page.rotation_matrix),"display_rect_pt":[0,0,width,height],"drawing_groups":len(drawings),
        "drawing_items":sum(len(d["items"]) for d in drawings),"primitive_counts":dict(type_counts),"source_feature_count":len(features),
        "drawing_groups_with_true_closepath":sum(d.get("closePath") is True for d in drawings),
        "groups_closed_by_endpoint_tolerance":sum(g["endpoint_chain_closed_by_tolerance"] for g in group_stats),
        "endpoint_tolerance_display_pt":endpoint_tol_pt,"inter_item_gaps_over_tolerance":sum(g["inter_item_gaps_over_tolerance"] for g in group_stats),
        "group_qa":group_stats,"display_bounds_of_vectors_pt":[minx,miny,maxx,maxy],"scale":scale,
        "topology_checks":topology,
        "dxf_curve_tessellation":{"steps_per_cubic":curve_steps,"maximum_sampled_curve_to_chord_deviation_pt":max(curve_errors_pt,default=0),
            "maximum_sampled_curve_to_chord_deviation_m":max(curve_errors_pt,default=0)*m_per_pt,
            "curve_count":len(curve_errors_pt),"note":"Empirical dense-sample bound for DXF polyline conversion; SVG keeps exact cubic Bezier commands."},
        "classification_counts":{"verified_source":0,"candidate":0,"unknown":len(features)},
        "topology_note":"PDF drawing groups are not CAD objects. Endpoint closure count is a topological diagnostic only and does not verify semantics, intersections, or boundary continuity.",
        "files":{"svg":str(safe/f"page-{page_number}.svg"),"geojson":str(safe/f"page-{page_number}.geojson"),"dxf":str(dxf_path) if dxf_path else None}}
    (safe/f"page-{page_number}-qa.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--pdf",type=Path,required=True); p.add_argument("--out",type=Path,required=True)
    p.add_argument("--pages",type=int,nargs="+",default=[7,8]); p.add_argument("--curve-steps",type=int,default=24)
    p.add_argument("--endpoint-tolerance-pt",type=float,default=0.20)
    p.add_argument("--scale-x0",type=float);p.add_argument("--scale-y0",type=float)
    p.add_argument("--scale-x1",type=float);p.add_argument("--scale-y1",type=float)
    p.add_argument("--scale-m",type=float);p.add_argument("--scale-endpoint-uncertainty-pt",type=float,default=0.10)
    p.add_argument("--private-render",action="store_true",help="Also render source-page previews; private only")
    a=p.parse_args()
    if not a.pdf.is_file(): p.error("PDF does not exist")
    if a.curve_steps<4 or a.endpoint_tolerance_pt<=0: p.error("curve steps must be >=4 and tolerance positive")
    supplied=[a.scale_x0,a.scale_y0,a.scale_x1,a.scale_y1,a.scale_m]
    if any(v is not None for v in supplied) and any(v is None for v in supplied): p.error("Supply all scale endpoint and length options together")
    endpoints=[[a.scale_x0,a.scale_y0],[a.scale_x1,a.scale_y1]] if all(v is not None for v in supplied) else None
    scale=scale_data(endpoints,a.scale_m,a.scale_endpoint_uncertainty_pt)
    pdf_sha=hashlib.sha256(a.pdf.read_bytes()).hexdigest(); doc=fitz.open(a.pdf)
    if any(n<1 or n>len(doc) for n in a.pages): p.error("Requested page outside PDF")
    a.out.mkdir(parents=True,exist_ok=True); reports=[]
    for n in a.pages:
        page=doc[n-1]
        # Page 8 uses the supplied page-7 graphic scale provisionally until p7/p8 controls pass review.
        rep=build_page(page,n,scale,a.out,a.curve_steps,a.endpoint_tolerance_pt,pdf_sha)
        rep["source_sha256"]=pdf_sha
        folder=Path(rep["files"]["qa"]) if "qa" in rep["files"] else a.out/f"C04-p{n:02d}-PRIVATE"/f"page-{n}-qa.json"
        (a.out/f"C04-p{n:02d}-PRIVATE"/f"page-{n}-qa.json").write_text(json.dumps(rep,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        if a.private_render:
            page.get_pixmap(matrix=fitz.Matrix(2,2),alpha=False).save(str(a.out/f"C04-p{n:02d}-PRIVATE"/f"page-{n}-source.png"))
        reports.append(rep)
    summary={"schema":"kkl-private-vector-reconstruction-v1","source_sha256":pdf_sha,"source_access":"PRIVATE - permission to redistribute/reproduce unresolved","scale":scale,"pages":reports}
    (a.out/"private-reconstruction-qa.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"out":str(a.out),"pages":[{"page":r["page"],"features":r["source_feature_count"],"groups_closed_by_endpoint_tolerance":r["groups_closed_by_endpoint_tolerance"],"unknown":r["classification_counts"]["unknown"]} for r in reports],"scale_m_per_display_pt":scale["metres_per_display_point"]},ensure_ascii=False))

if __name__=="__main__": main()
