#!/usr/bin/env python3
"""Summarize ghostdagsim benchmark manifests as CSV."""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

CANONICAL_SOURCE_SHA = "ba001537e3be8edc18e8e8692121da5bcb451189"
NS3_VERSION = "3.46.1"
CANONICAL_IMAGE_REPOSITORY = "ghcr.io/leodbc/ghostdagsim"
GREEN_MAX_SECONDS = 270 * 60
CAUTION_MAX_SECONDS = 330 * 60
MAX_HARNESS_DEADLINE_SECONDS = 350 * 60
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
IMAGE_REF_RE = re.compile(
    r"^ghcr\.io/leodbc/ghostdagsim@sha256:[0-9a-f]{64}$"
)


def reject_json_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON numeric constant is not allowed: {value}")


def finite_nonnegative(value: Any, *, field: str, required: bool) -> float | None:
    if value is None and not required:
        return None
    if type(value) not in (int, float):
        raise ValueError(f"{field} must be a finite non-negative number")
    try:
        number = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError(f"{field} must be a finite non-negative number") from exc
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"{field} must be a finite non-negative number")
    return number


def completed_manifest_is_coherent(manifest: dict[str, Any]) -> bool:
    trust = manifest.get("canonical_image_trust")
    verification = manifest.get("image_verification")
    output = manifest.get("output_integrity")
    if not isinstance(trust, dict) or not isinstance(verification, dict) or not isinstance(output, dict):
        return False

    if manifest.get("canonical_source_sha") != CANONICAL_SOURCE_SHA or manifest.get("source_sha") != CANONICAL_SOURCE_SHA:
        return False
    if manifest.get("canonical_ns3_version") != NS3_VERSION or manifest.get("ns3_version") != NS3_VERSION:
        return False

    if trust.get("repository") != CANONICAL_IMAGE_REPOSITORY:
        return False
    if trust.get("source_sha") != CANONICAL_SOURCE_SHA or trust.get("ns3_version") != NS3_VERSION:
        return False
    if trust.get("status") != "approved" or trust.get("approved_for_real_run") is not True:
        return False
    if trust.get("requested_ref_matched") is not True or trust.get("resolved_digest_matched") is not True:
        return False
    build_run_id = trust.get("build_workflow_run_id")
    if type(build_run_id) is not int or build_run_id <= 0:
        return False
    image_ref = trust.get("image_ref")
    image_digest = trust.get("image_digest")
    if not isinstance(image_ref, str) or IMAGE_REF_RE.fullmatch(image_ref) is None:
        return False
    if not isinstance(image_digest, str) or DIGEST_RE.fullmatch(image_digest) is None:
        return False
    if image_ref != f"{CANONICAL_IMAGE_REPOSITORY}@{image_digest}":
        return False

    if verification.get("status") != "verified":
        return False
    if verification.get("failure") is not None:
        return False
    if "failure_kind" in verification and verification.get("failure_kind") is not None:
        return False
    if verification.get("requested_image_reference") != image_ref:
        return False
    if verification.get("resolved_image_digest") != image_digest:
        return False
    if verification.get("trust_anchor_digest_matched") is not True:
        return False
    if verification.get("inspected_source_revision") != CANONICAL_SOURCE_SHA:
        return False
    if verification.get("detected_ns3_version") != NS3_VERSION:
        return False

    if manifest.get("requested_image_reference") != image_ref:
        return False
    if manifest.get("container_image") != image_ref:
        return False
    if manifest.get("resolved_image_digest") != image_digest:
        return False
    if manifest.get("container_digest") != image_digest:
        return False
    if manifest.get("timed_out") is not False:
        return False
    if manifest.get("harness_deadline_exhausted") is not False:
        return False
    if manifest.get("failure_kind") is not None or manifest.get("failure") is not None:
        return False

    if type(manifest.get("docker_client_return_code")) is not int or manifest.get("docker_client_return_code") != 0:
        return False
    if type(manifest.get("docker_container_exit_code")) is not int or manifest.get("docker_container_exit_code") != 0:
        return False
    if type(manifest.get("exit_code")) is not int or manifest.get("exit_code") != 0:
        return False
    if manifest.get("docker_status") != "exited" or manifest.get("docker_running") is not False:
        return False
    if manifest.get("oom_killed") is not False:
        return False
    if output.get("status") != "basic_pass":
        return False

    deadline = manifest.get("harness_deadline_seconds")
    if type(deadline) is not int or deadline <= 0 or deadline > MAX_HARNESS_DEADLINE_SECONDS:
        return False
    try:
        simulation_wall = finite_nonnegative(
            manifest.get("simulation_wall_seconds"),
            field="simulation_wall_seconds",
            required=True,
        )
        phase0_wall = finite_nonnegative(
            manifest.get("wall_seconds"),
            field="wall_seconds",
            required=True,
        )
        harness_wall = finite_nonnegative(
            manifest.get("harness_wall_seconds"),
            field="harness_wall_seconds",
            required=True,
        )
    except ValueError:
        return False
    if simulation_wall is None or phase0_wall is None or harness_wall is None:
        return False
    if phase0_wall != simulation_wall:
        return False
    if harness_wall > float(deadline):
        return False
    return True


def runtime_classify(manifest: dict[str, Any]) -> str:
    status = manifest.get("status")
    if status == "dry_run":
        return "dry-run"
    if status != "completed":
        return "no-go"
    if not completed_manifest_is_coherent(manifest):
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
    if data.get("wall_seconds") is not None:
        finite_nonnegative(data.get("wall_seconds"), field="wall_seconds", required=False)
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
                "scenario_definition_sha256": manifest.get("scenario_definition_sha256"),
                "mpi_threads": manifest.get("mpi_threads"),
                "rng_seed": manifest.get("rng_seed"),
                "rng_run": manifest.get("rng_run"),
                "status": manifest.get("status"),
                "runtime_classification": runtime_classify(manifest),
                "harness_wall_seconds": manifest.get("harness_wall_seconds"),
                "simulation_wall_seconds": manifest.get("simulation_wall_seconds"),
                "wall_seconds": manifest.get("wall_seconds"),
                "harness_deadline_seconds": manifest.get("harness_deadline_seconds"),
                "harness_deadline_exhausted": manifest.get("harness_deadline_exhausted"),
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
