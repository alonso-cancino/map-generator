# dcel-map-generator

Generate whimsical continent-style maps from a rooted hierarchy of zones. The pipeline produces a leaf-level [DCEL](https://en.wikipedia.org/wiki/Doubly_connected_edge_list) planar subdivision, an optional rendered PNG, and a frontend-ready JSON bundle for interactive exploration.

[Live Demo](https://alonso-cancino.github.io/map-generator/) | [GitHub](https://github.com/alonso-cancino/map-generator)

## Installation

```bash
pip install dcel-map-generator
```

Requires Python 3.11+.

## Quick Example

```python
from dcel_builder import generate_dcel

dcel, report = generate_dcel(
    zone_edges_path="zone_edges.json",
    tree_stats_path="zone_tree_stats.json",
    zone_index_path="zone_index.json",
    seed=42,
)

interior_faces = [f for f in dcel.faces if not f.is_outer]
print(f"Generated {len(interior_faces)} leaf territories")
```

## Python API

### `generate_dcel(...) -> (DCEL, report)`

Build a leaf-level DCEL from a rooted zone tree.

### `generate_frontend_bundle(...) -> (bundle_dict, report)`

Build a frontend-ready hierarchy bundle (JSON-serializable dict) that can be consumed by the companion React component [`@alonso-cancino/dcel-map-frontend`](https://www.npmjs.com/package/@alonso-cancino/dcel-map-frontend).

### `generate_map_artifacts(...) -> (DCEL, report, tree, zone_index)`

Low-level entry point that returns all intermediate artifacts.

All three functions accept the same parameters:

| Parameter | Type | Default | Description |
|---|---|---|---|
| `zone_edges_path` | `str \| Path` | required | Directed `[parent, child]` edge-list JSON |
| `tree_stats_path` | `str \| Path` | required | Sidecar stats JSON (can be `{}`) |
| `zone_index_path` | `str \| Path` | required | `{ "id": "name" }` mapping JSON |
| `seed` | `int \| None` | `None` | RNG seed for reproducible maps |
| `resolution` | `int` | `512` | Raster grid size H x H |
| `land_fraction` | `float` | `0.40` | Target fraction of land pixels |
| `noise_exponent` | `float` | `2.3` | Power-law exponent for spectral noise |
| `warp_strength` | `float` | `0.10` | Domain-warp amplitude (fraction of resolution) |
| `split_mode` | `str` | `"contour_guided"` | Split strategy: `contour_guided`, `field_guided`, or `seeded` |
| `quiet` | `bool` | `False` | Suppress progress output |

## CLI

The package installs a `dcel-map` command:

```bash
dcel-map \
  --zone-edges zone_edges.json \
  --tree-stats zone_tree_stats.json \
  --zone-index zone_index.json \
  --output dcel_map.json \
  --render --render-output map.png \
  --frontend-bundle map_bundle.json \
  --seed 42 --validate
```

Key flags:

| Flag | Description |
|---|---|
| `--output` | Path for the output DCEL JSON |
| `--render` | Render the DCEL to a PNG image |
| `--render-output` | PNG output path (default: `dcel_map.png`) |
| `--frontend-bundle` | Generate a frontend-ready JSON bundle |
| `--seed` | RNG seed for reproducibility |
| `--resolution` | Raster grid size (default: 512) |
| `--split-mode` | `contour_guided` (default), `field_guided`, or `seeded` |
| `--validate` | Run structural invariant checks before writing |
| `--quiet` | Suppress progress output |

## Input Files

The generator expects three JSON files describing a rooted tree of zones:

**`zone_edges.json`** — directed parent-child pairs:
```json
[[0, 1], [0, 2], [1, 3], [1, 4]]
```

**`zone_index.json`** — zone ID to display name:
```json
{"0": "World", "1": "North", "2": "South", "3": "Tundra", "4": "Forest"}
```

**`zone_tree_stats.json`** — optional metadata (an empty `{}` is accepted).

## Outputs

- **DCEL JSON** — serialized planar subdivision with vertices, half-edges, and faces. Each interior face is tagged with a `zone_id` from the input tree.
- **PNG render** — static map image colored by zone.
- **Frontend bundle** — JSON structure with SVG paths, bounding boxes, hierarchy, and zoom thresholds for interactive rendering.

## How It Works

The pipeline is tree-first:

1. Load a rooted hierarchy from the edge-list
2. Generate a continent mask using spectral noise with domain warping
3. Recursively partition each parent region among its children using weighted splits
4. Extract leaf polygons from the raster partition
5. Build a DCEL planar subdivision

Split modes control how regions are divided:
- **`contour_guided`** — splits along raster contour lines (organic, natural-looking boundaries)
- **`field_guided`** — uses distance/flow fields for partitioning
- **`seeded`** — random Voronoi-like splits

## License

MIT
