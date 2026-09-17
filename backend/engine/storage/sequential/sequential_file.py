import os
import struct


class SequentialFile:
    FILE_HEADER_FORMAT = "iiii" # total_registros, total_activos, total_eliminados, record_size

    def __init__(self, filename, record_format, key_index=0):
        self.filename = filename
        self.RECORD_FORMAT = record_format
        self.key_index = key_index
        self.RECORD_FLAG_FORMAT = self.RECORD_FORMAT + "b"
        self.RECORD_FLAG_SIZE = struct.calcsize(self.RECORD_FLAG_FORMAT)
        self.RECORD_SIZE = struct.calcsize(self.RECORD_FORMAT)
        self.FILE_HEADER_SIZE = struct.calcsize(self.FILE_HEADER_FORMAT)

        if not os.path.exists(filename) or os.path.getsize(filename) == 0:
            self.nuevo_archivo()

    def nuevo_archivo(self):
        with open(self.filename, "wb") as f:
            f.write(struct.pack(self.FILE_HEADER_FORMAT, 0, 0, 0, self.RECORD_FLAG_SIZE))

    def read_header(self):
        with open(self.filename, "rb") as f:
            data = f.read(self.FILE_HEADER_SIZE)
            if len(data) != self.FILE_HEADER_SIZE:
                raise ValueError("Header del archivo corrupto o vacío")
            total_records, total_activos, total_eliminados, record_size = struct.unpack(
                self.FILE_HEADER_FORMAT, data
            )
            return total_records, total_activos, total_eliminados, record_size

    def write_header(self, total_records, total_activos, total_eliminados, record_size):
        with open(self.filename, "r+b") as f:
            f.seek(0)
            f.write(struct.pack(
                self.FILE_HEADER_FORMAT,
                total_records,
                total_activos,
                total_eliminados,
                record_size,
            ))

    def read_record(self, position):
        with open(self.filename, "rb") as f:
            f.seek(self.FILE_HEADER_SIZE + position * self.RECORD_FLAG_SIZE)
            raw = f.read(self.RECORD_FLAG_SIZE)
            if len(raw) != self.RECORD_FLAG_SIZE:
                return None
            return struct.unpack(self.RECORD_FLAG_FORMAT, raw)

    def write_record(self, position, record_tuple):
        with open(self.filename, "r+b") as f:
            offset = self.FILE_HEADER_SIZE + position * self.RECORD_FLAG_SIZE
            f.seek(offset)
            f.write(struct.pack(self.RECORD_FLAG_FORMAT, *record_tuple))

    def get_key(self, record):
        return record[self.key_index]
