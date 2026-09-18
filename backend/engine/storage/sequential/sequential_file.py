import os
import struct


class SequentialFile:
    FILE_HEADER_FORMAT = "iiiii"  # total_registros, total_activos, total_eliminados, record_size, overflow_head

    def __init__(self, filename, record_format, key_index=0, overflow_limit=3):
        self.filename = filename
        self.RECORD_FORMAT = record_format
        self.key_index = key_index
        self.overflow_limit = overflow_limit
        self.RECORD_WITH_POINTER_FORMAT = self.RECORD_FORMAT + "i"
        self.RECORD_SIZE = struct.calcsize(self.RECORD_FORMAT)
        self.RECORD_WITH_POINTER_SIZE = struct.calcsize(self.RECORD_WITH_POINTER_FORMAT)
        self.FILE_HEADER_SIZE = struct.calcsize(self.FILE_HEADER_FORMAT)

        if not os.path.exists(filename) or os.path.getsize(filename) == 0:
            self.nuevo_archivo()

    def nuevo_archivo(self):
        with open(self.filename, "wb") as f:
            f.write(struct.pack(self.FILE_HEADER_FORMAT, 0, 0, 0, self.RECORD_WITH_POINTER_SIZE, -1))

    def read_header(self):
        with open(self.filename, "rb") as f:
            data = f.read(self.FILE_HEADER_SIZE)
            if len(data) != self.FILE_HEADER_SIZE:
                raise ValueError("Header del archivo corrupto o vacío")
            total_records, total_activos, total_eliminados, record_size, overflow_head = struct.unpack(
                self.FILE_HEADER_FORMAT, data
            )
            return total_records, total_activos, total_eliminados, record_size, overflow_head

    def write_header(self, total_records, total_activos, total_eliminados, record_size, overflow_head):
        with open(self.filename, "r+b") as f:
            f.seek(0)
            f.write(struct.pack(
                self.FILE_HEADER_FORMAT,
                total_records,
                total_activos,
                total_eliminados,
                record_size,
                overflow_head,
            ))

    def read_record(self, position):
        with open(self.filename, "rb") as f:
            offset = self.FILE_HEADER_SIZE + position * self.RECORD_WITH_POINTER_SIZE
            f.seek(offset)
            raw = f.read(self.RECORD_WITH_POINTER_SIZE)
            if len(raw) != self.RECORD_WITH_POINTER_SIZE:
                return None
            return struct.unpack(self.RECORD_WITH_POINTER_FORMAT, raw)

    def write_record(self, position, record_tuple):
        with open(self.filename, "r+b") as f:
            offset = self.FILE_HEADER_SIZE + position * self.RECORD_WITH_POINTER_SIZE
            f.seek(offset)
            f.write(struct.pack(self.RECORD_WITH_POINTER_FORMAT, *record_tuple))

    def get_key(self, record):
        return record[self.key_index]

    def insert(self, record):
        record = tuple(record)
        total_records, total_activos, total_eliminados, record_size, overflow_head = self.read_header()
        new_position = total_records
        self.write_record(new_position, record + (overflow_head,))
        overflow_head = new_position
        total_records += 1
        total_activos += 1

        self.write_header(
            total_records,
            total_activos,
            total_eliminados,
            self.RECORD_WITH_POINTER_SIZE,
            overflow_head,
        )

        return new_position

    def convertir_a_vacio(self, value):
        if isinstance(value, (bytes, bytearray)):
            return b""
        if isinstance(value, str):
            return ""
        if isinstance(value, float):
            return 0.0
        return 0

    def tombstone(self, data):
        return tuple(self.convertir_a_vacio(v) for v in data)

    def is_deleted(self, data):
        if not data:
            return False
        return all(
            (isinstance(v, str) and v == "") or
            (isinstance(v, (bytes, bytearray)) and v == b"") or
            (isinstance(v, float) and v == 0.0) or
            (not isinstance(v, (str, bytes, bytearray, float)) and v == 0)
            for v in data
        )

    def delete(self, key):
        total_records, total_activos, total_eliminados, record_size, overflow_head = self.read_header()
        if total_records == 0:
            return False

        previous_overflow = None
        current_overflow = overflow_head
        seen = set()
        while current_overflow != -1 and current_overflow not in seen:
            seen.add(current_overflow)
            raw = self.read_record(current_overflow)
            if raw is None:
                break
            data = raw[:-1]
            next_pointer = raw[-1]
            if data[self.key_index] == key:
                if previous_overflow is None:
                    overflow_head = next_pointer
                else:
                    previous_raw = self.read_record(previous_overflow)
                    if previous_raw is not None:
                        previous_data = previous_raw[:-1]
                        self.write_record(previous_overflow, previous_data + (next_pointer,))
                self.write_record(current_overflow, self.tombstone(data) + (-1,))
                total_activos -= 1
                total_eliminados += 1
                self.write_header(
                    total_records,
                    total_activos,
                    total_eliminados,
                    self.RECORD_WITH_POINTER_SIZE,
                    overflow_head,
                )
                return True
            
            previous_overflow = current_overflow
            current_overflow = next_pointer

        for position in range(total_records):
            if position in seen:
                continue
            raw = self.read_record(position)
            if raw is None:
                continue
            data = raw[:-1]
            if data[self.key_index] == key:
                self.write_record(position, self.tombstone(data) + (-1,))
                total_activos -= 1
                total_eliminados += 1
                self.write_header(
                    total_records,
                    total_activos,
                    total_eliminados,
                    self.RECORD_WITH_POINTER_SIZE,
                    overflow_head,
                )
                return True
        return False

    def search(self, key):
        total_records, total_activos, total_eliminados, record_size, overflow_head = self.read_header()
        if total_records == 0:
            return None
        
        seen = set()
        for position in range(total_records):
            raw = self.read_record(position)
            if raw is None:
                continue
            data = raw[:-1]
            if self.is_deleted(data):
                continue
            if position in seen:
                continue
            if data[self.key_index] == key:
                return data
        current = overflow_head
        while current != -1 and current not in seen:
            seen.add(current)
            raw = self.read_record(current)
            if raw is None:
                break
            data = raw[:-1]
            if self.is_deleted(data):
                current = raw[-1]
                continue
            if data[self.key_index] == key:
                return data
            current = raw[-1]
        return None
