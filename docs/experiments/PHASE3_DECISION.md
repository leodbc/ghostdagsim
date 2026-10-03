# Phase 3 execution-target decision

Status: **DECISION RECORDED — ready for review**

Issue: #7

Phase 3 baseline:

`8f873bb149cfe34e741b95044aa4bf1a9a994717`

Canonical simulator source:

`ba001537e3be8edc18e8e8692121da5bcb451189`

Canonical Phase 2 runtime image:

`ghcr.io/leodbc/ghostdagsim@sha256:13480d2ddc80ac63e46651f6b25b50abef33ae93cdd5ca527ca84d1d205878b0`

ns-3:

`3.46.1`

Phase 2 calibration run:

`37045361409`

Phase 3 diagnostic runs:

- direct MPI diagnostic: `37080047657`
- six-runner MPI2 sampling: `37081107243`
- static ISA inspection: `37081610281`

## Purpose

Phase 3 converts the Phase 2 calibration into an execution-target decision while
keeping observed evidence, diagnosis, uncertainty, and architecture choices
separate.

No campaign-scale implementation belongs in this phase.

## Observed Phase 2 evidence

The Phase 2 workflow executed the complete canonical 3 scenario × 3 MPI matrix.
All nine matrix cells reached a terminal state and retained a manifest/artifact.
The consolidated summarizer completed successfully.

| Scenario | MPI | Status | Runtime classification | Simulation wall | Exit/failure evidence | Raw result bytes |
| --- | ---: | --- | --- | ---: | --- | ---: |
| small | 1 | completed | green | 97.030539 s | exit 0; output integrity `basic_pass` | 9,085,955 |
| small | 2 | failed | no-go | 1.416929 s | exit 132; Open MPI child exited on SIGILL | 0 |
| small | 4 | failed | no-go | 0.214218 s | exit 1; Open MPI reported insufficient slots | 0 |
| representative | 1 | completed | green | 15,941.680371 s | exit 0; output integrity `basic_pass` | 997,047,427 |
| representative | 2 | failed | no-go | 1.517736 s | exit 132; Open MPI child exited on SIGILL | 0 |
| representative | 4 | failed | no-go | 0.214838 s | exit 1; Open MPI reported insufficient slots | 0 |
| heavy | 1 | failed | no-go | 19,200.001347 s | harness timeout at 320 min | 675,531,424 |
| heavy | 2 | failed | no-go | 2.368591 s | exit 132; Open MPI child exited on SIGILL | 0 |
| heavy | 4 | failed | no-go | 0.214520 s | exit 1; Open MPI reported insufficient slots | 0 |

Every summarized row verified:

- canonical source SHA `ba001537e3be8edc18e8e8692121da5bcb451189`;
- observed source SHA equal to the canonical source SHA;
- canonical and observed ns-3 version `3.46.1`;
- requested image ref equal to the approved immutable digest;
- resolved digest equal to the approved immutable digest;
- image verification status `verified`.

No summarized failure reported OOM. Disk free space remained roughly 91 GB after
the jobs. Memory or disk exhaustion is not the observed Phase 2 blocker.

## Diagnosed causes

### MPI 2 — classified as a CPU-ISA portability defect in the optimized image

Phase 2 showed repeatable SIGILL/exit 132 for MPI2 across all three scenarios.

The first Phase 3 reproducer used the same immutable canonical image outside the
Phase 1 harness on a fresh GitHub-hosted runner. Two trivial Open MPI ranks
worked, MPI1 worked, and the same small/MPI2 workload unexpectedly completed
with exit 0. This proved that the Phase 2 SIGILL was not deterministic from
image + scenario alone and that the benchmark harness was not required to
trigger it.

A second diagnostic sampled six independent GitHub-hosted runners. Each runner
executed the same immutable image and small/MPI2 workload through both the
canonical entrypoint and direct `mpirun -np 2`.

