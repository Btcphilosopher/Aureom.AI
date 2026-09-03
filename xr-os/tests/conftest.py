"""Shared pytest fixtures for the XR-OS test suite."""

from __future__ import annotations

import pytest

from xr_os.core.world_model import SpatialWorldModel
from xr_os.runtime.services import XRServices
from xr_os.scene.graph import XRSceneGraph


@pytest.fixture
def world_model() -> SpatialWorldModel:
    return SpatialWorldModel()


@pytest.fixture
def scene_graph(world_model: SpatialWorldModel) -> XRSceneGraph:
    return XRSceneGraph(world_model)


@pytest.fixture
def services() -> XRServices:
    return XRServices()
