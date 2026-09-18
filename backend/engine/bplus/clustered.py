import os

from engine.bplus.bplus_tree import BPlusTree


class ClusteredBPlusTree:
    def __init__(self, index_path, sequential_file, key_type, block_factor=32):
        self.index_path = index_path
        self.key_type = key_type
        self.block_factor = block_factor
        self.seq = sequential_file
        self.key_index = sequential_file.key_index
        self.tree = BPlusTree(index_path, key_type=key_type, block_factor=block_factor)
        self._last_reorg = sequential_file.reorganizations
        if self.tree.stats()["entries"] == 0 and len(self.seq.scan()) > 0:
            self.rebuild()

    def _new_tree(self):
        self.tree.close()
        for suffix in (".meta", ".nodes"):
            path = self.index_path + suffix
            if os.path.exists(path):
                os.remove(path)
        self.tree = BPlusTree(self.index_path, key_type=self.key_type, block_factor=self.block_factor)

    def rebuild(self):
        self._new_tree()
        for position, fields in self.seq._ordered_with_pos():
            key = fields[self.key_index]
            self.tree.insert(key, (position, 0))
        self._last_reorg = self.seq.reorganizations

    def insert(self, key, record):
        position = self.seq.insert(record)
        if self.seq.reorganizations != self._last_reorg:
            self.rebuild()
        else:
            self.tree.insert(key, (position, 0))
        return position

    def bulk_load(self, records):
        self.seq.bulk_load(records)
        self.rebuild()

    def search_with_pos(self, key):
        result = []
        for pair in self.tree.search(key):
            slot = self.seq.read_record(pair[0])
            if slot is None:
                continue
            if self.seq._deleted(slot) == 1:
                continue
            result.append((pair[0], self.seq._fields(slot)))
        return result

    def search(self, key):
        result = []
        for position, fields in self.search_with_pos(key):
            result.append(fields)
        return result

    def range_search(self, start_key, end_key):
        result = []
        for key, pair in self.tree.range_search(start_key, end_key):
            slot = self.seq.read_record(pair[0])
            if slot is None:
                continue
            if self.seq._deleted(slot) == 1:
                continue
            result.append((key, self.seq._fields(slot)))
        return result

    def delete(self, key):
        removed = self.seq.delete(key)
        if removed:
            self.tree.delete(key)
        return removed

    def stats(self):
        return self.tree.stats()

    def close(self):
        self.tree.close()
