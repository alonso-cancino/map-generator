"""Recursive tree-driven raster partitioning."""

from __future__ import annotations

import heapq
import math
from collections import Counter
from dataclasses import dataclass

import numpy as np
from scipy.ndimage import (
    binary_closing,
    binary_opening,
    distance_transform_edt,
    gaussian_filter,
    map_coordinates,
)
from scipy.ndimage import (
    label as cc_label,
)

from dcel_builder.dcel import DCEL
from dcel_builder.noise import derive_seed, spectral_noise_2d
from dcel_builder.raster_dcel import build_dcel_from_label_map
from dcel_builder.tree_loader import ZoneTree

OCEAN = -1
NEIGHBORS_4 = [(-1, 0), (1, 0), (0, -1), (0, 1)]
MIN_CHILD_RATIO = 0.45
MAX_AUTO_RESOLUTION = 1024


class ResolutionTooLowError(ValueError):
    """Raised when the recursive split cannot satisfy local size floors."""


@dataclass
class HierarchyBuildResult:
    """Output of the recursive hierarchy generator."""

    dcel: DCEL
    label_map: np.ndarray
    leaf_label_by_zone: dict[int, int]
    report: dict


def build_leaf_dcel_from_tree(
    tree: ZoneTree,
    seed: int | None,
    resolution: int,
    land_fraction: float,
    noise_exponent: float,
    warp_strength: float,
    split_mode: str = "seeded",
) -> HierarchyBuildResult:
    """Generate a recursive leaf tessellation and convert it to a DCEL."""
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
            _partition_node(
                tree=tree,
                node_id=tree.root,
                parent_mask=continent_mask,
                label_map=label_map,
                leaf_label_by_zone=leaf_label_by_zone,
                leaf_pixel_counts=leaf_pixel_counts,
                master_seed=master_seed,
                split_reports=split_reports,
                subtree_leaf_counts=subtree_leaf_counts,
                split_mode=split_mode,
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
        "min_size_ratio": MIN_CHILD_RATIO,
        "target_strategy": f"subtree_leaf_weighted_with_parent_floor:{split_mode}",
        "split_mode": split_mode,
        "split_reports": split_reports,
        "smallest_leaf_pixels": min(leaf_pixel_counts.values(), default=0),
    }
    return HierarchyBuildResult(
        dcel=dcel,
        label_map=label_map,
        leaf_label_by_zone=leaf_label_by_zone,
        report=report,
    )


