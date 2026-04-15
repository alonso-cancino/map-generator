from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib
import numpy as np
from matplotlib.collections import PolyCollection
from shapely.geometry import LineString, MultiLineString, Polygon

matplotlib.use("Agg")

import matplotlib.pyplot as plt

from dcel_builder.border_roughening import roughen_borders
from dcel_builder.geometry import face_polygon_coords
from dcel_builder.hierarchy import HierarchyBuildResult, build_leaf_dcel_from_tree
from dcel_builder.raster_dcel import build_dcel_from_label_map
from dcel_builder.render import _zone_color
from dcel_builder.tree_loader import ZoneTree, load_tree_inputs

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ZONE_EDGES = REPO_ROOT / "examples" / "atlantis" / "zone_edges.json"
DEFAULT_TREE_STATS = REPO_ROOT / "examples" / "atlantis" / "zone_tree_stats.json"
DEFAULT_ZONE_INDEX = REPO_ROOT / "examples" / "atlantis" / "zone_index.json"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "local" / "roughened_borders_demo"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare the default raster split against a border-roughened variant."
    )
    parser.add_argument("--zone-edges", default=str(DEFAULT_ZONE_EDGES))
    parser.add_argument("--tree-stats", default=str(DEFAULT_TREE_STATS))
    parser.add_argument("--zone-index", default=str(DEFAULT_ZONE_INDEX))
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--resolution", type=int, default=256)
    parser.add_argument("--land-fraction", type=float, default=0.40)
    parser.add_argument("--noise-exponent", type=float, default=2.3)
    parser.add_argument("--warp-strength", type=float, default=0.10)
    parser.add_argument("--roughen-amplitude", type=float, default=4.0)
    parser.add_argument("--roughen-exponent", type=float, default=2.0)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args(argv)

    tree, _, zone_index = load_tree_inputs(args.zone_edges, args.tree_stats, args.zone_index)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    baseline = build_leaf_dcel_from_tree(
        tree=tree,
        seed=args.seed,
        resolution=args.resolution,
        land_fraction=args.land_fraction,
        noise_exponent=args.noise_exponent,
        warp_strength=args.warp_strength,
    )
    roughened = _roughened_result(
        baseline,
        roughen_amplitude=args.roughen_amplitude,
        roughen_exponent=args.roughen_exponent,
        seed=args.seed,
    )

    baseline_path = output_dir / "baseline_seeded.png"
    roughened_path = output_dir / "experimental_roughened.png"
    comparison_path = output_dir / "comparison.png"

    _render_result(
        baseline,
        tree,
        zone_index,
        baseline_path,
        title=f"Baseline seeded split\nseed={args.seed} resolution={baseline.report['resolution']}",
    )
    _render_result(
        roughened,
        tree,
        zone_index,
        roughened_path,
        title=(
            f"Experimental roughened borders\n"
            f"seed={args.seed} amplitude={args.roughen_amplitude:.1f}"
        ),
    )
    _render_comparison(baseline, roughened, tree, zone_index, comparison_path, args.seed)

    baseline_metrics = _metrics_for_result(baseline)
    roughened_metrics = _metrics_for_result(roughened)
    print(
        _format_summary(
            args.seed,
            baseline.report["resolution"],
            baseline_metrics,
            roughened_metrics,
        )
    )
    print(f"wrote {baseline_path}")
    print(f"wrote {roughened_path}")
    print(f"wrote {comparison_path}")
    return 0


def _roughened_result(
    baseline: HierarchyBuildResult,
    *,
    roughen_amplitude: float,
    roughen_exponent: float,
    seed: int,
) -> HierarchyBuildResult:
    roughened_label_map = roughen_borders(
        baseline.label_map,
        amplitude=roughen_amplitude,
        exponent=roughen_exponent,
        master_seed=seed,
    )
    leaf_pixel_counts = {
        zone_id: int(np.sum(roughened_label_map == label_value))
        for zone_id, label_value in baseline.leaf_label_by_zone.items()
    }
    dcel = build_dcel_from_label_map(
        roughened_label_map,
        baseline.leaf_label_by_zone,
        leaf_pixel_counts,
    )
    for face in dcel.faces:
        if face.is_outer:
            continue
        face.target_area = baseline.report["leaf_area_stats"]["mean"]

    report = dict(baseline.report)
    report["leaf_pixel_counts"] = leaf_pixel_counts
    report["leaf_area_stats"] = _area_stats_from_counts(
        leaf_pixel_counts.values(),
        report["continent_pixels"],
    )
    report["target_strategy"] = "seeded_split_plus_border_roughening_demo"
    report["roughen_amplitude"] = roughen_amplitude
    report["roughen_exponent"] = roughen_exponent
    report["smallest_leaf_pixels"] = min(leaf_pixel_counts.values(), default=0)
    return HierarchyBuildResult(
        dcel=dcel,
        label_map=roughened_label_map,
        leaf_label_by_zone=baseline.leaf_label_by_zone,
        report=report,
    )


def _area_stats_from_counts(counts, continent_pixels: int) -> dict[str, float]:
    areas = np.array([count / max(continent_pixels, 1) for count in counts], dtype=np.float64)
    if len(areas) == 0:
        return {"min": 0.0, "max": 0.0, "mean": 0.0, "median": 0.0, "cv": 0.0, "within_50pct": 0}
    mean = float(np.mean(areas))
    return {
        "min": float(np.min(areas)),
        "max": float(np.max(areas)),
        "mean": mean,
        "median": float(np.median(areas)),
        "cv": float(np.std(areas) / mean) if mean > 1e-9 else 0.0,
        "within_50pct": int(np.sum(np.abs(areas - mean) <= mean * 0.5)),
    }


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
    roughened: HierarchyBuildResult,
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
        roughened,
        tree,
        zone_index,
        title=(
            "Roughened borders\n"
            f"seed={seed} amplitude={roughened.report['roughen_amplitude']:.1f}"
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
    straightness = [(_endpoint_distance(line) / max(line.length, 1e-9)) for line in borders]
    complexity = [max(len(line.coords) - 2, 0) / max(line.length, 1e-9) for line in borders]
    compactness = [
        (4.0 * np.pi * polygon.area) / max(polygon.length**2, 1e-9)
        for polygon in polygons.values()
        if polygon.area > 0
    ]
    return {
        "border_count": float(len(borders)),
        "mean_straightness": float(np.mean(straightness)) if straightness else 0.0,
        "mean_complexity": float(np.mean(complexity)) if complexity else 0.0,
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
    roughened: dict[str, float],
) -> str:
    straightness_delta = roughened["mean_straightness"] - baseline["mean_straightness"]
    complexity_delta = roughened["mean_complexity"] - baseline["mean_complexity"]
    compactness_delta = roughened["mean_compactness"] - baseline["mean_compactness"]
    return "\n".join(
        [
            f"Roughened border demo summary: seed={seed} resolution={resolution}",
            (
                "baseline:"
                f" borders={int(baseline['border_count'])}"
                f" straightness={baseline['mean_straightness']:.4f}"
                f" complexity={baseline['mean_complexity']:.4f}"
                f" compactness={baseline['mean_compactness']:.4f}"
            ),
            (
                "roughened:"
                f" borders={int(roughened['border_count'])}"
                f" straightness={roughened['mean_straightness']:.4f}"
                f" complexity={roughened['mean_complexity']:.4f}"
                f" compactness={roughened['mean_compactness']:.4f}"
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
