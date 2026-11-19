#!/usr/bin/env python3
"""Render source-derived SVG privately and compare its placement to the PDF page."""
import argparse
import json
import shutil
import subprocess
from pathlib import Path

import fitz
from PIL import Image, ImageChops, ImageFilter


def compare(pdf: Path, svg: Path, page_no: int, out: Path, dpi: int = 144):
    app = shutil.which("inkscape")
    if not app:
        raise RuntimeError("Inkscape is required to render the exported SVG for the private overlay")
    out.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(pdf)
    page = doc[page_no - 1]
    scale = dpi / 72
    source = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
    source_path = out / f"C04-p{page_no:02d}-PRIVATE-source-render.png"
    source.save(source_path)
    svg_render = out / f"C04-p{page_no:02d}-PRIVATE-svg-render.png"
    subprocess.run([app, str(svg), "--export-filename", str(svg_render),
                    f"--export-width={source.width}", f"--export-height={source.height}"],
                   check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    a = Image.open(source_path).convert("L")
    b = Image.open(svg_render).convert("L")
    if a.size != b.size:
        raise RuntimeError(f"Raster size mismatch: PDF {a.size} vs SVG {b.size}")
    # Compare extracted vector ink against all PDF page ink (text can only make this generous).
    source_ink = a.point(lambda x: 255 if x < 205 else 0)
    svg_ink = b.point(lambda x: 255 if x < 205 else 0)
    totals = svg_ink.histogram()[255]
    metrics = {"page": page_no, "source_pixels": list(a.size), "dpi": dpi,
               "svg_ink_pixels": totals, "within_1px_count": 0, "within_2px_count": 0,
               "within_1px_fraction": None, "within_2px_fraction": None,
               "comparison_note": "Nearest-pixel coverage of extracted SVG ink by the PDF raster ink. Includes PDF text/annotations as possible matches; diagnostic only, not semantic geometry validation."}
    for radius in (1, 2):
        near = source_ink.filter(ImageFilter.MaxFilter(2 * radius + 1))
        overlap = ImageChops.multiply(svg_ink, near)
        count = overlap.histogram()[255]
        metrics[f"within_{radius}px_count"] = count
        metrics[f"within_{radius}px_fraction"] = count / totals if totals else None
    # Green source PDF with magenta vector linework overlay, kept private.
    rgb = Image.merge("RGB", (a, a, a))
    color = Image.new("RGB", a.size, (255, 0, 180))
    alpha = svg_ink.point(lambda x: 110 if x else 0)
    overlay = Image.composite(color, rgb, alpha)
    overlay.save(out / f"C04-p{page_no:02d}-PRIVATE-overlay.png")
    (out / f"C04-p{page_no:02d}-PRIVATE-overlay-qa.json").write_text(json.dumps(metrics, indent=2)+"\n", encoding="utf-8")
    return metrics


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--pdf",type=Path,required=True); p.add_argument("--svg",type=Path,required=True)
    p.add_argument("--page",type=int,required=True); p.add_argument("--out",type=Path,required=True)
    p.add_argument("--dpi",type=int,default=144)
    a=p.parse_args()
    print(json.dumps(compare(a.pdf,a.svg,a.page,a.out,a.dpi),ensure_ascii=False,indent=2))

if __name__=="__main__": main()
