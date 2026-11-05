"""Corpus sintético con juicios de relevancia para el benchmark de texto (parte 3).

Cada documento pertenece a un tema; los temas se agrupan en familias que comparten
vocabulario. Un documento es relevante para una consulta si es del mismo tema que
ella. Las palabras son pseudopalabras con raíces distintas, para que el stemming no
mezcle temas por accidente; los conectores son stopwords reales del español.
"""

import argparse
import csv
import itertools
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from engine.fulltext.preprocess import raiz, stopwords

DOCS_PER_TOPIC = 15
TOPICS_PER_FAMILY = 10
TOPIC_TERMS = 6
FAMILY_TERMS = 40
BACKGROUND_TERMS = 5_000
LENGTH = (40, 160)
# Probabilidad de cada fuente por token; el resto es vocabulario de fondo (Zipf).
P_STOP, P_TOPIC, P_FAMILY, P_OTHER = 0.25, 0.12, 0.15, 0.04
QUERY_LENGTHS = {"1": (1, 1), "3": (3, 3), "5+": (5, 7)}
QUERIES_PER_LENGTH = 50
P_QUERY_BACKGROUND = 0.25
CONNECTORS = ("de", "la", "que", "el", "en", "y", "a", "los", "se", "del", "las", "un", "por", "con", "una", "su", "para", "al", "lo", "como")
CONSONANTS, VOWELS, ENDINGS = "bcdfglmnprstvz", "aeiou", ("", "", "n", "r", "s", "l")


def vocabulary(rng, size, used):
    words = []
    while len(words) < size:
        word = "".join(rng.choice(CONSONANTS) + rng.choice(VOWELS) for _ in range(rng.randint(2, 4))) + rng.choice(ENDINGS)
        stem = raiz(word)
        if word not in stopwords() and stem not in used:
            used.add(stem)
            words.append(word)
    return words


def generate(size, seed, output_dir):
    rng = random.Random(seed + size)
    topics = max(1, round(size / DOCS_PER_TOPIC))
    families = max(1, round(topics / TOPICS_PER_FAMILY))
    used = set()
    background = vocabulary(rng, BACKGROUND_TERMS, used)
    background_weights = list(itertools.accumulate(1 / rank for rank in range(1, BACKGROUND_TERMS + 1)))
    family_words = [vocabulary(rng, FAMILY_TERMS, used) for _ in range(families)]
    topic_words = [vocabulary(rng, TOPIC_TERMS, used) for _ in range(topics)]
    family_of = [topic % families for topic in range(topics)]
    thresholds = list(itertools.accumulate((P_STOP, P_TOPIC, P_FAMILY, P_OTHER)))

    doc_topics = [rng.randrange(topics) for _ in range(size)]
    with (output_dir / f"text_docs_{size}.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(("id", "topic", "text"))
        for doc_id, topic in enumerate(doc_topics):
            length = rng.randint(*LENGTH)
            tokens = rng.choices(background, cum_weights=background_weights, k=length)
            for position in range(length):
                draw = rng.random()
                if draw < thresholds[0]:
                    tokens[position] = rng.choice(CONNECTORS)
                elif draw < thresholds[1]:
                    tokens[position] = rng.choice(topic_words[topic])
                elif draw < thresholds[2]:
                    tokens[position] = rng.choice(family_words[family_of[topic]])
                elif draw < thresholds[3]:
                    tokens[position] = rng.choice(topic_words[rng.randrange(topics)])
            writer.writerow((doc_id, topic, " ".join(tokens) + "."))

    sizes = [0] * topics
    for topic in doc_topics:
        sizes[topic] += 1
    candidates = [topic for topic in range(topics) if sizes[topic] >= 5]
    with (output_dir / f"text_queries_{size}.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(("id", "length", "topic", "text"))
        query_id = 0
        for label, (low, high) in QUERY_LENGTHS.items():
            for _ in range(QUERIES_PER_LENGTH):
                topic = rng.choice(candidates)
                target = rng.randint(low, high)
                words = []
                # Términos distintos: el primero es del tema (60 %) o de su familia (40 %); los demás
                # pueden ser además palabras generales (25 %), cuyos postings crecen con la colección.
                while len(words) < target:
                    draw = rng.random()
                    if words and draw < P_QUERY_BACKGROUND:
                        word = rng.choices(background, cum_weights=background_weights)[0]
                    else:
                        pool = topic_words[topic] if rng.random() < .6 else family_words[family_of[topic]]
                        word = rng.choice(pool)
                    if word not in words:
                        words.append(word)
                writer.writerow((query_id, label, topic, " ".join(words)))
                query_id += 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sizes", nargs="+", type=int, default=[1_000, 10_000, 100_000])
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).resolve().parent / "generated")
    args = parser.parse_args()
    if any(size < DOCS_PER_TOPIC * 5 for size in args.sizes):
        parser.error(f"los tamaños deben ser >= {DOCS_PER_TOPIC * 5}")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for size in args.sizes:
        generate(size, args.seed, args.output_dir)


if __name__ == "__main__":
    main()
