# Phase 5 checkpoint — Stage A3 retry and upstream handoff

Date: 2026-10-10

Issue: #18

## Purpose

This checkpoint is the durable resume point for Phase 5 after the first Stage A3
CPU-profile execution, the symbolization-path repair, and the decision to prepare
an upstream handoff after Phase 5 closes.

Chat memory is not authoritative. Resume work from repository state and this
checkpoint.

## Canonical technical baseline

Phase-5 technical baseline immediately before this checkpoint documentation:

`1eec9d5181f49fe89c17b695753fbf3105c0cad2`

That SHA contains the merged Stage A3 symbolization repair from PR #26.

Canonical simulator source identity remains:

`ba001537e3be8edc18e8e8692121da5bcb451189`

ns-3 remains:

`3.46.1`

Approved Phase-4 benchmark runner identity remains:

`ghostdagsim-phase4-kvm`

Infrastructure ownership remains with:

`leodbc/infra-context#38`

No stronger physical hardware or paid replacement host is part of the Phase-5
solution.

## Project state

### Phase 0

Complete.

Canonical experiment identity, RNG policy, benchmark measurements and
green/caution/no-go rules were established.

### Phase 1

Complete.

The minimal reproducible benchmark harness and explicit small, representative
and heavy scenarios were established.

### Phase 2

Complete.

The original 3-scenario × MPI {1,2,4} calibration was executed on generic
GitHub-hosted capacity.

### Phase 3

Complete.

The MPI2 SIGILL was classified as an image CPU-ISA portability defect caused by
native optimization / AVX-512 assumptions, and generic GitHub-hosted runners were
rejected for representative/heavy execution.

The selected model became GitHub Actions as control plane plus a pinned
self-hosted Linux execution target.

### Phase 4

Complete.

A portable image and stable self-hosted VM/runner were validated. Native MPI4
worked without oversubscription.

Terminal Phase-4 evidence:

- small/MPI1, MPI2, MPI4: green;
- representative/MPI1: no-go / timeout;
- representative/MPI2: caution;
- representative/MPI4: green;
- heavy/MPI1, MPI2, MPI4: no-go / timeout at 390 minutes.

### Phase 5 Gate A

Complete.

Static characterization and diagnostic protocol were established.

### Phase 5 Gate B Stage A2

Complete.

D100 completed and reproduced its structural counters.

D1000, using the same diagnostic identity, reached the 3600-second timeout after
only about 27.47 seconds of simulated time.

At the same simulated horizon, D1000 showed approximately:

- 8.99x total logged events;
- 9.10x received-message events;
- 9.42x sent-message events;
- 8.75x block-received events;
- 7.86x block-colored events;
- 252x block-orphaned events;
- 155x block-unorphaned events.

The slowdown occurred before the first 30-second snapshot and with only 14 mined
blocks. Snapshot scans and late large-DAG GHOSTDAG work therefore cannot explain
the initial collapse.

The evidence prioritizes the early transaction/network/event path but does not
yet isolate a function-level CPU hotspot.

### Phase 5 Gate B Stage A3 — first execution

Workflow run:

`37930486240`

The run successfully completed:

- 300-second warmup;
- 600-second CPU sampling window;
- four raw per-rank gperftools profiles;
- cleanup.

The run failed only during symbolization because the runner attempted to write
`pprof.txt` inside root-owned per-rank raw-profile directories.

This was a harness artifact-path defect, not a simulator, profiler, Docker, MPI
or infrastructure failure.

### Stage A3 symbolization repair

PR #26 repaired the ownership boundary.

Merged technical baseline:

`1eec9d5181f49fe89c17b695753fbf3105c0cad2`

The repaired harness:

- preserves raw profiles under `cpu-profile/rankN/`;
- writes symbolized output under runner-owned
  `symbolized/rankN/pprof.txt`;
- requires exact MPI ranks 0..3;
- includes a deterministic symbolization regression.

Post-merge validation:

- Build run `37959976171`: SUCCESS;
- Test run `37959976139`: SUCCESS;
- diagnostics OFF: SUCCESS;
- diagnostics ON: SUCCESS;
- deterministic Stage A3 CPU profile symbolization smoke: SUCCESS.

