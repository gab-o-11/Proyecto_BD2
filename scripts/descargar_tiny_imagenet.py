#!/usr/bin/env python3
"""Descarga, verifica y descomprime Tiny ImageNet (parte 4). Solo biblioteca estándar, Python 3.10+.

    python scripts/descargar_tiny_imagenet.py                 # descarga y prepara
    python scripts/descargar_tiny_imagenet.py --zip ruta.zip  # usa un zip ya descargado (sin red)

Queda en data/multimedia/tiny-imagenet-200/, la carpeta que el backend lee para
SIMILAR_TO('archivo') y que docker-compose monta. El zip se verifica con SHA-256
antes de descomprimir. Se comprueban 200 clases, 500 imágenes de entrenamiento
por clase y 10 000 de validación etiquetadas. manifest.csv lista cada imagen
etiquetada con su ruta relativa a data/multimedia, su clase y su nombre.
Volver a ejecutarlo no repite el trabajo si la carpeta ya está verificada.
"""

import argparse
import csv
import hashlib
import json
import shutil
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

URL = "https://cs231n.stanford.edu/tiny-imagenet-200.zip"
SHA256 = "6198c8ae015e2b3e007c7841da39ec069199b9aa3bfa943a462022fe5e43c821"
SIZE = 248_100_043
NAME = "tiny-imagenet-200"
CLASSES, TRAIN_PER_CLASS, VAL = 200, 500, 10_000
ROOT = Path(__file__).resolve().parents[1]


def log(message):
    print(time.strftime("[%H:%M:%S]"), message, flush=True)


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        for chunk in iter(lambda: file.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(url, target):
    """Descarga a .part y la retoma si se cortó; publica el zip solo si el hash coincide."""
    partial = target.with_name(target.name + ".part")
    done = partial.stat().st_size if partial.exists() else 0
    if done > SIZE:
        partial.unlink()
        done = 0
    if done < SIZE:
        request = urllib.request.Request(url, headers={"User-Agent": "bd2-dataset-downloader"})
        if done:
            request.add_header("Range", f"bytes={done}-")
        with urllib.request.urlopen(request, timeout=60) as response:
            if done and response.status != 206:
                done = 0  # El servidor no retoma: empezar de cero.
            with open(partial, "ab" if done else "wb") as file:
                last = time.monotonic()
                while chunk := response.read(1 << 20):
                    file.write(chunk)
                    done += len(chunk)
                    if time.monotonic() - last >= 5:
                        log(f"Descargado {done / 2**20:.0f}/{SIZE / 2**20:.0f} MiB")
                        last = time.monotonic()
    check_zip(partial)
    partial.replace(target)


def check_zip(path):
    log("Verificando SHA-256 del zip...")
    if path.stat().st_size != SIZE or sha256(path) != SHA256:
        raise ValueError(f"{path} no es el zip esperado (tamaño o SHA-256 distintos); bórralo y vuelve a descargar")


def extract(archive, destination):
    """Descomprime en una carpeta temporal, rechazando rutas fuera de ella."""
    temporary = destination / f".{NAME}.tmp"
    shutil.rmtree(temporary, ignore_errors=True)
    temporary.mkdir()
    base = temporary.resolve()
    with zipfile.ZipFile(archive) as file:
        for member in file.infolist():
            target = (temporary / member.filename).resolve()
            if target != base and base not in target.parents:
                raise ValueError(f"ruta insegura en el zip: {member.filename}")
        log(f"Descomprimiendo {len(file.infolist()):,} entradas...")
        file.extractall(temporary)
    return temporary / NAME


def validate(dataset):
    """Comprueba la estructura y devuelve las filas etiquetadas del manifiesto."""
    wnids = (dataset / "wnids.txt").read_text(encoding="utf-8").split()
    assert len(wnids) == CLASSES == len(set(wnids)), "wnids.txt no tiene 200 clases distintas"
    names = {}
    for line in (dataset / "words.txt").read_text(encoding="utf-8").splitlines():
        wnid, _, words = line.partition("\t")
        names[wnid] = words.split(",")[0].strip()
    rows = []
    for wnid in sorted(wnids):
        images = sorted((dataset / "train" / wnid / "images").glob("*.JPEG"))
        assert len(images) == TRAIN_PER_CLASS, f"{wnid}: {len(images)} imágenes de entrenamiento"
        rows += [("train", image, wnid) for image in images]
    annotations = (dataset / "val" / "val_annotations.txt").read_text(encoding="utf-8").splitlines()
    assert len(annotations) == VAL, "val_annotations.txt no tiene 10 000 filas"
    for line in sorted(annotations):
        filename, wnid = line.split("\t")[:2]
        image = dataset / "val" / "images" / filename
        assert wnid in names and wnid in wnids and image.is_file(), f"anotación inválida: {line}"
        rows.append(("val", image, wnid))
    return [(split, image.relative_to(dataset.parent).as_posix(), wnid, names[wnid]) for split, image, wnid in rows]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--destino", type=Path, default=ROOT / "data" / "multimedia",
                        help="carpeta donde queda tiny-imagenet-200/ (default: data/multimedia)")
    parser.add_argument("--zip", type=Path, help="zip ya descargado; se verifica igual")
    parser.add_argument("--url", default=URL, help="espejo alternativo; el SHA-256 debe coincidir")
    parser.add_argument("--conservar-zip", action="store_true", help="no borrar el zip descargado")
    args = parser.parse_args()

    destination = args.destino.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    dataset = destination / NAME
    marker = dataset / ".verificado.json"
    if marker.exists() and json.loads(marker.read_text(encoding="utf-8")).get("zip_sha256") == SHA256:
        log(f"Ya está preparado y verificado: {dataset}")
        return 0
    if dataset.exists():
        raise SystemExit(f"Error: {dataset} existe pero no está verificado; bórralo y vuelve a ejecutar")

    try:
        if args.zip:
            archive = args.zip.resolve()
            check_zip(archive)
        else:
            archive = destination / f"{NAME}.zip"
            if archive.exists():
                check_zip(archive)
            else:
                log(f"Descargando {args.url} ({SIZE / 2**20:.0f} MiB)...")
                download(args.url, archive)
        extracted = extract(archive, destination)
        log("Validando clases e imágenes...")
        rows = validate(extracted)
        with open(extracted / "manifest.csv", "w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file, lineterminator="\n")
            writer.writerow(("split", "ruta", "wnid", "clase"))
            writer.writerows(rows)
        summary = {"url": args.url, "zip_sha256": SHA256, "train": len(rows) - VAL, "val": VAL, "classes": CLASSES,
                   "manifest_sha256": sha256(extracted / "manifest.csv")}
        (extracted / ".verificado.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        extracted.replace(dataset)
        shutil.rmtree(extracted.parent, ignore_errors=True)
        if not args.zip and not args.conservar_zip:
            archive.unlink()
    except (OSError, ValueError, AssertionError, zipfile.BadZipFile) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    log(f"Listo: {dataset} ({summary['train']:,} de entrenamiento, {VAL:,} de validación, {CLASSES} clases)")
    log(f"Manifiesto: {dataset / 'manifest.csv'} (SHA-256 {summary['manifest_sha256'][:12]}…)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
