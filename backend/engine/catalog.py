import os
import json
import struct

from engine.storage.heap.heapfile import Heapfile
from engine.storage.sequential.sequential_file import SequentialFile
from engine.hashing import ExtendibleHashIndex
from engine.bplus import BPlusTree, ClusteredBPlusTree
from engine.spatial_table import SpatialTable
from engine.common import as_pair
from engine.common.heap_adapter import heap_fetch, to_heap_rid

STRLEN = 32
PAGE_SIZE = 4096
BLOCK_FACTOR = 32
TABLE_SUFFIX = ".tbl"
STATS_SUFFIX = ".stats"
AUTOANALYZE_BASE = 50
AUTOANALYZE_FACTOR = 0.1


class StorageTable(SpatialTable):
    def __init__(self, name, schema, data_dir, index_field, index_kind, column_definitions=None):
        self.name = name
        self._init_spatial()
        self.schema = schema
        self.data_dir = data_dir
        self.index_field = index_field
        self.index_column = index_field
        self.index_kind = index_kind
        self.column_definitions = column_definitions or {}
        self.column_types = {name: definition["type"] for name, definition in self.column_definitions.items()}

        self.columns = []
        for col, col_type in schema:
            self.columns.append(col)

        record_format = ""
        for col, col_type in schema:
            if col_type == "int":
                record_format += "i"
            elif col_type == "float":
                record_format += "f"
            elif col_type == "point":
                record_format += "dd"
            else:
                record_format += str(self._string_size(col)) + "s"

        self.is_clustered = index_kind == "BPLUS_CLUSTERED"
        key_type = self._key_type(index_field)
        self.key_kind = key_type
        index_path = os.path.join(data_dir, name + "_" + index_field)
        if self.is_clustered:
            key_index = self._field_index(index_field)
            seq_path = os.path.join(data_dir, name + ".seq")
            self.seq = SequentialFile(seq_path, record_format, key_index=key_index, page_size=PAGE_SIZE)
            self.index = ClusteredBPlusTree(index_path, self.seq, key_type=key_type, block_factor=BLOCK_FACTOR)
            self.heap = None
        else:
            heap_path = os.path.join(data_dir, name + ".dat")
            self.heap = Heapfile(heap_path, page_size=PAGE_SIZE, record_format=record_format)
            if index_kind == "HASH":
                self.index = ExtendibleHashIndex(index_path, key_type=key_type, block_factor=BLOCK_FACTOR)
            else:
                self.index = BPlusTree(index_path, key_type=key_type, block_factor=BLOCK_FACTOR)
            self.seq = None
        self.record_format = record_format
        self.stats_path = os.path.join(data_dir, name + STATS_SUFFIX)
        self.estadisticas = self._leer_estadisticas()
        self._write_descriptor()
        self._abrir_indices_espaciales([col for col, col_type in schema if col_type == "point"])

    def _leer_estadisticas(self):
        if not os.path.exists(self.stats_path):
            return None
        with open(self.stats_path) as f:
            return json.load(f)

    def _guardar_estadisticas(self):
        with open(self.stats_path, "w") as f:
            json.dump(self.estadisticas, f)

    def filas_totales(self):
        if self.is_clustered:
            return self.seq.stats()["active"]
        return self.heap.read_file_header()[2]

    def paginas(self):
        if self.is_clustered:
            return self.seq.stats()["num_pages"]
        return self.heap.read_file_header()[1]

    def ancho(self):
        return struct.calcsize(self.record_format)

    def filas_por_pagina(self):
        if self.is_clustered:
            return self.seq.SLOTS_PER_PAGE
        return self.heap.SLOT_PER_PAGE

    def altura_indice(self):
        if self.is_clustered:
            return self.index.tree.height
        if self.index_kind == "HASH":
            return 1
        return self.index.height

    def analyze(self):
        valores = {}
        for col, col_type in self.schema:
            valores[col] = []
        total = 0
        for row in self._iter_rows():
            total += 1
            for col, col_type in self.schema:
                valores[col].append(row[col])
        columnas = {}
        for col, col_type in self.schema:
            datos = valores[col]
            info = {"n_distinct": len(set(datos)), "min": None, "max": None}
            if datos and col_type == "point":
                latitudes = [dato[0] for dato in datos]
                longitudes = [dato[1] for dato in datos]
                info["bbox"] = [min(latitudes), min(longitudes), max(latitudes), max(longitudes)]
            elif datos:
                info["min"] = min(datos)
                info["max"] = max(datos)
            columnas[col] = info
        self.estadisticas = {
            "filas": total,
            "paginas": self.paginas(),
            "columnas": columnas,
            "cambios": 0,
        }
        self._guardar_estadisticas()
        return self.estadisticas

    def registrar_cambios(self, cantidad):
        if cantidad <= 0:
            return
        if self.estadisticas is None:
            self.estadisticas = {"filas": 0, "paginas": 0, "columnas": {}, "cambios": 0}
        self.estadisticas["cambios"] = self.estadisticas.get("cambios", 0) + cantidad
        self._guardar_estadisticas()

    def autoanalyze(self):
        if self.estadisticas is None:
            return False
        umbral = AUTOANALYZE_BASE + AUTOANALYZE_FACTOR * self.estadisticas["filas"]
        if self.estadisticas.get("cambios", 0) > umbral:
            self.analyze()
            return True
        return False

    def _write_descriptor(self):
        columnas = []
        for col, col_type in self.schema:
            columnas.append([col, col_type])
        descriptor = {
            "name": self.name,
            "schema": columnas,
            "index_field": self.index_field,
            "index_kind": self.index_kind,
            "column_definitions": self.column_definitions,
        }
        path = os.path.join(self.data_dir, self.name + TABLE_SUFFIX)
        with open(path, "w") as f:
            json.dump(descriptor, f)

    def _field_index(self, field):
        offset = 0
        for col, col_type in self.schema:
            if col == field:
                return offset
            offset += 2 if col_type == "point" else 1
        return 0

    def _string_size(self, field):
        size = self.column_definitions.get(field, {}).get("size")
        return STRLEN if size is None else size * 4

    def _key_type(self, field):
        for col, col_type in self.schema:
            if col == field:
                if col_type == "int":
                    return "int"
                if col_type == "float":
                    return "float"
                return "str:" + str(self._string_size(field))
        return "int"

    def _to_tuple(self, row):
        values = []
        for col, col_type in self.schema:
            value = row[col]
            if col_type == "int":
                values.append(int(value))
            elif col_type == "float":
                values.append(float(value))
            elif col_type == "point":
                values.extend(value)
            else:
                values.append(str(value).encode()[:self._string_size(col)])
        return values

    def _to_dict(self, pair, data):
        row = {}
        offset = 0
        for col, col_type in self.schema:
            value = data[offset]
            if col_type == "point":
                value = tuple(data[offset:offset + 2])
            if col_type == "str":
                value = value.rstrip(b"\x00").decode()
            row[col] = value
            offset += 2 if col_type == "point" else 1
        row["__rid__"] = pair
        return row

    def _iter_rows(self):
        if self.is_clustered:
            for position, fields in self.seq._ordered_with_pos():
                yield self._to_dict(position, fields)
            return
        page_size, total_pages, total_records, first_id = self.heap.read_file_header()
        for page_id in range(1, total_pages + 1):
            page_id_leido, num_reg, reg_act, free_list = self.heap.read_page_header(page_id)
            for slot_id in range(num_reg):
                data = heap_fetch(self.heap, (page_id, slot_id))
                if data is None:
                    continue
                yield self._to_dict((page_id, slot_id), data)

    def insert(self, row):
        values = self._to_tuple(row)
        if self.is_clustered:
            reorganizaciones = self.seq.reorganizations
            position = self.index.insert(row[self.index_field], tuple(values))
            if self.seq.reorganizations != reorganizaciones:
                self.reconstruir_indices_espaciales()
            else:
                self._spatial_insert(dict(row, __rid__=position))
            return
        rid = self.heap.insert(*values)
        pair = as_pair(rid)
        self.index.insert(row[self.index_field], pair)
        self._spatial_insert(dict(row, __rid__=pair))

    def bulk_insert(self, rows):
        rows = list(rows)
        if self.is_clustered:
            values = [tuple(self._to_tuple(row)) for row in rows]
            self.seq.bulk_load(values)
            self.index.rebuild()
        else:
            pairs = []
            for row in rows:
                rid = self.heap.insert(*self._to_tuple(row))
                pairs.append((row[self.index_field], as_pair(rid)))
            self.index.bulk_load(pairs)
        self.reconstruir_indices_espaciales()
        self.analyze()
        return len(rows)

    def _ruta_rtree(self, column):
        return os.path.join(self.data_dir, self.name + "_" + column + "_rtree")

    @staticmethod
    def spatial_id(row):
        return row["__rid__"]

    def spatial_row(self, rid):
        if self.is_clustered:
            data = self.seq._fields(self.seq.read_record(rid))
        else:
            data = heap_fetch(self.heap, rid)
        return None if data is None else self._to_dict(rid, data)

    def scan(self):
        result = []
        for row in self._iter_rows():
            result.append(row)
        return result

    def search(self, column, value):
        result = []
        if self.is_clustered:
            for position, fields in self.index.search_with_pos(value):
                result.append(self._to_dict(position, fields))
            return result
        for pair in self.index.search(value):
            data = heap_fetch(self.heap, pair)
            if data is None:
                continue
            result.append(self._to_dict(pair, data))
        return result

    def search_range(self, op, value):
        if self.key_kind not in ("int", "float"):
            return None
        if self.index_kind == "HASH":
            return None
        if op in (">", ">="):
            low = value
            high = float("inf")
        else:
            low = float("-inf")
            high = value
        idx = self._field_index(self.index_field)
        result = []
        for pair, data in self._range_pairs(low, high):
            key = data[idx]
            if op == ">" and key == value:
                continue
            if op == "<" and key == value:
                continue
            result.append(self._to_dict(pair, data))
        return result

    def _range_pairs(self, low, high):
        pares = []
        if self.is_clustered:
            for key, fields in self.index.range_search(low, high):
                pares.append((key, fields))
            return pares
        for key, pair in self.index.range_search(low, high):
            data = heap_fetch(self.heap, pair)
            if data is None:
                continue
            pares.append((as_pair(pair), data))
        return pares

    def remove(self, rows):
        count = 0
        if self.is_clustered:
            reorganizaciones = self.seq.reorganizations
            for row in rows:
                if "__rid__" in row:
                    self._spatial_remove(row)
                if self.index.delete(row[self.index_field]):
                    count += 1
            if self.seq.reorganizations != reorganizaciones:
                self.reconstruir_indices_espaciales()
            return count
        for row in rows:
            pair = row.get("__rid__")
            if pair is None:
                continue
            self._spatial_remove(row)
            self.heap.delete(to_heap_rid(pair))
            self.index.delete(row[self.index_field], pair)
            count += 1
        return count

    def update_rows(self, rows, assignments):
        total = 0
        for row in rows:
            vieja = row[self.index_field]
            if not self.is_clustered:
                self._spatial_remove(row)
            for columna, valor in assignments:
                row[columna] = valor
            values = tuple(self._to_tuple(row))
            if self.is_clustered:
                self.seq.update(vieja, values)
                if row[self.index_field] != vieja:
                    self.index.rebuild()
            else:
                self.heap.update(to_heap_rid(row["__rid__"]), values)
                if row[self.index_field] != vieja:
                    self.index.delete(vieja, row["__rid__"])
                    self.index.insert(row[self.index_field], row["__rid__"])
                self._spatial_insert(row)
            total = total + 1
        if self.is_clustered and self.spatial_indexes:
            self.reconstruir_indices_espaciales()
        return total

    def count(self):
        total = 0
        for row in self._iter_rows():
            total += 1
        return total


