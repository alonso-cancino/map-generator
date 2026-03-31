"""T005: Unit tests for dcel.py — written BEFORE implementation (TDD)."""

import copy

import pytest


def _build_valid_dcel():
    """Build a hand-constructed valid DCEL from the sample_graph.

    Graph: 4-cycle + diagonal (0,2)
    Nodes: 0,1,2,3   Edges: (0,1),(1,2),(2,3),(3,0),(0,2)
    10 half-edges, 2 interior faces + 1 outer face.

    Half-edge assignments (face = left side):
      Face 0 (interior, CCW: 0→1→2→0):
        he[0]: 0→1, he[2]: 1→2, he[4]: 2→0
      Face 1 (interior, CCW: 0→2→3→0):
        he[5]: 0→2, he[6]: 2→3, he[8]: 3→0
      Face 2 (outer, CW: 1→0, 0→3, 3→2, 2→1):
        he[1]: 1→0, he[9]: 0→3, he[7]: 3→2, he[3]: 2→1
    """
    from dcel_builder.dcel import DCEL, Face, HalfEdge, Vertex

    verts = [
        Vertex(x=0.0, y=1.0, incident_edge=0),  # 0
        Vertex(x=1.0, y=1.0, incident_edge=2),  # 1
        Vertex(x=1.0, y=0.0, incident_edge=3),  # 2
        Vertex(x=0.0, y=0.0, incident_edge=8),  # 3
    ]
    faces = [
        Face(outer_component=0, is_outer=False, zone_id=10),  # face 0
        Face(outer_component=5, is_outer=False, zone_id=20),  # face 1
        Face(outer_component=None, is_outer=True, zone_id=None),  # face 2
    ]
    # HalfEdge(origin, twin, next, prev, incident_face)
    halfedges = [
        HalfEdge(0, 1, 2, 4, 0),  # he[0]: 0→1, face 0
        HalfEdge(1, 0, 9, 3, 2),  # he[1]: 1→0, outer
        HalfEdge(1, 3, 4, 0, 0),  # he[2]: 1→2, face 0
        HalfEdge(2, 2, 1, 7, 2),  # he[3]: 2→1, outer
        HalfEdge(2, 5, 0, 2, 0),  # he[4]: 2→0, face 0
        HalfEdge(0, 4, 6, 8, 1),  # he[5]: 0→2, face 1
        HalfEdge(2, 7, 8, 5, 1),  # he[6]: 2→3, face 1
        HalfEdge(3, 6, 3, 9, 2),  # he[7]: 3→2, outer
        HalfEdge(3, 9, 5, 6, 1),  # he[8]: 3→0, face 1
        HalfEdge(0, 8, 7, 1, 2),  # he[9]: 0→3, outer
    ]
    return DCEL(vertices=verts, halfedges=halfedges, faces=faces)


def test_vertex_fields():
    from dcel_builder.dcel import Vertex

    v = Vertex(x=1.0, y=2.5, incident_edge=3)
    assert v.x == 1.0
    assert v.y == 2.5
    assert v.incident_edge == 3


def test_halfedge_fields():
    from dcel_builder.dcel import HalfEdge

    he = HalfEdge(origin=0, twin=1, next=2, prev=5, incident_face=0)
    assert he.origin == 0
    assert he.twin == 1
    assert he.next == 2
    assert he.prev == 5
    assert he.incident_face == 0


def test_face_fields():
    from dcel_builder.dcel import Face

    f = Face(outer_component=3, is_outer=False, zone_id=42)
    assert f.outer_component == 3
    assert not f.is_outer
    assert f.zone_id == 42


def test_face_outer_fields():
    from dcel_builder.dcel import Face

    f = Face(outer_component=None, is_outer=True, zone_id=None)
    assert f.outer_component is None
    assert f.is_outer
    assert f.zone_id is None


def test_validate_passes_on_valid_dcel():
    """validate() should not raise on a correctly constructed DCEL."""
    dcel = _build_valid_dcel()
    dcel.validate()  # must not raise


def test_validate_raises_on_broken_twin():
    """validate() raises ValueError when twin.twin != self."""
    dcel = _build_valid_dcel()
    # Break he[0].twin so twin chain is inconsistent
    broken = copy.deepcopy(dcel)
    broken.halfedges[0] = broken.halfedges[0].__class__(
        origin=broken.halfedges[0].origin,
        twin=5,  # wrong twin (was 1)
        next=broken.halfedges[0].next,
        prev=broken.halfedges[0].prev,
        incident_face=broken.halfedges[0].incident_face,
    )
    with pytest.raises(ValueError, match="twin"):
        broken.validate()


def test_validate_raises_on_broken_next_prev():
    """validate() raises ValueError when next.prev != self."""
    dcel = _build_valid_dcel()
    broken = copy.deepcopy(dcel)
    # Break he[0].next so next.prev won't point back to 0
    broken.halfedges[0] = broken.halfedges[0].__class__(
        origin=broken.halfedges[0].origin,
        twin=broken.halfedges[0].twin,
        next=7,  # wrong next (was 2)
        prev=broken.halfedges[0].prev,
        incident_face=broken.halfedges[0].incident_face,
    )
    with pytest.raises(ValueError, match="next.prev"):
        broken.validate()


def test_validate_raises_when_outer_face_has_component():
    """validate() raises ValueError if outer face has outer_component != None."""
    from dcel_builder.dcel import Face

    dcel = _build_valid_dcel()
    broken = copy.deepcopy(dcel)
    # Set outer face outer_component to a non-None value
    broken.faces[2] = Face(outer_component=1, is_outer=True, zone_id=None)
    with pytest.raises(ValueError, match="outer"):
        broken.validate()
