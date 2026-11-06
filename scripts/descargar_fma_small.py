#!/usr/bin/env python3
"""Descarga, verifica y descomprime FMA small (audio de la parte 4). Solo biblioteca estándar, Python 3.10+.

    python scripts/descargar_fma_small.py                       # descarga (7.2 GiB) y prepara
    python scripts/descargar_fma_small.py --zip fma_small.zip   # usa un zip ya descargado (sin red)

Queda en data/multimedia/audio/fma_small/, donde lo leen entrenar_mfcc.ps1 y SIMILAR_TO.
El zip se verifica con el SHA-1 que publica FMA (github.com/mdeff/fma) antes de
descomprimir. Luego se comprueba que los 8000 MP3 coinciden en ruta y tamaño con los
que entrenaron data/modelos/audio_mfcc (training.json): la colección es la misma
que la del vocabulario. manifest.csv lista cada MP3 con su ruta relativa a
data/multimedia y su track_id. Volver a ejecutarlo no repite el trabajo si ya está verificado.
Necesita unos 15 GB libres mientras descomprime (zip + MP3).
"""

import argparse
import csv
import json
import shutil
import sys
import zipfile
from pathlib import Path

from descargar_tiny_imagenet import ROOT, download, extract, file_hash, log

URL = "https://os.unil.cloud.switch.ch/fma/fma_small.zip"
SHA1 = "ade154f733639d52e35e32f5593efe5be76c6d70"
SIZE = 7_679_594_875
NAME = "fma_small"
TRAINING = ROOT / "data" / "modelos" / "audio_mfcc" / "training.json"


def check_zip(path):
    log("Verificando SHA-1 del zip (7.2 GiB, tarda un poco)...")
    if path.stat().st_size != SIZE or file_hash(path, "sha1") != SHA1:
        raise ValueError(f"{path} no es el zip esperado (tamaño o SHA-1 distintos); bórralo y vuelve a descargar")


def validate(dataset, training):
    """Compara los MP3 con los del entrenamiento y devuelve las filas del manifiesto."""
    expected = {item["path"].replace("\\", "/"): item["size"] for item in training["specification"]["dataset"]["files"]}
    found = {mp3.relative_to(dataset).as_posix(): mp3.stat().st_size for mp3 in dataset.rglob("*.mp3")}
    missing, extra = expected.keys() - found.keys(), found.keys() - expected.keys()
    resized = {path for path in expected.keys() & found.keys() if expected[path] != found[path]}
    assert not (missing or extra or resized), (
        f"los MP3 no coinciden con {TRAINING.name}: {len(missing)} faltan, {len(extra)} sobran, "
        f"{len(resized)} con otro tamaño (ej. {sorted(missing | extra | resized)[:3]})")
    # dataset es aún la carpeta temporal; la ruta final relativa a --destino es audio/fma_small/...
    return [(f"audio/{NAME}/{path}", int(Path(path).stem)) for path in sorted(found)]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--destino", type=Path, default=ROOT / "data" / "multimedia",
                        help="carpeta multimedia; el dataset queda en <destino>/audio/fma_small (default: data/multimedia)")
    parser.add_argument("--zip", type=Path, help="zip ya descargado; se verifica igual")
    parser.add_argument("--url", default=URL, help="espejo alternativo; el SHA-1 debe coincidir")
    parser.add_argument("--conservar-zip", action="store_true", help="no borrar el zip descargado")
    args = parser.parse_args()

    audio = args.destino.resolve() / "audio"
    audio.mkdir(parents=True, exist_ok=True)
    dataset = audio / NAME
    marker = dataset / ".verificado.json"
    if marker.exists() and json.loads(marker.read_text(encoding="utf-8")).get("zip_sha1") == SHA1:
        log(f"Ya está preparado y verificado: {dataset}")
        return 0
    if dataset.exists():
        raise SystemExit(f"Error: {dataset} existe pero no está verificado; bórralo y vuelve a ejecutar")

    try:
        training = json.loads(TRAINING.read_text(encoding="utf-8"))
        if args.zip:
            archive = args.zip.resolve()
            check_zip(archive)
        else:
            archive = audio / f"{NAME}.zip"
            if archive.exists():
                check_zip(archive)
            else:
                log(f"Descargando {args.url} ({SIZE / 2**30:.1f} GiB)...")
                download(args.url, archive, SIZE, check_zip)
        extracted = extract(archive, audio, NAME)
        log("Comparando los MP3 con los del vocabulario...")
        rows = validate(extracted, training)
        with open(extracted / "manifest.csv", "w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file, lineterminator="\n")
            writer.writerow(("ruta", "track_id"))
            writer.writerows(rows)
        summary = {"url": args.url, "zip_sha1": SHA1, "tracks": len(rows),
                   "vocabulary_id": training["vocabulary_id"],
                   "manifest_sha256": file_hash(extracted / "manifest.csv")}
        (extracted / ".verificado.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        extracted.replace(dataset)
        shutil.rmtree(extracted.parent, ignore_errors=True)
        if not args.zip and not args.conservar_zip:
            archive.unlink()
    except (OSError, ValueError, KeyError, AssertionError, zipfile.BadZipFile) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    log(f"Listo: {dataset} ({len(rows):,} MP3, los mismos del vocabulario {summary['vocabulary_id'][:12]}…)")
    log(f"Manifiesto: {dataset / 'manifest.csv'} (SHA-256 {summary['manifest_sha256'][:12]}…)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
