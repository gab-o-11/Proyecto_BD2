from dataclasses import dataclass
from pathlib import Path
import hashlib
import json
import math
import random

@dataclass(frozen=True)
class Vocabulary:
    descriptor_id: str
    dimension: int
    centroide: tuple[Vector, ...]
    def __post_init__(self):
        batch = DescriptorBatch(
            self.descriptor_id, self.dimension, self.centroids
        )
        if not batch.values:
            raise ValueError("el vocabulario necesita al menos un centroide")
        object.__setattr__(self, "centroids", batch.values)

    @property
    def size(self):
        return len(self.centroids)

    def payload(self):
        return {
            "format_version": 1,
            "descriptor_id": self.descriptor_id,
            "dimension": self.dimension,
            "centroids": [list(row) for row in self.centroids],
        }

    @property
    def vocabulary_id(self):
        serialized = json.dumps(
            self.payload(), sort_keys=True, separators=(",", ":"),
            allow_nan=False,
        )
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

def save_vocabulary(vocabulary: Vocabulary, path):
    data = vocabulary.payload()
    data["vocabulary_id"] = vocabulary.vocabulary_id
    with Path(path).open("x", encoding="utf-8") as file:
        json.dump(data, file, indent=2, allow_nan=False)


def load_vocabulary(path):
    with Path(path).open(encoding="utf-8") as file:
        data = json.load(file)
    if data.get("format_version") != 1:
        raise ValueError("formato de vocabulario desconocido")
    vocabulary = Vocabulary(
        descriptor_id=data["descriptor_id"],
        dimension=data["dimension"],
        centroids=tuple(tuple(row) for row in data["centroids"]),
    )
    if data.get("vocabulary_id") != vocabulary.vocabulary_id:
        raise ValueError("el contenido no corresponde al vocabulary_id")
    return vocabulary
    
def squared_distance(left: Vector, right: Vector):
    if len(left) != len(right):
        raise ValueError("no se pueden comparar dimensiones distintas")
    value = sum((a - b) * (a - b) for a, b in zip(left, right))
    if not math.isfinite(value):
        raise ValueError("distancia fuera del rango numérico")
    return value

def nearest_word(descriptor: Vector, centroids: tuple[Vector, ...]):
    return min(
        range(len(centroids)),
        key=lambda index: squared_distance(descriptor, centroids[index]),
    )

