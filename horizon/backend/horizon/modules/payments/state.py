"""Cycle de vie des lots et des paiements — transitions documentées.

Distinction essentielle :
* SUBMITTED  = transmis ; ``technical_ack_at`` = réception technique (HTTP 2xx)
* ACCEPTED   = accepté par le système destinataire (événement métier)
* EXECUTED   = exécuté selon confirmation de règlement (événement SETTLED)
Une réponse HTTP positive ne fait JAMAIS passer un paiement à EXECUTED.
UNKNOWN = résultat inconnu (délai dépassé, coupure) : on recherche l'opération
chez le destinataire avant toute nouvelle soumission.
"""
from __future__ import annotations

from horizon.core.errors import Conflict

PAYMENT_LABELS = {
    "DRAFT": "Brouillon",
    "TO_REVIEW": "À vérifier",
    "PENDING_APPROVAL": "En attente d'approbation",
    "APPROVED": "Approuvé",
    "SCHEDULED": "Planifié",
    "SUBMITTED": "Soumis",
    "ACCEPTED": "Accepté par le système destinataire",
    "EXECUTED": "Exécuté selon confirmation",
    "REJECTED": "Rejeté",
    "CANCELLED": "Annulé",
    "UNKNOWN": "Résultat inconnu",
}
BATCH_LABELS = {
    **{k: v for k, v in PAYMENT_LABELS.items() if k in {"DRAFT", "TO_REVIEW", "PENDING_APPROVAL", "APPROVED", "SCHEDULED", "CANCELLED"}},
    "PROCESSING": "En cours de traitement",
    "COMPLETED": "Traitement terminé",
    "REJECTED": "Refusé à l'approbation",
}

PAYMENT_TRANSITIONS: dict[str, set[str]] = {
    "DRAFT": {"TO_REVIEW", "PENDING_APPROVAL", "CANCELLED"},
    "TO_REVIEW": {"DRAFT", "PENDING_APPROVAL", "CANCELLED"},
    "PENDING_APPROVAL": {"APPROVED", "TO_REVIEW", "DRAFT", "CANCELLED"},
    "APPROVED": {"SCHEDULED", "SUBMITTED", "TO_REVIEW", "PENDING_APPROVAL", "DRAFT", "CANCELLED"},
    "SCHEDULED": {"SUBMITTED", "TO_REVIEW", "PENDING_APPROVAL", "DRAFT", "CANCELLED"},
    "SUBMITTED": {"ACCEPTED", "EXECUTED", "REJECTED", "UNKNOWN"},
    "UNKNOWN": {"SUBMITTED", "ACCEPTED", "EXECUTED", "REJECTED"},
    "ACCEPTED": {"EXECUTED", "REJECTED"},
    "EXECUTED": set(),
    "REJECTED": set(),
    "CANCELLED": set(),
}
BATCH_TRANSITIONS: dict[str, set[str]] = {
    "DRAFT": {"TO_REVIEW", "PENDING_APPROVAL", "CANCELLED"},
    "TO_REVIEW": {"DRAFT", "PENDING_APPROVAL", "CANCELLED"},
    "PENDING_APPROVAL": {"APPROVED", "TO_REVIEW", "DRAFT", "REJECTED", "CANCELLED"},
    "APPROVED": {"SCHEDULED", "PROCESSING", "TO_REVIEW", "PENDING_APPROVAL", "DRAFT", "CANCELLED"},
    "SCHEDULED": {"PROCESSING", "TO_REVIEW", "PENDING_APPROVAL", "DRAFT", "CANCELLED"},
    "PROCESSING": {"COMPLETED"},
    "COMPLETED": set(),
    "REJECTED": set(),
    "CANCELLED": set(),
}
EDITABLE_BATCH = {"DRAFT", "TO_REVIEW", "PENDING_APPROVAL", "APPROVED", "SCHEDULED"}
CANCELLABLE = {"DRAFT", "TO_REVIEW", "PENDING_APPROVAL", "APPROVED", "SCHEDULED"}
IN_FLIGHT = {"SUBMITTED", "ACCEPTED", "UNKNOWN"}
FINAL = {"EXECUTED", "REJECTED", "CANCELLED"}


def check_payment(frm: str, to: str) -> None:
    if to not in PAYMENT_TRANSITIONS[frm]:
        raise Conflict("INVALID_TRANSITION", f"Transition de paiement interdite : {frm} → {to}",
                       {"from": frm, "to": to})


def check_batch(frm: str, to: str) -> None:
    if to not in BATCH_TRANSITIONS[frm]:
        raise Conflict("INVALID_TRANSITION", f"Transition de lot interdite : {frm} → {to}", {"from": frm, "to": to})


def transitions_doc() -> dict:
    return {
        "payment": {k: {"label": PAYMENT_LABELS[k], "next": sorted(v)} for k, v in PAYMENT_TRANSITIONS.items()},
        "batch": {k: {"label": BATCH_LABELS[k], "next": sorted(v)} for k, v in BATCH_TRANSITIONS.items()},
    }
