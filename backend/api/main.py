import os
import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from engine.catalog import create_catalog, table_info
from engine.parser.scanner import Scanner
from engine.parser.sql_parser import Parser
from engine.parser.executor import Executor
from engine.transactions import TransactionManager

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_DIR = os.path.dirname(BACKEND_DIR)
DATA_DIR = os.path.join(PROJECT_DIR, "data", "runtime")

catalog = create_catalog(DATA_DIR)

app = FastAPI(title="MiniGestor BD2")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class QueryBody(BaseModel):
    sql: str


def _tipo(sentencia):
    nombre = type(sentencia).__name__
    if nombre == "Select":
        return "select"
    if nombre == "Insert":
        return "insert"
    if nombre == "Delete":
        return "delete"
    if nombre == "Update":
        return "update"
    if nombre == "CreateTable":
        return "create"
    if nombre == "BeginTransaction":
        return "begin"
    if nombre == "EndTransaction":
        return "end"
    return "unknown"


def _project(columns, rows):
    projected = []
    for row in rows:
        item = {}
        for column in columns:
            item[column] = row[column]
        projected.append(item)
    return projected


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/tables")
def tables():
    salida = []
    for name in catalog:
        salida.append(table_info(catalog[name]))
    return salida


@app.post("/api/query")
def query(body: QueryBody):
    start = time.monotonic()
    try:
        sentencias = Parser(Scanner(body.sql)).parse_program()
    except Exception as error:
        return {"error": str(error), "plan": [], "statements": []}

    executor = Executor(catalog, TransactionManager(), DATA_DIR)
    salidas = executor.run(sentencias)
    elapsed = round((time.monotonic() - start) * 1000, 1)

    statements = []
    for i in range(len(sentencias)):
        salida = salidas[i]
        item = {"type": _tipo(sentencias[i]), "plan": salida["plan"]}
        if "error" in salida:
            item["error"] = salida["error"]
        elif "columns" in salida:
            item["columns"] = salida["columns"]
            item["rows"] = _project(salida["columns"], salida["rows"])
        else:
            item["message"] = salida["message"]
        statements.append(item)

    primero = None
    for item in statements:
        if "error" in item:
            primero = item
            break
    if primero is not None:
        return {"error": primero["error"], "plan": primero["plan"], "statements": statements, "elapsedMs": elapsed}

    respuesta = {"statements": statements, "elapsedMs": elapsed}
    ultimo = statements[-1]
    respuesta["plan"] = ultimo["plan"]
    if "columns" in ultimo:
        respuesta["columns"] = ultimo["columns"]
        respuesta["rows"] = ultimo["rows"]
    else:
        respuesta["message"] = ultimo["message"]
    for item in reversed(statements):
        if "columns" in item:
            respuesta["columns"] = item["columns"]
            respuesta["rows"] = item["rows"]
            break
    return respuesta
