from abc import ABC, abstractmethod
from dataclasses import dataclass
import numpy as np
import cv2

@dataclass(frozen=True, eq=False)
class DescriptorBatch:

    descriptor_id: str
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
            values = values.reshape(0, self.dimension)

        # Validar que se una matriz de N filas y D columnas
        if values.ndim != 2 or values.shape [1] != self.dimension:
            raise ValueError (f"se esperaba (N, {self.dimension}) y llegó {values.shape}")

        ##Si nos encontramos un Nan o valor infinito contamina el algoritmo k-means
        if not np.isfinite(values).all():
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
        
class SiftExtractor(LocalFeatureExtractor):
    def __init__(self, max_side = 512, nfeatures = 500): #(-,maximo de pixeles,maximo de keypoints) 
        if max_side <= 0:
            raise ValueError(f"max_side tiene que ser positivo")
        if nfeatures < 0:
            raise ValueError(f"nfeatures no puede ser negativo")
        self.max_side = max_side
        self.nfeatures = nfeatures
        
        self._sift = cv2.SIFT_create(nfeatures=nfeatures)
    
    @property
    def descriptor_id(self):
        return f"sift:gray:max{self.max_side}:nf{self.nfeatures}"
    
    @property
    def dimension(self):
        return 128 ##segun el pdf
    
    @staticmethod
    def _read_gray(path):
    
        data = np.fromfile(str(path), dtype=np.uint8)
        
        if data.size == 0:
            raise ValueError(f"el archivo está vacío: {path}")
        
        gray = cv2.imdecode(data, cv2.IMREAD_GRAYSCALE) ## se descomprime y se coloca en escala de grises, parte del SIFT
        
        if gray is None:
            raise ValueError(f"no se pudo leer como imagen: {path}")
        return gray ## devuelve la matriz de brillos

    def _downscale(self, gray):
        
        alto, ancho = gray.shape
        scale = self.max_side / max(alto, ancho)
        
        if scale >= 1: ##Si la scala es uno o más es que la imagen tiene 512px de ancho y no se reescala
            return gray, 1.0
        
        nuevo = (max(1, round(ancho * scale)), max(1, round(alto * scale))) 
        return cv2.resize(gray, nuevo, interpolation=cv2.INTER_AREA), scale ## se reescala la imagen
    
from abc import ABC, abstractmethod
from dataclasses import dataclass
import numpy as np
import cv2

@dataclass(frozen=True, eq=False)
class DescriptorBatch:

    descriptor_id: str
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
            values = values.reshape(0, self.dimension)

        # Validar que se una matriz de N filas y D columnas
        if values.ndim != 2 or values.shape [1] != self.dimension:
            raise ValueError (f"se esperaba (N, {self.dimension}) y llegó {values.shape}")

        ##Si nos encontramos un Nan o valor infinito contamina el algoritmo k-means
        if not np.isfinite(values).all():
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
        
class SiftExtractor(LocalFeatureExtractor):
    def __init__(self, max_side = 512, nfeatures = 500): #(-,maximo de pixeles,maximo de keypoints) 
        if max_side <= 0:
            raise ValueError(f"max_side tiene que ser positivo")
        if nfeatures < 0:
            raise ValueError(f"nfeatures no puede ser negativo")
        self.max_side = max_side
        self.nfeatures = nfeatures
        
        self._sift = cv2.SIFT_create(nfeatures=nfeatures)
    
    @property
    def descriptor_id(self):
        return f"sift:gray:max{self.max_side}:nf{self.nfeatures}"
    
    @property
    def dimension(self):
        return 128 ##segun el pdf
    
    @staticmethod
    def _read_gray(path):
    
        data = np.fromfile(str(path), dtype=np.uint8)
        
        if data.size == 0:
            raise ValueError(f"el archivo está vacío: {path}")
        
        gray = cv2.imdecode(data, cv2.IMREAD_GRAYSCALE) ## se descomprime y se coloca en escala de grises, parte del SIFT
        
        if gray is None:
            raise ValueError(f"no se pudo leer como imagen: {path}")
        return gray ## devuelve la matriz de brillos

    def _downscale(self, gray):
        
        alto, ancho = gray.shape
        scale = self.max_side / max(alto, ancho)
        
        if scale >= 1: ##Si la scala es uno o más es que la imagen tiene 512px de ancho y no se reescala
            return gray, 1.0
        
        nuevo = (max(1, round(ancho * scale)), max(1, round(alto * scale))) 
        return cv2.resize(gray, nuevo, interpolation=cv2.INTER_AREA), scale ## se reescala la imagen
    
    def extract(self, path):
        gray = self._read_gray(path)
        gray, scale = self._downscale(gray)

        keypoints, descriptors = self._sift.detectAndCompute(gray, None) ## se ejecuta sift

        if descriptors is None:
            descriptors = np.empty((0, self.dimension), dtype=np.float32)
            positions = np.empty((0, 4), dtype=np.float32)
        else:
            positions = np.array(
                [(kp.pt[0] / scale, kp.pt[1] / scale, kp.size / scale, kp.angle)
                 for kp in keypoints],
                dtype=np.float32,
            )

        return DescriptorBatch(
            self.descriptor_id, self.dimension, descriptors,
            source=str(path), positions=positions,
        )