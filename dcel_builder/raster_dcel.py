"""Build a DCEL directly from a raster label map via polygon extraction."""

from __future__ import annotations

from collections import defaultdict

import numpy as np
from shapely.geometry import MultiPolygon, Polygon, box
from shapely.geometry.polygon import orient
from shapely.ops import polygonize, unary_union

from dcel_builder.dcel import DCEL, Face, HalfEdge, Vertex

OCEAN = -1


def build_dcel_from_label_map(
    label_map: np.ndarray,
    leaf_label_by_zone: dict[int, int],
    leaf_pixel_counts: dict[int, int],
) -> DCEL:
    """Convert a leaf label map to a DCEL with exact shared polygon edges."""
    zone_polygons = _extract_zone_polygons(label_map, leaf_label_by_zone)
    merged = unary_union([polygon.boundary for polygon in zone_polygons.values()])
    cell_polygons = [orient(polygon, sign=1.0) for polygon in polygonize(merged)]

    face_polygons: dict[int, Polygon] = {}
    for polygon in cell_polygons:
        zone_id = _zone_id_at_point(label_map, leaf_label_by_zone, polygon.representative_point())
        if zone_id is None:
            continue
        existing = face_polygons.get(zone_id)
        face_polygons[zone_id] = polygon if existing is None else existing.union(polygon)

    if set(face_polygons) != set(leaf_label_by_zone):
        missing = sorted(set(leaf_label_by_zone) - set(face_polygons))
        raise ValueError(f"Failed to recover polygons for all leaves; missing {missing[:10]}")

    polygons = {
        zone_id: orient(_as_polygon(geom), sign=1.0)
        for zone_id, geom in face_polygons.items()
    }
    return _build_dcel_from_polygons(polygons, label_map, leaf_pixel_counts)


def _extract_zone_polygons(
    label_map: np.ndarray,
    leaf_label_by_zone: dict[int, int],
) -> dict[int, Polygon]:
    height, width = label_map.shape
    polygons: dict[int, Polygon] = {}

    for zone_id, label_value in leaf_label_by_zone.items():
        rows, cols = np.where(label_map == label_value)
        if len(rows) == 0:
            raise ValueError(f"Leaf zone {zone_id} has no assigned pixels.")
        cells = [
            box(
                col / width,
                1.0 - (row + 1) / height,
                (col + 1) / width,
                1.0 - row / height,
            )
            for row, col in zip(rows, cols, strict=False)
        ]
        polygons[zone_id] = orient(_as_polygon(unary_union(cells)), sign=1.0)

    return polygons


def _as_polygon(geometry) -> Polygon:
    if isinstance(geometry, Polygon):
        return geometry
    if isinstance(geometry, MultiPolygon):
        pieces = sorted(geometry.geoms, key=lambda polygon: polygon.area, reverse=True)
        return orient(pieces[0], sign=1.0)
    raise ValueError(f"Expected polygonal geometry, got {geometry.geom_type}")


def _zone_id_at_point(
    label_map: np.ndarray,
    leaf_label_by_zone: dict[int, int],
    point,
) -> int | None:
    height, width = label_map.shape
    x = min(max(point.x, 0.0), 1.0 - 1e-9)
    y = min(max(point.y, 0.0), 1.0 - 1e-9)
    col = min(int(x * width), width - 1)
    row = min(int((1.0 - y) * height), height - 1)
    label_value = int(label_map[row, col])
    if label_value == OCEAN:
        return None
    for zone_id, expected_label in leaf_label_by_zone.items():
        if expected_label == label_value:
            return zone_id
    return None


