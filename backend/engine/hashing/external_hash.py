import os
import pickle
import tempfile
from itertools import chain

MAX_HASH_BITS = 48
MASK63 = 0x7FFFFFFFFFFFFFFF


def _partition_index(key, num_partitions, hash_bits):
    return ((hash(key) & MASK63) >> hash_bits) % num_partitions


def _read_pickles(path):
    with open(path, "rb") as f:
        while True:
            try:
                yield pickle.load(f)
            except EOFError:
                return


def _spill(rows, key_fn, num_partitions, hash_bits, tmp_dir):
    paths = []
    files = []
    for _ in range(num_partitions):
        fd, path = tempfile.mkstemp(suffix=".part", dir=tmp_dir)
        os.close(fd)
        paths.append(path)
        files.append(open(path, "wb"))
    for row in rows:
        pickle.dump(row, files[_partition_index(key_fn(row), num_partitions, hash_bits)])
    for f in files:
        f.close()
    return paths


def _acc_init(op):
    if op in ("count", "sum"):
        return 0
    if op == "avg":
        return [0, 0]
    return None


def _acc_step(op, acc, value):
    if op == "count":
        return acc + 1
    if op == "sum":
        return acc + value
    if op == "min":
        if acc is None or value < acc:
            return value
        return acc
    if op == "max":
        if acc is None or value > acc:
            return value
        return acc
    acc[0] += value
    acc[1] += 1
    return acc


def _acc_final(op, acc):
    if op == "avg":
        if acc[1] == 0:
            return None
        return acc[0] / acc[1]
    return acc


def _aggregate(rows, key_fn, specs):
    table = {}
    for row in rows:
        key = key_fn(row)
        accs = table.get(key)
        if accs is None:
            accs = []
            for op, extractor in specs:
                accs.append(_acc_init(op))
            table[key] = accs
        for i in range(len(specs)):
            op = specs[i][0]
            extractor = specs[i][1]
            if extractor is None:
                value = None
            else:
                value = extractor(row)
            accs[i] = _acc_step(op, accs[i], value)
    return table


def external_group_by(rows, key_fn, specs, mem_budget=1000, num_partitions=16, tmp_dir=None, hash_bits=0):
    rows = iter(rows)
    buffered = []
    keys = set()
    spilled = False
    for row in rows:
        buffered.append(row)
        keys.add(key_fn(row))
        if len(keys) > mem_budget and hash_bits < MAX_HASH_BITS:
            spilled = True
            break
    if not spilled:
        table = _aggregate(buffered, key_fn, specs)
        for key in table:
            accs = table[key]
            row_out = []
            for i in range(len(specs)):
                op = specs[i][0]
                row_out.append(_acc_final(op, accs[i]))
            yield key, row_out
        return
    parts = _spill(chain(buffered, rows), key_fn, num_partitions, hash_bits, tmp_dir)
    for path in parts:
        yield from external_group_by(
            _read_pickles(path), key_fn, specs, mem_budget, num_partitions, tmp_dir, hash_bits + 4
        )
        os.remove(path)


def _distinct_within(path, key_fn, limit):
    keys = set()
    for row in _read_pickles(path):
        keys.add(key_fn(row))
        if len(keys) > limit:
            return False
    return True


def _join_partition(left_path, right_path, left_key, right_key):
    build = {}
    for row in _read_pickles(left_path):
        key = left_key(row)
        if key not in build:
            build[key] = []
        build[key].append(row)
    for right_row in _read_pickles(right_path):
        key = right_key(right_row)
        if key in build:
            for left_row in build[key]:
                yield left_row, right_row


def grace_hash_join(left, right, left_key, right_key, mem_budget=1000, num_partitions=16, tmp_dir=None, hash_bits=0):
    left_parts = _spill(left, left_key, num_partitions, hash_bits, tmp_dir)
    right_parts = _spill(right, right_key, num_partitions, hash_bits, tmp_dir)
    for left_path, right_path in zip(left_parts, right_parts):
        if hash_bits >= MAX_HASH_BITS or _distinct_within(left_path, left_key, mem_budget):
            yield from _join_partition(left_path, right_path, left_key, right_key)
        else:
            yield from grace_hash_join(
                _read_pickles(left_path), _read_pickles(right_path),
                left_key, right_key, mem_budget, num_partitions, tmp_dir, hash_bits + 4,
            )
        os.remove(left_path)
        os.remove(right_path)
