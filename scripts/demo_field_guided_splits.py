from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib
import numpy as np
from matplotlib.collections import PolyCollection
from shapely.geometry import LineString, MultiLineString, Polygon

matplotlib.use("Agg")

import matplotlib.pyplot as plt

from dcel_builder.geometry import face_polygon_coords
from dcel_builder.hierarchy import HierarchyBuildResult, build_leaf_dcel_from_tree
from dcel_builder.render import _zone_color
from dcel_builder.tree_loader import ZoneTree, load_tree_inputs

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ZONE_EDGES = REPO_ROOT / "examples" / "atlantis" / "zone_edges.json"
DEFAULT_TREE_STATS = REPO_ROOT / "examples" / "atlantis" / "zone_tree_stats.json"
DEFAULT_ZONE_INDEX = REPO_ROOT / "examples" / "atlantis" / "zone_index.json"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "local" / "field_guided_demo"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare the default seeded splitter against a field-guided prototype."
    )
    parser.add_argument("--zone-edges", default=str(DEFAULT_ZONE_EDGES))
    parser.add_argument("--tree-stats", default=str(DEFAULT_TREE_STATS))
    parser.add_argument("--zone-index", default=str(DEFAULT_ZONE_INDEX))
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--resolution", type=int, default=256)
    parser.add_argument("--land-fraction", type=float, default=0.40)
    parser.add_argument("--noise-exponent", type=float, default=2.3)
    parser.add_argument("--warp-strength", type=float, default=0.10)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args(argv)

    tree, _, zone_index = load_tree_inputs(args.zone_edges, args.tree_stats, args.zone_index)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    baseline = _generate_result(
        tree=tree,
        seed=args.seed,
        resolution=args.resolution,
        land_fraction=args.land_fraction,
        noise_exponent=args.noise_exponent,
        warp_strength=args.warp_strength,
        split_mode="seeded",
    )
    experimental = _generate_result(
        tree=tree,
        seed=args.seed,
        resolution=args.resolution,
        land_fraction=args.land_fraction,
        noise_exponent=args.noise_exponent,
        warp_strength=args.warp_strength,
        split_mode="field_guided",
    )

    baseline_path = output_dir / "baseline_seeded.png"
    experimental_path = output_dir / "experimental_field_guided.png"
    comparison_path = output_dir / "comparison.png"

    _render_result(
        baseline,
        tree,
        zone_index,
        baseline_path,
        title=f"Baseline seeded split\nseed={args.seed} resolution={baseline.report['resolution']}",
    )
    _render_result(
        experimental,
        tree,
        zone_index,
        experimental_path,
        title=(
            f"Experimental field-guided split\n"
            f"seed={args.seed} resolution={experimental.report['resolution']}"
        ),
    )
    _render_comparison(
        baseline,
        experimental,
        tree,
        zone_index,
        comparison_path,
        args.seed,
    )

    baseline_metrics = _metrics_for_result(baseline)
    experimental_metrics = _metrics_for_result(experimental)
    print(
        _format_summary(
            args.seed,
            baseline.report["resolution"],
            baseline_metrics,
            experimental_metrics,
        )
    )
    print(f"wrote {baseline_path}")
    print(f"wrote {experimental_path}")
    print(f"wrote {comparison_path}")
    return 0


def _generate_result(
    *,
    tree: ZoneTree,
    seed: int,
    resolution: int,
    land_fraction: float,
    noise_exponent: float,
    warp_strength: float,
    split_mode: str,
) -> HierarchyBuildResult:
    return build_leaf_dcel_from_tree(
        tree=tree,
        seed=seed,
        resolution=resolution,
        land_fraction=land_fraction,
        noise_exponent=noise_exponent,
        warp_strength=warp_strength,
        split_mode=split_mode,
    )


def _render_result(
    result: HierarchyBuildResult,
    tree: ZoneTree,
    zone_index: dict[int, str],
    output_path: Path,
    title: str,
) -> None:
    fig, ax = plt.subplots(figsize=(8, 8), dpi=160)
    _draw_result(ax, result, tree, zone_index, title=title)
    fig.tight_layout(pad=0.4)
    fig.savefig(output_path, bbox_inches="tight", pad_inches=0.1)
    plt.close(fig)


def _render_comparison(
    baseline: HierarchyBuildResult,
    experimental: HierarchyBuildResult,
    tree: ZoneTree,
    zone_index: dict[int, str],
    output_path: Path,
    seed: int,
) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(14, 7), dpi=160)
    _draw_result(
        axes[0],
        baseline,
        tree,
        zone_index,
        title=f"Baseline seeded split\nseed={seed} resolution={baseline.report['resolution']}",
    )
    _draw_result(
        axes[1],
        experimental,
        tree,
        zone_index,
        title=(
            f"Experimental field-guided split\n"
            f"seed={seed} resolution={experimental.report['resolution']}"
        ),
    )
    fig.tight_layout(pad=0.4)
    fig.savefig(output_path, bbox_inches="tight", pad_inches=0.1)
    plt.close(fig)


