from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable

ASCII_MIN_LEN = 4
UTF16_MIN_LEN = 4

DEFAULT_STOPWORDS = {
    "false",
    "true",
    "yes",
    "no",
    "null",
    "none",
    "itemheader",
    "itemname",
    "itempath",
    "id",
    "type",
    "name",
    "path",
    "project",
    "room",
    "panel",
    "form",
    "data",
    "calc",
    "window",
    "button",
}


@dataclass
class RawStringHit:
    text: str
    start: int
    end: int
    encoding: str
    score: float


@dataclass
class StringCluster:
    start: int
    end: int
    hits: list[RawStringHit] = field(default_factory=list)

    @property
    def span(self) -> int:
        return self.end - self.start

    @property
    def unique_texts(self) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for hit in self.hits:
            key = normalize_text(hit.text)
            if key and key not in seen:
                seen.add(key)
                out.append(hit.text)
        return out

    @property
    def summary(self) -> str:
        texts = self.unique_texts[:5]
        return " | ".join(texts)


@dataclass
class EntityCandidate:
    kind: str
    confidence: float
    anchor_text: str
    related_texts: list[str]
    cluster_start: int
    cluster_end: int


@dataclass
class ExtractionResult:
    file_path: str
    file_size: int
    raw_hits: list[RawStringHit]
    clusters: list[StringCluster]
    entities: list[EntityCandidate]
    frequent_strings: list[tuple[str, int]]

    def to_json_dict(self) -> dict:
        return {
            "file_path": self.file_path,
            "file_size": self.file_size,
            "raw_hits": [asdict(x) for x in self.raw_hits],
            "clusters": [
                {
                    "start": c.start,
                    "end": c.end,
                    "span": c.span,
                    "summary": c.summary,
                    "hits": [asdict(h) for h in c.hits],
                }
                for c in self.clusters
            ],
            "entities": [asdict(x) for x in self.entities],
            "frequent_strings": self.frequent_strings,
        }


def normalize_text(text: str) -> str:
    text = text.strip().strip("\x00")
    text = re.sub(r"\s+", " ", text)
    return text.casefold()


def is_probably_interesting(text: str, stopwords: set[str] | None = None) -> bool:
    stopwords = stopwords or DEFAULT_STOPWORDS
    t = normalize_text(text)

    if len(t) < 2:
        return False
    if t in stopwords:
        return False

    alnum_ratio = sum(ch.isalnum() for ch in t) / max(len(t), 1)
    if alnum_ratio < 0.35:
        return False

    if t.isdigit():
        return False

    if len(set(t)) == 1:
        return False

    return True


def score_text(text: str) -> float:
    t = text.strip()

    score = 0.0
    if len(t) >= 4:
        score += 1.0
    if any(ch.isalpha() for ch in t):
        score += 1.0
    if any(ch.isupper() for ch in t):
        score += 0.2
    if any(ch.isdigit() for ch in t):
        score += 0.2
    if any(ch in "áéíóöőúüűÁÉÍÓÖŐÚÜŰ" for ch in t):
        score += 0.5
    if " " in t:
        score += 0.3

    lower = t.casefold()
    if re.fullmatch(r"[a-z0-9_./\\:-]+", lower):
        score -= 0.3

    return score


def extract_ascii_strings(data: bytes, min_len: int = ASCII_MIN_LEN) -> list[RawStringHit]:
    pattern = rb"[\x20-\x7e\x80-\xff]{" + str(min_len).encode() + rb",}"
    hits: list[RawStringHit] = []

    for match in re.finditer(pattern, data):
        raw = match.group(0)
        text = raw.decode("latin-1", errors="ignore").strip("\x00").strip()
        if not text:
            continue
        hits.append(
            RawStringHit(
                text=text,
                start=match.start(),
                end=match.end(),
                encoding="latin-1",
                score=score_text(text),
            )
        )
    return hits


