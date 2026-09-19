import os
import time

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from engine.catalog import create_catalog, table_info
from engine.parser.scanner import Scanner
from engine.parser.sql_parser import Parser
from engine.parser.executor import Executor
from engine.transactions import TransactionManager
from engine.catalog import StorageTable
from engine.importer import CSVImportError, parse_csv

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


@app.post("/api/tables/import")
async def import_table(
    file: UploadFile = File(...),
    table_name: str = Form(...),
    index_kind: str = Form("HASH"),
    index_field: str = Form(""),
):
    try:
        valid_name = (
            bool(table_name)
            and (table_name[0].isalpha() or table_name[0] == "_")
            and all(char.isalnum() or char == "_" for char in table_name)
        )
        if not valid_name:
            raise CSVImportError("el nombre de tabla no es válido")
        if table_name in catalog:
            raise CSVImportError(f"la tabla '{table_name}' ya existe")
        index_kind = index_kind.upper()
        if index_kind not in ("HASH", "BPLUS", "BPLUS_CLUSTERED"):
            raise CSVImportError("el índice debe ser HASH, BPLUS o BPLUS_CLUSTERED")

        headers, schema, rows = parse_csv(await file.read())
        index_field = index_field or headers[0]
        if index_field not in headers:
            raise CSVImportError(f"la columna índice '{index_field}' no existe")
        table = StorageTable(table_name, schema, DATA_DIR, index_field, index_kind)
        table.bulk_insert(rows)
        catalog[table_name] = table
        return {
            "message": f"tabla '{table_name}' creada e importada correctamente",
            "table": table_info(table),
            "rowsImported": len(rows),
            "schema": [{"name": name, "type": col_type} for name, col_type in schema],
        }
    except (CSVImportError, ValueError, TypeError) as error:
        return {"error": str(error)}
