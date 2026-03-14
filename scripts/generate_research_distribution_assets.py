from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.research.distribution_generator import (  # noqa: E402
    DistributionGenerationError,
    execute_generation,
    load_settings,
    parse_request,
)


def main() -> None:
    settings = load_settings()
    args = parse_request()
    report = execute_generation(settings=settings, mode=args.mode, dry_run=bool(args.dry_run))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    try:
        main()
    except DistributionGenerationError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
