# DCEL Map Generator

Generate whimsical continent-style maps from a rooted hierarchy and export them as:

- a leaf-level DCEL
- a rendered preview image
- a frontend-ready bundle for an interactive zoomable map

This repo is the reusable core. Domain-specific map projects can keep their own hierarchy data and consume this generator/render stack.

[Live Demo](https://alonso-cancino.github.io/map-generator/)

![Atlantis demo map](docs/atlantis-map.png)

## What It Does

The pipeline is tree-first:

1. load a rooted hierarchy from `examples/atlantis/zone_edges.json`
2. generate a continent mask
3. recursively partition each parent region among its children
4. extract leaf polygons from the raster partition
5. build a DCEL and optional frontend bundle

The bundled demo dataset is a small fantasy world centered on **Atlantis** so you can run the project immediately without bringing your own taxonomy first.

## Quickstart

Requirements:

- Python 3.11+
- `uv`
- Node.js 20+ for the frontend demo

Install Python dependencies:

```bash
uv sync --dev
```

Generate the demo outputs:

```bash
uv run python -m dcel_builder \
  --zone-edges examples/atlantis/zone_edges.json \
  --tree-stats examples/atlantis/zone_tree_stats.json \
  --zone-index examples/atlantis/zone_index.json \
  --output dcel_map.json \
  --render \
  --render-output docs/atlantis-map.png \
  --frontend-bundle frontend/public/map_bundle.json \
  --validate
```

Run the interactive renderer locally:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173/`.

## Input Files

The generator expects three JSON files:

- `zone_edges.json`: directed `[parent, child]` pairs forming a rooted tree
- `zone_index.json`: `{ "id": "name" }` mapping used for labels/tooling
- `zone_tree_stats.json`: optional sidecar metadata; the generator currently tolerates an empty object

The bundled example describes a three-level fantasy continent:

- `Atlantis`
- major regions such as `Aurelia Reach`, `Tidehollow`, `Cinder Crown`, `Mistwood`
- smaller subregions and leaf territories beneath them

The tracked demo inputs live in [`examples/atlantis`](/home/alosc/proyectos/map/examples/atlantis). Private or domain-specific datasets can stay in ignored folders such as `local/`.

## Outputs

- `dcel_map.json`: serialized DCEL
- `docs/atlantis-map.png`: static render
- `frontend/public/map_bundle.json`: interactive bundle consumed by the frontend

## GitHub Pages Demo

The frontend is configured for GitHub Pages static hosting. A workflow in `.github/workflows/deploy-pages.yml` builds `frontend/` and publishes the interactive demo using the bundled Atlantis example.

## Development

```bash
uv run pytest
uv run ruff check .
cd frontend && npm run build
```

Contributor conventions live in `AGENTS.md`.

## License

MIT. See [LICENSE](LICENSE).
