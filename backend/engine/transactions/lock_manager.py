import threading
import time

from .models import LockMode


class LockError(Exception):
    pass


class LockTimeoutError(LockError):
    pass


class LockManager:
    def __init__(self):
        self._locks = {}
        self.owners = {}
        self.history = []
        self.condition = threading.Condition()

    @staticmethod
    def _normalize_mode(mode):
        if mode is None:
            return LockMode.PX
        if isinstance(mode, LockMode):
            return mode
        try:
            return LockMode(str(mode).upper())
        except ValueError as error:
            raise LockError(f"Modo de bloqueo inválido: {mode}") from error

    @staticmethod
    def _compatible(existing_mode, requested_mode):
        compatibility = {
            LockMode.PS: {LockMode.PS, LockMode.PU},
            LockMode.PU: {LockMode.PS},
            LockMode.PX: set(),
        }
        return requested_mode in compatibility[existing_mode]

    def _sync_owners(self, resource):
        lock = self._locks.get(resource)
        if lock is None:
            self.owners.pop(resource, None)
        elif len(lock["owners"]) == 1:
            self.owners[resource] = next(iter(lock["owners"]))
        else:
            self.owners[resource] = set(lock["owners"])

    @staticmethod
    def _effective_mode(lock):
        modes = set(lock["owners"].values())
        if LockMode.PX in modes:
            return LockMode.PX
        if LockMode.PU in modes:
            return LockMode.PU
        return LockMode.PS

    def _can_grant(self, transaction_id, resource, mode):
        lock = self._locks.get(resource)
        if lock is None:
            return True

        other_modes = [
            owner_mode
            for owner, owner_mode in lock["owners"].items()
            if owner != transaction_id
        ]
        return all(
            self._compatible(existing_mode, mode)
            for existing_mode in other_modes
        )

    def acquire(self, transaction_id, resource, mode=LockMode.PX, timeout=5):
        mode = self._normalize_mode(mode)
        end_time = time.monotonic() + timeout

        with self.condition:
            while not self._can_grant(transaction_id, resource, mode):
                self.history.append(("WAIT", transaction_id, resource))
                remaining = end_time - time.monotonic()
                if remaining <= 0:
                    raise LockTimeoutError("Tiempo de espera agotado")
                self.condition.wait(remaining)

            lock = self._locks.get(resource)
            if lock is None:
                self._locks[resource] = {"owners": {transaction_id: mode}}
                event = "ACQUIRED"
            elif transaction_id in lock["owners"]:
                current_mode = lock["owners"][transaction_id]
                stronger = {
                    LockMode.PS: 0,
                    LockMode.PU: 1,
                    LockMode.PX: 2,
                }
                if stronger[mode] > stronger[current_mode]:
                    lock["owners"][transaction_id] = mode
                    event = "UPGRADED"
                else:
                    event = "ACQUIRED"
            else:
                lock["owners"][transaction_id] = mode
                event = "ACQUIRED"

            self._sync_owners(resource)
            self.history.append((event, transaction_id, resource))
            return True

    def release(self, transaction_id, resource):
        with self.condition:
            lock = self._locks.get(resource)
            if lock is None or transaction_id not in lock["owners"]:
                raise LockError("La transacción no posee el recurso")

            del lock["owners"][transaction_id]
            if not lock["owners"]:
                del self._locks[resource]
            self._sync_owners(resource)
            self.history.append(("RELEASED", transaction_id, resource))
            self.condition.notify_all()

    def release_all(self, transaction_id):
        with self.condition:
            resources = [
                resource
                for resource, lock in self._locks.items()
                if transaction_id in lock["owners"]
            ]

            for resource in resources:
                lock = self._locks[resource]
                del lock["owners"][transaction_id]
                if not lock["owners"]:
                    del self._locks[resource]
                self._sync_owners(resource)
                self.history.append(("RELEASED", transaction_id, resource))

            if resources:
                self.condition.notify_all()

    def owner(self, resource):
        with self.condition:
            lock = self._locks.get(resource)
            if lock is None:
                return None
            if len(lock["owners"]) == 1:
                return next(iter(lock["owners"]))
            return set(lock["owners"])

    def mode(self, resource):
        with self.condition:
            lock = self._locks.get(resource)
            return None if lock is None else self._effective_mode(lock)

    def owners_of(self, resource):
        with self.condition:
            lock = self._locks.get(resource)
            return set() if lock is None else set(lock["owners"])

    def has_event(self, event_name, transaction_id):
        with self.condition:
            for event, event_transaction_id, _ in self.history:
                if event == event_name and event_transaction_id == transaction_id:
                    return True
            return False
