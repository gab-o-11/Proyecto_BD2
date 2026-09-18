import os
import struct

from .boundary import stable_hash
from .page import BucketConfig, Bucket, FileManager

DIR_HEADER_FORMAT = "<iii16s"
DIR_HEADER_SIZE = struct.calcsize(DIR_HEADER_FORMAT)
DIR_ENTRY_FORMAT = "<i"
DIR_ENTRY_SIZE = struct.calcsize(DIR_ENTRY_FORMAT)
MAX_GLOBAL_DEPTH = 32


class ExtendibleHashIndex:
    def __init__(self, path, key_type=None, block_factor=None, unique=False, global_depth=1):
        self.path = path
        self.dir_path = path + ".dir"
        self.buk_path = path + ".buk"
        exists = os.path.exists(self.dir_path)
        if exists:
            self._load_meta()
        else:
            self.key_type = key_type
            self.block_factor = block_factor
            self.unique = unique
            self.global_depth = global_depth
        self.cfg = BucketConfig(self.key_type, self.block_factor)
        self.buckets = FileManager(self.buk_path, self.cfg.page_size)
        if exists:
            self._load_directory()
        else:
            self._init_directory()

    @classmethod
    def open(cls, path):
        return cls(path)

    def _init_directory(self):
        self.directory = []
        for _ in range(1 << self.global_depth):
            page_id = self.buckets.append_raw(Bucket(self.cfg, self.global_depth).pack())
            self.directory.append(page_id)
        self._save()

    def _read_bucket(self, page_id):
        return Bucket.unpack(self.cfg, self.buckets.read_raw(page_id))

    def _write_bucket(self, page_id, bucket):
        self.buckets.write_raw(page_id, bucket.pack())

    def _dir_index(self, key):
        return stable_hash(key, self.key_type) & ((1 << self.global_depth) - 1)

    def _can_split(self, bucket):
        hashes = set()
        for key, rid in bucket.entries:
            hashes.add(stable_hash(key, self.key_type))
        return len(hashes) > 1

    def _double_directory(self):
        self.directory = self.directory + list(self.directory)
        self.global_depth += 1

    def _split(self, page_id):
        old = self._read_bucket(page_id)
        depth = old.local_depth
        low = Bucket(self.cfg, depth + 1)
        high = Bucket(self.cfg, depth + 1)
        for key, rid in old.entries:
            if (stable_hash(key, self.key_type) >> depth) & 1:
                high.add(key, rid)
            else:
                low.add(key, rid)
        self._write_bucket(page_id, low)
        high_id = self.buckets.append_raw(high.pack())
        for i in range(len(self.directory)):
            if self.directory[i] == page_id and (i >> depth) & 1:
                self.directory[i] = high_id
        self._save()

    def _chain_insert(self, page_id, bucket, key, rid):
        while bucket.overflow_ptr != -1:
            page_id = bucket.overflow_ptr
            bucket = self._read_bucket(page_id)
        if not bucket.is_full():
            bucket.add(key, rid)
            self._write_bucket(page_id, bucket)
            return
        overflow = Bucket(self.cfg, bucket.local_depth)
        overflow.add(key, rid)
        new_id = self.buckets.append_raw(overflow.pack())
        bucket.overflow_ptr = new_id
        self._write_bucket(page_id, bucket)

    def insert(self, key, rid):
        if self.unique and self.search(key):
            return False
        while True:
            page_id = self.directory[self._dir_index(key)]
            bucket = self._read_bucket(page_id)
            if not bucket.is_full():
                bucket.add(key, rid)
                self._write_bucket(page_id, bucket)
                return True
            if not self._can_split(bucket) or self.global_depth >= MAX_GLOBAL_DEPTH:
                self._chain_insert(page_id, bucket, key, rid)
                return True
            if bucket.local_depth == self.global_depth:
                self._double_directory()
            self._split(page_id)

    def search(self, key):
        page_id = self.directory[self._dir_index(key)]
        result = []
        while page_id != -1:
            bucket = self._read_bucket(page_id)
            for k, rid in bucket.entries:
                if k == key:
                    result.append(rid)
            page_id = bucket.overflow_ptr
        return result

    def delete(self, key, rid=None):
        page_id = self.directory[self._dir_index(key)]
        removed = False
        while page_id != -1:
            bucket = self._read_bucket(page_id)
            kept = []
            for k, r in bucket.entries:
                if k == key and (rid is None or r == rid):
                    removed = True
                else:
                    kept.append((k, r))
            if len(kept) != len(bucket.entries):
                bucket.entries = kept
                self._write_bucket(page_id, bucket)
            page_id = bucket.overflow_ptr
        return removed

    def bulk_load(self, pairs):
        for key, rid in pairs:
            self.insert(key, rid)

    def stats(self):
        seen = set()
        num_buckets = 0
        num_overflow = 0
        entries = 0
        for start in set(self.directory):
            page_id = start
            main = True
            while page_id != -1 and page_id not in seen:
                seen.add(page_id)
                bucket = self._read_bucket(page_id)
                num_buckets += 1
                if not main:
                    num_overflow += 1
                entries += len(bucket.entries)
                main = False
                page_id = bucket.overflow_ptr
        return {
            "global_depth": self.global_depth,
            "directory_size": len(self.directory),
            "num_buckets": num_buckets,
            "num_overflow": num_overflow,
            "entries": entries,
            "disk_accesses": self.buckets.disk_accesses,
            "height": 1,
        }

    def _save(self):
        with open(self.dir_path, "wb") as f:
            f.write(struct.pack(
                DIR_HEADER_FORMAT,
                self.global_depth,
                self.block_factor,
                1 if self.unique else 0,
                self.key_type.encode()[:16],
            ))
            for page_id in self.directory:
                f.write(struct.pack(DIR_ENTRY_FORMAT, page_id))

    def _load_meta(self):
        with open(self.dir_path, "rb") as f:
            gd, bf, uniq, kt = struct.unpack(DIR_HEADER_FORMAT, f.read(DIR_HEADER_SIZE))
        self.global_depth = gd
        self.block_factor = bf
        self.unique = bool(uniq)
        self.key_type = kt.rstrip(b"\x00").decode()

    def _load_directory(self):
        self.directory = []
        with open(self.dir_path, "rb") as f:
            f.seek(DIR_HEADER_SIZE)
            for _ in range(1 << self.global_depth):
                self.directory.append(struct.unpack(DIR_ENTRY_FORMAT, f.read(DIR_ENTRY_SIZE))[0])

    def close(self):
        self._save()
        self.buckets.close()
