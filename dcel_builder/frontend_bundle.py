"""Build a frontend-oriented hierarchy bundle from the generated DCEL."""

from __future__ import annotations

from itertools import combinations
from functools import lru_cache

from shapely.geometry import GeometryCollection, LineString, MultiLineString, MultiPolygon, Polygon
from shapely.geometry.polygon import orient
from shapely.ops import unary_union

from dcel_builder.dcel import DCEL
from dcel_builder.geometry import face_polygon_coords
from dcel_builder.tree_loader import ZoneTree


def build_frontend_bundle(dcel: DCEL, tree: ZoneTree, zone_index: dict[int, str]) -> dict:
    """Return a frontend-ready hierarchy bundle with geometry for every zone."""
    leaf_polygons = _leaf_polygons(dcel)

    @lru_cache(maxsize=None)
    def zone_geometry(zone_id: int):
        children = tree.children[zone_id]
        if not children:
            return leaf_polygons[zone_id]
        return _normalize_geometry(unary_union([zone_geometry(child) for child in children]))

    zone_geometries = {zone_id: zone_geometry(zone_id) for zone_id in sorted(tree.nodes)}
    zones: dict[str, dict] = {}
    for zone_id in sorted(tree.nodes):
        geometry = zone_geometries[zone_id]
        min_x, min_y, max_x, max_y = geometry.bounds
        children = list(tree.children[zone_id])
        depth = tree.depth[zone_id]
        zones[str(zone_id)] = {
            "id": zone_id,
            "name": zone_index.get(zone_id, str(zone_id)),
            "parent_id": tree.parent[zone_id],
            "depth": depth,
            "child_ids": children,
            "is_leaf": not children,
            "bbox": [min_x, min_y, max_x, max_y],
            "area": geometry.area,
            "path": _svg_path(geometry),
            "children_reveal_depth": depth + 1 if children else None,
        }

    borders = _shared_borders(zone_geometries, tree)
    levels = {
        str(depth): [zone_id for zone_id in sorted(tree.nodes) if tree.depth[zone_id] == depth]
        for depth in range(tree.max_depth + 1)
    }
    return {
        "root_id": tree.root,
        "max_depth": tree.max_depth,
        "world_bbox": [0.0, 0.0, 1.0, 1.0],
        "zoom_depth_thresholds": {
            str(depth): float(2**depth)
            for depth in range(tree.max_depth + 1)
        },
        "levels": levels,
        "borders": borders,
        "zones": zones,
    }


def _leaf_polygons(dcel: DCEL) -> dict[int, Polygon]:
    polygons: dict[int, Polygon] = {}
    for face in dcel.faces:
        if face.is_outer or face.zone_id is None or face.outer_component is None:
            continue
        coords = face_polygon_coords(dcel, face.outer_component)
        if len(coords) < 3:
            raise ValueError(f"Face for zone {face.zone_id} is degenerate.")
        polygons[face.zone_id] = orient(Polygon(coords), sign=1.0)
    return polygons


def _normalize_geometry(geometry):
    if isinstance(geometry, Polygon):
        return orient(geometry, sign=1.0)
    if isinstance(geometry, MultiPolygon):
        return MultiPolygon([orient(polygon, sign=1.0) for polygon in geometry.geoms])
    raise ValueError(f"Expected polygon geometry, got {geometry.geom_type}")


def _svg_path(geometry) -> str:
    if isinstance(geometry, Polygon):
        return _polygon_path(geometry)
    if isinstance(geometry, MultiPolygon):
        return " ".join(_polygon_path(polygon) for polygon in geometry.geoms)
    raise ValueError(f"Expected polygon geometry, got {geometry.geom_type}")


def _polygon_path(polygon: Polygon) -> str:
    segments = [_ring_path(list(polygon.exterior.coords))]
    segments.extend(_ring_path(list(interior.coords)) for interior in polygon.interiors)
    return " ".join(segments)


def _ring_path(coords: list[tuple[float, float]]) -> str:
    commands = [f"M{_fmt(coords[0][0])},{_fmt(coords[0][1])}"]
    commands.extend(f"L{_fmt(x)},{_fmt(y)}" for x, y in coords[1:])
    commands.append("Z")
    return " ".join(commands)


def _fmt(value: float) -> str:
    text = f"{value:.6f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


def _shared_borders(zone_geometries: dict[int, Polygon | MultiPolygon], tree: ZoneTree) -> list[dict]:
    borders: list[dict] = []
    for left_zone, right_zone in combinations(sorted(zone_geometries), 2):
        if _related_by_ancestry(tree, left_zone, right_zone):
            continue
        left_geometry = zone_geometries[left_zone]
        right_geometry = zone_geometries[right_zone]
        if not _bounds_intersect(left_geometry.bounds, right_geometry.bounds):
            continue
        shared = left_geometry.boundary.intersection(right_geometry.boundary)
        shared_lines = _as_multiline(shared)
        if shared_lines is None or shared_lines.length <= 1e-9:
            continue
        borders.append(
            {
                "id": f"{left_zone}:{right_zone}",
                "zone_ids": [left_zone, right_zone],
                "path": _line_path(shared_lines),
            }
        )
    return borders


def _related_by_ancestry(tree: ZoneTree, left_zone: int, right_zone: int) -> bool:
    current = tree.parent[left_zone]
    while current is not None:
        if current == right_zone:
            return True
        current = tree.parent[current]

    current = tree.parent[right_zone]
    while current is not None:
        if current == left_zone:
            return True
        current = tree.parent[current]
    return False


def _as_multiline(geometry) -> MultiLineString | None:
    if geometry.is_empty:
        return None
    if isinstance(geometry, LineString):
        return MultiLineString([geometry])
    if isinstance(geometry, MultiLineString):
        return geometry
    if isinstance(geometry, GeometryCollection):
        lines = [geom for geom in geometry.geoms if isinstance(geom, LineString) and geom.length > 0]
        return MultiLineString(lines) if lines else None
    return None


def _line_path(geometry: MultiLineString) -> str:
    commands: list[str] = []
    for line in geometry.geoms:
        coords = list(line.coords)
        if len(coords) < 2:
            continue
        commands.append(f"M{_fmt(coords[0][0])},{_fmt(coords[0][1])}")
        commands.extend(f"L{_fmt(x)},{_fmt(y)}" for x, y in coords[1:])
    return " ".join(commands)


def _bounds_intersect(
    left_bounds: tuple[float, float, float, float],
    right_bounds: tuple[float, float, float, float],
) -> bool:
    return not (
        left_bounds[2] < right_bounds[0]
        or right_bounds[2] < left_bounds[0]
        or left_bounds[3] < right_bounds[1]
        or right_bounds[3] < left_bounds[1]
    )
