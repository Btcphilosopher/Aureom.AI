"""
MITHRIL.OS — Entity Component System core.

Spec ref: 91 (engine/ecs), 67 (ECS).

A deliberately small, dependency-free ECS. Entities are bare integer ids.
Components are plain dataclasses stored in per-type dictionaries keyed by
entity id. This keeps the simulation introspectable (section 101/102 debug
overlays can iterate `World.components` directly) and trivially
serializable (section 60 save system).

Determinism note (section 62): entity ids are assigned by a monotonic
counter seeded from GameState, never from hashing or wall-clock time, so
two runs with identical commands allocate identical ids.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, Optional, Set, Tuple, Type, TypeVar

EntityId = int
C = TypeVar("C")


class World:
    """Container for all entities and their components."""

    def __init__(self) -> None:
        self._next_id: EntityId = 1
        self.components: Dict[str, Dict[EntityId, Any]] = {}
        self.tags: Dict[EntityId, Set[str]] = {}
        self.kind: Dict[EntityId, str] = {}
        self.alive: Set[EntityId] = set()

    # -- entity lifecycle -------------------------------------------------

    def create_entity(self, kind: str) -> EntityId:
        eid = self._next_id
        self._next_id += 1
        self.alive.add(eid)
        self.kind[eid] = kind
        self.tags[eid] = set()
        return eid

    def destroy_entity(self, eid: EntityId) -> None:
        if eid not in self.alive:
            return
        self.alive.discard(eid)
        self.kind.pop(eid, None)
        self.tags.pop(eid, None)
        for store in self.components.values():
            store.pop(eid, None)

    def is_alive(self, eid: EntityId) -> bool:
        return eid in self.alive

    # -- components ---------------------------------------------------------

    @staticmethod
    def _key(component_type: Type[C]) -> str:
        return component_type.__name__

    def add(self, eid: EntityId, component: C) -> C:
        key = self._key(type(component))
        self.components.setdefault(key, {})[eid] = component
        return component

    def get(self, eid: EntityId, component_type: Type[C]) -> Optional[C]:
        return self.components.get(self._key(component_type), {}).get(eid)

    def require(self, eid: EntityId, component_type: Type[C]) -> C:
        comp = self.get(eid, component_type)
        if comp is None:
            raise KeyError(f"entity {eid} missing component {component_type.__name__}")
        return comp

    def has(self, eid: EntityId, component_type: Type[C]) -> bool:
        return eid in self.components.get(self._key(component_type), {})

    def remove(self, eid: EntityId, component_type: Type[C]) -> None:
        self.components.get(self._key(component_type), {}).pop(eid, None)

    def query(self, *component_types: Type[Any]) -> Iterator[Tuple[EntityId, ...]]:
        """Iterate entities that own every given component type, yielding
        (eid, comp1, comp2, ...) tuples ordered by ascending entity id for
        determinism."""
        if not component_types:
            return
        stores = [self.components.get(self._key(ct), {}) for ct in component_types]
        base = stores[0]
        for eid in sorted(base.keys()):
            if eid not in self.alive:
                continue
            row = [base[eid]]
            ok = True
            for store in stores[1:]:
                if eid not in store:
                    ok = False
                    break
                row.append(store[eid])
            if ok:
                yield (eid, *row)

    def entities_of_kind(self, kind: str) -> Iterator[EntityId]:
        for eid in sorted(self.alive):
            if self.kind.get(eid) == kind:
                yield eid
