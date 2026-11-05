import json
import os
import threading

from .fulltext import spimi
from .fulltext.inverted_index import IndiceInvertido

FULLTEXT = "FULLTEXT"


class IndiceTexto:
    def __init__(self, tabla, nombre, columna):
        self.tabla = tabla
        self.nombre = nombre
        self.columna = columna
        self.tipo = FULLTEXT
        self.ruta = os.path.join(tabla.data_dir, tabla.name + "__" + nombre)
        self.estructura = None
        self.reconstrucciones = 0
        self._cerrojo = threading.Lock()

    def _documentos(self):
        for fila in self.tabla._iter_rows():
            texto = fila[self.columna]
            if texto is not None:
                yield self.tabla._rid_secundario(fila), texto

    def construir(self):
        with self._cerrojo:
            spimi.construir(self._documentos(), self.ruta, self.tabla.limite_spimi)
            self.estructura = IndiceInvertido(self.ruta)
            self.reconstrucciones += 1
        return self.estructura.meta

    def abrir(self):
        if not os.path.exists(self.ruta + ".ftmeta"):
            return
        with open(self.ruta + ".ftmeta") as archivo:
            meta = json.load(archivo)
        if not meta.get("desactualizado"):
            self.estructura = IndiceInvertido(self.ruta)

    def invalidar(self):
        if self.estructura is None:
            return
        self.estructura = None
        if os.path.exists(self.ruta + ".ftmeta"):
            with open(self.ruta + ".ftmeta") as archivo:
                meta = json.load(archivo)
            meta["desactualizado"] = True
            with open(self.ruta + ".ftmeta", "w") as archivo:
                json.dump(meta, archivo)

    def vigente(self):
        if self.estructura is None:
            self.construir()
        return self.estructura

    def destruir(self):
        self.estructura = None
        spimi.destruir(self.ruta)

    def describir(self):
        return {"name": self.nombre, "column": self.columna, "kind": self.tipo}


class TextIndexTable:

    def _init_texto(self, definiciones=None):
        self.indices_texto = {}
        self.limite_spimi = spimi.LIMITE_POSTINGS
        for definicion in definiciones or []:
            indice = IndiceTexto(self, definicion["name"], definicion["column"])
            indice.abrir()
            self.indices_texto[indice.nombre] = indice

    def indice_texto_de(self, columna):
        for nombre in sorted(self.indices_texto):
            if self.indices_texto[nombre].columna == columna:
                return self.indices_texto[nombre]
        return None

    def crear_indice_texto(self, nombre, columna):
        if dict(self.schema).get(columna) != "text":
            raise ValueError(f"FULLTEXT solo indexa columnas TEXT y '{columna}' no lo es")
        if self.indice_texto_de(columna) is not None:
            raise ValueError(f"'{columna}' ya tiene el índice FULLTEXT '{self.indice_texto_de(columna).nombre}'")
        indice = IndiceTexto(self, nombre, columna)
        indice.construir()
        self.indices_texto[nombre] = indice
        self._write_descriptor()
        return indice

    def eliminar_indice_texto(self, nombre):
        self.indices_texto.pop(nombre).destruir()
        self._write_descriptor()

    def _invalidar_textos(self):
        for indice in self.indices_texto.values():
            indice.invalidar()

    def _destruir_textos(self):
        for indice in self.indices_texto.values():
            indice.destruir()
