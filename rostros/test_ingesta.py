import numpy as np

import cliente_bd as bd
import lfw
from ingesta import armar, recortar


def _formato_sql():
    assert bd.texto_sql("O'Brien") == "'O''Brien'"
    assert bd.texto_sql(None) == "NULL"
    assert bd.numero_sql(7) == "7"
    assert bd.numero_sql(None) == "NULL"
    assert bd.vector_sql(np.array([0.5, -1.0, 1e-7], dtype=np.float32)) == "VECTOR(0.5, -1, 1e-07)"
    assert bd.lista_sql([3, 1]) == "(3, 1)"


def _nombres():
    assert lfw.persona_de("George_W_Bush_0001.jpg") == "George_W_Bush"
    assert lfw.nombre_visible("George_W_Bush") == "George W Bush"
    assert recortar("ñ" * 40) == "ñ" * 30
    assert len(recortar("a" * 80)) == 60


def _armar():
    fotos_lfw = [
        {"archivo": "Ana_Diaz_0001.jpg", "persona": "Ana_Diaz", "datos": b"a"},
        {"archivo": "Ana_Diaz_0002.jpg", "persona": "Ana_Diaz", "datos": b"b"},
        {"archivo": "Luis_Paz_0001.jpg", "persona": "Luis_Paz", "datos": b"c"},
    ]
    propias = [{"archivo": "1.jpg", "persona": "Javier", "datos": b"d"}]
    personas, rostros = armar([
        ("lfw", fotos_lfw, np.eye(3, 4, dtype=np.float32), np.array([True, False, True])),
        ("propia", propias, np.ones((1, 4), dtype=np.float32), np.array([True])),
    ])
    assert personas == [
        {"id": 1, "nombre": "Ana Diaz", "origen": "lfw"},
        {"id": 2, "nombre": "Luis Paz", "origen": "lfw"},
        {"id": 3, "nombre": "Javier", "origen": "propia"},
    ]
    resumen = []
    for rostro in rostros:
        resumen.append((rostro["id"], rostro["persona_id"], rostro["archivo"]))
    assert resumen == [
        (1, 1, "lfw/Ana_Diaz/Ana_Diaz_0001.jpg"),
        (2, 2, "lfw/Luis_Paz/Luis_Paz_0001.jpg"),
        (3, 3, "propias/3/3.jpg"),
    ]


def main():
    _formato_sql()
    _nombres()
    _armar()
    print("OK: formato SQL, nombres de LFW y armado de filas")


if __name__ == "__main__":
    main()
