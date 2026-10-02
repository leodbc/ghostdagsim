# Experiment harness

This directory contains the infrastructure-calibration scenarios used to decide
whether `ghostdagsim` fits GitHub-hosted Actions. These scenarios are **not** the
scientific design of a particular study.

## Canonical identities and image trust anchor

- simulator source SHA: `ba001537e3be8edc18e8e8692121da5bcb451189`
- canonical ns-3 version for this calibration: `3.46.1`
- canonical image repository: `ghcr.io/leodbc/ghostdagsim`
- versioned trust anchor: `experiments/canonical-image.json`
- calibration RNG identity: `RngSeed=1`, `RngRun=1`
- MPI candidates: `1`, `2`, `4`

The versioned trust anchor, not metadata self-declared by a candidate image, is
the primary authority for real execution. In this Phase-1 repair its exact state
is deliberately:

```json
{
  "schema_version": 1,
  "status": "unpublished",
  "repository": "ghcr.io/leodbc/ghostdagsim",
  "source_sha": "ba001537e3be8edc18e8e8692121da5bcb451189",
  "ns3_version": "3.46.1",
  "image_digest": null,
  "image_ref": null,
  "build_workflow_run_id": null
}
```

Therefore **real execution is currently fail-closed before any Docker pull or
simulation**. Dry-run remains allowed and records both the unpublished trust
anchor and `image_verification.status = "not_performed_dry_run"`; it does not
claim that an image was verified.

When Phase 2 publishes the canonical image, a separate audited change must update
only this trust anchor with `status="approved"`, the exact
`ghcr.io/leodbc/ghostdagsim@sha256:...` reference, its matching digest, and the
build workflow run id before calibration begins. For `unpublished`, a null
`build_workflow_run_id` remains valid. For `approved`, that field is mandatory
and must be a strictly positive integer; null, booleans, zero and negative values
are rejected. A real run then requires:

1. `--image-ref` exactly equals the approved `image_ref`;
2. the digest resolved by Docker exactly equals the approved `image_digest`;
3. `org.opencontainers.image.revision` equals the canonical simulator SHA;
4. `/usr/local/bin/ghostdagsim` exists and is executable; and
5. `ldd /usr/local/bin/ghostdagsim` identifies only linked ns-3 libraries for
   exactly `3.46.1`.

The OCI revision and runtime linkage checks are defense in depth. The `ldd`
parser is line-oriented and fail-closed: it validates the actual dependency token
with a full match, accepts only a numeric SONAME suffix such as `.so.1` or
`.so.1.2`, and requires every ns-3 dependency to resolve through `=>` to a
non-empty absolute path whose basename matches that dependency token. It rejects
`=> not found`, an empty/address-only RHS, relative paths, malformed
ns-3-looking tokens, wrong versions and mixed versions. A correctly self-declared
label or an arbitrary ns-3-looking file elsewhere in the image is not sufficient
to replace the independent trust anchor.

## Scenario provenance

`small` and `heavy` use the upstream v1.0.0 release as their actual evidence.
The release evidence was revalidated before this repair:

- upstream: `lechinskie/ghostdagsim`
- release id: `396520317`
- tag: `v1.0.0`
- tag commit: `354025407cf6ec595c8550bfc453bfdee09618b2`
- published at: `2026-09-25T10:42:25Z`
- canonical release URL: `https://github.com/lechinskie/ghostdagsim/releases/tag/v1.0.0`
- SHA256 of the exact release body used as evidence:
  `631c72eb7a020492e7d201bd2bd2b0e0d9f36af6abf6f9a3f312aa9288a155e5`

The release body supplies the quick-start workload `nodes=20`, `miners=10`,
`blocks_per_miner=50` and states that the simulator was tested with up to 1000
nodes on MPI. The full release body is not copied into this repository.

| Scenario | Core workload | Basis |
| --- | --- | --- |
| `small` | 20 nodes, 10 miners, 50 blocks/miner | upstream v1.0.0 release quick-start |
| `representative` | 100 nodes, 10 miners, 1000 blocks/miner | canonical `entrypoint.sh @ ba001537...` gives the 100-node example; canonical `main.cc @ ba001537...` gives miners=10 and blocks_per_miner=1000 |
| `heavy` | 1000 nodes, 10 miners, 1000 blocks/miner | upstream v1.0.0 release states testing up to 1000 MPI nodes; canonical `main.cc @ ba001537...` supplies miner/block defaults |

