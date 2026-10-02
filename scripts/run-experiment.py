#!/usr/bin/env python3
"""Run one canonical ghostdagsim calibration scenario and emit a manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import re
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CANONICAL_SOURCE_SHA = "ba001537e3be8edc18e8e8692121da5bcb451189"
NS3_VERSION = "3.46.1"
CANONICAL_IMAGE_REPOSITORY = "ghcr.io/leodbc/ghostdagsim"
TRUST_ANCHOR_PATH = Path(__file__).resolve().parents[1] / "experiments" / "canonical-image.json"
CALIBRATION_MPI_VALUES = (1, 2, 4)
DEFAULT_TIMEOUT_SECONDS = 320 * 60
MAX_TIMEOUT_SECONDS = 325 * 60
DEFAULT_HARNESS_DEADLINE_SECONDS = 345 * 60
MAX_HARNESS_DEADLINE_SECONDS = 350 * 60
CLEANUP_TIMEOUT_SECONDS = 15
JSONL_TAIL_BYTES = 65536
UINT32_MAX = (1 << 32) - 1
UINT64_MAX = (1 << 64) - 1
INT32_MAX = (1 << 31) - 1
CANONICAL_IMAGE_RE = re.compile(
    r"^ghcr\.io/leodbc/ghostdagsim@sha256:[0-9a-f]{64}$"
)
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
NS3_LIBRARY_RE = re.compile(r"libns(\d+\.\d+(?:\.\d+)?)-[A-Za-z0-9_.+-]+\.so(?:\.[0-9]+)*")
SAFE_REVISION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
ALLOWED_SCENARIOS = {"small", "representative", "heavy"}
REQUIRED_SIMULATOR_ARGS = {
    "nodes", "miners", "min_conn", "max_conn", "lambda", "derive_k",
    "delta", "dmax", "tau", "pareto_divider", "k", "txs_per_block",
    "mempool_size", "tx_fee_lambda", "tx_gen_interval", "tx_load",
    "snapshot_interval", "blocks_per_miner", "graphene", "inv_timeout",
    "tcp_mss",
}
FORBIDDEN_SCENARIO_ARGS = {"run_name", "RngSeed", "RngRun"}
class RunStop(Exception):
    def __init__(self, code: int) -> None:
        super().__init__(str(code))
        self.code = code


class HarnessInterruption(Exception):
    def __init__(self, signum: int | None, message: str = "interrupted") -> None:
        super().__init__(message)
        self.signum = signum


class HarnessDeadlineExceeded(Exception):
    def __init__(self, operation: str) -> None:
        super().__init__(f"global harness deadline exhausted during {operation}")
        self.operation = operation


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def reject_json_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON numeric constant is not allowed: {value}")


def strict_json_loads(text: str, *, context: str) -> Any:
    try:
        return json.loads(text, parse_constant=reject_json_constant)
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"invalid {context}: {exc}") from exc


def disk_snapshot(path: Path) -> dict[str, int]:
    usage = shutil.disk_usage(path)
    return {"total_bytes": usage.total, "used_bytes": usage.used, "free_bytes": usage.free}


def directory_bytes(path: Path, *, exclude: set[Path] | None = None) -> int:
    if not path.exists():
        return 0
    excluded = {p.resolve() for p in (exclude or set())}
    total = 0
    for item in path.rglob("*"):
        try:
            if item.is_symlink():
                continue
            if item.is_file() and item.resolve() not in excluded:
                total += item.stat().st_size
        except FileNotFoundError:
            continue
    return total


def is_int(value: Any) -> bool:
    return type(value) is int


def is_number(value: Any) -> bool:
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(float(value))
    except (OverflowError, ValueError):
        return False


def canonical_json_sha256(value: Any) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def scenario_definition_sha256(scenario: dict[str, Any]) -> str:
    return canonical_json_sha256(scenario)


def load_canonical_image_trust(path: Path = TRUST_ANCHOR_PATH) -> dict[str, Any]:
    try:
        data = strict_json_loads(path.read_text(encoding="utf-8"), context=f"canonical image trust anchor {path}")
    except OSError as exc:
        raise ValueError(f"cannot read canonical image trust anchor {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("canonical image trust anchor must be a JSON object")
    required = {
        "schema_version", "status", "repository", "source_sha", "ns3_version",
        "image_digest", "image_ref", "build_workflow_run_id",
    }
    if set(data) != required:
        raise ValueError(f"canonical image trust anchor keys must be exactly {sorted(required)}")
    if type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise ValueError("canonical image trust anchor schema_version must be integer 1")
    if data["status"] not in {"unpublished", "approved"}:
        raise ValueError("canonical image trust anchor status must be unpublished or approved")
    if data["repository"] != CANONICAL_IMAGE_REPOSITORY:
        raise ValueError("canonical image trust anchor repository mismatch")
    if data["source_sha"] != CANONICAL_SOURCE_SHA:
        raise ValueError("canonical image trust anchor source_sha mismatch")
    if data["ns3_version"] != NS3_VERSION:
        raise ValueError("canonical image trust anchor ns3_version mismatch")
    digest = data["image_digest"]
    image_ref = data["image_ref"]
    if digest is not None and (not isinstance(digest, str) or not DIGEST_RE.fullmatch(digest)):
        raise ValueError("canonical image trust anchor image_digest is invalid")
    if image_ref is not None and (not isinstance(image_ref, str) or not CANONICAL_IMAGE_RE.fullmatch(image_ref)):
        raise ValueError("canonical image trust anchor image_ref is invalid")
    workflow_run_id = data["build_workflow_run_id"]
    if workflow_run_id is not None and (type(workflow_run_id) is not int or workflow_run_id <= 0):
        raise ValueError("canonical image trust anchor build_workflow_run_id must be null or a positive integer")
    if data["status"] == "approved":
        if digest is None or image_ref is None:
            raise ValueError("approved canonical image trust anchor requires image_digest and image_ref")
        if image_ref != f"{CANONICAL_IMAGE_REPOSITORY}@{digest}":
            raise ValueError("approved canonical image trust anchor image_ref/digest mismatch")
    return data


def trust_manifest_snapshot(trust: dict[str, Any], *, requested_image_ref: str) -> dict[str, Any]:
    approved = trust["status"] == "approved" and trust["image_ref"] is not None and trust["image_digest"] is not None
    return {
        **trust,
        "approved_for_real_run": approved,
        "requested_ref_matched": requested_image_ref == trust.get("image_ref") if approved else False,
        "resolved_digest_matched": None,
    }


def validate_trust_for_real_run(trust: dict[str, Any], image_ref: str) -> None:
    if trust["status"] != "approved" or trust["image_ref"] is None or trust["image_digest"] is None:
        raise ValueError("canonical image trust anchor is not approved; real execution is disabled")
    if image_ref != trust["image_ref"]:
        raise ValueError("--image-ref does not exactly match the approved canonical image_ref")


def require_int(name: str, value: Any, *, minimum: int, maximum: int | None = None) -> None:
    if not is_int(value):
        raise ValueError(f"{name} must be an integer (boolean is not accepted)")
    if value < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    if maximum is not None and value > maximum:
        raise ValueError(f"{name} must be <= {maximum}")


def require_number(
    name: str,
    value: Any,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
    min_exclusive: bool = False,
    max_exclusive: bool = False,
) -> None:
    if not is_number(value):
        raise ValueError(f"{name} must be a finite number")
    number = float(value)
    if minimum is not None:
        bad = number <= minimum if min_exclusive else number < minimum
        if bad:
            op = ">" if min_exclusive else ">="
            raise ValueError(f"{name} must be {op} {minimum}")
    if maximum is not None:
        bad = number >= maximum if max_exclusive else number > maximum
        if bad:
            op = "<" if max_exclusive else "<="
            raise ValueError(f"{name} must be {op} {maximum}")


def cli_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if type(value) in (int, float, str):
        return str(value)
    raise ValueError(f"unsupported simulator argument value: {value!r}")


def validate_simulator_args(args: dict[str, Any]) -> None:
    missing = REQUIRED_SIMULATOR_ARGS - args.keys()
    extra = args.keys() - REQUIRED_SIMULATOR_ARGS
    forbidden = FORBIDDEN_SCENARIO_ARGS & args.keys()
    if missing:
        raise ValueError(f"scenario is missing simulator args: {sorted(missing)}")
    if extra:
        raise ValueError(f"scenario has unexpected simulator args: {sorted(extra)}")
    if forbidden:
        raise ValueError(f"scenario cannot define harness-owned args: {sorted(forbidden)}")

    require_int("nodes", args["nodes"], minimum=1, maximum=INT32_MAX)
    require_int("miners", args["miners"], minimum=1, maximum=INT32_MAX)
    if args["miners"] > args["nodes"]:
        raise ValueError("miners must be <= nodes")

    for name in ("min_conn", "max_conn"):
        if not is_int(args[name]):
            raise ValueError(f"{name} must be an integer (boolean is not accepted)")
    min_conn = args["min_conn"]
    max_conn = args["max_conn"]
    if (min_conn, max_conn) == (-1, -1):
        pass
    elif min_conn > 0 and max_conn > 0:
        if min_conn > max_conn:
            raise ValueError("min_conn must be <= max_conn")
        if max_conn > args["nodes"]:
            raise ValueError("max_conn must be <= nodes")
    else:
        raise ValueError("min_conn/max_conn must both be -1 or both be positive integers")

    require_number("lambda", args["lambda"], minimum=0.0, min_exclusive=True)
    if type(args["derive_k"]) is not bool:
        raise ValueError("derive_k must be a boolean")
    require_number("delta", args["delta"], minimum=0.0, maximum=1.0, min_exclusive=True, max_exclusive=True)
    require_number("dmax", args["dmax"], minimum=0.0)
    if args["derive_k"] and float(args["dmax"]) <= 0.0:
        raise ValueError("dmax must be > 0 when derive_k is true")
    require_number("tau", args["tau"], minimum=0.0, min_exclusive=True)
    require_number("pareto_divider", args["pareto_divider"], minimum=0.0, min_exclusive=True)
    require_int("k", args["k"], minimum=0, maximum=UINT32_MAX)
    require_int("txs_per_block", args["txs_per_block"], minimum=1, maximum=INT32_MAX)
    require_int("mempool_size", args["mempool_size"], minimum=1, maximum=INT32_MAX)
    require_number("tx_fee_lambda", args["tx_fee_lambda"], minimum=0.0, min_exclusive=True)
    require_number("tx_gen_interval", args["tx_gen_interval"], minimum=0.0, min_exclusive=True)
    require_number("tx_load", args["tx_load"], minimum=0.0)
    if float(args["tx_load"]) > 0.0 and args["nodes"] == args["miners"]:
        raise ValueError("tx_load > 0 requires at least one non-miner node")
    require_number("snapshot_interval", args["snapshot_interval"], minimum=0.0)
    require_int("blocks_per_miner", args["blocks_per_miner"], minimum=1, maximum=INT32_MAX)
    if type(args["graphene"]) is not bool:
        raise ValueError("graphene must be a boolean")
    require_number("inv_timeout", args["inv_timeout"], minimum=0.0, min_exclusive=True)
    require_int("tcp_mss", args["tcp_mss"], minimum=1, maximum=UINT32_MAX)


def load_scenario(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ValueError(f"scenario file does not exist: {path}") from exc
    except OSError as exc:
        raise ValueError(f"cannot read scenario file {path}: {exc}") from exc
    data = strict_json_loads(raw, context=f"scenario JSON {path}")
    if not isinstance(data, dict):
        raise ValueError("scenario JSON must be an object")
    if data.get("schema_version") != 1 or type(data.get("schema_version")) is not int:
        raise ValueError("scenario schema_version must be integer 1")

    name = data.get("name")
    if name not in ALLOWED_SCENARIOS:
        raise ValueError(f"scenario name must be one of {sorted(ALLOWED_SCENARIOS)}")
    if path.stem != name:
        raise ValueError(f"scenario file name {path.stem!r} must match scenario name {name!r}")

    revision = data.get("revision")
    if not isinstance(revision, str) or not SAFE_REVISION_RE.fullmatch(revision):
        raise ValueError("scenario revision must match [A-Za-z0-9][A-Za-z0-9._-]*")

    provenance = data.get("provenance")
    if not isinstance(provenance, dict) or not isinstance(provenance.get("reference"), str) or not provenance["reference"]:
        raise ValueError("scenario provenance.reference is required")

    sim_args = data.get("simulator_args")
    if not isinstance(sim_args, dict):
        raise ValueError("scenario simulator_args must be an object")
    validate_simulator_args(sim_args)
    return data


def simulator_arguments(
    scenario: dict[str, Any], *, run_name: str, rng_seed: int, rng_run: int
) -> list[str]:
    values = [f"--{key}={cli_value(value)}" for key, value in scenario["simulator_args"].items()]
    values.extend([f"--RngSeed={rng_seed}", f"--RngRun={rng_run}", f"--run_name={run_name}"])
    return values


def github_metadata() -> dict[str, str | None]:
    def env(name: str) -> str | None:
        value = os.getenv(name)
        return value if value else None
    return {
        "github_workflow": env("GITHUB_WORKFLOW"),
        "github_run_id": env("GITHUB_RUN_ID"),
        "github_run_attempt": env("GITHUB_RUN_ATTEMPT"),
        "github_sha": env("GITHUB_SHA"),
        "runner_os": env("RUNNER_OS") or platform.system(),
        "runner_arch": env("RUNNER_ARCH") or platform.machine(),
    }


def write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    temp = path.with_suffix(".json.tmp")
    temp.write_text(json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    temp.replace(path)


def run_command(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=False, text=True, **kwargs)


def remaining_deadline_seconds(deadline_at: float, *, operation: str) -> float:
    remaining = deadline_at - time.monotonic()
    if remaining <= 0:
        raise HarnessDeadlineExceeded(operation)
    return remaining


def run_command_with_deadline(
    command: list[str], *, deadline_at: float, operation: str,
    timeout_cap: float | None = None, **kwargs: Any,
) -> subprocess.CompletedProcess[str]:
    remaining = remaining_deadline_seconds(deadline_at, operation=operation)
    deadline_limited = timeout_cap is None or remaining <= timeout_cap
    timeout = remaining if timeout_cap is None else min(remaining, timeout_cap)
    try:
        return run_command(command, timeout=max(0.001, timeout), **kwargs)
    except subprocess.TimeoutExpired as exc:
        if deadline_limited:
            raise HarnessDeadlineExceeded(operation) from exc
        raise


def inspect_container_state(
    container_name: str, *, deadline_at: float
) -> tuple[dict[str, Any] | None, str | None]:
    try:
        inspect = run_command_with_deadline(
            ["docker", "inspect", "--format", "{{json .State}}", container_name],
            deadline_at=deadline_at,
            operation="docker inspect",
            capture_output=True,
        )
    except HarnessDeadlineExceeded:
        raise
    if inspect.returncode != 0:
        detail = inspect.stderr.strip() or inspect.stdout.strip() or f"exit {inspect.returncode}"
        return None, f"docker inspect failed: {detail}"
    try:
        state = strict_json_loads(inspect.stdout, context="docker state JSON")
    except ValueError as exc:
        return None, str(exc)
    if not isinstance(state, dict):
        return None, "docker inspect state was not an object"
    return state, None


def cleanup_container(container_name: str) -> tuple[bool, str | None]:
    try:
        cleanup = run_command(
            ["docker", "rm", "-f", container_name],
            capture_output=True,
            timeout=CLEANUP_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return False, f"docker rm -f exceeded cleanup timeout of {CLEANUP_TIMEOUT_SECONDS} seconds"
    detail = cleanup.stderr.strip() or cleanup.stdout.strip()
    if cleanup.returncode == 0 or "No such container" in detail:
        return True, None
    return False, f"docker rm -f failed: {detail or f'exit {cleanup.returncode}'}"


def detect_ns3_versions_from_ldd(text: str) -> list[str]:
    return sorted({match.group(1) for match in NS3_LIBRARY_RE.finditer(text)})


def verify_image(
    image_ref: str,
    verification_container_name: str,
    trust: dict[str, Any],
    *,
    deadline_at: float,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": "failed",
        "requested_image_reference": image_ref,
        "resolved_image_digest": None,
        "oci_labels": {},
        "inspected_source_revision": None,
        "detected_ns3_version": None,
        "trust_anchor_digest_matched": False,
        "failure": None,
        "failure_kind": None,
        "cleanup": {"attempted": False, "succeeded": None, "failure": None},
    }

    validate_trust_for_real_run(trust, image_ref)

    pull = run_command_with_deadline(
        ["docker", "pull", image_ref],
        deadline_at=deadline_at,
        operation="docker pull",
        capture_output=True,
    )
    if pull.returncode != 0:
        detail = pull.stderr.strip() or pull.stdout.strip() or f"exit {pull.returncode}"
        result["failure"] = f"docker pull failed: {detail}"
        result["failure_kind"] = "docker_create_pull_failure"
        return result

    inspect = run_command_with_deadline(
        ["docker", "image", "inspect", "--format", "{{json .}}", image_ref],
        deadline_at=deadline_at,
        operation="docker image inspect",
        capture_output=True,
    )
    if inspect.returncode != 0:
        detail = inspect.stderr.strip() or inspect.stdout.strip() or f"exit {inspect.returncode}"
        result["failure"] = f"docker image inspect failed: {detail}"
        result["failure_kind"] = "docker_inspect_state_failure"
        return result
    try:
        image_data = strict_json_loads(inspect.stdout, context="docker image inspect JSON")
    except ValueError as exc:
        result["failure"] = str(exc)
        result["failure_kind"] = "docker_inspect_state_failure"
        return result
    if not isinstance(image_data, dict):
        result["failure"] = "docker image inspect did not return an object"
        result["failure_kind"] = "docker_inspect_state_failure"
        return result

    requested_digest = image_ref.split("@", 1)[1]
    repo_digests = image_data.get("RepoDigests")
    if not isinstance(repo_digests, list):
        repo_digests = []
    resolved_candidates = {
        candidate.split("@", 1)[1]
        for candidate in repo_digests
        if isinstance(candidate, str)
        and candidate.startswith(f"{CANONICAL_IMAGE_REPOSITORY}@sha256:")
        and "@" in candidate
    }
    resolved = requested_digest if requested_digest in resolved_candidates else None
    result["resolved_image_digest"] = resolved
    result["trust_anchor_digest_matched"] = resolved == trust["image_digest"]

    config = image_data.get("Config")
    labels = config.get("Labels") if isinstance(config, dict) else None
    if not isinstance(labels, dict):
        labels = {}
    relevant_labels = {
        str(k): str(v) for k, v in labels.items()
        if isinstance(k, str) and k.startswith("org.opencontainers.image.")
    }
    result["oci_labels"] = relevant_labels
    revision = relevant_labels.get("org.opencontainers.image.revision")
    result["inspected_source_revision"] = revision

    if resolved != requested_digest or resolved != trust["image_digest"]:
        result["failure"] = "resolved repository digest does not match the approved canonical image digest"
        result["failure_kind"] = "image_verification_failure"
        return result
    if revision != CANONICAL_SOURCE_SHA:
        result["failure"] = (
            "org.opencontainers.image.revision is absent or does not match canonical source SHA"
        )
        result["failure_kind"] = "image_verification_failure"
        return result

    create_cmd = [
        "docker", "create", "--name", verification_container_name,
        "--entrypoint", "/bin/sh", image_ref,
        "-c",
        "test -x /usr/local/bin/ghostdagsim && command -v ldd >/dev/null 2>&1 && ldd /usr/local/bin/ghostdagsim",
    ]
    create_attempted = True
    try:
        created = run_command_with_deadline(
            create_cmd,
            deadline_at=deadline_at,
            operation="verification docker create",
            capture_output=True,
        )
        if created.returncode != 0:
            detail = created.stderr.strip() or created.stdout.strip() or f"exit {created.returncode}"
            result["failure"] = f"docker create for runtime verification failed: {detail}"
            result["failure_kind"] = "docker_create_pull_failure"
            return result

        started = run_command_with_deadline(
            ["docker", "start", "-a", verification_container_name],
            deadline_at=deadline_at,
            operation="verification docker start",
            capture_output=True,
        )
        if started.returncode != 0:
            detail = started.stderr.strip() or started.stdout.strip() or f"exit {started.returncode}"
            result["failure"] = (
                "runtime verification failed; /usr/local/bin/ghostdagsim must be executable "
                f"and ldd must succeed: {detail}"
            )
            result["failure_kind"] = "docker_start_runtime_failure"
            return result

        versions = detect_ns3_versions_from_ldd(started.stdout)
        result["detected_ns3_version"] = versions[0] if len(versions) == 1 else versions or None
        if versions != [NS3_VERSION]:
            result["failure"] = (
                f"ghostdagsim linkage does not identify exactly ns-{NS3_VERSION}; detected={versions}"
            )
            result["failure_kind"] = "image_verification_failure"
            return result
        result["status"] = "verified"
        return result
    finally:
        if create_attempted:
            result["cleanup"]["attempted"] = True
            ok, error = cleanup_container(verification_container_name)
            result["cleanup"]["succeeded"] = ok
            result["cleanup"]["failure"] = error
            if not ok and result.get("status") == "verified":
                result["status"] = "failed"
                result["failure"] = error
                result["failure_kind"] = "docker_start_runtime_failure"


def read_last_nonempty_json_line(path: Path, *, tail_bytes: int = JSONL_TAIL_BYTES) -> None:
    size = path.stat().st_size
    if size <= 0:
        raise ValueError(f"events JSONL file is empty: {path}")
    start = max(0, size - tail_bytes)
    with path.open("rb") as handle:
        handle.seek(start)
        data = handle.read(tail_bytes)
    trimmed = data.rstrip(b" \t\r\n")
    if not trimmed:
        raise ValueError(f"events JSONL file is empty or whitespace-only: {path}")
    boundary = trimmed.rfind(b"\n")
    if boundary >= 0:
        record = trimmed[boundary + 1 :].strip()
    else:
        if start > 0:
            raise ValueError(f"final JSONL record exceeds validation cap of {tail_bytes} bytes: {path}")
        record = trimmed.strip()
    if not record:
        raise ValueError(f"events JSONL file has no non-empty JSON record: {path}")
    try:
        text = record.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"last JSONL record is not UTF-8: {exc}") from exc
    value = strict_json_loads(text, context=f"final JSONL record in {path}")
    if not isinstance(value, dict):
        raise ValueError(f"final JSONL record in {path} is not a JSON object")


def validate_output_integrity(run_dir: Path, *, run_name: str, mpi_threads: int) -> dict[str, Any]:
    result: dict[str, Any] = {"status": "basic_fail", "failure": None, "checked_ranks": []}
    try:
        for item in run_dir.rglob("*"):
            if item.is_symlink():
                raise ValueError(f"unexpected symlink in run output: {item.relative_to(run_dir)}")
        config = run_dir / "config.json"
        if config.is_symlink() or not config.is_file():
            raise ValueError("config.json is missing, not regular, or is a symlink")
        config_data = strict_json_loads(config.read_text(encoding="utf-8"), context="config.json")
        if not isinstance(config_data, dict):
            raise ValueError("config.json must contain a JSON object")
        if "scenario_name" not in config_data:
            raise ValueError("config.json is missing required scenario_name")
        scenario_identity = config_data["scenario_name"]
        if scenario_identity != run_name:
            raise ValueError(
                f"config scenario_name {scenario_identity!r} does not match run identity {run_name!r}"
            )

        for rank in range(mpi_threads):
            rank_dir = run_dir / f"rank{rank}"
            if rank_dir.is_symlink() or not rank_dir.is_dir():
                raise ValueError(f"expected rank directory missing/not regular: rank{rank}")
            events = rank_dir / "events.jsonl"
            if events.is_symlink() or not events.is_file():
                raise ValueError(f"expected events file missing/not regular: rank{rank}/events.jsonl")
            read_last_nonempty_json_line(events)
            result["checked_ranks"].append(rank)

        result["status"] = "basic_pass"
        return result
    except (OSError, ValueError) as exc:
        result["failure"] = str(exc)
        return result


def validate_completed_docker_state(
    state: dict[str, Any], client_return_code: Any
) -> tuple[bool, str | None, str | None]:
    required_types = {
        "Status": str,
        "Running": bool,
        "ExitCode": int,
        "OOMKilled": bool,
        "Error": str,
    }
    for field, expected_type in required_types.items():
        if field not in state:
            return False, "docker_inspect_state_failure", f"Docker state is missing required field {field}"
        value = state[field]
        if expected_type is int:
            valid_type = type(value) is int
        else:
            valid_type = type(value) is expected_type
        if not valid_type:
            return False, "docker_inspect_state_failure", f"Docker state field {field} has invalid type"
    if state["OOMKilled"] is True:
        return False, "oom", "Docker reported OOMKilled=true"
    if state["Error"] != "":
        return False, "docker_start_runtime_failure", f"Docker State.Error is non-empty: {state['Error']}"
    if state["Status"] != "exited" or state["Running"] is not False:
        return False, "docker_inspect_state_failure", (
            f"Docker state is not exited/non-running: status={state['Status']!r}, running={state['Running']!r}"
        )
    if state["ExitCode"] != 0:
        return False, "simulator_nonzero", f"simulator/container exited with code {state['ExitCode']}"
    if type(client_return_code) is not int or client_return_code != 0:
        return False, "docker_start_runtime_failure", f"docker start client returned {client_return_code!r}"
    return True, None, None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", required=True, type=Path, help="scenario JSON file")
    parser.add_argument("--image-ref", required=True, help="immutable ghcr.io/leodbc/ghostdagsim@sha256:<digest> reference")
    parser.add_argument("--mpi-threads", required=True, type=int, choices=CALIBRATION_MPI_VALUES)
    parser.add_argument("--rng-seed", type=int, default=1)
    parser.add_argument("--rng-run", type=int, default=1)
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS,
                        help=f"simulation/container timeout (default {DEFAULT_TIMEOUT_SECONDS}s; max {MAX_TIMEOUT_SECONDS}s)")
    parser.add_argument("--harness-deadline-seconds", type=int, default=DEFAULT_HARNESS_DEADLINE_SECONDS,
                        help=f"overall real-run harness deadline (default {DEFAULT_HARNESS_DEADLINE_SECONDS}s; max {MAX_HARNESS_DEADLINE_SECONDS}s)")
    parser.add_argument("--results-root", type=Path, default=Path("results"),
                        help="host directory receiving simulator results (default: ./results)")
    parser.add_argument("--dry-run", action="store_true", help="validate and emit manifest without invoking Docker")
    return parser.parse_args()


def install_signal_handlers() -> dict[int, Any]:
    previous: dict[int, Any] = {}
    def handler(signum: int, _frame: Any) -> None:
        raise HarnessInterruption(signum, f"received signal {signum}")
    for sig in (signal.SIGINT, signal.SIGTERM):
        previous[sig] = signal.getsignal(sig)
        signal.signal(sig, handler)
    return previous


def restore_signal_handlers(previous: dict[int, Any]) -> None:
    for sig, old in previous.items():
        signal.signal(sig, old)


def main() -> int:
    args = parse_args()

    if not CANONICAL_IMAGE_RE.fullmatch(args.image_ref):
        print("error: --image-ref must be an immutable ghcr.io/leodbc/ghostdagsim@sha256:<64 lowercase hex> reference", file=sys.stderr)
        return 2
    if not is_int(args.rng_seed) or not 1 <= args.rng_seed <= UINT32_MAX:
        print(f"error: --rng-seed must be in [1, {UINT32_MAX}]", file=sys.stderr)
        return 2
    if not is_int(args.rng_run) or not 1 <= args.rng_run <= UINT64_MAX:
        print(f"error: --rng-run must be in [1, {UINT64_MAX}]", file=sys.stderr)
        return 2
    if not is_int(args.timeout_seconds) or not 1 <= args.timeout_seconds <= MAX_TIMEOUT_SECONDS:
        print(f"error: --timeout-seconds must be in [1, {MAX_TIMEOUT_SECONDS}]", file=sys.stderr)
        return 2

    try:
        scenario = load_scenario(args.scenario)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    run_name = (
        f"{scenario['name']}-r{scenario['revision']}-mpi{args.mpi_threads}"
        f"-seed{args.rng_seed}-rng{args.rng_run}"
    )
    results_root = args.results_root.resolve()
    try:
        results_root.mkdir(parents=True, exist_ok=True)
        run_dir = results_root / run_name
        run_dir.mkdir(parents=False, exist_ok=False)
    except FileExistsError:
        print(f"error: refusing to reuse existing result directory: {results_root / run_name}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"error: could not reserve result directory: {exc}", file=sys.stderr)
        return 2

    manifest_path = run_dir / "manifest.json"
    sim_args = simulator_arguments(scenario, run_name=run_name, rng_seed=args.rng_seed, rng_run=args.rng_run)
    container_name = f"ghostdagsim-{run_name}"
    verification_container_name = f"ghostdagsim-verify-{os.getpid()}-{int(time.monotonic_ns() % 1_000_000_000)}"
    docker_create = [
        "docker", "create", "--name", container_name,
        "-v", f"{run_dir}:/results/results/{run_name}",
        "-e", f"MPI_THREADS={args.mpi_threads}",
        args.image_ref, "--", *sim_args,
    ]

    harness_start = time.monotonic()
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "status": "starting",
        "canonical_source_sha": CANONICAL_SOURCE_SHA,
        "source_sha": None,
        "canonical_ns3_version": NS3_VERSION,
        "ns3_version": None,
        "scenario_name": scenario["name"],
        "scenario_revision": scenario["revision"],
        "scenario_role": scenario.get("role"),
        "scenario_provenance": scenario.get("provenance"),
        "mpi_threads": args.mpi_threads,
        "rng_seed": args.rng_seed,
        "rng_run": args.rng_run,
        "run_name": run_name,
        "full_simulator_arguments": sim_args,
        "requested_image_reference": args.image_ref,
        "resolved_image_digest": None,
        "container_image": args.image_ref,
        "container_digest": None,
        "image_verification": {
            "status": "not_performed_dry_run" if args.dry_run else "pending",
            "requested_image_reference": args.image_ref,
            "resolved_image_digest": None,
            "oci_labels": {},
            "inspected_source_revision": None,
            "detected_ns3_version": None,
            "failure": None,
        },
        "docker_create_command": docker_create,
        "expected_result_dir": str(run_dir),
        "timeout_seconds": args.timeout_seconds,
        "started_at": utc_now(),
        "finished_at": None,
        "harness_wall_seconds": None,
        "simulation_wall_seconds": None,
        "timed_out": False,
        "failure_kind": None,
        "failure": None,
        "docker_client_return_code": None,
        "docker_container_exit_code": None,
        "docker_status": None,
        "docker_running": None,
        "oom_killed": None,
        "exit_code": None,
        "disk_before": None,
        "disk_after": None,
        "raw_result_bytes": None,
        "output_integrity": {"status": "not_checked", "failure": None, "checked_ranks": []},
        "cleanup": {"attempted": False, "succeeded": None, "failure": None},
        **github_metadata(),
    }

    try:
        manifest["disk_before"] = disk_snapshot(results_root)
        write_manifest(manifest_path, manifest)
    except OSError as exc:
        print(f"error: harness/filesystem failure before execution: {exc}", file=sys.stderr)
        return 125

    if args.dry_run:
        manifest.update({
            "status": "dry_run",
            "finished_at": utc_now(),
            "harness_wall_seconds": round(time.monotonic() - harness_start, 6),
            "disk_after": disk_snapshot(results_root),
            "raw_result_bytes": directory_bytes(run_dir, exclude={manifest_path}),
        })
        write_manifest(manifest_path, manifest)
        print(json.dumps(manifest, indent=2, sort_keys=True))
        return 0

    if shutil.which("docker") is None:
        manifest.update({
            "status": "failed", "failure_kind": "harness_filesystem_failure",
            "failure": "docker executable not found", "exit_code": 127,
            "finished_at": utc_now(),
            "harness_wall_seconds": round(time.monotonic() - harness_start, 6),
            "disk_after": disk_snapshot(results_root),
            "raw_result_bytes": directory_bytes(run_dir, exclude={manifest_path}),
        })
        write_manifest(manifest_path, manifest)
        print("error: docker executable not found", file=sys.stderr)
        return 127

    previous_handlers = install_signal_handlers()
    container_created = False
    return_code = 125
    simulation_start: float | None = None
    simulation_end: float | None = None
    try:
        verification = verify_image(args.image_ref, verification_container_name)
        manifest["image_verification"] = verification
        manifest["resolved_image_digest"] = verification.get("resolved_image_digest")
        manifest["container_digest"] = verification.get("resolved_image_digest")
        if verification.get("status") == "verified":
            manifest["source_sha"] = verification.get("inspected_source_revision")
            manifest["ns3_version"] = verification.get("detected_ns3_version")
        if verification.get("status") != "verified":
            manifest["status"] = "failed"
            manifest["failure_kind"] = verification.get("failure_kind") or "image_verification_failure"
            manifest["failure"] = verification.get("failure") or "image verification failed"
            return_code = 125
            raise RunStop(return_code)

        create = run_command(docker_create, capture_output=True)
        if create.returncode != 0:
            detail = create.stderr.strip() or create.stdout.strip() or f"exit {create.returncode}"
            manifest["status"] = "failed"
            manifest["failure_kind"] = "docker_create_pull_failure"
            manifest["failure"] = f"docker create failed: {detail}"
            manifest["docker_client_return_code"] = create.returncode
            return_code = create.returncode or 125
            raise RunStop(return_code)
        container_created = True

        simulation_start = time.monotonic()
        try:
            start = run_command(
                ["docker", "start", "-a", container_name],
                timeout=args.timeout_seconds,
            )
            simulation_end = time.monotonic()
            manifest["docker_client_return_code"] = start.returncode
        except subprocess.TimeoutExpired:
            simulation_end = time.monotonic()
            manifest["timed_out"] = True
            manifest["status"] = "failed"
            manifest["failure_kind"] = "timeout"
            manifest["failure"] = f"simulation exceeded harness timeout of {args.timeout_seconds} seconds"
            return_code = 124

        state, inspect_error = inspect_container_state(container_name)
        if state is not None:
            manifest["docker_container_exit_code"] = state.get("ExitCode") if is_int(state.get("ExitCode")) else None
            manifest["docker_status"] = state.get("Status")
            manifest["docker_running"] = state.get("Running") if type(state.get("Running")) is bool else None
            manifest["oom_killed"] = state.get("OOMKilled") if type(state.get("OOMKilled")) is bool else None
            if state.get("Error") and not manifest.get("failure"):
                manifest["failure"] = str(state["Error"])
        elif not manifest["timed_out"]:
            manifest["status"] = "failed"
            manifest["failure_kind"] = "docker_inspect_state_failure"
            manifest["failure"] = inspect_error
            return_code = 125

        if manifest["timed_out"]:
            raise RunStop(return_code)
        if state is None:
            raise RunStop(return_code)

        persisted_exit = manifest["docker_container_exit_code"]
        docker_status = manifest["docker_status"]
        running = manifest["docker_running"]
        client_rc = manifest["docker_client_return_code"]
        oom = manifest["oom_killed"]

        if oom is True:
            manifest["status"] = "failed"
            manifest["failure_kind"] = "oom"
            manifest["failure"] = manifest.get("failure") or "Docker reported OOMKilled=true"
            return_code = persisted_exit if isinstance(persisted_exit, int) and persisted_exit != 0 else 137
            raise RunStop(return_code)
        if client_rc not in (None, 0) and docker_status == "created" and running is False:
            manifest["status"] = "failed"
            manifest["failure_kind"] = "docker_start_runtime_failure"
            manifest["failure"] = f"docker start failed before the container reached a terminal state (client return {client_rc})"
            return_code = client_rc or 125
            raise RunStop(return_code)
        if docker_status not in TERMINAL_DOCKER_STATUSES or running is not False:
            manifest["status"] = "failed"
            manifest["failure_kind"] = "docker_inspect_state_failure"
            manifest["failure"] = f"Docker state is not a coherent terminal state: status={docker_status!r}, running={running!r}"
            return_code = 125
            raise RunStop(return_code)
        if docker_status != "exited":
            manifest["status"] = "failed"
            manifest["failure_kind"] = "docker_start_runtime_failure"
            manifest["failure"] = f"container ended in Docker status {docker_status!r}"
            return_code = persisted_exit if isinstance(persisted_exit, int) and persisted_exit != 0 else 125
            raise RunStop(return_code)
        if not isinstance(persisted_exit, int):
            manifest["status"] = "failed"
            manifest["failure_kind"] = "docker_inspect_state_failure"
            manifest["failure"] = "Docker persisted exit code is missing or invalid"
            return_code = 125
            raise RunStop(return_code)
        if persisted_exit != 0:
            manifest["status"] = "failed"
            manifest["failure_kind"] = "simulator_nonzero"
            manifest["failure"] = manifest.get("failure") or f"simulator/container exited with code {persisted_exit}"
            return_code = persisted_exit
            raise RunStop(return_code)
        if client_rc != 0:
            manifest["status"] = "failed"
            manifest["failure_kind"] = "docker_start_runtime_failure"
            manifest["failure"] = f"docker start client returned {client_rc} despite persisted container exit 0"
            return_code = client_rc or 125
            raise RunStop(return_code)

        integrity = validate_output_integrity(run_dir, run_name=run_name, mpi_threads=args.mpi_threads)
        manifest["output_integrity"] = integrity
        if integrity["status"] != "basic_pass":
            manifest["status"] = "failed"
            manifest["failure_kind"] = "output_integrity_failure"
            manifest["failure"] = integrity.get("failure") or "basic output integrity validation failed"
            return_code = 1
            raise RunStop(return_code)

        manifest["status"] = "completed"
        return_code = 0
        raise RunStop(return_code)
    except RunStop as exc:
        return_code = exc.code
    except HarnessInterruption as exc:
        simulation_end = simulation_end or (time.monotonic() if simulation_start is not None else None)
        manifest["status"] = "failed"
        manifest["failure_kind"] = "interruption"
        manifest["failure"] = str(exc)
        manifest["interrupted_signal"] = exc.signum
        return_code = 128 + exc.signum if exc.signum else 130
    except KeyboardInterrupt:
        simulation_end = simulation_end or (time.monotonic() if simulation_start is not None else None)
        manifest["status"] = "failed"
        manifest["failure_kind"] = "interruption"
        manifest["failure"] = "KeyboardInterrupt"
        return_code = 130
    except OSError as exc:
        simulation_end = simulation_end or (time.monotonic() if simulation_start is not None else None)
        manifest["status"] = "failed"
        manifest["failure_kind"] = "harness_filesystem_failure"
        manifest["failure"] = f"harness/filesystem error: {exc}"
        return_code = 125
    finally:
        if simulation_start is not None:
            end = simulation_end if simulation_end is not None else time.monotonic()
            manifest["simulation_wall_seconds"] = round(max(0.0, end - simulation_start), 6)

        if container_created:
            manifest["cleanup"]["attempted"] = True
            ok, error = cleanup_container(container_name)
            manifest["cleanup"]["succeeded"] = ok
            manifest["cleanup"]["failure"] = error
            if not ok and manifest.get("status") == "completed":
                manifest["status"] = "failed"
                manifest["failure_kind"] = "docker_start_runtime_failure"
                manifest["failure"] = error
                return_code = 125

        try:
            manifest["finished_at"] = utc_now()
            manifest["harness_wall_seconds"] = round(time.monotonic() - harness_start, 6)
            manifest["exit_code"] = return_code
            manifest["disk_after"] = disk_snapshot(results_root)
            manifest["raw_result_bytes"] = directory_bytes(run_dir, exclude={manifest_path})
            write_manifest(manifest_path, manifest)
            print(f"manifest: {manifest_path}")
        except OSError as exc:
            print(f"error: harness/filesystem failure finalizing manifest: {exc}", file=sys.stderr)
            return_code = 125
        restore_signal_handlers(previous_handlers)

    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
