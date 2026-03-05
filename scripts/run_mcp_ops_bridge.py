from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.mcp_bridge_ops.server import run_server


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Context API MCP ops bridge.")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default=None,
        help="MCP transport override. Defaults to MCP_BRIDGE_TRANSPORT env var.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_server(transport=args.transport)


if __name__ == "__main__":
    main()
