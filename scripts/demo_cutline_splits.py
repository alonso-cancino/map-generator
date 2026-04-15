from __future__ import annotations

import argparse
import heapq
from collections import Counter
from pathlib import Path

import matplotlib
import numpy as np
from matplotlib.collections import PolyCollection
from scipy.ndimage import distance_transform_edt
from shapely.geometry import LineString, MultiLineString, Polygon

matplotlib.use("Agg")

import matplotlib.pyplot as plt

from dcel_builder.geometry import face_polygon_coords
from dcel_builder.hierarchy import (
    MAX_AUTO_RESOLUTION,
    OCEAN,
    HierarchyBuildResult,
    ResolutionTooLowError,
    _area_stats,
    _effective_resolution,
    _generate_continent_mask,
    _mean_face_area,
    _minimum_child_pixels,
    _neighbor_coords,
    _populate_face_areas_from_pixels,
    _subtree_leaf_counts,
    _weighted_targets,
)
from dcel_builder.noise import derive_seed, spectral_noise_2d
from dcel_builder.raster_dcel import build_dcel_from_label_map
from dcel_builder.render import _zone_color
from dcel_builder.tree_loader import ZoneTree, load_tree_inputs

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ZONE_EDGES = REPO_ROOT / "examples" / "atlantis" / "zone_edges.json"
DEFAULT_TREE_STATS = REPO_ROOT / "examples" / "atlantis" / "zone_tree_stats.json"
DEFAULT_ZONE_INDEX = REPO_ROOT / "examples" / "atlantis" / "zone_index.json"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "local" / "cutline_demo"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare the default seeded splitter against a cut-line band-growth demo."
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

    from dcel_builder.hierarchy import build_leaf_dcel_from_tree

    baseline = build_leaf_dcel_from_tree(
        tree=tree,
        seed=args.seed,
        resolution=args.resolution,
        land_fraction=args.land_fraction,
        noise_exponent=args.noise_exponent,
        warp_strength=args.warp_strength,
    )
    experimental = build_leaf_dcel_with_cutline_splits(
        tree=tree,
        seed=args.seed,
        resolution=args.resolution,
        land_fraction=args.land_fraction,
        noise_exponent=args.noise_exponent,
        warp_strength=args.warp_strength,
    )

    baseline_path = output_dir / "baseline_seeded.png"
    experimental_path = output_dir / "experimental_cutline.png"
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
            f"Experimental cut-line split\n"
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


def build_leaf_dcel_with_cutline_splits(
    tree: ZoneTree,
    seed: int | None,
    resolution: int,
    land_fraction: float,
    noise_exponent: float,
    warp_strength: float,
) -> HierarchyBuildResult:
    master_seed = 42 if seed is None else int(seed)
    resolution = _effective_resolution(resolution, len(tree.leaves))
    sorted_leaves = tuple(sorted(tree.leaves))
    leaf_label_by_zone = {zone_id: i for i, zone_id in enumerate(sorted_leaves)}
    subtree_leaf_counts = _subtree_leaf_counts(tree)

    while True:
        continent_mask = _generate_continent_mask(
            resolution=resolution,
            land_fraction=land_fraction,
            noise_exponent=noise_exponent,
            warp_strength=warp_strength,
            master_seed=master_seed,
        )
        label_map = np.full((resolution, resolution), OCEAN, dtype=np.int32)
        leaf_pixel_counts: dict[int, int] = {}
        split_reports: list[dict[str, int | float]] = []

        try:
            _partition_node_with_cutlines(
                tree=tree,
                node_id=tree.root,
                parent_mask=continent_mask,
                label_map=label_map,
                leaf_label_by_zone=leaf_label_by_zone,
                leaf_pixel_counts=leaf_pixel_counts,
                master_seed=master_seed,
                split_reports=split_reports,
                subtree_leaf_counts=subtree_leaf_counts,
            )
            break
        except ResolutionTooLowError:
            if resolution >= MAX_AUTO_RESOLUTION:
                raise
            resolution = min(MAX_AUTO_RESOLUTION, resolution * 2)

    dcel = build_dcel_from_label_map(label_map, leaf_label_by_zone, leaf_pixel_counts)
    _populate_face_areas_from_pixels(
        dcel=dcel,
        leaf_pixel_counts=leaf_pixel_counts,
        continent_pixels=int(continent_mask.sum()),
    )
    target_area = _mean_face_area(dcel)
    for face in dcel.faces:
        if not face.is_outer:
            face.target_area = target_area

    interior_areas = [face.area for face in dcel.faces if not face.is_outer]
    report = {
        "root_id": tree.root,
        "node_count": len(tree.nodes),
        "leaf_count": len(sorted_leaves),
        "max_depth": tree.max_depth,
        "level_counts": dict(Counter(tree.depth.values())),
        "resolution": resolution,
        "continent_pixels": int(continent_mask.sum()),
        "leaf_pixel_counts": leaf_pixel_counts,
        "leaf_area_stats": _area_stats(np.array(interior_areas, dtype=np.float64)),
        "min_size_ratio": _minimum_child_pixels(
            int(continent_mask.sum()),
            max(1, len(tree.children)),
        ),
        "target_strategy": "recursive_cutline_bands",
        "split_reports": split_reports,
        "smallest_leaf_pixels": min(leaf_pixel_counts.values(), default=0),
    }
    return HierarchyBuildResult(
        dcel=dcel,
        label_map=label_map,
        leaf_label_by_zone=leaf_label_by_zone,
        report=report,
    )


