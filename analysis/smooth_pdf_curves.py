#!/usr/bin/env python3
"""Fit continuous curves to connected PDF line fragments, within a stated tolerance.

The original vectors stay untouched. This tool emits a separate derived SVG and
QA report; source IDs make every fitted curve traceable to its PDF line items.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET

import fitz
import numpy as np
from scipy.spatial import cKDTree


def point(p, matrix):
    q = fitz.Point(p) * matrix
    return np.array([q.x, q.y], dtype=float)


def collect_line_chains(page, join_tolerance: float):
    """Join only sequential line items whose endpoints meet within tolerance."""
    chains = []
    for di, drawing in enumerate(page.get_drawings()):
        vertices, refs = [], []
        def flush():
            nonlocal vertices, refs
            if len(vertices) >= 2:
                chains.append({"drawing_index": di, "points": np.asarray(vertices),
                               "source_refs": refs[:]})
            vertices, refs = [], []
        for ii, item in enumerate(drawing["items"]):
            if item[0] != "l":
                flush()
                continue
            a, b = point(item[1], page.rotation_matrix), point(item[2], page.rotation_matrix)
            if vertices and np.linalg.norm(vertices[-1] - a) > join_tolerance:
                flush()
            if not vertices:
                vertices.append(a)
            vertices.append(b)
            refs.append(f"{page.number + 1}:{di}:{ii}")
        flush()
    return chains


def dedupe(points, eps=1e-8):
    out = [points[0]]
    for p in points[1:]:
        if np.linalg.norm(p - out[-1]) > eps:
            out.append(p)
    return np.asarray(out)


def fit_circle(points):
    x, y = points[:, 0], points[:, 1]
    A = np.column_stack((2*x, 2*y, np.ones_like(x)))
    z = x*x + y*y
    try:
        cx, cy, c = np.linalg.lstsq(A, z, rcond=None)[0]
    except np.linalg.LinAlgError:
        return None
    r = math.sqrt(max(0.0, c + cx*cx + cy*cy))
    if not np.isfinite(r) or r <= 0:
        return None
    residuals = np.abs(np.linalg.norm(points - [cx, cy], axis=1) - r)
    angles = np.unwrap(np.arctan2(y - cy, x - cx))
    sweep = float(angles[-1] - angles[0])
    if abs(sweep) < math.radians(2) or abs(sweep) > math.radians(330):
        return None
    # Endpoint radii must also agree with the fitted circle.
    return np.array([cx, cy]), r, sweep, residuals


def unit(v):
    n = np.linalg.norm(v)
    return v / n if n > 1e-10 else None


def fit_cubic(points):
    """Least-squares cubic with endpoints fixed to preserve chain continuity."""
    p = dedupe(points)
    if len(p) < 4:
        return None
    t = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))]
    if t[-1] <= 1e-10:
        return None
    t /= t[-1]
    p0, p3 = p[0], p[-1]
    def solve(params):
        rows, rhs = [], [[], []]
        for ti, pi in zip(params[1:-1], p[1:-1]):
            u = 1-ti
            b0, b1, b2, b3 = u**3, 3*u*u*ti, 3*u*ti*ti, ti**3
            rows.append([b1, b2])
            rhs[0].append(pi[0] - b0*p0[0] - b3*p3[0])
            rhs[1].append(pi[1] - b0*p0[1] - b3*p3[1])
        controls = np.asarray([np.linalg.lstsq(np.asarray(rows), np.asarray(values), rcond=None)[0]
                               for values in rhs]).T
        return np.array([p0, controls[0], controls[1], p3])

    ctrl = solve(t)
    # Reassign curve parameters by closest sampled position, then refit. This
    # reduces bias from using chord length as a proxy for Bezier parameter.
    for _ in range(4):
        dense_t = np.linspace(0, 1, 1201)
        dense = cubic_points(ctrl, len(dense_t))
        _, nearest_idx = cKDTree(dense).query(p, k=1)
        nearest = dense_t[nearest_idx]
        nearest[0], nearest[-1] = 0.0, 1.0
        nearest = np.maximum.accumulate(nearest)
        ctrl = solve(nearest)
    return ctrl


def cubic_points(ctrl, count=250):
    t = np.linspace(0, 1, count)
    u = 1-t
    return (u[:,None]**3*ctrl[0] + 3*u[:,None]**2*t[:,None]*ctrl[1]
            + 3*u[:,None]*t[:,None]**2*ctrl[2] + t[:,None]**3*ctrl[3])


def distance_to_polyline(query, line):
    maximum = 0.0
    for p in query:
        dmin = float("inf")
        for a, b in zip(line[:-1], line[1:]):
            v = b-a
            den = float(v @ v)
            t = max(0.0, min(1.0, float((p-a) @ v / den))) if den else 0.0
            dmin = min(dmin, float(np.linalg.norm(p-(a+t*v))))
        maximum = max(maximum, dmin)
    return maximum


def symmetric_error(source, fitted):
    samples = []
    for a, b in zip(source[:-1], source[1:]):
        n = max(1, math.ceil(np.linalg.norm(b-a) / 0.25))
        samples.extend(a + (b-a)*t for t in np.linspace(0, 1, n+1))
    return max(distance_to_polyline(np.asarray(samples), fitted),
               distance_to_polyline(fitted, source))


def fmt(p):
    return f"{p[0]:.4f},{p[1]:.4f}"


def fit_chain(chain, tolerance):
    source = dedupe(chain["points"])
    if len(source) < 5:
        return None
    # Do not turn segmented straight walls into nominal splines.
    chord = source[-1] - source[0]
    clen = np.linalg.norm(chord)
    if clen <= 1e-10:
        return None
    rel = source-source[0]
    bend = np.max(np.abs((chord[0]*rel[:,1] - chord[1]*rel[:,0]) / clen))
    if bend < 0.15:
        return None
    circle = fit_circle(source)
    if circle:
        center, radius, sweep, residuals = circle
        if max(abs(np.linalg.norm(source[0]-center)-radius),
               abs(np.linalg.norm(source[-1]-center)-radius)) > tolerance:
            circle = None
    if circle:
        center, radius, sweep, residuals = circle
        # Check a rendered circular arc against source samples, preserving endpoints.
        angles = np.unwrap(np.arctan2(source[:,1]-center[1], source[:,0]-center[0]))
        fitted = np.column_stack((center[0] + radius*np.cos(angles),
                                  center[1] + radius*np.sin(angles)))
        err = symmetric_error(source, fitted)
        if err <= tolerance:
            return {"kind":"arc", "center":center, "radius":radius,
                    "sweep":sweep, "error":err}
    cubic = fit_cubic(source)
    if cubic is None:
        return None
    err = symmetric_error(source, cubic_points(cubic))
    if err <= tolerance:
        return {"kind":"cubic", "control":cubic, "error":err}
    return None


def render(page, chains, out, tolerance, min_segments, base_svg=None):
    width, height = float(page.rect.width), float(page.rect.height)
    accepted, rejected, paths = [], 0, []
    for chain in chains:
        if len(chain["source_refs"]) < min_segments:
            continue
        fit = fit_chain(chain, tolerance)
        if not fit:
            rejected += 1
            continue
        refs = chain["source_refs"]
        if fit["kind"] == "arc":
            p0, p1 = chain["points"][0], chain["points"][-1]
            large = int(abs(fit["sweep"]) > math.pi)
            sweep_flag = int(fit["sweep"] > 0)
            d = (f"M {fmt(p0)} A {fit['radius']:.4f},{fit['radius']:.4f} "
                 f"0 {large} {sweep_flag} {fmt(p1)}")
            controls = {"center":fit["center"].tolist(), "radius":fit["radius"],
                        "sweep_radians":fit["sweep"]}
        else:
            c = fit["control"]
            d = f"M {fmt(c[0])} C {fmt(c[1])} {fmt(c[2])} {fmt(c[3])}"
            controls = {"bezier_control_points_display_pt":c.tolist()}
        cid = f"smooth-{len(accepted):05d}"
        paths.append(f'<path id="{cid}" data-source-refs="{",".join(refs)}" d="{d}"/>')
        accepted.append({"id":cid, "kind":fit["kind"], "drawing_index":chain["drawing_index"],
                         "source_refs":refs, "source_segment_count":len(refs),
                         "max_symmetric_deviation_display_pt":fit["error"], **controls})
    svg=(f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.3f}pt" height="{height:.3f}pt" viewBox="0 0 {width:.5f} {height:.5f}">\n'
         '<metadata>Private derived curve layer. Source lines remain unchanged; candidates fitted within declared tolerance.</metadata>\n'
         '<g fill="none" stroke="#cc2b22" stroke-width="0.45" stroke-linecap="round" stroke-linejoin="round">\n'
         + "\n".join(paths) + "\n</g></svg>\n")
    if base_svg:
        # Make an edited copy of the complete source SVG, replacing only fitted
        # source paths. The original export remains untouched for comparison.
        tree=ET.parse(base_svg)
        root=tree.getroot()
        source_group=root.find(".//{http://www.w3.org/2000/svg}g[@id='source-vectors']")
        if source_group is None:
            raise ValueError("base SVG lacks #source-vectors group")
        replaced={ref for item in accepted for ref in item["source_refs"]}
        for node in list(source_group):
            ref=node.attrib.get("data-source-ref")
            if ref in replaced:
                source_group.remove(node)
        ns="{http://www.w3.org/2000/svg}"
        for item, d in zip(accepted, paths):
            # Parse the generated path element and inherit the base stroke style.
            node=ET.fromstring(d)
            node.tag=ns+"path"
            node.set("data-classification","derived_curve_candidate")
            node.set("data-max-deviation-display-pt",f"{item['max_symmetric_deviation_display_pt']:.6f}")
            source_group.append(node)
        tree.write(out,encoding="utf-8",xml_declaration=True)
    else:
        out.write_text(svg, encoding="utf-8")
    report={"page":page.number+1,"page_rotation_degrees":page.rotation,
            "join_tolerance_display_pt":0.20,"curve_fit_tolerance_display_pt":tolerance,
            "minimum_source_line_segments":min_segments,"connected_line_chains":len(chains),
            "accepted_curve_count":len(accepted),"rejected_eligible_chain_count":rejected,
            "source_line_segments_replaced":sum(x["source_segment_count"] for x in accepted),
            "source_refs_replaced":sum((x["source_refs"] for x in accepted),[]),
            "maximum_deviation_display_pt":max((x["max_symmetric_deviation_display_pt"] for x in accepted),default=0),
            "maximum_deviation_m_using_page_scale":max((x["max_symmetric_deviation_display_pt"] for x in accepted),default=0)*1.03199256,
            "curves":accepted,
            "base_svg_used":str(base_svg) if base_svg else None,
            "status":"derived_visual smoothing only; source geometry preserved and semantics unverified"}
    return report


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pdf",required=True,type=Path)
    ap.add_argument("--page",type=int,default=7)
    ap.add_argument("--out",required=True,type=Path)
    ap.add_argument("--base-svg",type=Path,help="optional full raw extraction SVG to create a full smoothed-plan copy")
    ap.add_argument("--tolerance-pt",type=float,default=0.10)
    ap.add_argument("--join-tolerance-pt",type=float,default=0.20)
    ap.add_argument("--minimum-segments",type=int,default=10,
                    help="ignore shorter chains, which are often text glyphs or tiny symbols")
    a=ap.parse_args()
    doc=fitz.open(a.pdf); page=doc[a.page-1]
    chains=collect_line_chains(page,a.join_tolerance_pt)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    report=render(page,chains,a.out,a.tolerance_pt,a.minimum_segments,a.base_svg)
    report["source_pdf_sha256"]=hashlib.sha256(a.pdf.read_bytes()).hexdigest()
    report_path=a.out.with_suffix('.qa.json')
    report_path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('page','connected_line_chains','accepted_curve_count','rejected_eligible_chain_count','source_line_segments_replaced','maximum_deviation_display_pt','maximum_deviation_m_using_page_scale')},ensure_ascii=False))


if __name__ == '__main__':
    main()