def extract_utf16le_strings(data: bytes, min_len: int = UTF16_MIN_LEN) -> list[RawStringHit]:
    hits: list[RawStringHit] = []
    i = 0
    n = len(data)

    while i < n - 2:
        start = i
        chars: list[int] = []

        while i + 1 < n:
            lo = data[i]
            hi = data[i + 1]

            if hi == 0 and 32 <= lo <= 126:
                chars.append(lo)
                i += 2
                continue

            codepoint = lo + (hi << 8)
            if 160 <= codepoint <= 687:
                chars.append(codepoint)
                i += 2
                continue

            break

        if len(chars) >= min_len:
            text = "".join(chr(c) for c in chars).strip("\x00").strip()
            if text:
                hits.append(
                    RawStringHit(
                        text=text,
                        start=start,
                        end=i,
                        encoding="utf-16le",
                        score=score_text(text) + 0.2,
                    )
                )
        else:
            i = start + 1

    return hits


def deduplicate_hits(hits: Iterable[RawStringHit], window: int = 6) -> list[RawStringHit]:
    ordered = sorted(hits, key=lambda x: (x.start, x.end, x.encoding))
    out: list[RawStringHit] = []

    for hit in ordered:
        norm = normalize_text(hit.text)
        duplicate = False

        for prev in reversed(out[-20:]):
            if abs(hit.start - prev.start) <= window and normalize_text(prev.text) == norm:
                duplicate = True
                if hit.score > prev.score:
                    out.remove(prev)
                    out.append(hit)
                break

        if not duplicate:
            out.append(hit)

    return sorted(out, key=lambda x: x.start)


def filter_hits(hits: Iterable[RawStringHit], stopwords: set[str] | None = None) -> list[RawStringHit]:
    return [hit for hit in hits if is_probably_interesting(hit.text, stopwords=stopwords)]


def cluster_hits(hits: list[RawStringHit], max_gap: int = 192) -> list[StringCluster]:
    if not hits:
        return []

    hits = sorted(hits, key=lambda x: x.start)
    clusters: list[StringCluster] = []

    current = StringCluster(start=hits[0].start, end=hits[0].end, hits=[hits[0]])

    for hit in hits[1:]:
        gap = hit.start - current.end
        if gap <= max_gap:
            current.hits.append(hit)
            current.end = max(current.end, hit.end)
        else:
            clusters.append(current)
            current = StringCluster(start=hit.start, end=hit.end, hits=[hit])

    clusters.append(current)
    return clusters


ROOM_HINTS = [
    "nappali",
    "konyha",
    "szoba",
    "háló",
    "halo",
    "fürdő",
    "furdo",
    "wc",
    "előtér",
    "eloter",
    "közlekedő",
    "kozlekedo",
    "kamra",
    "garázs",
    "garazs",
    "tetőtér",
    "tetoter",
]

OPENING_HINTS = [
    "ablak",
    "ajtó",
    "ajto",
    "erkélyajtó",
    "erkelyajto",
    "tetőablak",
    "tetoablak",
]

SYSTEM_HINTS = [
    "kazán",
    "kazan",
    "radiátor",
    "radiator",
    "hőszivattyú",
    "hoszivattyu",
    "padlófűtés",
    "padlofutes",
    "bojler",
    "split",
    "fan-coil",
    "fan coil",
]

BOUNDARY_HINTS = [
    "fal",
    "födém",
    "fodem",
    "padló",
    "padlo",
    "tető",
    "teto",
    "külső",
    "kulso",
    "homlokzat",
    "panel",
    "födémszerkezet",
    "rétegrend",
    "retegrend",
]


def infer_kind(texts: list[str]) -> tuple[str, float]:
    joined = " | ".join(normalize_text(text) for text in texts)

    def match_score(hints: list[str]) -> float:
        return sum(1.0 for hint in hints if hint in joined)

    scores = {
        "room": match_score(ROOM_HINTS),
        "opening": match_score(OPENING_HINTS),
        "system": match_score(SYSTEM_HINTS),
        "boundary": match_score(BOUNDARY_HINTS),
    }

    kind, best = max(scores.items(), key=lambda x: x[1])
    if best <= 0:
        return "unknown", 0.15

    confidence = min(0.95, 0.35 + best * 0.18)
    return kind, confidence


def infer_entities(clusters: list[StringCluster]) -> list[EntityCandidate]:
    entities: list[EntityCandidate] = []

    for cluster in clusters:
        texts = cluster.unique_texts
        if not texts:
            continue

        anchor = max(texts, key=lambda text: score_text(text))
        kind, confidence = infer_kind(texts)

        if kind == "unknown":
            labelish = [text for text in texts if len(text.strip()) >= 4 and any(ch.isalpha() for ch in text)]
            if labelish:
                kind = "label_group"
                confidence = 0.30

        entities.append(
            EntityCandidate(
                kind=kind,
                confidence=confidence,
                anchor_text=anchor,
                related_texts=texts[:12],
                cluster_start=cluster.start,
                cluster_end=cluster.end,
            )
        )

    return entities


