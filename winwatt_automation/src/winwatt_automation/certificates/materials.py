"""Deterministic local material matching against a WinWatt catalogue.

The matcher prefers a catalogue object only when source name/family and every
available physical property agree. Weak evidence stays a review item; it never
creates an invented material.
"""
from __future__ import annotations

import re
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path

from .models import MaterialCandidate, MaterialDecision


def _normal(value: str) -> str:
    text = unicodedata.normalize("NFD", value.casefold())
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())


def _number(value: str | None) -> float | None:
    try:
        result = float((value or "").replace(",", "."))
    except ValueError:
        return None
    return result if result > 0 else None


def load_catalog(path: Path) -> list[MaterialCandidate]:
    raw = path.read_bytes()
    encoding = re.search(br'encoding=["\']([^"\']+)', raw[:200])
    text = raw.decode(encoding.group(1).decode("ascii") if encoding else "utf-8", errors="replace")
    root = ET.fromstring(re.sub(r"<\?xml[^>]+\?>", "", text).strip())
    result: list[MaterialCandidate] = []
    for item in root.iter("WinWatt32Material"):
        header = item.find("ItemHeader")
        result.append(MaterialCandidate(
            name=(header.findtext("ItemName") if header is not None else "") or "",
            material_id=header.findtext("ID") if header is not None else None,
            path=header.findtext("ItemPath") if header is not None else None,
            lambda_wmk=_number(item.findtext("ThermalCond")),
            density_kgm3=_number(item.findtext("Density")),
            heat_capacity_kjkgk=_number(item.findtext("HeatCapacity")),
        ))
    return result


def _relative_agreement(source: float | None, candidate: float | None) -> float | None:
    if source is None or candidate is None:
        return None
    return max(0.0, 1.0 - abs(source - candidate) / max(abs(source), abs(candidate), 1e-9))


def material_family(name: str) -> str | None:
    text = _normal(name)
    rules = (("air_gap", ("legreteg",)), ("metal", ("femlemez", "trapezlemez", "acellemez")),
             ("eps", ("polisztirol", "expandalt ps", "eps")), ("xps", ("xps",)),
             ("bitumen", ("vizszigeteles", "bitumen", "parazaro")), ("pe", ("polietilen", "elvalaszto reteg", "pe folia")),
             ("concrete", ("beton", "vasbeton", "szerelobeton", "aljzatbeton")), ("brick", ("tegla",)),
             ("plaster", ("vakolat", "ragaszto")), ("gravel", ("kavics",)), ("ceramic", ("keramia", "burkolat")), ("slag", ("salak",)))
    return next((family for family, terms in rules if any(term in text for term in terms)), None)


def match_material(
    source_name: str,
    catalog: list[MaterialCandidate],
    *,
    lambda_wmk: float | None = None,
    density_kgm3: float | None = None,
    heat_capacity_kjkgk: float | None = None,
    family: str | None = None,
) -> MaterialDecision:
    """Rank local candidates from source text plus known physical data."""
    # ``family`` is a classification hint, not part of the material name.
    # Adding it to the token set used to dilute exact names such as
    # "kavicsfeltöltés" when a source model supplied a verbose layer type.
    query = _normal(source_name)
    source_family = material_family(query) or material_family(family or "")
    if source_family == "air_gap":
        return MaterialDecision(source_name=source_name, status="special", confidence=1, decision_mode="special", reason="Zárt légrés: WinWatt rétegellenállásként kezelendő, nem normál katalogizált anyag.")
    tokens = {token for token in query.split() if len(token) > 2}
    ranked: list[tuple[float, MaterialCandidate, str, float | None, float]] = []
    for candidate in catalog:
        if source_family and material_family(f"{candidate.name} {candidate.path or ''}") != source_family:
            continue
        candidate_tokens = set(_normal(f"{candidate.name} {candidate.path or ''}").split())
        name_score = len(tokens & candidate_tokens) / len(tokens) if tokens else 0.0
        values = [
            _relative_agreement(lambda_wmk, candidate.lambda_wmk),
            _relative_agreement(density_kgm3, candidate.density_kgm3),
            _relative_agreement(heat_capacity_kjkgk, candidate.heat_capacity_kjkgk),
        ]
        known = [item for item in values if item is not None]
        physical = sum(known) / len(known) if known else None
        score = 0.55 * name_score + (0.45 * physical if physical is not None else 0.0)
        details = f"név={name_score:.0%}" + (f", fizika={physical:.0%}" if physical is not None else ", fizika=hiányos")
        ranked.append((score, candidate, details, values[0], name_score))
    score, candidate, details, lambda_agreement, name_score = max(ranked, default=(0.0, None, "nincs katalógus", None, 0.0), key=lambda item: item[0])
    if candidate is None:
        return MaterialDecision(source_name=source_name, status="review", reason="Nincs azonos anyagcsalád a helyi katalógusban; új anyag nem készült.")
    # With no supplied physics an exact catalogue name is still a safe local
    # match; partial prose matches require the combined threshold above.
    if (score >= 0.72 or name_score >= 0.95) and not (lambda_agreement is not None and lambda_agreement < 0.65):
        return MaterialDecision(source_name=source_name, status="catalog", candidate=candidate, confidence=round(score, 3), decision_mode="catalog_match", reason=f"Helyi katalógus-egyezés: {details}.")
    return MaterialDecision(source_name=source_name, status="review", candidate=candidate, confidence=round(score, 3), reason=f"Nem elég biztos katalógus-egyezés ({details}); ellenőrzés szükséges, új anyag nem készült.")


def match_by_name(source_name: str, catalog: list[MaterialCandidate]) -> MaterialDecision:
    """Compatibility wrapper for sparse PDF text; no physics is presumed."""
    return match_material(source_name, catalog)
