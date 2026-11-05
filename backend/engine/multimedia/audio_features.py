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
