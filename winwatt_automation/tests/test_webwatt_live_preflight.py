from winwatt_automation.workflows.webwatt_live_preflight import assess_worker_environment


def test_preflight_reports_missing_secrets_without_values() -> None:
    report = assess_worker_environment({"SUPABASE_URL": "https://example.supabase.co"})

    assert report["status"] == "blocked"
    assert report["missing"] == ["SUPABASE_SERVICE_ROLE_KEY or WEBWATT_WORKER_TOKEN"]
    assert report["secrets_redacted"] is True
    assert "https://example.supabase.co" not in str(report)


def test_xml_worker_is_ready_without_catalog() -> None:
    report = assess_worker_environment({
        "SUPABASE_URL": "https://example.supabase.co",
        "SUPABASE_SERVICE_ROLE_KEY": "secret",
    })

    assert report["status"] == "ready"
    assert report["missing"] == []


def test_gateway_worker_is_ready_without_service_role_key() -> None:
    report = assess_worker_environment({
        "SUPABASE_URL": "https://example.supabase.co",
        "WEBWATT_WORKER_TOKEN": "worker-secret",
    })

    assert report["status"] == "ready"
    assert report["checks"]["worker_token_configured"] is True
    assert report["checks"]["service_role_key_configured"] is False


def test_pdf_worker_requires_existing_catalog(tmp_path) -> None:
    environment = {
        "SUPABASE_URL": "https://example.supabase.co",
        "SUPABASE_SERVICE_ROLE_KEY": "secret",
        "WINWATT_CATALOG_XML": str(tmp_path / "missing.xml"),
    }

    report = assess_worker_environment(environment, require_catalog=True)

    assert report["status"] == "blocked"
    assert report["missing"] == ["WINWATT_CATALOG_XML (existing file)"]

