from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np

from dcel_builder.hierarchy import build_leaf_dcel_from_tree
from dcel_builder.tree_loader import ZoneTree


def _small_tree() -> ZoneTree:
    return ZoneTree(
        root=0,
        children={
            0: (1, 2, 3),
            1: (),
            2: (4, 5),
            3: (),
            4: (),
            5: (),
        },
        parent={0: None, 1: 0, 2: 0, 3: 0, 4: 2, 5: 2},
        depth={0: 0, 1: 1, 2: 1, 3: 1, 4: 2, 5: 2},
        leaves=(1, 3, 4, 5),
    )


def test_contour_guided_split_mode_builds_valid_but_distinct_partition():
    tree = _small_tree()
    seeded = build_leaf_dcel_from_tree(
        tree=tree,
        seed=17,
        resolution=96,
        land_fraction=0.42,
        noise_exponent=2.1,
        warp_strength=0.06,
        split_mode="seeded",
    )
    contour_guided = build_leaf_dcel_from_tree(
        tree=tree,
        seed=17,
        resolution=96,
        land_fraction=0.42,
        noise_exponent=2.1,
        warp_strength=0.06,
        split_mode="contour_guided",
    )

    seeded.dcel.validate()
    contour_guided.dcel.validate()
    assert seeded.label_map.shape == contour_guided.label_map.shape
    assert np.any(seeded.label_map != contour_guided.label_map)


def test_contour_guided_demo_script_writes_expected_outputs(tmp_path: Path):
    repo_root = Path(__file__).resolve().parents[2]
    output_dir = tmp_path / "demo"
    script_path = repo_root / "scripts" / "demo_contour_guided_splits.py"

    result = subprocess.run(
        [
            sys.executable,
            str(script_path),
            "--resolution",
            "96",
            "--seed",
            "17",
            "--output-dir",
            str(output_dir),
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Contour-guided split demo summary" in result.stdout
    assert (output_dir / "baseline_seeded.png").exists()
    assert (output_dir / "experimental_contour_guided.png").exists()
    assert (output_dir / "comparison.png").exists()
