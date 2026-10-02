# Benchmark protocol

## Objective

Measure whether representative `ghostdagsim` simulations fit GitHub-hosted
Actions reliably and determine the most useful local MPI rank count before a
campaign runner is built.

The benchmark exists to make the next architecture decision with evidence. It
is not itself a research campaign.

## Preconditions

A benchmark run may start only after all of the following are true:

1. source is pinned to
   `ba001537e3be8edc18e8e8692121da5bcb451189`;
2. the production experiment image was built from that source revision;
3. the image is referenced by immutable OCI digest;
4. exact `small`, `representative`, and `heavy` scenario parameter files
   are committed;
5. the benchmark harness records the run manifest defined in
   `BASELINE.md`.

If any identity input changes, the benchmark revision changes.

## Calibration matrix

The first calibration matrix is exactly:

| Scenario | MPI_THREADS |
| --- | ---: |
| small | 1 |
| small | 2 |
| small | 4 |
| representative | 1 |
| representative | 2 |
| representative | 4 |
| heavy | 1 |
| heavy | 2 |
| heavy | 4 |

Total: **9 simulation jobs**.

Use the same explicit `RngSeed` and `RngRun` across MPI candidates for a
given scenario during performance calibration.

Initial calibration RNG identity:

```text
RngSeed = 1
RngRun  = 1
```

This RNG choice is a benchmark control, not a substitute for independent
replications in later scientific campaigns.

## Scenario definition rules

### small

Purpose: cheap smoke workload.

It should:

- exercise Docker, MPI, metrics, result mounting, manifest generation, and
  artifact handling;
- finish quickly enough that harness failures are inexpensive;
- not be used to infer heavy-workload scaling by itself.

### representative

Purpose: approximate the workload the project actually intends to run most
often.

Its parameter values must come from the intended experiment design or an
existing representative invocation. Do not invent values merely to make the
benchmark convenient.

### heavy

Purpose: test the largest plausible workload intended for GitHub-hosted
execution.

It should be realistic, not an artificial denial-of-service stress case. If the
real intended workload is larger than the runner can support, the benchmark
should expose that result instead of hiding it.

## Required measurements

Every matrix job must record:

### Identity

- source SHA;
- image digest;
- ns-3 version;
- scenario name and revision;
- full simulator arguments;
- `MPI_THREADS`;
- `RngSeed`;
- `RngRun`;
- GitHub run identifiers.

### Runtime

- wall-clock start/end;
- wall-clock duration;
- simulator/container exit code;
- timeout state, if any.

### Storage

- host filesystem free/used space before the simulation;
- raw result bytes after the simulation;
- compressed result bytes when compression is evaluated;
- host filesystem free/used space after the simulation.

### Memory / failure evidence

Prefer an explicit peak-memory measurement when the harness can collect it
without perturbing the simulation materially. At minimum record enough
container/runner state to distinguish:

- normal exit;
- timeout;
- container OOM/resource failure;
- disk exhaustion;
- simulator error.

### Output integrity

Confirm that the expected `results/<run_name>/` directory exists and that the
run manifest is preserved even when the simulation fails.

## Operational thresholds

These are conservative decision gates for the initial GitHub-hosted design, not
scientific constraints on `ghostdagsim`.

### Green

A configuration is green when:

- simulation wall time is below **270 minutes (4 h 30 min)**;
- no memory/resource failure is observed;
- disk has comfortable headroom;
- result upload/retention is practical;
- repeated smoke validation is stable.

### Caution

A configuration is caution when:

- wall time is **270–330 minutes**; or
- disk/memory headroom is narrow; or
- result size makes artifact retention materially awkward; or
- MPI scaling is unstable.

Do not scale campaign concurrency from a caution result without investigating
the bottleneck first.

### No-go for the initial GitHub-hosted architecture

A configuration is a no-go when:

- simulation wall time is **330 minutes or more**;
- it reaches the platform job timeout;
- it exhausts memory or disk;
- required output cannot be retained or exported reliably.

A no-go result does **not** trigger checkpoint implementation automatically.
The next decision is to compare simulator optimization, a longer-lived
self-hosted/HPC/cloud environment, and only then checkpoint/resume if continuity
of a single simulation truly requires it.

## MPI selection rule

Do not assume `MPI_THREADS=4` is best because the runner exposes four CPUs.

Select the campaign MPI value only after the 1/2/4 calibration. Consider:

- wall-clock improvement;
- stability;
- memory pressure;
- output correctness/integrity;
- whether additional ranks provide material speedup.

Prefer the smallest rank count that captures most of the useful speedup when
the larger setting adds meaningful overhead or instability.

## Parallelism during calibration

The first calibration workflow should start conservatively:

```text
max-parallel = 3 or 4
```

Do not begin at the account concurrency ceiling. Calibration is measuring the
workload, not maximizing throughput.

## Failure isolation

The benchmark matrix should eventually use independent jobs and
`fail-fast: false` so a failed scenario does not cancel unrelated measurements.

Each job must have a run name that uniquely encodes at least:

```text
scenario + mpi_threads + rng_run
```

## Result retention

For the calibration phase, short-lived GitHub Actions artifacts are acceptable.

The benchmark must measure raw and compressed output sizes before a permanent
storage strategy is selected. Phase 0 intentionally does not choose external
storage without those measurements.

## Scientific replication after calibration

The performance calibration uses one controlled RNG identity to compare runtime
conditions.

A later experiment campaign uses independent ns-3 runs:

```text
fixed RngSeed
RngRun = 1, 2, 3, ...
```

The number of scientific replications is part of the experiment design and is
not decided by this infrastructure protocol.

## Decision gate after the 9-job calibration

After calibration, stop implementation and review the measurements.

Proceed to a GitHub Actions campaign matrix only if the intended scenarios have
adequate runtime/resource headroom and the approach remains operationally
appropriate.

If they do not, do not paper over the evidence with recursive workflows,
automatic restart chains, or premature checkpoint code. Re-evaluate the
execution environment or simulator bottleneck first.

## Phase boundaries

Phase 0: canonical documentation only.

Phase 1: minimal benchmark harness and scenario definitions.

Phase 2: execute the 9-job calibration matrix.

Phase 3: analyze results and decide whether GitHub-hosted Actions remains the
execution target.

Campaign execution, external storage, hardening, and scale testing come only
after that decision.