NOMBRES = [
    "Ana", "Beto", "Caro", "Dora", "Elin", "Fabio", "Gina", "Hugo", "Iris", "Juan",
    "Kira", "Leo", "Mia", "Nico", "Olga", "Pablo", "Rosa", "Saul", "Tina", "Ugo",
    "Vera", "Wes", "Xime", "Yago",
]
CIUDADES = ["Lima", "Cusco", "Arequipa", "Trujillo", "Piura"]
CATEGORIAS = ["A", "B", "C"]
PRODUCTOS = ["Teclado", "Mouse", "Monitor", "Laptop", "Cable", "Webcam", "Router", "SSD", "RAM", "GPU"]


def _seed_clientes(tabla):
    for i in range(24):
        tabla.insert({
            "id": i + 1,
            "nombre": NOMBRES[i],
            "ciudad": CIUDADES[i % len(CIUDADES)],
            "edad": 18 + ((i + 1) * 7) % 43,
        })


def _seed_ventas(tabla):
    for i in range(40):
        tabla.insert({
            "id": i + 1,
            "cliente_id": 1 + ((i + 1) * 5) % 24,
            "monto": 100 + ((i + 1) * 137) % 900,
            "categoria": CATEGORIAS[(i + 1) % 3],
        })


def _seed_productos(tabla):
    for i in range(30):
        pid = ((i * 7) % 30) + 1
        tabla.insert({
            "id": pid,
            "nombre": PRODUCTOS[pid % len(PRODUCTOS)],
            "precio": float(50 + (pid * 37) % 950),
            "stock": (pid * 13) % 200,
        })


