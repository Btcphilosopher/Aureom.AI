"""Adaptateurs d'intégration (contrats).

Ces interfaces isolent HORIZON des systèmes externes. La seule implémentation
fournie est un simulateur déterministe : aucune connexion bancaire réelle,
aucun partenariat n'est revendiqué.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol


class GatewayTimeout(Exception):
    """Pas de réponse exploitable : le résultat est INCONNU (l'ordre a pu être enregistré)."""


class GatewayRejected(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass
class SubmitAck:
    bank_reference: str
    received_at: datetime
    http_status: int = 202  # réception technique uniquement


@dataclass
class OrderStatus:
    submission_key: str
    bank_reference: str
    status: str  # RECEIVED / ACCEPTED / SETTLED / REJECTED / RETURNED
    rejection_code: str | None = None


@dataclass
class StatementLine:
    line_ref: str
    booking_date: date
    amount_minor: int  # signé
    currency: str
    description: str
    end_to_end_id: str | None
    bank_reference: str | None
    kind: str


class PaymentGateway(Protocol):
    name: str

    def submit(self, order: dict) -> SubmitAck: ...
    def find(self, submission_key: str) -> OrderStatus | None: ...


class StatementProvider(Protocol):
    name: str

    def statement(self, iban: str, since: date) -> list[StatementLine]: ...


class NotificationSender(Protocol):
    def send(self, recipient: str, subject: str, body: str) -> None: ...


class LogNotificationSender:
    """Notifications de démonstration : journalisées, jamais envoyées."""

    sent: list[dict] = []

    def send(self, recipient: str, subject: str, body: str) -> None:
        self.sent.append({"to": recipient, "subject": subject, "body": body})
