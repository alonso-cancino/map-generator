"""T028-T030: JSON serialization and deserialization for DCEL."""

from __future__ import annotations

from dcel_builder.dcel import DCEL, Face, HalfEdge, Vertex


def to_json(dcel: DCEL, pos: dict) -> dict:
    """Serialize a DCEL to a JSON-serializable dict.

    Parameters
    ----------
    dcel:
        The DCEL to serialize.
    pos:
        Vertex positions (unused; coordinates are read from dcel.vertices).

    Returns
    -------
    dict
        Keys: ``vertices``, ``halfedges``, ``faces``.
    """
    return {
        "vertices": [{"x": v.x, "y": v.y, "incident_edge": v.incident_edge} for v in dcel.vertices],
        "halfedges": [
            {
                "origin": he.origin,
                "twin": he.twin,
                "next": he.next,
                "prev": he.prev,
                "incident_face": he.incident_face,
            }
            for he in dcel.halfedges
        ],
        "faces": [
            {
                "outer_component": f.outer_component,
                "is_outer": f.is_outer,
                "zone_id": f.zone_id,
                "area": f.area,
                "target_area": f.target_area,
            }
            for f in dcel.faces
        ],
    }


def from_json(data: dict) -> DCEL:
    """Deserialize a DCEL from a dict produced by :func:`to_json`.

    Parameters
    ----------
    data:
        Dict with ``vertices``, ``halfedges``, ``faces`` lists.

    Returns
    -------
    DCEL
        The reconstructed DCEL.
    """
    vertices = [
        Vertex(x=v["x"], y=v["y"], incident_edge=v["incident_edge"]) for v in data["vertices"]
    ]
    halfedges = [
        HalfEdge(
            origin=he["origin"],
            twin=he["twin"],
            next=he["next"],
            prev=he["prev"],
            incident_face=he["incident_face"],
        )
        for he in data["halfedges"]
    ]
    faces = [
        Face(
            outer_component=f["outer_component"],
            is_outer=f["is_outer"],
            zone_id=f["zone_id"],
            area=f.get("area", 0.0),
            target_area=f.get("target_area", 0.0),
        )
        for f in data["faces"]
    ]
    return DCEL(vertices=vertices, halfedges=halfedges, faces=faces)


def validate_invariants(dcel: DCEL) -> bool:
    """Check DCEL structural invariants without raising.

    Returns
    -------
    bool
        True if all invariants hold, False otherwise.
    """
    try:
        dcel.validate()
        return True
    except ValueError:
        return False
