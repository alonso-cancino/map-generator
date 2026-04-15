from __future__ import annotations

import numpy as np
from scipy.ndimage import label as scipy_label

from dcel_builder.border_roughening import roughen_borders


def _simple_label_map() -> tuple[np.ndarray, np.ndarray]:
    label_map = np.full((64, 64), -1, dtype=np.int32)
    label_map[8:56, 8:32] = 0
    label_map[8:56, 32:56] = 1
    continent_mask = label_map >= 0
    return label_map, continent_mask


def test_roughened_borders_changes_label_map() -> None:
    label_map, continent_mask = _simple_label_map()
    result = roughen_borders(
        label_map,
        continent_mask=continent_mask,
        amplitude=3.0,
        exponent=2.0,
        master_seed=42,
    )
    assert not np.array_equal(result, label_map)


def test_roughened_borders_preserves_connectivity() -> None:
    label_map, continent_mask = _simple_label_map()
    result = roughen_borders(
        label_map,
        continent_mask=continent_mask,
        amplitude=3.0,
        exponent=2.0,
        master_seed=42,
    )
    for label_value in [0, 1]:
        region = result == label_value
        _, count = scipy_label(region)
        assert count == 1


def test_roughened_borders_area_change_is_bounded() -> None:
    label_map, continent_mask = _simple_label_map()
    result = roughen_borders(
        label_map,
        continent_mask=continent_mask,
        amplitude=2.0,
        exponent=2.0,
        master_seed=42,
    )
    total = int(np.sum(continent_mask))
    for label_value in [0, 1]:
        original_area = int(np.sum(label_map == label_value)) / total
        new_area = int(np.sum(result == label_value)) / total
        assert abs(new_area - original_area) < 0.05
