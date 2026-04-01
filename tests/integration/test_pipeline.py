from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
EXAMPLE_ROOT = REPO_ROOT / "examples" / "atlantis"
ZONE_EDGES = EXAMPLE_ROOT / "zone_edges.json"
TREE_STATS = EXAMPLE_ROOT / "zone_tree_stats.json"
ZONE_INDEX = EXAMPLE_ROOT / "zone_index.json"


@pytest.fixture(scope="module")
def pipeline_output():
    from dcel_builder import generate_dcel

    dcel, report = generate_dcel(
        ZONE_EDGES,
        TREE_STATS,
        ZONE_INDEX,
        seed=42,
        resolution=256,
        quiet=True,
    )
    return dcel, report


def test_pipeline_leaf_face_count_matches_tree(pipeline_output):
    dcel, report = pipeline_output
    interior = [face for face in dcel.faces if not face.is_outer]
    outer = [face for face in dcel.faces if face.is_outer]

    assert len(interior) == report["leaf_count"] == 16
    assert len(outer) == 1
    dcel.validate()


def test_every_leaf_zone_id_is_present_exactly_once(pipeline_output):
    dcel, report = pipeline_output
    zone_ids = [face.zone_id for face in dcel.faces if not face.is_outer]

    assert len(zone_ids) == len(set(zone_ids))
    assert set(zone_ids) == set(report["leaf_pixel_counts"])


def test_every_zone_has_positive_area(pipeline_output):
    dcel, _ = pipeline_output
    zero_area = [
        face.zone_id
        for face in dcel.faces
        if not face.is_outer and face.zone_id is not None and face.area <= 0
    ]
    assert zero_area == []


def test_uniform_target_area_is_populated(pipeline_output):
    dcel, report = pipeline_output
    target = report["leaf_area_stats"]["mean"]
    targets = [
        face.target_area for face in dcel.faces if not face.is_outer and face.zone_id is not None
    ]
    assert all(target_area > 0 for target_area in targets)
    assert max(abs(target_area - target) for target_area in targets) < 1e-9


def test_leaf_area_balance_is_reasonable(pipeline_output):
    _, report = pipeline_output
    stats = report["leaf_area_stats"]

    assert stats["cv"] < 1.5
    assert stats["within_50pct"] >= 8


def test_smallest_leaf_is_not_tiny_relative_to_mean(pipeline_output):
    _, report = pipeline_output
    stats = report["leaf_area_stats"]

    assert stats["min"] >= stats["mean"] * 0.12


def test_allocator_reports_weighted_target_strategy(pipeline_output):
    _, report = pipeline_output

    assert report["target_strategy"] == "subtree_leaf_weighted_with_parent_floor:contour_guided"
    assert report["split_mode"] == "contour_guided"
