"""Raster shared-border roughening using 1D spectral noise."""

from __future__ import annotations

from collections import Counter

import numpy as np
from scipy.ndimage import label as scipy_label

from dcel_builder.noise import derive_seed, spectral_noise_1d


def roughen_borders(
    label_map: np.ndarray,
    *,
    continent_mask: np.ndarray | None = None,
    amplitude: float,
    exponent: float,
    master_seed: int,
) -> np.ndarray:
    """Return a copy of ``label_map`` with shared borders roughened in raster space."""
    if amplitude < 0.5:
        return label_map.copy()

    if continent_mask is None:
        continent_mask = label_map >= 0

    result = label_map.copy()
    adjacent_pairs = _find_adjacent_pairs(label_map, continent_mask)

    for label_a, label_b in sorted(adjacent_pairs):
        border_pixels = _extract_border_pixels(result, label_a, label_b)
        if len(border_pixels) < 10:
            continue

        ordered = _order_border_pixels(border_pixels)
        if len(ordered) < 10:
            continue

        noise_seed = derive_seed(master_seed, "roughen", label_a, label_b)
        noise = spectral_noise_1d(len(ordered), exponent, noise_seed)
        peak = float(np.max(np.abs(noise)))
        if peak > 0:
            noise = noise / peak
        noise *= amplitude

        triple_mask = _find_triple_points(result, ordered)
        _taper_noise_at_triples(noise, triple_mask)
        _apply_displacement(result, ordered, noise, label_a, label_b, continent_mask)

    _verify_and_fix_connectivity(result, label_map, continent_mask)
    return result


def _find_adjacent_pairs(
    label_map: np.ndarray,
    continent_mask: np.ndarray,
) -> set[tuple[int, int]]:
    pairs: set[tuple[int, int]] = set()
    for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
        shifted = np.roll(np.roll(label_map, dr, axis=0), dc, axis=1)
        neighbor_land = np.roll(np.roll(continent_mask, dr, axis=0), dc, axis=1)
        mask = (label_map != shifted) & continent_mask & neighbor_land
        if dr == -1:
            mask[0, :] = False
        elif dr == 1:
            mask[-1, :] = False
        if dc == -1:
            mask[:, 0] = False
        elif dc == 1:
            mask[:, -1] = False

        for left, right in zip(label_map[mask].ravel(), shifted[mask].ravel(), strict=False):
            if left >= 0 and right >= 0 and left != right:
                pairs.add((min(int(left), int(right)), max(int(left), int(right))))
    return pairs


def _extract_border_pixels(
    label_map: np.ndarray,
    label_a: int,
    label_b: int,
) -> list[tuple[int, int]]:
    height, width = label_map.shape
    mask_a = label_map == label_a
    border: list[tuple[int, int]] = []
    rows, cols = np.where(mask_a)
    for row, col in zip(rows, cols, strict=False):
        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nr, nc = row + dr, col + dc
            if 0 <= nr < height and 0 <= nc < width and label_map[nr, nc] == label_b:
                border.append((int(row), int(col)))
                break
    return border


def _order_border_pixels(pixels: list[tuple[int, int]]) -> list[tuple[int, int]]:
    if not pixels:
        return []

    remaining = set(range(len(pixels)))
    ordered = [0]
    remaining.remove(0)

    while remaining:
        last_row, last_col = pixels[ordered[-1]]
        best_idx = None
        best_distance = float("inf")
        for idx in remaining:
            row, col = pixels[idx]
            distance = abs(row - last_row) + abs(col - last_col)
            if distance < best_distance:
                best_distance = distance
                best_idx = idx
            if distance <= 1:
                break
        if best_idx is None or best_distance > 3:
            break
        ordered.append(best_idx)
        remaining.remove(best_idx)

    return [pixels[idx] for idx in ordered]


def _find_triple_points(
    label_map: np.ndarray,
    border: list[tuple[int, int]],
) -> np.ndarray:
    height, width = label_map.shape
    triple_mask = np.zeros(len(border), dtype=bool)
    for idx, (row, col) in enumerate(border):
        neighbors: set[int] = set()
        for dr in range(-2, 3):
            for dc in range(-2, 3):
                nr, nc = row + dr, col + dc
                if 0 <= nr < height and 0 <= nc < width:
                    label_value = int(label_map[nr, nc])
                    if label_value >= 0:
                        neighbors.add(label_value)
        if len(neighbors) > 2:
            triple_mask[idx] = True
    return triple_mask


