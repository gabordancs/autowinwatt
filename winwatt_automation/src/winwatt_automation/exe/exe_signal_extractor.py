from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from winwatt_automation.wwp.wwp_signal_extractor import (
    BOUNDARY_HINTS,
    OPENING_HINTS,
    ROOM_HINTS,
    SYSTEM_HINTS,
    load_ui_labels_from_snapshot,
)

ASCII_MIN_LEN = 4
UTF16_MIN_LEN = 4

GENERIC_FIELD_HINTS = [
    "name",
    "nev",
    "leiras",
    "description",
    "ertek",
    "value",
    "azonosito",
    "id",
    "width",
    "height",
    "temperature",
    "homerseklet",
    "power",
    "teljesitmeny",
    "volume",
    "terfogat",
    "notes",
    "megjegyzes",
]

NOISE_WORDS = {
    "http",
    "https",
    "microsoft",
    "kernel32",
    "version",
    "runtime",
    "debug",
    "release",
}


@dataclass
class StringCluster:
    key: str
    strings: list[str]


@dataclass
class EntityCandidate:
    kind: str
    confidence: float
    anchor_text: str
    related_texts: list[str]


def normalize_text(text: str) -> str:
    text = text.strip().strip("\x00")
    text = re.sub(r"\s+", " ", text)
    return text.casefold()


