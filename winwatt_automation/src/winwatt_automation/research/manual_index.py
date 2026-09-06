from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pypdf import PdfReader

from .models import ResearchSource


class ManualIndex:
    """A deliberately small, reproducible lexical index for one PDF manual."""

    def __init__(self, source_path: Path, index_path: Path) -> None:
        self.source_path = source_path.resolve()
        self.index_path = index_path.resolve()
        self.source: ResearchSource | None = None
        self.chunks: list[dict[str, Any]] = []

    @staticmethod
    def _heading(lines: list[str]) -> str | None:
        for line in lines[:8]:
            compact = " ".join(line.split())
            if 3 <= len(compact) <= 100 and not re.search(r"[.!?]$", compact) and sum(char.isalpha() for char in compact) >= 3:
                return compact
        return None

    @staticmethod
    def _chunks(text: str, size: int = 900) -> list[str]:
        words = text.split()
        chunks: list[str] = []
        current: list[str] = []
        length = 0
        for word in words:
            if current and length + len(word) + 1 > size:
                chunks.append(" ".join(current))
                current, length = [], 0
            current.append(word)
            length += len(word) + 1
        if current:
            chunks.append(" ".join(current))
        return chunks

    def build(self) -> ResearchSource:
        if not self.source_path.is_file():
            raise FileNotFoundError(f"Manual PDF not found: {self.source_path}")
        reader = PdfReader(str(self.source_path))
        pages = [page.extract_text() or "" for page in reader.pages]
        return self.build_from_pages(pages)

    def build_from_pages(self, pages: list[str]) -> ResearchSource:
        digest = hashlib.sha256(self.source_path.read_bytes()).hexdigest() if self.source_path.is_file() else hashlib.sha256("\n".join(pages).encode()).hexdigest()
        source = ResearchSource(
            id=f"manual:winwatt:{digest[:12]}", type="manual", title=self.source_path.stem,
            path=str(self.source_path), version=digest[:12],
            metadata={"sha256": digest, "page_count": len(pages)},
        )
        chunks: list[dict[str, Any]] = []
        current_heading: str | None = None
        for number, text in enumerate(pages, start=1):
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            heading = self._heading(lines)
            if heading:
                current_heading = heading
            for position, chunk in enumerate(self._chunks("\n".join(lines))):
                chunks.append({"chunk_id": f"p{number:03d}-c{position:02d}", "page": number, "heading": current_heading, "text": chunk})
        payload = {"format": "manual_index_v0", "built_at": datetime.now(timezone.utc).isoformat(), "source": source.model_dump(mode="json"), "chunks": chunks}
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        self.index_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self.source = source
        self.chunks = chunks
        return source

    def load(self) -> dict[str, Any]:
        payload = json.loads(self.index_path.read_text(encoding="utf-8"))
        self.source = ResearchSource.model_validate(payload["source"])
        self.chunks = list(payload["chunks"])
        return payload

    def search(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        query_terms = [term for term in re.findall(r"\w+", query.casefold()) if term]
        if not query_terms:
            return []
        index = self.load()
        phrase = " ".join(query_terms)
        scored: list[tuple[int, dict[str, Any]]] = []
        for chunk in index["chunks"]:
            haystack = f"{chunk.get('heading') or ''} {chunk['text']}".casefold()
            matches = sum(haystack.count(term) for term in query_terms)
            if matches:
                score = matches + (len(query_terms) * 3 if phrase in haystack else 0)
                scored.append((score, chunk))
        return [
            {"source_id": index["source"]["id"], "page": item["page"], "heading": item.get("heading"), "excerpt": item["text"], "score": score}
            for score, item in sorted(scored, key=lambda pair: (-pair[0], pair[1]["page"], pair[1]["chunk_id"]))[:limit]
        ]
