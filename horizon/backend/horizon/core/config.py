"""Configuration chargée depuis l'environnement.

Aucun secret n'est codé en dur pour la production : les valeurs par défaut ne
sont acceptées que lorsque HORIZON_ENV vaut ``demo`` ou ``test``.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env(name: str, default: str | None = None) -> str | None:
    return os.environ.get(name, default)


@dataclass(frozen=True)
class Settings:
    env: str = field(default_factory=lambda: _env("HORIZON_ENV", "demo"))
    database_url: str = field(
        default_factory=lambda: _env(
            "HORIZON_DATABASE_URL",
            "postgresql+psycopg://horizon:horizon@localhost:5433/horizon",
        )
    )
    # Clé maîtresse servant à dériver les clés de chiffrement (TOTP, liens).
    secret_key: str = field(
        default_factory=lambda: _env("HORIZON_SECRET_KEY", "demo-only-secret-key-change-me-0123456789")
    )
    simulator_webhook_secret: str = field(
        default_factory=lambda: _env("HORIZON_SIMULATOR_WEBHOOK_SECRET", "demo-simulator-webhook-secret")
    )
    storage_backend: str = field(default_factory=lambda: _env("HORIZON_STORAGE_BACKEND", "filesystem"))
    storage_path: str = field(default_factory=lambda: _env("HORIZON_STORAGE_PATH", "./var/objects"))
    s3_endpoint: str = field(default_factory=lambda: _env("HORIZON_S3_ENDPOINT", "minio:9000"))
    s3_access_key: str = field(default_factory=lambda: _env("HORIZON_S3_ACCESS_KEY", ""))
    s3_secret_key: str = field(default_factory=lambda: _env("HORIZON_S3_SECRET_KEY", ""))
    s3_bucket: str = field(default_factory=lambda: _env("HORIZON_S3_BUCKET", "horizon-documents"))
    s3_secure: bool = field(default_factory=lambda: _env("HORIZON_S3_SECURE", "false") == "true")
    cookie_secure: bool = field(default_factory=lambda: _env("HORIZON_COOKIE_SECURE", "false") == "true")
    session_ttl_minutes: int = field(default_factory=lambda: int(_env("HORIZON_SESSION_TTL_MINUTES", "480")))
    step_up_ttl_seconds: int = field(default_factory=lambda: int(_env("HORIZON_STEP_UP_TTL_SECONDS", "300")))
    document_link_ttl_seconds: int = field(default_factory=lambda: int(_env("HORIZON_DOC_LINK_TTL", "300")))
    external_data_stale_hours: int = field(default_factory=lambda: int(_env("HORIZON_STALE_HOURS", "24")))
    base_currency: str = "EUR"
    api_version: str = "2026-11-01"
    # Expose les contrôles du simulateur (injection de pannes, redélivrance).
    demo_controls: bool = field(default_factory=lambda: _env("HORIZON_DEMO_CONTROLS", "true") == "true")
    # Montre le code TOTP courant des utilisateurs fictifs sur l'écran de connexion.
    demo_show_totp: bool = field(default_factory=lambda: _env("HORIZON_DEMO_SHOW_TOTP", "true") == "true")

    def validate(self) -> None:
        if self.env not in {"demo", "test"}:
            if "demo-only" in self.secret_key or len(self.secret_key) < 32:
                raise RuntimeError("HORIZON_SECRET_KEY doit être défini (>= 32 caractères) hors démonstration")
            if self.demo_controls or self.demo_show_totp:
                raise RuntimeError("Les contrôles de démonstration doivent être désactivés hors démonstration")


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
        _settings.validate()
    return _settings


def reset_settings() -> None:
    global _settings
    _settings = None
