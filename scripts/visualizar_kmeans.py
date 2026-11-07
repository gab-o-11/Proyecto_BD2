"""Exporta un entrenamiento de entrenar_Kmeans.py a una página D3 interactiva.

Calcula aquí lo que el navegador no puede (t-SNE, PCA, reasignaciones, árbol sustituto) y lo incrusta
como JSON en la plantilla visualizar_kmeans.html. Requiere un entrenamiento con historial, fotos por
iteración (snapshots/) y, para la sección de géneros, sample-files.npy y tracks.csv de fma_metadata.

    micromamba run -n bd2 python scripts/visualizar_kmeans.py --run data/modelos/kmeans_mfcc_hist
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = Path(__file__).with_name("visualizar_kmeans.html")
PLACEHOLDER = '<script id="datos" type="application/json">null</script>'
SLOTS = 8  # colores de la paleta categórica; el resto de clusters va en gris


def assign(points, centers):
    d = (points * points).sum(1)[:, None] - 2 * points @ centers.T + (centers * centers).sum(1)[None]
    return d.argmin(1)


def rounded(values, digits):
    return np.round(np.asarray(values, dtype=np.float64), digits).tolist()


def codes(slots):
    """Índices 0-7 (o -1) a un texto de un carácter por punto: compacto para miles de puntos × T."""
    return "".join(np.array(list("01234567."))[np.where(slots < 0, 8, slots)])


def export(run, tracks, n_sub, n_proj, seed):
    from sklearn.decomposition import PCA
    from sklearn.manifold import TSNE
    from sklearn.metrics import balanced_accuracy_score, recall_score
    from sklearn.model_selection import train_test_split
    from sklearn.tree import DecisionTreeClassifier, export_text

    spec = json.loads((run / "run.json").read_text(encoding="utf-8"))
    report = json.loads((run / "training.json").read_text(encoding="utf-8"))
    history = report["result"].get("history", [])
    if not history:
        raise ValueError("training.json sin historial: entrena con la versión instrumentada del script")
    paths = sorted((run / "snapshots").glob("iter_*.npy"))
    if [int(p.stem[5:]) for p in paths] != list(range(len(paths))):
        raise ValueError("faltan fotos intermedias en snapshots/")
    snapshots = np.stack([np.load(p) for p in paths])
    T, K, D = snapshots.shape
    final = json.loads((run / "vocabulary.json").read_text(encoding="utf-8"))["centroids"]
    if not np.allclose(snapshots[-1], final):
        raise ValueError("la última foto no coincide con vocabulary.json")

    sample = np.load(run / "sample.npy", mmap_mode="r")
    origins = np.load(run / "sample-files.npy") if (run / "sample-files.npy").exists() else None
    names = ([f"mfcc{i + 1}" for i in range(D)] if spec["extractor"]["extractor"] == "mfcc"
             else [f"d{i}" for i in range(D)])
    rng = np.random.default_rng(seed)
    sub = np.sort(rng.choice(len(sample), min(n_sub, len(sample)), replace=False))
    X = np.asarray(sample[sub], dtype=np.float64)
    labels = np.stack([assign(X, C) for C in snapshots])          # (T, n)
    sizes = np.array(report["result"]["cluster_sizes"])
    top = np.argsort(sizes, kind="stable")[::-1][:SLOTS]
    slot_of = np.full(K, -1)
    slot_of[top] = np.arange(len(top))

    print(f"t-SNE sobre {min(n_proj, len(X)):,} descriptores...", file=sys.stderr)
    proj = np.sort(rng.choice(len(X), min(n_proj, len(X)), replace=False))
    emb = TSNE(n_components=2, init="pca", perplexity=30, random_state=seed).fit_transform(X[proj])
    pca = PCA(n_components=2, random_state=seed).fit(X)
    traj = pca.transform(snapshots.reshape(-1, D)).reshape(T, K, 2)

    C = snapshots[-1]
    sq = (C * C).sum(1)
    dist = np.sqrt(np.maximum(sq[:, None] - 2 * C @ C.T + sq[None], 0))
    np.fill_diagonal(dist, np.inf)
    i, j = np.triu_indices(K, 1)
    closest = np.argsort(dist[i, j])[:5]

    y = np.where(np.isin(labels[-1], top), labels[-1], -1)
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.3, random_state=seed, stratify=y)
    tree = DecisionTreeClassifier(max_depth=4, class_weight="balanced", random_state=seed).fit(X_tr, y_tr)
    pred = tree.predict(X_te)

    data = {
        "meta": {
            "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "run": str(run), "dataset": spec["dataset"]["root"], "extractor": spec["extractor"]["extractor"],
            "descriptor_id": spec.get("descriptor_id"), "k": K, "d": D, "iterations": T - 1,
            "converged": report["result"]["converged"], "tolerance": spec["training"]["tolerance"],
            "sample": len(sample), "subsample": len(X), "projected": len(proj),
            "final_inertia": report["result"]["inertia"], "seed": spec["training"]["seed"],
        },
        "history": history,
        "churn": rounded((labels[1:] != labels[:-1]).mean(1), 6),
        "top": top.tolist(),
        "sizes": sizes.tolist(),
        "nearest": rounded(dist.min(1), 4),
        "pairs": [[int(i[p]), int(j[p]), round(float(dist[i[p], j[p]]), 4)] for p in closest],
        "proj": {
            "x": rounded(emb[:, 0], 2), "y": rounded(emb[:, 1], 2),
            "slots": [codes(slot_of[labels[t][proj]]) for t in range(T)],
            "final": labels[-1][proj].tolist(),
        },
        "pca": {
            "evr": rounded(pca.explained_variance_ratio_, 4),
            "bg": rounded(pca.transform(X[proj]), 3),
            "traj": [rounded(traj[:, c].ravel(), 3) for c in range(K)],
            "path": rounded(np.linalg.norm(np.diff(snapshots, axis=0), axis=2).sum(0), 4),
            "net": rounded(np.linalg.norm(snapshots[-1] - snapshots[0], axis=1), 4),
        },
        "surrogate": {
            "balanced": round(float(balanced_accuracy_score(y_te, pred)), 4),
            "accuracy": round(float((pred == y_te).mean()), 4),
            "chance": round(1 / (len(top) + 1), 4),
            "recall": rounded(recall_score(y_te, pred, labels=top, average=None, zero_division=0), 4),
            "rules": export_text(tree, feature_names=names, decimals=2),
        },
        "genres": genres(spec, tracks, origins, sub, proj, labels[-1]),
    }
    return data


def genres(spec, tracks, origins, sub, proj, final):
    if origins is None or not tracks.is_file():
        return None
    import pandas as pd
    table = pd.read_csv(tracks, index_col=0, header=[0, 1])
    track_ids = np.array([int(Path(f["path"]).stem) for f in spec["dataset"]["files"]])
    genre = table[("track", "genre_top")].reindex(track_ids[origins[sub]]).to_numpy()
    known = pd.notna(genre)
    names = sorted(set(genre[known]))
    if len(names) > SLOTS:
        raise ValueError(f"{len(names)} géneros: más que colores en la paleta")
    index = np.array([names.index(g) if ok else -1 for g, ok in zip(genre, known)])
    cross = pd.crosstab(final[known], genre[known])
    per_word = cross.sum(axis=1)
    biggest = per_word.sort_values(ascending=False).index[:30]
    purity = (cross.max(axis=1) / per_word)[per_word >= 50].sort_values(ascending=False).head(10)
    return {
        "names": names,
        "proj": codes(index[proj]),
        "purity": round(float(cross.max(axis=1).sum() / cross.values.sum()), 4),
        "baseline": round(float(cross.sum(axis=0).max() / cross.values.sum()), 4),
        "pure": [[int(w), round(float(p), 4), str(cross.loc[w].idxmax())] for w, p in purity.items()],
        "heat": {"clusters": [int(c) for c in biggest],
                 "shares": rounded(cross.loc[biggest].div(per_word[biggest], axis=0)
                                   .reindex(columns=names, fill_value=0).values, 4)},
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run", type=Path, default=ROOT / "data/modelos/kmeans_mfcc_hist",
                        help="carpeta de salida de entrenar_Kmeans.py")
    parser.add_argument("--tracks", type=Path, default=ROOT / "data/multimedia/audio/fma_metadata/tracks.csv",
                        help="tracks.csv de fma_metadata (opcional: activa la sección de géneros)")
    parser.add_argument("--salida", type=Path, help="HTML a escribir (default: <run>/aprendizaje.html)")
    parser.add_argument("--submuestra", type=int, default=20_000)
    parser.add_argument("--proyectados", type=int, default=5_000)
    parser.add_argument("--semilla", type=int, default=0)
    args = parser.parse_args(argv)
    try:
        data = export(args.run.resolve(), args.tracks, args.submuestra, args.proyectados, args.semilla)
    except (OSError, ValueError, KeyError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    template = TEMPLATE.read_text(encoding="utf-8")
    assert template.count(PLACEHOLDER) == 1, "la plantilla perdió el marcador de datos"
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"), allow_nan=False).replace("</", "<\\/")
    page = template.replace(PLACEHOLDER, PLACEHOLDER.replace("null", payload))
    output = args.salida or args.run / "aprendizaje.html"
    output.write_text(page, encoding="utf-8")
    print(f"Escrito {output} ({len(page) / 2**20:.1f} MiB)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
