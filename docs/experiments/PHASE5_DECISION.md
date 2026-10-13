# Phase 5 closeout decision

Status: **COMPLETE — Gate D closed / HEAVY_LIMITATION_RECORDED**

Issue: #18

Canonical control-plane SHA at the final Gate-D decision:

`07ccfa0576d1fe5db73f308d13d3263641f9d04b`

Accepted simulator source:

`e89e959f0fd3a908bb46227df9e45f29a8918a08`

Accepted optimization:

`--mpi_partition=degree-balanced`

Canonical Gate-D image:

`ghcr.io/leodbc/ghostdagsim@sha256:99af0e185bc0c5d4e211c41862077d05c8a92e2a132f24db104a75347a8bf18a`

Final Gate-D workflow run:

`38396404836`

## Purpose

Phase 5 started from the Phase-4 finding that the canonical heavy workload did
not complete on the accepted fixed 4-core execution target at MPI1, MPI2 or
MPI4 within the 390-minute simulator timeout.

The phase intentionally kept physical execution capacity fixed and asked a
narrower question:

> Can measured software/runtime profiling identify one bounded optimization
> that materially improves the heavy execution path without changing scientific
> semantics, and does that accepted optimization make the canonical heavy
> workload viable under the unchanged runtime contract?

The answer is now complete.

## Gate A — static characterization

Gate A completed the source-level characterization without preselecting an
optimization.

The initial candidate cost buckets were:

1. transaction/event scheduling;
2. blockchain/GHOSTDAG processing;
3. network/MPI fanout and rank imbalance;
4. metrics/output serialization and snapshot scanning.

No static hypothesis was treated as measured evidence.

## Gate B — profiling result

Gate B completed the diagnostic measurement sequence.

Stage A2 showed that the 1000-node diagnostic workload collapsed early, before
the first 30-second snapshot boundary and before a large DAG existed. This
excluded late snapshot scans and late large-DAG work as explanations for the
initial scaling collapse.

Stage A3 then produced valid per-rank CPU profiles.

The measured first-order bottleneck was severe MPI-rank work imbalance under
round-robin node-ID placement in the high-degree topology:

- one rank spent most of its CPU in useful simulator/network event processing;
- other ranks spent large fractions of CPU in MPI progress;
- receive-path/network-stack work was strongly skewed across ranks.

That evidence satisfied the optimization-admission rule for exactly one bounded
candidate.

## Gate C — accepted bounded optimization

Gate C compared historical round-robin placement with deterministic
topology-degree-aware placement under one immutable candidate image.

Canonical comparison run:

`38306442092`

Artifact:

- ID: `11774462184`
- name: `phase5-gatec-placement-profile-38306442092-1`
- digest:
  `sha256:62e20d655ea77fb61277603f3f4f4fb1bb20993839cfc731cc6c79b8e4b5fcc3`

Measured direction:

- mean flat `mca_pml_ob1_progress`: 37.95% → 17.28%;
- MPI-progress rank range: 55.8 pp → 13.2 pp;
- mean cumulative `DistributedSimulatorImpl::ProcessOneEvent`: 47.73% → 73.53%;
- event-loop rank range: 78.1 pp → 16.5 pp;
- `Ipv4EndPointDemux::Lookup` rank range: 20.4 pp → 5.6 pp.

The scientific-config identity check passed.

PR #28 merged the accepted candidate as:

`e89e959f0fd3a908bb46227df9e45f29a8918a08`

The implementation changes only execution placement when explicitly selected.
Historical round-robin remains the default.

No second Gate-C candidate was admitted.

## Gate D — canonical heavy validation

Gate D used a separately reviewed baseline transition because the historical
Phase-4 image predated the accepted Gate-C optimization.

The transition preserved the canonical heavy contract:

- exact scenario: `experiments/scenarios/heavy.json`;
- scenario SHA256:
  `a4b55a306c7be4cf04d8ee3b7722475cb9797ef9738b1f3beed31746794a988a`;
- MPI: 4;
- RNG seed/run: 1/1;
- partition: `degree-balanced`;
- simulator timeout: 23,400 s;
- harness deadline: 25,200 s;
- ns-3: 3.46.1;
- optimized build;
- metrics ON;
- diagnostics OFF;
- native optimizations OFF;
- accepted fixed VM/runner capacity;
- no oversubscription.

The immutable Gate-D image was published, verified, signed and approved through
a separate trust-anchor change before the heavy run was authorized.

### Final run

Workflow:

`Phase 5 Gate D Heavy Validation`

Run:

`38396404836`

Job:

`115292630422`

The workflow itself completed successfully. Every pre-execution gate, evidence
classification step and artifact upload step passed.

The simulator result was:

- status: `failed`;
- failure kind: `timeout`;
- exit code: `124`;
- timed out: `true`;
- simulation wall time: `23400.003728 s`;
- harness wall time: `23415.012876 s`;
- harness deadline exhausted: `false`;
- cleanup: successful.

This is the intended Gate-D timeout classification, not an infrastructure or
harness failure.

### Durable evidence

Gate-D artifact:

- ID: `11840142485`;
- name: `phase5-gated-heavy-38396404836-1`;
- size: `58,530,464 bytes` compressed;
- artifact digest:
  `sha256:1346942258fe9f342a8cbe064722044f38a436412dd2c180241842bba835e694`.

Decision manifest SHA256:

`f3c6fe77d72eb23441b0f17cf0b155faa7572cca2238c86b728e02321777ccfc`

The retained raw rank streams contain approximately 727 MB uncompressed:

| Rank | Events | `block_mined` events |
| --- | ---: | ---: |
| 0 | 1,311,344 | 146 |
| 1 | 1,311,164 | 134 |
| 2 | 1,339,422 | 207 |
| 3 | 1,337,455 | 218 |
| **Total** | **5,299,385** | **705** |

The latest observed event timestamp across the retained streams is about
`1374.004 s` simulated time. This is evidence of substantial progress and is
not claimed as the exact final simulator clock.

## Final Phase-5 decision

`HEAVY_LIMITATION_RECORDED`

The accepted degree-balanced placement is a real and measured runtime
improvement. It substantially reduces rank imbalance and MPI-progress waste.

It is **not sufficient** to make the canonical heavy upper-envelope workload
complete on the accepted fixed 4-core execution target inside the unchanged
390-minute simulator timeout.

Therefore:

- Gate D is closed;
- Phase 5 is complete;
- no second optimization candidate is admitted under Phase 5;
- the heavy workload remains unsupported on this fixed execution target under
  the current canonical runtime contract.

## What this result does not mean

This result does not establish that:

- the heavy workload is impossible on stronger hardware;
- degree-balanced placement has no value;
- the simulator cannot be further optimized in a future phase;
- timeouts should be increased until the workload completes;
- the heavy scenario, RNG identity or MPI count should be changed to obtain a
  pass.

Those are separate future decisions and require their own reviewed authority.

## Operational consequence

The stable portable-image/self-hosted-runner architecture remains valid.

The accepted 4-core KVM target remains useful for reproducible small,
representative and diagnostic work. It simply does not provide a viable
canonical heavy completion path under the current ceiling.

No campaign-scale scheduler, Kubernetes layer, checkpoint/resume mechanism or
new hardware is introduced by this closeout.

## Upstream handoff

Phase-5 closeout now moves to an explicit upstream-handoff preparation.

The handoff is documented separately in:

`docs/experiments/PHASE5_UPSTREAM_HANDOFF.md`

Upstream acceptance is not required for Phase 5 to remain complete.
