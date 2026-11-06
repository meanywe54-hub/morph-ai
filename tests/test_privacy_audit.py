import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "release_audit", Path(__file__).parents[1] / "scripts" / "audit_release.py"
)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def test_release_audit_rejects_raw_artifacts_but_allows_summary():
    assert audit.forbidden_path("reports/run.json")
    assert audit.forbidden_path("local-results/run.json")
    assert audit.forbidden_path(".env.production")
    assert not audit.forbidden_path("reports/README.md")
    assert not audit.forbidden_path(".env.example")


def test_release_audit_reports_names_without_exposing_secret_values(monkeypatch):
    value = "sk-" + "x" * 30
    monkeypatch.setenv("OPENAI_API_KEY", value)
    result = audit.findings("example", value)
    assert any(item["finding"] == "configured_credential:OPENAI_API_KEY" for item in result)
    assert value not in str(result)
    sample_path = "C:" + chr(92) + "Users" + chr(92) + "someone" + chr(92) + "private.txt"
    assert any(
        item["finding"] == "local_user_path" for item in audit.findings("example", sample_path)
    )
