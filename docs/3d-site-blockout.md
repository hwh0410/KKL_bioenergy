# 3D site blockout

The current project priority is the 3D site visualization. The 2D page extraction is used as a placement reference; complete restoration of every source line is not a prerequisite for the first 3D pass.

`analysis/build_site_blockout.py` builds an editable Blender scene and exports GLB using the project's visitor-zone, existing-building, and OSM-road GeoJSON layers. It creates simple extruded building masses, low circular water features, a conceptual curved pedestrian path, a green bottle-park mound, and stylized bottle landmarks. A flat ground plane provides context.

## Run

```bash
blender --background --python analysis/build_site_blockout.py -- \
  --visitor data/visitor-zone.geojson \
  --buildings data/existing-buildings.geojson \
  --roads data/roads-osm.geojson \
  --out /private/path/KKL_Jinning_site_blockout_PRIVATE.glb \
  --preview /private/path/KKL_Jinning_site_blockout_preview_PRIVATE.png
```

The local model frame is a tangent-plane conversion from WGS84 around 118.3420°E, 24.4313°N; model XY coordinates are metres east and north. The generated `.glb.json` sidecar documents the origin and limitations.

This is an indicative visualization blockout. Footprints and heights are approximate; terrain is not modeled; water features, bottle sculptures, and the 曲水流觴 path are simplified. The GLB must not be treated as an as-built survey or engineering model. Refine facility locations and heights against better site evidence as it becomes available.
