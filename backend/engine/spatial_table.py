import os
import tempfile
from threading import RLock

from .rtree import RTree


class SpatialTable:

    def _init_spatial(self):
        self.spatial_indexes = {}
        self._spatial_lock = RLock()
        self._directorio_temporal = None
        self._base_temporal = tempfile.gettempdir()

    def _ruta_rtree(self, column):
        if self._directorio_temporal is None:
            self._directorio_temporal = tempfile.TemporaryDirectory(prefix="rtree_", dir=self._base_temporal)
        return os.path.join(self._directorio_temporal.name, column + "_rtree")

    def _abrir_indices_espaciales(self, columns):
        with self._spatial_lock:
            nuevos = []
            for column in columns:
                tree = RTree(self._ruta_rtree(column))
                self.spatial_indexes[column] = tree
                if tree.nuevo:
                    nuevos.append(column)
            if nuevos:
                self._cargar_indices(nuevos)

    def _cargar_indices(self, columns):
        filas = self.scan()
        for column in columns:
            self.spatial_indexes[column].bulk_load([(row[column], self.spatial_id(row)) for row in filas])

    def spatial_index(self, column):
        with self._spatial_lock:
            if column not in self.spatial_indexes:
                self.spatial_indexes[column] = RTree(self._ruta_rtree(column))
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
