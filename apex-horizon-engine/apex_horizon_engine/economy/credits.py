"""
Player currency ledger. Every credit gain or loss anywhere in the engine
(event payouts, market purchases, sponsorship income, repair bills)
should route through this class so ``ui.hud`` / ``ui.garage_ui`` and save
files always agree on the balance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple


@dataclass
class LedgerEntry:
    delta: int
    reason: str
    balance_after: int


@dataclass
class CreditLedger:
    balance: int = 0
    history: List[LedgerEntry] = field(default_factory=list)
    _max_history: int = 500

    def earn(self, amount: int, reason: str = "") -> None:
        if amount < 0:
            raise ValueError("earn() requires a non-negative amount; use spend() to deduct")
        self.balance += amount
        self._record(amount, reason)

    def spend(self, amount: int, reason: str = "") -> bool:
        if amount < 0:
            raise ValueError("spend() requires a non-negative amount")
        if amount > self.balance:
            return False
        self.balance -= amount
        self._record(-amount, reason)
        return True

    def _record(self, delta: int, reason: str) -> None:
        self.history.append(LedgerEntry(delta, reason, self.balance))
        if len(self.history) > self._max_history:
            self.history = self.history[-self._max_history:]

    def recent(self, n: int = 10) -> List[LedgerEntry]:
        return self.history[-n:]

    def net_over(self, entries: int) -> int:
        return sum(e.delta for e in self.history[-entries:])
