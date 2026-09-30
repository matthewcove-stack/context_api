from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from app.research.embeddings import EmbeddingProviderError
from scripts import reembed_research_documents as cli


@pytest.mark.parametrize("account_blocked,expected", [(True, 78), (False, 75)])
def test_reembed_stops_on_first_provider_failure(monkeypatch, capsys, account_blocked, expected):
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
