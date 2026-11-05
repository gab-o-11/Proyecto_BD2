import os
import random
import tempfile

from .catalog import StorageTable, TEXT_SUFFIX
from .storage.text.text_store import TextStore

SCHEMA = [("id", "int"), ("titulo", "str"), ("contenido", "text"), ("resumen", "text")]
DEFINICIONES = {
    "id": {"type": "INT", "size": None, "primary_key": True, "not_null": True},
    "titulo": {"type": "VARCHAR", "size": 20, "primary_key": False, "not_null": False},
    "contenido": {"type": "TEXT", "size": None, "primary_key": False, "not_null": False},
    "resumen": {"type": "TEXT", "size": None, "primary_key": False, "not_null": False},
}
LARGO = "La economía peruana creció según el BCRP; año de señales mixtas. " * 300


def _falla(funcion, caso):
    try:
        funcion()
    except ValueError:
        return
    raise AssertionError(f"debía fallar: {caso}")


def _tabla(carpeta, nombre, tipo="HASH"):
    return StorageTable(nombre, SCHEMA, carpeta, "id", tipo, DEFINICIONES)


def _por_id(tabla):
    filas = {}
    for fila in tabla.scan():
        filas[fila["id"]] = fila
    return filas


def _almacen():
    with tempfile.TemporaryDirectory() as carpeta:
        ruta = os.path.join(carpeta, "textos.txt")
        almacen = TextStore(ruta, page_size=64)
        a = almacen.agregar("hola")
        b = almacen.agregar("ñandú " * 40)
        c = almacen.agregar("")
        assert almacen.leer(*a) == "hola"
        assert almacen.leer(*b) == "ñandú " * 40
        assert almacen.leer(*c) == ""
        assert not almacen.requiere_compactar()
        almacen.marcar_basura(b[1])
        assert almacen.requiere_compactar()
        nuevas = almacen.compactar([a, c])
        assert almacen.leer(nuevas[a[0]], a[1]) == "hola"
        assert almacen.stats()["basura"] == 0
        assert almacen.stats()["usados"] == 4
        assert TextStore(ruta).leer(nuevas[a[0]], a[1]) == "hola"


def _heap():
    with tempfile.TemporaryDirectory() as carpeta:
        tabla = _tabla(carpeta, "noticias")
        tabla.insert({"id": 1, "titulo": "largo", "contenido": LARGO, "resumen": "corto"})
        tabla.insert({"id": 2, "titulo": "nulo", "contenido": None, "resumen": ""})
        tabla.bulk_insert([{"id": 3 + i, "titulo": "t" + str(i), "contenido": "texto " + str(i), "resumen": None} for i in range(50)])
        assert len(LARGO.encode()) > 18000

        filas = _por_id(tabla)
        assert filas[1]["contenido"] == LARGO
        assert filas[1]["resumen"] == "corto"
        assert filas[2]["contenido"] is None
        assert filas[2]["resumen"] == ""
        assert filas[10]["contenido"] == "texto 7"
        assert filas[10]["resumen"] is None
        assert tabla.search("id", 1)[0]["contenido"] == LARGO

        estadisticas = tabla.analyze()["columnas"]
        assert estadisticas["contenido"]["largo_promedio"] > 300
        assert estadisticas["contenido"]["n_distinct"] == 51
        assert tabla.ancho() > 300

        tabla.cerrar()
        reabierta = _tabla(carpeta, "noticias")
        assert _por_id(reabierta)[1]["contenido"] == LARGO

        basura = reabierta.textos.stats()["basura"]
        reabierta.update_rows([_por_id(reabierta)[1]], [("titulo", "otro")])
        assert reabierta.textos.stats()["basura"] == basura
        reabierta.update_rows([_por_id(reabierta)[10]], [("contenido", "cambiado")])
        assert reabierta.textos.stats()["basura"] == basura + len("texto 7")
        reabierta.update_rows([_por_id(reabierta)[11]], [("contenido", None)])
        filas = _por_id(reabierta)
        assert filas[1]["titulo"] == "otro" and filas[1]["contenido"] == LARGO
        assert filas[10]["contenido"] == "cambiado"
        assert filas[11]["contenido"] is None

        reabierta.destruir()
        assert not os.path.exists(os.path.join(carpeta, "noticias" + TEXT_SUFFIX))


def _compactacion(tipo):
    with tempfile.TemporaryDirectory() as carpeta:
        tabla = _tabla(carpeta, "docs", tipo)
        generador = random.Random(7)
        claves = list(range(1, 201))
        generador.shuffle(claves)
        esperado = {}
        for clave in claves:
            fila = {"id": clave, "titulo": "d" + str(clave), "contenido": ("doc " + str(clave) + " ñ ") * generador.randint(1, 80), "resumen": "r" + str(clave)}
            tabla.insert(fila)
            esperado[clave] = fila
        antes = os.path.getsize(tabla.textos.ruta)

        borrar = []
        for fila in tabla.scan():
            if fila["id"] % 3 != 0:
                borrar.append(fila)
        tabla.remove(borrar)
        for fila in borrar:
            del esperado[fila["id"]]

        assert tabla.textos.compactaciones >= 1
        assert os.path.getsize(tabla.textos.ruta) < antes
        assert tabla.textos.stats()["fraccion_basura"] <= 0.30

        filas = _por_id(tabla)
        assert set(filas) == set(esperado)
        for clave, fila in esperado.items():
            assert filas[clave]["contenido"] == fila["contenido"]
            assert filas[clave]["resumen"] == fila["resumen"]

        cambios = []
        for fila in tabla.scan():
            cambios.append(fila)
        tabla.update_rows(cambios, [("contenido", "nuevo")])
        assert tabla.textos.compactaciones >= 2
        for fila in tabla.scan():
            assert fila["contenido"] == "nuevo"
            assert fila["resumen"] == "r" + str(fila["id"])
        tabla.cerrar()
        assert len(_por_id(_tabla(carpeta, "docs", tipo))) == len(esperado)


def _restricciones():
    with tempfile.TemporaryDirectory() as carpeta:
        _falla(lambda: StorageTable("mal", SCHEMA, carpeta, "contenido", "HASH", DEFINICIONES), "TEXT como columna índice")
        tabla = _tabla(carpeta, "ok")
        _falla(lambda: tabla.crear_indice("idx_contenido", "contenido", "BPLUS"), "índice BPLUS sobre TEXT")
        _falla(lambda: tabla.crear_indice("idx_resumen", "resumen", "HASH"), "índice HASH sobre TEXT")
        sin_texto = StorageTable("plana", [("id", "int")], carpeta, "id", "HASH")
        assert sin_texto.textos is None
        assert not os.path.exists(os.path.join(carpeta, "plana" + TEXT_SUFFIX))


def main():
    _almacen()
    _heap()
    _compactacion("HASH")
    _compactacion("BPLUS")
    _compactacion("BPLUS_CLUSTERED")
    _restricciones()
    print("OK: almacén de textos, TEXT en heap, compactación en HASH, BPLUS y BPLUS_CLUSTERED, persistencia y restricciones")


if __name__ == "__main__":
    main()
