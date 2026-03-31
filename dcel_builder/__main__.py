"""CLI entry point for dcel_builder."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a DCEL map from a zone tree.")
    parser.add_argument(
        "--zone-edges",
        default="examples/atlantis/zone_edges.json",
        help="Path to zone tree edge-list JSON",
    )
    parser.add_argument(
        "--leaf-graph",
        default=None,
        help="Deprecated compatibility alias for --zone-edges",
    )
    parser.add_argument(
        "--tree-stats",
        default="examples/atlantis/zone_tree_stats.json",
        help="Path to zone tree stats JSON",
    )
    parser.add_argument(
        "--zone-index",
        default="examples/atlantis/zone_index.json",
        help="Path to zone index JSON",
    )
    parser.add_argument(
        "--output",
        default="dcel_map.json",
        help="Path for the output DCEL JSON",
    )
    parser.add_argument(
        "--frontend-bundle",
        default=None,
        help="Optional path for a frontend-ready hierarchy JSON bundle",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="RNG seed for reproducible generation (random if omitted)",
    )
    parser.add_argument(
        "--resolution",
        type=int,
        default=512,
        help="Raster grid size H×H (default: 512)",
    )
    parser.add_argument(
        "--land-fraction",
        type=float,
        default=0.40,
        help="Target fraction of raster pixels that are land (default: 0.40)",
    )
    parser.add_argument(
        "--noise-exponent",
        type=float,
        default=2.3,
        help="Power-law exponent for spectral noise (default: 2.3)",
    )
    parser.add_argument(
        "--warp-strength",
        type=float,
        default=0.10,
        help="Domain-warp amplitude as fraction of resolution (default: 0.10)",
    )
    parser.add_argument(
        "--canvas-size",
        type=float,
        default=1.0,
        help="(Retained for compatibility; has no effect on raster resolution)",
    )
    parser.add_argument(
        "--blob-radius",
        type=float,
        default=0.5,
        help="Gaussian blob radius for continent shape (default: 0.5)",
    )
    parser.add_argument(
        "--disk-radius",
        type=int,
        default=None,
        help="Reserved disk radius in pixels; auto-computed if omitted",
    )
    parser.add_argument(
        "--area-floor",
        type=float,
        default=0.5,
        help="Minimum fraction of target area a zone can be reduced to (default: 0.5)",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Run structural invariant checks on output before writing",
    )
    parser.add_argument(
        "--render",
        action="store_true",
        help="Render the generated DCEL to a PNG image",
    )
    parser.add_argument(
        "--render-output",
        default="dcel_map.png",
        help="Path for the rendered PNG when --render is used",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress progress output",
    )

    args = parser.parse_args()

    # Validate new parameters
    if args.blob_radius <= 0:
        parser.error("--blob-radius must be > 0")
    if args.disk_radius is not None and args.disk_radius < 1:
        parser.error("--disk-radius must be >= 1")
    if not (0 < args.area_floor <= 1):
        parser.error("--area-floor must be in (0, 1]")

    zone_edges_arg = args.leaf_graph or args.zone_edges
    zone_edges_path = Path(zone_edges_arg)
    if not zone_edges_path.exists():
        print(f"ERROR: Input file not found: {zone_edges_path}", file=sys.stderr)
        sys.exit(1)

    from dcel_builder import generate_map_artifacts
    from dcel_builder.frontend_bundle import build_frontend_bundle
    from dcel_builder.serializer import to_json, validate_invariants

    try:
        if not args.quiet:
            ignored = [
                "--canvas-size",
                "--blob-radius",
                "--disk-radius",
                "--area-floor",
            ]
            print(
                "Tree-first recursive pipeline active; compatibility flags are accepted but "
                "ignored: "
                + ", ".join(ignored)
            )
        dcel, report, tree, zone_index = generate_map_artifacts(
            zone_edges_arg,
            args.tree_stats,
            args.zone_index,
            seed=args.seed,
            resolution=args.resolution,
            land_fraction=args.land_fraction,
            noise_exponent=args.noise_exponent,
            warp_strength=args.warp_strength,
            quiet=args.quiet,
            blob_radius=args.blob_radius,
            disk_radius=args.disk_radius,
            area_floor=args.area_floor,
        )
    except ValueError as e:
        msg = str(e)
        if "no valid seed" in msg.lower():
            print(f"ERROR: Insufficient land pixels. {msg}", file=sys.stderr)
            sys.exit(3)
        print(f"ERROR: Invalid input. {msg}", file=sys.stderr)
        sys.exit(2)

    if args.validate:
        if not validate_invariants(dcel):
            print("ERROR: DCEL structural validation failed.", file=sys.stderr)
            sys.exit(4)

    data = to_json(dcel, {})
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(data, indent=2))

    frontend_bundle_path = None
    if args.frontend_bundle is not None:
        frontend_bundle = build_frontend_bundle(dcel, tree, zone_index)
        frontend_bundle_path = Path(args.frontend_bundle)
        frontend_bundle_path.parent.mkdir(parents=True, exist_ok=True)
        frontend_bundle_path.write_text(json.dumps(frontend_bundle, indent=2))

    render_path = None
    if args.render:
        from dcel_builder.render import render_dcel

        render_path = Path(args.render_output)
        render_path.parent.mkdir(parents=True, exist_ok=True)
        render_dcel(dcel, render_path)

    if not args.quiet:
        interior = sum(1 for f in dcel.faces if not f.is_outer)
        message = (
            f"DCEL map written to {output_path} "
            f"({interior} leaf faces, root {report['root_id']}, max depth {report['max_depth']})"
        )
        if frontend_bundle_path is not None:
            message += f"; frontend bundle written to {frontend_bundle_path}"
        if render_path is not None:
            message += f"; render written to {render_path}"
        print(message)


if __name__ == "__main__":
    main()
