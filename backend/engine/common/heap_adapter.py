import struct

from engine.storage.heap.heapfile import RID
from engine.common.rid import as_pair


def to_heap_rid(rid):
    page_id, slot_id = as_pair(rid)
    return RID(page_id, slot_id)


def heap_fetch(heap, rid):
    page_id, slot_id = as_pair(rid)
    offset = heap.calcular_slot(page_id, slot_id)
    with open(heap.filename, "rb") as f:
        f.seek(offset)
        raw = f.read(heap.RECORD_SIZE)
    if len(raw) < heap.RECORD_SIZE:
        return None
    record = struct.unpack(heap.RECORD_FORMAT, raw)
    if record[-1] != -1:
        return None
    return record[:-1]


def build_index(heap, index, key_field):
    page_size, total_pages, total_records, first_id = heap.read_file_header()
    for page_id in range(1, total_pages + 1):
        _, num_reg, _, _ = heap.read_page_header(page_id)
        for slot_id in range(num_reg):
            data = heap_fetch(heap, (page_id, slot_id))
            if data is None:
                continue
            index.insert(data[key_field], (page_id, slot_id))
    return index
