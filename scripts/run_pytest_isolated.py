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


def _wait_for_postgres(container_name: str, *, timeout_s: float = 30.0) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        result = _run(
            ["docker", "exec", container_name, "pg_isready", "-h", "127.0.0.1", "-U", "context", "-d", "context_test"],
            check=False,
            capture_output=True,
        )
        if result.returncode == 0:
            return
        time.sleep(0.5)
    raise RuntimeError(f"Timed out waiting for Postgres container {container_name}")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def main() -> None:
    parser = argparse.ArgumentParser(description="Run context_api pytest against an isolated disposable Postgres instance.")
    args, pytest_args = parser.parse_known_args()

    repo_root = Path(__file__).resolve().parent.parent
    run_suffix = uuid.uuid4().hex[:8]
    container_name = f"context-api-test-db-{run_suffix}"
    network_name = f"context-api-test-{run_suffix}"
    image_tag = "context-api-test-runner:local"
    port = _free_port()
    db_url = "postgresql+psycopg://context:context@test-db:5432/context_test"
    pytest_args = pytest_args or ["tests"]

    try:
        _run(["docker", "network", "create", network_name], cwd=repo_root)
        _run(["docker", "build", "-q", "-t", image_tag, "."], cwd=repo_root)
        _run(
            [
                "docker",
                "run",
                "--rm",
                "-d",
                "--name",
                container_name,
                "--network",
                network_name,
                "--network-alias",
                "test-db",
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
        _wait_for_postgres(container_name)
        _run(
            [
                "docker",
                "run",
                "--rm",
                "--network",
                network_name,
                "-e",
                f"DATABASE_URL={db_url}",
                "-e",
                "CONTEXT_API_TOKEN=test-token",
                image_tag,
                "alembic",
                "upgrade",
                "head",
            ],
            cwd=repo_root,
        )
        _run(
            [
                "docker",
                "run",
                "--rm",
                "--network",
                network_name,
                "-e",
                f"DATABASE_URL={db_url}",
                "-e",
                "CONTEXT_API_TOKEN=test-token",
                "-e",
                "RESEARCH_EMBEDDING_MODEL=hash-64",
                "-e",
                "RESEARCH_ALLOW_HASH_EMBEDDINGS=true",
                image_tag,
                "pytest",
                *pytest_args,
            ],
            cwd=repo_root,
        )
    finally:
        _run(["docker", "rm", "-f", container_name], check=False, capture_output=True)
        _run(["docker", "network", "rm", network_name], check=False, capture_output=True)


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        if exc.stdout:
            sys.stdout.write(exc.stdout)
        if exc.stderr:
            sys.stderr.write(exc.stderr)
        raise
