from threading import RLock

from .rtree import RTree
from .rtree_paged import PagedRTree


class SpatialTable:

    def _init_spatial(self):
        self.spatial_indexes = {}
        self._spatial_lock = RLock()

    def _ruta_rtree(self, column):
        return None

    def _nuevo_rtree(self, column):
        ruta = self._ruta_rtree(column)
        if ruta is None:
            return RTree()
        return PagedRTree(ruta)

    def _abrir_indices_espaciales(self, columns):
        with self._spatial_lock:
            nuevos = []
            for column in columns:
                tree = self._nuevo_rtree(column)
                self.spatial_indexes[column] = tree
                if getattr(tree, "nuevo", False):
                    nuevos.append(column)
            if nuevos:
                self._cargar_indices(nuevos)

    def _cargar_indices(self, columns):
        filas = self.scan()
        for column in columns:
            tree = self.spatial_indexes[column]
            pares = [(row[column], self.spatial_id(row)) for row in filas]
            if isinstance(tree, PagedRTree):
                tree.bulk_load(pares)
                continue
            tree = RTree()
            for coordinates, payload in pares:
                tree.insert(coordinates, payload)
            self.spatial_indexes[column] = tree

    def spatial_index(self, column):
        with self._spatial_lock:
            if column not in self.spatial_indexes:
                tree = self._nuevo_rtree(column)
                self.spatial_indexes[column] = tree
                self._cargar_indices([column])
            return self.spatial_indexes[column]

    def reconstruir_indices_espaciales(self):
        with self._spatial_lock:
            if self.spatial_indexes:
                self._cargar_indices(list(self.spatial_indexes))

    def _spatial_insert(self, row):
        for column, tree in self.spatial_indexes.items():
            tree.insert(row[column], self.spatial_id(row))

    def _spatial_remove(self, row):
        for column, tree in self.spatial_indexes.items():
            tree.delete(row[column], self.spatial_id(row))
