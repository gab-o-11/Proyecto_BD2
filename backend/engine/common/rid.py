def as_pair(rid):
    if isinstance(rid, tuple) or isinstance(rid, list):
        return (rid[0], rid[1])
    if hasattr(rid, "getter"):
        page_id, slot_id = rid.getter()
        return (page_id, slot_id)
    return (rid.page_id, rid.slot_id)
