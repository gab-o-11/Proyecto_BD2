from pathlib import Path
import numpy as np
from .local_features import DescriptorBatch, LocalFeatureExtractor


class MsdTimbreExtractor(LocalFeatureExtractor):
    @property
    def descriptor_id(self):
        return "msd:segments_timbre:12:raw:v1"

    @property
    def dimension(self):
        return 12

    def extract(self, path):
        import h5py
        if Path(path).suffix.lower() not in (".h5", ".hdf5"):
            raise ValueError("este vocabulario requiere un archivo MSD .h5; no admite MP3/WAV")
        with h5py.File(path, "r") as source:
            if "analysis/segments_timbre" not in source:
                raise ValueError("el archivo no contiene analysis/segments_timbre")
            if "analysis/songs" in source and len(source["analysis/songs"]) != 1:
                raise ValueError("se requiere un archivo MSD por cancion")
            values = np.asarray(source["analysis/segments_timbre"], dtype=np.float32)
        return DescriptorBatch(self.descriptor_id, self.dimension, values, source=str(path))

class MfccExtractor(LocalFeatureExtractor):
    
    def __init__(self, sr=22050, n_mfcc=13, n_fft=2048, hop_length=512, include_c0=False, max_seconds=None):
        if sr <= 0:
            raise ValueError(f"sr debe ser positivo")
        if n_mfcc < 2:
            raise ValueError(f"n_mfcc debe ser al menos 2")
        if n_fft <= 0 or hop_length <= 0:
            raise ValueError(f"n_fft y hop_length deben ser positivos, llegaron {n_fft} y {hop_length}")
        if max_seconds is not None and max_seconds <= 0:
            raise ValueError(f"max_seconds debe ser positivo o None, llegó {max_seconds}")
        self.sr = sr
        self.n_mfcc = n_mfcc
        self.n_fft = n_fft
        self.hop_length = hop_length
        self.include_c0 = include_c0
        self.max_seconds = max_seconds

    @property
    def descriptor_id(self):
        c0 = "c0" if self.include_c0 else "sinc0"
        duracion = "" if self.max_seconds is None else f":dur{self.max_seconds:g}"
        return f"mfcc:sr{self.sr}:n{self.n_mfcc}:fft{self.n_fft}:hop{self.hop_length}:{c0}{duracion}"

    @property
    def dimension(self):
        return self.n_mfcc if self.include_c0 else self.n_mfcc - 1

    def extract(self, path):

        import librosa

        y = self._read_mono(path)

        if len(y) < self.n_fft or not np.any(y):
            return DescriptorBatch(
                self.descriptor_id, self.dimension,
                np.empty((0, self.dimension), dtype=np.float32),
                source=str(path), positions=np.empty((0, 1), dtype=np.float32),
            )

        mfcc = librosa.feature.mfcc(
            y=y, sr=self.sr, n_mfcc=self.n_mfcc,
            n_fft=self.n_fft, hop_length=self.hop_length,
        )
        if not self.include_c0:
            mfcc = mfcc[1:]

        values = mfcc.T

        tiempos = librosa.frames_to_time(
            np.arange(values.shape[0]), sr=self.sr, hop_length=self.hop_length,
        )

        return DescriptorBatch(
            self.descriptor_id, self.dimension, values,
            source=str(path), positions=tiempos,
        )

    def _read_mono(self, path):
        import librosa
        import soundfile as sf

        if Path(path).stat().st_size == 0:
            raise ValueError(f"el archivo está vacío: {path}")
        with open(path, "rb") as archivo:
            try:
                y, _ = librosa.load(archivo, sr=self.sr, mono=True, duration=self.max_seconds)
            except sf.SoundFileError as error:
                raise ValueError(f"no se pudo leer como audio: {path}") from error
        return y