def _partition_node_with_cutlines(
    *,
    tree: ZoneTree,
    node_id: int,
    parent_mask: np.ndarray,
    label_map: np.ndarray,
    leaf_label_by_zone: dict[int, int],
    leaf_pixel_counts: dict[int, int],
    master_seed: int,
    split_reports: list[dict[str, int | float]],
    subtree_leaf_counts: dict[int, int],
) -> None:
    children = tree.children[node_id]
    if not children:
        label_map[parent_mask] = leaf_label_by_zone[node_id]
        leaf_pixel_counts[node_id] = int(parent_mask.sum())
        return

    partitions = _split_child_group(
        parent_mask=parent_mask,
        child_ids=list(children),
        child_weights=[subtree_leaf_counts[child] for child in children],
        split_seed=derive_seed(master_seed, node_id, "cutline"),
    )
    split_reports.append(
        {
            "node_id": node_id,
            "child_count": len(children),
            "parent_pixels": int(parent_mask.sum()),
            "min_child_pixels": min(int(mask.sum()) for mask in partitions.values()),
            "required_min_pixels": _minimum_child_pixels(int(parent_mask.sum()), len(children)),
        }
    )
    for child, child_mask in partitions.items():
        _partition_node_with_cutlines(
            tree=tree,
            node_id=child,
            parent_mask=child_mask,
            label_map=label_map,
            leaf_label_by_zone=leaf_label_by_zone,
            leaf_pixel_counts=leaf_pixel_counts,
            master_seed=master_seed,
            split_reports=split_reports,
            subtree_leaf_counts=subtree_leaf_counts,
        )


def _split_child_group(
    *,
    parent_mask: np.ndarray,
    child_ids: list[int],
    child_weights: list[int],
    split_seed: int,
) -> dict[int, np.ndarray]:
    if len(child_ids) == 1:
        return {child_ids[0]: parent_mask.copy()}
    if int(parent_mask.sum()) < len(child_ids):
        raise ResolutionTooLowError("Parent region is too small to split into child regions.")

    if len(child_ids) == 2:
        left_mask, right_mask = _split_mask_with_cutline_bands(
            parent_mask=parent_mask,
            weights=child_weights,
            split_seed=split_seed,
        )
        return {child_ids[0]: left_mask, child_ids[1]: right_mask}

    left_group, right_group = _balanced_child_groups(child_ids, child_weights)
    left_ids, left_weights = left_group
    right_ids, right_weights = right_group
    left_mask, right_mask = _split_mask_with_cutline_bands(
        parent_mask=parent_mask,
        weights=[sum(left_weights), sum(right_weights)],
        split_seed=split_seed,
    )
    partitions = _split_child_group(
        parent_mask=left_mask,
        child_ids=left_ids,
        child_weights=left_weights,
        split_seed=derive_seed(split_seed, "left"),
    )
    partitions.update(
        _split_child_group(
            parent_mask=right_mask,
            child_ids=right_ids,
            child_weights=right_weights,
            split_seed=derive_seed(split_seed, "right"),
        )
    )
    return partitions


def _balanced_child_groups(
    child_ids: list[int],
    child_weights: list[int],
) -> tuple[tuple[list[int], list[int]], tuple[list[int], list[int]]]:
    ordered = sorted(
        zip(child_ids, child_weights, strict=False),
        key=lambda item: (item[1], item[0]),
        reverse=True,
    )
    left_ids: list[int] = []
    left_weights: list[int] = []
    right_ids: list[int] = []
    right_weights: list[int] = []
    left_total = 0
    right_total = 0
    for child_id, weight in ordered:
        if len(left_ids) == 0:
            left_ids.append(child_id)
            left_weights.append(weight)
            left_total += weight
            continue
        if len(right_ids) == 0:
            right_ids.append(child_id)
            right_weights.append(weight)
            right_total += weight
            continue
        if left_total <= right_total:
            left_ids.append(child_id)
            left_weights.append(weight)
            left_total += weight
        else:
            right_ids.append(child_id)
            right_weights.append(weight)
            right_total += weight
    return (left_ids, left_weights), (right_ids, right_weights)


