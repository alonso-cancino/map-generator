from __future__ import annotations

import re
from importlib.metadata import PackageNotFoundError


def test_package_version_looks_up_distribution_name(monkeypatch):
    import dcel_builder

    def fake_version(name: str) -> str:
        assert name == "dcel-map-generator"
        return "9.9.9"

    monkeypatch.setattr(dcel_builder, "version", fake_version)

    assert dcel_builder._package_version() == "9.9.9"


def test_package_version_falls_back_when_distribution_missing(monkeypatch):
    import dcel_builder

    def fake_version(name: str) -> str:
        raise PackageNotFoundError(name)

    monkeypatch.setattr(dcel_builder, "version", fake_version)

    result = dcel_builder._package_version()
    # The fallback version should be a valid semver string, not empty
    assert re.fullmatch(r"\d+\.\d+\.\d+", result), f"Invalid fallback version: {result}"
