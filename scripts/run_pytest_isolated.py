from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path


def _run(command: list[str], *, cwd: Path | None = None, check: bool = True, capture_output: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        check=check,
        text=True,
        capture_output=capture_output,
    )


def _wait_for_port(host: str, port: int, *, timeout_s: float = 30.0) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1.0):
                return
        except OSError:
            time.sleep(0.5)
    raise RuntimeError(f"Timed out waiting for Postgres on {host}:{port}")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def main() -> None:
    parser = argparse.ArgumentParser(description="Run context_api pytest against an isolated disposable Postgres instance.")
    args, pytest_args = parser.parse_known_args()

    repo_root = Path(__file__).resolve().parent.parent
    env_file = repo_root / ".env"
    if not env_file.exists():
        raise RuntimeError("context_api/.env is required; run scripts/sync_runtime_env.py first")

    container_name = f"context-api-test-db-{uuid.uuid4().hex[:8]}"
    port = _free_port()
    db_url = f"postgresql+psycopg://context:context@host.docker.internal:{port}/context_test"
    pytest_args = pytest_args or ["tests"]

    try:
        _run(
            [
                "docker",
                "run",
                "--rm",
                "-d",
                "--name",
                container_name,
                "-e",
                "POSTGRES_DB=context_test",
                "-e",
                "POSTGRES_USER=context",
                "-e",
                "POSTGRES_PASSWORD=context",
                "-p",
                f"{port}:5432",
                "postgres:16",
            ],
            cwd=repo_root,
        )
        _wait_for_port("127.0.0.1", port)
        _run(
            [
                "docker",
                "compose",
                "--env-file",
                ".env",
                "-f",
                "docker-compose.yml",
                "run",
                "--rm",
                "-e",
                f"DATABASE_URL={db_url}",
                "-e",
                "CONTEXT_API_TEST_ALLOW_DB_RESET=true",
                "api",
                "alembic",
                "upgrade",
                "head",
            ],
            cwd=repo_root,
        )
        _run(
            [
                "docker",
                "compose",
                "--env-file",
                ".env",
                "-f",
                "docker-compose.yml",
                "run",
                "--rm",
                "-e",
                f"DATABASE_URL={db_url}",
                "-e",
                "CONTEXT_API_TEST_ALLOW_DB_RESET=true",
                "api",
                "pytest",
                *pytest_args,
            ],
            cwd=repo_root,
        )
    finally:
        _run(["docker", "rm", "-f", container_name], check=False, capture_output=True)


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        if exc.stdout:
            sys.stdout.write(exc.stdout)
        if exc.stderr:
            sys.stderr.write(exc.stderr)
        raise
