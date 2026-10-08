#!/usr/bin/env python3
"""Run one Phase-5 Gate-B diagnostic cell without producing canonical evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

NS3_VERSION = "3.46.1"
DIAGNOSTIC_ROLE = "phase5_gateb_diagnostic"
EXECUTION_CLASS = "diagnostic"
DIAGNOSTIC_SCHEMA = "ghostdagsim.gateb.diagnostics"
EXPECTED_RUNNER_NAME = "ghostdagsim-phase4-kvm"
EXPECTED_RUNNER_LABEL = "ghostdagsim-phase4"
EXPECTED_MPI_SIZE = 4
IMAGE_ID_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
SAFE_REVISION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
RANK_DIR_RE = re.compile(r"^rank([0-9]+)$")
UINT32_MAX = (1 << 32) - 1
UINT64_MAX = (1 << 64) - 1
CLEANUP_TIMEOUT_SECONDS = 15
RUNNER_APPROVAL_PATH = Path(__file__).resolve().parents[1] / "experiments" / "runner-approval.json"

REQUIRED_SIMULATOR_ARGS = {
    "nodes", "miners", "min_conn", "max_conn", "lambda", "derive_k",
    "delta", "dmax", "tau", "pareto_divider", "k", "txs_per_block",
    "mempool_size", "tx_fee_lambda", "tx_gen_interval", "tx_load",
    "snapshot_interval", "blocks_per_miner", "graphene", "inv_timeout",
    "tcp_mss",
}
FORBIDDEN_SCENARIO_ARGS = {"run_name", "RngSeed", "RngRun"}

COMMON_SIMULATOR_ARGS: dict[str, Any] = {
    "miners": 10,
    "min_conn": -1,
    "max_conn": -1,
    "lambda": 20.0,
    "derive_k": False,
    "delta": 0.01,
    "dmax": 0.0,
    "tau": 1.0,
    "pareto_divider": 5.0,
    "k": 10,
    "txs_per_block": 100,
    "mempool_size": 10000,
    "tx_fee_lambda": 150.0,
    "tx_gen_interval": 0.5,
    "tx_load": 0.0,
    "snapshot_interval": 30.0,
    "blocks_per_miner": 20,
    "graphene": False,
    "inv_timeout": 20.0,
    "tcp_mss": 536,
}

SCENARIO_CONTRACTS = {
    "diagnostic-d100": {
        "diagnostic_id": "D100",
        "nodes": 100,
        "simulation_timeout": 1200,
        "harness_deadline": 1800,
    },
    "diagnostic-d1000": {
        "diagnostic_id": "D1000",
        "nodes": 1000,
        "simulation_timeout": 3600,
        "harness_deadline": 4500,
    },
}


class HarnessDeadlineExceeded(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def reject_json_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON numeric constant is not allowed: {value}")


def strict_json_loads(text: str, *, context: str) -> Any:
    try:
        return json.loads(text, parse_constant=reject_json_constant)
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"invalid {context}: {exc}") from exc


def strict_json_file(path: Path, *, context: str | None = None) -> dict[str, Any]:
    try:
        value = strict_json_loads(
            path.read_text(encoding="utf-8"), context=context or str(path)
        )
    except OSError as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{context or path} must contain a JSON object")
    return value


def canonical_json_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def same_typed_value(actual: Any, expected: Any) -> bool:
    return type(actual) is type(expected) and actual == expected


def validate_scenario(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    scenario = strict_json_file(path, context="diagnostic scenario")
    if type(scenario.get("schema_version")) is not int or scenario["schema_version"] != 1:
        raise ValueError("diagnostic scenario schema_version must be integer 1")

    name = scenario.get("name")
    if name not in SCENARIO_CONTRACTS:
        raise ValueError(
            "diagnostic harness accepts only diagnostic-d100 and diagnostic-d1000; "
            f"refusing scenario {name!r}"
        )
    if path.stem != name:
        raise ValueError(f"scenario filename {path.stem!r} must match name {name!r}")
    if scenario.get("role") != DIAGNOSTIC_ROLE:
        raise ValueError(f"scenario role must be {DIAGNOSTIC_ROLE!r}")
    if scenario.get("execution_class") != EXECUTION_CLASS:
        raise ValueError("scenario execution_class must be 'diagnostic'")

    revision = scenario.get("revision")
    if not isinstance(revision, str) or SAFE_REVISION_RE.fullmatch(revision) is None:
        raise ValueError("scenario revision has invalid format")

    provenance = scenario.get("provenance")
    if not isinstance(provenance, dict):
        raise ValueError("scenario provenance must be an object")
    if not isinstance(provenance.get("reference"), str) or not provenance["reference"]:
        raise ValueError("scenario provenance.reference must be non-empty")

    rng = scenario.get("rng")
    if not isinstance(rng, dict) or set(rng) != {"seed", "run"}:
        raise ValueError("scenario rng must contain exactly seed and run")
    if type(rng["seed"]) is not int or rng["seed"] != 1:
        raise ValueError("Gate-B diagnostic rng.seed must be integer 1")
    if type(rng["run"]) is not int or rng["run"] != 1:
        raise ValueError("Gate-B diagnostic rng.run must be integer 1")

    sim = scenario.get("simulator_args")
    if not isinstance(sim, dict):
        raise ValueError("scenario simulator_args must be an object")
    forbidden = sorted(FORBIDDEN_SCENARIO_ARGS & set(sim))
    if forbidden:
        raise ValueError(f"harness-owned arguments present in simulator_args: {forbidden}")
    if set(sim) != REQUIRED_SIMULATOR_ARGS:
        missing = sorted(REQUIRED_SIMULATOR_ARGS - set(sim))
        extra = sorted(set(sim) - REQUIRED_SIMULATOR_ARGS)
        raise ValueError(f"simulator_args keys mismatch; missing={missing}, extra={extra}")

    contract = SCENARIO_CONTRACTS[name]
    expected = {"nodes": contract["nodes"], **COMMON_SIMULATOR_ARGS}
    for key, expected_value in expected.items():
        actual = sim.get(key)
        if not same_typed_value(actual, expected_value):
            raise ValueError(
                f"diagnostic scenario {name} has unexpected {key}: "
                f"expected={expected_value!r}, observed={actual!r}"
            )

    return scenario, contract


def load_runner_evidence(path: Path) -> dict[str, Any]:
    data = strict_json_file(path, context="runner evidence")
    if type(data.get("schema_version")) is not int or data["schema_version"] != 1:
        raise ValueError("runner evidence schema_version must be integer 1")
    if data.get("status") != "verified":
        raise ValueError("runner evidence status must be verified")
    if data.get("runner_name") != EXPECTED_RUNNER_NAME:
        raise ValueError("runner evidence does not identify ghostdagsim-phase4-kvm")
    if data.get("dedicated_label") != EXPECTED_RUNNER_LABEL:
        raise ValueError("runner evidence dedicated label mismatch")
    if data.get("runner_os") != "Linux" or data.get("runner_arch") != "X64":
        raise ValueError("runner evidence must identify Linux/X64")
    if data.get("native_mpi4_probe") != "pass":
        raise ValueError("runner evidence requires native_mpi4_probe=pass")
    for key in ("logical_cpus", "physical_cores"):
        if type(data.get(key)) is not int or data[key] < EXPECTED_MPI_SIZE:
            raise ValueError(f"runner evidence {key} must be at least {EXPECTED_MPI_SIZE}")
    approval_sha = data.get("runner_approval_sha256")
    if not isinstance(approval_sha, str) or HEX64_RE.fullmatch(approval_sha) is None:
        raise ValueError("runner evidence runner_approval_sha256 must be 64 lowercase hex")
    try:
        expected_approval_sha = hashlib.sha256(RUNNER_APPROVAL_PATH.read_bytes()).hexdigest()
    except OSError as exc:
        raise ValueError(f"cannot read runner approval authority {RUNNER_APPROVAL_PATH}: {exc}") from exc
    if approval_sha != expected_approval_sha:
        raise ValueError("runner evidence is not bound to the repository runner approval file")
    return data


def cli_value(value: Any) -> str:
    if type(value) is bool:
        return "true" if value else "false"
    if type(value) in (int, float):
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("non-finite simulator argument")
        return str(value)
    raise ValueError(f"unsupported simulator argument type: {type(value).__name__}")


def simulator_arguments(
    scenario: dict[str, Any], *, run_name: str, rng_seed: int, rng_run: int
) -> list[str]:
    args = [
        f"--{key}={cli_value(value)}"
        for key, value in scenario["simulator_args"].items()
    ]
    args.extend(
        [f"--RngSeed={rng_seed}", f"--RngRun={rng_run}", f"--run_name={run_name}"]
    )
    return args


def remaining_seconds(deadline_at: float, *, operation: str) -> float:
    remaining = deadline_at - time.monotonic()
    if remaining <= 0:
        raise HarnessDeadlineExceeded(f"harness deadline exhausted during {operation}")
    return remaining


def run_with_deadline(
    command: list[str],
    *,
    deadline_at: float,
    operation: str,
    timeout_cap: float | None = None,
    capture_output: bool = True,
) -> subprocess.CompletedProcess[str]:
    timeout = remaining_seconds(deadline_at, operation=operation)
    if timeout_cap is not None:
        timeout = min(timeout, timeout_cap)
    try:
        return subprocess.run(
            command,
            check=False,
            text=True,
            stdout=subprocess.PIPE if capture_output else None,
            stderr=subprocess.PIPE if capture_output else None,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise HarnessDeadlineExceeded(
            f"harness deadline exhausted during {operation}"
        ) from exc


def inspect_local_image(
    image_id: str, *, source_sha: str, deadline_at: float
) -> tuple[dict[str, Any], dict[str, str]]:
    proc = run_with_deadline(
        ["docker", "image", "inspect", image_id],
        deadline_at=deadline_at,
        operation="local image inspection",
    )
    if proc.returncode != 0:
        detail = proc.stderr.strip() or proc.stdout.strip() or f"exit {proc.returncode}"
        raise ValueError(f"docker image inspect failed: {detail}")
    parsed = strict_json_loads(proc.stdout, context="docker image inspect output")
    if not isinstance(parsed, list) or len(parsed) != 1 or not isinstance(parsed[0], dict):
        raise ValueError("docker image inspect must return exactly one image object")
    image = parsed[0]
    if image.get("Id") != image_id:
        raise ValueError(
            f"local image ID mismatch: requested={image_id!r}, observed={image.get('Id')!r}"
        )
    config = image.get("Config")
    labels = config.get("Labels") if isinstance(config, dict) else None
    if not isinstance(labels, dict):
        raise ValueError("local image is missing Config.Labels")
    required_labels = {
        "org.opencontainers.image.revision": source_sha,
        "io.ghostdagsim.diagnostics": "ON",
        "io.ghostdagsim.metrics": "on",
        "io.ghostdagsim.ns3.build_profile": "optimized",
        "io.ghostdagsim.ns3.native_optimizations": "off",
        "io.ghostdagsim.ns3.version": NS3_VERSION,
    }
    for key, expected in required_labels.items():
        if labels.get(key) != expected:
            raise ValueError(
                f"local image label mismatch for {key}: "
                f"expected={expected!r}, observed={labels.get(key)!r}"
            )
    return image, labels


def write_json(path: Path, value: Any) -> None:
    payload = json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(payload, encoding="utf-8")
    temp.replace(path)


def github_identity() -> tuple[int | None, int | None]:
    def parse(name: str) -> int | None:
        value = os.getenv(name)
        return int(value) if value and value.isdigit() else None
    return parse("GITHUB_RUN_ID"), parse("GITHUB_RUN_ATTEMPT")


def validate_events_jsonl(path: Path, *, deadline_at: float) -> int:
    count = 0
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line_no, line in enumerate(handle, start=1):
                if line_no % 1024 == 0:
                    remaining_seconds(deadline_at, operation=f"events validation {path}")
                stripped = line.strip()
                if not stripped:
                    continue
                value = strict_json_loads(
                    stripped, context=f"{path} line {line_no}"
                )
                if not isinstance(value, dict):
                    raise ValueError(f"{path} line {line_no} is not a JSON object")
                count += 1
    except UnicodeDecodeError as exc:
        raise ValueError(f"events JSONL is not UTF-8: {path}: {exc}") from exc
    if count == 0:
        raise ValueError(f"events JSONL has no JSON records: {path}")
    return count


def validate_config(config: dict[str, Any], *, run_name: str, scenario: dict[str, Any]) -> None:
    if config.get("scenario_name") != run_name:
        raise ValueError("config.json scenario_name does not match diagnostic run identity")
    key_map = {
        "inv_timeout": "inv_timeout_seconds",
    }
    for scenario_key, expected in scenario["simulator_args"].items():
        config_key = key_map.get(scenario_key, scenario_key)
        if config_key not in config:
            raise ValueError(f"config.json missing {config_key}")
        observed = config[config_key]
        if not same_typed_value(observed, expected):
            # JSON encoders may serialize mathematically integral doubles as integers;
            # retain strict boolean handling while permitting numeric equality.
            numeric = (
                type(observed) in (int, float)
                and type(expected) in (int, float)
                and type(observed) is not bool
                and type(expected) is not bool
                and float(observed) == float(expected)
            )
            if not numeric:
                raise ValueError(
                    f"config.json mismatch for {config_key}: "
                    f"expected={expected!r}, observed={observed!r}"
                )


def validate_output_integrity(
    cell_root: Path,
    *,
    run_name: str,
    scenario: dict[str, Any],
    mpi_size: int,
    deadline_at: float,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": "incomplete",
        "failure": None,
        "checked_ranks": [],
        "events_records_per_rank": {},
        "instrumentation_base_sha": None,
    }
    try:
        for index, item in enumerate(cell_root.rglob("*")):
            if index % 256 == 0:
                remaining_seconds(deadline_at, operation="output symlink validation")
            if item.is_symlink():
                raise ValueError(f"unexpected symlink in diagnostic output: {item}")

        config_path = cell_root / "config.json"
        if not config_path.is_file():
            raise ValueError("config.json is missing")
        config = strict_json_file(config_path, context="config.json")
        validate_config(config, run_name=run_name, scenario=scenario)

        observed_rank_dirs: dict[int, Path] = {}
        for item in cell_root.iterdir():
            match = RANK_DIR_RE.fullmatch(item.name)
            if match:
                if not item.is_dir():
                    raise ValueError(f"{item.name} is not a directory")
                observed_rank_dirs[int(match.group(1))] = item
        expected_ranks = set(range(mpi_size))
        if set(observed_rank_dirs) != expected_ranks:
            raise ValueError(
                f"rank directory set mismatch: expected={sorted(expected_ranks)}, "
                f"observed={sorted(observed_rank_dirs)}"
            )

        instrumentation_base: str | None = None
        sim = scenario["simulator_args"]
        for rank in range(mpi_size):
            remaining_seconds(deadline_at, operation=f"rank{rank} integrity validation")
            rank_dir = observed_rank_dirs[rank]
            diagnostics_path = rank_dir / "diagnostics.json"
            events_path = rank_dir / "events.jsonl"
            if not diagnostics_path.is_file():
                raise ValueError(f"rank{rank}/diagnostics.json is missing")
            if not events_path.is_file():
                raise ValueError(f"rank{rank}/events.jsonl is missing")

            diagnostics = strict_json_file(
                diagnostics_path, context=f"rank{rank}/diagnostics.json"
            )
            if diagnostics.get("diagnostic_only") is not True:
                raise ValueError(f"rank{rank} diagnostics is not diagnostic_only=true")
            if diagnostics.get("schema") != DIAGNOSTIC_SCHEMA:
                raise ValueError(f"rank{rank} diagnostics schema mismatch")
            if type(diagnostics.get("schema_version")) is not int or diagnostics["schema_version"] != 1:
                raise ValueError(f"rank{rank} diagnostics schema_version mismatch")
            if diagnostics.get("rank") != rank:
                raise ValueError(f"rank{rank} diagnostics rank mismatch")
            if diagnostics.get("mpi_size") != mpi_size:
                raise ValueError(f"rank{rank} diagnostics mpi_size mismatch")
            if diagnostics.get("scenario") != run_name:
                raise ValueError(f"rank{rank} diagnostics scenario identity mismatch")
            for key in ("nodes", "miners", "blocks_per_miner"):
                if diagnostics.get(key) != sim[key]:
                    raise ValueError(f"rank{rank} diagnostics {key} mismatch")

            build = diagnostics.get("build")
            if not isinstance(build, dict) or build.get("diagnostics") is not True:
                raise ValueError(f"rank{rank} diagnostics build identity is invalid")
            observed_base = build.get("instrumentation_base_sha")
            if not isinstance(observed_base, str) or SHA40_RE.fullmatch(observed_base) is None:
                raise ValueError(f"rank{rank} instrumentation_base_sha is invalid")
            if instrumentation_base is None:
                instrumentation_base = observed_base
            elif instrumentation_base != observed_base:
                raise ValueError("instrumentation_base_sha differs across ranks")

            process_timing = diagnostics.get("process_timing")
            if not isinstance(process_timing, dict) or process_timing.get("interval") != "Simulator::Run":
                raise ValueError(f"rank{rank} diagnostics timing interval mismatch")
            for timing_key in (
                "simulation_wall_ns", "process_cpu_ns", "user_cpu_ns", "system_cpu_ns"
            ):
                if type(process_timing.get(timing_key)) is not int or process_timing[timing_key] < 0:
                    raise ValueError(f"rank{rank} diagnostics {timing_key} is invalid")

            records = validate_events_jsonl(events_path, deadline_at=deadline_at)
            result["events_records_per_rank"][str(rank)] = records
            result["checked_ranks"].append(rank)

        result["instrumentation_base_sha"] = instrumentation_base
        result["status"] = "complete"
        return result
    except HarnessDeadlineExceeded:
        raise
    except (OSError, ValueError) as exc:
        result["failure"] = str(exc)
        return result


def inspect_container_state(name: str, *, timeout: float = CLEANUP_TIMEOUT_SECONDS) -> dict[str, Any] | None:
    try:
        proc = subprocess.run(
            ["docker", "inspect", name],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    try:
        parsed = strict_json_loads(proc.stdout, context="docker inspect output")
    except ValueError:
        return None
    if not isinstance(parsed, list) or len(parsed) != 1 or not isinstance(parsed[0], dict):
        return None
    state = parsed[0].get("State")
    return state if isinstance(state, dict) else None


def cleanup_container(name: str) -> tuple[bool, str | None]:
    try:
        proc = subprocess.run(
            ["docker", "rm", "-f", name],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=CLEANUP_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    if proc.returncode == 0 or "No such container" in proc.stderr:
        return True, None
    return False, proc.stderr.strip() or proc.stdout.strip() or f"exit {proc.returncode}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", required=True, type=Path)
    parser.add_argument("--image-id", required=True)
    parser.add_argument("--mpi-threads", required=True, type=int)
    parser.add_argument("--rng-seed", required=True, type=int)
    parser.add_argument("--rng-run", required=True, type=int)
    parser.add_argument("--timeout-seconds", required=True, type=int)
    parser.add_argument("--harness-deadline-seconds", required=True, type=int)
    parser.add_argument("--runner-evidence", required=True, type=Path)
    parser.add_argument("--results-root", required=True, type=Path)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="validate the diagnostic contract and emit a dry-run manifest without Docker",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        if IMAGE_ID_RE.fullmatch(args.image_id) is None:
            raise ValueError("--image-id must be an immutable local Docker image ID sha256:<64 lowercase hex>")
        if SHA40_RE.fullmatch(args.source_sha) is None:
            raise ValueError("--source-sha must be a full 40-character lowercase commit SHA")
        if args.mpi_threads != EXPECTED_MPI_SIZE:
            raise ValueError("Gate-B diagnostics require exactly MPI4")
        if not (1 <= args.rng_seed <= UINT32_MAX) or args.rng_seed != 1:
            raise ValueError("Gate-B diagnostics require --rng-seed 1")
        if not (1 <= args.rng_run <= UINT64_MAX) or args.rng_run != 1:
            raise ValueError("Gate-B diagnostics require --rng-run 1")

        scenario, contract = validate_scenario(args.scenario)
        if args.rng_seed != scenario["rng"]["seed"] or args.rng_run != scenario["rng"]["run"]:
            raise ValueError("CLI RNG identity must match diagnostic scenario rng identity")
        if args.timeout_seconds != contract["simulation_timeout"]:
            raise ValueError(
                f"{scenario['name']} requires simulation timeout {contract['simulation_timeout']} seconds"
            )
        if args.harness_deadline_seconds != contract["harness_deadline"]:
            raise ValueError(
                f"{scenario['name']} requires harness deadline {contract['harness_deadline']} seconds"
            )
        if args.harness_deadline_seconds <= args.timeout_seconds:
            raise ValueError("harness deadline must exceed simulation timeout")
        runner_evidence = load_runner_evidence(args.runner_evidence)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    scenario_sha = canonical_json_sha256(scenario)
    diagnostic_id = contract["diagnostic_id"]
    run_name = (
        f"phase5-gateb-{diagnostic_id.lower()}-r{scenario['revision']}-"
        f"h{scenario_sha[:12]}-mpi{args.mpi_threads}-seed{args.rng_seed}-rng{args.rng_run}"
    )
    run_id, run_attempt = github_identity()

    cell_root = args.results_root
    try:
        cell_root.mkdir(parents=True, exist_ok=False)
        shutil.copyfile(args.scenario, cell_root / "scenario.json")
    except OSError as exc:
        print(f"error: cannot reserve diagnostic results root {cell_root}: {exc}", file=sys.stderr)
        return 125

    run_log_path = cell_root / "run.log"
    run_log_path.write_text(
        f"diagnostic_id={diagnostic_id}\nrun_name={run_name}\nexecution_class=diagnostic\n",
        encoding="utf-8",
    )

    harness_start = time.monotonic()
    started_at = utc_now()
    deadline_at = harness_start + args.harness_deadline_seconds
    sim = scenario["simulator_args"]

    manifest: dict[str, Any] = {
        "schema_version": 1,
        "status": "starting",
        "execution_class": EXECUTION_CLASS,
        "diagnostic_id": diagnostic_id,
        "scenario_name": scenario["name"],
        "scenario_revision": scenario["revision"],
        "scenario_definition_sha256": scenario_sha,
        "scenario_role": scenario["role"],
        "scenario_provenance": scenario["provenance"],
        "run_id": run_id,
        "run_attempt": run_attempt,
        "run_name": run_name,
        "source_sha": args.source_sha,
        "instrumentation_base_sha": None,
        "ns3_version": NS3_VERSION,
        "metrics_enabled": True,
        "diagnostics_enabled": True,
        "optimized": True,
        "native_optimizations": False,
        "local_image_id": args.image_id,
        "image_reference_type": "local_image_id",
        "image_revision": None,
        "runner_name": runner_evidence["runner_name"],
        "runner_approval_sha256": runner_evidence["runner_approval_sha256"],
        "mpi_size": args.mpi_threads,
        "rng_seed": args.rng_seed,
        "rng_run": args.rng_run,
        "nodes": sim["nodes"],
        "miners": sim["miners"],
        "blocks_per_miner": sim["blocks_per_miner"],
        "full_simulator_arguments": simulator_arguments(
            scenario, run_name=run_name, rng_seed=args.rng_seed, rng_run=args.rng_run
        ),
        "simulation_timeout_seconds": args.timeout_seconds,
        "harness_deadline_seconds": args.harness_deadline_seconds,
        "started_at": started_at,
        "finished_at": None,
        "simulation_wall_seconds": None,
        "harness_wall_seconds": None,
        "exit_code": None,
        "timed_out": False,
        "oom_killed": None,
        "failure_kind": None,
        "failure": None,
        "docker_container_exit_code": None,
        "output_integrity": {
            "status": "not_checked",
            "failure": None,
            "checked_ranks": [],
        },
        "cleanup": {"attempted": False, "succeeded": None, "failure": None},
    }
    manifest_path = cell_root / "manifest.json"
    timing_path = cell_root / "timing.json"
    write_json(manifest_path, manifest)

    if args.dry_run:
        manifest.update(
            {
                "status": "dry_run",
                "finished_at": utc_now(),
                "harness_wall_seconds": round(time.monotonic() - harness_start, 6),
                "exit_code": 0,
            }
        )
        write_json(manifest_path, manifest)
        write_json(
            timing_path,
            {
                "started_at": manifest["started_at"],
                "finished_at": manifest["finished_at"],
                "simulation_wall_seconds": None,
                "harness_wall_seconds": manifest["harness_wall_seconds"],
                "simulation_timeout_seconds": args.timeout_seconds,
                "harness_deadline_seconds": args.harness_deadline_seconds,
            },
        )
        print(json.dumps(manifest, indent=2, sort_keys=True))
        return 0

    if shutil.which("docker") is None:
        manifest.update(
            {
                "status": "failed",
                "failure_kind": "docker_unavailable",
                "failure": "docker executable not found",
                "exit_code": 127,
                "finished_at": utc_now(),
                "harness_wall_seconds": round(time.monotonic() - harness_start, 6),
            }
        )
        write_json(manifest_path, manifest)
        write_json(timing_path, {k: manifest[k] for k in (
            "started_at", "finished_at", "simulation_wall_seconds", "harness_wall_seconds",
            "simulation_timeout_seconds", "harness_deadline_seconds"
        )})
        return 127

    container_name = (
        f"ghostdagsim-phase5-{diagnostic_id.lower()}-"
        f"{run_id or 'local'}-{run_attempt or os.getpid()}"
    )
    docker_created = False
    simulation_start: float | None = None
    return_code = 125

    try:
        _, labels = inspect_local_image(
            args.image_id, source_sha=args.source_sha, deadline_at=deadline_at
        )
        manifest["image_revision"] = labels["org.opencontainers.image.revision"]
        write_json(manifest_path, manifest)

        sim_args = manifest["full_simulator_arguments"]
        mount_target = f"/results/results/{run_name}"
        create_cmd = [
            "docker", "create",
            "--name", container_name,
            "-v", f"{cell_root.resolve()}:{mount_target}",
            "-e", f"MPI_THREADS={args.mpi_threads}",
            args.image_id,
            "--",
            *sim_args,
        ]
        create = run_with_deadline(
            create_cmd,
            deadline_at=deadline_at,
            operation="diagnostic container creation",
        )
        with run_log_path.open("a", encoding="utf-8") as log:
            if create.stdout:
                log.write(create.stdout)
            if create.stderr:
                log.write(create.stderr)
        if create.returncode != 0:
            raise RuntimeError(
                "docker_create_failure: "
                + (create.stderr.strip() or create.stdout.strip() or f"exit {create.returncode}")
            )
        docker_created = True

        simulation_start = time.monotonic()
        remaining_before_sim = remaining_seconds(deadline_at, operation="simulation start")
        simulation_budget = min(float(args.timeout_seconds), remaining_before_sim)
        deadline_is_limiter = remaining_before_sim <= float(args.timeout_seconds)
        try:
            with run_log_path.open("a", encoding="utf-8") as log:
                start = subprocess.run(
                    ["docker", "start", "-a", container_name],
                    check=False,
                    text=True,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    timeout=simulation_budget,
                )
            manifest["simulation_wall_seconds"] = round(
                time.monotonic() - simulation_start, 6
            )
        except subprocess.TimeoutExpired:
            manifest["simulation_wall_seconds"] = round(
                time.monotonic() - simulation_start, 6
            )
            manifest["timed_out"] = True
            if deadline_is_limiter:
                manifest["failure_kind"] = "harness_deadline"
                manifest["failure"] = "global harness deadline exhausted during simulation"
            else:
                manifest["failure_kind"] = "timeout"
                manifest["failure"] = (
                    f"simulation exceeded diagnostic timeout of {args.timeout_seconds} seconds"
                )
            state = inspect_container_state(container_name)
            if state is not None:
                manifest["oom_killed"] = state.get("OOMKilled")
                manifest["docker_container_exit_code"] = state.get("ExitCode")
            return_code = 124
            raise HarnessDeadlineExceeded(manifest["failure"])

        state = inspect_container_state(container_name)
        if state is None:
            manifest["failure_kind"] = "docker_inspect_state_failure"
            manifest["failure"] = "could not inspect diagnostic container terminal state"
            return_code = 125
            raise RuntimeError(manifest["failure"])

        manifest["oom_killed"] = state.get("OOMKilled")
        manifest["docker_container_exit_code"] = state.get("ExitCode")
        if state.get("OOMKilled") is True:
            manifest["failure_kind"] = "oom"
            manifest["failure"] = "Docker reported OOMKilled=true"
            return_code = 137
            raise RuntimeError(manifest["failure"])
        if state.get("Status") != "exited" or state.get("Running") is not False:
            manifest["failure_kind"] = "docker_inspect_state_failure"
            manifest["failure"] = "diagnostic container did not reach exited/non-running state"
            return_code = 125
            raise RuntimeError(manifest["failure"])
        if not isinstance(state.get("Error"), str) or state.get("Error") != "":
            manifest["failure_kind"] = "docker_runtime_failure"
            manifest["failure"] = f"Docker State.Error is non-empty: {state.get('Error')!r}"
            return_code = 125
            raise RuntimeError(manifest["failure"])
        if type(state.get("ExitCode")) is not int or state["ExitCode"] != 0 or start.returncode != 0:
            manifest["failure_kind"] = "simulator_nonzero"
            manifest["failure"] = (
                f"simulator/container exit was non-zero: state={state.get('ExitCode')!r}, "
                f"docker_start={start.returncode!r}"
            )
            return_code = state.get("ExitCode") if type(state.get("ExitCode")) is int and state["ExitCode"] != 0 else 1
            raise RuntimeError(manifest["failure"])

        # Cleanup before artifact validation so no process can continue mutating output.
        manifest["cleanup"]["attempted"] = True
        ok, cleanup_error = cleanup_container(container_name)
        manifest["cleanup"]["succeeded"] = ok
        manifest["cleanup"]["failure"] = cleanup_error
        docker_created = False
        if not ok:
            manifest["failure_kind"] = "cleanup_failure"
            manifest["failure"] = cleanup_error or "container cleanup failed"
            return_code = 125
            raise RuntimeError(manifest["failure"])

        integrity = validate_output_integrity(
            cell_root,
            run_name=run_name,
            scenario=scenario,
            mpi_size=args.mpi_threads,
            deadline_at=deadline_at,
        )
        manifest["output_integrity"] = integrity
        if integrity["status"] != "complete":
            manifest["failure_kind"] = "output_integrity_failure"
            manifest["failure"] = integrity.get("failure") or "diagnostic output integrity failed"
            return_code = 1
            raise RuntimeError(manifest["failure"])

        manifest["instrumentation_base_sha"] = integrity.get("instrumentation_base_sha")
        manifest["status"] = "completed"
        return_code = 0

    except HarnessDeadlineExceeded as exc:
        if manifest["failure_kind"] is None:
            manifest["failure_kind"] = "harness_deadline"
            manifest["failure"] = str(exc)
            return_code = 124
        manifest["status"] = "failed"
    except (ValueError, RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
        if manifest["failure_kind"] is None:
            manifest["failure_kind"] = "harness_failure"
            manifest["failure"] = str(exc)
        manifest["status"] = "failed"
    finally:
        if docker_created:
            manifest["cleanup"]["attempted"] = True
            ok, cleanup_error = cleanup_container(container_name)
            manifest["cleanup"]["succeeded"] = ok
            manifest["cleanup"]["failure"] = cleanup_error
            if not ok and return_code == 0:
                return_code = 125
                manifest["status"] = "failed"
                manifest["failure_kind"] = "cleanup_failure"
                manifest["failure"] = cleanup_error or "container cleanup failed"

        manifest["exit_code"] = return_code
        manifest["finished_at"] = utc_now()
        manifest["harness_wall_seconds"] = round(time.monotonic() - harness_start, 6)
        try:
            write_json(manifest_path, manifest)
            write_json(
                timing_path,
                {
                    "started_at": manifest["started_at"],
                    "finished_at": manifest["finished_at"],
                    "simulation_wall_seconds": manifest["simulation_wall_seconds"],
                    "harness_wall_seconds": manifest["harness_wall_seconds"],
                    "simulation_timeout_seconds": args.timeout_seconds,
                    "harness_deadline_seconds": args.harness_deadline_seconds,
                },
            )
        except OSError as exc:
            print(f"error: could not persist final diagnostic evidence: {exc}", file=sys.stderr)
            return_code = 125

    print(f"manifest: {manifest_path}")
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
