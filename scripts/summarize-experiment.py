#!/usr/bin/env python3
"""Summarize ghostdagsim benchmark manifests as CSV."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

GREEN_MAX_SECONDS = 270 * 60
CAUTION_MAX_SECONDS = 330 * 60


def classify(manifest: dict[str, Any]) -> str:
    status = manifest.get("status")
    if status == "dry_run":
        return "dry-run"
    if manifest.get("exit_code") not in (0, None):
        return "no-go"
    if manifest.get("oom_killed") is True:
        return "no-go"
    wall = manifest.get("wall_seconds")
    if not isinstance(wall, (int, float)):
        return "unknown"
    if wall >= CAUTION_MAX_SECONDS:
        return "no-go"
    if wall >= GREEN_MAX_SECONDS:
        return "caution"
    return "green"


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read manifest {path}: {exc}") from exc
    if data.get("schema_version") != 1:
        raise ValueError(f"unsupported manifest schema in {path}")
    return data


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifests", nargs="+", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rows: list[dict[str, Any]] = []
    try:
        for path in args.manifests:
            manifest = load_manifest(path)
            rows.append(
                {
                    "scenario": manifest.get("scenario_name"),
                    "scenario_revision": manifest.get("scenario_revision"),
                    "mpi_threads": manifest.get("mpi_threads"),
                    "rng_seed": manifest.get("rng_seed"),
                    "rng_run": manifest.get("rng_run"),
                    "status": manifest.get("status"),
                    "classification": classify(manifest),
                    "wall_seconds": manifest.get("wall_seconds"),
                    "exit_code": manifest.get("exit_code"),
                    "oom_killed": manifest.get("oom_killed"),
                    "raw_result_bytes": manifest.get("raw_result_bytes"),
                    "source_sha": manifest.get("source_sha"),
                    "container_digest": manifest.get("container_digest"),
                }
            )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    fieldnames = [
        "scenario",
        "scenario_revision",
        "mpi_threads",
        "rng_seed",
        "rng_run",
        "status",
        "classification",
        "wall_seconds",
        "exit_code",
        "oom_killed",
        "raw_result_bytes",
        "source_sha",
        "container_digest",
    ]
    writer = csv.DictWriter(
        sys.stdout, fieldnames=fieldnames, lineterminator="\n"
    )
    writer.writeheader()
    writer.writerows(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
