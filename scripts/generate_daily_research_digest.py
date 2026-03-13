from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.research.digest_generator import DigestGenerationError, execute_generation, load_settings, parse_request


def main() -> None:
    settings = load_settings()
    request = parse_request()
    report = execute_generation(settings=settings, request=request)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    try:
        main()
    except DigestGenerationError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
