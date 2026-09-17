import os
import tempfile

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from engine.hashing import ExtendibleHashIndex

app = FastAPI(title="MiniGestor BD2")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/hashing/demo")
def hashing_demo():
    path = os.path.join(tempfile.gettempdir(), "api_hash")
    for suffix in (".dir", ".buk"):
        full = path + suffix
        if os.path.exists(full):
            os.remove(full)
    idx = ExtendibleHashIndex(path, key_type="int", block_factor=3)
    claves = [10, 13, 34, 6, 23, 12, 15, 73, 28, 19, 67, 17, 41, 87, 57, 27, 11]
    for i, k in enumerate(claves):
        idx.insert(k, (i, 0))
    stats = idx.stats()
    idx.close()
    return {"claves": claves, "stats": stats}
