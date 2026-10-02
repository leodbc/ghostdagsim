# Canonical experiment baseline

## Purpose

This document freezes the identity and invariants of the first GitHub Actions
benchmarking phase for `ghostdagsim`. The purpose of Phase 0 is to remove
ambiguity before any benchmark harness, campaign runner, storage integration, or
simulator change is introduced.

## Repository identity

| Field | Canonical value |
| --- | --- |
| Working repository | `leodbc/ghostdagsim` |
| Upstream reference | `lechinskie/ghostdagsim` |
| Canonical source SHA | `ba001537e3be8edc18e8e8692121da5bcb451189` |
| Canonical base branch | `master` |
| Phase 0 branch | `phase0/canonical-experiment-baseline` |
| Baseline commit message | `profiling optimizations` |

At Phase 0 start, the working fork's `master` and upstream `master` were
identical at the canonical source SHA.

The canonical SHA is an immutable source identity. Future upstream or
`master` movement does not change this baseline. Any benchmark that intends to
represent another source revision must establish a new baseline explicitly.

## Runtime baseline

The repository's existing GitHub Actions build/test/publish workflows explicitly
pass `NS3_VERSION=3.46.1` to the Docker build. Therefore the first benchmark
image SHALL use:

- ns-3: `3.46.1`;
- the canonical source SHA above;
- the existing production `Dockerfile`;
- metrics enabled as currently built by the production Dockerfile.

The `Dockerfile` has its own default `NS3_VERSION`, but the experiment SHALL
not rely on that implicit default. The version must be passed explicitly.

## Container identity

Benchmarks MUST NOT use a mutable tag such as `latest` as their canonical
runtime identity.

Before the first benchmark run, an image built from the canonical source SHA
must be published and recorded by immutable OCI digest:

```text
ghcr.io/leodbc/ghostdagsim@sha256:<digest>
```

Phase 0 deliberately leaves the digest unset because no benchmark image is
published by this phase.

Required image metadata for every benchmark run:

- source SHA;
- image digest;
- ns-3 version;
- image build workflow/run identifier when available.

## Experiment dimensions

The initial calibration has exactly three workload classes:

- `small`: smoke/low-cost workload that proves the path end to end;
- `representative`: workload representative of the intended research use;
- `heavy`: largest plausible workload expected to be used on GitHub-hosted
  runners.

Phase 0 defines the classes, not invented scientific parameter values. Exact
scenario parameters must be committed before the first benchmark run and must
remain unchanged during the MPI calibration unless a new benchmark revision is
declared.

The MPI calibration set is fixed to:

```text
MPI_THREADS = {1, 2, 4}
```

This produces a 3 scenario × 3 MPI configuration calibration matrix.

## RNG policy

Reproducibility MUST be explicit rather than dependent on implicit ns-3
defaults.

For a benchmark comparison:

- `RngSeed` is fixed and recorded;
- `RngRun` is fixed and recorded;
- the same scenario arguments and RNG identity are used across MPI candidates.

For scientific replications after calibration:

- keep the canonical `RngSeed` fixed;
- vary `RngRun` per independent replication;
- record both values in every run manifest.

The initial canonical seed is:

```text
RngSeed = 1
```

The benchmark harness will pass it explicitly.

## Required run identity

Every run must be traceable to, at minimum:

```text
source_sha
container_digest
ns3_version
scenario_name
scenario_revision
mpi_threads
rng_seed
rng_run
full_simulator_arguments
github_workflow
github_run_id
github_run_attempt
runner_os
started_at
finished_at
wall_seconds
exit_code
```

The run manifest is part of the result, not optional logging.

## Result location

The simulator currently writes run results beneath:

```text
results/<run_name>/
```

The benchmark harness should preserve this contract rather than changing the
simulator output model in Phase 1.

## Source invariants for Phase 0

Phase 0 is documentation-only.

It MUST NOT change:

- `*.cc` or `*.h` simulator code;
- `Dockerfile` or `Dockerfile.test`;
- `entrypoint.sh`;
- existing GitHub Actions workflows;
- build semantics;
- simulation semantics.

## Explicit non-goals

The following are deliberately out of scope until measurement demonstrates a
need:

- checkpoint/resume;
- custom scheduler or queue;
- multi-runner MPI;
- Kubernetes;
- external storage integration;
- self-hosted runners;
- cloud/HPC abstraction;
- campaign-scale parallelism;
- simulator performance refactors;
- dashboards.

## Phase 0 completion gate

Phase 0 is complete when:

1. this baseline and the benchmark protocol are committed on the Phase 0 branch;
2. the branch is a documentation-only diff from the canonical SHA;
3. a draft pull request exists for audit;
4. the benchmark image digest is explicitly marked as a prerequisite for the
   later benchmark execution, not silently inferred from a tag.

No benchmark execution belongs to Phase 0.
