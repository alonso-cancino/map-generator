from __future__ import annotations

import json

import pytest


def _build_small_bundle(tmp_path):
    from dcel_builder import generate_map_artifacts
    from dcel_builder.frontend_bundle import build_frontend_bundle

    (tmp_path / "edges.json").write_text(json.dumps([[0, 1], [0, 2], [2, 3], [2, 4]]))
    (tmp_path / "stats.json").write_text(json.dumps({}))
    (tmp_path / "index.json").write_text(
        json.dumps(
            {
                "0": "root",
                "1": "left",
                "2": "right",
                "3": "right_child_a",
                "4": "right_child_b",
            }
        )
    )

    dcel, _, tree, zone_index = generate_map_artifacts(
        tmp_path / "edges.json",
        tmp_path / "stats.json",
        tmp_path / "index.json",
        seed=42,
        resolution=64,
        quiet=True,
    )
    return build_frontend_bundle(dcel, tree, zone_index)


@pytest.fixture
def small_bundle(tmp_path):
    return _build_small_bundle(tmp_path)


def test_build_frontend_bundle_includes_all_tree_levels(small_bundle):
    bundle = small_bundle

    assert bundle["root_id"] == 0
    assert bundle["max_depth"] == 2
    assert bundle["world_outline_path"].startswith("M")
    assert "C" in bundle["world_outline_path"]
    assert bundle["levels"] == {"0": [0], "1": [1, 2], "2": [3, 4]}
    assert set(bundle["zones"]) == {"0", "1", "2", "3", "4"}

    root = bundle["zones"]["0"]
    right = bundle["zones"]["2"]
    leaf = bundle["zones"]["3"]

    assert root["name"] == "root"
    assert root["child_ids"] == [1, 2]
    assert root["children_reveal_depth"] == 1
    assert right["children_reveal_depth"] == 2
    assert leaf["children_reveal_depth"] is None
    assert root["area"] >= right["area"] >= leaf["area"] > 0
    assert root["path"].startswith("M")
    assert "C" in root["path"]
    assert "C" in leaf["path"]
    # Simplification + per-arc emission should keep small-map paths compact.
    # Regenerates caught regressions when the whole arc was double-emitted.
    assert len(root["path"]) < 40_000, (
        f"root path grew unexpectedly to {len(root['path'])} bytes"
    )
    assert all(0.0 <= value <= 1.0 for value in root["bbox"])
    assert root["bbox"][0] <= leaf["bbox"][0] <= leaf["bbox"][2] <= root["bbox"][2]
    assert root["bbox"][1] <= leaf["bbox"][1] <= leaf["bbox"][3] <= root["bbox"][3]
    assert bundle["borders"], "expected shared borders in frontend bundle"

    border_ids = {border["id"] for border in bundle["borders"]}
    # Every non-ancestor zone pair whose arcs are adjacent should be present.
    expected_ids = {"1:2", "1:3", "1:4", "3:4"}
    assert expected_ids.issubset(border_ids)
    for border in bundle["borders"]:
        assert len(border["zone_ids"]) == 2
        assert border["path"].startswith("M")
        assert "C" in border["path"]


def test_world_outline_is_closed_and_curved(small_bundle):
    outline = small_bundle["world_outline_path"]
    assert outline.startswith("M")
    assert "C" in outline
    assert outline.rstrip().endswith("Z")


def _parse_subpath(subpath: str) -> tuple[tuple[float, float], list[tuple[tuple[float, float], tuple[float, float], tuple[float, float]]]]:
    """Parse a ``Mx,y Cc1x,c1y c2x,c2y px,py ...`` sub-path into anchors.

    Note: the emitter writes ``M`` directly fused to its number with no
    separator, and ``C`` the same way. We split the command letter away
    from its operands before tokenizing.
    """
    stripped = subpath.replace(",", " ")
    # Insert a space after any command letter fused to a number.
    spaced = ""
    for ch in stripped:
        if ch in "MCZ":
            if spaced and spaced[-1] != " ":
                spaced += " "
            spaced += ch + " "
        else:
            spaced += ch
    tokens = spaced.split()
    assert tokens[0] == "M", f"expected M, got {tokens[0]!r}"
    start = (float(tokens[1]), float(tokens[2]))
    segments: list[tuple[tuple[float, float], tuple[float, float], tuple[float, float]]] = []
    i = 3
    while i < len(tokens):
        if tokens[i] == "Z":
            break
        assert tokens[i] == "C", f"expected C, got {tokens[i]!r} at position {i}"
        c1 = (float(tokens[i + 1]), float(tokens[i + 2]))
        c2 = (float(tokens[i + 3]), float(tokens[i + 4]))
        p = (float(tokens[i + 5]), float(tokens[i + 6]))
        segments.append((c1, c2, p))
        i += 7
    return start, segments


