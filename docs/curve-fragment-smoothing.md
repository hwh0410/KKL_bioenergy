# PDF short-segment curve reconstruction

`analysis/smooth_pdf_curves.py` reconstructs continuous SVG arcs and cubic Bézier curves from sequential, connected PDF line fragments. It never overwrites the raw extraction. Accepted curves replace only their matching source line paths in a separate derived SVG; rejected or short chains remain unchanged.

## Run

First use `analysis/c04_reconstruct.py` to create the raw page SVG. Then run:

```bash
python -m pip install -r analysis/requirements.txt
python analysis/smooth_pdf_curves.py \
  --pdf /private/path/C04.PDF \
  --page 7 \
  --base-svg /private/path/C04-p07-PRIVATE/page-7.svg \
  --out /private/path/C04-p07-smoothed-PRIVATE.svg \
  --join-tolerance-pt 0.20 \
  --tolerance-pt 0.10 \
  --minimum-segments 10
```

The output has a companion `.qa.json` file. It records each replaced source reference, fit type, and maximum symmetric deviation. The default 0.10 display-point tolerance is a geometric acceptance threshold, not survey accuracy. Shorter chains are skipped because PDF text glyphs and small symbols also contain connected line fragments.

Keep the raw SVG and the derived smoothed SVG side by side. The smoothing output is a visual/geometric reconstruction layer; it does not classify a curve as a road, building, pool, or other facility. Source PDF, source-derived SVG/GeoJSON/DXF, and overlays remain private until reproduction rights are confirmed.
