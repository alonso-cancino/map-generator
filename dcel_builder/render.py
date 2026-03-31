"""Render DCEL geometry to a static PNG."""

from __future__ import annotations

import hashlib
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.collections import PolyCollection

from dcel_builder.dcel import DCEL
from dcel_builder.geometry import face_polygon_coords

SMOOTH_RENDER_PASSES = 2


def render_dcel(
    dcel: DCEL,
    output_path: str | Path,
    figsize: tuple[float, float] = (12.0, 12.0),
    dpi: int = 200,
) -> None:
    """Render the DCEL as filled polygons with black borders."""
    polygons: list[list[tuple[float, float]]] = []
    face_colors: list[tuple[float, float, float, float]] = []

    for face in dcel.faces:
        if face.is_outer or face.outer_component is None:
            continue
        polygon = _face_polygon(dcel, face.outer_component)
        if len(polygon) < 3:
            continue
        polygons.append(_smooth_polygon(polygon))
        face_colors.append(_zone_color(face.zone_id))

    fig, ax = plt.subplots(figsize=figsize, dpi=dpi)
    ax.set_facecolor("#f5f1e8")

    collection = PolyCollection(
        polygons,
        facecolors=face_colors,
        edgecolors="#111111",
        linewidths=0.6,
        antialiaseds=True,
    )
    ax.add_collection(collection)
    ax.autoscale_view()
    ax.set_aspect("equal", adjustable="box")
    ax.axis("off")
    fig.tight_layout(pad=0)
    fig.savefig(output_path, bbox_inches="tight", pad_inches=0.02)
    plt.close(fig)


def render_label_map(
    label_map: np.ndarray,
    output_path: str | Path,
    figsize: tuple[float, float] = (12.0, 12.0),
    dpi: int = 200,
) -> None:
    """Render a raw raster partition for debugging."""
    ocean = label_map < 0
    color_image = np.zeros(label_map.shape + (4,), dtype=float)
    color_image[..., :] = (0.96, 0.95, 0.91, 1.0)

    for label_value in np.unique(label_map[label_map >= 0]):
        color = _zone_color(int(label_value))
        color_image[label_map == label_value] = color
    color_image[ocean] = (1.0, 1.0, 1.0, 1.0)

    fig, ax = plt.subplots(figsize=figsize, dpi=dpi)
    ax.imshow(color_image, origin="upper")
    ax.axis("off")
    fig.tight_layout(pad=0)
    fig.savefig(output_path, bbox_inches="tight", pad_inches=0.02)
    plt.close(fig)


def _face_polygon(dcel: DCEL, start_halfedge: int) -> list[tuple[float, float]]:
    return face_polygon_coords(dcel, start_halfedge)


def _smooth_polygon(polygon: list[tuple[float, float]]) -> list[tuple[float, float]]:
    if len(polygon) < 4:
        return polygon
    current = polygon
    for _ in range(SMOOTH_RENDER_PASSES):
        refined: list[tuple[float, float]] = []
        for start, end in zip(current, current[1:] + current[:1], strict=False):
            refined.append((0.75 * start[0] + 0.25 * end[0], 0.75 * start[1] + 0.25 * end[1]))
            refined.append((0.25 * start[0] + 0.75 * end[0], 0.25 * start[1] + 0.75 * end[1]))
        current = refined
    return current


def _zone_color(zone_id: int | None) -> tuple[float, float, float, float]:
    key = "outer" if zone_id is None else str(zone_id)
    digest = hashlib.blake2b(key.encode("utf-8"), digest_size=6).digest()
    r = 0.25 + digest[0] / 255.0 * 0.55
    g = 0.28 + digest[1] / 255.0 * 0.50
    b = 0.22 + digest[2] / 255.0 * 0.55
    return (min(r, 0.92), min(g, 0.88), min(b, 0.90), 1.0)
