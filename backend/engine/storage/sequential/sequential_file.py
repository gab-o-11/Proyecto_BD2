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
        total_records, total_activos, total_eliminados, _, overflow_head = self.read_header()
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
