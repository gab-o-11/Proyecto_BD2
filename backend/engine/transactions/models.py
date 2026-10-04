from dataclasses import dataclass
from enum import Enum


class TransactionState(Enum):
    ACTIVE = "active"
    ENDED = "ended"


class LockMode(Enum):
    """Modos de bloqueo del protocolo del curso."""

    PS = "PS"  # Compartido (shared)
    PU = "PU"  # Actualización (update)
    PX = "PX"  # Exclusivo (exclusive)


class TransactionError(Exception):
    pass


@dataclass
class Transaction:
    transaction_id: int
    thread_id: int
    state: TransactionState = TransactionState.ACTIVE
