import os
import struct

from engine.hashing.boundary import key_format, pack_key, unpack_key, pack_rid, unpack_rid, RID_SIZE
from engine.hashing.page import FileManager

NODE_HEADER_FORMAT = "<iii"
NODE_HEADER_SIZE = struct.calcsize(NODE_HEADER_FORMAT)
PTR_FORMAT = "<i"
PTR_SIZE = struct.calcsize(PTR_FORMAT)
META_FORMAT = "<iiii16s"
META_SIZE = struct.calcsize(META_FORMAT)


class NodeConfig:
    def __init__(self, key_type, order):
        self.key_type = key_type
        self.key_fmt = key_format(key_type)
        self.key_size = struct.calcsize(self.key_fmt)
        self.order = order
        leaf_body = order * (self.key_size + RID_SIZE)
        internal_body = (order + 1) * PTR_SIZE + order * self.key_size
        self.page_size = NODE_HEADER_SIZE + max(leaf_body, internal_body)


class Node:
    def __init__(self, cfg, is_leaf=True, keys=None, rids=None, children=None, next_leaf=-1):
        self.cfg = cfg
        self.is_leaf = is_leaf
        self.keys = keys if keys is not None else []
        self.rids = rids if rids is not None else []
        self.children = children if children is not None else []
        self.next_leaf = next_leaf

    def pack(self):
        cfg = self.cfg
        out = struct.pack(NODE_HEADER_FORMAT, 1 if self.is_leaf else 0, len(self.keys), self.next_leaf)
        if self.is_leaf:
            for key, rid in zip(self.keys, self.rids):
                out += pack_key(key, cfg.key_type, cfg.key_fmt) + pack_rid(rid)
        else:
            for child in self.children:
                out += struct.pack(PTR_FORMAT, child)
            for key in self.keys:
                out += pack_key(key, cfg.key_type, cfg.key_fmt)
        return out.ljust(cfg.page_size, b"\x00")

    @classmethod
    def unpack(cls, cfg, raw):
        is_leaf, count, next_leaf = struct.unpack_from(NODE_HEADER_FORMAT, raw, 0)
        pos = NODE_HEADER_SIZE
        if is_leaf:
            keys, rids = [], []
            for _ in range(count):
                keys.append(unpack_key(raw[pos:pos + cfg.key_size], cfg.key_type, cfg.key_fmt))
                rids.append(unpack_rid(raw[pos + cfg.key_size:pos + cfg.key_size + RID_SIZE]))
                pos += cfg.key_size + RID_SIZE
            return cls(cfg, True, keys, rids, None, next_leaf)
        children = []
        for _ in range(count + 1):
            children.append(struct.unpack(PTR_FORMAT, raw[pos:pos + PTR_SIZE])[0])
            pos += PTR_SIZE
        keys = []
        for _ in range(count):
            keys.append(unpack_key(raw[pos:pos + cfg.key_size], cfg.key_type, cfg.key_fmt))
            pos += cfg.key_size
        return cls(cfg, False, keys, None, children, -1)


