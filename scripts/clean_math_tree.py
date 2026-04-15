"""Clean up the mathematics hierarchy tree.

Applies renames, removals, reparentings, and additions to ensure every node
represents a legitimate field or subfield of mathematics.
"""

from __future__ import annotations

import json
from collections import defaultdict, deque
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# 1. Renames: {id: new_name}
# ---------------------------------------------------------------------------
RENAMES: dict[int, str] = {
    128: "computational_commutative_algebra",
    176: "abstract_harmonic_analysis",
    186: "fluid_pdes",
    187: "dispersive_pdes",
    193: "topological_dynamics",
    198: "classical_curves",
    203: "projective_invariants",
    225: "convex_analysis",
    239: "metrization_theory",
    251: "differential_structures",
    264: "zeta_functions",
    266: "prime_distribution_theory",
    267: "sieve_theory",
    270: "analytic_methods_in_number_theory",
    286: "geometry_of_numbers_lattices",
    307: "structural_proof_theory",
    323: "lattice_path_combinatorics",
    324: "enumeration_under_symmetry",
    325: "combinatorial_identities",
    379: "bayesian_computation",
    408: "mathematical_fluid_dynamics",
    412: "mathematical_epidemiology",
    413: "mathematical_neuroscience",
    415: "biological_network_theory",
    416: "mathematical_phylogenetics",
    417: "derivative_pricing_theory",
    418: "quantitative_risk_management",
    421: "financial_risk_theory",
    437: "reliability_theory",
    462: "nondeterministic_computation",
    470: "combinatorial_algorithms",
    471: "algorithmic_graph_theory",
    475: "sublinear_computation",
    477: "parallel_computation_theory",
    520: "convergence_of_integrals",
    524: "pointwise_ergodic_theory",
    552: "weak_and_strong_convergence",
    553: "normal_approximation_theory",
    564: "likelihood_theory",
    565: "moment_based_estimation",
    568: "algebraic_coding_theory",
}

# ---------------------------------------------------------------------------
# 2. Edges to remove  (parent, child)
# ---------------------------------------------------------------------------
EDGES_TO_REMOVE: set[tuple[int, int]] = {
    # Engineering subtree
    (9, 96), (96, 452), (96, 453), (96, 454),
    # Data assimilation
    (9, 98),
    # Physics subtree (old nodes)
    (87, 403), (403, 571), (403, 572),
    (87, 404), (404, 573), (404, 574),
    (87, 405), (87, 407), (87, 409), (87, 410),
    # Duplicates / merges
    (7, 79),    # topological_combinatorics_comb
    (102, 476), # sublinear_algorithms
    # Reparentings (remove old parent edge)
    (22, 156),  # measure_theory from real_analysis
    (15, 133),  # abelian_categories from homological_algebra
}

# IDs whose index entries should be deleted (before adding new ones)
IDS_TO_DELETE: set[int] = {
    # Engineering
    96, 452, 453, 454,
    # Data assimilation
    98,
    # Old physics nodes + their children
    403, 404, 405, 407, 409, 410, 571, 572, 573, 574,
    # Duplicates / merges
    79, 476,
}

# ---------------------------------------------------------------------------
# 3. New edges to add  (parent, child)
# ---------------------------------------------------------------------------
EDGES_TO_ADD: list[tuple[int, int]] = [
    # Reparentings
    (2, 156),   # measure_theory -> analysis (L2)
    (17, 133),  # abelian_categories -> category_theory
    # New math_physics children
    (87, 403),  # gauge_theory_physics
    (87, 404),  # conformal_field_theory
    (87, 405),  # topological_field_theory
    (87, 407),  # mathematical_mechanics
    (87, 409),  # spectral_theory_physics
    (87, 410),  # integrable_systems
    (87, 571),  # mathematical_quantum_theory
    (87, 572),  # mathematical_relativity
    # New fields (reusing freed IDs)
    (1, 96),    # tropical_algebra
    (5, 98),    # diophantine_approximation
    (119, 452), # geometric_group_theory
    (24, 453),  # operator_semigroups
    (28, 454),  # complex_dynamics
    (50, 476),  # applied_algebraic_topology
    (50, 79),   # persistent_homology
    (27, 573),  # stochastic_pdes
    (26, 574),  # delay_differential_equations
    (156, 578), # geometric_measure_theory
]

