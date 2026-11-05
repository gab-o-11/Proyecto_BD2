import heapq
import math
import os
import random

import numpy as np

from .metricas import distancias, distancias_entre, validar_metrica

EF_SEARCH = 40


class IndiceHNSW:
    tipo = "HNSW"

    def __init__(self, almacen, metrica, m=16, ef_construccion=64, semilla=0):
        if m < 2:
            raise ValueError("m debe ser mayor o igual a 2")
        if ef_construccion < 1:
            raise ValueError("ef_construccion debe ser un entero positivo")
        self.almacen = almacen
        self.metrica = validar_metrica(metrica)
        self.m = m
        self.m_max = m
        self.m_max0 = 2 * m
        self.ml = 1.0 / math.log(m)
        self.ef_construccion = ef_construccion
        self.semilla = semilla
        self.azar = random.Random(semilla)
        self.vecinos = {}
        self.entrada = None
        self.nivel_maximo = -1

    def _nivel_aleatorio(self):
        return int(-math.log(1.0 - self.azar.random()) * self.ml)

    def _limite(self, capa):
        if capa == 0:
            return self.m_max0
        return self.m_max

    def _explorar(self, consulta, entradas, ef, capa, vivos=None):
        matriz = self.almacen.matriz()
        visitados = np.zeros(self.almacen.total, dtype=bool)
        visitados[entradas] = True
        valores = distancias(consulta, matriz[entradas], self.metrica).tolist()
        candidatos = []
        resultados = []
        for valor, identificador in zip(valores, entradas):
            heapq.heappush(candidatos, (valor, identificador))
            if vivos is None or vivos[identificador]:
                heapq.heappush(resultados, (-valor, identificador))
        while candidatos:
            valor, actual = heapq.heappop(candidatos)
            if len(resultados) >= ef and valor > -resultados[0][0]:
                break
            lista = self.vecinos[actual][capa]
            if not lista:
                continue
            nuevos = np.array(lista, dtype=np.int64)
            nuevos = nuevos[~visitados[nuevos]]
            if nuevos.size == 0:
                continue
            visitados[nuevos] = True
            valores = distancias(consulta, matriz[nuevos], self.metrica).tolist()
            for valor_nuevo, identificador in zip(valores, nuevos.tolist()):
                if len(resultados) < ef or valor_nuevo < -resultados[0][0]:
                    heapq.heappush(candidatos, (valor_nuevo, identificador))
                    if vivos is None or vivos[identificador]:
                        heapq.heappush(resultados, (-valor_nuevo, identificador))
                        if len(resultados) > ef:
                            heapq.heappop(resultados)
        ordenados = []
        for valor, identificador in resultados:
            ordenados.append((-valor, identificador))
        ordenados.sort()
        return ordenados

    def _seleccionar(self, candidatos, m):
        if len(candidatos) <= m:
            elegidos = []
            for _, identificador in candidatos:
                elegidos.append(identificador)
            return elegidos
        identificadores = []
        valores = []
        for valor, identificador in candidatos:
            valores.append(valor)
            identificadores.append(identificador)
        valores = np.array(valores, dtype=np.float32)
        cruzadas = distancias_entre(self.almacen.matriz()[identificadores], self.metrica)
        descartado = np.zeros(len(identificadores), dtype=bool)
        elegidos = []
        posiciones = []
        for posicion in range(len(identificadores)):
            if descartado[posicion]:
                continue
            elegidos.append(identificadores[posicion])
            posiciones.append(posicion)
            if len(elegidos) == m:
                return elegidos
            descartado |= cruzadas[posicion] <= valores
        descartado[posiciones] = False
        for posicion in np.flatnonzero(descartado).tolist():
            if len(elegidos) == m:
                break
            elegidos.append(identificadores[posicion])
        return elegidos

    def _recortar(self, identificador, capa):
        lista = self.vecinos[identificador][capa]
        limite = self._limite(capa)
        if len(lista) <= limite:
            return
        matriz = self.almacen.matriz()
        valores = distancias(matriz[identificador], matriz[lista], self.metrica).tolist()
        candidatos = sorted(zip(valores, lista))
        self.vecinos[identificador][capa] = self._seleccionar(candidatos, limite)

    def _descender(self, consulta, entrada, desde, hasta):
        capa = desde
        while capa > hasta:
            entrada = self._explorar(consulta, [entrada], 1, capa)[0][1]
            capa -= 1
        return entrada

    def insertar(self, identificador):
        if identificador in self.vecinos:
            return
        nivel = self._nivel_aleatorio()
        self.vecinos[identificador] = []
        for _ in range(nivel + 1):
            self.vecinos[identificador].append([])
        if self.entrada is None:
            self.entrada = identificador
            self.nivel_maximo = nivel
            return
        consulta = self.almacen.vector(identificador)
        entrada = self._descender(consulta, self.entrada, self.nivel_maximo, nivel)
        entradas = [entrada]
        capa = min(nivel, self.nivel_maximo)
        while capa >= 0:
            candidatos = self._explorar(consulta, entradas, self.ef_construccion, capa)
            elegidos = self._seleccionar(candidatos, self.m)
            self.vecinos[identificador][capa] = elegidos
            for vecino in elegidos:
                self.vecinos[vecino][capa].append(identificador)
                self._recortar(vecino, capa)
            entradas = []
            for _, candidato in candidatos:
                entradas.append(candidato)
            capa -= 1
        if nivel > self.nivel_maximo:
            self.entrada = identificador
            self.nivel_maximo = nivel

    def construir(self):
        for identificador in self.almacen.ids_vivos().tolist():
            self.insertar(identificador)

    def buscar(self, consulta, k, ef_search=None):
        if k <= 0:
            raise ValueError("k debe ser un entero positivo")
        if ef_search is None:
            ef_search = EF_SEARCH
        if ef_search <= 0:
            raise ValueError("ef_search debe ser un entero positivo")
        if self.entrada is None:
            return []
        entrada = self._descender(consulta, self.entrada, self.nivel_maximo, 0)
        vivos = self.almacen.mascara_vivos()
        return self._explorar(consulta, [entrada], max(ef_search, k), 0, vivos)[:k]

    def borrar(self, identificador):
        return

    def sincronizar(self):
        for identificador in self.almacen.ids_vivos().tolist():
            self.insertar(identificador)

    def guardar(self, ruta):
        ids = []
        capas = []
        longitudes = []
        planos = []
        for identificador, listas in self.vecinos.items():
            ids.append(identificador)
            capas.append(len(listas))
            for lista in listas:
                longitudes.append(len(lista))
                planos.extend(lista)
        temporal = ruta + ".tmp"
        with open(temporal, "wb") as archivo:
            np.savez(
                archivo,
                ids=np.array(ids, dtype=np.int64),
                capas=np.array(capas, dtype=np.int64),
                longitudes=np.array(longitudes, dtype=np.int64),
                vecinos=np.array(planos, dtype=np.int64),
                parametros=np.array([self.m, self.ef_construccion, self.semilla, self.nivel_maximo, -1 if self.entrada is None else self.entrada]),
                metrica=np.array(self.metrica),
            )
        os.replace(temporal, ruta)

    @classmethod
    def abrir(cls, almacen, ruta):
        with np.load(ruta) as datos:
            m, ef_construccion, semilla, nivel_maximo, entrada = datos["parametros"].tolist()
            indice = cls(almacen, str(datos["metrica"]), m, ef_construccion, semilla + almacen.total)
            ids = datos["ids"].tolist()
            capas = datos["capas"].tolist()
            longitudes = datos["longitudes"].tolist()
            planos = datos["vecinos"].tolist()
        indice.nivel_maximo = nivel_maximo
        if entrada >= 0:
            indice.entrada = entrada
        posicion_capa = 0
        posicion_vecino = 0
        for identificador, cantidad in zip(ids, capas):
            listas = []
            for _ in range(cantidad):
                longitud = longitudes[posicion_capa]
                listas.append(planos[posicion_vecino:posicion_vecino + longitud])
                posicion_capa += 1
                posicion_vecino += longitud
            indice.vecinos[identificador] = listas
        indice.sincronizar()
        return indice
