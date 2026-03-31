"""T006: DCEL data structure — Vertex, HalfEdge, Face, and DCEL container."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Vertex:
    """A 2-D point in the DCEL map."""

    x: float
    y: float
    incident_edge: int  # index of one outgoing half-edge


@dataclass
class HalfEdge:
    """A directed half-edge in the DCEL."""

    origin: int  # index of origin Vertex
    twin: int  # index of the opposite half-edge
    next: int  # index of next half-edge in CCW face cycle
    prev: int  # index of previous half-edge in same cycle
    incident_face: int  # index of face to the left of this half-edge


@dataclass
class Face:
    """A polygon face in the DCEL (or the unbounded outer face)."""

    outer_component: Optional[int]  # index of one bounding half-edge; None for outer
    is_outer: bool
    zone_id: Optional[int]  # node ID from zone_leaf_graph; None for outer
    area: float = field(default=0.0)
    target_area: float = field(default=0.0)


class DCEL:
    """Doubly-Connected Edge List container.

    Holds flat lists of Vertex, HalfEdge, and Face objects.
    Array position = implicit index for all cross-references.
    """

    def __init__(
        self,
        vertices: list[Vertex],
        halfedges: list[HalfEdge],
        faces: list[Face],
    ) -> None:
        self.vertices = vertices
        self.halfedges = halfedges
        self.faces = faces

    # ------------------------------------------------------------------
    # Structural validation
    # ------------------------------------------------------------------

    def validate(self) -> None:
        """Check all four DCEL structural invariants.

        Raises
        ------
        ValueError
            Lists every violated invariant found.
        """
        violations: list[str] = []
        he = self.halfedges

        for i, h in enumerate(he):
            # 1. twin.twin == self
            if he[h.twin].twin != i:
                violations.append(
                    f"twin invariant violated at he[{i}]: "
                    f"he[{h.twin}].twin = {he[h.twin].twin}, expected {i}"
                )

            # 2. next.prev == self
            if he[h.next].prev != i:
                violations.append(
                    f"next.prev invariant violated at he[{i}]: "
                    f"he[{h.next}].prev = {he[h.next].prev}, expected {i}"
                )

            # 3. twin faces differ
            if he[h.twin].incident_face == h.incident_face:
                violations.append(
                    f"twin face invariant violated at he[{i}]: "
                    f"he[{i}].incident_face == he[{h.twin}].incident_face == "
                    f"{h.incident_face}"
                )

        # 4. Outer face must have outer_component == None
        for j, f in enumerate(self.faces):
            if f.is_outer and f.outer_component is not None:
                violations.append(
                    f"outer face invariant violated at face[{j}]: "
                    f"outer_component should be None, got {f.outer_component}"
                )

        if violations:
            raise ValueError("DCEL structural validation failed:\n" + "\n".join(violations))

    # ------------------------------------------------------------------
    # Geometry helpers (added in US2 / T021)
    # ------------------------------------------------------------------

    def compute_face_areas(
        self,
        pos: dict[int, tuple[float, float]],
        target_map: Optional[dict[int, float]] = None,
    ) -> None:
        """Compute and store the polygon area for every interior face.

        Uses the shoelace formula.  Results are stored in ``face.area``.
        If *target_map* is provided (zone_id → target_area), also sets
        ``face.target_area``.

        Parameters
        ----------
        pos:
            Mapping from graph node IDs to (x, y) coordinates.
        target_map:
            Optional mapping from zone_id to target area.
        """
        # Store vertex positions keyed by vertex index for quick lookup.
        vert_pos = {i: (v.x, v.y) for i, v in enumerate(self.vertices)}

        # Build a coordinate → vertex_index map
        coord_to_vidx = {(v.x, v.y): i for i, v in enumerate(self.vertices)}

        # Build vertex_index → node_id map using pos
        vidx_to_node: dict[int, int] = {}
        for node_id, (x, y) in pos.items():
            key = (x, y)
            if key in coord_to_vidx:
                vidx_to_node[coord_to_vidx[key]] = node_id

        for face_idx, face in enumerate(self.faces):
            if face.is_outer:
                continue
            if face.outer_component is None:
                continue

            # Walk the half-edge boundary cycle to collect vertex coords
            start = face.outer_component
            coords: list[tuple[float, float]] = []
            cur = start
            while True:
                v_idx = self.halfedges[cur].origin
                coords.append(vert_pos[v_idx])
                cur = self.halfedges[cur].next
                if cur == start:
                    break

            # Shoelace formula
            area = _shoelace_area(coords)
            face.area = abs(area)

            if target_map is not None and face.zone_id is not None:
                face.target_area = target_map.get(face.zone_id, 0.0)


def _shoelace_area(coords: list[tuple[float, float]]) -> float:
    """Return signed area via the shoelace formula (positive = CCW)."""
    n = len(coords)
    s = 0.0
    for i in range(n):
        x0, y0 = coords[i]
        x1, y1 = coords[(i + 1) % n]
        s += x0 * y1 - x1 * y0
    return s / 2.0
