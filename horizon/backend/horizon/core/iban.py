"""Validation de FORMAT d'IBAN (ISO 13616, modulo 97).

Attention : un IBAN au format valide ne prouve ni l'existence du compte ni
l'identité de son titulaire. HORIZON l'indique systématiquement.
"""
from __future__ import annotations

import re

LENGTHS = {"FR": 27, "DE": 22, "IT": 27, "ES": 24, "BE": 16, "NL": 18, "GB": 22, "CH": 21, "LU": 20, "PT": 25,
           "AT": 20, "IE": 22, "PL": 28, "SE": 24, "MC": 27}


def normalize(iban: str) -> str:
    return re.sub(r"\s+", "", iban or "").upper()


def check_format(iban: str) -> dict:
    v = normalize(iban)
    issues = []
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{10,30}", v):
        issues.append("Structure invalide")
    else:
        cc = v[:2]
        if cc in LENGTHS and len(v) != LENGTHS[cc]:
            issues.append(f"Longueur {len(v)} incorrecte pour {cc} (attendu {LENGTHS[cc]})")
        rearranged = v[4:] + v[:4]
        digits = "".join(str(int(ch, 36)) for ch in rearranged)
        if int(digits) % 97 != 1:
            issues.append("Clé de contrôle (modulo 97) incorrecte")
    return {
        "iban": v,
        "format_valid": not issues,
        "issues": issues,
        "scope": "Contrôle de format uniquement : ne prouve ni l'existence du compte ni l'identité du titulaire.",
        "account_existence_verified": False,
        "holder_name_verified": False,
    }


def make_iban(country: str, bban: str) -> str:
    """Construit un IBAN synthétique au format valide (pour les données fictives)."""
    rearranged = bban + country + "00"
    digits = "".join(str(int(ch, 36)) for ch in rearranged)
    check = 98 - int(digits) % 97
    return f"{country}{check:02d}{bban}"
