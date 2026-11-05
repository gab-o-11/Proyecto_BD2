import os
import struct

from engine.common.io_stats import touch

HEADER_FORMAT = "QQ"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)
UMBRAL_BASURA = 0.30


class TextStore:
    def __init__(self, ruta, page_size=4096, umbral=UMBRAL_BASURA):
        self.ruta = ruta
        self.PAGE_SIZE = page_size
        self.umbral = umbral
        self.compactaciones = 0
        if not os.path.exists(ruta) or os.path.getsize(ruta) < HEADER_SIZE:
            with open(ruta, "wb") as f:
                f.write(struct.pack(HEADER_FORMAT, 0, 0))

    def _tocar(self, offset, longitud):
        primera = offset // self.PAGE_SIZE
        ultima = (offset + max(longitud, 1) - 1) // self.PAGE_SIZE
        for pagina in range(primera, ultima + 1):
            touch(self.ruta, pagina)

    def leer_header(self):
        touch(self.ruta, 0)
        with open(self.ruta, "rb") as f:
            return struct.unpack(HEADER_FORMAT, f.read(HEADER_SIZE))

    def escribir_header(self, usados, basura):
        touch(self.ruta, 0)
        with open(self.ruta, "r+b") as f:
            f.write(struct.pack(HEADER_FORMAT, usados, basura))

    def agregar(self, texto):
        datos = texto.encode()
        usados, basura = self.leer_header()
        with open(self.ruta, "r+b") as f:
            f.seek(0, os.SEEK_END)
            offset = f.tell()
            f.write(datos)
        self._tocar(offset, len(datos))
        self.escribir_header(usados + len(datos), basura)
        return offset, len(datos)

    def leer(self, offset, longitud):
        if longitud == 0:
            return ""
        self._tocar(offset, longitud)
        with open(self.ruta, "rb") as f:
            f.seek(offset)
            datos = f.read(longitud)
        if len(datos) != longitud:
            raise ValueError(f"referencia de texto fuera del archivo: ({offset}, {longitud})")
        return datos.decode()

    def marcar_basura(self, longitud):
        if longitud == 0:
            return
        usados, basura = self.leer_header()
        self.escribir_header(usados, min(usados, basura + longitud))

    def requiere_compactar(self):
        usados, basura = self.leer_header()
        return usados > 0 and basura > self.umbral * usados

    def compactar(self, referencias):
        temporal = self.ruta + ".tmp"
        nuevas = {}
        usados = 0
        with open(self.ruta, "rb") as origen, open(temporal, "wb") as destino:
            destino.write(struct.pack(HEADER_FORMAT, 0, 0))
            for offset, longitud in sorted(set(referencias)):
                if longitud == 0:
                    continue
                self._tocar(offset, longitud)
                origen.seek(offset)
                datos = origen.read(longitud)
                if len(datos) != longitud:
                    raise ValueError(f"referencia de texto fuera del archivo: ({offset}, {longitud})")
                nuevas[offset] = destino.tell()
                self._tocar(nuevas[offset], longitud)
                destino.write(datos)
                usados += longitud
            destino.seek(0)
            destino.write(struct.pack(HEADER_FORMAT, usados, 0))
        os.replace(temporal, self.ruta)
        self.compactaciones += 1
        return nuevas

    def stats(self):
        usados, basura = self.leer_header()
        return {
            "bytes": os.path.getsize(self.ruta),
            "usados": usados,
            "basura": basura,
            "fraccion_basura": basura / usados if usados else 0.0,
            "compactaciones": self.compactaciones,
        }

    def destruir(self):
        for ruta in (self.ruta, self.ruta + ".tmp"):
            if os.path.exists(ruta):
                os.remove(ruta)
