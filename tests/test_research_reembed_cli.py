from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from app.research.embeddings import EmbeddingProviderError
from scripts import reembed_research_documents as cli


@pytest.mark.parametrize("account_blocked,expected", [(True, 78), (False, 75)])
def test_reembed_stops_on_first_provider_failure(monkeypatch, capsys, tmp_path, account_blocked, expected):
    monkeypatch.setenv("BRIEF_PUBLISH_REPORT_DIR", str(tmp_path / "reports"))
    monkeypatch.setenv("DATABASE_URL", "unused-test-url")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("RESEARCH_EMBEDDING_MODEL", "text-embedding-3-small")
    monkeypatch.setattr("sys.argv", ["reembed", "--topic-key", "ai", "--limit", "3"])
    monkeypatch.setattr(cli, "create_db_engine", lambda url: object())
    monkeypatch.setattr(cli, "list_research_documents_for_reembed", lambda *a, **kw: [
        {"document_id": str(i), "extracted_text": "Source text"} for i in range(3)
    ])
    calls = []
    def embed(*args, **kwargs):
        calls.append(kwargs)
        raise EmbeddingProviderError(status=429, code="test_quota", account_blocked=account_blocked)
    monkeypatch.setattr(cli, "_embed_existing_document", embed)
    assert cli.main() == expected
    assert len(calls) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "blocked-provider"
    assert report["remaining"] == 2
    assert "test-key" not in json.dumps(report)
    artifacts = list((tmp_path / "reports").glob("*.json"))
    assert len(artifacts) == 1
    artifact = json.loads(artifacts[0].read_text())
    assert artifact == dict(report, phase="embedding-repair", exit_status=expected)
    assert "test-key" not in json.dumps(artifact)


@pytest.mark.parametrize("failed", [False, True])
def test_reembed_persists_terminal_summary(monkeypatch, capsys, tmp_path, failed):
    monkeypatch.setenv("BRIEF_PUBLISH_REPORT_DIR", str(tmp_path))
    monkeypatch.setenv("DATABASE_URL", "unused-test-url")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("RESEARCH_EMBEDDING_MODEL", "text-embedding-3-small")
    monkeypatch.setattr("sys.argv", ["reembed", "--topic-key", "ai", "--limit", "1"])
    monkeypatch.setattr(cli, "create_db_engine", lambda url: object())
    monkeypatch.setattr(cli, "list_research_documents_for_reembed", lambda *a, **kw: [
        {"document_id": "one", "extracted_text": "Source text"}
    ])
    def embed(*args, **kwargs):
        if failed:
            raise RuntimeError("request details must not enter the artifact")
    monkeypatch.setattr(cli, "_embed_existing_document", embed)
    assert cli.main() == int(failed)
    artifact = json.loads(next(tmp_path.glob("*.json")).read_text())
    assert artifact["exit_status"] == int(failed)
    assert artifact["processed"] == int(not failed)
    assert artifact["failed"] == int(failed)
    assert "request details" not in json.dumps(artifact)


def test_report_write_failure_keeps_provider_exit_status(monkeypatch, capsys, tmp_path):
    blocked_path = tmp_path / "file"
    blocked_path.write_text("not a directory")
    monkeypatch.setenv("BRIEF_PUBLISH_REPORT_DIR", str(blocked_path))
    cli.emit_report({"status": "blocked-provider"}, exit_status=78)
    output = capsys.readouterr()
    assert json.loads(output.out)["status"] == "blocked-provider"
    assert "Unable to write" in output.err


def test_report_directory_is_optional(monkeypatch, capsys):
    monkeypatch.delenv("BRIEF_PUBLISH_REPORT_DIR", raising=False)
    cli.emit_report({"selected": 0}, exit_status=0)
    assert json.loads(capsys.readouterr().out) == {"selected": 0}


@pytest.mark.skipif(not shutil.which("flock"), reason="Linux scheduler test needs flock")
@pytest.mark.parametrize("exit_status", [0, 1, 75, 78])
def test_scheduled_publish_does_not_lower_thresholds_or_retry(tmp_path, exit_status):
    source = Path(__file__).resolve().parents[1] / "scripts/run_lambic_brief_publish_daily.sh"
    wrapper = tmp_path / source.name
    shutil.copy(source, wrapper)
    publisher = tmp_path / "run_lambic_brief_publish.sh"
    publisher.write_text(f'#!/bin/bash\nprintf "%s\\n" "$*"\nexit {exit_status}\n')
    publisher.chmod(0o755)
    import os
    env = dict(os.environ, BRIEF_PUBLISH_LOCK_FILE=str(tmp_path / "publish.lock"))
    result = subprocess.run(["bash", str(wrapper)], env=env, text=True, capture_output=True)
    assert result.returncode == exit_status
    assert result.stdout.strip() == "--mode daily --allow-skipped-weak"