# ---------------------------------------------------------------------------
# 4. New index entries  {id: name}
# ---------------------------------------------------------------------------
NEW_INDEX_ENTRIES: dict[int, str] = {
    # Math physics replacements
    403: "gauge_theory_physics",
    404: "conformal_field_theory",
    405: "topological_field_theory",
    407: "mathematical_mechanics",
    409: "spectral_theory_physics",
    410: "integrable_systems",
    571: "mathematical_quantum_theory",
    572: "mathematical_relativity",
    # New fields
    96:  "tropical_algebra",
    98:  "diophantine_approximation",
    452: "geometric_group_theory",
    453: "operator_semigroups",
    454: "complex_dynamics",
    476: "applied_algebraic_topology",
    79:  "persistent_homology",
    573: "stochastic_pdes",
    574: "delay_differential_equations",
    578: "geometric_measure_theory",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_json(path: Path):
    return json.loads(path.read_text())


def write_json(path: Path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def compute_tree_stats(
    index: dict[int, str],
    edges: list[tuple[int, int]],
) -> dict:
    children: dict[int, list[int]] = defaultdict(list)
    parent: dict[int, int | None] = {}
    for p, c in edges:
        children[p].append(c)
        parent[c] = p

    all_nodes = set(parent.keys()) | set(children.keys())
    roots = [n for n in all_nodes if n not in parent]
    assert len(roots) == 1, f"Expected 1 root, found {len(roots)}"
    root = roots[0]

    # BFS to compute depths
    depth: dict[int, int] = {root: 0}
    queue: deque[int] = deque([root])
    while queue:
        node = queue.popleft()
        for child in children.get(node, []):
            depth[child] = depth[node] + 1
            queue.append(child)

    # Identify leaves
    leaves = {n for n in all_nodes if not children.get(n)}
    leaf_depths = {index[n]: depth[n] for n in sorted(leaves)}

    # Count leaf descendants per node
    def count_leaf_descendants(node: int) -> int:
        if node in leaves:
            return 1
        return sum(count_leaf_descendants(c) for c in children.get(node, []))

    # Per-level stats
    max_depth = max(depth.values())
    avg_leaf_descendants_per_level: dict[str, dict] = {}
    for level in range(max_depth + 1):
        nodes_at_level = [n for n, d in depth.items() if d == level]
        if not nodes_at_level:
            continue
        counts = [count_leaf_descendants(n) for n in nodes_at_level]
        # Only include nodes that have leaf descendants (internal + leaf nodes)
        # Actually the original stats include all nodes at each level
        avg_leaf_descendants_per_level[str(level)] = {
            "node_count": len(nodes_at_level),
            "avg_leaf_descendants": round(sum(counts) / len(counts), 2),
            "min_leaf_descendants": min(counts),
            "max_leaf_descendants": max(counts),
        }

    return {
        "leaf_depths": dict(sorted(leaf_depths.items())),
        "avg_leaf_descendants_per_level": avg_leaf_descendants_per_level,
    }


def validate_tree(index: dict[int, str], edges: list[tuple[int, int]]):
    """Validate the tree is a proper arborescence."""
    import networkx as nx

    g = nx.DiGraph()
    g.add_edges_from(edges)

    # Check single root
    roots = [n for n in g.nodes if g.in_degree(n) == 0]
    assert len(roots) == 1, f"Expected 1 root, found {len(roots)}: {roots}"

    # Check arborescence
    assert nx.is_arborescence(g), "Not a valid arborescence"

    # Check index consistency
    edge_nodes = set()
    for p, c in edges:
        edge_nodes.add(p)
        edge_nodes.add(c)
    index_ids = set(index.keys())
    assert edge_nodes == index_ids, (
        f"Mismatch: in edges but not index: {edge_nodes - index_ids}, "
        f"in index but not edges: {index_ids - edge_nodes}"
    )

    # Check name uniqueness
    names = list(index.values())
    assert len(names) == len(set(names)), (
        f"Duplicate names found: "
        f"{[n for n in names if names.count(n) > 1]}"
    )

    # Check no remaining theorem/equation names
    bad_patterns = ["_theorem", "_equation", "_lemma", "_conjecture", "_law_of_"]
    flagged = [
        (nid, name)
        for nid, name in index.items()
        if any(pat in name for pat in bad_patterns)
    ]
    if flagged:
        print(f"WARNING: Potentially problematic names remaining: {flagged}")

    print(f"Validation passed: {len(index)} nodes, {len(edges)} edges, "
          f"root={roots[0]}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    index_path = ROOT / "zone_index.json"
    edges_path = ROOT / "zone_edges.json"
    stats_path = ROOT / "zone_tree_stats.json"

    # Load
    raw_index = load_json(index_path)
    index: dict[int, str] = {int(k): str(v) for k, v in raw_index.items()}
    raw_edges: list[list[int]] = load_json(edges_path)
    edges: list[tuple[int, int]] = [(p, c) for p, c in raw_edges]

    print(f"Loaded: {len(index)} nodes, {len(edges)} edges")

    # Step 1: Apply renames
    for nid, new_name in RENAMES.items():
        assert nid in index, f"Rename target {nid} not in index"
        old = index[nid]
        index[nid] = new_name
        print(f"  Renamed {nid}: {old} -> {new_name}")

    # Step 2: Remove edges
    edges = [e for e in edges if (e[0], e[1]) not in EDGES_TO_REMOVE]
    print(f"  Removed {len(EDGES_TO_REMOVE)} edges, {len(edges)} remaining")

    # Step 3: Remove index entries for deleted nodes
    for nid in IDS_TO_DELETE:
        if nid in index:
            old = index.pop(nid)
            print(f"  Deleted node {nid}: {old}")

    # Step 4: Add new index entries
    for nid, name in NEW_INDEX_ENTRIES.items():
        assert nid not in index, f"ID {nid} already in index as {index[nid]}"
        index[nid] = name
        print(f"  Added node {nid}: {name}")

    # Step 5: Add new edges
    for p, c in EDGES_TO_ADD:
        edges.append((p, c))
        print(f"  Added edge [{p}, {c}] ({index.get(p, '?')} -> {index.get(c, '?')})")

    print(f"\nResult: {len(index)} nodes, {len(edges)} edges")

    # Step 6: Validate
    validate_tree(index, edges)

    # Step 7: Compute stats
    stats = compute_tree_stats(index, edges)
    leaf_count = len(stats["leaf_depths"])
    max_depth = max(stats["leaf_depths"].values())
    print(f"Stats: {leaf_count} leaves, max depth {max_depth}")

    # Step 8: Write output
    out_index = {str(k): v for k, v in sorted(index.items())}
    out_edges = sorted(edges)
    write_json(index_path, out_index)
    write_json(edges_path, out_edges)
    write_json(stats_path, stats)
    print(f"\nWrote {index_path.name}, {edges_path.name}, {stats_path.name}")


if __name__ == "__main__":
    main()