def _format_pair(value: tuple[float, float]) -> str:
    return f"{_format_fmt(value[0])},{_format_fmt(value[1])}"


def _format_fmt(value: float) -> str:
    text = f"{value:.6f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


def _border_appears_in_path(border_subpath: str, haystack: str) -> bool:
    """True if the border's arc bytes appear verbatim in haystack.

    The backend now emits each arc as a single contiguous cubic sequence
    (per-arc emission with walk rotation to start at a node vertex). So
    the border's whole C sequence, or its byte-for-byte reversal, should
    appear once inside every fill path that uses that arc.
    """
    start, segments = _parse_subpath(border_subpath)
    if not segments:
        return True
    forward_c = " ".join(
        f"C{_format_pair(c1)} {_format_pair(c2)} {_format_pair(p)}"
        for (c1, c2, p) in segments
    )
    if forward_c and forward_c in haystack:
        return True
    # Byte-for-byte reversal: walk anchors in reverse order, swapping c1/c2.
    anchors = [start] + [seg[2] for seg in segments]
    reverse_c = " ".join(
        f"C{_format_pair(segments[k][1])} {_format_pair(segments[k][0])} "
        f"{_format_pair(anchors[k])}"
        for k in range(len(segments) - 1, -1, -1)
    )
    return bool(reverse_c) and reverse_c in haystack


def test_sibling_border_bytes_appear_in_sibling_fill(small_bundle):
    """The byte-level shared-edge invariant: the bytes of a leaf-leaf border
    appear (forward or reversed) inside both sibling fill paths."""
    bundle = small_bundle
    leaves = {1, 3, 4}
    leaf_borders = [
        border
        for border in bundle["borders"]
        if set(border["zone_ids"]).issubset(leaves)
    ]
    assert leaf_borders, "expected at least one leaf-leaf border"

    for border in leaf_borders:
        za, zb = border["zone_ids"]
        fill_a = bundle["zones"][str(za)]["path"]
        fill_b = bundle["zones"][str(zb)]["path"]
        assert _border_appears_in_path(border["path"], fill_a), (
            f"border {border['id']} bytes not found in zone {za} fill"
        )
        assert _border_appears_in_path(border["path"], fill_b), (
            f"border {border['id']} bytes not found in zone {zb} fill"
        )


def test_parent_path_contains_leaf_external_arc_bytes(small_bundle):
    """Parent zone 2 tiles zones 3 and 4. Any arc whose other side is zone
    1 (outside parent 2's subtree) must appear verbatim in both the leaf's
    fill path AND parent 2's fill path — that's the exact-coincidence
    guarantee the refactor was built for."""
    bundle = small_bundle
    parent_path = bundle["zones"]["2"]["path"]
    # The 1:3 and 1:4 borders are external to parent 2.
    for border in bundle["borders"]:
        if border["id"] not in {"1:3", "1:4"}:
            continue
        leaf_id = border["zone_ids"][1]  # 3 or 4
        leaf_path = bundle["zones"][str(leaf_id)]["path"]
        assert _border_appears_in_path(border["path"], leaf_path), (
            f"border {border['id']} bytes missing from leaf {leaf_id} fill"
        )
        assert _border_appears_in_path(border["path"], parent_path), (
            f"border {border['id']} bytes missing from parent 2 fill "
            "(parent/child shared-edge invariant violated)"
        )


def test_zoom_thresholds_scale_by_depth(tmp_path):
    from dcel_builder import generate_frontend_bundle

    (tmp_path / "edges.json").write_text(json.dumps([[0, 1], [0, 2]]))
    (tmp_path / "stats.json").write_text(json.dumps({}))
    (tmp_path / "index.json").write_text(json.dumps({"0": "root", "1": "left", "2": "right"}))

    bundle, _ = generate_frontend_bundle(
        tmp_path / "edges.json",
        tmp_path / "stats.json",
        tmp_path / "index.json",
        seed=7,
        resolution=64,
        quiet=True,
    )

    assert bundle["zoom_depth_thresholds"] == {"0": 1.0, "1": 2.0}
