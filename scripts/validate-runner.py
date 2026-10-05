#!/usr/bin/env python3
"""Validate the current self-hosted runner against the approved Phase 4 identity."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import platform
import re
import shutil
import subprocess
import sys
from typing import Any

APPROVAL_REQUIRED_KEYS = {
    "schema_version",
    "status",
    "dedicated_label",
    "runner_name",
    "runner_os",
    "runner_arch",
    "cpu_model",
    "cpu_flags_sha256",
    "logical_cpus",
    "physical_cores",
    "memory_bytes",
    "disk_total_bytes",
    "kernel",
    "docker_server_version",
    "openmpi_version",
    "native_mpi4_probe",
    "portable_mpi4_smoke",
    "host_lifetime_policy",
    "approved_image_ref",
    "approved_image_digest",
    "acceptance_workflow_run_id",
    "acceptance_artifact_id",
    "acceptance_artifact_digest",
    "infrastructure_request",
    "project_request_id",
    "vm_name",
    "vm_uuid",
}

DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
IMAGE_REF_RE = re.compile(r"^ghcr\.io/leodbc/ghostdagsim@sha256:[0-9a-f]{64}$")
HEX64_RE = re.compile(r"^[0-9a-f]{64}$")


def fail(message: str) -> "NoReturn":
    raise ValueError(message)


def run(*args: str) -> str:
    return subprocess.check_output(args, text=True).strip()


def run_shell(command: str) -> str:
    return subprocess.check_output(["bash", "-lc", command], text=True).strip()


def strict_json(path: pathlib.Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def load_approval(path: pathlib.Path) -> dict[str, Any]:
    data = strict_json(path)
    if set(data) != APPROVAL_REQUIRED_KEYS:
        missing = sorted(APPROVAL_REQUIRED_KEYS - set(data))
        extra = sorted(set(data) - APPROVAL_REQUIRED_KEYS)
        raise ValueError(f"runner approval keys mismatch; missing={missing}, extra={extra}")
    if type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise ValueError("runner approval schema_version must be integer 1")
    if data["status"] != "approved":
        raise ValueError("runner approval status must be approved")
    for key in (
        "dedicated_label",
        "runner_name",
        "runner_os",
        "runner_arch",
        "cpu_model",
        "kernel",
        "docker_server_version",
        "openmpi_version",
        "host_lifetime_policy",
        "infrastructure_request",
        "project_request_id",
        "vm_name",
        "vm_uuid",
    ):
        if not isinstance(data[key], str) or not data[key].strip():
            raise ValueError(f"runner approval {key} must be a non-empty string")
    if not isinstance(data["cpu_flags_sha256"], str) or HEX64_RE.fullmatch(data["cpu_flags_sha256"]) is None:
        raise ValueError("runner approval cpu_flags_sha256 must be 64 lowercase hex")
    for key in ("logical_cpus", "physical_cores", "memory_bytes", "disk_total_bytes", "acceptance_workflow_run_id", "acceptance_artifact_id"):
        if type(data[key]) is not int or data[key] <= 0:
            raise ValueError(f"runner approval {key} must be a positive integer")
    if data["native_mpi4_probe"] != "pass" or data["portable_mpi4_smoke"] != "pass":
        raise ValueError("runner approval requires passing native MPI4 and portable-image MPI4 evidence")
    if not isinstance(data["approved_image_digest"], str) or DIGEST_RE.fullmatch(data["approved_image_digest"]) is None:
        raise ValueError("runner approval approved_image_digest is invalid")
    if not isinstance(data["approved_image_ref"], str) or IMAGE_REF_RE.fullmatch(data["approved_image_ref"]) is None:
        raise ValueError("runner approval approved_image_ref is invalid")
    if data["approved_image_ref"] != f"ghcr.io/leodbc/ghostdagsim@{data['approved_image_digest']}":
        raise ValueError("runner approval image ref/digest mismatch")
    if not isinstance(data["acceptance_artifact_digest"], str) or DIGEST_RE.fullmatch(data["acceptance_artifact_digest"]) is None:
        raise ValueError("runner approval acceptance_artifact_digest is invalid")
    return data


def validate_image_binding(approval: dict[str, Any], canonical_image_path: pathlib.Path) -> None:
    trust = strict_json(canonical_image_path)
    if trust.get("status") != "approved":
        raise ValueError("canonical image trust anchor is not approved")
    if trust.get("image_ref") != approval["approved_image_ref"]:
        raise ValueError("runner approval image_ref does not match canonical image trust anchor")
    if trust.get("image_digest") != approval["approved_image_digest"]:
        raise ValueError("runner approval image_digest does not match canonical image trust anchor")


def first_cpu_flags() -> str:
    for line in pathlib.Path("/proc/cpuinfo").read_text(encoding="utf-8").splitlines():
        if line.startswith("flags"):
            return line.split(":", 1)[1].strip()
    raise ValueError("CPU flags not found in /proc/cpuinfo")


def observe_runner() -> dict[str, Any]:
    lscpu = run("lscpu")
    model_match = re.search(r"^Model name:\s*(.+)$", lscpu, re.MULTILINE)
    if not model_match:
        raise ValueError("CPU model not found in lscpu output")

    flags = " ".join(sorted(set(first_cpu_flags().split())))
    flags_sha = hashlib.sha256(flags.encode()).hexdigest()

    mem_kib = None
    for line in pathlib.Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
        if line.startswith("MemTotal:"):
            mem_kib = int(line.split()[1])
            break
    if mem_kib is None:
        raise ValueError("MemTotal not found")

    return {
        "runner_name": os.environ.get("RUNNER_NAME"),
        "runner_os": os.environ.get("RUNNER_OS") or platform.system(),
        "runner_arch": os.environ.get("RUNNER_ARCH") or platform.machine(),
        "cpu_model": model_match.group(1).strip(),
        "cpu_flags_sha256": flags_sha,
        "logical_cpus": int(run("nproc", "--all")),
        "physical_cores": int(run_shell("lscpu -p=CORE,SOCKET | grep -v '^#' | sort -u | wc -l")),
        "memory_bytes": mem_kib * 1024,
        "disk_total_bytes": int(run_shell("df --output=size -B1 / | tail -1 | tr -d ' '")),
        "kernel": run("uname", "-srmo"),
        "docker_server_version": run("docker", "version", "--format", "{{.Server.Version}}"),
        "openmpi_version": run_shell("mpirun --version | head -n1"),
    }


def verify_identity(approval: dict[str, Any], observed: dict[str, Any]) -> None:
    for key, observed_value in observed.items():
        if approval.get(key) != observed_value:
            raise ValueError(
                f"runner identity mismatch for {key}: "
                f"approved={approval.get(key)!r}, observed={observed_value!r}"
            )


def verify_native_mpi4() -> None:
    proc = subprocess.run(
        ["mpirun", "-np", "4", "/bin/sh", "-c", 'printf "%s\\n" "$OMPI_COMM_WORLD_RANK"'],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if proc.returncode != 0:
        raise ValueError(f"native MPI4 probe failed: rc={proc.returncode}; stderr={proc.stderr.strip()!r}")
    try:
        ranks = sorted(int(line.strip()) for line in proc.stdout.splitlines() if line.strip())
    except ValueError as exc:
        raise ValueError(f"native MPI4 probe produced non-integer rank output: {proc.stdout!r}") from exc
    if ranks != [0, 1, 2, 3]:
        raise ValueError(f"native MPI4 probe returned unexpected ranks: {ranks}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--approval", type=pathlib.Path, default=pathlib.Path("experiments/runner-approval.json"))
    parser.add_argument("--canonical-image", type=pathlib.Path, default=pathlib.Path("experiments/canonical-image.json"))
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()

    try:
        approval = load_approval(args.approval)
        validate_image_binding(approval, args.canonical_image)
        observed = observe_runner()
        verify_identity(approval, observed)
        verify_native_mpi4()
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    evidence = {
        "schema_version": 1,
        "status": "verified",
        "dedicated_label": approval["dedicated_label"],
        **observed,
        "native_mpi4_probe": "pass",
        "approved_image_ref": approval["approved_image_ref"],
        "approved_image_digest": approval["approved_image_digest"],
        "runner_approval_sha256": hashlib.sha256(
            args.approval.read_bytes()
        ).hexdigest(),
        "acceptance_workflow_run_id": approval["acceptance_workflow_run_id"],
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(evidence, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
