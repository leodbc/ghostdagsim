#!/usr/bin/env python3
"""Run one canonical ghostdagsim calibration scenario and emit a manifest."""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CANONICAL_SOURCE_SHA = "ba001537e3be8edc18e8e8692121da5bcb451189"
NS3_VERSION = "3.46.1"
CALIBRATION_MPI_VALUES = (1, 2, 4)
CANONICAL_IMAGE_RE = re.compile(
    r"^ghcr\.io/leodbc/ghostdagsim@sha256:[0-9a-fA-F]{64}$"
)
ALLOWED_SCENARIOS = {"small", "representative", "heavy"}
REQUIRED_SIMULATOR_ARGS = {
    "nodes",
    "miners",
    "min_conn",
    "max_conn",
    "lambda",
    "derive_k",
    "delta",
    "dmax",
    "tau",
    "pareto_divider",
    "k",
    "txs_per_block",
    "mempool_size",
    "tx_fee_lambda",
    "tx_gen_interval",
    "tx_load",
    "snapshot_interval",
    "blocks_per_miner",
    "graphene",
    "inv_timeout",
    "tcp_mss",
}
FORBIDDEN_SCENARIO_ARGS = {"run_name", "RngSeed", "RngRun"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def disk_snapshot(path: Path) -> dict[str, int]:
    usage = shutil.disk_usage(path)
    return {
        "total_bytes": usage.total,
        "used_bytes": usage.used,
        "free_bytes": usage.free,
    }


def directory_bytes(path: Path, *, exclude: set[Path] | None = None) -> int:
    if not path.exists():
        return 0
    excluded = {p.resolve() for p in (exclude or set())}
    total = 0
    for item in path.rglob("*"):
        try:
            if item.is_file() and item.resolve() not in excluded:
                total += item.stat().st_size
        except FileNotFoundError:
            # A concurrently removed temporary file should not make manifest
            # generation fail after the simulation itself has already ended.
            continue
    return total


def cli_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float, str)):
        return str(value)
    raise ValueError(f"unsupported simulator argument value: {value!r}")


def load_scenario(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"scenario file does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid scenario JSON: {path}: {exc}") from exc

    if data.get("schema_version") != 1:
        raise ValueError("scenario schema_version must be 1")

    name = data.get("name")
    if name not in ALLOWED_SCENARIOS:
        raise ValueError(f"scenario name must be one of {sorted(ALLOWED_SCENARIOS)}")
    if path.stem != name:
        raise ValueError(
            f"scenario file name {path.stem!r} must match scenario name {name!r}"
        )

    revision = data.get("revision")
    if not isinstance(revision, str) or not revision.strip():
        raise ValueError("scenario revision must be a non-empty string")

    provenance = data.get("provenance")
    if not isinstance(provenance, dict) or not provenance.get("reference"):
        raise ValueError("scenario provenance.reference is required")

    args = data.get("simulator_args")
    if not isinstance(args, dict):
        raise ValueError("scenario simulator_args must be an object")

    missing = REQUIRED_SIMULATOR_ARGS - args.keys()
    extra = args.keys() - REQUIRED_SIMULATOR_ARGS
    forbidden = FORBIDDEN_SCENARIO_ARGS & args.keys()
    if missing:
        raise ValueError(f"scenario is missing simulator args: {sorted(missing)}")
    if extra:
        raise ValueError(f"scenario has unexpected simulator args: {sorted(extra)}")
    if forbidden:
        raise ValueError(f"scenario cannot define harness-owned args: {sorted(forbidden)}")

    nodes = args["nodes"]
    miners = args["miners"]
    blocks = args["blocks_per_miner"]
    if not isinstance(nodes, int) or nodes <= 0:
        raise ValueError("nodes must be a positive integer")
    if not isinstance(miners, int) or miners <= 0 or miners > nodes:
        raise ValueError("miners must be a positive integer not greater than nodes")
    if not isinstance(blocks, int) or blocks <= 0:
        raise ValueError("blocks_per_miner must be a positive integer")

    return data


