"""Loads the internal procedures and ranks passages with BM25 (pure Python)."""
from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

STOPWORDS = set("""
a au aux avec ce ces cette dans de des du elle en est et il je la le les leur lui ma mais me mes
moi mon ne nos notre nous on ou par pas pour qu que qui sa se ses son sur ta te tes toi ton tu un si
une vos votre vous y d l j n s t c qu est-ce comment quel quelle quels quelles quoi faut faire
dois doit peut puis est sont été être avoir ai as avons avez ont the to of and
""".split())


def normalise(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def tokens(text: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+", normalise(text))
    out = []
    for w in words:
        if w in STOPWORDS or len(w) < 2:
            continue
        # light French stemming: plural and common verb endings
        for suffix in ("ements", "ement", "ations", "ation", "ees", "ee", "es", "s", "er", "ez"):
            if len(w) > len(suffix) + 3 and w.endswith(suffix):
                w = w[: -len(suffix)]
                break
        out.append(w)
    return out


@dataclass
class Passage:
    source: str
    title: str
    level: str
    text: str


def load_procedures(folder: Path) -> list[Passage]:
    """Each file has a small front matter (title, classification) and sections split by '## '."""
    passages: list[Passage] = []
    for path in sorted(folder.glob("*.md")):
        raw = path.read_text(encoding="utf-8")
        meta: dict[str, str] = {}
        body = raw
        if raw.startswith("---"):
            head, body = raw[3:].split("---", 1)
            for line in head.strip().splitlines():
                k, _, v = line.partition(":")
                meta[k.strip()] = v.strip()
        level = meta.get("classification", "C2")[:2]
        if level == "C4":
            continue  # secret documents are never indexed
        title = meta.get("title", path.stem)
        for section in re.split(r"\n(?=## )", body.strip()):
            section = section.strip()
            if section:
                passages.append(Passage(path.name, title, level, section))
    return passages


class BM25:
    def __init__(self, passages: list[Passage], k1: float = 1.4, b: float = 0.75):
        self.passages = passages
        self.docs = [tokens(p.title + " " + p.text) for p in passages]
        self.k1, self.b = k1, b
        self.avgdl = sum(len(d) for d in self.docs) / max(1, len(self.docs))
        df: dict[str, int] = {}
        for d in self.docs:
            for t in set(d):
                df[t] = df.get(t, 0) + 1
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def search(self, query: str, k: int = 3, allowed_levels: set[str] | None = None) -> list[tuple[float, Passage]]:
        q = tokens(query)
        scored = []
        for doc, p in zip(self.docs, self.passages):
            if allowed_levels is not None and p.level not in allowed_levels:
                continue
            tf: dict[str, int] = {}
            for t in doc:
                tf[t] = tf.get(t, 0) + 1
            s = 0.0
            for t in q:
                if t in tf:
                    f = tf[t]
                    s += self.idf.get(t, 0.0) * f * (self.k1 + 1) / (
                        f + self.k1 * (1 - self.b + self.b * len(doc) / self.avgdl))
            if s > 0:
                scored.append((s, p))
        scored.sort(key=lambda x: -x[0])
        return scored[:k]
