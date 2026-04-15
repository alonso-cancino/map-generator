"""Tree-first recursive DCEL generation from a hierarchical zone tree."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from dcel_builder.frontend_bundle import build_frontend_bundle
from dcel_builder.hierarchy import build_leaf_dcel_from_tree
from dcel_builder.tree_loader import load_tree_inputs


def _package_version() -> str:
    try:
        return version("dcel-map-generator")
    except PackageNotFoundError:
        return "0.9.2"


__version__ = _package_version()


def generate_map_artifacts(
    zone_edges_path: str | Path,
    tree_stats_path: str | Path,
    zone_index_path: str | Path,
    seed: int | None = None,
    resolution: int = 512,
    land_fraction: float = 0.40,
    noise_exponent: float = 2.3,
    warp_strength: float = 0.10,
    split_mode: str = "contour_guided",
    quiet: bool = False,
    blob_radius: float = 0.5,
    disk_radius: int | None = None,
    area_floor: float = 0.5,
) -> tuple:
    """Build the core map artifacts from a rooted zone tree."""
    del blob_radius
    del disk_radius
    del area_floor

    tree, tree_stats, zone_index = load_tree_inputs(
        zone_edges_path,
        tree_stats_path,
        zone_index_path,
    )
    result = build_leaf_dcel_from_tree(
        tree=tree,
        seed=seed,
        resolution=resolution,
        land_fraction=land_fraction,
        noise_exponent=noise_exponent,
        warp_strength=warp_strength,
        split_mode=split_mode,
    )
    dcel, report = result.dcel, result.report
    report["tree_stats_loaded"] = bool(tree_stats)
    report["zone_index_loaded"] = bool(zone_index)

    if not quiet:
        interior = sum(1 for face in dcel.faces if not face.is_outer)
        print(
            f"Built recursive tree-first DCEL with {interior} leaf faces and "
            f"{len(dcel.halfedges)} halfedges."
        )

    return dcel, report, tree, zone_index


def generate_dcel(
    zone_edges_path: str | Path,
    tree_stats_path: str | Path,
    zone_index_path: str | Path,
    seed: int | None = None,
    resolution: int = 512,
    land_fraction: float = 0.40,
    noise_exponent: float = 2.3,
    warp_strength: float = 0.10,
    split_mode: str = "contour_guided",
    quiet: bool = False,
    blob_radius: float = 0.5,
    disk_radius: int | None = None,
    area_floor: float = 0.5,
) -> tuple:
    """Build a leaf-level DCEL from a rooted zone tree."""
    dcel, report, _, _ = generate_map_artifacts(
        zone_edges_path=zone_edges_path,
        tree_stats_path=tree_stats_path,
        zone_index_path=zone_index_path,
        seed=seed,
        resolution=resolution,
        land_fraction=land_fraction,
        noise_exponent=noise_exponent,
        warp_strength=warp_strength,
        split_mode=split_mode,
        quiet=quiet,
        blob_radius=blob_radius,
        disk_radius=disk_radius,
        area_floor=area_floor,
    )
    return dcel, report


def generate_frontend_bundle(
    zone_edges_path: str | Path,
    tree_stats_path: str | Path,
    zone_index_path: str | Path,
    seed: int | None = None,
    resolution: int = 512,
    land_fraction: float = 0.40,
    noise_exponent: float = 2.3,
    warp_strength: float = 0.10,
    split_mode: str = "contour_guided",
    quiet: bool = False,
    blob_radius: float = 0.5,
    disk_radius: int | None = None,
    area_floor: float = 0.5,
) -> tuple[dict, dict]:
    """Build a frontend-ready hierarchy bundle from a rooted zone tree."""
    dcel, report, tree, zone_index = generate_map_artifacts(
        zone_edges_path=zone_edges_path,
        tree_stats_path=tree_stats_path,
        zone_index_path=zone_index_path,
        seed=seed,
        resolution=resolution,
        land_fraction=land_fraction,
        noise_exponent=noise_exponent,
        warp_strength=warp_strength,
        split_mode=split_mode,
        quiet=quiet,
        blob_radius=blob_radius,
        disk_radius=disk_radius,
        area_floor=area_floor,
    )
    return build_frontend_bundle(dcel, tree, zone_index), report
