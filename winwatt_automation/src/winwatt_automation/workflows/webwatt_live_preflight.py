"""Secret-safe readiness checks for the live WebWatt certificate worker."""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any


def assess_worker_environment(
    environ: Mapping[str, str], *, require_catalog: bool = False,
) -> dict[str, Any]:
    """Return readiness without copying credential values into the report."""
    url_configured = bool(environ.get("SUPABASE_URL", "").strip())
    service_key_configured = bool(environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip())
    catalog_value = environ.get("WINWATT_CATALOG_XML", "").strip()
    catalog = Path(catalog_value).expanduser() if catalog_value else None
    catalog_exists = bool(catalog and catalog.is_file())
    checks = {
        "supabase_url_configured": url_configured,
        "service_role_key_configured": service_key_configured,
        "catalog_configured": bool(catalog_value),
        "catalog_exists": catalog_exists,
        "catalog_required": require_catalog,
    }
    missing = []
    if not url_configured:
        missing.append("SUPABASE_URL")
    if not service_key_configured:
        missing.append("SUPABASE_SERVICE_ROLE_KEY")
    if require_catalog and not catalog_exists:
        missing.append("WINWATT_CATALOG_XML (existing file)")
    return {
        "status": "ready" if not missing else "blocked",
        "checks": checks,
        "missing": missing,
        "secrets_redacted": True,
    }