def _taper_noise_at_triples(noise: np.ndarray, triple_mask: np.ndarray) -> None:
    taper = np.ones(len(noise), dtype=np.float64)
    taper_distance = min(10, len(noise) // 4)
    if taper_distance < 1:
        return
    for idx, is_triple in enumerate(triple_mask):
        if not is_triple:
            continue
        start = max(0, idx - taper_distance)
        stop = min(len(noise), idx + taper_distance + 1)
        for inner in range(start, stop):
            distance = abs(inner - idx) / taper_distance
            taper[inner] = min(taper[inner], distance)
    noise *= taper


def _apply_displacement(
    label_map: np.ndarray,
    border: list[tuple[int, int]],
    noise: np.ndarray,
    label_a: int,
    label_b: int,
    continent_mask: np.ndarray,
) -> None:
    height, width = label_map.shape
    for idx, (row, col) in enumerate(border):
        displacement = float(noise[idx])
        if abs(displacement) < 0.5:
            continue

        tangent = _local_tangent(border, idx)
        if tangent is None:
            continue
        dr, dc = tangent
        norm = float(np.hypot(dr, dc))
        if norm < 1e-9:
            continue
        normal_x = -dc / norm
        normal_y = dr / norm

        for step in range(1, int(abs(displacement)) + 1):
            nr = int(round(row + normal_y * step * np.sign(displacement)))
            nc = int(round(col + normal_x * step * np.sign(displacement)))
            if 0 <= nr < height and 0 <= nc < width and continent_mask[nr, nc]:
                current = int(label_map[nr, nc])
                if displacement > 0 and current == label_b:
                    label_map[nr, nc] = label_a
                elif displacement < 0 and current == label_a:
                    label_map[nr, nc] = label_b


def _local_tangent(
    border: list[tuple[int, int]],
    idx: int,
) -> tuple[int, int] | None:
    if idx > 0 and idx < len(border) - 1:
        return (
            border[idx + 1][0] - border[idx - 1][0],
            border[idx + 1][1] - border[idx - 1][1],
        )
    if idx == 0 and len(border) > 1:
        return (
            border[1][0] - border[0][0],
            border[1][1] - border[0][1],
        )
    if idx == len(border) - 1 and len(border) > 1:
        return (
            border[-1][0] - border[-2][0],
            border[-1][1] - border[-2][1],
        )
    return None


def _verify_and_fix_connectivity(
    result: np.ndarray,
    original: np.ndarray,
    continent_mask: np.ndarray,
) -> None:
    labels = set(int(value) for value in np.unique(result[continent_mask]))
    labels.discard(-1)

    for label_value in labels:
        region = result == label_value
        labeled, n_components = scipy_label(region)
        if n_components <= 1:
            continue
        sizes = np.bincount(labeled.ravel())
        sizes[0] = 0
        largest_component = int(np.argmax(sizes))
        revert_mask = region & (labeled != largest_component)
        result[revert_mask] = original[revert_mask]

    _fill_holes_from_neighbors(result, continent_mask)


def _fill_holes_from_neighbors(label_map: np.ndarray, continent_mask: np.ndarray) -> None:
    while True:
        rows, cols = np.where(continent_mask & (label_map < 0))
        if len(rows) == 0:
            return
        changed = False
        for row, col in zip(rows, cols, strict=False):
            neighbors = [
                int(label_map[nr, nc])
                for nr, nc in [
                    (row - 1, col),
                    (row + 1, col),
                    (row, col - 1),
                    (row, col + 1),
                ]
                if 0 <= nr < label_map.shape[0]
                and 0 <= nc < label_map.shape[1]
                and label_map[nr, nc] >= 0
            ]
            if not neighbors:
                continue
            label_map[row, col] = Counter(neighbors).most_common(1)[0][0]
            changed = True
        if not changed:
            return
