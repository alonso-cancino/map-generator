from __future__ import annotations

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

    assert dcel_builder._package_version() == "0.2.0"
