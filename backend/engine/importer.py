import csv
import io
import re


IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class CSVImportError(Exception):
    pass


def _infer_type(values):
    values = [value.strip() for value in values if value.strip()]
    if not values:
        return "str"
    try:
        for value in values:
            int(value)
        return "int"
    except ValueError:
        pass
    try:
        for value in values:
            float(value)
        return "float"
    except ValueError:
        return "str"


def _convert(value, col_type, row_number, column):
    value = value.strip()
    if not value:
        raise CSVImportError(f"fila {row_number}, columna '{column}': valor vacío")
    try:
        if col_type == "int":
            converted = int(value)
            if not -(2**31) <= converted <= 2**31 - 1:
                raise CSVImportError(f"fila {row_number}, columna '{column}': entero fuera de rango")
            return converted
        if col_type == "float":
            return float(value)
        if len(value.encode("utf-8")) > 32:
            raise CSVImportError(f"fila {row_number}, columna '{column}': texto mayor a 32 bytes")
        return value
    except ValueError as error:
        raise CSVImportError(
            f"fila {row_number}, columna '{column}': '{value}' no es {col_type}"
        ) from error


def parse_csv(content):
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise CSVImportError("el CSV debe estar codificado en UTF-8") from error
    reader = csv.reader(io.StringIO(text))
    try:
        headers = [header.strip() for header in next(reader)]
    except StopIteration as error:
        raise CSVImportError("el CSV está vacío") from error
    if not headers or any(not header for header in headers):
        raise CSVImportError("el encabezado debe contener nombres de columna")
    if any(not IDENTIFIER.match(header) for header in headers):
        raise CSVImportError("los nombres de columna solo pueden usar letras, números y '_'")
    if len(set(headers)) != len(headers):
        raise CSVImportError("el CSV contiene columnas repetidas")

    raw_rows = []
    for row_number, row in enumerate(reader, start=2):
        if not row or all(not value.strip() for value in row):
            continue
        if len(row) != len(headers):
            raise CSVImportError(
                f"fila {row_number}: se esperaban {len(headers)} columnas y hay {len(row)}"
            )
        raw_rows.append((row_number, row))
    if not raw_rows:
        raise CSVImportError("el CSV no contiene registros")

    schema = [
        (header, _infer_type([row[index] for _, row in raw_rows]))
        for index, header in enumerate(headers)
    ]
    rows = []
    for row_number, row in raw_rows:
        converted = {}
        for (column, col_type), value in zip(schema, row):
            converted[column] = _convert(value, col_type, row_number, column)
        rows.append(converted)
    return headers, schema, rows