def _canonical_label(text: str) -> str:
    normalized = normalize_text(text)
    normalized = re.sub(r"\b\d+\b", "", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _is_noise(text: str, min_len: int) -> bool:
    cleaned = text.strip("\x00").strip()
    if len(cleaned) < min_len:
        return True

    if len(set(cleaned)) == 1:
        return True

    printable_ratio = sum(ch.isprintable() and not ch.isspace() for ch in cleaned) / max(len(cleaned), 1)
    if printable_ratio < 0.6:
        return True

    if re.fullmatch(r"[\W_]+", cleaned):
        return True

    if re.fullmatch(r"[A-Fa-f0-9]{8,}", cleaned):
        return True

    return False


def extract_exe_strings(
    path: str,
    *,
    min_len: int = ASCII_MIN_LEN,
    utf16_scan: bool = True,
    utf16_min_len: int = UTF16_MIN_LEN,
) -> list[str]:
    data = Path(path).read_bytes()
    found: list[str] = []

    ascii_pattern = rb"[\x20-\x7e\x80-\xff]{" + str(min_len).encode() + rb",}"
    for match in re.finditer(ascii_pattern, data):
        text = match.group(0).decode("latin-1", errors="ignore")
        text = text.strip("\x00").strip()
        if text and not _is_noise(text, min_len=min_len):
            found.append(text)

    if utf16_scan:
        i = 0
        n = len(data)
        while i + 1 < n:
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

            if len(chars) >= utf16_min_len:
                text = "".join(chr(c) for c in chars).strip("\x00").strip()
                if text and not _is_noise(text, min_len=utf16_min_len):
                    found.append(text)
            else:
                i = start + 1

    deduped: list[str] = []
    seen: set[str] = set()
    for item in found:
        norm = normalize_text(item)
        if norm and norm not in seen:
            seen.add(norm)
            deduped.append(item)

    return deduped


def _cluster_key(text: str) -> str:
    norm = normalize_text(text)
    parts = [p for p in re.split(r"[^\wáéíóöőúüű]+|_", norm) if p]
    if not parts:
        return norm[:10]
    return parts[0]


def cluster_exe_strings(strings: Iterable[str], min_cluster_size: int = 2) -> list[StringCluster]:
    grouped: dict[str, set[str]] = defaultdict(set)

    for value in strings:
        key = _cluster_key(value)
        grouped[key].add(value)

    clusters: list[StringCluster] = []
    for key, values in grouped.items():
        if len(values) < min_cluster_size:
            continue
        clusters.append(StringCluster(key=key, strings=sorted(values, key=normalize_text)))

    clusters.sort(key=lambda c: (-len(c.strings), c.key))
    return clusters


def infer_exe_entities(strings: Iterable[str]) -> list[EntityCandidate]:
    text_list = [s for s in strings if normalize_text(s)]

    hint_sets: dict[str, list[str]] = {
        "room": ROOM_HINTS,
        "panel": BOUNDARY_HINTS,
        "boundary": BOUNDARY_HINTS,
        "opening": OPENING_HINTS,
        "system": SYSTEM_HINTS,
        "generic_field": GENERIC_FIELD_HINTS,
    }

    matches: dict[str, list[tuple[str, float]]] = defaultdict(list)

    for text in text_list:
        norm = normalize_text(text)
        if norm in NOISE_WORDS:
            continue

        for kind, hints in hint_sets.items():
            hit_count = sum(1 for hint in hints if hint in norm)
            if hit_count == 0:
                continue
            score = min(0.95, 0.3 + 0.2 * hit_count)
            if any(ch.isdigit() for ch in text):
                score += 0.05
            matches[kind].append((text, min(score, 0.99)))

    entities: list[EntityCandidate] = []
    for kind, values in matches.items():
        values.sort(key=lambda x: x[1], reverse=True)
        anchor, confidence = values[0]
        related = [text for text, _ in values[:10]]
        entities.append(
            EntityCandidate(kind=kind, confidence=round(confidence, 3), anchor_text=anchor, related_texts=related)
        )

    entities.sort(key=lambda e: e.confidence, reverse=True)
    return entities


def _extract_texts_from_wwp_result(wwp_result: dict | list | None) -> set[str]:
    if not wwp_result:
        return set()

    values: set[str] = set()

    def walk(node: object) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "text" and isinstance(value, str):
                    values.add(value)
                elif key == "raw_hits" and isinstance(value, list):
                    for item in value:
                        if isinstance(item, dict) and isinstance(item.get("text"), str):
                            values.add(item["text"])
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(wwp_result)
    return values


def compare_exe_with_wwp(exe_strings: Iterable[str], wwp_result: dict | list | None) -> dict:
    exe_map = {_canonical_label(x): x for x in exe_strings if _canonical_label(x)}
    wwp_strings = _extract_texts_from_wwp_result(wwp_result)
    wwp_map = {_canonical_label(x): x for x in wwp_strings if _canonical_label(x)}

    common = sorted({exe_map[k] for k in exe_map.keys() & wwp_map.keys()}, key=normalize_text)
    exe_only = sorted({exe_map[k] for k in exe_map.keys() - wwp_map.keys()}, key=normalize_text)
    wwp_only = sorted({wwp_map[k] for k in wwp_map.keys() - exe_map.keys()}, key=normalize_text)

    return {
        "common_count": len(common),
        "exe_only_count": len(exe_only),
        "wwp_only_count": len(wwp_only),
        "common": common,
        "exe_only": exe_only,
        "wwp_only": wwp_only,
    }


def compare_exe_with_ui(exe_strings: Iterable[str], ui_labels: Iterable[str]) -> dict:
    exe_map = {_canonical_label(x): x for x in exe_strings if _canonical_label(x)}
    ui_map = {_canonical_label(x): x for x in ui_labels if _canonical_label(x)}

    confirmed = sorted(
        [{"exe": exe_map[norm], "ui": ui_map[norm], "norm": norm} for norm in exe_map.keys() & ui_map.keys()],
        key=lambda x: x["norm"],
    )
    hidden = sorted({exe_map[k] for k in exe_map.keys() - ui_map.keys()}, key=normalize_text)
    ui_only = sorted({ui_map[k] for k in ui_map.keys() - exe_map.keys()}, key=normalize_text)

    return {
        "confirmed_labels": confirmed,
        "confirmed_count": len(confirmed),
        "hidden_exe_strings": hidden,
        "hidden_count": len(hidden),
        "ui_only": ui_only,
        "ui_only_count": len(ui_only),
    }


def collect_top_tokens(strings: Iterable[str], top_n: int = 20) -> list[tuple[str, int]]:
    counter: Counter[str] = Counter()
    for value in strings:
        for token in re.findall(r"[\wáéíóöőúüű]+", normalize_text(value)):
            if len(token) >= 3:
                counter[token] += 1
    return counter.most_common(top_n)


def result_to_json(
    *,
    strings: list[str],
    clusters: list[StringCluster],
    entities: list[EntityCandidate],
    comparisons: dict | None = None,
) -> dict:
    return {
        "strings": strings,
        "clusters": [asdict(cluster) for cluster in clusters],
        "inferred_entities": [asdict(entity) for entity in entities],
        "comparisons": comparisons or {},
    }


def load_json(path: str | Path) -> dict | list:
    return json.loads(Path(path).read_text(encoding="utf-8"))


__all__ = [
    "ASCII_MIN_LEN",
    "UTF16_MIN_LEN",
    "EntityCandidate",
    "StringCluster",
    "cluster_exe_strings",
    "collect_top_tokens",
    "compare_exe_with_ui",
    "compare_exe_with_wwp",
    "extract_exe_strings",
    "infer_exe_entities",
    "load_json",
    "load_ui_labels_from_snapshot",
    "result_to_json",
]
