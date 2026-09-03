"""Security & privacy: per-app permission enforcement."""

import pytest

from xr_os.security.permissions import PermissionDeniedError, PermissionManager, PermissionScope, PermissionStatus


def test_default_status_is_not_determined():
    manager = PermissionManager()
    assert manager.status("app1", PermissionScope.CAMERA) == PermissionStatus.NOT_DETERMINED
    assert not manager.is_granted("app1", PermissionScope.CAMERA)


def test_request_does_not_auto_grant():
    manager = PermissionManager()
    status = manager.request("app1", PermissionScope.MICROPHONE)
    assert status == PermissionStatus.NOT_DETERMINED
    assert not manager.is_granted("app1", PermissionScope.MICROPHONE)


def test_request_publishes_event_only_once_undetermined():
    manager = PermissionManager()
    requests = []
    manager.events.subscribe("security.permission.requested", lambda p: requests.append(p))
    manager.request("app1", PermissionScope.SPATIAL_MAP)
    manager.grant("app1", PermissionScope.SPATIAL_MAP)
    manager.request("app1", PermissionScope.SPATIAL_MAP)  # already determined, no new request event
    assert len(requests) == 1


def test_grant_and_enforce():
    manager = PermissionManager()
    manager.grant("app1", PermissionScope.HAND_TRACKING)
    manager.enforce("app1", PermissionScope.HAND_TRACKING)  # should not raise


def test_enforce_raises_when_denied():
    manager = PermissionManager()
    manager.deny("app1", PermissionScope.EYE_TRACKING)
    with pytest.raises(PermissionDeniedError):
        manager.enforce("app1", PermissionScope.EYE_TRACKING)


def test_enforce_raises_when_not_determined():
    manager = PermissionManager()
    with pytest.raises(PermissionDeniedError):
        manager.enforce("app1", PermissionScope.CAMERA)


def test_revoke_resets_to_not_determined():
    manager = PermissionManager()
    manager.grant("app1", PermissionScope.CAMERA)
    manager.revoke("app1", PermissionScope.CAMERA)
    assert manager.status("app1", PermissionScope.CAMERA) == PermissionStatus.NOT_DETERMINED


def test_grants_for_app_only_includes_that_app():
    manager = PermissionManager()
    manager.grant("app1", PermissionScope.CAMERA)
    manager.grant("app2", PermissionScope.MICROPHONE)
    grants = manager.grants_for("app1")
    assert grants == {PermissionScope.CAMERA: PermissionStatus.GRANTED}


def test_apps_are_isolated_from_each_other():
    manager = PermissionManager()
    manager.grant("app1", PermissionScope.SPATIAL_MAP)
    assert not manager.is_granted("app2", PermissionScope.SPATIAL_MAP)
