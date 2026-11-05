import json
import os

import numpy as np

CAPACIDAD_INICIAL = 64
SIN_RID = -1
SUFIJOS = (".vec", ".vrid", ".vmeta")


class AlmacenVectores:
    def __init__(self, ruta, dimension):
        if not isinstance(dimension, (int, np.integer)) or dimension <= 0:
            raise ValueError("la dimensión debe ser un entero positivo")
        self.ruta = ruta
        self.dimension = int(dimension)
        self.total = 0
        self.capacidad = 0
        self.id_por_rid = {}
        self._vectores = None
        self._rids = None
        if os.path.exists(ruta + ".vmeta"):
            self._abrir()
        else:
            self._reservar(CAPACIDAD_INICIAL)
            self._guardar_meta()

    def _abrir(self):
        with open(self.ruta + ".vmeta") as archivo:
            meta = json.load(archivo)
        if meta["dimension"] != self.dimension:
            raise ValueError(f"el almacén tiene dimensión {meta['dimension']}, no {self.dimension}")
        self.total = meta["total"]
        self.capacidad = os.path.getsize(self.ruta + ".vec") // (self.dimension * 4)
        self._mapear()
        for identificador in self.ids_vivos().tolist():
            self.id_por_rid[self.rid(identificador)] = identificador

    def _mapear(self):
        self._vectores = np.memmap(self.ruta + ".vec", dtype=np.float32, mode="r+", shape=(self.capacidad, self.dimension))
        self._rids = np.memmap(self.ruta + ".vrid", dtype=np.int64, mode="r+", shape=(self.capacidad, 2))

    def _reservar(self, capacidad):
        self.vaciar_mapas()
        for sufijo, bytes_por_fila in ((".vec", self.dimension * 4), (".vrid", 16)):
            with open(self.ruta + sufijo, "ab") as archivo:
                archivo.truncate(capacidad * bytes_por_fila)
        self.capacidad = capacidad
        self._mapear()

    def vaciar_mapas(self):
        for mapa in (self._vectores, self._rids):
            if mapa is not None:
                mapa.flush()
        self._vectores = None
        self._rids = None

    def _guardar_meta(self):
        temporal = self.ruta + ".vmeta.tmp"
        with open(temporal, "w") as archivo:
            json.dump({"dimension": self.dimension, "total": self.total}, archivo)
        os.replace(temporal, self.ruta + ".vmeta")

    def _validar(self, vector):
        vector = np.asarray(vector, dtype=np.float32)
        if vector.shape != (self.dimension,):
            raise ValueError(f"se esperaba un vector de dimensión {self.dimension} y llegó {vector.shape}")
        if not np.isfinite(vector).all():
            raise ValueError("el vector contiene NaN o infinitos")
        return vector

    def agregar(self, vector, rid):
        identificador = self._escribir(self._validar(vector), rid)
        self._guardar_meta()
        return identificador

    def agregar_lote(self, vectores, rids):
        validados = []
        for vector in vectores:
            validados.append(self._validar(vector))
        identificadores = []
        for vector, rid in zip(validados, rids):
            identificadores.append(self._escribir(vector, rid))
        self._guardar_meta()
        return identificadores

    def _escribir(self, vector, rid):
        rid = (int(rid[0]), int(rid[1]))
        if rid in self.id_por_rid:
            raise ValueError(f"el RID {rid} ya tiene un vector")
        if self.total == self.capacidad:
            self._reservar(self.capacidad * 2)
        identificador = self.total
        self._vectores[identificador] = vector
        self._rids[identificador] = rid
        self.total += 1
        self.id_por_rid[rid] = identificador
        return identificador

    def borrar(self, rid):
        identificador = self.id_por_rid.pop((int(rid[0]), int(rid[1])), None)
        if identificador is not None:
            self._rids[identificador] = (SIN_RID, SIN_RID)
        return identificador

    def matriz(self):
        return np.asarray(self._vectores)

    def vector(self, identificador):
        return np.array(self._vectores[identificador])

    def rid(self, identificador):
        pagina, ranura = self._rids[identificador].tolist()
        return (pagina, ranura)

    def id_de(self, rid):
        return self.id_por_rid.get((int(rid[0]), int(rid[1])))

    def vivo(self, identificador):
        return bool(self._rids[identificador, 0] != SIN_RID)

    def mascara_vivos(self):
        mascara = np.zeros(self.total, dtype=bool)
        mascara[:] = self._rids[:self.total, 0] != SIN_RID
        return mascara

    def ids_vivos(self):
        return np.flatnonzero(self.mascara_vivos())

    def __len__(self):
        return len(self.id_por_rid)

    def cerrar(self):
        self.vaciar_mapas()
        self._guardar_meta()

    def destruir(self):
        self.vaciar_mapas()
        for sufijo in SUFIJOS:
            if os.path.exists(self.ruta + sufijo):
                os.remove(self.ruta + sufijo)
