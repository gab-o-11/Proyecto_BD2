import os
import struct
import operator


class SequentialFile:
    FILE_HEADER_FORMAT = "iiiii"
    PAGE_HEADER_FORMAT = "ii"

    def __init__(self, filename, record_format, key_index=0, page_size=4096, waste_threshold=0.30):
        self.filename = filename
        self.RECORD_FORMAT = record_format
        self.key_index = key_index
        self.PAGE_SIZE = page_size
        self.waste_threshold = waste_threshold
        self.reorg_floor = 4
        self.reorganizations = 0
        self._tails = {}

        self.RECORD_WITH_POINTER_FORMAT = self.RECORD_FORMAT + "ii"
        self.SLOT_SIZE = struct.calcsize(self.RECORD_WITH_POINTER_FORMAT)
        self.FILE_HEADER_SIZE = struct.calcsize(self.FILE_HEADER_FORMAT)
        self.PAGE_HEADER_SIZE = struct.calcsize(self.PAGE_HEADER_FORMAT)
        self.SLOTS_PER_PAGE = (self.PAGE_SIZE - self.PAGE_HEADER_SIZE) // self.SLOT_SIZE
        if self.SLOTS_PER_PAGE < 1:
            self.SLOTS_PER_PAGE = 1

        if not os.path.exists(filename) or os.path.getsize(filename) == 0:
            self.nuevo_archivo()

    def nuevo_archivo(self):
        with open(self.filename, "wb") as f:
            f.write(struct.pack(self.FILE_HEADER_FORMAT, 0, 0, 0, self.SLOT_SIZE, -1))

    def read_header(self):
        with open(self.filename, "rb") as f:
            data = f.read(self.FILE_HEADER_SIZE)
            if len(data) != self.FILE_HEADER_SIZE:
                raise ValueError("Header del archivo corrupto o vacio")
            return struct.unpack(self.FILE_HEADER_FORMAT, data)

    def write_header(self, main_count, total_slots, deleted_count, record_size, overflow_head):
        with open(self.filename, "r+b") as f:
            f.seek(0)
            f.write(struct.pack(
                self.FILE_HEADER_FORMAT,
                main_count,
                total_slots,
                deleted_count,
                record_size,
                overflow_head,
            ))

    def _locate(self, position):
        page_id = position // self.SLOTS_PER_PAGE
        slot = position % self.SLOTS_PER_PAGE
        page_start = self.FILE_HEADER_SIZE + page_id * self.PAGE_SIZE
        offset = page_start + self.PAGE_HEADER_SIZE + slot * self.SLOT_SIZE
        return page_id, slot, page_start, offset

    def read_record(self, position):
        page_id, slot, page_start, offset = self._locate(position)
        with open(self.filename, "rb") as f:
            f.seek(offset)
            raw = f.read(self.SLOT_SIZE)
            if len(raw) != self.SLOT_SIZE:
                return None
            return struct.unpack(self.RECORD_WITH_POINTER_FORMAT, raw)

    def write_record(self, position, slot_tuple):
        page_id, slot, page_start, offset = self._locate(position)
        with open(self.filename, "r+b") as f:
            f.seek(offset)
            f.write(struct.pack(self.RECORD_WITH_POINTER_FORMAT, *slot_tuple))

    def _append_slot(self, position, slot_tuple):
        page_id, slot, page_start, offset = self._locate(position)
        with open(self.filename, "r+b") as f:
            if slot == 0:
                f.seek(page_start)
                f.write(struct.pack(self.PAGE_HEADER_FORMAT, page_id, 1))
            else:
                f.seek(page_start)
                header = f.read(self.PAGE_HEADER_SIZE)
                stored_id, stored_count = struct.unpack(self.PAGE_HEADER_FORMAT, header)
                f.seek(page_start)
                f.write(struct.pack(self.PAGE_HEADER_FORMAT, stored_id, stored_count + 1))
            f.seek(offset)
            f.write(struct.pack(self.RECORD_WITH_POINTER_FORMAT, *slot_tuple))

    def get_key(self, record):
        return record[self.key_index]

    def _fields(self, slot):
        return slot[:-2]

    def _next(self, slot):
        return slot[-2]

    def _deleted(self, slot):
        return slot[-1]

    def _bisect_right_main(self, key, main_count):
        lo = 0
        hi = main_count
        while lo < hi:
            mid = (lo + hi) // 2
            slot = self.read_record(mid)
            if slot[self.key_index] > key:
                hi = mid
            else:
                lo = mid + 1
        return lo

    def _should_reorganize(self, main_count, total_slots, deleted_count):
        if total_slots < self.reorg_floor:
            return False
        wasted = deleted_count + (total_slots - main_count)
        return wasted > self.waste_threshold * total_slots

    def _tail_ok(self, gap, key):
        pos = self._tails.get(gap)
        if pos is None:
            return False
        slot = self.read_record(pos)
        if slot is None:
            return False
        if self._next(slot) != -1:
            return False
        if slot[self.key_index] > key:
            return False
        return True

    def insert(self, record):
        record = tuple(record)
        main_count, total_slots, deleted_count, record_size, overflow_head = self.read_header()
        key = record[self.key_index]
        new_position = total_slots

        right = self._bisect_right_main(key, main_count)
        gap = right - 1

        if self._tail_ok(gap, key):
            tail_pos = self._tails[gap]
            self._append_slot(new_position, record + (-1, 0))
            tail_slot = self.read_record(tail_pos)
            self.write_record(tail_pos, self._fields(tail_slot) + (new_position, self._deleted(tail_slot)))
            total_slots += 1
            self.write_header(main_count, total_slots, deleted_count, self.SLOT_SIZE, overflow_head)
            self._tails[gap] = new_position
            if self._should_reorganize(main_count, total_slots, deleted_count):
                self.reorganize()
                return self._find_position(key)
            return new_position

        if gap < 0:
            chain_head = overflow_head
        else:
            chain_head = self._next(self.read_record(gap))

        previous = -1
        current = chain_head
        while current != -1:
            slot = self.read_record(current)
            if slot[self.key_index] > key:
                break
            previous = current
            current = self._next(slot)

        self._append_slot(new_position, record + (current, 0))

        if previous == -1:
            if gap < 0:
                overflow_head = new_position
            else:
                gap_slot = self.read_record(gap)
                self.write_record(gap, self._fields(gap_slot) + (new_position, self._deleted(gap_slot)))
        else:
            previous_slot = self.read_record(previous)
            self.write_record(previous, self._fields(previous_slot) + (new_position, self._deleted(previous_slot)))

        total_slots += 1
        self.write_header(main_count, total_slots, deleted_count, self.SLOT_SIZE, overflow_head)

        if current == -1:
            self._tails[gap] = new_position

        if self._should_reorganize(main_count, total_slots, deleted_count):
            self.reorganize()
            return self._find_position(key)

        return new_position

    def _write_sorted(self, records):
        with open(self.filename, "wb") as f:
            f.write(struct.pack(self.FILE_HEADER_FORMAT, len(records), len(records), 0, self.SLOT_SIZE, -1))
            total = len(records)
            index = 0
            page_id = 0
            while index < total:
                count = self.SLOTS_PER_PAGE
                if total - index < count:
                    count = total - index
                page = bytearray(self.PAGE_SIZE)
                struct.pack_into(self.PAGE_HEADER_FORMAT, page, 0, page_id, count)
                s = 0
                while s < count:
                    record = records[index + s]
                    place = self.PAGE_HEADER_SIZE + s * self.SLOT_SIZE
                    struct.pack_into(self.RECORD_WITH_POINTER_FORMAT, page, place, *(record + (-1, 0)))
                    s += 1
                f.write(page)
                index += count
                page_id += 1

    def reorganize(self):
        records = self.scan()
        self._write_sorted(records)
        self.reorganizations += 1
        self._tails = {}

    def bulk_load(self, records):
        combined = self.scan()
        for record in records:
            combined.append(tuple(record))
        combined.sort(key=operator.itemgetter(self.key_index))
        self._write_sorted(combined)
        self.reorganizations += 1
        self._tails = {}

    def _walk_chain(self, start, out):
        current = start
        seen = set()
        while current != -1 and current not in seen:
            seen.add(current)
            slot = self.read_record(current)
            if slot is None:
                break
            if self._deleted(slot) == 0:
                out.append((current, self._fields(slot)))
            current = self._next(slot)

    def _ordered_with_pos(self):
        main_count, total_slots, deleted_count, record_size, overflow_head = self.read_header()
        out = []
        self._walk_chain(overflow_head, out)
        for i in range(main_count):
            slot = self.read_record(i)
            if slot is None:
                continue
            if self._deleted(slot) == 0:
                out.append((i, self._fields(slot)))
            self._walk_chain(self._next(slot), out)
        return out

    def scan(self):
        result = []
        for position, fields in self._ordered_with_pos():
            result.append(fields)
        return result

    def _find_position(self, key):
        main_count, total_slots, deleted_count, record_size, overflow_head = self.read_header()
        right = self._bisect_right_main(key, main_count)
        j = right - 1
        while j >= 0:
            slot = self.read_record(j)
            if slot[self.key_index] != key:
                break
            if self._deleted(slot) == 0:
                return j
            j -= 1
        gap = right - 1
        if gap < 0:
            current = overflow_head
        else:
            current = self._next(self.read_record(gap))
        while current != -1:
            slot = self.read_record(current)
            if slot[self.key_index] == key and self._deleted(slot) == 0:
                return current
            if slot[self.key_index] > key:
                break
            current = self._next(slot)
        return -1

    def search(self, key):
        position = self._find_position(key)
        if position == -1:
            return None
        return self._fields(self.read_record(position))

    def search_range(self, start_key, end_key):
        results = []
        for position, fields in self._ordered_with_pos():
            key_value = fields[self.key_index]
            if key_value < start_key:
                continue
            if key_value > end_key:
                break
            results.append(fields)
        return results

    def delete(self, key):
        position = self._find_position(key)
        if position == -1:
            return False
        slot = self.read_record(position)
        self.write_record(position, self._fields(slot) + (self._next(slot), 1))
        main_count, total_slots, deleted_count, record_size, overflow_head = self.read_header()
        deleted_count += 1
        self.write_header(main_count, total_slots, deleted_count, self.SLOT_SIZE, overflow_head)
        if self._should_reorganize(main_count, total_slots, deleted_count):
            self.reorganize()
        return True

    def update(self, key, new_record):
        new_record = tuple(new_record)
        position = self._find_position(key)
        if position == -1:
            return False
        slot = self.read_record(position)
        if len(new_record) != len(self._fields(slot)):
            raise ValueError("Formato de registro incorrecto")
        if new_record[self.key_index] == key:
            self.write_record(position, new_record + (self._next(slot), 0))
            return True
        self.delete(key)
        self.insert(new_record)
        return True

    def stats(self):
        main_count, total_slots, deleted_count, record_size, overflow_head = self.read_header()
        overflow = total_slots - main_count
        active = total_slots - deleted_count
        num_pages = 0
        if total_slots > 0:
            num_pages = (total_slots + self.SLOTS_PER_PAGE - 1) // self.SLOTS_PER_PAGE
        wasted_ratio = 0.0
        if total_slots > 0:
            wasted_ratio = (deleted_count + overflow) / total_slots
        return {
            "page_size": self.PAGE_SIZE,
            "slots_per_page": self.SLOTS_PER_PAGE,
            "num_pages": num_pages,
            "total_slots": total_slots,
            "active": active,
            "main_ordered": main_count,
            "overflow": overflow,
            "deleted": deleted_count,
            "wasted_ratio": wasted_ratio,
            "reorganizations": self.reorganizations,
        }
