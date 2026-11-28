"""Expurgation des journaux techniques et des détails d'audit.

Les IBAN sont masqués (seuls les 4 derniers caractères restent), ainsi que les
jetons, mots de passe et codes à usage unique.
"""
from __future__ import annotations

import logging
import re
from typing import Any

IBAN_RE = re.compile(r"\b([A-Z]{2}\d{2})((?:\s?[A-Z0-9]){8,30})\b")
SECRET_KEYS = {"password", "token", "code", "totp", "secret", "authorization", "cookie", "otp", "totp_secret"}


def mask_iban(value: str) -> str:
    compact = value.replace(" ", "")
    if len(compact) < 8:
        return "****"
    return f"{compact[:4]}{'*' * (len(compact) - 8)}{compact[-4:]}"


def redact_text(text: str) -> str:
    return IBAN_RE.sub(lambda m: mask_iban(m.group(0)), text)


def redact(obj: Any) -> Any:
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k.lower() in SECRET_KEYS or k.lower().endswith("_token"):
                out[k] = "[expurgé]"
            elif k.lower() in {"iban", "creditor_iban", "debtor_iban"} and isinstance(v, str):
                out[k] = mask_iban(v)
            else:
                out[k] = redact(v)
        return out
    if isinstance(obj, list):
        return [redact(v) for v in obj]
    if isinstance(obj, str):
        return redact_text(obj)
    return obj


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact_text(record.msg)
        if record.args:
            record.args = tuple(redact_text(a) if isinstance(a, str) else a for a in record.args)
        return True


def configure_logging() -> None:
    root = logging.getLogger()
    if not any(isinstance(f, RedactingFilter) for f in root.filters):
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
        for h in root.handlers:
            h.addFilter(RedactingFilter())
        root.addFilter(RedactingFilter())
