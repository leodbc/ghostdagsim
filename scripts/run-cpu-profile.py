#!/usr/bin/env python3
"""Gate-B Stage A3 userspace CPU sampling harness.

This harness intentionally does not run a benchmark to completion. It profiles
only the D1000 diagnostic identity for a fixed wall-clock warmup and sampling
window, then stops the simulator after gperftools has flushed per-rank profiles.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import time
from typing import Any

BASE = runpy.run_path(str(Path(__file__).with_name("run-diagnostic.py")), run_name="gateb_cpu_profile_base")

EXPECTED_MPI = 4
EXPECTED_SEED = 1
EXPECTED_RUN = 1
EXPECTED_WARMUP = 300
EXPECTED_PROFILE = 600
EXPECTED_FREQUENCY = 100
EXPECTED_DEADLINE = 1200
PROFILE_SIGNAL = 12
EXECUTION_CLASS = "diagnostic_cpu_profile"
PROFILE_SCHEMA = "ghostdagsim.gateb.cpu_profile"
PROFILE_SCHEMA_VERSION = 1


class ProfileError(RuntimeError):
    pass


def utc_now() -> str:
    return BASE["utc_now"]()


def write_json(path: Path, value: Any) -> None:
    BASE["write_json"](path, value)


def remaining(deadline_at: float, operation: str) -> float:
    return BASE["remaining_seconds"](deadline_at, operation=operation)


def run(command: list[str], *, deadline_at: float, operation: str,
        capture_output: bool = True) -> subprocess.CompletedProcess[str]:
    return BASE["run_with_deadline"](
        command, deadline_at=deadline_at, operation=operation,
        capture_output=capture_output,
    )


def container_running(name: str, *, deadline_at: float) -> bool:
    proc = run(
        ["docker", "inspect", "--format", "{{.State.Running}}", name],
        deadline_at=deadline_at, operation="container running inspection",
    )
    return proc.returncode == 0 and proc.stdout.strip() == "true"


def wait_while_alive(name: str, seconds: int, *, deadline_at: float, phase: str) -> None:
    end = time.monotonic() + seconds
    while True:
        now = time.monotonic()
        if now >= end:
            return
        if not container_running(name, deadline_at=deadline_at):
            raise ProfileError(f"diagnostic container exited during {phase}")
        sleep_for = min(5.0, end - now, remaining(deadline_at, phase))
        time.sleep(max(0.05, sleep_for))


def wait_for_rank_pids(profile_root: Path, *, deadline_at: float) -> dict[int, int]:
    while True:
        result: dict[int, int] = {}
        for rank in range(EXPECTED_MPI):
            path = profile_root / f"rank{rank}" / "rank.pid"
            if not path.is_file():
                break
            raw = path.read_text(encoding="utf-8").strip()
            if not raw.isdigit() or int(raw) <= 1:
                raise ProfileError(f"invalid rank pid for rank{rank}: {raw!r}")
            result[rank] = int(raw)
        if len(result) == EXPECTED_MPI:
            return result
        remaining(deadline_at, "rank pid discovery")
        time.sleep(0.25)


def send_profile_signal(container_name: str, pids: dict[int, int], *,
                        deadline_at: float, phase: str) -> None:
    ordered = [str(pids[rank]) for rank in range(EXPECTED_MPI)]
    proc = run(
        ["docker", "exec", container_name, "kill", f"-{PROFILE_SIGNAL}", *ordered],
        deadline_at=deadline_at, operation=f"profile signal {phase}",
    )
    if proc.returncode != 0:
        detail = proc.stderr.strip() or proc.stdout.strip() or f"exit {proc.returncode}"
        raise ProfileError(f"could not {phase} CPU profiler: {detail}")


def discover_profile_file(rank_dir: Path) -> Path | None:
    candidates = sorted(
        p for p in rank_dir.glob("cpu.prof*")
        if p.is_file() and p.stat().st_size > 0
    )
    return candidates[-1] if candidates else None


def wait_for_profiles(profile_root: Path, *, deadline_at: float) -> dict[int, Path]:
    while True:
        found: dict[int, Path] = {}
        for rank in range(EXPECTED_MPI):
            path = discover_profile_file(profile_root / f"rank{rank}")
            if path is not None:
                found[rank] = path
        if len(found) == EXPECTED_MPI:
            time.sleep(0.5)
            return found
        remaining(deadline_at, "profile flush")
        time.sleep(0.25)


def inspect_partial_events(cell_root: Path) -> tuple[dict[str, int], dict[str, float | None]]:
    counts: dict[str, int] = {}
    maxima: dict[str, float | None] = {}
    for rank in range(EXPECTED_MPI):
        path = cell_root / f"rank{rank}" / "events.jsonl"
        count = 0
        max_t: float | None = None
        if path.is_file():
            with path.open("r", encoding="utf-8") as handle:
                for line_no, line in enumerate(handle, start=1):
                    stripped = line.strip()
                    if not stripped:
                        continue
                    try:
                        event = json.loads(stripped)
                    except json.JSONDecodeError as exc:
                        raise ProfileError(
                            f"rank{rank} events.jsonl invalid JSON at line {line_no}: {exc}"
                        ) from exc
                    if not isinstance(event, dict):
                        raise ProfileError(f"rank{rank} event line {line_no} is not an object")
                    t = event.get("t")
                    if isinstance(t, (int, float)) and not isinstance(t, bool):
                        value = float(t)
                        max_t = value if max_t is None else max(max_t, value)
                    count += 1
        counts[str(rank)] = count
        maxima[str(rank)] = max_t
    return counts, maxima


def symbolize_profiles(image_id: str, cell_root: Path, profiles: dict[int, Path], *,
                       deadline_at: float) -> dict[str, str]:
    outputs: dict[str, str] = {}
    mount = f"{cell_root.resolve()}:/profile:ro"
    symbolized_root = cell_root / "symbolized"
    symbolized_root.mkdir(parents=True, exist_ok=True)
    for rank in sorted(profiles):
        raw = profiles[rank]
        relative = raw.relative_to(cell_root).as_posix()
        rank_output = symbolized_root / f"rank{rank}"
        rank_output.mkdir(parents=True, exist_ok=True)
        out_path = rank_output / "pprof.txt"
        err_path = rank_output / "pprof.stderr.txt"
        proc = run(
            [
                "docker", "run", "--rm",
                "--entrypoint", "/usr/bin/google-pprof",
                "-v", mount,
                image_id,
                "--text",
                "/usr/local/bin/ghostdagsim",
                f"/profile/{relative}",
            ],
            deadline_at=deadline_at, operation=f"symbolize rank{rank} profile",
        )
        out_path.write_text(proc.stdout, encoding="utf-8")
        err_path.write_text(proc.stderr, encoding="utf-8")
        if proc.returncode != 0 or not proc.stdout.strip():
            detail = proc.stderr.strip() or f"exit {proc.returncode}"
            raise ProfileError(f"rank{rank} symbolization failed: {detail}")
        outputs[str(rank)] = str(out_path.relative_to(cell_root))
    return outputs


def cleanup_container(name: str) -> tuple[bool, str | None]:
    return BASE["cleanup_container"](name)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", required=True, type=Path)
    parser.add_argument("--image-id", required=True)
    parser.add_argument("--mpi-threads", required=True, type=int)
    parser.add_argument("--rng-seed", required=True, type=int)
    parser.add_argument("--rng-run", required=True, type=int)
    parser.add_argument("--warmup-seconds", required=True, type=int)
    parser.add_argument("--profile-seconds", required=True, type=int)
    parser.add_argument("--frequency-hz", required=True, type=int)
    parser.add_argument("--harness-deadline-seconds", required=True, type=int)
    parser.add_argument("--runner-evidence", required=True, type=Path)
    parser.add_argument("--results-root", required=True, type=Path)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if BASE["IMAGE_ID_RE"].fullmatch(args.image_id) is None:
            raise ValueError("--image-id must be an immutable local Docker image ID sha256:<64 lowercase hex>")
        if BASE["SHA40_RE"].fullmatch(args.source_sha) is None:
            raise ValueError("--source-sha must be a full 40-character lowercase commit SHA")
        if args.mpi_threads != EXPECTED_MPI:
            raise ValueError("Stage A3 CPU profiling requires exactly MPI4")
        if args.rng_seed != EXPECTED_SEED or args.rng_run != EXPECTED_RUN:
            raise ValueError("Stage A3 CPU profiling requires RNG seed/run 1/1")
        if args.warmup_seconds != EXPECTED_WARMUP:
            raise ValueError(f"Stage A3 requires warmup {EXPECTED_WARMUP} seconds")
        if args.profile_seconds != EXPECTED_PROFILE:
            raise ValueError(f"Stage A3 requires profile window {EXPECTED_PROFILE} seconds")
        if args.frequency_hz != EXPECTED_FREQUENCY:
            raise ValueError(f"Stage A3 requires {EXPECTED_FREQUENCY} Hz sampling")
        if args.harness_deadline_seconds != EXPECTED_DEADLINE:
            raise ValueError(f"Stage A3 requires harness deadline {EXPECTED_DEADLINE} seconds")
        scenario, _ = BASE["validate_scenario"](args.scenario)
        if scenario["name"] != "diagnostic-d1000":
            raise ValueError("Stage A3 accepts only diagnostic-d1000")
        if scenario["rng"] != {"seed": EXPECTED_SEED, "run": EXPECTED_RUN}:
            raise ValueError("scenario RNG identity mismatch")
        runner = BASE["load_runner_evidence"](args.runner_evidence)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    scenario_sha = BASE["canonical_json_sha256"](scenario)
    run_name = (
        f"phase5-gateb-cpu-profile-d1000-r{scenario['revision']}-"
        f"h{scenario_sha[:12]}-mpi4-seed1-rng1"
    )
    cell_root = args.results_root
    try:
        cell_root.mkdir(parents=True, exist_ok=False)
        shutil.copyfile(args.scenario, cell_root / "scenario.json")
    except OSError as exc:
        print(f"error: cannot reserve profile results root {cell_root}: {exc}", file=sys.stderr)
        return 125

    manifest_path = cell_root / "profile-manifest.json"
    manifest: dict[str, Any] = {
        "schema": PROFILE_SCHEMA,
        "schema_version": PROFILE_SCHEMA_VERSION,
        "status": "starting",
        "execution_class": EXECUTION_CLASS,
        "simulation_completion_expected": False,
        "diagnostic_id": "D1000_CPU_PROFILE",
        "scenario_name": scenario["name"],
        "scenario_revision": scenario["revision"],
        "scenario_definition_sha256": scenario_sha,
        "source_sha": args.source_sha,
        "local_image_id": args.image_id,
        "image_reference_type": "local_image_id",
        "runner_name": runner["runner_name"],
        "mpi_size": EXPECTED_MPI,
        "rng_seed": EXPECTED_SEED,
        "rng_run": EXPECTED_RUN,
        "nodes": scenario["simulator_args"]["nodes"],
        "miners": scenario["simulator_args"]["miners"],
        "blocks_per_miner": scenario["simulator_args"]["blocks_per_miner"],
        "warmup_seconds": args.warmup_seconds,
        "profile_seconds": args.profile_seconds,
        "frequency_hz": args.frequency_hz,
        "profile_signal": PROFILE_SIGNAL,
        "started_at": utc_now(),
        "finished_at": None,
        "failure": None,
        "cleanup": {"attempted": False, "succeeded": None, "failure": None},
        "raw_profiles": {},
        "symbolized_profiles": {},
        "events_records_per_rank": {},
        "max_simulated_time_per_rank": {},
    }
    write_json(manifest_path, manifest)

    if args.dry_run:
        manifest["status"] = "dry_run"
        manifest["finished_at"] = utc_now()
        write_json(manifest_path, manifest)
        print(json.dumps(manifest, indent=2, sort_keys=True))
        return 0

    harness_start = time.monotonic()
    deadline_at = harness_start + args.harness_deadline_seconds
    container_name = (
        f"ghostdagsim-phase5-cpu-profile-"
        f"{os.getenv('GITHUB_RUN_ID', 'local')}-"
        f"{os.getenv('GITHUB_RUN_ATTEMPT', os.getpid())}"
    )
    created = False
    return_code = 125
    try:
        _, labels = BASE["inspect_local_image"](
            args.image_id, source_sha=args.source_sha, deadline_at=deadline_at
        )
        if labels.get("io.ghostdagsim.cpu_profiler") != "ON":
            raise ProfileError("local image is not a Stage A3 CPU profiler image")
        if labels.get("io.ghostdagsim.diagnostics") != "ON":
            raise ProfileError("Stage A3 image must keep diagnostics ON")

        sim_args = BASE["simulator_arguments"](
            scenario, run_name=run_name, rng_seed=EXPECTED_SEED, rng_run=EXPECTED_RUN
        )
        mount_target = f"/results/results/{run_name}"
        profile_root_in_container = f"{mount_target}/cpu-profile"
        create = run(
            [
                "docker", "create",
                "--name", container_name,
                "-v", f"{cell_root.resolve()}:{mount_target}",
                "-e", f"MPI_THREADS={EXPECTED_MPI}",
                "-e", "GHOSTDAGSIM_CPU_PROFILE=1",
                "-e", f"GHOSTDAGSIM_CPU_PROFILE_ROOT={profile_root_in_container}",
                "-e", f"GHOSTDAGSIM_CPU_PROFILE_FREQUENCY={EXPECTED_FREQUENCY}",
                "-e", f"GHOSTDAGSIM_CPU_PROFILE_SIGNAL={PROFILE_SIGNAL}",
                args.image_id,
                "--", *sim_args,
            ],
            deadline_at=deadline_at, operation="profile container creation",
        )
        if create.returncode != 0:
            detail = create.stderr.strip() or create.stdout.strip() or f"exit {create.returncode}"
            raise ProfileError(f"docker create failed: {detail}")
        created = True

        start = run(
            ["docker", "start", container_name],
            deadline_at=deadline_at, operation="profile container start",
        )
        if start.returncode != 0:
            detail = start.stderr.strip() or start.stdout.strip() or f"exit {start.returncode}"
            raise ProfileError(f"docker start failed: {detail}")

        profile_root = cell_root / "cpu-profile"
        pids = wait_for_rank_pids(profile_root, deadline_at=deadline_at)
        wait_while_alive(container_name, args.warmup_seconds,
                         deadline_at=deadline_at, phase="warmup")
        send_profile_signal(container_name, pids, deadline_at=deadline_at, phase="start")
        manifest["profile_started_at"] = utc_now()

        wait_while_alive(container_name, args.profile_seconds,
                         deadline_at=deadline_at, phase="sampling")
        send_profile_signal(container_name, pids, deadline_at=deadline_at, phase="stop")
        manifest["profile_stopped_at"] = utc_now()

        profiles = wait_for_profiles(profile_root, deadline_at=deadline_at)
        manifest["raw_profiles"] = {
            str(rank): str(path.relative_to(cell_root))
            for rank, path in profiles.items()
        }
        write_json(manifest_path, manifest)

        manifest["cleanup"]["attempted"] = True
        ok, cleanup_error = cleanup_container(container_name)
        manifest["cleanup"]["succeeded"] = ok
        manifest["cleanup"]["failure"] = cleanup_error
        created = False
        if not ok:
            raise ProfileError(cleanup_error or "profile container cleanup failed")

        manifest["symbolized_profiles"] = symbolize_profiles(
            args.image_id, cell_root, profiles, deadline_at=deadline_at
        )

        config_path = cell_root / "config.json"
        if not config_path.is_file():
            raise ProfileError("profile run did not emit config.json")
        config = json.loads(config_path.read_text(encoding="utf-8"))
        BASE["validate_config"](config, run_name=run_name, scenario=scenario)

        counts, maxima = inspect_partial_events(cell_root)
        if any(count <= 0 for count in counts.values()):
            raise ProfileError("each MPI rank must emit partial events during CPU profile")
        manifest["events_records_per_rank"] = counts
        manifest["max_simulated_time_per_rank"] = maxima
        manifest["status"] = "profile_completed"
        manifest["termination_reason"] = "profile_window_complete"
        return_code = 0

    except (ValueError, ProfileError, OSError, BASE["HarnessDeadlineExceeded"]) as exc:
        manifest["status"] = "failed"
        manifest["failure"] = str(exc)
        return_code = 125
    finally:
        if created:
            manifest["cleanup"]["attempted"] = True
            ok, cleanup_error = cleanup_container(container_name)
            manifest["cleanup"]["succeeded"] = ok
            manifest["cleanup"]["failure"] = cleanup_error
            if not ok and manifest["failure"] is None:
                manifest["failure"] = cleanup_error or "cleanup failed"
        manifest["finished_at"] = utc_now()
        manifest["harness_wall_seconds"] = round(time.monotonic() - harness_start, 6)
        write_json(manifest_path, manifest)

    print(f"profile manifest: {manifest_path}")
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