| Sample | CPU model | AVX-512 exposed | Entrypoint | Direct mpirun | Result |
| --- | --- | --- | ---: | ---: | --- |
| 1 | Intel Xeon Platinum 8370C | yes | 0 | 0 | success |
| 2 | AMD EPYC 7763 | no | 132 | 132 | SIGILL |
| 3 | AMD EPYC 9V74 | yes | 0 | 0 | success |
| 4 | AMD EPYC 9V45 | yes | 0 | 0 | success |
| 5 | AMD EPYC 9V74 | no | 132 | 132 | SIGILL |
| 6 | AMD EPYC 7763 | no | 132 | 132 | SIGILL |

The same EPYC 9V74 model appeared once with AVX-512 exposed and passing, and
once without AVX-512 exposed and failing. CPU model name alone is therefore not
the discriminator.

Across this six-runner sample:

- 3/3 runners exposing AVX-512 completed MPI2 successfully;
- 3/3 runners without AVX-512 exited 132/SIGILL;
- entrypoint and direct `mpirun` agreed in every sample.

The canonical Publish run configured the optimized ns-3 build with
`NS3_NATIVE_OPTIMIZATIONS=ON`.

Static inspection of the exact immutable canonical image then found AVX-512
instructions in multiple shipped ns-3 libraries, including:

- `libns3.46.1-core-optimized.so`
- `libns3.46.1-internet-optimized.so`
- `libns3.46.1-mpi-optimized.so`
- `libns3.46.1-network-optimized.so`
- `libns3.46.1-point-to-point-optimized.so`
- `libns3.46.1-stats-optimized.so`
- `libns3.46.1-traffic-control-optimized.so`

Examples include `vmovdqu8`, `vmovdqu64`, `vmovdqa64`, and `vpermt2q`
using ZMM registers.

### MPI2 classification

The evidence is sufficient to classify the Phase 2 MPI2 SIGILL as a
**portability defect in the canonical optimized runtime image**: native build
optimization emitted AVX-512 instructions, while the generic GitHub-hosted pool
does not guarantee that AVX-512 is exposed to every runner.

The exact single faulting instruction/address was not captured. That remaining
detail is not required for the execution-target decision because the
image/runtime incompatibility itself is directly demonstrated.

MPI2 Phase 2 timings are therefore not performance measurements.

### MPI 4 — classified as hosted-runner slot capacity

All three MPI4 cells failed before meaningful simulation work because Open MPI
reported fewer than four allocatable slots.

The Phase 3 diagnostics showed GitHub-hosted runners with four logical CPUs but
topologies such as two cores × two threads. The Phase 2 error is consistent with
Open MPI's native slot accounting.

No evidence supports treating `--oversubscribe` as equivalent four-rank
capacity. Oversubscription remains diagnostic-only.

MPI4 Phase 2 timings are therefore not performance measurements.

## Valid workload evidence

### Small / MPI1

Small/MPI1 is comfortably viable on the tested hosted environment:

- simulation wall: 97.030539 s;
- exit 0;
- output integrity `basic_pass`.

This is suitable as a smoke/CI-scale workload.

### Representative / MPI1

Representative/MPI1 completed successfully in 15,941.680371 seconds, about
265.7 minutes.

The Phase 0 threshold marks this green only below 270 minutes, leaving about
258 seconds (4.3 minutes) of margin.

A single successful run with only ~4.3 minutes of green headroom is not a robust
long-running production envelope.

### Heavy / MPI1

Heavy/MPI1 reached the canonical 19,200-second simulation timeout and is no-go
under the current GitHub-hosted design.

This no-go is not explained by OOM or disk exhaustion.

## Execution-target options

### Option A — generic GitHub-hosted Actions for long simulations

Advantages:

- already integrated with the repository;
- artifacts and manifests work;
- small/MPI1 is healthy.

Rejected for representative/heavy execution because:

- CPU ISA exposure is heterogeneous;
- the current native-optimized image is not portable across that pool;
- native four-rank capacity is not guaranteed;
- representative/MPI1 has only ~4.3 minutes of green headroom;
- heavy/MPI1 exceeds the canonical 320-minute timeout.

Generic GitHub-hosted Actions remains useful for CI, smoke tests, image
publication, trust checks, and lightweight diagnostics.

### Option B — pinned self-hosted GitHub Actions runner on a fixed Linux host/VM

