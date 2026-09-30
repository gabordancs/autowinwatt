#!/usr/bin/env python
"""Local-only worker for the WebWatt certificate intake queue.

It deliberately stops after deterministic source extraction and material
matching.  It never starts WinWatt, imports native XML or creates a WWP.
Those actions require a later, explicitly approved job type and a reviewed
geometry model.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any

# The worker is usable both from the project's virtual environment and directly
# from a checked-out repository during first-time setup.
SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from winwatt_automation.workflows.webwatt_certificate_intake import MANIFEST_NAME, process_local_intake, sha256
from winwatt_automation.workflows.webwatt_publisher import publish_review_artifacts

BUCKET = "project-documents"
JOB_TYPE = "certificate_intake"
MAX_ERROR_LENGTH = 1500


class SupabaseRest:
    def __init__(self, url: str, service_key: str) -> None:
        self.url = url.rstrip("/")
        self.headers = {"apikey": service_key, "Authorization": f"Bearer {service_key}"}

    def request(self, method: str, path: str, payload: Any | None = None, headers: dict[str, str] | None = None) -> Any:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        request_headers = {**self.headers, **(headers or {})}
        if payload is not None:
            request_headers.setdefault("Content-Type", "application/json")
        request = urllib.request.Request(f"{self.url}{path}", data=body, headers=request_headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                raw = response.read()
                return json.loads(raw.decode("utf-8")) if raw else None
        except urllib.error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Supabase {method} {path}: HTTP {exc.code}: {details[:500]}") from exc

    def rpc(self, name: str, payload: dict[str, Any]) -> Any:
        return self.request("POST", f"/rest/v1/rpc/{name}", payload)

    def download(self, storage_path: str, destination: Path) -> None:
        encoded = "/".join(urllib.parse.quote(part, safe="") for part in storage_path.split("/"))
        request = urllib.request.Request(f"{self.url}/storage/v1/object/{BUCKET}/{encoded}", headers=self.headers)
        with urllib.request.urlopen(request, timeout=120) as response:
            destination.write_bytes(response.read())

    def upload(self, storage_path: str, source: Path) -> None:
        encoded = "/".join(urllib.parse.quote(part, safe="") for part in storage_path.split("/"))
        request = urllib.request.Request(
            f"{self.url}/storage/v1/object/{BUCKET}/{encoded}", data=source.read_bytes(), method="POST",
            headers={**self.headers, "Content-Type": "application/json" if source.suffix == ".json" else "application/octet-stream", "x-upsert": "false"},
        )
        with urllib.request.urlopen(request, timeout=120):
            pass

    def storage_object_exists(self, storage_path: str) -> bool:
        encoded = "/".join(urllib.parse.quote(part, safe="") for part in storage_path.split("/"))
        request = urllib.request.Request(
            f"{self.url}/storage/v1/object/{BUCKET}/{encoded}", method="HEAD", headers=self.headers,
        )
        try:
            with urllib.request.urlopen(request, timeout=60):
                return True
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return False
            raise

    def upload_if_missing(self, storage_path: str, source: Path) -> bool:
        if self.storage_object_exists(storage_path):
            return False
        try:
            self.upload(storage_path, source)
            return True
        except urllib.error.HTTPError as exc:
            if exc.code == 409:
                return False
            raise

    def find_document_id(self, *, project_id: str, storage_path: str) -> str | None:
        query = urllib.parse.urlencode({
            "select": "id", "project_id": f"eq.{project_id}",
            "file_url": f"eq.{storage_path}", "limit": "1",
        })
        result = self.request("GET", f"/rest/v1/project_documents?{query}")
        return str(result[0]["id"]) if result else None

    def ensure_document(
        self, *, project_id: str, user_id: str, doc_type: str, storage_path: str,
    ) -> tuple[str, bool]:
        existing = self.find_document_id(project_id=project_id, storage_path=storage_path)
        if existing is not None:
            return existing, False
        deterministic_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"webwatt:{project_id}:{storage_path}"))
        result = self.request("POST", "/rest/v1/project_documents", [{
            "id": deterministic_id, "project_id": project_id, "created_by": user_id,
            "doc_type": doc_type, "status": "draft", "file_url": storage_path,
        }], {"Prefer": "resolution=ignore-duplicates,return=representation"})
        return deterministic_id, bool(result)

    def insert_document(self, *, project_id: str, user_id: str, doc_type: str, storage_path: str) -> str:
        result = self.request("POST", "/rest/v1/project_documents", [{
            "project_id": project_id, "created_by": user_id, "doc_type": doc_type,
            "status": "draft", "file_url": storage_path,
        }], {"Prefer": "return=representation"})
        return result[0]["id"]


def safe_filename(name: str) -> str:
    return "".join(char if char.isalnum() or char in "._-" else "_" for char in name)


def process_job(api: SupabaseRest, job: dict[str, Any], workspace_root: Path, catalog_xml: Path | None) -> dict[str, Any]:
    payload = job.get("input_payload") or {}
    if payload.get("operation") != "certificate_intake":
        raise ValueError("This worker accepts only certificate_intake jobs.")
    project_id = job.get("project_id")
    user_id = job.get("user_id")
    source_path = payload.get("source_storage_path")
    filename = str(payload.get("source_filename") or "source")
    if not all(isinstance(value, str) and value for value in (project_id, user_id, source_path)):
        raise ValueError("Job is missing project_id, user_id or source_storage_path.")

    job_dir = workspace_root / str(job["id"])
    output_dir = job_dir / "result"
    job_dir.mkdir(parents=True, exist_ok=True)
    source = job_dir / safe_filename(filename)
    api.download(source_path, source)
    intake = process_local_intake(source=source, output_dir=output_dir, catalog_xml=catalog_xml)

    artifacts = publish_review_artifacts(
        api=api, output_dir=output_dir, project_id=project_id,
        user_id=user_id, job_id=str(job["id"]),
    )
    return {
        "operation": "certificate_intake", "review_required": True,
        "winwatt_started": False, "llm_used": False, "artifacts": artifacts,
        "summary": intake["summary"], "source_sha256": intake["source"]["sha256"],
        "local_manifest_sha256": sha256(output_dir / MANIFEST_NAME),
    }


def run_once(api: SupabaseRest, worker_id: str, workspace_root: Path, catalog_xml: Path | None) -> bool:
    job = api.rpc("claim_next_job", {"_worker_id": worker_id, "_job_types": [JOB_TYPE]})
    if not job:
        return False
    job_id = str(job["id"])
    api.rpc("start_job", {"_job_id": job_id, "_worker_id": worker_id})
    try:
        output = process_job(api, job, workspace_root, catalog_xml)
        api.rpc("complete_job", {"_job_id": job_id, "_worker_id": worker_id, "_output": output})
    except Exception as exc:
        message = f"{type(exc).__name__}: {exc}"[:MAX_ERROR_LENGTH]
        api.rpc("fail_job", {"_job_id": job_id, "_worker_id": worker_id, "_error": message})
        print(f"[{job_id}] failed: {message}", file=sys.stderr)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Local WebWatt certificate intake worker (never starts WinWatt).")
    parser.add_argument("command", choices=["once", "watch", "dry-run"], nargs="?", default="watch")
    parser.add_argument("--poll-seconds", type=int, default=10)
    parser.add_argument("--workspace", type=Path, default=Path("data/webwatt_jobs"))
    parser.add_argument("--source", type=Path, help="Local PDF or XML for dry-run")
    parser.add_argument("--catalog", type=Path, help="Local material catalogue for PDF dry-run")
    args = parser.parse_args()
    if args.command == "dry-run":
        if args.source is None:
            parser.error("dry-run requires --source")
        manifest = process_local_intake(
            source=args.source, output_dir=args.workspace.resolve(), catalog_xml=args.catalog,
        )
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
        return 0
    url, key = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        parser.error("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY environment variables are required.")
    worker_id = os.environ.get("WEBWATT_WORKER_ID", f"{platform.node()}-certificate-worker")
    catalog_value = os.environ.get("WINWATT_CATALOG_XML")
    catalog_xml = Path(catalog_value).expanduser().resolve() if catalog_value else None
    api = SupabaseRest(url, key)
    workspace = args.workspace.resolve()
    if args.command == "once":
        run_once(api, worker_id, workspace, catalog_xml)
        return 0
    print(f"WebWatt certificate worker running as {worker_id}. Ctrl+C to stop.")
    while True:
        processed = run_once(api, worker_id, workspace, catalog_xml)
        if not processed:
            time.sleep(max(2, args.poll_seconds))


if __name__ == "__main__":
    raise SystemExit(main())
