from __future__ import annotations

from pathlib import Path

from dcel_builder.dcel import DCEL, Face, HalfEdge, Vertex


def _make_triangle_dcel() -> DCEL:
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
        Face(outer_component=0, is_outer=False, zone_id=42, area=0.5, target_area=0.0),
        Face(outer_component=None, is_outer=True, zone_id=None),
    ]
    return DCEL(vertices=vertices, halfedges=halfedges, faces=faces)


def test_render_dcel_writes_png(tmp_path: Path):
    from dcel_builder.render import render_dcel

    output = tmp_path / "triangle.png"
    render_dcel(_make_triangle_dcel(), output, figsize=(3, 3), dpi=100)

    assert output.exists()
    assert output.stat().st_size > 0
