from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import time

try:
    import numpy as np
except ImportError:
    np = None


VERSION = 1
EXTENSIONS = {
    "imagenes": {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"},
    "audio": {".wav", ".flac", ".mp3", ".ogg", ".m4a", ".aiff", ".aif"},
    "audio-msd": {".h5", ".hdf5"},
    "descriptores": {".npy"},
}


def log(message):
    print(time.strftime("[%H:%M:%S]"), message, flush=True)


def digest(data):
    text = json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def atomic_write(path, writer):
    path = Path(path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as file:
            temporary = Path(file.name)
            writer(file)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def save_json(path, data):
    encoded = json.dumps(data, indent=2, allow_nan=False).encode("utf-8")
    atomic_write(path, lambda file: file.write(encoded))


def save_array(path, array):
    atomic_write(path, lambda file: np.save(file, array, allow_pickle=False))


@contextmanager
def output_lock(directory):
    if os.name == "nt":
        import msvcrt
    else:
        import fcntl
    with (directory / ".lock").open("a+b") as lock:
        if os.name == "nt":
            if lock.seek(0, os.SEEK_END) == 0:
                lock.write(b"\0")
                lock.flush()
            lock.seek(0)
        try:
            if os.name == "nt":
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise ValueError("otro entrenamiento está usando esta salida") from error
        try:
            yield
        finally:
            if os.name == "nt":
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock, fcntl.LOCK_UN)


def discover(args):
    source = args.dataset.resolve()
    output = args.salida.resolve()
    if not source.exists():
        raise ValueError(f"no existe el dataset: {source}")
    if source == output or output in source.parents:
        raise ValueError("la salida no puede ser el dataset ni contenerlo")
    paths = [source] if source.is_file() else sorted(source.rglob("*"))
    groups = {kind: [] for kind in EXTENSIONS}
    for path in paths:
        if not path.is_file() or output == path or output in path.parents:
            continue
        for kind, suffixes in EXTENSIONS.items():
            if path.suffix.lower() in suffixes:
                groups[kind].append(path)
    kinds = [kind for kind, files in groups.items() if files]
    if args.tipo == "auto":
        if len(kinds) != 1:
            raise ValueError(
                "no hay una modalidad única; usa --tipo imagenes, audio, audio-msd o "
                "descriptores (el dataset debe estar descomprimido)"
            )
        args.tipo = kinds[0]
    paths = groups[args.tipo]
    if not paths:
        raise ValueError(f"no hay archivos compatibles con --tipo {args.tipo}")
    total = len(paths)
    if args.max_archivos and total > args.max_archivos:
        rng = np.random.default_rng(args.semilla)
        indices = sorted(rng.choice(total, args.max_archivos, replace=False))
        paths = [paths[i] for i in indices]
    base = source if source.is_dir() else source.parent
    entries = []
    for path in paths:
        stat = path.stat()
        entries.append({"path": str(path.relative_to(base)),
                        "size": stat.st_size, "mtime_ns": stat.st_mtime_ns})
    log(f"Dataset: {total} archivos compatibles; seleccionados {len(paths)}.")
    return paths, {"root": str(source), "total_files": total, "files": entries}


def make_extractor(args):
    """Devuelve una función archivo -> (N,D) y su configuración reproducible."""
    if args.tipo == "imagenes":
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
        from engine.multimedia.local_features import SiftExtractor
        import cv2
        cv2.setNumThreads(1)
        if args.normalizacion not in ("auto", "none"):
            raise ValueError("el extractor del gestor usa descriptores sin normalizacion L2 adicional")
        extractor = SiftExtractor(max_side=args.max_lado, nfeatures=500)
        config = {"extractor": "sift", "descriptor_id": extractor.descriptor_id,
                  "opencv": cv2.__version__, "max_side": args.max_lado,
                  "nfeatures": 500, "normalization": "none"}

        def extract(path):
            return extractor.extract(path).values

    elif args.tipo == "audio-msd":
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
        from engine.multimedia.audio_features import MsdTimbreExtractor
        import h5py
        if args.normalizacion not in ("auto", "none"):
            raise ValueError("el lector MSD del gestor usa timbre sin normalizacion adicional")
        extractor = MsdTimbreExtractor()
        config = {"extractor": "msd-timbre", "descriptor_id": extractor.descriptor_id,
                  "h5py": h5py.__version__, "field": "analysis/segments_timbre",
                  "dimension": 12, "normalization": "none"}

        def extract(path):
            return extractor.extract(path).values

    elif args.tipo == "audio":
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
        try:
            import librosa
        except ImportError as error:
            raise ValueError('instala audio: python -m pip install "librosa>=0.10.2"') from error
        from engine.multimedia.audio_features import MfccExtractor
        if args.normalizacion not in ("auto", "none"):
            raise ValueError("el extractor MFCC del gestor usa coeficientes sin normalizacion adicional")
        extractor = MfccExtractor(sr=args.sr, n_mfcc=args.mfcc, max_seconds=args.segundos)
        config = {"extractor": "mfcc", "descriptor_id": extractor.descriptor_id,
                  "librosa": librosa.__version__, "sample_rate": args.sr,
                  "n_mfcc": args.mfcc, "include_c0": False, "n_fft": 2048,
                  "hop_length": 512, "max_seconds": args.segundos, "normalization": "none"}

        def extract(path):
            return extractor.extract(path).values
    else:
        if not args.descriptor_id:
            raise ValueError("--tipo descriptores requiere --descriptor-id (extractor y versión)")
        config = {"extractor": "external-npy", "source_id": args.descriptor_id}

        def extract(path):
            return np.load(path, mmap_mode="r", allow_pickle=False)

    config["normalization"] = (
        "none"
    ) if args.normalizacion == "auto" else args.normalizacion
    return extract, config


def prepare_rows(rows, per_file, seed, normalization):
    if rows.ndim != 2 or rows.shape[1] < 1 or rows.dtype.kind not in "fiu":
        raise ValueError("se esperaba una matriz numérica real (N, D)")
    rng = np.random.default_rng(seed)
    if len(rows) > per_file:
        rows = rows[rng.choice(len(rows), per_file, replace=False)]
    rows = np.array(rows, dtype=np.float64, copy=True)
    if not np.isfinite(rows).all():
        raise ValueError("los descriptores contienen NaN o infinito")
    if normalization == "l2" and len(rows):
        norms = np.linalg.norm(rows, axis=1)
        if not np.isfinite(norms).all():
            raise ValueError("magnitudes de descriptores demasiado grandes")
        rows = rows[norms > 0] / norms[norms > 0, None]
    return rows


class DescriptorReservoir:
    def __init__(self, capacity, dimension, seed):
        self.rows = np.empty((capacity, dimension), dtype=np.float64)
        self.priorities = np.empty(capacity)
        # Índice en dataset.files (run.json) del archivo de cada descriptor.
        self.origins = np.empty(capacity, dtype=np.int64)
        self.used = 0
        self.rng = np.random.default_rng(seed)

    def add(self, rows, origin):
        keys = self.rng.random(len(rows))
        capacity = len(self.rows)
        fill = min(capacity - self.used, len(rows))
        self.rows[self.used:self.used + fill] = rows[:fill]
        self.priorities[self.used:self.used + fill] = keys[:fill]
        self.origins[self.used:self.used + fill] = origin
        self.used += fill
        if fill == len(rows):
            return
        rows, keys = rows[fill:], keys[fill:]
        candidates = keys < self.priorities.max()
        rows, keys = rows[candidates], keys[candidates]
        if not len(rows):
            return
        priorities = np.concatenate((self.priorities, keys))
        keep = np.argpartition(priorities, capacity - 1)[:capacity]
        retained = np.zeros(capacity, dtype=bool)
        retained[keep[keep < capacity]] = True
        incoming = keep[keep >= capacity] - capacity
        self.rows[~retained] = rows[incoming]
        self.priorities[~retained] = keys[incoming]
        self.origins[~retained] = origin

    @property
    def values(self):
        return self.rows[:self.used]

    @property
    def files(self):
        return self.origins[:self.used]


def prepare_sample(args, paths, entries, extract, config, output):
    sample_path = output / "sample.npy"
    if sample_path.exists():
        sample = np.load(sample_path, mmap_mode="r", allow_pickle=False)
        log(f"Reutilizando muestra: {sample.shape}.")
        return sample
    cache = output / "cache"
    cache.mkdir(exist_ok=True)
    reservoir = None
    seen = good = skipped = 0
    began = time.monotonic()
    with (output / "omitidos.jsonl").open("w", encoding="utf-8") as errors:
        for index, (path, entry) in enumerate(zip(paths, entries)):
            key = digest(entry)
            target = cache / (key + ".npy")
            cached = target.exists()
            try:
                if cached:
                    rows = np.load(target, allow_pickle=False)
                else:
                    rows = prepare_rows(extract(path), args.por_archivo,
                                        [args.semilla, int(key[:16], 16)],
                                        config["normalization"])
                if not len(rows):
                    raise ValueError("no produjo descriptores utilizables")
            except MemoryError:
                raise
            except Exception as error:
                if args.tipo == "descriptores":
                    raise ValueError(f"descriptores inválidos en {path}: {error}") from error
                skipped += 1
                errors.write(json.dumps({"path": str(path), "error": str(error)}) + "\n")
                errors.flush()
                if skipped <= 5:
                    log(f"Omitido {path.name}: {error}")
                continue
            if not cached:
                save_array(target, rows)
            if reservoir is None:
                reservoir = DescriptorReservoir(args.max_descriptores, rows.shape[1], args.semilla)
            if rows.shape[1] != reservoir.rows.shape[1]:
                raise ValueError(f"dimensiones incompatibles en {path}; no mezcles extractores")
            reservoir.add(rows, index)
            seen += len(rows)
            good += 1
            if (index + 1) % 25 == 0 or index + 1 == len(paths):
                elapsed = time.monotonic() - began
                eta = elapsed / (index + 1) * (len(paths) - index - 1)
                log(f"Preparación {index + 1}/{len(paths)}; muestra={reservoir.used}; "
                    f"omitidos={skipped}; restante aprox. {eta / 60:.1f} min")
    if reservoir is None or reservoir.used < args.k:
        raise ValueError("no hay suficientes descriptores para K; revisa omitidos.jsonl o reduce --k")
    sample = reservoir.values
    save_json(output / "sample-info.json", {"usable_files": good, "skipped_files": skipped,
                                           "descriptors_seen": seen, "sample_size": len(sample)})
    # Antes que sample.npy: su existencia marca la muestra como terminada.
    save_array(output / "sample-files.npy", reservoir.files)
    save_array(sample_path, sample)
    log(f"Muestra preparada: {sample.shape}; {skipped} archivos omitidos.")
    return np.load(sample_path, mmap_mode="r", allow_pickle=False)


def assignment(rows, centers, batch_size):
    """Entrega índices y distancias cuadradas por lote, sin matriz N×K×D."""
    for start in range(0, len(rows), batch_size):
        block = np.asarray(rows[start:start + batch_size], dtype=np.float64)
        distances = np.empty((len(block), len(centers)), dtype=np.float64)
        for index, center in enumerate(centers):
            delta = block - center
            distances[:, index] = np.einsum("ij,ij->i", delta, delta)
        if not np.isfinite(distances).all():
            raise ValueError("distancias no finitas; revisa la escala de los descriptores")
        labels = distances.argmin(axis=1)
        yield start, block, labels, distances[np.arange(len(block)), labels]


def initialize(rows, k, batch_size, seed):
    if len(rows) < k:
        raise ValueError("K supera la cantidad de descriptores")
    rng = np.random.default_rng(seed)
    centers = [np.array(rows[rng.integers(len(rows))], dtype=np.float64)]
    closest = np.full(len(rows), np.inf)
    for index in range(1, k):
        for start, block, _, distances in assignment(rows, centers[-1:], batch_size):
            closest[start:start + len(block)] = np.minimum(
                closest[start:start + len(block)], distances)
        total = closest.sum()
        if total <= 0:
            raise ValueError("K supera la cantidad de descriptores distintos")
        if not math.isfinite(total):
            raise ValueError("distancias demasiado grandes para inicializar")
        centers.append(np.array(rows[rng.choice(len(rows), p=closest / total)]))
        if (index + 1) % 32 == 0 or index + 1 == k:
            log(f"Inicialización K-Means++: {index + 1}/{k} centroides")
    return np.array(centers)


def save_checkpoint(path, centers, iteration, converged, history):
    # La foto va antes del checkpoint: un checkpoint nunca apunta a una foto faltante.
    snapshots = path.parent / "snapshots"
    snapshots.mkdir(exist_ok=True)
    save_array(snapshots / f"iter_{iteration:03d}.npy", centers)
    atomic_write(path, lambda file: np.savez(file, centers=centers,
                                           iteration=iteration, converged=converged,
                                           history=np.array(json.dumps(history))))


def fit(rows, args, checkpoint):
    if checkpoint.exists():
        with np.load(checkpoint, allow_pickle=False) as saved:
            centers = saved["centers"].copy()
            iteration = int(saved["iteration"])
            converged = bool(saved["converged"])
            # Checkpoints anteriores al historial lo empiezan vacío.
            history = json.loads(str(saved["history"])) if "history" in saved.files else []
        if centers.shape != (args.k, rows.shape[1]) or not np.isfinite(centers).all():
            raise ValueError("checkpoint inválido")
        log(f"Checkpoint recuperado: iteración {iteration}; convergencia={converged}.")
    else:
        log("Inicializando centroides con K-Means++...")
        centers = initialize(rows, args.k, args.lote, args.semilla)
        iteration, converged, history = 0, False, []
        save_checkpoint(checkpoint, centers, iteration, converged, history)
    while iteration < args.iteraciones and not converged:
        began = time.monotonic()
        last_progress = began
        sums = np.zeros_like(centers)
        counts = np.zeros(args.k, dtype=np.int64)
        inertia = 0.0
        for start, block, labels, distances in assignment(rows, centers, args.lote):
            np.add.at(sums, labels, block)
            counts += np.bincount(labels, minlength=args.k)
            inertia += float(distances.sum())
            now = time.monotonic()
            if now - last_progress >= 10:
                log(f"Iteración {iteration + 1}: {start + len(block)}/{len(rows)} descriptores")
                last_progress = now
        new = centers.copy()
        used = counts > 0
        new[used] = sums[used] / counts[used, None]
        # Los grupos vacíos conservan su centro; se informan al terminar.
        movement = float(np.linalg.norm(new - centers, axis=1).max())
        if not math.isfinite(movement):
            raise ValueError("actualización no finita de centroides")
        if not math.isfinite(inertia):
            raise ValueError("inercia no finita")
        centers = new
        iteration += 1
        converged = movement <= args.tolerancia
        # La inercia es la de los centros de entrada (snapshots/iter_{iteration-1}).
        history.append({"iteration": iteration, "inertia": inertia, "movement": movement,
                        "empty": int((counts == 0).sum())})
        save_checkpoint(checkpoint, centers, iteration, converged, history)
        elapsed = time.monotonic() - began
        log(f"Iteración {iteration}/{args.iteraciones}: desplazamiento={movement:.6g}, "
            f"vacíos={int((counts == 0).sum())}, {elapsed:.1f} s")
    inertia = 0.0
    counts = np.zeros(args.k, dtype=np.int64)
    for _, _, labels, distances in assignment(rows, centers, args.lote):
        inertia += float(distances.sum())
        counts += np.bincount(labels, minlength=args.k)
    if not math.isfinite(inertia):
        raise ValueError("inercia no finita")
    return centers, {"iterations": iteration, "converged": converged,
                     "inertia": inertia, "cluster_sizes": counts.tolist(),
                     "history": history}


def run(args):
    if np is None:
        raise ValueError('instala NumPy: python -m pip install "numpy>=1.24,<2.3"')
    paths, dataset = discover(args)
    extract, config = make_extractor(args)
    config["numpy"] = np.__version__
    descriptor_id = config.get("descriptor_id") or (args.descriptor_id if args.tipo == "descriptores" and
                     config["normalization"] == "none" else
                     config["extractor"] + ":" + digest(config))
    specification = {
        "version": VERSION, "dataset": dataset, "extractor": config,
        "descriptor_id": descriptor_id,
        "training": {"k": args.k, "seed": args.semilla, "tolerance": args.tolerancia,
                     "per_file": args.por_archivo, "max_descriptors": args.max_descriptores,
                     "max_files": args.max_archivos, "batch_size": args.lote},
    }
    output = args.salida.resolve()
    output.mkdir(parents=True, exist_ok=True)
    with output_lock(output):
        manifest = output / "run.json"
        if manifest.exists():
            if not args.reanudar:
                raise ValueError("la salida ya contiene un entrenamiento; usa --reanudar o una salida nueva")
            if json.loads(manifest.read_text()) != specification:
                raise ValueError("dataset/configuración distintos al entrenamiento anterior; usa una salida nueva")
        else:
            if args.reanudar:
                raise ValueError("no hay entrenamiento para reanudar en esta salida")
            if any(path.name != ".lock" for path in output.iterdir()):
                raise ValueError("la carpeta de salida debe estar vacía")
            save_json(manifest, specification)
        sample = prepare_sample(args, paths, dataset["files"], extract, config, output)
        n, dimension = sample.shape
        log(f"Entrenando: N={n}, D={dimension}, K={args.k}. CPU; sin GPU.")
        log(f"Muestra: {n * dimension * 8 / 2**20:.1f} MiB; matriz de distancias/lote: "
            f"{min(n, args.lote) * args.k * 8 / 2**20:.1f} MiB (más temporales).")
        try:
            centers, stats = fit(sample, args, output / "checkpoint.npz")
        finally:
            sample._mmap.close()
        vocabulary = {"format_version": 1, "descriptor_id": descriptor_id,
                      "dimension": dimension, "centroids": centers.tolist()}
        vocabulary["vocabulary_id"] = digest(vocabulary)
        report = {"specification": specification, "sample": json.loads(
            (output / "sample-info.json").read_text()), "result": stats,
            "vocabulary_id": vocabulary["vocabulary_id"]}
        save_json(output / "training.json", report)
        save_json(output / "vocabulary.json", vocabulary)
        log(f"Vocabulario guardado: {output / 'vocabulary.json'}")
        log(f"Inercia={stats['inertia']:.6g}; convergencia={stats['converged']}.")
        if not stats["converged"]:
            log("Se alcanzó el límite; puedes aumentar --iteraciones con --reanudar.")
        return vocabulary, report


def parser():
    command = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    command.add_argument("--dataset", type=Path, help="carpeta descomprimida o archivo .npy")
    command.add_argument("--salida", type=Path, default=Path("data/modelos/kmeans"))
    command.add_argument("--tipo", choices=["auto", *EXTENSIONS], default="auto")
    command.add_argument("--k", type=int, default=256, help="palabras del vocabulario (default: 256)")
    command.add_argument("--max-descriptores", type=int, default=100_000)
    command.add_argument("--por-archivo", type=int, default=256)
    command.add_argument("--max-archivos", type=int, default=10_000, help="0 = todos; muestra aleatoria")
    command.add_argument("--iteraciones", type=int, default=50)
    command.add_argument("--lote", type=int, default=512)
    command.add_argument("--semilla", type=int, default=42)
    command.add_argument("--tolerancia", type=float, default=1e-4)
    command.add_argument("--max-lado", type=int, default=512, help="lado máximo de imagen al extraer SIFT")
    command.add_argument("--segundos", type=float, default=30, help="primeros segundos de cada audio")
    command.add_argument("--sr", type=int, default=22050)
    command.add_argument("--mfcc", type=int, default=13)
    command.add_argument("--normalizacion", choices=["auto", "l2", "none"], default="auto")
    command.add_argument("--descriptor-id", help="extractor y configuración de los .npy externos")
    command.add_argument("--reanudar", action="store_true")
    command.add_argument("--autoprueba", action="store_true", help="prueba numérica y reanudación, sin dataset")
    return command


def validate(args, command):
    if args.dataset is None:
        command.error("debes indicar --dataset")
    for name in ("k", "max_descriptores", "por_archivo", "iteraciones", "lote", "max_lado", "sr", "mfcc"):
        if getattr(args, name) <= 0:
            command.error(f"--{name.replace('_', '-')} debe ser positivo")
    if args.max_archivos < 0 or args.semilla < 0:
        command.error("--max-archivos y --semilla deben ser no negativos")
    if not math.isfinite(args.tolerancia) or args.tolerancia < 0:
        command.error("--tolerancia debe ser finita y no negativa")
    if not math.isfinite(args.segundos) or args.segundos <= 0:
        command.error("--segundos debe ser finito y positivo")
    if args.mfcc > 128:
        command.error("--mfcc no puede superar los 128 filtros Mel configurados")
    if args.k > args.max_descriptores:
        command.error("--k no puede superar --max-descriptores")


def self_test():
    if np is None:
        raise ValueError("la autoprueba requiere NumPy")
    with tempfile.TemporaryDirectory(prefix="bd2-kmeans-") as directory:
        root = Path(directory)
        dataset = root / "dataset"
        dataset.mkdir()
        np.save(dataset / "a.npy", np.array([[0., 0.], [0., 2.]]))
        np.save(dataset / "b.npy", np.array([[10., 10.], [10., 12.]]))
        argv = ["--dataset", str(dataset), "--salida", str(root / "model"),
                "--tipo", "descriptores", "--descriptor-id", "demo:2d:v1",
                "--k", "2", "--iteraciones", "1", "--lote", "2"]
        first, report = run(parser().parse_args(argv))
        assert sorted(first["centroids"]) == [[0., 1.], [10., 11.]]
        assert report["result"]["inertia"] == 4.0
        assert report["result"]["cluster_sizes"] == [2, 2]
        argv[argv.index("--iteraciones") + 1] = "10"
        second, report = run(parser().parse_args(argv + ["--reanudar"]))
        assert first == second and report["result"]["converged"]
        assert report["result"]["iterations"] == 2
        # El historial sobrevive a la reanudación sin duplicarse.
        history = report["result"]["history"]
        assert [row["iteration"] for row in history] == [1, 2]
        assert history[1]["inertia"] == 4.0 and history[1]["movement"] == 0.0
        model = root / "model"
        assert sorted(p.name for p in (model / "snapshots").iterdir()) == [
            "iter_000.npy", "iter_001.npy", "iter_002.npy"]
        assert np.array_equal(np.load(model / "snapshots" / "iter_002.npy"), first["centroids"])
        sample = np.load(model / "sample.npy")
        origins = np.load(model / "sample-files.npy")
        assert origins.tolist() == (sample[:, 0] == 10).astype(int).tolist()  # a.npy=0, b.npy=1
        payload = {key: value for key, value in first.items() if key != "vocabulary_id"}
        assert digest(payload) == first["vocabulary_id"]
        # No sobrescribir entrenamientos ni aceptar otra configuración al reanudar.
        for invalid in (argv, argv + ["--reanudar", "--semilla", "9"]):
            try:
                run(parser().parse_args(invalid))
            except ValueError:
                pass
            else:
                raise AssertionError("debió rechazarse la configuración")
        for rows, k in ((np.ones((4, 2)), 2), (np.zeros((1, 2)), 2)):
            try:
                initialize(rows, k, 2, 42)
            except ValueError:
                pass
            else:
                raise AssertionError("debió rechazarse K")
        try:
            prepare_rows(np.array([[np.nan, 1]]), 10, 42, "none")
        except ValueError:
            pass
        else:
            raise AssertionError("debió rechazarse NaN")
        rows = np.array([[1e10, 1e10], [1e10 + 3, 1e10 + 4]])
        _, _, labels, distances = next(assignment(rows, rows[:1], 2))
        assert labels.tolist() == [0, 0] and distances.tolist() == [0., 25.]
        normalized = prepare_rows(np.array([[0., 0.], [3., 4.]]), 10, 42, "l2")
        assert np.allclose(normalized, [[0.6, 0.8]])
        population = np.arange(100, dtype=np.float64).reshape(-1, 1)
        reservoir = DescriptorReservoir(7, 1, 42)
        for offset in range(0, 100, 11):
            reservoir.add(population[offset:offset + 11], offset // 11)
        expected = np.argsort(np.random.default_rng(42).random(100))[:7]
        assert set(reservoir.values[:, 0]) == set(expected)
        assert reservoir.files.tolist() == (reservoir.values[:, 0] // 11).astype(int).tolist()
        assert reservoir.values.shape == (7, 1)
        resume_args = parser().parse_args(argv)
        paths, dataset_info = discover(resume_args)
        extractor, config = make_extractor(resume_args)
        interrupted = root / "interrupted"
        uninterrupted = root / "uninterrupted"
        interrupted.mkdir()
        uninterrupted.mkdir()
        calls = []

        def stop_on_second(path):
            calls.append(path)
            if len(calls) == 2:
                raise KeyboardInterrupt
            return extractor(path)

        try:
            prepare_sample(resume_args, paths, dataset_info["files"], stop_on_second, config, interrupted)
        except KeyboardInterrupt:
            pass
        else:
            raise AssertionError("faltó la interrupción de prueba")
        assert len(list((interrupted / "cache").glob("*.npy"))) == 1
        calls.clear()

        def record_call(path):
            calls.append(path)
            return extractor(path)

        resumed = prepare_sample(resume_args, paths, dataset_info["files"], record_call, config, interrupted)
        continuous = prepare_sample(resume_args, paths, dataset_info["files"], extractor, config, uninterrupted)
        try:
            assert len(calls) == 1 and np.array_equal(resumed, continuous)
        finally:
            resumed._mmap.close()
            continuous._mmap.close()
        atomic = root / "atomic.json"
        save_json(atomic, {"value": "original"})

        def failing_writer(file):
            file.write(b"incompleto")
            raise KeyboardInterrupt

        try:
            atomic_write(atomic, failing_writer)
        except KeyboardInterrupt:
            pass
        assert json.loads(atomic.read_text()) == {"value": "original"}
    log("OK: centroides, inercia, persistencia, reanudación, validaciones y distancias.")


def main(argv=None):
    command = parser()
    args = command.parse_args(argv)
    try:
        if args.autoprueba:
            self_test()
        else:
            validate(args, command)
            run(args)
    except KeyboardInterrupt:
        log("Interrumpido. Repite el mismo comando con --reanudar.")
        return 130
    except (ValueError, OSError, ImportError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
