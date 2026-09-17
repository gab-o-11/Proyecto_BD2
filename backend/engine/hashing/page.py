import os
import struct

from .boundary import (
    RID_SIZE,
    key_format,
    pack_key,
    unpack_key,
    pack_rid,
    unpack_rid,
)

HEADER_FORMAT = "<iii"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)


class BucketConfig:
    def __init__(self, key_type, block_factor):
        self.key_type = key_type
        self.key_fmt = key_format(key_type)
        self.key_size = struct.calcsize(self.key_fmt)
        self.block_factor = block_factor
        self.entry_size = self.key_size + RID_SIZE
        self.page_size = HEADER_SIZE + block_factor * self.entry_size


class Bucket:
    def __init__(self, cfg, local_depth=0, entries=None, overflow_ptr=-1):
        self.cfg = cfg
        self.local_depth = local_depth
        self.entries = entries if entries is not None else []
        self.overflow_ptr = overflow_ptr

    def is_full(self):
        return len(self.entries) >= self.cfg.block_factor

    def add(self, key, rid):
        self.entries.append((key, rid))

    def remove(self, key, rid=None):
        for i, (k, r) in enumerate(self.entries):
            if k == key and (rid is None or r == rid):
                del self.entries[i]
                return True
        return False

    def pack(self):
        cfg = self.cfg
        out = struct.pack(HEADER_FORMAT, self.local_depth, len(self.entries), self.overflow_ptr)
        for key, rid in self.entries:
            out += pack_key(key, cfg.key_type, cfg.key_fmt) + pack_rid(rid)
        return out.ljust(cfg.page_size, b"\x00")

    @classmethod
    def unpack(cls, cfg, raw):
        local_depth, count, overflow_ptr = struct.unpack_from(HEADER_FORMAT, raw, 0)
        entries = []
        pos = HEADER_SIZE
        for _ in range(count):
            key = unpack_key(raw[pos:pos + cfg.key_size], cfg.key_type, cfg.key_fmt)
            rid = unpack_rid(raw[pos + cfg.key_size:pos + cfg.entry_size])
            entries.append((key, rid))
            pos += cfg.entry_size
        return cls(cfg, local_depth, entries, overflow_ptr)


class FileManager:
    def __init__(self, filename, page_size):
        self.filename = filename
        self.page_size = page_size
        nuevo = not os.path.exists(filename)
        self.f = open(filename, "w+b" if nuevo else "r+b")
        self.disk_accesses = 0

    def num_pages(self):
        self.f.seek(0, os.SEEK_END)
        return self.f.tell() // self.page_size

    def read_raw(self, idx):
        self.disk_accesses += 1
        self.f.seek(idx * self.page_size)
        return self.f.read(self.page_size)

    def write_raw(self, idx, data):
        self.disk_accesses += 1
        self.f.seek(idx * self.page_size)
        self.f.write(data)
        self.f.flush()

    def append_raw(self, data):
        self.disk_accesses += 1
        self.f.seek(0, os.SEEK_END)
        idx = self.f.tell() // self.page_size
        self.f.write(data)
        self.f.flush()
        return idx

    def close(self):
        self.f.close()