def simulator_arguments(
    scenario: dict[str, Any], *, run_name: str, rng_seed: int, rng_run: int
) -> list[str]:
    args = [
        f"--{key}={cli_value(value)}"
        for key, value in scenario["simulator_args"].items()
    ]
    args.extend(
        [
            f"--RngSeed={rng_seed}",
            f"--RngRun={rng_run}",
            f"--run_name={run_name}",
        ]
    )
    return args


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
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".json.tmp")
    temp.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temp.replace(path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", required=True, type=Path, help="scenario JSON file")
    parser.add_argument(
        "--image-ref",
        required=True,
        help="immutable ghcr.io/leodbc/ghostdagsim@sha256:<digest> reference",
    )
    parser.add_argument(
        "--mpi-threads", required=True, type=int, choices=CALIBRATION_MPI_VALUES
    )
    parser.add_argument("--rng-seed", type=int, default=1)
    parser.add_argument("--rng-run", type=int, default=1)
    parser.add_argument(
        "--results-root",
        type=Path,
        default=Path("results"),
        help="host directory receiving simulator results (default: ./results)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="validate and emit the manifest without invoking Docker",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if not CANONICAL_IMAGE_RE.fullmatch(args.image_ref):
        print(
            "error: --image-ref must be an immutable "
            "ghcr.io/leodbc/ghostdagsim@sha256:<64 hex> reference",
            file=sys.stderr,
        )
        return 2
    if args.rng_seed <= 0 or args.rng_run <= 0:
        print(
            "error: --rng-seed and --rng-run must be positive integers",
            file=sys.stderr,
        )
        return 2

    try:
        scenario = load_scenario(args.scenario)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    run_name = f"{scenario['name']}-mpi{args.mpi_threads}-rng{args.rng_run}"
    results_root = args.results_root.resolve()
    results_root.mkdir(parents=True, exist_ok=True)
    run_dir = results_root / run_name
    manifest_path = run_dir / "manifest.json"

    if run_dir.exists() and any(run_dir.iterdir()):
        print(
            f"error: refusing to reuse non-empty result directory: {run_dir}",
            file=sys.stderr,
        )
        return 2
    run_dir.mkdir(parents=True, exist_ok=True)

    sim_args = simulator_arguments(
        scenario,
        run_name=run_name,
        rng_seed=args.rng_seed,
        rng_run=args.rng_run,
    )
    container_name = f"ghostdagsim-{run_name}"
    docker_create = [
        "docker",
        "create",
        "--name",
        container_name,
        "-v",
        f"{results_root}:/results/results",
        "-e",
        f"MPI_THREADS={args.mpi_threads}",
        args.image_ref,
        "--",
        *sim_args,
    ]

    start_iso = utc_now()
    monotonic_start = time.monotonic()
    before = disk_snapshot(results_root)
    metadata = github_metadata()
    image_digest = args.image_ref.split("@", 1)[1]

    manifest: dict[str, Any] = {
        "schema_version": 1,
        "status": "starting",
        "source_sha": CANONICAL_SOURCE_SHA,
        "container_image": args.image_ref,
        "container_digest": image_digest,
        "ns3_version": NS3_VERSION,
        "scenario_name": scenario["name"],
        "scenario_revision": scenario["revision"],
        "scenario_role": scenario.get("role"),
        "scenario_provenance": scenario.get("provenance"),
        "mpi_threads": args.mpi_threads,
        "rng_seed": args.rng_seed,
        "rng_run": args.rng_run,
        "run_name": run_name,
        "full_simulator_arguments": sim_args,
        "docker_create_command": docker_create,
        "expected_result_dir": str(run_dir),
        "started_at": start_iso,
        "finished_at": None,
        "wall_seconds": None,
        "exit_code": None,
        "oom_killed": None,
        "disk_before": before,
        "disk_after": None,
        "raw_result_bytes": None,
        "failure": None,
        **metadata,
    }
    write_manifest(manifest_path, manifest)

    if args.dry_run:
        manifest.update(
            {
                "status": "dry_run",
                "finished_at": utc_now(),
                "wall_seconds": round(time.monotonic() - monotonic_start, 6),
                "disk_after": disk_snapshot(results_root),
                "raw_result_bytes": directory_bytes(
                    run_dir, exclude={manifest_path}
                ),
            }
        )
        write_manifest(manifest_path, manifest)
        print(json.dumps(manifest, indent=2, sort_keys=True))
        return 0

    if shutil.which("docker") is None:
        manifest.update(
            {
                "status": "harness_error",
                "finished_at": utc_now(),
                "wall_seconds": round(time.monotonic() - monotonic_start, 6),
                "disk_after": disk_snapshot(results_root),
                "raw_result_bytes": directory_bytes(
                    run_dir, exclude={manifest_path}
                ),
                "failure": "docker executable not found",
            }
        )
        write_manifest(manifest_path, manifest)
        print("error: docker executable not found", file=sys.stderr)
        return 127

    container_created = False
    exit_code = 125
    oom_killed: bool | None = None
    failure: str | None = None

    try:
        create = subprocess.run(docker_create, check=False)
        if create.returncode != 0:
            exit_code = create.returncode
            failure = f"docker create failed with exit code {create.returncode}"
        else:
            container_created = True
            start = subprocess.run(
                ["docker", "start", "-a", container_name], check=False
            )
            exit_code = start.returncode

            inspect = subprocess.run(
                [
                    "docker",
                    "inspect",
                    "--format",
                    "{{json .State}}",
                    container_name,
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            if inspect.returncode == 0:
                try:
                    state = json.loads(inspect.stdout)
                    oom_killed = bool(state.get("OOMKilled", False))
                    # Docker start normally mirrors the container exit status,
                    # but prefer Docker's persisted state when available.
                    exit_code = int(state.get("ExitCode", exit_code))
                    if state.get("Error"):
                        failure = str(state["Error"])
                except (json.JSONDecodeError, TypeError, ValueError):
                    failure = "could not parse docker inspect state"
            elif failure is None:
                failure = "docker inspect failed"
    except KeyboardInterrupt:
        failure = "interrupted"
        exit_code = 130
    except OSError as exc:
        failure = f"docker execution error: {exc}"
        exit_code = 125
    finally:
        if container_created:
            subprocess.run(
                ["docker", "rm", "-f", container_name],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

    raw_bytes = directory_bytes(run_dir, exclude={manifest_path})
    manifest.update(
        {
            "status": "completed" if exit_code == 0 else "failed",
            "finished_at": utc_now(),
            "wall_seconds": round(time.monotonic() - monotonic_start, 6),
            "exit_code": exit_code,
            "oom_killed": oom_killed,
            "disk_after": disk_snapshot(results_root),
            "raw_result_bytes": raw_bytes,
            "failure": failure,
        }
    )

    if exit_code == 0 and raw_bytes == 0:
        manifest["status"] = "failed"
        manifest["failure"] = (
            "simulation exited successfully but produced no result bytes"
        )
        exit_code = 1
        manifest["exit_code"] = exit_code

    write_manifest(manifest_path, manifest)
    print(f"manifest: {manifest_path}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
