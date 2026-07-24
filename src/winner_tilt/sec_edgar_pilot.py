"""Command entry point for an explicitly authorized SEC EDGAR ingest-only run.

Run with:
    python -m winner_tilt.sec_edgar_pilot --snapshot-dir <isolated-directory>

All authorization values are read from environment variables and validated
fail-closed by SecEdgarLiveRuntimeConfig.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from winner_tilt.data_providers.sec_edgar import SecEdgarPolicyError
from winner_tilt.data_providers.sec_edgar_live import (
    SecEdgarLiveRuntimeConfig,
    SecEdgarTransportError,
    run_authorized_pilot,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the bounded SEC EDGAR ingest-only pilot")
    parser.add_argument(
        "--snapshot-dir",
        required=True,
        help="Dedicated destination directory for immutable ingest-only snapshots",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        runtime = SecEdgarLiveRuntimeConfig.from_env()
        outputs = run_authorized_pilot(runtime, snapshot_dir=Path(args.snapshot_dir))
    except (SecEdgarPolicyError, SecEdgarTransportError, OSError, ValueError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2

    print(json.dumps({
        "status": "completed_ingest_only",
        "snapshot_count": len(outputs),
        "snapshots": [str(path) for path in outputs],
        "downstream_consumption": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
