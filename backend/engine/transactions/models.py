from dataclasses import dataclass
from enum import Enum


class TransactionState(Enum):
    ACTIVE = "active"
    ENDED = "ended"


class LockMode(Enum):
    PS = "PS"  # Compartido
    PU = "PU"  # Actualización
    PX = "PX"  # Exclusivo


class TransactionError(Exception):
    pass


@dataclass
class Transaction:
    transaction_id: int
    thread_id: int
    state: TransactionState = TransactionState.ACTIVE