def _draw_result(
    ax,
    result: HierarchyBuildResult,
    tree: ZoneTree,
    zone_index: dict[int, str],
    *,
    title: str,
) -> None:
    polygons: list[list[tuple[float, float]]] = []
    face_colors: list[tuple[float, float, float, float]] = []
    for face in result.dcel.faces:
        if face.is_outer or face.outer_component is None or face.zone_id is None:
            continue
        polygon = face_polygon_coords(result.dcel, face.outer_component)
        if len(polygon) < 3:
            continue
        polygons.append(polygon)
        face_colors.append(_zone_color(face.zone_id))

    ax.set_facecolor("#f5f1e8")
    collection = PolyCollection(
        polygons,
        facecolors=face_colors,
        edgecolors="#101010",
        linewidths=0.7,
        antialiaseds=True,
    )
    ax.add_collection(collection)
    ax.set_xlim(0.0, 1.0)
    ax.set_ylim(0.0, 1.0)
    ax.set_aspect("equal", adjustable="box")
    ax.axis("off")
    ax.set_title(title, fontsize=11)

    root_label = zone_index.get(tree.root, str(tree.root))
    ax.text(
        0.02,
        0.02,
        f"{root_label}\nleafs={len(tree.leaves)}",
        transform=ax.transAxes,
        fontsize=8,
        va="bottom",
        ha="left",
        bbox={"facecolor": "#f5f1e8", "edgecolor": "#bbb5a7", "boxstyle": "round,pad=0.25"},
    )


def _metrics_for_result(result: HierarchyBuildResult) -> dict[str, float]:
    polygons = _leaf_polygons(result)
    borders = _shared_borders(polygons)
    if borders:
        straightness = [(_endpoint_distance(line) / max(line.length, 1e-9)) for line in borders]
        complexity = [max(len(line.coords) - 2, 0) / max(line.length, 1e-9) for line in borders]
        mean_straightness = float(np.mean(straightness))
        mean_complexity = float(np.mean(complexity))
    else:
        mean_straightness = 0.0
        mean_complexity = 0.0

    compactness = [
        (4.0 * np.pi * polygon.area) / max(polygon.length**2, 1e-9)
        for polygon in polygons.values()
        if polygon.area > 0
    ]
    return {
        "border_count": float(len(borders)),
        "mean_straightness": mean_straightness,
        "mean_complexity": mean_complexity,
        "mean_compactness": float(np.mean(compactness)) if compactness else 0.0,
    }


def _leaf_polygons(result: HierarchyBuildResult) -> dict[int, Polygon]:
    polygons: dict[int, Polygon] = {}
    for face in result.dcel.faces:
        if face.is_outer or face.outer_component is None or face.zone_id is None:
            continue
        polygons[face.zone_id] = Polygon(face_polygon_coords(result.dcel, face.outer_component))
    return polygons


def _shared_borders(polygons: dict[int, Polygon]) -> list[LineString]:
    zone_ids = sorted(polygons)
    borders: list[LineString] = []
    for index, left_zone in enumerate(zone_ids):
        for right_zone in zone_ids[index + 1 :]:
            shared = polygons[left_zone].boundary.intersection(polygons[right_zone].boundary)
            borders.extend(_flatten_lines(shared))
    return [line for line in borders if line.length > 1e-6]


def _flatten_lines(geometry) -> list[LineString]:
    if geometry.is_empty:
        return []
    if isinstance(geometry, LineString):
        return [geometry]
    if isinstance(geometry, MultiLineString):
        return [line for line in geometry.geoms if line.length > 0]
    if hasattr(geometry, "geoms"):
        lines: list[LineString] = []
        for item in geometry.geoms:
            lines.extend(_flatten_lines(item))
        return lines
    return []


def _endpoint_distance(line: LineString) -> float:
    start_x, start_y = line.coords[0]
    end_x, end_y = line.coords[-1]
    return float(np.hypot(end_x - start_x, end_y - start_y))


def _format_summary(
    seed: int,
    resolution: int,
    baseline: dict[str, float],
    experimental: dict[str, float],
) -> str:
    straightness_delta = experimental["mean_straightness"] - baseline["mean_straightness"]
    complexity_delta = experimental["mean_complexity"] - baseline["mean_complexity"]
    compactness_delta = experimental["mean_compactness"] - baseline["mean_compactness"]
    return "\n".join(
        [
            f"Field-guided split demo summary: seed={seed} resolution={resolution}",
            (
                "baseline:"
                f" borders={int(baseline['border_count'])}"
                f" straightness={baseline['mean_straightness']:.4f}"
                f" complexity={baseline['mean_complexity']:.4f}"
                f" compactness={baseline['mean_compactness']:.4f}"
            ),
            (
                "experimental:"
                f" borders={int(experimental['border_count'])}"
                f" straightness={experimental['mean_straightness']:.4f}"
                f" complexity={experimental['mean_complexity']:.4f}"
                f" compactness={experimental['mean_compactness']:.4f}"
            ),
            (
                "delta:"
                f" straightness={straightness_delta:+.4f}"
                f" complexity={complexity_delta:+.4f}"
                f" compactness={compactness_delta:+.4f}"
            ),
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
