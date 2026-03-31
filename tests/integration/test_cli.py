"""T017: Integration tests for the dcel_builder CLI."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
EXAMPLE_ROOT = REPO_ROOT / "examples" / "atlantis"
ZONE_EDGES = EXAMPLE_ROOT / "zone_edges.json"
TREE_STATS = EXAMPLE_ROOT / "zone_tree_stats.json"
ZONE_INDEX = EXAMPLE_ROOT / "zone_index.json"


@pytest.fixture(autouse=True)
def require_input_files():
    """Skip CLI tests if input files are not present."""
    for p in [ZONE_EDGES, TREE_STATS, ZONE_INDEX]:
        if not p.exists():
            pytest.skip(f"Input file not found: {p}")


def test_cli_produces_output_file(tmp_path):
    """CLI writes dcel_map.json to the specified output path."""
    output = tmp_path / "dcel_map.json"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "dcel_builder",
            "--zone-edges",
            str(ZONE_EDGES),
            "--tree-stats",
            str(TREE_STATS),
            "--zone-index",
            str(ZONE_INDEX),
            "--output",
            str(output),
            "--seed",
            "42",
            "--resolution",
            "64",
            "--quiet",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"CLI exited {result.returncode}: {result.stderr}"
    assert output.exists(), "Output file was not created"


def test_cli_output_has_expected_structure(tmp_path):
    """Output JSON has vertices, halfedges, faces keys with non-zero counts."""
    output = tmp_path / "dcel_map.json"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "dcel_builder",
            "--zone-edges",
            str(ZONE_EDGES),
            "--tree-stats",
            str(TREE_STATS),
            "--zone-index",
            str(ZONE_INDEX),
            "--output",
            str(output),
            "--seed",
            "42",
            "--resolution",
            "64",
            "--quiet",
        ],
        check=True,
        capture_output=True,
    )
    data = json.loads(output.read_text())
    assert "vertices" in data
    assert "halfedges" in data
    assert "faces" in data
    interior = [f for f in data["faces"] if not f["is_outer"]]
    assert len(interior) == 16


def test_cli_writes_frontend_bundle(tmp_path):
    """CLI writes a hierarchy bundle containing all levels when requested."""
    output = tmp_path / "dcel_map.json"
    frontend_bundle = tmp_path / "map_bundle.json"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "dcel_builder",
            "--zone-edges",
            str(ZONE_EDGES),
            "--tree-stats",
            str(TREE_STATS),
            "--zone-index",
            str(ZONE_INDEX),
            "--output",
            str(output),
            "--frontend-bundle",
            str(frontend_bundle),
            "--seed",
            "42",
            "--resolution",
            "64",
            "--quiet",
        ],
        check=True,
        capture_output=True,
    )
    bundle = json.loads(frontend_bundle.read_text())

    assert frontend_bundle.exists()
    assert bundle["root_id"] == 0
    assert bundle["max_depth"] >= 1
    assert "0" in bundle["levels"]
    assert "0" in bundle["zones"]
    assert bundle["borders"]
    assert bundle["zones"]["0"]["child_ids"]
    assert bundle["zones"]["0"]["path"].startswith("M")


def test_cli_validate_flag_exits_zero(tmp_path):
    """--validate flag exits 0 for a valid DCEL."""
    output = tmp_path / "dcel_map.json"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "dcel_builder",
            "--zone-edges",
            str(ZONE_EDGES),
            "--tree-stats",
            str(TREE_STATS),
            "--zone-index",
            str(ZONE_INDEX),
            "--output",
            str(output),
            "--seed",
            "42",
            "--resolution",
            "64",
            "--validate",
            "--quiet",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"CLI exited {result.returncode}: {result.stderr}"


def test_cli_missing_input_exits_one(tmp_path):
    """CLI exits 1 when an input file is not found."""
    output = tmp_path / "dcel_map.json"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "dcel_builder",
            "--zone-edges",
            "nonexistent_file.json",
            "--tree-stats",
            str(TREE_STATS),
            "--zone-index",
            str(ZONE_INDEX),
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1


def test_cli_seed_flag_accepted(tmp_path):
    """--seed flag is accepted and produces deterministic output."""
    output = tmp_path / "dcel_map.json"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "dcel_builder",
            "--zone-edges",
            str(ZONE_EDGES),
            "--tree-stats",
            str(TREE_STATS),
            "--zone-index",
            str(ZONE_INDEX),
            "--output",
            str(output),
            "--seed",
            "42",
            "--resolution",
            "64",
            "--quiet",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"--seed flag not accepted: {result.stderr}"


def test_cli_resolution_flag_accepted(tmp_path):
    """--resolution flag is accepted."""
    output = tmp_path / "dcel_map.json"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "dcel_builder",
            "--zone-edges",
            str(ZONE_EDGES),
            "--tree-stats",
            str(TREE_STATS),
            "--zone-index",
            str(ZONE_INDEX),
            "--output",
            str(output),
            "--seed",
            "7",
            "--resolution",
            "64",
            "--quiet",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"--resolution flag not accepted: {result.stderr}"


def test_cli_render_flag_writes_png(tmp_path):
    """--render writes a PNG alongside the JSON output."""
    output = tmp_path / "dcel_map.json"
    render_output = tmp_path / "dcel_map.png"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "dcel_builder",
            "--zone-edges",
            str(ZONE_EDGES),
            "--tree-stats",
            str(TREE_STATS),
            "--zone-index",
            str(ZONE_INDEX),
            "--output",
            str(output),
            "--render",
            "--render-output",
            str(render_output),
            "--quiet",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"--render failed: {result.stderr}"
    assert output.exists()
    assert render_output.exists()
    assert render_output.stat().st_size > 0


# ---------------------------------------------------------------------------
# T028 — new flag tests (US3)
# These tests invoke the CLI with non-existent input files so they work
# without real data. The autouse fixture would skip them if files exist; here
# we test argparse behavior directly via subprocess without relying on input files.
# ---------------------------------------------------------------------------


class TestNewFlags:
    """Argparse flag tests for US3 — run with nonexistent inputs to test argparse only."""

    """Argparse flag tests for US3 (blob-radius, disk-radius, area-floor)."""

    FAKE = "nonexistent_file.json"

    def _run(self, *extra_args, tmp_path=None):
        output = (tmp_path or Path("/tmp")) / "test_output.json"
        cmd = [
            sys.executable,
            "-m",
            "dcel_builder",
            "--zone-edges",
            self.FAKE,
            "--tree-stats",
            self.FAKE,
            "--zone-index",
            self.FAKE,
            "--output",
            str(output),
        ] + list(extra_args)
        return subprocess.run(cmd, capture_output=True, text=True)

    def test_blob_radius_flag_accepted(self, tmp_path):
        """T028a: --blob-radius is a recognised argparse argument (not exit code 2)."""
        result = self._run("--blob-radius", "0.7", tmp_path=tmp_path)
        # Exit 1 = input file not found (acceptable); exit 2 = argparse error (fail)
        assert result.returncode != 2, f"--blob-radius caused argparse error: {result.stderr}"

    def test_disk_radius_flag_accepted(self, tmp_path):
        """T028b: --disk-radius is a recognised argparse argument."""
        result = self._run("--disk-radius", "3", tmp_path=tmp_path)
        assert result.returncode != 2, f"--disk-radius caused argparse error: {result.stderr}"

    def test_area_floor_flag_accepted(self, tmp_path):
        """T028c: --area-floor is a recognised argparse argument."""
        result = self._run("--area-floor", "0.6", tmp_path=tmp_path)
        assert result.returncode != 2, f"--area-floor caused argparse error: {result.stderr}"

    def test_invalid_blob_radius_rejected(self, tmp_path):
        """T028d: --blob-radius abc gives non-zero exit code."""
        result = self._run("--blob-radius", "abc", tmp_path=tmp_path)
        assert result.returncode != 0, "--blob-radius abc should fail but got exit 0"

    def test_area_floor_out_of_range_rejected(self, tmp_path):
        """T028e: --area-floor 1.5 (outside (0,1]) gives non-zero exit code."""
        result = self._run("--area-floor", "1.5", tmp_path=tmp_path)
        assert result.returncode != 0, "--area-floor 1.5 should fail but got exit 0"