def _split_mask_with_cutline_bands(
    *,
    parent_mask: np.ndarray,
    weights: list[int],
    split_seed: int,
) -> tuple[np.ndarray, np.ndarray]:
    total_pixels = int(parent_mask.sum())
    if total_pixels < 2:
        raise ResolutionTooLowError("Parent region is too small to split.")

    targets = _weighted_targets(total_pixels, weights)
    coords = np.argwhere(parent_mask)
    scores = _cutline_scores(parent_mask, coords, split_seed)
    band_size = max(4, min(total_pixels // 24, total_pixels // 2))
    ordered = np.argsort(scores, kind="stable")
    left_anchor_indices = ordered[:band_size]
    right_anchor_indices = ordered[-band_size:]

    ownership = np.full(parent_mask.shape, -1, dtype=np.int8)
    frontier = {0: [], 1: []}
    assigned = [0, 0]
    tie_break = 0
    noise_field = spectral_noise_2d(parent_mask.shape[0], 3.3, derive_seed(split_seed, "frontier"))
    score_map = np.full(parent_mask.shape, np.nan, dtype=np.float64)
    for (row, col), score in zip(coords, scores, strict=False):
        score_map[row, col] = score

    for idx in left_anchor_indices:
        row, col = (int(v) for v in coords[idx])
        if ownership[row, col] == -1:
            ownership[row, col] = 0
            assigned[0] += 1
    for idx in right_anchor_indices[::-1]:
        row, col = (int(v) for v in coords[idx])
        if ownership[row, col] == -1:
            ownership[row, col] = 1
            assigned[1] += 1

    side_reference = [
        float(np.mean(scores[left_anchor_indices])),
        float(np.mean(scores[right_anchor_indices])),
    ]
    for side in (0, 1):
        rows, cols = np.where(ownership == side)
        for row, col in zip(rows, cols, strict=False):
            for nr, nc in _neighbor_coords(row, col, ownership.shape):
                if not parent_mask[nr, nc] or ownership[nr, nc] != -1:
                    continue
                tie_break += 1
                heapq.heappush(
                    frontier[side],
                    (
                        _cutline_candidate_cost(
                            nr,
                            nc,
                            score_map,
                            side_reference[side],
                            noise_field,
                        ),
                        tie_break,
                        nr,
                        nc,
                    ),
                )

    remaining = total_pixels - sum(assigned)
    while remaining > 0:
        active = [side for side in (0, 1) if assigned[side] < targets[side] and frontier[side]]
        if not active:
            active = [side for side in (0, 1) if frontier[side]]
        if not active:
            break
        side = min(
            active,
            key=lambda item: (assigned[item] / max(targets[item], 1), assigned[item]),
        )
        placed = False
        while frontier[side]:
            _, _, row, col = heapq.heappop(frontier[side])
            if ownership[row, col] != -1 or not parent_mask[row, col]:
                continue
            if not _touches_side(ownership, row, col, side):
                continue
            ownership[row, col] = side
            assigned[side] += 1
            remaining -= 1
            for nr, nc in _neighbor_coords(row, col, ownership.shape):
                if not parent_mask[nr, nc] or ownership[nr, nc] != -1:
                    continue
                tie_break += 1
                heapq.heappush(
                    frontier[side],
                    (
                        _cutline_candidate_cost(
                            nr,
                            nc,
                            score_map,
                            side_reference[side],
                            noise_field,
                        ),
                        tie_break,
                        nr,
                        nc,
                    ),
                )
            placed = True
            break
        if not placed:
            frontier[side].clear()

    if remaining > 0:
        _fill_unassigned_by_neighbors(parent_mask, ownership)
    left_mask = ownership == 0
    left_mask = _repair_side_connectivity(left_mask, parent_mask)
    right_mask = parent_mask & ~left_mask
    right_mask = _repair_side_connectivity(right_mask, parent_mask)
    left_mask = parent_mask & ~right_mask

    if int(left_mask.sum()) == 0 or int(right_mask.sum()) == 0:
        raise ResolutionTooLowError("Cut-line split produced an empty child region.")
    return left_mask, right_mask


def _cutline_scores(
    parent_mask: np.ndarray,
    coords: np.ndarray,
    split_seed: int,
) -> np.ndarray:
    center = coords.mean(axis=0)
    centered = coords - center
    covariance = np.cov(centered.T)
    eigenvalues, eigenvectors = np.linalg.eigh(covariance)
    axis = eigenvectors[:, int(np.argmax(eigenvalues))]
    normal = np.array([-axis[1], axis[0]])
    base_projection = centered @ normal

    field = spectral_noise_2d(
        parent_mask.shape[0],
        2.9,
        derive_seed(split_seed, "cutline", "field"),
    )
    warp = spectral_noise_2d(
        parent_mask.shape[0],
        3.8,
        derive_seed(split_seed, "cutline", "warp"),
    )
    boundary_distance = distance_transform_edt(parent_mask)
    boundary_term = boundary_distance[coords[:, 0], coords[:, 1]]
    if float(boundary_term.max()) > 0:
        boundary_term = boundary_term / float(boundary_term.max())

    local_field = field[coords[:, 0], coords[:, 1]] - 0.5
    local_warp = warp[coords[:, 0], coords[:, 1]] - 0.5
    return (
        base_projection
        + local_field * parent_mask.shape[0] * 0.14
        + local_warp * 6.0
        - boundary_term * 3.5
    )


def _cutline_candidate_cost(
    row: int,
    col: int,
    score_map: np.ndarray,
    side_reference: float,
    noise_field: np.ndarray,
) -> float:
    contour_cost = abs(float(score_map[row, col]) - side_reference)
    jitter = abs(float(noise_field[row, col]) - 0.5) * 0.35
    return contour_cost + jitter


def _touches_side(ownership: np.ndarray, row: int, col: int, side: int) -> bool:
    for nr, nc in _neighbor_coords(row, col, ownership.shape):
        if ownership[nr, nc] == side:
            return True
    return False


def _fill_unassigned_by_neighbors(parent_mask: np.ndarray, ownership: np.ndarray) -> None:
    while True:
        changed = False
        rows, cols = np.where(parent_mask & (ownership == -1))
        if len(rows) == 0:
            return
        for row, col in zip(rows, cols, strict=False):
            neighbors = [
                ownership[nr, nc]
                for nr, nc in _neighbor_coords(row, col, ownership.shape)
                if ownership[nr, nc] >= 0
            ]
            if not neighbors:
                continue
            ownership[row, col] = Counter(neighbors).most_common(1)[0][0]
            changed = True
        if not changed:
            raise ResolutionTooLowError("Could not assign all pixels during cut-line split.")


def _repair_side_connectivity(mask: np.ndarray, parent_mask: np.ndarray) -> np.ndarray:
    coords = np.argwhere(mask)
    if coords.size == 0:
        return mask
    labeled, count = _connected_components(mask)
    if count <= 1:
        return mask
    sizes = np.bincount(labeled.ravel())
    sizes[0] = 0
    keep = int(np.argmax(sizes))
    repaired = labeled == keep
    return repaired & parent_mask


def _connected_components(mask: np.ndarray) -> tuple[np.ndarray, int]:
    labels = np.zeros(mask.shape, dtype=np.int32)
    current = 0
    for row, col in np.argwhere(mask):
        row = int(row)
        col = int(col)
        if labels[row, col] != 0:
            continue
        current += 1
        stack = [(row, col)]
        labels[row, col] = current
        while stack:
            cr, cc = stack.pop()
            for nr, nc in _neighbor_coords(cr, cc, mask.shape):
                if mask[nr, nc] and labels[nr, nc] == 0:
                    labels[nr, nc] = current
                    stack.append((nr, nc))
    return labels, current


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
            f"Experimental cut-line split\n"
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
    compactness = [
        (4.0 * np.pi * polygon.area) / max(polygon.length**2, 1e-9)
        for polygon in polygons.values()
        if polygon.area > 0
    ]
    border_lengths = [line.length for line in borders]
    return {
        "border_count": float(len(borders)),
        "mean_compactness": float(np.mean(compactness)) if compactness else 0.0,
        "median_border_length": float(np.median(border_lengths)) if border_lengths else 0.0,
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


def _format_summary(
    seed: int,
    resolution: int,
    baseline: dict[str, float],
    experimental: dict[str, float],
) -> str:
    compactness_delta = experimental["mean_compactness"] - baseline["mean_compactness"]
    border_length_delta = (
        experimental["median_border_length"] - baseline["median_border_length"]
    )
    return "\n".join(
        [
            f"Cut-line split demo summary: seed={seed} resolution={resolution}",
            (
                "baseline:"
                f" borders={int(baseline['border_count'])}"
                f" compactness={baseline['mean_compactness']:.4f}"
                f" median_border_length={baseline['median_border_length']:.4f}"
            ),
            (
                "experimental:"
                f" borders={int(experimental['border_count'])}"
                f" compactness={experimental['mean_compactness']:.4f}"
                f" median_border_length={experimental['median_border_length']:.4f}"
            ),
            (
                "delta:"
                f" compactness={compactness_delta:+.4f}"
                f" median_border_length={border_length_delta:+.4f}"
            ),
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
