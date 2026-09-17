import struct

RID = tuple

RID_FORMAT = "<ii"
RID_SIZE = struct.calcsize(RID_FORMAT)

FNV_OFFSET = 0xCBF29CE484222325
FNV_PRIME = 0x100000001B3
MASK64 = 0xFFFFFFFFFFFFFFFF


def key_format(key_type):
    if key_type == "int":
        return "<q"
    if key_type == "float":
        return "<d"
    if key_type.startswith("str:"):
        n = int(key_type.split(":")[1])
        return "<%ds" % n
    raise ValueError(key_type)


def pack_key(key, key_type, fmt):
    if key_type.startswith("str:"):
        n = int(key_type.split(":")[1])
        return struct.pack(fmt, str(key).encode()[:n])
    if key_type == "int":
        return struct.pack(fmt, int(key))
    return struct.pack(fmt, float(key))


def unpack_key(raw, key_type, fmt):
    value = struct.unpack(fmt, raw)[0]
    if key_type.startswith("str:"):
        return value.rstrip(b"\x00").decode()
    return value


def pack_rid(rid):
    return struct.pack(RID_FORMAT, rid[0], rid[1])


def unpack_rid(raw):
    return tuple(struct.unpack(RID_FORMAT, raw))


def stable_hash(key, key_type):
    if key_type == "int":
        return int(key) & MASK64
    if key_type == "float":
        data = struct.pack("<d", float(key))
    else:
        n = int(key_type.split(":")[1])
        data = str(key).encode()[:n]
    h = FNV_OFFSET
    for b in data:
        h ^= b
        h = (h * FNV_PRIME) & MASK64
    return h
