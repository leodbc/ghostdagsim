# Experiment harness

This directory contains the infrastructure-calibration scenarios used to decide
whether `ghostdagsim` fits GitHub-hosted Actions. These scenarios are **not** the
scientific design of a particular study.

## Canonical identities

- simulator source SHA: `ba001537e3be8edc18e8e8692121da5bcb451189`
- canonical ns-3 version for this calibration: `3.46.1`
- benchmark image: `ghcr.io/leodbc/ghostdagsim@sha256:<digest>` only
- calibration RNG identity: `RngSeed=1`, `RngRun=1`
- MPI candidates: `1`, `2`, `4`

A real run does not trust the requested digest by itself. Before simulation the
harness pulls and inspects the image, requires the OCI label
`org.opencontainers.image.revision` to equal the canonical simulator SHA, and
checks runtime libraries under `/usr/local/lib/ns3/` for exactly ns-3 `3.46.1`.
If any check is absent, ambiguous, or different, the run fails closed. Dry-run
mode performs no mandatory pull and records
`image_verification.status = "not_performed_dry_run"`.

Publishing/pinning the compliant canonical image is outside this PR and remains
a prerequisite for real calibration.

## Scenario provenance

All repository links below are pinned to the canonical source SHA rather than a
mutable branch.

| Scenario | Core workload | Basis |
| --- | --- | --- |
| `small` | 20 nodes, 10 miners, 50 blocks/miner | canonical snapshot of the upstream v1.0.0 quick-start workload |
| `representative` | 100 nodes, 10 miners, 1000 blocks/miner | canonical `entrypoint.sh` gives the 100-node example; canonical `main.cc` gives defaults miners=10 and blocks_per_miner=1000 |
| `heavy` | 1000 nodes, 10 miners, 1000 blocks/miner | canonical README records MPI testing up to 1000 nodes; canonical `main.cc` gives the current miner/block defaults |

Every other relevant simulator default is explicit in each scenario file so
future C++ default changes cannot silently alter a benchmark revision.
`representative` means representative *infrastructure calibration* workload,
not evidence of a particular scientific campaign.

## Strict input validation

Scenario JSON is parsed as strict JSON: `NaN`, `Infinity`, `-Infinity`, wrong
types, booleans where integers are expected, non-finite numbers, and invalid
ranges are rejected. Validation follows the canonical simulator parameter types
and the current calibration contract. `RngSeed` is constrained to positive
`uint32_t`; `RngRun` is constrained to positive `uint64_t`.

For `min_conn`/`max_conn`, the current canonical behavior is represented as
either `-1/-1` for automatic topology selection or a positive integer pair with
`min_conn <= max_conn <= nodes`.

## Run identity and output isolation

The deterministic run name includes scenario, scenario revision, MPI, seed, and
run, for example:

```text
small-r1-mpi4-seed1-rng1
```

The host reserves `results/<run_name>/` atomically and refuses **any** existing
path, including an empty directory. Only the current run directory is mounted
read-write into the container:

```text
host:      <results-root>/<run_name>/
container: /results/results/<run_name>/
```

This preserves the simulator's relative `results/<run_name>/` contract without
granting the container write access to results from other runs.

## Runner

Example dry-run validation:

```bash
python3 scripts/run-experiment.py \
  --scenario experiments/scenarios/small.json \
  --image-ref ghcr.io/leodbc/ghostdagsim@sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef \
  --mpi-threads 1 \
  --rng-seed 1 \
  --rng-run 1 \
  --results-root /tmp/ghostdagsim-results \
  --dry-run
```

A real run uses the same command without `--dry-run` and with the compliant
canonical image digest.

The harness has its own simulation timeout. The default is 320 minutes, below
the Phase-0 330-minute no-go boundary and leaving cleanup/finalization margin;
the accepted configurable maximum is 325 minutes. Image pull, image inspection,
and `docker create` are included in `harness_wall_seconds` but excluded from
`simulation_wall_seconds`. The simulation timer starts immediately before
`docker start -a`.

## Manifest and failure semantics

Each invocation writes `results/<run_name>/manifest.json`. Important structured
fields include:

- `harness_wall_seconds` and `simulation_wall_seconds`;
- `timed_out`, `failure_kind`, and `failure`;
- Docker client return code, persisted container exit code, status/running state,
  and `OOMKilled`;
- requested image reference, resolved digest, relevant OCI labels, inspected
  source revision, detected ns-3 version, and image-verification status;
- disk snapshots and raw result bytes;
- basic output-integrity status.

Failure kinds distinguish timeout, OOM, simulator non-zero, Docker pull/create,
Docker start/runtime, Docker inspect/state, harness/filesystem, interruption,
image-verification, and output-integrity failures. A successful Docker exit code
alone is never sufficient: `completed` requires a coherent terminal Docker state
and passing basic output validation.

On SIGINT, SIGTERM, Ctrl+C, or timeout, the harness attempts to inspect state and
force-remove any known simulation container, then finalizes the manifest when
the host filesystem remains writable. Abrupt host destruction or SIGKILL cannot
be made cleanup-safe by a userspace harness and is explicitly not guaranteed.

## Basic output integrity

After a terminal exit 0, the harness verifies, without changing C++:

- `config.json` exists, is regular/non-symlink, and parses as strict JSON;
- the config's `scenario_name`/run identity matches when present;
- `rank0` through `rank<N-1>` exist as real directories;
- each expected `events.jsonl` is a regular non-symlink file;
- the last observable non-empty JSONL record parses as a JSON object, using only
  a bounded tail read rather than rereading giant outputs.

A pass is recorded as `output_integrity.status = "basic_pass"`; failures are
`basic_fail` and make the run non-completed. This check is intentionally only a
cheap harness-side integrity screen. The canonical C++ currently does not
necessarily propagate every internal `ofstream` write/open failure to the
process exit status, so this harness **cannot prove complete scientific output
integrity** without future simulator changes. Such C++ changes are out of scope
for Phase 1.

## RNG limitation

`RngSeed` and `RngRun` control ns-3 RNG streams. The canonical simulator also
contains its own randomness outside those streams, so varying only `RngRun` has
**not** been demonstrated to create fully independent scientific replications of
the entire simulation. This does not invalidate the Phase-2 MPI 1/2/4
calibration, which keeps the RNG identity controlled. A scientific campaign
must revisit replication policy before production research runs.

## Summary

Summarize one or more manifests as CSV:

```bash
python3 scripts/summarize-experiment.py results/*/manifest.json
```

The CSV uses `runtime_classification`, based only on completed simulation wall
time and execution integrity:

- `green`: completed + valid finite `simulation_wall_seconds` < 270 minutes;
- `caution`: completed + 270 <= simulation wall time < 330 minutes;
- `no-go`: >= 330 minutes, or failed/incomplete/timeout/OOM/integrity failure;
- `dry-run`: command/manifest validation only.

`runtime_classification` is **not** the overall Phase-0 operational decision
gate. Disk headroom, storage practicality, runner stability, and other Phase-0
factors remain separate inputs. The CSV therefore also exposes measured resource
and execution fields for later operational evaluation; no new overall threshold
is invented here.

The 3×MPI calibration matrix belongs to Phase 2 and is not executed or
implemented by this repair.