def _partition_node(
    tree: ZoneTree,
    node_id: int,
    parent_mask: np.ndarray,
    label_map: np.ndarray,
    leaf_label_by_zone: dict[int, int],
    leaf_pixel_counts: dict[int, int],
    master_seed: int,
    split_reports: list[dict[str, int | float]],
    subtree_leaf_counts: dict[int, int],
    split_mode: str,
) -> None:
    children = tree.children[node_id]
    if not children:
        label_map[parent_mask] = leaf_label_by_zone[node_id]
        leaf_pixel_counts[node_id] = int(parent_mask.sum())
        return

    partitions = _split_mask_among_children(
        parent_mask=parent_mask,
        children=children,
        child_leaf_counts=[subtree_leaf_counts[child] for child in children],
        split_seed=derive_seed(master_seed, node_id, "split"),
        split_mode=split_mode,
        depth=tree.depth[node_id],
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
        _partition_node(
            tree=tree,
            node_id=child,
            parent_mask=child_mask,
            label_map=label_map,
            leaf_label_by_zone=leaf_label_by_zone,
            leaf_pixel_counts=leaf_pixel_counts,
            master_seed=master_seed,
            split_reports=split_reports,
            subtree_leaf_counts=subtree_leaf_counts,
            split_mode=split_mode,
        )


def _split_mask_among_children(
    parent_mask: np.ndarray,
    children: tuple[int, ...],
    child_leaf_counts: list[int],
    split_seed: int,
    split_mode: str = "seeded",
    depth: int = 0,
) -> dict[int, np.ndarray]:
    total_pixels = int(parent_mask.sum())
    if total_pixels < len(children):
        raise ResolutionTooLowError(
            f"Parent region is too small to split into {len(children)} child regions."
        )

    rng = np.random.default_rng(split_seed % (2**63))
    targets = _weighted_targets(total_pixels, child_leaf_counts)
    ownership = np.full(parent_mask.shape, -1, dtype=np.int16)
    frontier: dict[int, list[tuple[float, int, int]]] = {idx: [] for idx in range(len(children))}
    assigned = [0 for _ in children]
    noise_field = spectral_noise_2d(parent_mask.shape[0], 2.6, derive_seed(split_seed, "noise"))
    guide_field = None
    guide_gradient = None
    contour_cost = None
    candidate_cost = _candidate_cost_seeded
    if split_mode == "contour_guided":
        contour_cost = _split_contour_cost_field(parent_mask.shape[0], split_seed, depth)
        seed_pixels = _select_seed_pixels_contour(
            parent_mask,
            len(children),
            rng,
            contour_cost,
            depth=depth,
        )
        candidate_cost = _candidate_cost_contour_guided
    elif split_mode == "field_guided":
        seed_pixels = _select_seed_pixels(parent_mask, len(children), rng)
        guide_field, guide_gradient = _split_guide_field(parent_mask.shape[0], split_seed)
        candidate_cost = _candidate_cost_field_guided
    elif split_mode == "seeded":
        seed_pixels = _select_seed_pixels(parent_mask, len(children), rng)
    else:
        raise ValueError(f"Unknown split mode: {split_mode}")
    tie_break = 0

    for idx, (row, col) in enumerate(seed_pixels):
        ownership[row, col] = idx
        assigned[idx] = 1

    for idx, (row, col) in enumerate(seed_pixels):
        for nr, nc in _neighbor_coords(row, col, parent_mask.shape):
            if not parent_mask[nr, nc] or ownership[nr, nc] != -1:
                continue
            tie_break += 1
            heapq.heappush(
                frontier[idx],
                (
                    candidate_cost(
                        nr,
                        nc,
                        seed_pixels[idx],
                        noise_field,
                        guide_field=guide_field,
                        guide_gradient=guide_gradient,
                        contour_cost=contour_cost,
                        depth=depth,
                    ),
                    tie_break,
                    nr,
                    nc,
                ),
            )

    remaining = total_pixels - len(children)
    while remaining > 0:
        active = [
            idx
            for idx in range(len(children))
            if assigned[idx] < targets[idx] and frontier[idx]
        ]
        if not active:
            active = [idx for idx in range(len(children)) if frontier[idx]]
        if not active:
            break

        child_idx = min(
            active,
            key=lambda idx: (assigned[idx] / max(targets[idx], 1), assigned[idx], idx),
        )

        placed = False
        while frontier[child_idx]:
            _, _, row, col = heapq.heappop(frontier[child_idx])
            if ownership[row, col] != -1 or not parent_mask[row, col]:
                continue
            if not _touches_region(ownership, row, col, child_idx):
                continue
            ownership[row, col] = child_idx
            assigned[child_idx] += 1
            remaining -= 1
            for nr, nc in _neighbor_coords(row, col, parent_mask.shape):
                if not parent_mask[nr, nc] or ownership[nr, nc] != -1:
                    continue
                tie_break += 1
                heapq.heappush(
                    frontier[child_idx],
                    (
                        candidate_cost(
                            nr,
                            nc,
                            seed_pixels[child_idx],
                            noise_field,
                            guide_field=guide_field,
                            guide_gradient=guide_gradient,
                            contour_cost=contour_cost,
                            depth=depth,
                        ),
                        tie_break,
                        nr,
                        nc,
                    ),
                )
            placed = True
            break

        if not placed:
            frontier[child_idx].clear()

    if remaining > 0:
        _fill_unassigned_pixels(parent_mask, ownership)

    partitions: dict[int, np.ndarray] = {}
    for idx, child in enumerate(children):
        raw_mask = ownership == idx
        partitions[child] = raw_mask

    if sum(int(mask.sum()) for mask in partitions.values()) != total_pixels:
        raise ValueError("Recursive partition lost coverage inside the parent mask.")
    return partitions


def _select_seed_pixels(
    mask: np.ndarray,
    count: int,
    rng: np.random.Generator,
) -> list[tuple[int, int]]:
    coords = np.argwhere(mask)
    if coords.shape[0] < count:
        raise ValueError("Not enough land pixels to place child seeds.")

    if coords.shape[0] > 5000:
        sample_idx = rng.choice(coords.shape[0], size=5000, replace=False)
        coords = coords[sample_idx]

    boundary_distance = distance_transform_edt(mask)
    base_scores = np.array(
        [boundary_distance[row, col] for row, col in coords],
        dtype=np.float64,
    )
    base_scores += rng.random(len(coords)) * 0.25

    chosen: list[tuple[int, int]] = []
    first_idx = int(np.argmax(base_scores))
    chosen.append(tuple(int(v) for v in coords[first_idx]))

    for _ in range(1, count):
        best_score = -math.inf
        best_coord = None
        for row, col in coords:
            coord = (int(row), int(col))
            if coord in chosen:
                continue
            min_sq_dist = min((row - cr) ** 2 + (col - cc) ** 2 for cr, cc in chosen)
            score = min_sq_dist * (1.0 + 0.25 * boundary_distance[row, col])
            if score > best_score:
                best_score = score
                best_coord = coord
        assert best_coord is not None
        chosen.append(best_coord)

    return chosen


def _select_seed_pixels_contour(
    mask: np.ndarray,
    count: int,
    rng: np.random.Generator,
    contour_cost: np.ndarray,
    *,
    depth: int,
) -> list[tuple[int, int]]:
    coords = np.argwhere(mask)
    if coords.shape[0] < count:
        raise ValueError("Not enough land pixels to place child seeds.")

    if coords.shape[0] > 5000:
        sample_idx = rng.choice(coords.shape[0], size=5000, replace=False)
        coords = coords[sample_idx]

    boundary_distance = distance_transform_edt(mask)
    boundary_values = np.array(
        [boundary_distance[row, col] for row, col in coords],
        dtype=np.float64,
    )
    if float(boundary_values.max()) > 0:
        boundary_values = boundary_values / float(boundary_values.max())
    contour_values = np.array([contour_cost[row, col] for row, col in coords], dtype=np.float64)

    # Prefer seeds away from the deepest center and away from the hard coastline,
    # while still sitting near low-cost contour channels.
    target_band = 0.34 if depth == 0 else 0.40 if depth == 1 else 0.46
    middle_band = 1.0 - np.abs(boundary_values - target_band) / max(target_band, 1e-6)
    middle_band = np.clip(middle_band, 0.0, 1.0)
    contour_weight = 0.55 if depth == 0 else 0.40 if depth == 1 else 0.25
    first_scores = middle_band * (1.0 - contour_weight) + (1.0 - contour_values) * contour_weight
    first_scores += rng.random(len(coords)) * 0.15

    chosen: list[tuple[int, int]] = []
    first_idx = int(np.argmax(first_scores))
    chosen.append(tuple(int(v) for v in coords[first_idx]))

    for _ in range(1, count):
        best_score = -math.inf
        best_coord = None
        for coord_idx, (row, col) in enumerate(coords):
            coord = (int(row), int(col))
            if coord in chosen:
                continue
            min_sq_dist = min((row - cr) ** 2 + (col - cc) ** 2 for cr, cc in chosen)
            spacing = math.sqrt(min_sq_dist)
            spacing_weight = 1.25 if depth == 0 else 1.0 if depth == 1 else 0.8
            band_weight = 15.0 if depth == 0 else 11.0 if depth == 1 else 8.0
            contour_score_weight = 12.0 if depth == 0 else 8.0 if depth == 1 else 5.0
            score = (
                spacing * spacing_weight
                + middle_band[coord_idx] * band_weight
                + (1.0 - contour_values[coord_idx]) * contour_score_weight
            )
            if score > best_score:
                best_score = score
                best_coord = coord
        assert best_coord is not None
        chosen.append(best_coord)

    return chosen


def _generate_continent_mask(
    resolution: int,
    land_fraction: float,
    noise_exponent: float,
    warp_strength: float,
    master_seed: int,
) -> np.ndarray:
    base_seed = derive_seed(master_seed, "continent", "base")
    detail_seed = derive_seed(master_seed, "continent", "detail")
    warp_x_seed = derive_seed(master_seed, "continent", "warp_x")
    warp_y_seed = derive_seed(master_seed, "continent", "warp_y")

    base = spectral_noise_2d(resolution, max(noise_exponent + 0.5, 2.8), base_seed)
    detail = spectral_noise_2d(resolution, max(noise_exponent, 2.0), detail_seed)
    heightmap = 0.75 * base + 0.25 * detail
    warped = _apply_domain_warp(heightmap, resolution, warp_strength, warp_x_seed, warp_y_seed)

    falloff = _radial_falloff(resolution, radius=0.78, sharpness=3.2)
    margin = _edge_margin(resolution, width_frac=0.12)
    elevation = gaussian_filter(warped * falloff * margin, sigma=resolution / 200)

    threshold = np.percentile(elevation, 100 * (1 - land_fraction))
    land_mask = elevation > threshold
    morph_radius = max(1, resolution // 200)
    land_mask = binary_closing(land_mask, iterations=morph_radius)
    land_mask = binary_opening(land_mask, iterations=morph_radius)
    land_mask = _largest_component(land_mask)
    return _fill_holes(land_mask)


def _apply_domain_warp(
    heightmap: np.ndarray,
    resolution: int,
    warp_strength: float,
    warp_x_seed: int,
    warp_y_seed: int,
) -> np.ndarray:
    wx = spectral_noise_2d(resolution, 3.0, warp_x_seed)
    wy = spectral_noise_2d(resolution, 3.0, warp_y_seed)
    scale = 2 * warp_strength * resolution
    wx = (wx - 0.5) * scale
    wy = (wy - 0.5) * scale

    rows, cols = np.mgrid[0:resolution, 0:resolution]
    return np.asarray(
        map_coordinates(
            heightmap,
            [(rows + wy) % resolution, (cols + wx) % resolution],
            order=3,
            mode="wrap",
        )
    )


def _radial_falloff(resolution: int, radius: float, sharpness: float) -> np.ndarray:
    axis = np.linspace(-1.0, 1.0, resolution)
    yy, xx = np.meshgrid(axis, axis, indexing="ij")
    dist = np.sqrt(xx**2 + yy**2)
    return 1.0 / (1.0 + (dist / max(radius, 1e-6)) ** (2 * sharpness))


def _edge_margin(resolution: int, width_frac: float) -> np.ndarray:
    width = max(1, int(resolution * width_frac))
    taper = np.ones(resolution, dtype=np.float64)
    ramp = 0.5 * (1 - np.cos(np.linspace(0.0, np.pi, width)))
    taper[:width] = ramp
    taper[-width:] = ramp[::-1]
    return np.outer(taper, taper)


def _fill_holes(mask: np.ndarray) -> np.ndarray:
    ocean = ~mask
    labeled, count = cc_label(ocean)
    if count == 0:
        return mask
    border_labels = (
        set(labeled[0, :])
        | set(labeled[-1, :])
        | set(labeled[:, 0])
        | set(labeled[:, -1])
    )
    border_labels.discard(0)
    real_ocean = np.zeros_like(mask, dtype=bool)
    for ocean_label in border_labels:
        real_ocean |= labeled == ocean_label
    return ~real_ocean


def _largest_component(mask: np.ndarray) -> np.ndarray:
    labeled, count = cc_label(mask)
    if count == 0:
        return mask
    sizes = np.bincount(labeled.ravel())
    sizes[0] = 0
    return labeled == int(np.argmax(sizes))


def _candidate_cost(
    row: int,
    col: int,
    seed: tuple[int, int],
    noise_field: np.ndarray,
) -> float:
    distance = math.hypot(row - seed[0], col - seed[1])
    return distance * 0.03 + float(noise_field[row, col])


def _candidate_cost_seeded(
    row: int,
    col: int,
    seed: tuple[int, int],
    noise_field: np.ndarray,
    *,
    guide_field: np.ndarray | None = None,
    guide_gradient: np.ndarray | None = None,
    contour_cost: np.ndarray | None = None,
    depth: int = 0,
) -> float:
    del guide_field
    del guide_gradient
    del contour_cost
    del depth
    return _candidate_cost(row, col, seed, noise_field)


def _candidate_cost_field_guided(
    row: int,
    col: int,
    seed: tuple[int, int],
    noise_field: np.ndarray,
    *,
    guide_field: np.ndarray | None = None,
    guide_gradient: np.ndarray | None = None,
    contour_cost: np.ndarray | None = None,
    depth: int = 0,
) -> float:
    del contour_cost
    del depth
    if guide_field is None or guide_gradient is None:
        raise ValueError("Field-guided split mode requires guide field inputs.")
    distance = math.hypot(row - seed[0], col - seed[1])
    local_noise = float(noise_field[row, col]) - 0.5
    contour_bias = abs(float(guide_field[row, col]) - 0.5)
    gradient_bias = 1.0 - float(guide_gradient[row, col])
    return distance * 0.02 + local_noise * 0.10 + contour_bias * 0.55 + gradient_bias * 0.35


def _candidate_cost_contour_guided(
    row: int,
    col: int,
    seed: tuple[int, int],
    noise_field: np.ndarray,
    *,
    guide_field: np.ndarray | None = None,
    guide_gradient: np.ndarray | None = None,
    contour_cost: np.ndarray | None = None,
    depth: int = 0,
) -> float:
    del guide_field
    del guide_gradient
    if contour_cost is None:
        raise ValueError("Contour-guided split mode requires contour cost input.")
    distance = math.hypot(row - seed[0], col - seed[1])
    local_noise = abs(float(noise_field[row, col]) - 0.5)
    channel_cost = float(contour_cost[row, col])
    distance_weight = 0.008 if depth == 0 else 0.010 if depth == 1 else 0.013
    channel_weight = 1.25 if depth == 0 else 0.95 if depth == 1 else 0.65
    noise_weight = 0.04 if depth == 0 else 0.06 if depth == 1 else 0.09
    return distance * distance_weight + channel_cost * channel_weight + local_noise * noise_weight


def _split_contour_cost_field(
    resolution: int,
    split_seed: int,
    depth: int,
) -> np.ndarray:
    border_seed = derive_seed(split_seed, "contour", "field")
    border_noise = spectral_noise_2d(resolution, 2.7, border_seed)
    sigma = (
        resolution / 18.0
        if depth == 0
        else resolution / 28.0 if depth == 1 else resolution / 40.0
    )
    smooth = gaussian_filter(border_noise, sigma=max(sigma, 1.0))
    smin = float(smooth.min())
    smax = float(smooth.max())
    if smax > smin:
        smooth = (smooth - smin) / (smax - smin)
    num_contours = 2.5 if depth == 0 else 4.0 if depth == 1 else 6.0
    sharpness = 0.45 if depth == 0 else 0.55 if depth == 1 else 0.70
    contour_channels = np.abs(np.sin(np.pi * num_contours * smooth))
    return np.power(contour_channels, sharpness)


def _split_guide_field(
    resolution: int,
    split_seed: int,
) -> tuple[np.ndarray, np.ndarray]:
    base = spectral_noise_2d(resolution, 3.0, derive_seed(split_seed, "guide", "base"))
    detail = spectral_noise_2d(resolution, 4.2, derive_seed(split_seed, "guide", "detail"))
    warp_x = spectral_noise_2d(resolution, 3.4, derive_seed(split_seed, "guide", "warp_x"))
    warp_y = spectral_noise_2d(resolution, 3.4, derive_seed(split_seed, "guide", "warp_y"))
    field = _warp_field(0.7 * base + 0.3 * detail, resolution, 0.035, warp_x, warp_y)
    grad_y, grad_x = np.gradient(field)
    gradient = np.sqrt(grad_x**2 + grad_y**2)
    if float(gradient.max()) > 0:
        gradient = gradient / float(gradient.max())
    return field, gradient


def _warp_field(
    heightmap: np.ndarray,
    resolution: int,
    warp_strength: float,
    warp_x: np.ndarray,
    warp_y: np.ndarray,
) -> np.ndarray:
    scale = 2 * warp_strength * resolution
    offset_x = (warp_x - 0.5) * scale
    offset_y = (warp_y - 0.5) * scale
    rows, cols = np.mgrid[0:resolution, 0:resolution]
    return np.asarray(
        map_coordinates(
            heightmap,
            [(rows + offset_y) % resolution, (cols + offset_x) % resolution],
            order=3,
            mode="wrap",
        )
    )


def _touches_region(ownership: np.ndarray, row: int, col: int, child_idx: int) -> bool:
    for nr, nc in _neighbor_coords(row, col, ownership.shape):
        if ownership[nr, nc] == child_idx:
            return True
    return False


def _neighbor_coords(row: int, col: int, shape: tuple[int, int]):
    height, width = shape
    for dr, dc in NEIGHBORS_4:
        nr, nc = row + dr, col + dc
        if 0 <= nr < height and 0 <= nc < width:
            yield nr, nc


def _fill_unassigned_pixels(parent_mask: np.ndarray, ownership: np.ndarray) -> None:
    while True:
        changed = False
        rows, cols = np.where(parent_mask & (ownership == -1))
        if len(rows) == 0:
            return
        for row, col in zip(rows, cols, strict=False):
            neighbor_labels = [
                ownership[nr, nc]
                for nr, nc in _neighbor_coords(row, col, ownership.shape)
                if ownership[nr, nc] >= 0
            ]
            if not neighbor_labels:
                continue
            ownership[row, col] = Counter(neighbor_labels).most_common(1)[0][0]
            changed = True
        if not changed:
            raise ValueError("Could not assign all pixels during recursive partition.")


def _integer_targets(total: int, parts: int) -> list[int]:
    base = total // parts
    remainder = total % parts
    return [base + (1 if idx < remainder else 0) for idx in range(parts)]


def _weighted_targets(total: int, weights: list[int]) -> list[int]:
    if not weights:
        return []
    weight_sum = sum(weights)
    if weight_sum <= 0:
        return _integer_targets(total, len(weights))

    raw = [total * weight / weight_sum for weight in weights]
    targets = [max(1, int(math.floor(value))) for value in raw]
    allocated = sum(targets)

    if allocated < total:
        order = sorted(
            range(len(weights)),
            key=lambda idx: (raw[idx] - targets[idx], weights[idx]),
            reverse=True,
        )
        for idx in order[: total - allocated]:
            targets[idx] += 1
    elif allocated > total:
        order = sorted(
            range(len(weights)),
            key=lambda idx: (targets[idx] - raw[idx], weights[idx]),
            reverse=True,
        )
        to_remove = allocated - total
        for idx in order:
            removable = min(to_remove, max(0, targets[idx] - 1))
            targets[idx] -= removable
            to_remove -= removable
            if to_remove == 0:
                break

    return targets


def _minimum_child_pixels(total_pixels: int, child_count: int) -> int:
    equal_target = total_pixels / max(child_count, 1)
    return max(1, int(math.floor(equal_target * MIN_CHILD_RATIO)))




def _populate_face_areas_from_pixels(
    dcel: DCEL,
    leaf_pixel_counts: dict[int, int],
    continent_pixels: int,
) -> None:
    scale = max(continent_pixels, 1)
    for face in dcel.faces:
        if face.is_outer or face.zone_id is None:
            continue
        face.area = leaf_pixel_counts.get(face.zone_id, 0) / scale


def _mean_face_area(dcel: DCEL) -> float:
    areas = [face.area for face in dcel.faces if not face.is_outer]
    if not areas:
        return 0.0
    return float(sum(areas) / len(areas))


def _area_stats(areas: np.ndarray) -> dict[str, float]:
    if areas.size == 0:
        return {"min": 0.0, "max": 0.0, "mean": 0.0, "cv": 0.0, "within_50pct": 0.0}
    mean = float(areas.mean())
    within_50pct = float(np.sum(np.abs(areas - mean) <= mean * 0.5))
    cv = float(areas.std() / mean) if mean > 0 else 0.0
    return {
        "min": float(areas.min()),
        "max": float(areas.max()),
        "mean": mean,
        "cv": cv,
        "within_50pct": within_50pct,
    }


def _effective_resolution(requested: int, leaf_count: int) -> int:
    minimum = 96
    if leaf_count > 128:
        minimum = 256
    elif leaf_count > 32:
        minimum = 160
    return max(int(requested), minimum)


def _subtree_leaf_counts(tree: ZoneTree) -> dict[int, int]:
    counts: dict[int, int] = {}
    for node in sorted(tree.nodes, key=lambda node_id: tree.depth[node_id], reverse=True):
        children = tree.children[node]
        if not children:
            counts[node] = 1
            continue
        counts[node] = sum(counts[child] for child in children)
    return counts
