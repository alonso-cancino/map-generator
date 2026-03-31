from __future__ import annotations

import json

import pytest


def test_load_tree_inputs_returns_rooted_tree(tmp_path):
    from dcel_builder.tree_loader import load_tree_inputs

    (tmp_path / "edges.json").write_text(json.dumps([[0, 1], [0, 2], [2, 3]]))
    (tmp_path / "stats.json").write_text(json.dumps({"leaf_depths": {"1": 1}}))
    (tmp_path / "index.json").write_text(json.dumps({"0": "root", "3": "leaf"}))

    tree, stats, zone_index = load_tree_inputs(
        tmp_path / "edges.json",
        tmp_path / "stats.json",
        tmp_path / "index.json",
    )

    assert tree.root == 0
    assert tree.children[0] == (1, 2)
    assert tree.leaves == (1, 3)
    assert tree.max_depth == 2
    assert stats["leaf_depths"] == {"1": 1}
    assert zone_index[3] == "leaf"


def test_load_tree_inputs_rejects_cycle(tmp_path):
    from dcel_builder.tree_loader import load_tree_inputs

    (tmp_path / "edges.json").write_text(json.dumps([[0, 1], [1, 2], [2, 0]]))
    (tmp_path / "stats.json").write_text(json.dumps({}))
    (tmp_path / "index.json").write_text(json.dumps({}))

    with pytest.raises(ValueError, match="root"):
        load_tree_inputs(
            tmp_path / "edges.json",
            tmp_path / "stats.json",
            tmp_path / "index.json",
        )


def test_load_tree_inputs_rejects_multiple_parents(tmp_path):
    from dcel_builder.tree_loader import load_tree_inputs

    (tmp_path / "edges.json").write_text(json.dumps([[0, 2], [1, 2]]))
    (tmp_path / "stats.json").write_text(json.dumps({}))
    (tmp_path / "index.json").write_text(json.dumps({}))

    with pytest.raises(ValueError, match="one parent|exactly one parent"):
        load_tree_inputs(
            tmp_path / "edges.json",
            tmp_path / "stats.json",
            tmp_path / "index.json",
        )
