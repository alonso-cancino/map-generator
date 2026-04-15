from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_demo_script_writes_expected_outputs(tmp_path: Path):
    repo_root = Path(__file__).resolve().parents[2]
    output_dir = tmp_path / "demo"
    script_path = repo_root / "scripts" / "demo_roughened_borders.py"

    result = subprocess.run(
        [
            sys.executable,
            str(script_path),
            "--resolution",
            "96",
            "--seed",
            "17",
            "--roughen-amplitude",
            "3.0",
            "--output-dir",
            str(output_dir),
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Roughened border demo summary" in result.stdout
    assert (output_dir / "baseline_seeded.png").exists()
    assert (output_dir / "experimental_roughened.png").exists()
    assert (output_dir / "comparison.png").exists()
