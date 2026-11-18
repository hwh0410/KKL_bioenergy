# Visitor Facility Position Review (Private Outputs)

`analysis/visitor_position_review.py` produces a **local-only** review overlay for the visitor facilities on C04 page 7. It consumes the previously reviewed candidate GeoJSON and a manually reviewed axial-endpoint point. It writes a source-page overlay, a page-coordinate candidate GeoJSON, and a JSON QA report. The source PDF and all generated overlays must remain outside this repository while reproduction rights are unresolved.

The script reports distances from candidate polygon edges to nearby source vector primitives. These distances are diagnostics only: nearby vectors can be labels, symbols, or unrelated plan detail. No output is promoted to verified engineering geometry. Candidate outlines retain `review_required: true` and `engineering_geometry: false`.

## Run locally

```bash
python -m pip install -r analysis/requirements.txt
python -m unittest discover -s analysis/tests -v
python analysis/visitor_position_review.py \
  --pdf /private/path/C04.PDF \
  --candidates data/eia-p07-semantic-calibrated-v0.9.4.geojson \
  --axial-endpoint DISPLAY_X DISPLAY_Y \
  --out /private/path/visitor-location-review
```

`DISPLAY_X DISPLAY_Y` must be independently reviewed in the rotated page-display coordinate system. Do not use the photographs or historic EIA site area to derive scale. The current page scale and source-control evidence are documented in the private QA report.

The user identified the S-shaped feature as the 曲水流觴 walkway. Keep it classified as pedestrian circulation; do not trace it as a water contour. Facility photo labels are a semantic crosswalk only and do not prove footprint boundaries. In particular, one supplied facade image says 福利大樓 while the user labeled it 廠史館; resolve that identity against the user before promoting a semantic label.
