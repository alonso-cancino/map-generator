from __future__ import annotations

import json


def test_build_frontend_bundle_includes_all_tree_levels(tmp_path):
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
    bundle = build_frontend_bundle(dcel, tree, zone_index)

    assert bundle["root_id"] == 0
    assert bundle["max_depth"] == 2
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
    assert all(0.0 <= value <= 1.0 for value in root["bbox"])
    assert root["bbox"][0] <= leaf["bbox"][0] <= leaf["bbox"][2] <= root["bbox"][2]
    assert root["bbox"][1] <= leaf["bbox"][1] <= leaf["bbox"][3] <= root["bbox"][3]
    assert bundle["borders"], "expected shared borders in frontend bundle"
    for border in bundle["borders"]:
        assert len(border["zone_ids"]) == 2
        assert border["path"].startswith("M")


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
