"""T024-T026: Unit tests for dcel_builder.serializer."""

from dcel_builder.dcel import DCEL, Face, HalfEdge, Vertex


def _make_triangle_dcel() -> DCEL:
    """Build a minimal valid DCEL: one interior triangle + outer face.

    Interior face (CCW): 0 → 1 → 2 → 0
    Outer face: 1 → 0 → 2 → 1 (CW)
    Half-edges:
      0: origin=0, twin=3, next=1, prev=2, incident_face=0
      1: origin=1, twin=5, next=2, prev=0, incident_face=0
      2: origin=2, twin=4, next=0, prev=1, incident_face=0
      3: origin=1, twin=0, next=4, prev=5, incident_face=1
      4: origin=0, twin=2, next=5, prev=3, incident_face=1
      5: origin=2, twin=1, next=3, prev=4, incident_face=1
    """
    vertices = [
        Vertex(x=0.0, y=0.0, incident_edge=0),
        Vertex(x=1.0, y=0.0, incident_edge=1),
        Vertex(x=0.5, y=1.0, incident_edge=2),
    ]
    halfedges = [
        HalfEdge(origin=0, twin=3, next=1, prev=2, incident_face=0),
        HalfEdge(origin=1, twin=5, next=2, prev=0, incident_face=0),
        HalfEdge(origin=2, twin=4, next=0, prev=1, incident_face=0),
        HalfEdge(origin=1, twin=0, next=4, prev=5, incident_face=1),
        HalfEdge(origin=0, twin=2, next=5, prev=3, incident_face=1),
        HalfEdge(origin=2, twin=1, next=3, prev=4, incident_face=1),
    ]
    faces = [
        Face(outer_component=0, is_outer=False, zone_id=42, area=0.5, target_area=0.5),
        Face(outer_component=None, is_outer=True, zone_id=None),
    ]
    return DCEL(vertices=vertices, halfedges=halfedges, faces=faces)


def test_to_json_shape():
    """T024: to_json produces a dict with correctly-sized vertex/halfedge/face lists."""
    from dcel_builder.serializer import to_json

    dcel = _make_triangle_dcel()
    data = to_json(dcel, {})

    assert set(data.keys()) == {"vertices", "halfedges", "faces"}
    assert len(data["vertices"]) == 3
    assert len(data["halfedges"]) == 6
    assert len(data["faces"]) == 2


def test_to_json_vertex_fields():
    """T024: Each vertex entry has x, y, incident_edge fields."""
    from dcel_builder.serializer import to_json

    dcel = _make_triangle_dcel()
    data = to_json(dcel, {})

    v = data["vertices"][0]
    assert v["x"] == 0.0
    assert v["y"] == 0.0
    assert v["incident_edge"] == 0


def test_to_json_face_fields():
    """T024: Each face entry has outer_component, is_outer, zone_id, area, target_area."""
    from dcel_builder.serializer import to_json

    dcel = _make_triangle_dcel()
    data = to_json(dcel, {})

    f0 = data["faces"][0]
    assert f0["outer_component"] == 0
    assert f0["is_outer"] is False
    assert f0["zone_id"] == 42
    assert f0["area"] == 0.5

    f1 = data["faces"][1]
    assert f1["outer_component"] is None
    assert f1["is_outer"] is True


def test_round_trip():
    """T025: from_json(to_json(dcel)) reproduces the original DCEL."""
    from dcel_builder.serializer import from_json, to_json

    dcel = _make_triangle_dcel()
    data = to_json(dcel, {})
    restored = from_json(data)

    assert len(restored.vertices) == len(dcel.vertices)
    assert len(restored.halfedges) == len(dcel.halfedges)
    assert len(restored.faces) == len(dcel.faces)

    for i, (orig, rest) in enumerate(zip(dcel.vertices, restored.vertices)):
        assert rest.x == orig.x, f"vertex[{i}].x mismatch"
        assert rest.y == orig.y, f"vertex[{i}].y mismatch"
        assert rest.incident_edge == orig.incident_edge

    for i, (orig, rest) in enumerate(zip(dcel.halfedges, restored.halfedges)):
        assert rest.origin == orig.origin
        assert rest.twin == orig.twin
        assert rest.next == orig.next
        assert rest.prev == orig.prev
        assert rest.incident_face == orig.incident_face

    for i, (orig, rest) in enumerate(zip(dcel.faces, restored.faces)):
        assert rest.outer_component == orig.outer_component
        assert rest.is_outer == orig.is_outer
        assert rest.zone_id == orig.zone_id


def test_round_trip_validates():
    """T025: Restored DCEL passes structural validation."""
    from dcel_builder.serializer import from_json, to_json

    dcel = _make_triangle_dcel()
    restored = from_json(to_json(dcel, {}))
    restored.validate()  # must not raise


def test_validate_invariants_true():
    """T026: validate_invariants returns True for a valid DCEL."""
    from dcel_builder.serializer import validate_invariants

    dcel = _make_triangle_dcel()
    assert validate_invariants(dcel) is True


def test_validate_invariants_false():
    """T026: validate_invariants returns False for a broken DCEL."""
    from dcel_builder.serializer import validate_invariants

    vertices = [Vertex(x=0.0, y=0.0, incident_edge=0)]
    # twin points to itself → twin.twin == self fails
    halfedges = [HalfEdge(origin=0, twin=0, next=0, prev=0, incident_face=0)]
    faces = [Face(outer_component=0, is_outer=False, zone_id=None)]
    broken = DCEL(vertices=vertices, halfedges=halfedges, faces=faces)

    assert validate_invariants(broken) is False
