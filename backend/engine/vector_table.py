import os

from .vectorial.almacen import AlmacenVectores


class VectorTable:

    def _init_vectorial(self):
        self.almacenes = {}
        for columna, definicion in self.column_definitions.items():
            if definicion.get("type") == "VECTOR":
                self.almacenes[columna] = AlmacenVectores(self._ruta_vector(columna), definicion["size"])

    def _ruta_vector(self, columna):
        return os.path.join(self.data_dir, self.name + "_" + columna + "_vector")

    def columnas_declaradas(self):
        if not self.almacenes:
            return list(self.columns)
        return list(self.column_definitions)

    def _vector_insert(self, row, rid):
        for columna, almacen in self.almacenes.items():
            vector = row.get(columna)
            if vector is not None:
                almacen.agregar(vector, rid)

    def _vector_remove(self, row):
        for almacen in self.almacenes.values():
            almacen.borrar(row["__rid__"])

    def _vector_update(self, row, asignaciones):
        for columna, valor in asignaciones:
            almacen = self.almacenes.get(columna)
            if almacen is None:
                continue
            almacen.borrar(row["__rid__"])
            if valor is not None:
                almacen.agregar(valor, row["__rid__"])

    def _cerrar_vectorial(self):
        for almacen in self.almacenes.values():
            almacen.cerrar()

    def _destruir_vectorial(self):
        for almacen in self.almacenes.values():
            almacen.destruir()
