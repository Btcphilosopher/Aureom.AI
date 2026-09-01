"""
Traceability (spec item 30): full manufacturing genealogy from raw-material
batch through electrode batch, cell, module and pack.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass


@dataclass
class GenealogyNode:
    node_id: str
    node_type: str  # "material_batch" | "electrode_batch" | "cell" | "module" | "pack"


class GenealogyGraph:
    """A simple directed acyclic "consumed by" graph. Forward = towards the
    finished product; backward = towards raw materials."""

    def __init__(self) -> None:
        self.nodes: dict[str, GenealogyNode] = {}
        self.forward: dict[str, set[str]] = defaultdict(set)   # parent -> children
        self.backward: dict[str, set[str]] = defaultdict(set)  # child -> parents

    def add_node(self, node_id: str, node_type: str) -> None:
        self.nodes.setdefault(node_id, GenealogyNode(node_id, node_type))

    def link(self, parent_id: str, child_id: str) -> None:
        self.forward[parent_id].add(child_id)
        self.backward[child_id].add(parent_id)

    def trace_forward(self, node_id: str) -> set[str]:
        seen: set[str] = set()
        frontier = [node_id]
        while frontier:
            current = frontier.pop()
            for child in self.forward.get(current, ()):
                if child not in seen:
                    seen.add(child)
                    frontier.append(child)
        return seen

    def trace_backward(self, node_id: str) -> set[str]:
        seen: set[str] = set()
        frontier = [node_id]
        while frontier:
            current = frontier.pop()
            for parent in self.backward.get(current, ()):
                if parent not in seen:
                    seen.add(parent)
                    frontier.append(parent)
        return seen
