"""Travailleur de tâches en arrière-plan.

Boucle : tâches périodiques (exécutions planifiées, reprise des soumissions
interrompues, avancée du simulateur) puis traitement de la file. Arrêt propre
sur SIGTERM ; une tâche interrompue est reprise grâce à son bail expiré.
"""
from __future__ import annotations

import logging
import signal
import time
import uuid

from horizon.core import clock
from horizon.core.db import session_scope
from horizon.core.redaction import configure_logging
from horizon.modules.jobs import queue
import horizon.modules.payments.execution  # noqa: F401 - enregistre les gestionnaires

log = logging.getLogger("horizon.worker")
_running = True


def _stop(*_):
    global _running
    _running = False


def periodic() -> None:
    bucket = clock.now().strftime("%Y%m%d%H%M")
    with session_scope() as s:
        queue.enqueue(s, "run_scheduled", {}, f"run_scheduled:{bucket}")
        queue.enqueue(s, "recover_stale_submissions", {}, f"recover_stale:{bucket}")
        queue.enqueue(s, "sim_process", {}, f"sim_process:periodic:{bucket}")


def main() -> None:
    configure_logging()
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    log.info("Travailleur HORIZON démarré (%s)", uuid.uuid4().hex[:8])
    last = 0.0
    while _running:
        if time.time() - last > 30:
            periodic()
            last = time.time()
        if not queue.run_one():
            time.sleep(1)
    log.info("Travailleur arrêté proprement")


if __name__ == "__main__":
    main()
