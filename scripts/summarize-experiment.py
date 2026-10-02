#!/usr/bin/env python3
"""Summarize ghostdagsim benchmark manifests as CSV."""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path
from typing import Any

GREEN_MAX_SECONDS = 270 * 60
CAUTION_MAX_SECONDS = 330 * 60


def reject_json_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON numeric constant is not allowed: {value}")


def finite_nonnegative(value: Any, *, field: str, required: bool) -> float | None:
    if value is None and not required:
        return None
    if type(value) not in (int, float) or not math.isfinite(float(value)) or float(value) < 0:
        raise ValueError(f"{field} must be a finite non-negative number")
    return float(value)


def runtime_classify(manifest: dict[str, Any]) -> str:
    status = manifest.get("status")
    if status == "dry_run":
        return "dry-run"
    if status != "completed":
        return "no-go"
    if manifest.get("timed_out") is True:
        return "no-go"
    if manifest.get("oom_killed") is True:
        return "no-go"
    if manifest.get("output_integrity", {}).get("status") != "basic_pass":
        return "no-go"
    if manifest.get("exit_code") != 0:
        return "no-go"
    wall = finite_nonnegative(manifest.get("simulation_wall_seconds"), field="simulation_wall_seconds", required=True)
    assert wall is not None
    if wall >= CAUTION_MAX_SECONDS:
        return "no-go"
    if wall >= GREEN_MAX_SECONDS:
        return "caution"
    return "green"


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"), parse_constant=reject_json_constant)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"cannot read manifest {path}: {exc}") from exc
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise ValueError(f"unsupported manifest schema in {path}")
    finite_nonnegative(data.get("harness_wall_seconds"), field="harness_wall_seconds", required=data.get("status") != "starting")
    if data.get("simulation_wall_seconds") is not None:
        finite_nonnegative(data.get("simulation_wall_seconds"), field="simulation_wall_seconds", required=False)
    return data


def nested(manifest: dict[str, Any], *path: str) -> Any:
    value: Any = manifest
    for key in path:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


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
            rows.append({
                "scenario": manifest.get("scenario_name"),
                "scenario_revision": manifest.get("scenario_revision"),
                "mpi_threads": manifest.get("mpi_threads"),
                "rng_seed": manifest.get("rng_seed"),
                "rng_run": manifest.get("rng_run"),
                "status": manifest.get("status"),
                "runtime_classification": runtime_classify(manifest),
                "harness_wall_seconds": manifest.get("harness_wall_seconds"),
                "simulation_wall_seconds": manifest.get("simulation_wall_seconds"),
                "timed_out": manifest.get("timed_out"),
                "failure_kind": manifest.get("failure_kind"),
                "exit_code": manifest.get("exit_code"),
                "docker_client_return_code": manifest.get("docker_client_return_code"),
                "docker_container_exit_code": manifest.get("docker_container_exit_code"),
                "docker_status": manifest.get("docker_status"),
                "docker_running": manifest.get("docker_running"),
                "oom_killed": manifest.get("oom_killed"),
                "output_integrity_status": nested(manifest, "output_integrity", "status"),
                "image_verification_status": nested(manifest, "image_verification", "status"),
                "failure": manifest.get("failure"),
                "raw_result_bytes": manifest.get("raw_result_bytes"),
                "disk_before_total_bytes": nested(manifest, "disk_before", "total_bytes"),
                "disk_before_used_bytes": nested(manifest, "disk_before", "used_bytes"),
                "disk_before_free_bytes": nested(manifest, "disk_before", "free_bytes"),
                "disk_after_total_bytes": nested(manifest, "disk_after", "total_bytes"),
                "disk_after_used_bytes": nested(manifest, "disk_after", "used_bytes"),
                "disk_after_free_bytes": nested(manifest, "disk_after", "free_bytes"),
                "canonical_source_sha": manifest.get("canonical_source_sha"),
                "source_sha": manifest.get("source_sha"),
                "canonical_ns3_version": manifest.get("canonical_ns3_version"),
                "ns3_version": manifest.get("ns3_version"),
                "requested_image_reference": manifest.get("requested_image_reference"),
                "resolved_image_digest": manifest.get("resolved_image_digest"),
            })
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    fieldnames = list(rows[0].keys()) if rows else []
    writer = csv.DictWriter(sys.stdout, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
