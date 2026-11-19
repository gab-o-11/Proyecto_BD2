import requests

from config import URL_MOTOR


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


def ejecutar(sql):
    respuesta = requests.post(URL_MOTOR + "/api/query", json={"sql": sql}, timeout=1800)
    respuesta.raise_for_status()
    datos = respuesta.json()
    if "error" in datos:
        raise ErrorMotor(datos["error"])
    return datos


def filas(sql):
    return ejecutar(sql).get("rows", [])


def tablas():
    respuesta = requests.get(URL_MOTOR + "/api/tables", timeout=60)
    respuesta.raise_for_status()
    return respuesta.json()


def disponible():
    try:
        respuesta = requests.get(URL_MOTOR + "/api/health", timeout=5)
        return respuesta.status_code == 200
    except requests.RequestException:
        return False
