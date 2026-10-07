# Phase 4 closeout decision

Status: **COMPLETE — evidence reviewed; stop condition reached**

Issue: #9

Phase 4 baseline:

`4d67fb14a539deb7e8f2749d017f497f6bdd90e1`

Closeout branch base:

`a053ec667f110b237e05f2a3e7a874526e14ed7e`

Canonical simulator source:

`ba001537e3be8edc18e8e8692121da5bcb451189`

ns-3:

`3.46.1`

Approved portable image:

`ghcr.io/leodbc/ghostdagsim@sha256:89e37f6f28348c189df41d611fbf4fd7041fdb7af711edb77201eec13264e366`

Approved benchmark runner:

`ghostdagsim-phase4-kvm`

Gate C source runs:

- attempt 1: `37410277338`;
- completion: `37573460831`.

Durable combined evidence index:

`experiments/phase4-gatec-complete.json`

## Purpose

Phase 4 tested the Phase 3 execution-target decision under controlled evidence:

1. repair the benchmark image so it no longer depends on accidental AVX-512 exposure;
2. accept one fixed self-hosted Linux x86_64 target with native MPI4 capacity;
3. execute the canonical 3 × 3 scenario/MPI calibration on that target;
4. compare valid Phase 4 measurements with valid Phase 2 evidence;
5. stop before campaign orchestration, checkpointing, scheduler work, or broad performance changes.

All five objectives are now satisfied.

## Gate A — portable image result

Gate A succeeded.

The portable image was built from the exact canonical source with ns-3 3.46.1
and native CPU optimization explicitly disabled.

The publication path verified:

- exact canonical source identity;
- immutable image digest;
- OCI source/revision identity;
- runtime ns-3 linkage;
- absence of decoded AVX-512 ZMM/opmask use in shipped objects;
- direct MPI2 smoke on generic hosted compute;
- cosign keyless signing and transparency-log publication.

This removes the Phase 2 accidental AVX-512 dependency from the approved
benchmark image.

## Gate B — stable execution-target result

Gate B succeeded.

The accepted runner is the isolated KVM guest `ghostdagsim-phase4-kvm` on the
owned devserver, with:

- Linux x86_64;
- Intel Core i5-4590 @ 3.30 GHz;
- 4 physical / 4 logical CPUs exposed for the benchmark contract;
- native `mpirun -np 4` success without oversubscription;
- Docker 29.1.3;
- Open MPI 4.1.6;
- exact CPU-flags fingerprint recorded;
- persistent VM identity;
- zero out-of-pocket execution capacity.

Runner identity is fail-closed and embedded into Gate C manifests.

The self-hosted target eliminated both operational blockers diagnosed in Phase
2:

- MPI2 no longer fails with SIGILL;
- MPI4 no longer fails for insufficient native slots.

Those two Phase 2 failure modes were environment/image defects, not useful
performance measurements.

## Gate C — canonical 3 × 3 result

The full canonical matrix is complete across two evidence-preserving workflow
runs.

Attempt 1 reached the 24-hour job envelope after seven valid terminal cells.
The seven valid cells were retained. A dedicated continuation reran only the
two missing cells on the same approved persistent VM with a fresh ephemeral
runner registration.

The completion workflow verified the composed matrix as:

`status = complete_matrix_evidence`

### Final matrix

| Scenario | MPI | Simulation wall | Classification |
| --- | ---: | ---: | --- |
| small | 1 | 174.393 s | green |
| small | 2 | 106.016 s | green |
| small | 4 | 75.448 s | green |
| representative | 1 | 23,400.003 s (390 min) | no-go / timeout |
| representative | 2 | 17,210.134 s (~286.84 min) | caution |
| representative | 4 | 11,375.669 s (~189.59 min) | green |
| heavy | 1 | 23,400.003 s (390 min) | no-go / timeout |
| heavy | 2 | 23,400.003 s (390 min) | no-go / timeout |
| heavy | 4 | 23,400.003 s (390 min) | no-go / timeout |

The workflow success for the completion run means evidence collection and
validation succeeded. It does not mean the heavy simulations completed.

## Valid Phase 2 comparison

Only Phase 2 measurements that represented real simulation execution are used
as performance baselines.

Phase 2 MPI2 SIGILL and MPI4 insufficient-slot durations are excluded.

### Small / MPI1

Phase 2:

- 97.030539 s;
- completed / green.

Phase 4:

- 174.393351 s;
- completed / green.

On MPI1, the accepted Phase 4 portable-image + KVM environment is about 79.7%
slower for the small calibration cell than the Phase 2 hosted/native-optimized
combination.

