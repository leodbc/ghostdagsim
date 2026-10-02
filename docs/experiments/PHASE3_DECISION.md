# Phase 3 execution-target decision

Status: **OPEN — diagnosis in progress**

Issue: #7

Phase 3 baseline:

`8f873bb149cfe34e741b95044aa4bf1a9a994717`

Canonical simulator source:

`ba001537e3be8edc18e8e8692121da5bcb451189`

Canonical runtime image:

`ghcr.io/leodbc/ghostdagsim@sha256:13480d2ddc80ac63e46651f6b25b50abef33ae93cdd5ca527ca84d1d205878b0`

ns-3:

`3.46.1`

Phase 2 calibration run:

`37045361409`

## Purpose

Phase 3 turns the Phase 2 calibration evidence into an execution-target
decision.

This document deliberately separates:

1. observed evidence;
2. diagnosed causes;
3. unresolved uncertainty;
4. execution-target options;
5. the final decision.

No campaign-scale implementation belongs here.

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
the jobs. Memory or disk exhaustion is therefore not the observed Phase 2
blocker.

## What the evidence already establishes

### MPI 1

The small workload is comfortably viable on the tested GitHub-hosted runner.

The representative workload completed successfully in 15,941.680371 seconds,
about 265.7 minutes. This is technically below the 270-minute green/caution
boundary, but only by about 258 seconds (4.3 minutes). A single successful run
with that margin is weak operational headroom.

The heavy workload did not complete before the canonical 320-minute simulation
timeout. Under the current GitHub-hosted design it is a no-go.

### MPI 4

All three MPI 4 cells failed before meaningful simulation work because Open MPI
reported that the environment did not expose enough allocatable slots for four
ranks.

This is currently classified as a runner-capacity/configuration limitation, not
as a measured simulator scaling result.

Using `--oversubscribe` would change the resource model. It may be useful as a
diagnostic experiment, but an oversubscribed result must not be treated as
evidence that the current runner genuinely provides four-rank capacity.

### MPI 2

All three MPI 2 cells failed within seconds with exit code 132 and Open MPI
reporting that a child exited on SIGILL (Illegal instruction).

The consistency across small, representative, and heavy workloads shows that
the failure is not dependent on scenario scale.

This does **not** yet establish the root cause. MPI 2 must not be used for
performance comparison until the SIGILL path is reproduced and classified.

## MPI 2 diagnostic questions

The next diagnostic must use the smallest reproducer that preserves the
canonical source/image identity and should answer, in order:

1. Does the exact canonical image reproduce SIGILL with two ranks on the same
   GitHub-hosted runner when invoked directly outside the full benchmark
   harness?
2. Does one rank remain healthy under the same invocation and CPU environment?
3. Which process/rank reaches SIGILL and at what point relative to
   `MpiInterface::Enable`, topology creation, and `Simulator::Run`?
4. Does the failure depend on the production optimized build profile?
5. Is the instruction failure in ghostdagsim/ns-3 code, Open MPI, or another
   linked runtime library?
6. Is the behavior specific to the hosted runner CPU/runtime characteristics?

A narrow diagnostic workflow is allowed if needed to collect this evidence. It
must not silently mutate the canonical benchmark image or claim a repaired
performance result.

## Execution-target options

### Option A — remain on GitHub-hosted Actions

Potential advantages:

- existing workflow and artifact handling already work;
- small/MPI1 is comfortably viable;
- representative/MPI1 completed.

Material concerns:

- representative/MPI1 has only about 4.3 minutes of margin before caution;
- heavy/MPI1 is no-go at the 320-minute timeout;
- MPI2 is unusable until SIGILL is understood;
- MPI4 has no native capacity on the tested runner.

This option is not yet selected.

### Option B — use a longer-lived self-hosted/HPC/cloud execution environment

Potential advantages:

- more predictable CPU/rank capacity;
- longer wall-time envelope;
- potentially enough headroom for heavy workloads;
- better fit for long-running simulation campaigns.

Costs/risks:

- provisioning and maintenance;
- separate storage/retention design may become necessary;
- reproducibility metadata must remain as strict as the current GitHub harness.

This option is not yet selected.

### Option C — optimize simulator/runtime first, then re-evaluate hosted Actions

Potential advantages:

- may reduce representative/heavy runtime enough to recover headroom;
- may expose or fix the MPI2 failure if it originates in the distributed
  execution path.

Costs/risks:

- performance changes can affect scientific/runtime behavior and need careful
  validation;
- broad optimization before diagnosing SIGILL would mix causes.

This option is not yet selected.

### Option D — checkpoint/resume

Checkpoint/resume is deferred.

Phase 2 does not prove that continuity of one simulation is the fundamental
constraint. Environment selection and simulator/runtime diagnosis must be
considered first.

## Decision status

**PENDING**

Phase 3 must not select an execution target until the MPI2 SIGILL has been
classified enough to distinguish an environment limitation from a simulator or
runtime defect.

The final decision record will state:

- selected execution target;
- supporting evidence;
- known limitations;
- rejected/deferred alternatives;
- exact scope for the next implementation phase.
