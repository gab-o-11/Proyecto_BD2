from dataclasses import dataclass
from enum import Enum


class TransactionState(Enum):
    ACTIVE = "active"
    ENDED = "ended"


class TransactionError(Exception):
    pass


@dataclass
class Transaction:
    transaction_id: int
    thread_id: int
    state: TransactionState = TransactionState.ACTIVE
