from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.research.brief_ops import BriefOpsError  # noqa: E402
from app.research.digest_generator import DigestGenerationError  # noqa: E402
from app.research.distribution_generator import DistributionGenerationError  # noqa: E402
from app.research.publish_pipeline import BriefPublishError, execute_publish, parse_request  # noqa: E402


def main() -> None:
    request = parse_request()
    report = execute_publish(request=request)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (BriefOpsError, BriefPublishError, DigestGenerationError, DistributionGenerationError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