def collect_frequent_strings(hits: list[RawStringHit], top_n: int = 40) -> list[tuple[str, int]]:
    counter = Counter(normalize_text(hit.text) for hit in hits if len(normalize_text(hit.text)) >= 3)
    common = []
    for text, count in counter.most_common(top_n):
        if count >= 2:
            common.append((text, count))
    return common


def extract_wwp_signals(
    file_path: str | Path,
    *,
    ascii_min_len: int = ASCII_MIN_LEN,
    utf16_min_len: int = UTF16_MIN_LEN,
    cluster_gap: int = 192,
    stopwords: set[str] | None = None,
) -> ExtractionResult:
    path = Path(file_path)
    data = path.read_bytes()

    hits: list[RawStringHit] = []
    hits.extend(extract_ascii_strings(data, min_len=ascii_min_len))
    hits.extend(extract_utf16le_strings(data, min_len=utf16_min_len))

    hits = deduplicate_hits(hits)
    hits = filter_hits(hits, stopwords=stopwords)
    clusters = cluster_hits(hits, max_gap=cluster_gap)
    entities = infer_entities(clusters)
    frequent = collect_frequent_strings(hits)

    return ExtractionResult(
        file_path=str(path),
        file_size=len(data),
        raw_hits=hits,
        clusters=clusters,
        entities=entities,
        frequent_strings=frequent,
    )


def compare_with_ui_labels(extraction: ExtractionResult, ui_labels: Iterable[str]) -> dict:
    ui_norm = {normalize_text(x): x for x in ui_labels if normalize_text(x)}
    wwp_norm = {normalize_text(hit.text): hit.text for hit in extraction.raw_hits if normalize_text(hit.text)}

    matched = []
    only_in_wwp = []
    only_in_ui = []

    for norm, original in wwp_norm.items():
        if norm in ui_norm:
            matched.append({"norm": norm, "wwp": original, "ui": ui_norm[norm]})
        else:
            only_in_wwp.append(original)

    for norm, original in ui_norm.items():
        if norm not in wwp_norm:
            only_in_ui.append(original)

    return {
        "matched_count": len(matched),
        "only_in_wwp_count": len(only_in_wwp),
        "only_in_ui_count": len(only_in_ui),
        "matched": sorted(matched, key=lambda x: x["norm"]),
        "only_in_wwp": sorted(set(only_in_wwp)),
        "only_in_ui": sorted(set(only_in_ui)),
    }


def save_result_json(result: ExtractionResult, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.write_text(json.dumps(result.to_json_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_ui_labels_from_snapshot(snapshot_path: str | Path) -> list[str]:
    data = json.loads(Path(snapshot_path).read_text(encoding="utf-8"))
    labels: list[str] = []

    def walk(node: object) -> None:
        if isinstance(node, dict):
            for key in ("text", "label", "name", "title", "caption"):
                value = node.get(key)
                if isinstance(value, str) and value.strip():
                    labels.append(value.strip())
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(data)
    return labels


def print_console_summary(result: ExtractionResult) -> None:
    print(f"Fájl: {result.file_path}")
    print(f"Méret: {result.file_size} byte")
    print(f"Kinyert stringek: {len(result.raw_hits)}")
    print(f"Klaszterek: {len(result.clusters)}")
    print(f"Entitásjelöltek: {len(result.entities)}")
    print()

    print("Leggyakoribb stringek:")
    for text, count in result.frequent_strings[:15]:
        print(f"  {count:>3}x  {text}")

    print()
    print("Top entitásjelöltek:")
    for entity in sorted(result.entities, key=lambda e: e.confidence, reverse=True)[:20]:
        related = " | ".join(entity.related_texts[:4])
        print(
            f"  [{entity.kind:<10}] conf={entity.confidence:.2f} "
            f"anchor={entity.anchor_text!r} "
            f"range=({entity.cluster_start}-{entity.cluster_end}) "
            f"related={related}"
        )
