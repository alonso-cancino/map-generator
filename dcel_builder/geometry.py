"""Helpers for reconstructing polygon geometry from a DCEL."""

from __future__ import annotations

from dcel_builder.dcel import DCEL


def face_polygon_coords(dcel: DCEL, start_halfedge: int, close_ring: bool = False) -> list[tuple[float, float]]:
    """Return the ordered coordinates for a face boundary cycle."""
    polygon: list[tuple[float, float]] = []
    current = start_halfedge
    while True:
        vertex = dcel.vertices[dcel.halfedges[current].origin]
        polygon.append((vertex.x, vertex.y))
        current = dcel.halfedges[current].next
        if current == start_halfedge:
            break
    if close_ring and polygon:
        polygon.append(polygon[0])
    return polygon
