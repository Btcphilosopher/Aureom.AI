"""Adaptateur de stockage objet S3 (SDK minio) testé contre un émulateur S3 (moto).

Vérifie : création du seau, aller-retour, chiffrement côté application (l'objet
stocké n'est pas lisible en clair dans le seau)."""
import socket

import pytest

moto_server = pytest.importorskip("moto.server")


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture
def s3_endpoint(monkeypatch):
    port = _free_port()
    server = moto_server.ThreadedMotoServer(ip_address="127.0.0.1", port=port)
    server.start()
    for k, v in {"HORIZON_STORAGE_BACKEND": "s3", "HORIZON_S3_ENDPOINT": f"127.0.0.1:{port}",
                 "HORIZON_S3_ACCESS_KEY": "test", "HORIZON_S3_SECRET_KEY": "testsecret",
                 "HORIZON_S3_BUCKET": "horizon-test", "HORIZON_S3_SECURE": "false"}.items():
        monkeypatch.setenv(k, v)
    for k in ("HTTPS_PROXY", "HTTP_PROXY", "https_proxy", "http_proxy"):
        monkeypatch.delenv(k, raising=False)
    from horizon.core.config import reset_settings

    reset_settings()
    yield f"127.0.0.1:{port}"
    server.stop()
    reset_settings()


def test_s3_storage_roundtrip_and_encryption(s3_endpoint):
    from minio import Minio

    from horizon.modules.documents.storage import S3Storage

    st = S3Storage()
    payload = b"%PDF-1.4 contrat fictif"
    st.put("org/doc-1", payload)
    assert st.get("org/doc-1") == payload
    raw = Minio(s3_endpoint, access_key="test", secret_key="testsecret", secure=False).get_object("horizon-test", "org/doc-1")
    try:
        stored = raw.read()
    finally:
        raw.close()
    assert stored != payload and b"contrat" not in stored
