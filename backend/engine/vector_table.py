import os

from .vectorial.almacen import AlmacenVectores
from .vectorial.hnsw import IndiceHNSW
from .vectorial.ivf import IndiceIVF
from .vectorial.metricas import COSINE


class IndiceVectorial:
    def __init__(self, tabla, nombre, columna, tipo, opciones):
        self.nombre = nombre
        self.columna = columna
        self.tipo = tipo
        self.opciones = opciones
        self.metrica = opciones.get("METRIC", COSINE)
        self.almacen = tabla.almacenes[columna]
        self.ruta = os.path.join(tabla.data_dir, tabla.name + "_" + nombre + ".vidx")
        self.estructura = None

    def _nueva(self):
        if self.tipo == "IVF":
            return IndiceIVF(self.almacen, self.metrica, self.opciones.get("LISTS"))
        return IndiceHNSW(self.almacen, self.metrica, self.opciones.get("M", 16), self.opciones.get("EF_CONSTRUCTION", 64))

    def construir(self):
        self.estructura = self._nueva()
        self.estructura.construir()
        self.guardar()

    def abrir(self):
        if not os.path.exists(self.ruta):
            self.construir()
        elif self.tipo == "IVF":
            self.estructura = IndiceIVF.abrir(self.almacen, self.ruta)
        else:
            self.estructura = IndiceHNSW.abrir(self.almacen, self.ruta)

    def guardar(self):
        self.estructura.guardar(self.ruta)

    def destruir(self):
        if os.path.exists(self.ruta):
            os.remove(self.ruta)

    def describir(self):
        return {"name": self.nombre, "column": self.columna, "kind": self.tipo, "options": self.opciones}


class VectorTable:

    def _init_vectorial(self, definiciones=None):
        self.almacenes = {}
        self.indices_vectoriales = {}
        for columna, definicion in self.column_definitions.items():
            if definicion.get("type") == "VECTOR":
                self.almacenes[columna] = AlmacenVectores(self._ruta_vector(columna), definicion["size"])
        for definicion in definiciones or []:
            indice = IndiceVectorial(self, definicion["name"], definicion["column"], definicion["kind"], definicion["options"])
            indice.abrir()
            self.indices_vectoriales[indice.nombre] = indice

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

    def crear_indice_vectorial(self, nombre, columna, tipo, opciones):
        indice = IndiceVectorial(self, nombre, columna, tipo, opciones)
        indice.construir()
        self.indices_vectoriales[nombre] = indice
        self._write_descriptor()
        return indice

    def eliminar_indice_vectorial(self, nombre):
        self.indices_vectoriales.pop(nombre).destruir()
        self._write_descriptor()

    def _cerrar_vectorial(self):
        for indice in self.indices_vectoriales.values():
            indice.guardar()
        for almacen in self.almacenes.values():
            almacen.cerrar()

    def _destruir_vectorial(self):
        for indice in self.indices_vectoriales.values():
            indice.destruir()
        for almacen in self.almacenes.values():
            almacen.destruir()
