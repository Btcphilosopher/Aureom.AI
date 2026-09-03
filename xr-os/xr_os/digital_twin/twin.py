"""Connects XR-OS to an external digital twin data source and mirrors its assets into the spatial world."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable

from pydantic import BaseModel, Field

from xr_os.core.spatial_object import SpatialObject, SpatialObjectType
from xr_os.core.world_model import SpatialWorldModel
from xr_os.scene.graph import XRSceneGraph
from xr_os.scene.nodes import ModelNode


class TwinAsset(BaseModel):
    """One piece of physical infrastructure as represented in the digital twin."""

    id: str
    name: str
    kind: str = "asset"
    position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotation: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0)
    telemetry: dict = Field(default_factory=dict)


class DigitalTwinSource(ABC):
    """Contract for wherever twin data actually comes from (a factory SCADA/BIM system, a REST API, ...)."""

    @abstractmethod
    def fetch_assets(self) -> list[TwinAsset]: ...


class HttpJsonTwinSource(DigitalTwinSource):
    """Fetches a JSON array of assets from a REST endpoint, via a caller-supplied mapping function."""

    def __init__(self, url: str, mapper: Callable[[dict], TwinAsset] | None = None, timeout: float = 5.0) -> None:
        self.url = url
        self.timeout = timeout
        self.mapper = mapper or self._default_mapper

    @staticmethod
    def _default_mapper(item: dict) -> TwinAsset:
        return TwinAsset(
            id=str(item["id"]),
            name=item.get("name", str(item["id"])),
            kind=item.get("kind", "asset"),
            position=tuple(item.get("position", (0.0, 0.0, 0.0))),
            rotation=tuple(item.get("rotation", (0.0, 0.0, 0.0, 1.0))),
            telemetry=item.get("telemetry", {}),
        )

    def fetch_assets(self) -> list[TwinAsset]:
        import httpx

        response = httpx.get(self.url, timeout=self.timeout)
        response.raise_for_status()
        return [self.mapper(item) for item in response.json()]


class StaticTwinSource(DigitalTwinSource):
    """A fixed, in-memory set of assets -- useful for tests, demos, and offline twins."""

    def __init__(self, assets: list[TwinAsset]) -> None:
        self._assets = assets

    def fetch_assets(self) -> list[TwinAsset]:
        return list(self._assets)

    def update_telemetry(self, asset_id: str, telemetry: dict) -> None:
        for asset in self._assets:
            if asset.id == asset_id:
                asset.telemetry.update(telemetry)


class DigitalTwinConnector:
    """Pulls assets from a ``DigitalTwinSource`` into the spatial world model (and, optionally, the scene graph)."""

    def __init__(self, source: DigitalTwinSource, world_model: SpatialWorldModel, scene_graph: XRSceneGraph | None = None) -> None:
        self.source = source
        self.world_model = world_model
        self.scene_graph = scene_graph
        self._nodes: dict[str, str] = {}  # asset_id -> scene node id

    def sync(self) -> list[SpatialObject]:
        objects: list[SpatialObject] = []
        for asset in self.source.fetch_assets():
            object_id = f"twin.{asset.id}"
            existing = self.world_model.get(object_id)
            if existing is None:
                obj = SpatialObject(
                    id=object_id,
                    type=SpatialObjectType.VIRTUAL_OBJECT,
                    label=asset.name,
                    position=asset.position,
                    rotation=asset.rotation,
                    metadata={"digital_twin": True, "kind": asset.kind, "telemetry": asset.telemetry},
                )
                self.world_model.add(obj)
            else:
                existing.position = asset.position
                existing.rotation = asset.rotation
                existing.metadata["telemetry"] = asset.telemetry
                existing.touch()
                obj = existing
            objects.append(obj)
            if self.scene_graph is not None:
                self._sync_node(asset, obj)
        return objects

    def _sync_node(self, asset: TwinAsset, obj: SpatialObject) -> None:
        node_id = self._nodes.get(asset.id)
        node = self.scene_graph.find(node_id) if node_id else None
        if node is None:
            node = ModelNode(asset.name, node_id=obj.id, spatial_object_id=obj.id)
            self.scene_graph.add_virtual(node)
            self._nodes[asset.id] = node.id
        node.local_transform = obj.transform
        node.metadata["telemetry"] = asset.telemetry
