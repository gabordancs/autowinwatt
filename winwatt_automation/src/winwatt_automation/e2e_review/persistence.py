"""Crash-safe local review persistence with an append-only audit trail."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .domain import ReviewCandidate, ReviewStatus


class ReviewStore:
    def __init__(self, database: Path):
        self.database = database
        database.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(database)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS candidates (
              candidate_id TEXT PRIMARY KEY, payload_json TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS audit_events (
              event_id INTEGER PRIMARY KEY AUTOINCREMENT, candidate_id TEXT NOT NULL,
              action TEXT NOT NULL, before_json TEXT, after_json TEXT NOT NULL, at TEXT NOT NULL
            );
            """
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def seed(self, candidates: list[ReviewCandidate]) -> int:
        count = 0
        for candidate in candidates:
            existing = self.connection.execute("SELECT 1 FROM candidates WHERE candidate_id=?", (candidate.candidate_id,)).fetchone()
            if existing is None:
                self._write(candidate, "import", None)
                count += 1
        self.connection.commit()
        return count

    def _write(self, candidate: ReviewCandidate, action: str, before: ReviewCandidate | None) -> None:
        now = datetime.now(timezone.utc).isoformat()
        payload = json.dumps(candidate.to_dict(), ensure_ascii=False, sort_keys=True)
        self.connection.execute(
            "INSERT INTO candidates(candidate_id,payload_json,updated_at) VALUES(?,?,?) ON CONFLICT(candidate_id) DO UPDATE SET payload_json=excluded.payload_json,updated_at=excluded.updated_at",
            (candidate.candidate_id, payload, now),
        )
        self.connection.execute(
            "INSERT INTO audit_events(candidate_id,action,before_json,after_json,at) VALUES(?,?,?,?,?)",
            (candidate.candidate_id, action, json.dumps(before.to_dict(), ensure_ascii=False, sort_keys=True) if before else None, payload, now),
        )

    def get(self, candidate_id: str) -> ReviewCandidate:
        row = self.connection.execute("SELECT payload_json FROM candidates WHERE candidate_id=?", (candidate_id,)).fetchone()
        if row is None:
            raise KeyError(candidate_id)
        return ReviewCandidate.from_dict(json.loads(row["payload_json"]))

    def list(self, statuses: set[ReviewStatus] | None = None) -> list[ReviewCandidate]:
        rows = self.connection.execute("SELECT payload_json FROM candidates ORDER BY candidate_id").fetchall()
        values = [ReviewCandidate.from_dict(json.loads(row["payload_json"])) for row in rows]
        return [value for value in values if statuses is None or value.status in statuses]

    def transition(self, candidate_id: str, status: ReviewStatus, *, reviewer: str, reviewed_value: object = None, note: str | None = None) -> ReviewCandidate:
        before = self.get(candidate_id)
        after = before.transition(status, reviewer=reviewer, reviewed_value=reviewed_value, note=note)
        self._write(after, status.value, before)
        self.connection.commit()
        return after

    def replace(self, candidate: ReviewCandidate, *, action: str = "update") -> ReviewCandidate:
        """Persist derived evidence without changing machine/review values."""
        before=self.get(candidate.candidate_id)
        self._write(candidate,action,before)
        self.connection.commit()
        return candidate

    def audit(self, candidate_id: str | None = None) -> list[dict]:
        if candidate_id:
            rows = self.connection.execute("SELECT * FROM audit_events WHERE candidate_id=? ORDER BY event_id", (candidate_id,)).fetchall()
        else:
            rows = self.connection.execute("SELECT * FROM audit_events ORDER BY event_id").fetchall()
        return [dict(row) for row in rows]
