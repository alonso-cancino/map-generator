"""Build a frontend-oriented hierarchy bundle from the generated DCEL."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache

from shapely.geometry import LineString, MultiPolygon, Polygon
from shapely.geometry.polygon import orient
from shapely.ops import unary_union

from dcel_builder.dcel import DCEL
from dcel_builder.geometry import face_polygon_coords
from dcel_builder.tree_loader import ZoneTree

_CORNER_COORDS: tuple[tuple[float, float], ...] = (
    (0.0, 0.0),
    (1.0, 0.0),
    (1.0, 1.0),
    (0.0, 1.0),
)

# Per-arc Douglas-Peucker tolerance applied before Catmull-Rom smoothing.
# Roughly 4 pixels at a 1024-cell raster. Shapely's LineString.simplify uses
# DP and always retains the first and last vertex, which is what we need to
# keep arc endpoints (node vertices) pinned so the shared-edge invariant
# across adjacent arcs is preserved.
_ARC_SIMPLIFY_TOLERANCE = 1.0 / 256


@dataclass
class _Arc:
    """A maximal chain of half-edges sharing the same unordered face pair.

    The stored direction is the canonical one ("forward"). Half-edges that
    traverse the arc in reverse are recorded with direction = -1 in the
    halfedge_to_arc map.
    """

    id: int
    face_pair: frozenset[int]
    halfedge_ids: list[int]
    vertex_indices: list[int]
    coords: list[tuple[float, float]]
    segments: list[tuple[float, float, float, float, float, float]] = field(
        default_factory=list
    )


def _halfedge_destination(dcel: DCEL, halfedge_idx: int) -> int:
    """Return the destination vertex index of a half-edge."""
    return dcel.halfedges[dcel.halfedges[halfedge_idx].twin].origin


def _halfedge_face_pair(dcel: DCEL, halfedge_idx: int) -> frozenset[int]:
    h = dcel.halfedges[halfedge_idx]
    twin = dcel.halfedges[h.twin]
    return frozenset({h.incident_face, twin.incident_face})


def _vertex_face_sets(dcel: DCEL) -> list[set[int]]:
    """For each vertex, collect the set of incident face indices."""
    face_sets: list[set[int]] = [set() for _ in dcel.vertices]
    for he in dcel.halfedges:
        face_sets[he.origin].add(he.incident_face)
    return face_sets


def _corner_vertex_indices(dcel: DCEL) -> set[int]:
    """Return DCEL vertex indices whose coords match canonical map corners."""
    corners: set[int] = set()
    for idx, v in enumerate(dcel.vertices):
        for cx, cy in _CORNER_COORDS:
            if abs(v.x - cx) <= 1e-9 and abs(v.y - cy) <= 1e-9:
                corners.add(idx)
                break
    return corners


def _is_node_vertex(
    v_idx: int,
    face_sets: list[set[int]],
    corner_vertices: set[int],
) -> bool:
    """True if this vertex terminates any arc passing through it."""
    if v_idx in corner_vertices:
        return True
    return len(face_sets[v_idx]) != 2


def _build_node_vertex_set(
    dcel: DCEL,
    face_sets: list[set[int]],
    corner_vertices: set[int],
) -> set[int]:
    """Precompute the set of DCEL vertex indices that are arc endpoints."""
    return {
        v_idx
        for v_idx in range(len(dcel.vertices))
        if _is_node_vertex(v_idx, face_sets, corner_vertices)
    }


def _build_halfedge_indices(
    dcel: DCEL,
) -> tuple[dict[tuple[int, int], int], dict[tuple[float, float], int]]:
    """Return directed-edge and coord lookup maps."""
    directed_edge_to_halfedge: dict[tuple[int, int], int] = {}
    for idx, he in enumerate(dcel.halfedges):
        dest = dcel.halfedges[he.twin].origin
        directed_edge_to_halfedge[(he.origin, dest)] = idx
    coord_to_vertex: dict[tuple[float, float], int] = {
        (v.x, v.y): idx for idx, v in enumerate(dcel.vertices)
    }
    return directed_edge_to_halfedge, coord_to_vertex


def _smooth_arc(
    coords: list[tuple[float, float]],
) -> list[tuple[float, float, float, float, float, float]]:
    """Produce cubic Bezier segments for an arc's polyline via Catmull-Rom.

    Uses the same boundary reflection as the legacy ``_curve_line_path``:
    ``previous = current`` at the start and ``after_next = next_point`` at
    the end. The arc is treated as an open polyline so curves from adjacent
    arcs meet at nodes exactly (same anchor) but can have different tangents
    (creases are expected at T-junctions).
    """
    points = _dedupe_consecutive(coords)
    if len(points) < 2:
        return []
    segments: list[tuple[float, float, float, float, float, float]] = []
    if len(points) == 2:
        (ax, ay), (bx, by) = points
        segments.append((ax, ay, bx, by, bx, by))
        return segments
    for index in range(len(points) - 1):
        previous_point = points[index - 1] if index > 0 else points[index]
        current = points[index]
        next_point = points[index + 1]
        after_next = points[index + 2] if index + 2 < len(points) else next_point
        c1 = _catmull_control_after(current, next_point, previous_point)
        c2 = _catmull_control_before(current, next_point, after_next)
        segments.append((c1[0], c1[1], c2[0], c2[1], next_point[0], next_point[1]))
    return segments


def _arc_forward_c_commands(arc: _Arc) -> str:
    return " ".join(
        f"C{_fmt(c1x)},{_fmt(c1y)} {_fmt(c2x)},{_fmt(c2y)} {_fmt(px)},{_fmt(py)}"
        for (c1x, c1y, c2x, c2y, px, py) in arc.segments
    )


def _arc_reverse_c_commands(arc: _Arc) -> str:
    """Emit arc segments walking backwards from the last anchor to the first.

    Reversing a cubic Bezier P_k -> C1 -> C2 -> P_{k+1} into one going from
    P_{k+1} -> C2 -> C1 -> P_k is just swapping the control points and using
    the predecessor anchor.
    """
    commands: list[str] = []
    for k in range(len(arc.segments) - 1, -1, -1):
        c1x, c1y, c2x, c2y, _, _ = arc.segments[k]
        px, py = arc.coords[k]
        commands.append(
            f"C{_fmt(c2x)},{_fmt(c2y)} {_fmt(c1x)},{_fmt(c1y)} {_fmt(px)},{_fmt(py)}"
        )
    return " ".join(commands)


def _rotate_halfedges_to_node(
    halfedge_ids: list[int],
    dcel: DCEL,
    node_vertices: set[int],
) -> list[int]:
    """Cyclically rotate the walk so the first half-edge's origin is a node.

    Returns the rotated list, or the original list if no node vertex appears
    on the walk (edge case: a face whose entire boundary is one closed arc
    with no T-junctions).
    """
    for i, h_idx in enumerate(halfedge_ids):
        origin = dcel.halfedges[h_idx].origin
        if origin in node_vertices:
            if i == 0:
                return halfedge_ids
            return halfedge_ids[i:] + halfedge_ids[:i]
    return halfedge_ids


def _ring_path_from_halfedges(
    halfedge_ids: list[int],
    halfedge_to_arc: dict[int, tuple[int, int]],
    arcs: list[_Arc],
    node_vertices: set[int],
    dcel: DCEL,
    closed: bool = True,
) -> str:
    """Assemble an SVG path by emitting each arc's cached cubic sequence once.

    The walk is cyclically rotated so it starts at a node (T-junction)
    vertex; after that rotation every arc is traversed in one contiguous
    run and can be emitted as a single forward or reverse cubic sequence.
    The ``M`` anchor is the origin of the first half-edge after rotation.
    """
    if not halfedge_ids:
        return ""
    rotated = _rotate_halfedges_to_node(halfedge_ids, dcel, node_vertices)

    first_h = rotated[0]
    first_origin = dcel.halfedges[first_h].origin
    first_v = dcel.vertices[first_origin]
    commands: list[str] = [f"M{_fmt(first_v.x)},{_fmt(first_v.y)}"]

    current_arc_id: int | None = None
    current_direction: int = 0
    for h_idx in rotated:
        arc_id, direction = halfedge_to_arc[h_idx]
        if arc_id != current_arc_id or direction != current_direction:
            arc = arcs[arc_id]
            if direction == 1:
                segment_c = _arc_forward_c_commands(arc)
            else:
                segment_c = _arc_reverse_c_commands(arc)
            if segment_c:
                commands.append(segment_c)
            current_arc_id = arc_id
            current_direction = direction

    if closed:
        commands.append("Z")
    return " ".join(commands)


def _simplify_coords(
    coords: list[tuple[float, float]],
    tolerance: float,
) -> list[tuple[float, float]]:
    """Douglas-Peucker simplify an open polyline, preserving both endpoints.

    Uses ``shapely.geometry.LineString(coords).simplify``. For polylines
    with fewer than 3 distinct points, the simplification is a no-op.
    ``preserve_topology=False`` selects the DP algorithm directly.
    """
    if len(coords) < 3 or tolerance <= 0.0:
        return list(coords)
    try:
        simplified = LineString(coords).simplify(tolerance, preserve_topology=False)
    except ValueError:
        return list(coords)
    if simplified.is_empty:
        return list(coords)
    simplified_coords = [(x, y) for x, y in simplified.coords]
    if len(simplified_coords) < 2:
        return list(coords)
    return simplified_coords


def _build_arcs(
    dcel: DCEL,
    face_sets: list[set[int]],
    corner_vertices: set[int],
) -> tuple[list[_Arc], dict[int, tuple[int, int]]]:
    """Decompose the DCEL into arcs and associate every half-edge with one.

    An arc is a maximal chain of half-edges sharing the same unordered face
    pair, split at any vertex that is not interior to the pair (a node). Each
    arc's coord polyline is DP-simplified (endpoints pinned so adjacent arcs
    still meet at the same node) and then smoothed once with Catmull-Rom.

    Returns ``(arcs, halfedge_to_arc)``. ``halfedge_to_arc[h]`` is the tuple
    ``(arc_id, direction)`` where direction is ``+1`` if ``h`` walks the arc
    forward (matches the stored chain order) and ``-1`` if ``h`` is the twin
    of a chain member (walks the arc in reverse).
    """
    arcs: list[_Arc] = []
    halfedge_to_arc: dict[int, tuple[int, int]] = {}

    def is_node(v_idx: int) -> bool:
        return _is_node_vertex(v_idx, face_sets, corner_vertices)

    for seed_idx in range(len(dcel.halfedges)):
        if seed_idx in halfedge_to_arc:
            continue

        fp = _halfedge_face_pair(dcel, seed_idx)
        chain: list[int] = [seed_idx]
        visited: set[int] = {seed_idx}

        # Extend backward along .prev while the shared vertex is interior to the arc.
        while True:
            head_idx = chain[0]
            head_he = dcel.halfedges[head_idx]
            shared_v = head_he.origin
            if is_node(shared_v):
                break
            prev_idx = head_he.prev
            if prev_idx in visited:
                break
            if _halfedge_face_pair(dcel, prev_idx) != fp:
                break
            chain.insert(0, prev_idx)
            visited.add(prev_idx)

        # Extend forward along .next while the shared vertex is interior to the arc.
        while True:
            tail_idx = chain[-1]
            tail_he = dcel.halfedges[tail_idx]
            shared_v = dcel.halfedges[tail_he.twin].origin  # destination of tail
            if is_node(shared_v):
                break
            next_idx = tail_he.next
            if next_idx in visited:
                break
            if _halfedge_face_pair(dcel, next_idx) != fp:
                break
            chain.append(next_idx)
            visited.add(next_idx)

        vertex_indices = [dcel.halfedges[h].origin for h in chain]
        last_dest = dcel.halfedges[dcel.halfedges[chain[-1]].twin].origin
        vertex_indices.append(last_dest)
        raw_coords = [(dcel.vertices[v].x, dcel.vertices[v].y) for v in vertex_indices]
        simplified_coords = _simplify_coords(raw_coords, _ARC_SIMPLIFY_TOLERANCE)

        arc_id = len(arcs)
        arc = _Arc(
            id=arc_id,
            face_pair=fp,
            halfedge_ids=list(chain),
            vertex_indices=vertex_indices,
            coords=simplified_coords,
            segments=_smooth_arc(simplified_coords),
        )
        arcs.append(arc)

        for h_idx in chain:
            halfedge_to_arc[h_idx] = (arc_id, 1)
            twin_idx = dcel.halfedges[h_idx].twin
            halfedge_to_arc[twin_idx] = (arc_id, -1)

    assert len(halfedge_to_arc) == len(dcel.halfedges), (
        f"arc decomposition coverage mismatch: "
        f"{len(halfedge_to_arc)} of {len(dcel.halfedges)} halfedges assigned"
    )
    return arcs, halfedge_to_arc


def _ring_path_from_coord_ring(
    ring_coords: list[tuple[float, float]],
    directed_edge_to_halfedge: dict[tuple[int, int], int],
    coord_to_vertex: dict[tuple[float, float], int],
    halfedge_to_arc: dict[int, tuple[int, int]],
    arcs: list[_Arc],
    node_vertices: set[int],
    dcel: DCEL,
) -> str:
    """Assemble a closed smoothed ring from a shapely coord sequence.

    The caller is responsible for passing coords with the closing vertex
    stripped (shapely includes it twice). Each consecutive pair is looked
    up in the directed-edge map to recover the underlying half-edge, then
    the half-edge list is handed to ``_ring_path_from_halfedges`` which
    will rotate the walk so arcs are emitted in one contiguous run each.
    """
    vertex_ring = [coord_to_vertex[coord] for coord in ring_coords]
    halfedge_ids: list[int] = []
    n = len(vertex_ring)
    for i in range(n):
        v_from = vertex_ring[i]
        v_to = vertex_ring[(i + 1) % n]
        halfedge_ids.append(directed_edge_to_halfedge[(v_from, v_to)])
    return _ring_path_from_halfedges(
        halfedge_ids,
        halfedge_to_arc,
        arcs,
        node_vertices,
        dcel,
        closed=True,
    )


def _zone_path_from_geometry(
    geometry,
    directed_edge_to_halfedge: dict[tuple[int, int], int],
    coord_to_vertex: dict[tuple[float, float], int],
    halfedge_to_arc: dict[int, tuple[int, int]],
    arcs: list[_Arc],
    node_vertices: set[int],
    dcel: DCEL,
) -> str:
    """Serialize a (Multi)Polygon via arc assembly."""

    def polygon_path(polygon: Polygon) -> str:
        sub_paths: list[str] = []
        exterior = list(polygon.exterior.coords)
        if exterior and exterior[0] == exterior[-1]:
            exterior = exterior[:-1]
        sub_paths.append(
            _ring_path_from_coord_ring(
                exterior,
                directed_edge_to_halfedge,
                coord_to_vertex,
                halfedge_to_arc,
                arcs,
                node_vertices,
                dcel,
            )
        )
        for interior in polygon.interiors:
            ring = list(interior.coords)
            if ring and ring[0] == ring[-1]:
                ring = ring[:-1]
            sub_paths.append(
                _ring_path_from_coord_ring(
                    ring,
                    directed_edge_to_halfedge,
                    coord_to_vertex,
                    halfedge_to_arc,
                    arcs,
                    node_vertices,
                    dcel,
                )
            )
        return " ".join(sub_paths)

    if isinstance(geometry, Polygon):
        return polygon_path(geometry)
    if isinstance(geometry, MultiPolygon):
        return " ".join(polygon_path(poly) for poly in geometry.geoms)
    raise ValueError(f"Expected polygon geometry, got {geometry.geom_type}")


def _ancestors_including_self(tree: ZoneTree, zone_id: int) -> list[int]:
    chain: list[int] = []
    cur: int | None = zone_id
    while cur is not None:
        chain.append(cur)
        cur = tree.parent[cur]
    return chain


def _build_borders(
    arcs: list[_Arc],
    dcel: DCEL,
    tree: ZoneTree,
) -> list[dict]:
    """Produce shared-border entries for every non-ancestor zone pair.

    Each arc's face pair gives a pair of leaf zones. For every ancestor of
    each leaf (including the leaf itself), we collect the arc under the
    appropriate non-ancestor zone-pair entry. One arc can contribute to
    many pairs when several tree levels separate it.
    """
    border_arcs: dict[tuple[int, int], list[_Arc]] = {}
    for arc in arcs:
        face_ids = sorted(arc.face_pair)
        faces = [dcel.faces[i] for i in face_ids]
        if any(f.is_outer or f.zone_id is None for f in faces):
            continue
        leaf_a, leaf_b = faces[0].zone_id, faces[1].zone_id
        ancestors_a = _ancestors_including_self(tree, leaf_a)
        ancestors_b = _ancestors_including_self(tree, leaf_b)
        for za in ancestors_a:
            for zb in ancestors_b:
                if za == zb or _related_by_ancestry(tree, za, zb):
                    continue
                key = (min(za, zb), max(za, zb))
                border_arcs.setdefault(key, []).append(arc)

    borders: list[dict] = []
    for (zone_a, zone_b), arc_list in border_arcs.items():
        parts: list[str] = []
        for arc in arc_list:
            anchor_x, anchor_y = arc.coords[0]
            piece = f"M{_fmt(anchor_x)},{_fmt(anchor_y)}"
            forward = _arc_forward_c_commands(arc)
            if forward:
                piece += " " + forward
            parts.append(piece)
        borders.append(
            {
                "id": f"{zone_a}:{zone_b}",
                "zone_ids": [zone_a, zone_b],
                "path": " ".join(parts),
            }
        )
    return borders


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

    face_sets = _vertex_face_sets(dcel)
    corner_vertices = _corner_vertex_indices(dcel)
    node_vertices = _build_node_vertex_set(dcel, face_sets, corner_vertices)
    arcs, halfedge_to_arc = _build_arcs(dcel, face_sets, corner_vertices)
    directed_edge_to_halfedge, coord_to_vertex = _build_halfedge_indices(dcel)

    def serialize_zone(geometry) -> str:
        return _zone_path_from_geometry(
            geometry,
            directed_edge_to_halfedge,
            coord_to_vertex,
            halfedge_to_arc,
            arcs,
            node_vertices,
            dcel,
        )

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
            "path": serialize_zone(geometry),
            "children_reveal_depth": depth + 1 if children else None,
        }

    borders = _build_borders(arcs, dcel, tree)
    levels = {
        str(depth): [zone_id for zone_id in sorted(tree.nodes) if tree.depth[zone_id] == depth]
        for depth in range(tree.max_depth + 1)
    }
    return {
        "root_id": tree.root,
        "max_depth": tree.max_depth,
        "world_bbox": [0.0, 0.0, 1.0, 1.0],
        "world_outline_path": serialize_zone(zone_geometries[tree.root]),
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


def _fmt(value: float) -> str:
    text = f"{value:.6f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


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


def _catmull_control_after(
    current: tuple[float, float],
    next_point: tuple[float, float],
    previous_point: tuple[float, float],
) -> tuple[float, float]:
    return (
        current[0] + (next_point[0] - previous_point[0]) / 6.0,
        current[1] + (next_point[1] - previous_point[1]) / 6.0,
    )


def _catmull_control_before(
    current: tuple[float, float],
    next_point: tuple[float, float],
    after_next: tuple[float, float],
) -> tuple[float, float]:
    return (
        next_point[0] - (after_next[0] - current[0]) / 6.0,
        next_point[1] - (after_next[1] - current[1]) / 6.0,
    )


def _dedupe_consecutive(coords: list[tuple[float, float]]) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for coord in coords:
        if not points or not _same_point(points[-1], coord):
            points.append(coord)
    return points


def _same_point(left: tuple[float, float], right: tuple[float, float]) -> bool:
    return abs(left[0] - right[0]) <= 1e-12 and abs(left[1] - right[1]) <= 1e-12