def _load_tables(data_dir):
    catalogo = {}
    nombres = os.listdir(data_dir)
    nombres.sort()
    for archivo in nombres:
        if not archivo.endswith(TABLE_SUFFIX):
            continue
        with open(os.path.join(data_dir, archivo)) as f:
            descriptor = json.load(f)
        schema = []
        for par in descriptor["schema"]:
            schema.append((par[0], par[1]))
        tabla = StorageTable(
            descriptor["name"],
            schema,
            data_dir,
            descriptor["index_field"],
            descriptor["index_kind"],
            descriptor.get("column_definitions"),
        )
        catalogo[descriptor["name"]] = tabla
    for tabla in catalogo.values():
        if tabla.estadisticas is None:
            tabla.analyze()
    return catalogo


def create_catalog(data_dir):
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)

    existentes = _load_tables(data_dir)
    if existentes:
        return existentes

    clientes = StorageTable(
        "clientes",
        [("id", "int"), ("nombre", "str"), ("ciudad", "str"), ("edad", "int")],
        data_dir,
        index_field="id",
        index_kind="HASH",
    )
    ventas = StorageTable(
        "ventas",
        [("id", "int"), ("cliente_id", "int"), ("monto", "int"), ("categoria", "str")],
        data_dir,
        index_field="id",
        index_kind="BPLUS",
    )
    productos = StorageTable(
        "productos",
        [("id", "int"), ("nombre", "str"), ("precio", "float"), ("stock", "int")],
        data_dir,
        index_field="id",
        index_kind="BPLUS_CLUSTERED",
    )
    if clientes.count() == 0:
        _seed_clientes(clientes)
    if ventas.count() == 0:
        _seed_ventas(ventas)
    if productos.count() == 0:
        _seed_productos(productos)
    for tabla in (clientes, ventas, productos):
        tabla.analyze()
    return {"clientes": clientes, "ventas": ventas, "productos": productos}


def table_info(tabla):
    columns = []
    for col, col_type in tabla.schema:
        columns.append({"name": col, "type": col_type})
    kind = str(tabla.index_kind).upper()
    indexes = [{"field": tabla.index_field, "type": kind}]
    indexes.extend({"field": col, "type": "RTREE"} for col, typ in tabla.schema if typ == "point")
    storage = "sequential"
    if not tabla.is_clustered:
        storage = "heap"
    return {
        "name": tabla.name,
        "columns": columns,
        "indexes": indexes,
        "rows": tabla.count(),
        "storage": storage,
    }
