import threading
import time

from .manager import TransactionManager
from .resources import Resource


class SharedPage:
    def __init__(self, value):
        self.value = value

    def read(self):
        return self.value

    def write(self, value):
        self.value = value


def run_unsafe_demo():
    page = SharedPage(100)
    manager = TransactionManager()
    reads_finished = threading.Barrier(2)
    first_write_finished = threading.Event()
    transaction_ids = []
    errors = []

    def add_value():
        try:
            transaction = manager.begin()
            transaction_ids.append(transaction.transaction_id)
            current_value = page.read()
            reads_finished.wait()
            page.write(current_value + 50)
            first_write_finished.set()
            manager.end()
        except Exception as error:
            errors.append(error)

    def subtract_value():
        try:
            transaction = manager.begin()
            transaction_ids.append(transaction.transaction_id)
            current_value = page.read()
            reads_finished.wait()
            first_write_finished.wait()
            page.write(current_value - 30)
            manager.end()
        except Exception as error:
            errors.append(error)

    first = threading.Thread(target=add_value)
    second = threading.Thread(target=subtract_value)
    first.start()
    second.start()
    first.join(timeout=10)
    second.join(timeout=10)

    if errors:
        raise errors[0]

    return {
        "initial_value": 100,
        "expected_value": 120,
        "final_value": page.read(),
        "transaction_ids": transaction_ids,
        "threads_finished": not first.is_alive() and not second.is_alive(),
    }


def run_safe_demo():
    page = SharedPage(100)
    manager = TransactionManager()
    resource = Resource("page", "demo", 1)
    transactions_started = threading.Barrier(2)
    first_has_lock = threading.Event()
    second_transaction_id = []
    transaction_ids = []
    errors = []

    def add_value():
        try:
            transaction = manager.begin()
            transaction_ids.append(transaction.transaction_id)
            transactions_started.wait()
            manager.acquire(resource)
            first_has_lock.set()

            limit = time.monotonic() + 2
            while time.monotonic() < limit:
                if second_transaction_id and manager.lock_manager.has_event(
                    "WAIT", second_transaction_id[0]
                ):
                    break
                time.sleep(0.01)

            current_value = page.read()
            page.write(current_value + 50)
            manager.end()
        except Exception as error:
            errors.append(error)

    def subtract_value():
        try:
            transaction = manager.begin()
            transaction_ids.append(transaction.transaction_id)
            second_transaction_id.append(transaction.transaction_id)
            transactions_started.wait()
            first_has_lock.wait()
            manager.acquire(resource)
            current_value = page.read()
            page.write(current_value - 30)
            manager.end()
        except Exception as error:
            errors.append(error)

    first = threading.Thread(target=add_value)
    second = threading.Thread(target=subtract_value)
    first.start()
    second.start()
    first.join(timeout=10)
    second.join(timeout=10)

    if errors:
        raise errors[0]

    wait_detected = False
    if second_transaction_id:
        wait_detected = manager.lock_manager.has_event(
            "WAIT", second_transaction_id[0]
        )

    return {
        "initial_value": 100,
        "expected_value": 120,
        "final_value": page.read(),
        "transaction_ids": transaction_ids,
        "wait_detected": wait_detected,
        "threads_finished": not first.is_alive() and not second.is_alive(),
        "active_locks": len(manager.lock_manager.owners),
    }


def main():
    unsafe_result = run_unsafe_demo()
    safe_result = run_safe_demo()

    print("Escenario sin bloqueos")
    print("Resultado esperado:", unsafe_result["expected_value"])
    print("Resultado obtenido:", unsafe_result["final_value"])
    print("Se produjo una actualización perdida")
    print()
    print("Escenario con bloqueos")
    print("Resultado esperado:", safe_result["expected_value"])
    print("Resultado obtenido:", safe_result["final_value"])
    print("Espera detectada:", safe_result["wait_detected"])


if __name__ == "__main__":
    main()
