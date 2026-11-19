import cliente_bd as bd
from config import DIMENSION, LARGO_NOMBRE, TABLA_PERSONAS, TABLA_ROSTROS


def nombres_indices(tabla_rostros):
    return f"hnsw_{tabla_rostros}", f"hash_{tabla_rostros}_persona"


def existen(tabla_personas=TABLA_PERSONAS, tabla_rostros=TABLA_ROSTROS):
    tablas = bd.tablas()
    return tabla_personas in tablas or tabla_rostros in tablas


def borrar(tabla_personas=TABLA_PERSONAS, tabla_rostros=TABLA_ROSTROS):
    bd.ejecutar(f"DROP TABLE IF EXISTS {tabla_rostros}; DROP TABLE IF EXISTS {tabla_personas};")


def crear_tablas(tabla_personas=TABLA_PERSONAS, tabla_rostros=TABLA_ROSTROS):
    bd.ejecutar(
        f"CREATE TABLE {tabla_personas} (id INT PRIMARY KEY, nombre VARCHAR({LARGO_NOMBRE}), origen VARCHAR(10)); "
        f"CREATE TABLE {tabla_rostros} (id INT PRIMARY KEY, persona_id INT, archivo VARCHAR(120), emb VECTOR({DIMENSION}));"
    )


def crear_indices(tabla_rostros=TABLA_ROSTROS):
    vectorial, persona = nombres_indices(tabla_rostros)
    bd.ejecutar(
        f"CREATE INDEX {vectorial} ON {tabla_rostros} (emb) USING HNSW WITH (METRIC=cosine); "
        f"CREATE INDEX {persona} ON {tabla_rostros} (persona_id) USING HASH;"
    )