## Current authorization state

No simulator optimization is authorized yet.

Gate C is still closed.

The optimization admission rule still requires symbolized Stage A3
function-level evidence showing a specific measured CPU cost.

No canonical Phase-4 runtime classification has changed.

## Exact next action

Run exactly one new Stage A3 D1000 CPU-profile workflow using the current
canonical repository state after this checkpoint is merged.

Before dispatch, reuse `leodbc/infra-context#38` for a fresh point-in-time
readiness check.

Required readiness evidence:

- physical `devserver` idle/low;
- approved `ghostdagsim-phase4` VM healthy;
- fresh ephemeral runner under Unix user `gh-ghostdagsim`;
- runner name `ghostdagsim-phase4-kvm`;
- label `ghostdagsim-phase4`;
- Docker passing under the same Unix user;
- OpenMPI 4.1.6 / native MPI4 ranks `0,1,2,3`;
- no competing GhostDagSim workflow or benchmark;
- current canonical master SHA revalidated immediately before dispatch.

Do not reuse a stale host-idle attestation.

Do not register the runner on physical host user `leodbc`.

## After the Stage A3 rerun

1. Download and audit the full profiling artifact.
2. Require four non-empty raw profiles.
3. Require four non-empty symbolized `pprof.txt` outputs.
4. Compare rank-level hotspots and imbalance.
5. Identify the narrowest evidence-backed Gate-C optimization candidate.
6. Record:
   - measured bottleneck;
   - correctness invariant;
   - expected mechanism/complexity gain;
   - cheap before/after test;
   - proof that scientific output semantics remain unchanged.
7. Only then admit one bounded Gate-C optimization branch.

Do not combine unrelated optimizations in the first Gate-C experiment.

## Gate C

Gate C consists of bounded, independently reviewable optimization experiments.

Each accepted optimization must:

- follow directly from Gate-B evidence;
- preserve correctness;
- be measured first on cheap diagnostic workload(s);
- show repeatable material benefit;
- be rejected if benefit is not material.

## Gate D

After evidence-backed optimization exists, run the minimum canonical validation
needed to decide whether the heavy workload became viable on fixed
infrastructure.

Do not:

- move timeout thresholds merely to obtain success;
- change canonical scenario/RNG identity;
- oversubscribe MPI;
- substitute stronger hardware;
- present a diagnostic run as canonical evidence.

Phase 5 must end with an explicit heavy viability or limitation decision.

## Upstream handoff decision

After Gate D and the Phase-5 final decision, prepare an upstream handoff to
`lechinskie/ghostdagsim` before campaign-scale orchestration begins.

Classify changes into:

### Upstreamable core changes

Examples:

- portable build / CPU-ISA fixes;
- correctness fixes;
- MPI robustness;
- measured performance optimizations;
- reusable diagnostics;
- generally useful tests.

### Optionally upstreamable experiment tooling

Examples:

- benchmark harness;
- profiling helpers;
- reproducibility metadata;
- generic workflows.

### Fork-specific state that stays local

Examples:

- `devserver`;
- `ghostdagsim-phase4` VM;
- self-hosted runner registration details;
- `infra-context#38`;
- host-idle attestations;
- LEODBC-specific governance and orchestration.

Preferred delivery form:

small, reviewable upstream PRs rather than one monolithic fork merge.

Upstream acceptance is not required for Phase 5 itself to be considered
complete.

## Campaign-scale work

Campaign-scale orchestration is still deferred.

Do not begin:

- Kubernetes;
- custom scheduler/queue;
- checkpoint/resume merely to mask runtime;
- broad campaign automation;
- external storage architecture;

until Phase 5 closes and the post-Phase-5 architecture is reviewed.

## Resume protocol

If a chat/session ends, reconstruct from:

1. `docs/experiments/PHASE5_PLAN.md`;
2. this file;
3. Issue #18;
4. exact current `master` HEAD;
5. latest relevant workflow/artifact evidence.

Then continue from the **Exact next action** section above.

Never use an old SHA from this checkpoint as a substitute for verifying current
`master`.
