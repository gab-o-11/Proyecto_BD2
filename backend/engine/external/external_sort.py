import heapq
import os
import pickle
import tempfile


def _read_pickles(path):
    with open(path, "rb") as f:
        while True:
            try:
                yield pickle.load(f)
            except EOFError:
                return


def _write_run(chunk, key_fn, reverse, tmp_dir):
    chunk.sort(key=key_fn, reverse=reverse)
    fd, path = tempfile.mkstemp(suffix=".run", dir=tmp_dir)
    os.close(fd)
    with open(path, "wb") as f:
        for row in chunk:
            pickle.dump(row, f)
    return path


def external_sort(rows, key_fn, mem_budget=1000, reverse=False, tmp_dir=None):
    runs = []
    chunk = []
    iterators = []
    try:
        for row in rows:
            chunk.append(row)
            if len(chunk) >= mem_budget:
                runs.append(_write_run(chunk, key_fn, reverse, tmp_dir))
                chunk = []
        if chunk:
            runs.append(_write_run(chunk, key_fn, reverse, tmp_dir))
        for path in runs:
            iterators.append(_read_pickles(path))
        yield from heapq.merge(*iterators, key=key_fn, reverse=reverse)
    finally:
        for iterator in iterators:
            iterator.close()
        for path in runs:
            os.remove(path)
