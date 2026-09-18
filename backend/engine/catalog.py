import os
import json

from engine.storage.heap.heapfile import Heapfile
from engine.storage.sequential.sequential_file import SequentialFile
from engine.hashing import ExtendibleHashIndex
from engine.bplus import BPlusTree, ClusteredBPlusTree
from engine.common import as_pair
from engine.common.heap_adapter import heap_fetch, to_heap_rid

STRLEN = 32
PAGE_SIZE = 4096
BLOCK_FACTOR = 32
TABLE_SUFFIX = ".tbl"


class StorageTable:
    def __init__(self, name, schema, data_dir, index_field, index_kind):
        self.name = name
        self.schema = schema
        self.data_dir = data_dir
        self.index_field = index_field
        self.index_column = index_field
        self.index_kind = index_kind

        self.columns = []
        for col, col_type in schema:
            self.columns.append(col)

        record_format = ""
        for col, col_type in schema:
            if col_type == "int":
                record_format += "i"
            elif col_type == "float":
                record_format += "f"
            else:
                record_format += str(STRLEN) + "s"

        self.is_clustered = index_kind == "BPLUS_CLUSTERED"
        key_type = self._key_type(index_field)
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
        self._write_descriptor()

    def _write_descriptor(self):
        columnas = []
        for col, col_type in self.schema:
            columnas.append([col, col_type])
        descriptor = {
            "name": self.name,
            "schema": columnas,
            "index_field": self.index_field,
            "index_kind": self.index_kind,
        }
        path = os.path.join(self.data_dir, self.name + TABLE_SUFFIX)
        with open(path, "w") as f:
            json.dump(descriptor, f)

    def _field_index(self, field):
        for i in range(len(self.schema)):
            if self.schema[i][0] == field:
                return i
        return 0

    def _key_type(self, field):
        for col, col_type in self.schema:
            if col == field:
                if col_type == "int":
                    return "int"
                if col_type == "float":
                    return "float"
                return "str:" + str(STRLEN)
        return "int"

    def _to_tuple(self, row):
        values = []
        for col, col_type in self.schema:
            value = row[col]
            if col_type == "int":
                values.append(int(value))
            elif col_type == "float":
                values.append(float(value))
            else:
                values.append(str(value).encode()[:STRLEN])
        return values

    def _to_dict(self, pair, data):
        row = {}
        for i in range(len(self.schema)):
            col = self.schema[i][0]
            col_type = self.schema[i][1]
            value = data[i]
            if col_type == "str":
                value = value.rstrip(b"\x00").decode()
            row[col] = value
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
            self.index.insert(row[self.index_field], tuple(values))
            return
        rid = self.heap.insert(*values)
        pair = as_pair(rid)
        self.index.insert(row[self.index_field], pair)

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

    def remove(self, rows):
        count = 0
        if self.is_clustered:
            for row in rows:
                if self.index.delete(row[self.index_field]):
                    count += 1
            return count
        for row in rows:
            pair = row.get("__rid__")
            if pair is None:
                continue
            self.heap.delete(to_heap_rid(pair))
            self.index.delete(row[self.index_field], pair)
            count += 1
        return count

    def update_rows(self, rows, assignments):
        total = 0
        for row in rows:
            vieja = row[self.index_field]
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
            total = total + 1
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
        )
        catalogo[descriptor["name"]] = tabla
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
    return {"clientes": clientes, "ventas": ventas, "productos": productos}


def table_info(tabla):
    columns = []
    for col, col_type in tabla.schema:
        columns.append({"name": col, "type": col_type})
    kind = str(tabla.index_kind).upper()
    indexes = [{"field": tabla.index_field, "type": kind}]
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
