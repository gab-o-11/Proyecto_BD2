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


def _plan_steps(plan):
    steps = []
    for line in plan:
        steps.append({"op": line})
    return steps


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
        return {"error": str(error)}

    executor = Executor(catalog, TransactionManager())
    salidas = executor.run(sentencias)
    elapsed = round((time.monotonic() - start) * 1000, 1)

    for salida in salidas:
        if "error" in salida:
            return {"error": salida["error"], "plan": _plan_steps(salida["plan"])}

    ultima = salidas[-1]
    respuesta = {"plan": _plan_steps(ultima["plan"]), "elapsedMs": elapsed}
    if "columns" in ultima:
        respuesta["columns"] = ultima["columns"]
        respuesta["rows"] = _project(ultima["columns"], ultima["rows"])
    else:
        respuesta["message"] = ultima["message"]
    return respuesta
