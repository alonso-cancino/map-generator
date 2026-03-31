from __future__ import annotations

from collections import deque

import numpy as np

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


def test_recursive_builder_assigns_every_leaf_and_validates():
    from dcel_builder.hierarchy import build_leaf_dcel_from_tree

    result = build_leaf_dcel_from_tree(
        tree=_small_tree(),
        seed=7,
        resolution=96,
        land_fraction=0.45,
        noise_exponent=2.3,
        warp_strength=0.08,
    )

    assert set(result.leaf_label_by_zone) == {1, 3, 4, 5}
    assert np.sum(result.label_map >= 0) == result.report["continent_pixels"]
    assert set(np.unique(result.label_map[result.label_map >= 0])) == {0, 1, 2, 3}
    result.dcel.validate()


def test_recursive_builder_produces_connected_leaf_regions():
    from dcel_builder.hierarchy import build_leaf_dcel_from_tree

    result = build_leaf_dcel_from_tree(
        tree=_small_tree(),
        seed=11,
        resolution=96,
        land_fraction=0.42,
        noise_exponent=2.1,
        warp_strength=0.06,
    )

    for label_value in np.unique(result.label_map[result.label_map >= 0]):
        mask = result.label_map == label_value
        assert _is_connected(mask)


def test_recursive_builder_allocates_more_area_to_larger_subtrees():
    from dcel_builder.hierarchy import build_leaf_dcel_from_tree

    result = build_leaf_dcel_from_tree(
        tree=_small_tree(),
        seed=13,
        resolution=96,
        land_fraction=0.42,
        noise_exponent=2.1,
        warp_strength=0.06,
    )

    leaf_counts = result.report["leaf_pixel_counts"]
    assert leaf_counts[4] + leaf_counts[5] > leaf_counts[1]
    assert leaf_counts[4] + leaf_counts[5] > leaf_counts[3]


def _is_connected(mask: np.ndarray) -> bool:
    coords = np.argwhere(mask)
    if coords.size == 0:
        return False
    start = tuple(int(v) for v in coords[0])
    seen = {start}
    queue = deque([start])

    while queue:
        row, col = queue.popleft()
        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nr, nc = row + dr, col + dc
            nxt = (nr, nc)
            if (
                0 <= nr < mask.shape[0]
                and 0 <= nc < mask.shape[1]
                and mask[nr, nc]
                and nxt not in seen
            ):
                seen.add(nxt)
                queue.append(nxt)

    return len(seen) == int(mask.sum())
