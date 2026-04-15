from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from dcel_builder.tree_loader import load_tree_inputs


def test_cutline_demo_builder_produces_valid_dcel():
    from scripts.demo_cutline_splits import build_leaf_dcel_with_cutline_splits

    repo_root = Path(__file__).resolve().parents[2]
    tree, _, _ = load_tree_inputs(
        repo_root / "examples" / "atlantis" / "zone_edges.json",
        repo_root / "examples" / "atlantis" / "zone_tree_stats.json",
        repo_root / "examples" / "atlantis" / "zone_index.json",
    )

    result = build_leaf_dcel_with_cutline_splits(
        tree=tree,
        seed=17,
        resolution=96,
        land_fraction=0.40,
        noise_exponent=2.3,
        warp_strength=0.10,
    )

    result.dcel.validate()
    assert result.report["leaf_count"] == 16


def test_cutline_demo_script_writes_expected_outputs(tmp_path: Path):
    repo_root = Path(__file__).resolve().parents[2]
    output_dir = tmp_path / "demo"
    script_path = repo_root / "scripts" / "demo_cutline_splits.py"

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
    assert "Cut-line split demo summary" in result.stdout
    assert (output_dir / "baseline_seeded.png").exists()
    assert (output_dir / "experimental_cutline.png").exists()
    assert (output_dir / "comparison.png").exists()
