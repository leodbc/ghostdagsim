# Phase 5 checkpoint — Gate C complete, Gate D baseline transition

Date: 2026-10-12

Issue: #18

## Purpose

This checkpoint is the durable resume point after the first evidence-backed
Phase-5 optimization was measured, accepted and merged.

Chat memory is not authoritative. Resume from repository state, this checkpoint,
Issue #18 and exact current workflow evidence.

## Accepted simulator source

The Gate-C optimization was merged as PR #28.

Accepted simulator source SHA:

`e89e959f0fd3a908bb46227df9e45f29a8918a08`

The accepted change adds deterministic topology-degree-aware MPI SystemId
placement behind:

`--mpi_partition=degree-balanced`

Historical `round-robin` remains the default when the option is absent.

Post-merge validation:

- Build `38312853513`: SUCCESS
- Test `38312853782`: SUCCESS

## Phase status

### Phases 0–4

Complete.

The fixed execution capacity remains:

- physical host: `devserver`
- VM: `ghostdagsim-phase4`
- runner: `ghostdagsim-phase4-kvm`
- dedicated label: `ghostdagsim-phase4`
- infrastructure authority: `leodbc/infra-context#38`
- Project Request ID:
  `prq_6ee8c5ec-90c0-4b77-b07f-3f5d4e74d466`

Phase-4 heavy/MPI1, MPI2 and MPI4 all timed out under the canonical 390-minute
simulation ceiling.

### Phase 5 Gate A

Complete.

### Phase 5 Gate B

Complete.

Stage A2 established the early D1000 collapse before the first 30-second snapshot
and before a large DAG existed.

Stage A3 run `38172629979` produced valid four-rank CPU profiles.

Measured first-order bottleneck:

**severe MPI-rank work imbalance caused by round-robin node-ID placement under
the high-degree topology, producing a network-stack straggler while other ranks
spend large CPU fractions in MPI progress.**

### Phase 5 Gate C

`CLOSED / PASS`

Canonical comparison run:

`38306442092`

Artifact:

- ID: `11774462184`
- name: `phase5-gatec-placement-profile-38306442092-1`
- digest:
  `sha256:62e20d655ea77fb61277603f3f4f4fb1bb20993839cfc731cc6c79b8e4b5fcc3`

The comparison used one immutable candidate image and the same D1000 / MPI4 /
RNG 1/1 / 300-second warmup / 600-second sampling contract for both cells.

Measured direction:

- mean flat `mca_pml_ob1_progress`: 37.95% → 17.28%
- MPI-progress rank range: 55.8 pp → 13.2 pp
- mean cumulative `DistributedSimulatorImpl::ProcessOneEvent`: 47.73% → 73.53%
- event-loop rank range: 78.1 pp → 16.5 pp
- `Ipv4EndPointDemux::Lookup` rank range: 20.4 pp → 5.6 pp

Scientific-config identity check passed.

PR #28 was accepted and merged. No second Gate-C optimization candidate is
admitted before Gate D.

## Gate D protocol decision

Gate D is the minimum canonical validation required to decide exactly one of:

- `HEAVY_VIABLE`
- `HEAVY_LIMITATION_RECORDED`

The historical Phase-4 immutable image cannot be reused for this decision because
it predates the accepted Gate-C optimization.

Phase-5 therefore creates a **separately reviewed baseline transition**, as
allowed by `PHASE5_PLAN.md`.

The transition preserves all scientific/runtime-contract fields except the
accepted execution placement mechanism:

- scenario: exact `experiments/scenarios/heavy.json`
- heavy scenario SHA-256:
  `a4b55a306c7be4cf04d8ee3b7722475cb9797ef9738b1f3beed31746794a988a`
- MPI: 4
- RNG seed/run: 1/1
- simulation timeout: 23,400 s (390 min)
- harness deadline: 25,200 s (420 min)
- ns-3: 3.46.1
- build profile: optimized
- metrics: ON
- diagnostics: OFF
- native optimizations: OFF
- fixed approved VM/runner capacity
- no oversubscription
- MPI partition: `degree-balanced`

Accepted simulator source remains pinned to:

`e89e959f0fd3a908bb46227df9e45f29a8918a08`

## Gate D image trust

A separate trust anchor is introduced:

`experiments/phase5-gated-image.json`

It starts fail-closed as:

`status = unpublished`

No Gate-D heavy run is authorized while that status remains unpublished.

The image publication lane must:

1. check out the exact accepted simulator source SHA;
2. build the existing portable Dockerfile with diagnostics OFF;
3. keep ns-3 3.46.1 / optimized / metrics ON / native optimizations OFF;
4. publish to GHCR;
5. verify the immutable digest and OCI source revision;
6. run a degree-balanced MPI smoke;
7. sign the immutable image;
8. preserve publish evidence.

After publication, a separate audited repository change must update only the
Gate-D trust anchor with:

- `status = approved`
- exact immutable image digest/ref
- exact publish workflow run id

Only then may the heavy Gate-D workflow run.

## Gate D execution lane

Workflow:

`.github/workflows/phase5-gated-heavy.yml`

It runs exactly one heavy/MPI4 cell.

Valid terminal outcomes:

### Completed canonical run

If the heavy workload completes inside the unchanged 390-minute simulation
ceiling with valid output integrity and durable success evidence:

`HEAVY_VIABLE`

### Canonical timeout

If the run reaches the unchanged 390-minute timeout without OOM or unrelated
harness/infrastructure failure:

`HEAVY_LIMITATION_RECORDED`

Any other failure is **not** a Phase-5 final decision. It must be classified and
repaired without changing the heavy scenario, timeout, RNG, MPI count or fixed
hardware merely to obtain a pass.

## Exact next action

1. Review and merge the Gate-D baseline-transition PR.
2. Require green post-merge Build/Test.
3. Dispatch the Gate-D image publish workflow on exact current master.
4. Audit its image digest/source/signing evidence.
5. Update and merge only `experiments/phase5-gated-image.json` to approved
   state with that exact digest/ref/run id.
6. Reuse `leodbc/infra-context#38` for a new point-in-time host/VM readiness
   and fresh ephemeral runner.
7. Immediately dispatch exactly one Gate-D heavy workflow.
8. Audit its artifact and record the final heavy viability/limitation decision.

Do not request the fresh long-lived Gate-D runner before the image trust anchor
is approved.

## After Gate D

After the final Gate-D decision:

- record the durable Phase-5 closeout;
- prepare the upstream handoff to `lechinskie/ghostdagsim`;
- split upstreamable simulator/runtime improvements, optional experiment tooling
  and fork-specific operational state;
- prefer small reviewable upstream PRs;
- do not begin campaign-scale orchestration before Phase 5 closes.

Upstream acceptance is not required for Phase 5 itself to close.

## Resume protocol

Reconstruct from:

1. `docs/experiments/PHASE5_PLAN.md`
2. this checkpoint
3. Issue #18
4. exact current `master`
5. current open PRs
6. latest relevant workflow runs/artifacts

Never substitute a SHA written here for a fresh `master` revalidation.
