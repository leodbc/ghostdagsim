# Phase 5 checkpoint — COMPLETE / Gate D limitation recorded

Date: 2026-10-13

Issue: #18

Status:

`PHASE5_COMPLETE`

Final decision:

`HEAVY_LIMITATION_RECORDED`

## Durable authority

Chat memory is not authoritative.

Resume from:

1. `docs/experiments/PHASE5_DECISION.md`
2. `docs/experiments/PHASE5_UPSTREAM_HANDOFF.md`
3. this checkpoint
4. Issue #18
5. exact current `master`
6. exact relevant workflow/artifact evidence

Always revalidate current repository state before acting.

## Decision-point repository state

Canonical control SHA at the final Gate-D run:

`07ccfa0576d1fe5db73f308d13d3263641f9d04b`

Accepted simulator source:

`e89e959f0fd3a908bb46227df9e45f29a8918a08`

Accepted optimization:

`--mpi_partition=degree-balanced`

Canonical Gate-D image:

`ghcr.io/leodbc/ghostdagsim@sha256:99af0e185bc0c5d4e211c41862077d05c8a92e2a132f24db104a75347a8bf18a`

## Phase 5 result by gate

### Gate A

Complete.

Static source characterization produced candidate cost buckets without
preselecting an optimization.

### Gate B

Complete.

Stage A2 showed the 1000-node scaling collapse begins before the first
30-second snapshot and before a large DAG exists.

Stage A3 produced valid four-rank CPU profiles and identified severe work
imbalance under round-robin placement as the first measured bottleneck.

### Gate C

`CLOSED / PASS`

Comparison run:

`38306442092`

Accepted result:

topology-degree-aware deterministic MPI placement materially reduced rank
imbalance and MPI-progress waste while increasing useful event-loop CPU
attribution.

PR #28 merged the implementation as:

`e89e959f0fd3a908bb46227df9e45f29a8918a08`

No second optimization candidate was admitted.

### Gate D

`CLOSED / HEAVY_LIMITATION_RECORDED`

Final run:

`38396404836`

Job:

`115292630422`

Canonical identity:

- scenario SHA256:
  `a4b55a306c7be4cf04d8ee3b7722475cb9797ef9738b1f3beed31746794a988a`
- MPI4
- RNG 1/1
- `degree-balanced`
- simulator timeout: 23,400 s
- harness deadline: 25,200 s
- fixed accepted runner capacity

Terminal evidence:

- simulator failure kind: `timeout`
- exit code: `124`
- simulation wall: `23400.003728 s`
- harness wall: `23415.012876 s`
- harness deadline exhausted: `false`
- cleanup: successful

Artifact:

- ID: `11840142485`
- name: `phase5-gated-heavy-38396404836-1`
- digest:
  `sha256:1346942258fe9f342a8cbe064722044f38a436412dd2c180241842bba835e694`

Decision manifest SHA256:

`f3c6fe77d72eb23441b0f17cf0b155faa7572cca2238c86b728e02321777ccfc`

The retained rank streams contain 5,299,385 logged events and 705
`block_mined` events. The latest observed retained timestamp is about
1,374.004 simulated seconds.

## Interpretation

The degree-balanced optimization is accepted and useful.

It is insufficient, by itself, to make the canonical heavy upper-envelope
workload complete on the accepted fixed 4-core target inside the unchanged
390-minute simulator ceiling.

That is the Phase-5 answer.

Do not reinterpret the workflow-level SUCCESS as simulation completion. The
workflow succeeded because evidence collection and classification completed
correctly.

## Stop conditions

Phase 5 stops here.

Do not under Phase 5:

- admit a second optimization candidate;
- extend the simulator timeout;
- change heavy scenario identity;
- change RNG identity;
- change MPI count;
- enable oversubscription;
- provision stronger hardware;
- add checkpoint/resume;
- add Kubernetes/scheduler orchestration;
- begin campaign-scale execution.

Any such work requires a separately authorized future phase/project decision.

## Infrastructure status

The accepted persistent VM/capacity remains a reusable reference environment.

The Gate-D runner was intentionally ephemeral.

No Phase-5 authority depends on keeping an active runner listener after the
final run.

Infrastructure ownership remains with `leodbc/infra-context`.

## Upstream handoff

The upstream handoff is prepared in:

`docs/experiments/PHASE5_UPSTREAM_HANDOFF.md`

Key rule:

do not open a monolithic fork-to-upstream PR.

Current upstream had already diverged with `--seed` and
`--drain_seconds` changes touching the same topology/main source surface.
The accepted degree-balanced placement must therefore be ported on a fresh
upstream branch while preserving upstream behavior.

Recommended first upstream unit:

the core degree-balanced placement only.

Upstream acceptance is not required for Phase 5 to remain complete.

## Exact next action after this closeout is merged

1. Require green Build/Test for the closeout documentation change.
2. Close Issue #18 as complete.
3. Do not execute any additional Phase-5 benchmark.
4. If upstream contribution is desired, start only the first handoff unit from
   fresh current `lechinskie/ghostdagsim@master`.
5. Treat any campaign-scale or new-capacity work as a new separately authorized
   decision.

Never substitute the SHAs written here for fresh revalidation of live refs.
