# C04 p.7 V1.3 — building/road position review

## Result

- V1.2 overlap envelope check: **3 building-to-road intersections** (tested against every road ribbon and a 1.2 px roof overhang).
- V1.3 after adjustment: **0 intersections** across 21 building masses and 9 road ribbons.
- Graphic scale used: **0.6879945 m per display pixel** from the 0–60 m bar; this is a plan-scale visual check, not survey accuracy.
- Minimum post-adjustment clearance (including roof overhang): **2.12 m** at Cooling water vs North internal road.

## V1.2 intersections found

- Distillery 1 × South internal road: 219.3 px² (about 103.83 m² at graphic scale).
- Sorghum store × Middle east west road: 492.4 px² (about 233.09 m² at graphic scale).
- Visitor support × Middle east west road: 20.1 px² (about 9.52 m² at graphic scale).

## V1.3 adjustments

- **景觀區服務設施:** x max 352→344; y min 402→408; removes its corner from the middle-road corridor.
- **高粱筒倉區:** y min 398→412; places mass fully below the middle-road corridor with clearance.
- **製酒一場:** y max 515→508; separates the southern footprint edge from the south internal road.
- **附屬大樓:** y max 394→391; adds roof-margin clearance to the middle-road corridor.
- **加油站:** y max 477→468; clears the diagonal east-access road envelope.
- **Outer east access:** south endpoint x 740→752 (illustrative route centerline); aligns route edge to corridor visible in source-plan coordinate grid and clears the fuel-station mass.

## Current near-clearance list

- Cooling water → North internal road: 2.12 m.
- Site office → South internal road: 2.55 m.
- Sorghum store → Middle east west road: 2.55 m.
- Koji factory 2 → North internal road: 2.80 m.
- Annex → Middle east west road: 3.24 m.
- Visitor support → Middle east west road: 3.30 m.
- Oil tank area → North internal road: 3.49 m.
- Jinning office → Middle east west road: 3.93 m.

## Review overlay

The adjacent PNG is a private source-plan overlay for visual review. It must not be copied into the public repository or website.

## Limits

- Footprints and road axes remain manually digitized candidates, not semantically matched to all original PDF source IDs.
- Clearance is a visualization QA check only; the scale and plan are not an as-built survey.
- No original PDF raster, extracted vectors, or overlay is included in public repository assets.
