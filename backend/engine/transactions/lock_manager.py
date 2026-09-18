import threading
import time


class LockError(Exception):
    pass


class LockTimeoutError(LockError):
    pass


class LockManager:
    def __init__(self):
        self.owners = {}
        self.history = []
        self.condition = threading.Condition()

    def acquire(self, transaction_id, resource, timeout=5):
        end_time = time.monotonic() + timeout

        with self.condition:
            owner = self.owners.get(resource)
            if owner == transaction_id:
                return True

            if owner is not None:
                self.history.append(("WAIT", transaction_id, resource))

            while resource in self.owners:
                remaining = end_time - time.monotonic()
                if remaining <= 0:
                    raise LockTimeoutError("Tiempo de espera agotado")
                self.condition.wait(remaining)

            self.owners[resource] = transaction_id
            self.history.append(("ACQUIRED", transaction_id, resource))
            return True

    def release(self, transaction_id, resource):
        with self.condition:
            owner = self.owners.get(resource)
            if owner != transaction_id:
                raise LockError("La transacción no posee el recurso")

            del self.owners[resource]
            self.history.append(("RELEASED", transaction_id, resource))
            self.condition.notify_all()

    def release_all(self, transaction_id):
        with self.condition:
            resources = []
            for resource, owner in self.owners.items():
                if owner == transaction_id:
                    resources.append(resource)

            for resource in resources:
                del self.owners[resource]
                self.history.append(("RELEASED", transaction_id, resource))

            if resources:
                self.condition.notify_all()

    def owner(self, resource):
        with self.condition:
            return self.owners.get(resource)

    def has_event(self, event_name, transaction_id):
        with self.condition:
            for event, event_transaction_id, _ in self.history:
                if event == event_name and event_transaction_id == transaction_id:
                    return True
            return False