Advantages:

- keeps the existing GitHub Actions control plane and artifact model;
- CPU model/ISA can be pinned and recorded;
- MPI slot capacity can be validated before accepting the host;
- job lifetime can be provisioned with material headroom beyond the heavy
  workload;
- minimizes orchestration change compared with a separate scheduler.

Costs/risks:

- host/VM provisioning and maintenance;
- capacity and cost become explicit project concerns;
- long-run artifact retention may later need a dedicated storage decision.

**Selected.**

### Option C — external HPC/batch scheduler as the immediate target

Potentially appropriate at larger campaign scale, but not selected yet.

Phase 2 proves a need for a stable long-lived execution environment; it does not
yet prove that a separate scheduler/queue is necessary.

Deferred until workload concurrency or campaign scale justifies it.

### Option D — optimize simulator/runtime first, then remain hosted

Not selected as the primary target.

Performance optimization may still be valuable, but using it to recover a
fragile hosted-runner envelope would mix runtime optimization with execution
reliability. Broad optimization is deferred until a stable execution target
exists.

### Option E — checkpoint/resume

Deferred.

Phase 2 does not prove that checkpointing is the first-order requirement.
Environment stability and image portability should be fixed first.

## Decision

### Selected execution model

**Use GitHub Actions as the control plane, but move representative/heavy
simulation execution to a pinned self-hosted Linux runner on a fixed host or
cloud VM.**

Generic GitHub-hosted runners remain the target for:

- CI/unit tests;
- small smoke runs;
- image publication and provenance;
- trust-anchor verification;
- lightweight diagnostics.

The self-hosted execution target must pass explicit acceptance gates before any
new calibration is treated as comparable evidence:

1. fixed and recorded x86_64 CPU model/ISA;
2. canonical runner metadata captured in every manifest;
3. direct `mpirun -np 4` trivial-rank probe succeeds **without**
   `--oversubscribe`;
4. job lifetime provides material headroom beyond 320 minutes;
5. sufficient memory/disk verified before execution;
6. container runtime and Open MPI versions recorded;
7. immutable image digest enforced exactly as in Phase 2.

### Mandatory image portability repair

Before production calibration on the selected target, build a new benchmark
image from the same canonical simulator source with native CPU optimization
disabled or replaced by an explicit portable ISA baseline.

The benchmark image must not depend on accidental AVX-512 exposure from the
image-build machine.

The new image must receive:

- immutable digest;
- source SHA attestation;
- ns-3 version attestation;
- runtime linkage verification;
- static ISA inspection showing the declared baseline is respected.

The Phase 2 image remains immutable historical evidence and must not be silently
retagged or replaced.

## Rejected/deferred alternatives

- generic GitHub-hosted pool for representative/heavy: rejected for the next
  execution phase;
- `--oversubscribe` as a way to claim MPI4 capacity: rejected;
- retrying until a runner with AVX-512 appears: rejected;
- checkpoint/resume: deferred;
- Kubernetes: deferred;
- external HPC/batch scheduler: deferred;
- broad simulator performance refactor: deferred;
- campaign-scale orchestration: deferred.

## Remaining uncertainty

The exact faulting AVX-512 instruction/address from a failing runner was not
captured.

MPI2 and MPI4 scaling performance remain unknown because Phase 2 did not produce
valid comparable timings for those modes.

Neither uncertainty changes the execution-target decision.

## Next-phase scope

The next implementation phase should be limited to:

1. provision or identify one pinned self-hosted Linux runner/VM;
2. verify native MPI slot capacity and long-job envelope;
3. create the portable benchmark image from canonical source;
4. verify provenance/runtime/ISA identity;
5. rerun the 3 × 3 calibration matrix on the stable target;
6. compare valid measurements with Phase 2 without treating the invalid MPI2/4
   Phase 2 timings as performance baselines;
7. stop for another evidence review before campaign-scale orchestration.

## Phase 3 stop condition

The execution-target decision is now recorded.

No provisioning, portable-image implementation, or new calibration belongs in
Phase 3. Those actions require the next phase.