class BPlusTree:
    def __init__(self, path, key_type=None, block_factor=None, unique=False):
        self.path = path
        self.meta_path = path + ".meta"
        self.nodes_path = path + ".nodes"
        exists = os.path.exists(self.meta_path)
        if exists:
            self._load_meta()
        else:
            self.key_type = key_type
            self.order = block_factor
            self.unique = unique
            self.height = 1
        self.cfg = NodeConfig(self.key_type, self.order)
        self.nodes = FileManager(self.nodes_path, self.cfg.page_size)
        if exists:
            return
        self.root_id = self.nodes.append_raw(Node(self.cfg, is_leaf=True).pack())
        self._save()

    @classmethod
    def open(cls, path):
        return cls(path)

    def _read(self, page_id):
        return Node.unpack(self.cfg, self.nodes.read_raw(page_id))

    def _write(self, page_id, node):
        self.nodes.write_raw(page_id, node.pack())

    def _child_index(self, node, key):
        i = 0
        while i < len(node.keys) and key >= node.keys[i]:
            i += 1
        return i

    def _descend(self, key):
        page_id = self.root_id
        node = self._read(page_id)
        while not node.is_leaf:
            page_id = node.children[self._child_index(node, key)]
            node = self._read(page_id)
        return page_id, node

    def _split_leaf(self, page_id, node):
        mid = (len(node.keys) + 1) // 2
        right = Node(self.cfg, True, node.keys[mid:], node.rids[mid:], None, node.next_leaf)
        node.keys = node.keys[:mid]
        node.rids = node.rids[:mid]
        right_id = self.nodes.append_raw(right.pack())
        node.next_leaf = right_id
        self._write(page_id, node)
        return right.keys[0], right_id

    def _split_internal(self, page_id, node):
        mid = len(node.keys) // 2
        sep = node.keys[mid]
        right = Node(self.cfg, False, node.keys[mid + 1:], None, node.children[mid + 1:])
        node.keys = node.keys[:mid]
        node.children = node.children[:mid + 1]
        right_id = self.nodes.append_raw(right.pack())
        self._write(page_id, node)
        return sep, right_id

    def _insert(self, page_id, key, rid):
        node = self._read(page_id)
        if node.is_leaf:
            pos = 0
            while pos < len(node.keys) and node.keys[pos] <= key:
                pos += 1
            node.keys.insert(pos, key)
            node.rids.insert(pos, rid)
            if len(node.keys) <= self.order:
                self._write(page_id, node)
                return None
            return self._split_leaf(page_id, node)
        i = self._child_index(node, key)
        result = self._insert(node.children[i], key, rid)
        if result is None:
            return None
        sep, new_id = result
        node.keys.insert(i, sep)
        node.children.insert(i + 1, new_id)
        if len(node.keys) <= self.order:
            self._write(page_id, node)
            return None
        return self._split_internal(page_id, node)

    def insert(self, key, rid):
        if self.unique and self.search(key):
            return False
        result = self._insert(self.root_id, key, rid)
        if result is not None:
            sep, new_id = result
            new_root = Node(self.cfg, False, [sep], None, [self.root_id, new_id])
            self.root_id = self.nodes.append_raw(new_root.pack())
            self.height += 1
            self._save()
        return True

    def search(self, key):
        _, node = self._descend(key)
        result = []
        while node is not None:
            over = False
            for k, rid in zip(node.keys, node.rids):
                if k == key:
                    result.append(rid)
                elif k > key:
                    over = True
                    break
            if over or node.next_leaf == -1:
                break
            node = self._read(node.next_leaf)
        return result

    def range_search(self, low, high):
        _, node = self._descend(low)
        result = []
        while node is not None:
            over = False
            for k, rid in zip(node.keys, node.rids):
                if k < low:
                    continue
                if k > high:
                    over = True
                    break
                result.append((k, rid))
            if over or node.next_leaf == -1:
                break
            node = self._read(node.next_leaf)
        return result

    def scan(self):
        node = self._read(self.root_id)
        while not node.is_leaf:
            node = self._read(node.children[0])
        while node is not None:
            for k, rid in zip(node.keys, node.rids):
                yield k, rid
            node = self._read(node.next_leaf) if node.next_leaf != -1 else None

    def delete(self, key, rid=None):
        page_id, node = self._descend(key)
        removed = False
        while page_id != -1:
            over = False
            new_keys, new_rids = [], []
            for k, r in zip(node.keys, node.rids):
                if k == key and (rid is None or r == rid):
                    removed = True
                    continue
                if k > key:
                    over = True
                new_keys.append(k)
                new_rids.append(r)
            if len(new_keys) != len(node.keys):
                node.keys, node.rids = new_keys, new_rids
                self._write(page_id, node)
            nxt = node.next_leaf
            if over or nxt == -1:
                break
            page_id = nxt
            node = self._read(page_id)
        return removed

    def bulk_load(self, pairs):
        for key, rid in pairs:
            self.insert(key, rid)

    def stats(self):
        leaves = 0
        internals = 0
        entries = 0
        stack = [self.root_id]
        while stack:
            node = self._read(stack.pop())
            if node.is_leaf:
                leaves += 1
                entries += len(node.keys)
            else:
                internals += 1
                stack.extend(node.children)
        return {
            "height": self.height,
            "order": self.order,
            "num_leaves": leaves,
            "num_internal": internals,
            "entries": entries,
            "disk_accesses": self.nodes.disk_accesses,
        }

    def _save(self):
        with open(self.meta_path, "wb") as f:
            f.write(struct.pack(
                META_FORMAT,
                self.root_id,
                self.height,
                self.order,
                1 if self.unique else 0,
                self.key_type.encode()[:16],
            ))

    def _load_meta(self):
        with open(self.meta_path, "rb") as f:
            root_id, height, order, uniq, kt = struct.unpack(META_FORMAT, f.read(META_SIZE))
        self.root_id = root_id
        self.height = height
        self.order = order
        self.unique = bool(uniq)
        self.key_type = kt.rstrip(b"\x00").decode()

    def close(self):
        self._save()
        self.nodes.close()
