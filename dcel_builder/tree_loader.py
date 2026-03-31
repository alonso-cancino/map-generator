"""Load and validate the hierarchical zone tree."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import networkx as nx


@dataclass(frozen=True)
class ZoneTree:
    """Validated rooted tree metadata."""

    root: int
    children: dict[int, tuple[int, ...]]
    parent: dict[int, int | None]
    depth: dict[int, int]
    leaves: tuple[int, ...]

    @property
    def nodes(self) -> tuple[int, ...]:
        return tuple(self.parent)

    @property
    def max_depth(self) -> int:
        return max(self.depth.values(), default=0)

    def descendants(self, node_id: int) -> tuple[int, ...]:
        """Return all descendants of a node, excluding the node itself."""
        out: list[int] = []
        stack = list(self.children.get(node_id, ()))
        while stack:
            current = stack.pop()
            out.append(current)
            stack.extend(self.children.get(current, ()))
        return tuple(out)


def load_tree_inputs(
    zone_edges_path: str | Path,
    tree_stats_path: str | Path,
    zone_index_path: str | Path,
) -> tuple[ZoneTree, dict, dict[int, str]]:
    """Load the rooted tree and optional sidecar files."""
    zone_edges_path = Path(zone_edges_path)
    if not zone_edges_path.exists():
        raise ValueError(f"Input file not found: {zone_edges_path}")

    try:
        edge_data = json.loads(zone_edges_path.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {zone_edges_path}: {exc}") from exc

    if not isinstance(edge_data, list):
        raise ValueError(f"Expected edge-list JSON in {zone_edges_path}")

    edges: list[tuple[int, int]] = []
    seen: set[tuple[int, int]] = set()
    for entry in edge_data:
        if not isinstance(entry, list | tuple) or len(entry) != 2:
            raise ValueError(f"Invalid edge entry: {entry!r}")
        parent, child = entry
        if not isinstance(parent, int) or not isinstance(child, int):
            raise ValueError(f"Zone edge endpoints must be integers: {entry!r}")
        if parent == child:
            raise ValueError(f"Self-loops are not supported: ({parent}, {child})")
        key = (parent, child)
        if key in seen:
            raise ValueError(f"Duplicate directed edge: ({parent}, {child})")
        seen.add(key)
        edges.append(key)

    tree = _build_zone_tree(edges)
    tree_stats = _load_optional_json(Path(tree_stats_path))
    zone_index_raw = _load_optional_json(Path(zone_index_path))
    zone_index = {int(node_id): str(name) for node_id, name in zone_index_raw.items()}
    return tree, tree_stats, zone_index


def _build_zone_tree(edges: list[tuple[int, int]]) -> ZoneTree:
    if not edges:
        raise ValueError("Zone tree is empty.")

    graph = nx.DiGraph()
    graph.add_edges_from(edges)

    multi_parent_nodes = [node for node in graph.nodes if graph.in_degree(node) > 1]
    if multi_parent_nodes:
        node = multi_parent_nodes[0]
        raise ValueError(
            f"Node {node} must have exactly one parent, found {graph.in_degree(node)}."
        )

    roots = [node for node in graph.nodes if graph.in_degree(node) == 0]
    if len(roots) != 1:
        raise ValueError(f"Expected exactly one root, found {len(roots)}.")

    for node in graph.nodes:
        indegree = graph.in_degree(node)
        if node == roots[0]:
            if indegree != 0:
                raise ValueError("Root must have indegree 0.")
            continue
        if indegree != 1:
            raise ValueError(f"Node {node} must have exactly one parent, found {indegree}.")

    if not nx.is_arborescence(graph):
        raise ValueError("Zone edges must define a connected rooted tree.")

    root = roots[0]
    children = {
        node: tuple(sorted(graph.successors(node)))
        for node in sorted(graph.nodes)
    }
    parent = {root: None}
    depth = {root: 0}
    queue = [root]
    while queue:
        node = queue.pop(0)
        for child in children[node]:
            parent[child] = node
            depth[child] = depth[node] + 1
            queue.append(child)

    leaves = tuple(sorted(node for node, kids in children.items() if not kids))
    return ZoneTree(
        root=root,
        children=children,
        parent=parent,
        depth=depth,
        leaves=leaves,
    )


def _load_optional_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"Expected object JSON in {path}")
    return data
