from threading import RLock

from .rtree import RTree


class SpatialTable:
    """Índices derivados de los POINT persistidos, construidos al primer uso."""

    def _init_spatial(self):
        self.spatial_indexes = {}
        self._spatial_lock = RLock()

    def spatial_index(self, column):
        with self._spatial_lock:
            if column not in self.spatial_indexes:
                tree = RTree()
                for row in self.scan():
                    tree.insert(row[column], self.spatial_id(row))
                self.spatial_indexes[column] = tree
            return self.spatial_indexes[column]

    def _spatial_insert(self, row):
        for column, tree in self.spatial_indexes.items():
            tree.insert(row[column], self.spatial_id(row))

    def _spatial_remove(self, row):
        for column, tree in self.spatial_indexes.items():
            tree.delete(row[column], self.spatial_id(row))
