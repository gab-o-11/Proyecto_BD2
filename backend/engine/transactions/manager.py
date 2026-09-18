import threading

from .lock_manager import LockManager
from .models import Transaction, TransactionError, TransactionState


class TransactionManager:
    def __init__(self, lock_manager=None):
        self.next_transaction_id = 1
        self.transactions = {}
        self.mutex = threading.Lock()
        self.lock_manager = lock_manager or LockManager()

    def begin(self):
        thread_id = threading.get_ident()

        with self.mutex:
            current = self.transactions.get(thread_id)
            if current is not None and current.state == TransactionState.ACTIVE:
                raise TransactionError("Ya existe una transacción activa")

            transaction = Transaction(self.next_transaction_id, thread_id)
            self.next_transaction_id += 1
            self.transactions[thread_id] = transaction
            return transaction

    def current(self):
        thread_id = threading.get_ident()

        with self.mutex:
            transaction = self.transactions.get(thread_id)
            if transaction is None or transaction.state != TransactionState.ACTIVE:
                return None
            return transaction

    def end(self):
        thread_id = threading.get_ident()

        with self.mutex:
            transaction = self.transactions.get(thread_id)
            if transaction is None or transaction.state != TransactionState.ACTIVE:
                raise TransactionError("No existe una transacción activa")

            self.lock_manager.release_all(transaction.transaction_id)
            transaction.state = TransactionState.ENDED
            del self.transactions[thread_id]
            return transaction

    def acquire(self, resource, timeout=5):
        transaction = self.current()
        if transaction is None:
            raise TransactionError("No existe una transacción activa")

        return self.lock_manager.acquire(
            transaction.transaction_id,
            resource,
            timeout,
        )