def _build_dcel_from_polygons(
    polygons: dict[int, Polygon],
    label_map: np.ndarray,
    leaf_pixel_counts: dict[int, int],
) -> DCEL:
    vertices: list[Vertex] = []
    vertex_index: dict[tuple[float, float], int] = {}
    halfedges: list[HalfEdge] = []
    destinations: list[int] = []
    pending_twins: dict[tuple[int, int], int] = {}

    zone_ids = sorted(polygons)
    faces = [Face(outer_component=None, is_outer=False, zone_id=zone_id) for zone_id in zone_ids]
    outer_face_index = len(faces)
    faces.append(Face(outer_component=None, is_outer=True, zone_id=None))
    zone_to_face = {zone_id: idx for idx, zone_id in enumerate(zone_ids)}

    for zone_id in zone_ids:
        polygon = polygons[zone_id]
        ring = list(polygon.exterior.coords[:-1])
        if len(ring) < 3:
            raise ValueError(f"Zone {zone_id} polygon is degenerate.")

        face_index = zone_to_face[zone_id]
        cycle: list[int] = []
        for start, end in zip(ring, ring[1:] + ring[:1], strict=False):
            origin = _get_vertex_index(vertices, vertex_index, start)
            destination = _get_vertex_index(vertices, vertex_index, end)
            he_index = len(halfedges)
            halfedges.append(
                HalfEdge(
                    origin=origin,
                    twin=-1,
                    next=-1,
                    prev=-1,
                    incident_face=face_index,
                )
            )
            destinations.append(destination)
            cycle.append(he_index)

            reverse_key = (destination, origin)
            if reverse_key in pending_twins:
                twin_index = pending_twins.pop(reverse_key)
                halfedges[he_index].twin = twin_index
                halfedges[twin_index].twin = he_index
            else:
                pending_twins[(origin, destination)] = he_index

        for current, nxt, prev in zip(
            cycle,
            cycle[1:] + cycle[:1],
            cycle[-1:] + cycle[:-1],
            strict=False,
        ):
            halfedges[current].next = nxt
            halfedges[current].prev = prev
        faces[face_index].outer_component = cycle[0]

    outer_halfedges: list[int] = []
    for twinless_index in list(pending_twins.values()):
        origin = destinations[twinless_index]
        destination = halfedges[twinless_index].origin
        outer_index = len(halfedges)
        halfedges.append(
            HalfEdge(
                origin=origin,
                twin=twinless_index,
                next=-1,
                prev=-1,
                incident_face=outer_face_index,
            )
        )
        destinations.append(destination)
        halfedges[twinless_index].twin = outer_index
        outer_halfedges.append(outer_index)

    _wire_outer_halfedges(halfedges, destinations, outer_halfedges)

    for vertex_id, vertex in enumerate(vertices):
        incident = next(
            (
                he_index
                for he_index, halfedge in enumerate(halfedges)
                if halfedge.origin == vertex_id
            ),
            0,
        )
        vertex.incident_edge = incident

    continent_pixels = max(int(np.sum(label_map >= 0)), 1)
    for face in faces:
        if face.is_outer or face.zone_id is None:
            continue
        face.area = leaf_pixel_counts.get(face.zone_id, 0) / continent_pixels

    dcel = DCEL(vertices=vertices, halfedges=halfedges, faces=faces)
    dcel.validate()
    return dcel


def _get_vertex_index(
    vertices: list[Vertex],
    vertex_index: dict[tuple[float, float], int],
    coord: tuple[float, float],
) -> int:
    key = (round(coord[0], 12), round(coord[1], 12))
    if key not in vertex_index:
        vertex_index[key] = len(vertices)
        vertices.append(Vertex(x=coord[0], y=coord[1], incident_edge=0))
    return vertex_index[key]


def _wire_outer_halfedges(
    halfedges: list[HalfEdge],
    destinations: list[int],
    outer_halfedges: list[int],
) -> None:
    outgoing: dict[int, list[int]] = defaultdict(list)
    for he_index in outer_halfedges:
        outgoing[halfedges[he_index].origin].append(he_index)

    visited: set[int] = set()
    for start in outer_halfedges:
        if start in visited:
            continue
        cycle = [start]
        visited.add(start)
        current = start
        while True:
            next_origin = destinations[current]
            candidates = outgoing[next_origin]
            next_he = next(
                (candidate for candidate in candidates if candidate not in visited),
                None,
            )
            if next_he is None:
                next_he = start if next_origin == halfedges[start].origin else None
            if next_he is None:
                raise ValueError("Could not close outer boundary cycle.")
            if next_he == start:
                break
            cycle.append(next_he)
            visited.add(next_he)
            current = next_he

        for current, nxt, prev in zip(
            cycle,
            cycle[1:] + cycle[:1],
            cycle[-1:] + cycle[:-1],
            strict=False,
        ):
            halfedges[current].next = nxt
            halfedges[current].prev = prev
