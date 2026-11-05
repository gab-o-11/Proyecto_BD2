import json
import os

from ..common.io_stats import touch
from .spimi import DOCUMENTO, ENTRADA, LARGO, POSTING, SUFIJOS

PAGE_SIZE = 4096


class IndiceInvertido:
    def __init__(self, ruta, page_size=PAGE_SIZE):
        self.ruta = ruta
        self.PAGE_SIZE = page_size
        with open(ruta + ".ftmeta") as archivo:
            self.meta = json.load(archivo)
        self.documentos = self.meta["documentos"]
        self.longitud_promedio = self.meta["longitud_promedio"]
        self.lexico = {}
        with open(ruta + ".lex", "rb") as archivo:
            while True:
                cabecera = archivo.read(LARGO.size)
                if not cabecera:
                    break
                termino = archivo.read(LARGO.unpack(cabecera)[0]).decode()
                self.lexico[termino] = ENTRADA.unpack(archivo.read(ENTRADA.size))
        self.rids = []
        self.longitudes = []
        self.normas = []
        with open(ruta + ".docs", "rb") as archivo:
            for pagina, slot, longitud, norma in DOCUMENTO.iter_unpack(archivo.read()):
                self.rids.append((pagina, slot))
                self.longitudes.append(longitud)
                self.normas.append(norma)

    def df(self, termino):
        entrada = self.lexico.get(termino)
        return 0 if entrada is None else entrada[0]

    def postings(self, termino):
        entrada = self.lexico.get(termino)
        if entrada is None:
            return []
        cantidad, offset = entrada
        largo = cantidad * POSTING.size
        primera = offset // self.PAGE_SIZE
        ultima = (offset + max(largo, 1) - 1) // self.PAGE_SIZE
        for pagina in range(primera, ultima + 1):
            touch(self.ruta + ".post", pagina)
        with open(self.ruta + ".post", "rb") as archivo:
            archivo.seek(offset)
            return list(POSTING.iter_unpack(archivo.read(largo)))

    def rid(self, doc):
        return self.rids[doc]

    def bytes_en_disco(self):
        total = 0
        for sufijo in SUFIJOS:
            if os.path.exists(self.ruta + sufijo):
                total += os.path.getsize(self.ruta + sufijo)
        return total