This is a cross-environment operational comparison. It does not isolate whether
the difference comes from CPU generation, virtualization, portable build flags,
or another environment factor.

### Representative / MPI1

Phase 2:

- 15,941.680371 s (~265.7 min);
- completed / green, with only narrow green headroom.

Phase 4:

- timed out at 23,400.002954 s (390 min);
- no-go.

The Phase 4 MPI1 path therefore consumed at least 46.8% more wall time than the
valid Phase 2 completion and still did not finish.

Again, this is a combined environment/image comparison, not attribution to one
cause.

### Heavy / MPI1

Phase 2:

- timed out at 19,200.001347 s (320 min);
- no-go.

Phase 4:

- timed out at 23,400.003441 s (390 min);
- no-go.

The stable target and additional evidence headroom did not make heavy/MPI1
viable.

## Phase 4 internal MPI scaling

Phase 4 provides the first valid comparable MPI1/MPI2/MPI4 measurements under a
single accepted image/runner identity.

### Small

All modes are green:

- MPI1: 174.393 s;
- MPI2: 106.016 s;
- MPI4: 75.448 s.

Relative to MPI1:

- MPI2 is about 1.64× faster;
- MPI4 is about 2.31× faster.

Small remains a suitable smoke/CI-scale workload; using more ranks is not
required merely to prove basic functionality.

### Representative

- MPI1: no-go at 390-minute timeout;
- MPI2: caution at ~286.84 min;
- MPI4: green at ~189.59 min.

MPI4 is about 1.51× faster than MPI2 on the accepted runner.

MPI4 finishes in less than half of the observed lower bound for MPI1, because
MPI1 had already exceeded 390 minutes without completion.

**Operational decision for this runner: MPI4 is the preferred representative
execution mode.**

### Heavy

MPI1, MPI2, and MPI4 all reached the exact 390-minute simulation timeout.

Therefore Phase 4 does not establish a viable heavy execution mode on this
runner.

Partial output byte counts differ across the timed-out heavy cells, but those
partial-output sizes are not used as a performance or completion proxy.

**Operational decision for this runner: heavy is unsupported under the current
canonical runtime contract.**

## Phase 4 decision

The Phase 3 architecture decision is **validated with an important capacity
qualification**.

### Validated

Keep GitHub Actions as the control plane for:

- CI and unit tests;
- small smoke runs;
- portable-image publication;
- provenance/signing/trust verification;
- benchmark dispatch and evidence retention.

Use an accepted fixed self-hosted target when stable CPU identity, native MPI
capacity, and long execution windows are required.

The portable image and fail-closed runner identity model should remain the
baseline for future performance work.

### Capacity qualification

The selected zero-cost 4-core KVM target is sufficient for:

- small at MPI1/MPI2/MPI4;
- representative at MPI4;
- representative at MPI2 only with caution classification.

It is not sufficient for:

- representative/MPI1 under the Phase 4 runtime contract;
- heavy at MPI1, MPI2, or MPI4.

The existence of a stable self-hosted target solved portability and runner-slot
correctness. It did **not** solve heavy-workload capacity.

## What Phase 4 does not justify

Do not respond to the heavy no-go by silently:

- extending the green/caution/no-go thresholds;
- extending timeouts until heavy happens to finish;
- enabling oversubscription;
- retrying on arbitrary runner hardware;
- changing RNG identity;
- changing the heavy scenario;
- introducing checkpoint/resume;
- adding Kubernetes or a scheduler;
- beginning campaign-scale orchestration.

Any such change belongs to a separately reviewed next phase.

## Recommended next-phase question

The next phase should be framed as a **heavy-workload execution strategy**
decision, not as campaign implementation.

It should determine the cheapest robust way to make the intended heavy or
real-world scientific workload viable while preserving the Phase 4 evidence
contract.

The evidence supports evaluating two first-order levers separately:

1. **execution capacity** — a more capable fixed CPU target and/or more native
   MPI ranks, with the exact hardware and cost measured before adoption;
2. **simulator/runtime performance** — focused profiling of the heavy workload
   on a stable accepted environment before any broad optimization work.

The phase should avoid mixing these levers until baseline profiling can show
where wall time is actually spent.

The current KVM target remains useful as a reproducible small/representative
reference platform even if a stronger target is later needed for heavy runs.

## Gate D conclusion

Gate D review is complete.

The Phase 4 acceptance criteria are satisfied:

- portable image: approved;
- fixed runner: approved;
- native MPI4: proven;
- fail-closed identity: proven;
- full 3 × 3 terminal matrix: complete;
- evidence: summarized and durably indexed;
- Phase 2 comparison: limited to valid evidence;
- campaign implementation: not started.

Phase 4 stops here.
