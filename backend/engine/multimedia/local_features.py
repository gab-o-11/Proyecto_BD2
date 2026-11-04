from abc import ABC, abstractmethod
from dataclasses import dataclass
import numpy as np

@dataclass(frozen=True, eq=False)
class DescriptorBatch:

    descriptor: str
    dimension: int
    values: np.ndarray
    source: str | None = None
    positions: np.ndarray | None = None

def __post_init__(self):
    if not isinstance(self.dimension, (int,np.integer)) or self.dimension <= 0:
        raise ValueError(f"La dimesión tiene que ser un número entero positivo, lo que llegó fue {self.dimension!r}")

    #se convierte a array de float32
    values = np.asarray(self.values, dtype = np.float32)

    #cuando una imagen no tiene keypoints(0,) se da la forma de (0,dimesiones)
    if values.size == 0:
        values = values.reshape(0, self.dimesion)

    # Validar que se una matriz de N filas y D columnas
    if values.ndim != 2 or values.shape [1] != self.dimesion:
        raise ValueError (f"se esperaba (N, {self.dimension}) y llegó {values.shape}")

    ##Si nos encontramos un Nan o valor infinito contamina el algoritmo k-means
    if not np.isinfinite(values).all():
        raise ValueError("values contiene NaN o infinitos")

    object.__setattr__(self, "values", values)


    ##sirve para ubicar los keypoints en una imagen con un el visualizador de opencv  y para MFCC para el audio
    if self.positions is not None:
            positions = np.asarray(self.positions, dtype=np.float32)
            # MFCC puede entregar los tiempos como vector (N,): lo pasamos a (N, 1).
            if positions.ndim == 1:
                positions = positions.reshape(-1, 1)
            if positions.ndim != 2 or positions.shape[0] != values.shape[0]:
                raise ValueError(
                    f"positions debe tener {values.shape[0]} filas y llegó con forma {positions.shape}"
                )
            object.__setattr__(self, "positions", positions)


def __len__(self):
    return self.values.shape[0]

class LocalFeatureExtractor(ABC):

    @property
    @abstractmethod
    def descriptor_id(self) -> str:
        """Extractor + parámetros. Dos lotes con distinto id no se comparan."""

    @property
    @abstractmethod
    def dimension(self) -> int:
        """D: longitud de cada descriptor."""

    @abstractmethod
    def extract(self, path) -> DescriptorBatch:
        """Lee el archivo en `path` y devuelve sus descriptores locales."""