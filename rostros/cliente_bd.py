import requests

from config import URL_MOTOR

sesion = requests.Session()


class ErrorMotor(Exception):
    pass


def texto_sql(valor):
    if valor is None:
        return "NULL"
    return "'" + str(valor).replace("'", "''") + "'"


def numero_sql(valor):
    if valor is None:
        return "NULL"
    return str(valor)


def vector_sql(vector):
    partes = []
    for valor in vector:
        partes.append(format(float(valor), ".6g"))
    return "VECTOR(" + ", ".join(partes) + ")"


def lista_sql(valores):
    partes = []
    for valor in valores:
        partes.append(str(int(valor)))
    return "(" + ", ".join(partes) + ")"


def ejecutar(sql, limite=120):
    respuesta = sesion.post(URL_MOTOR + "/api/query", json={"sql": sql}, timeout=limite)
    respuesta.raise_for_status()
    datos = respuesta.json()
    if "error" in datos:
        raise ErrorMotor(datos["error"])
    return datos


def filas(sql):
    return ejecutar(sql).get("rows", [])


def disponible():
    try:
        return sesion.get(URL_MOTOR + "/api/health", timeout=3).ok
    except requests.RequestException:
        return False


def tablas():
    respuesta = sesion.get(URL_MOTOR + "/api/tables", timeout=30)
    respuesta.raise_for_status()
    nombres = set()
    for tabla in respuesta.json():
        nombres.add(tabla["name"])
    return nombres