No workload values were changed by this repair. Every other relevant simulator
default remains explicit in each scenario file so future C++ default changes
cannot silently alter a benchmark definition.

## Strict input validation

Scenario JSON is parsed as strict JSON: `NaN`, `Infinity`, `-Infinity`, wrong
types, booleans where integers are expected, non-finite numbers, invalid ranges,
and integers too large to convert safely to a finite float are rejected in a
controlled way. In particular, an extreme JSON integer such as `10**309` cannot
escape validation through an uncaught `OverflowError`.

`RngSeed` is constrained to positive `uint32_t`; `RngRun` is constrained to
positive `uint64_t`. For `min_conn`/`max_conn`, the canonical behavior is either
`-1/-1` for automatic topology selection or a positive pair satisfying
`min_conn <= max_conn <= nodes`.

## Scenario and run identity

The harness computes `scenario_definition_sha256` from deterministic canonical
JSON serialization of the complete scenario definition. The run name includes
the first 12 hexadecimal characters of that hash in addition to scenario name,
revision, MPI and RNG identity, for example:

```text
small-r1-h<12hex>-mpi4-seed1-rng1
```

Changing simulator arguments while accidentally retaining the same name and
revision therefore changes both `scenario_definition_sha256` and the run
identity. The hash is recorded only in the manifest; it is not self-referential
inside the scenario JSON.

The host reserves `results/<run_name>/` atomically and refuses **any** existing
path, including an empty directory. Only the current run directory is mounted
read-write into the container:

```text
host:      <results-root>/<run_name>/
container: /results/results/<run_name>/
```

## Runner and deadlines

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

Dry-run does not require an approved image because it invokes no Docker
operation. A real run remains disabled until `canonical-image.json` is approved.

Real execution uses two time limits:

- simulation timeout: default 320 minutes, configurable up to 325 minutes;
- global harness deadline: default 345 minutes, configurable up to 350 minutes.

The global deadline is monotonic and covers Docker pull, image inspect,
verification create/start, simulation create/execution, Docker inspect and the
cleanup/finalization path. Before every blocking Docker operation the harness
computes the remaining budget and uses it as the operation timeout. If setup
consumes the budget, the run fails before simulation. Cleanup uses its own short
15-second timeout so it cannot block indefinitely even when the global deadline
has already been exhausted.

`wall_seconds` is the Phase-0 compatibility alias for simulation wall time.
Whenever simulation starts, `wall_seconds == simulation_wall_seconds`.
`simulation_wall_seconds` is the explicit name used by runtime thresholds.
`harness_wall_seconds` measures the harness through finalization-state
preparation immediately before the terminal manifest candidate is persisted.
It therefore includes setup, simulation, cleanup and final result measurement,
but deliberately does not pretend to include the subsequent filesystem writes
that publish the candidate and, for success, the separate durable success
commit. If simulation never starts, `wall_seconds` remains present and null.

Finalization remains under the global deadline. The harness checks the monotonic
deadline around the final disk snapshot, periodically while traversing result
files, before and after the temporary manifest write, and immediately before the
separate success commit. A completed `manifest.json` is only a candidate and is
never sufficient for green/caution. The exact durable success commit is the
atomic replacement that publishes `results/<run_name>/success-commit.json`
after its temporary file has been written and the final deadline preflight has
passed. The marker contains the SHA-256 of the exact manifest bytes plus run and
canonical identity. There is intentionally no post-success-commit deadline check
that could turn the process into failure after consumable success evidence
already exists. Marker publication is the point of no return: if an interruption
or filesystem exception is observed around the atomic replacement, the runner
reconciles the final marker against the exact expected evidence and candidate
manifest SHA. A matching durable marker wins over that post-commit userspace
exception, no failure manifest rewrite is attempted, and SIGINT/SIGTERM are
neutralized through the immediate CLI exit. Before a coherent marker exists,
interruptions retain their normal failure semantics.

If the deadline is detected after a completed manifest candidate was published
but before the success marker commit, the run becomes
`failure_kind="harness_deadline"` with RC 124 and the failure manifest is
rewritten best-effort. Even if that rewrite itself fails, the success marker is
absent, so the surviving completed candidate remains fail-closed. Missing,
corrupt or mismatched success evidence is always no-go/error.

## Docker terminal-state contract

A run can become `completed` only if Docker state is fully present, correctly
typed and exactly coherent:

- `Status` is the string `"exited"`;
- `Running` is boolean `false`;
- `ExitCode` is an integer (not bool) and exactly `0`;
- `OOMKilled` is boolean `false`;
- `State.Error` exists as a string and is empty; and
- the Docker client return code is integer `0`.

Missing fields, malformed types, non-empty `State.Error`, unknown OOM state,
non-terminal status or any non-zero client/container code fail closed.

Container cleanup is idempotent by deterministic container name. The harness
marks a create attempt **before** invoking `docker create`; its `finally` path
then attempts `docker rm -f` even if a signal arrives after the daemon created
the container but before Python observed success. Cleanup remains bounded to 15
seconds and handles timeout, `OSError`, `HarnessInterruption` and
`KeyboardInterrupt` without letting those normal cleanup paths skip final
manifest persistence. Signal information is preserved when available, cleanup
interruption makes the run failed with a non-zero code, and `No such container`
is treated as successful idempotent cleanup. This applies to both verification
and simulation containers. SIGKILL or abrupt host destruction remains outside
the userspace guarantee.

## Basic output integrity

After coherent Docker exit 0, the harness verifies without changing C++:

- no output path is a symlink;
- `config.json` exists, is a regular file and parses as strict JSON;
- `config.json` contains mandatory `scenario_name == run_name`;
- every expected `rank0` through `rank<N-1>` directory exists and is real;
- every expected `rank<N>/events.jsonl` is a regular non-symlink file;
- every expected events file contains at least one non-empty JSON record; and
- the final non-empty record parses as a JSON object.

Final-record checking is bounded to 64 KiB. Trailing whitespace/newlines are
ignored conceptually. If the complete final record starts before the available
bounded window, validation fails explicitly rather than silently discarding a
partial line. Empty, whitespace-only, truncated and oversized final records are
all fail-closed.

A pass is recorded as `output_integrity.status = "basic_pass"`. This remains a
cheap harness-side integrity screen, not proof of scientific completeness: the
canonical C++ does not necessarily propagate every internal `ofstream`
write/open failure to process exit status.

## Manifest and summarizer coherence

Each invocation writes `results/<run_name>/manifest.json`, including scenario
content hash, trust-anchor state, image verification evidence, both deadlines,
Docker state, wall times, disk snapshots and output-integrity results. A real
successful run also writes sibling `success-commit.json`; dry-runs and failed or
incomplete runs do not require success evidence.

The summarizer does not trust `status="completed"` by itself. It reads each
`manifest.json` byte sequence exactly once, computes SHA-256 from that immutable
snapshot, and JSON-parses the same bytes; `load_success_commit` never rereads the
manifest. Before returning `green` or `caution`, it requires a valid
`success-commit.json` whose protocol, run identity and manifest SHA-256 match
that exact observed snapshot, and then requires the completed manifest to satisfy
the full canonical snapshot: canonical repository/source/ns-3 trust identity, an approved anchor
with a positive integer build run id and coherent image ref/digest, verified
image evidence for the same source/ns-3/ref/digest, no timeout/deadline/failure,
strict integer zero client/container/top-level return codes, exact
exited/non-running/non-OOM Docker state, `basic_pass` output integrity, finite
non-negative simulation/harness times, `wall_seconds` equal to
`simulation_wall_seconds`, and harness wall time not exceeding the configured
deadline. Booleans do not satisfy integer return-code or build-run-id fields.
Any incoherent completed manifest is `no-go`.

Runtime classification remains:

- `< 270 min`: `green`;
- `270 <= runtime < 330 min`: `caution`;
- `>= 330 min`: `no-go`;
- failed/incoherent/timeout/OOM manifests: `no-go`;
- dry-run manifests: `dry-run`.

`runtime_classification` is **not** the overall Phase-0 operational decision
gate. Disk headroom, storage practicality, runner stability and other Phase-0
factors remain separate inputs.

## RNG limitation and deferred work

`RngSeed` and `RngRun` control ns-3 RNG streams. The canonical simulator also
contains randomness outside those streams, so varying only `RngRun` has not been
demonstrated to create fully independent scientific replications.

This repair does not modify C++, headers, Dockerfiles, `entrypoint.sh` or GitHub
Actions. It does not publish an image, execute the real calibration matrix,
implement checkpoint/resume, add external storage or add a scheduler. Publishing
and approving the canonical image digest is the next prerequisite for Phase 2.
