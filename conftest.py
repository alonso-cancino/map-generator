"""Shared pytest fixtures for all test modules."""

import networkx as nx
import pytest


@pytest.fixture
def sample_graph() -> nx.Graph:
    """A small known-planar graph: 4-cycle plus one diagonal.

    Nodes: 0, 1, 2, 3
    Edges: (0,1), (1,2), (2,3), (3,0), (0,2)   [5 edges]
    Faces (Euler: F = E - V + 2 = 3):
      - interior triangle (0, 1, 2)
      - interior triangle (0, 2, 3)
      - outer face
    """
    G = nx.Graph()
    G.add_nodes_from([0, 1, 2, 3])
    G.add_edges_from([(0, 1), (1, 2), (2, 3), (3, 0), (0, 2)])
    return G


@pytest.fixture
def sample_embedding(sample_graph) -> nx.PlanarEmbedding:
    """Planar embedding of the sample_graph fixture."""
    is_planar, embedding = nx.check_planarity(sample_graph)
    assert is_planar
    return embedding
