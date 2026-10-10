# Phase 5 — fixed-infrastructure heavy-workload profiling plan

Status: **GATE B — Stage A3 rerun pending after symbolization-path repair**

Issue: #18

Baseline:

`a68a39a3d9e5e5ed34c3f7163ae36b78b1745449`

Canonical source:

`ba001537e3be8edc18e8e8692121da5bcb451189`

Approved Phase-4 image:

`ghcr.io/leodbc/ghostdagsim@sha256:89e37f6f28348c189df41d611fbf4fd7041fdb7af711edb77201eec13264e366`

Approved benchmark runner:

`ghostdagsim-phase4-kvm`

## Purpose

Phase 4 established that the portable-image and stable-runner model is correct,
but the canonical heavy workload does not finish inside the 390-minute runtime
contract at MPI1, MPI2, or MPI4.

Phase 5 treats physical execution capacity as fixed.

The project must therefore identify the dominant software/runtime costs and
evaluate bounded optimizations without silently changing the scientific workload
or success criteria.

## Ownership boundary

GhostDagSim owns:

- source-code analysis;
- diagnostic instrumentation;
- profiling design;
- simulator/runtime optimizations;
- correctness tests;
- benchmark evidence and scientific interpretation.

`leodbc/infra-context` owns any requested mutation of:

- the physical devserver;
- hypervisor/KVM configuration;
- VM resource allocation;
- CPU affinity/pinning/governor;
- host storage/packages;
- runner placement or other infrastructure-owned state.

This Phase does not currently request an infrastructure change.

## Canonical versus diagnostic execution

### Canonical benchmark

Canonical runs are the only runs used to change the project's runtime
classification.

They retain the applicable scenario, RNG, image/evidence and benchmark-contract
identity unless a separately reviewed protocol change creates a new baseline.

### Diagnostic run

Diagnostic runs exist only to explain cost.

They may:

- use a diagnostic-only build/image;
- add sampling or counters;
- reduce blocks or simulated duration;
- run only a subset of MPI modes;
- emit additional profiling artifacts.

They must be labeled diagnostic and must never replace canonical benchmark
evidence.

## Static characterization

These observations come from the Phase-4 canonical source and scenario files.
They are hypotheses about runtime importance until profiling measures them.

### 1. Heavy differs from representative primarily by node count

Representative:

- nodes: 100;
- miners: 10;
- blocks per miner: 1000;
- lambda: 20 s;
- tx generation interval: 0.5 s;
- snapshots: every 30 s.

Heavy:

- nodes: 1000;
- miners: 10;
- blocks per miner: 1000;
- lambda: 20 s;
- tx generation interval: 0.5 s;
- snapshots: every 30 s.

The nominal simulated duration is therefore identical:

`1000 blocks/miner * 20 s / 60 = 333.33 minutes`.

The heavy workload is not "more blocks"; it is principally much more per-node
work and network/event fanout over the same simulated time.

### 2. Transaction-generation event pressure scales with non-miner nodes

Only non-miners generate transactions.

With `tx_load=0`, the configured 0.5-second mean generation interval remains
fixed as node count grows.

Expected generator rates are therefore approximately:

- representative: 90 non-miners × 2 events/s = 180 generator events/s;
- heavy: 990 non-miners × 2 events/s = 1980 generator events/s.

Across about 20,000 seconds of simulated time, the order-of-magnitude generator
event counts are:

- representative: ~3.6 million;
- heavy: ~39.6 million.

`GenerateTransaction()` schedules the next generation event even when the
local mempool is full, so mempool saturation does not stop this scheduler load.

This estimate counts generator callbacks only; transaction announcement,
request, response, timeout and TCP/ns-3 events are additional.

### 3. Snapshot work scales with nodes and local DAG size

Every node schedules a DAG snapshot every 30 simulated seconds.

Over about 20,000 simulated seconds this is roughly 666 snapshot callbacks per
node:

- representative: ~66,600 snapshot callbacks;
- heavy: ~666,000 snapshot callbacks.

Each snapshot scans the node's current `m_blockchain.blocks` to count blue
blocks before serializing a metric event.

If nodes eventually know approximately the full 10,000-block DAG, the aggregate
block-iteration cost of snapshots can be large. Exact cost must be measured.

### 4. AddBlock contains a full accepted-block recoloring scan

After adding a block, `Blockchain::AddBlock()`:

1. computes/updates past and blue-set state;
2. selects the current tip;
3. iterates over every accepted block to refresh `is_blue`.

The full scan occurs for each accepted block at each node.

With a DAG approaching 10,000 blocks, this produces a structurally quadratic
component in block count per node before multiplying by the number of simulated
nodes.

This is a high-priority profiling hypothesis, not yet an optimization approval.

### 5. GHOSTDAG itself contains variable set/topological work

`GreedyBlueSet()` performs:

- bit-set difference;
- topological sorting of the merge set;
- blue-anticone checks against past sets.

The implementation already uses dense bitsets for ancestor and blue sets, but
the actual hot-path contribution is unknown.

### 6. Heavy enables the intended high-degree miner topology

Topology construction declares miner connection targets of 700–800 peers.

At 1000 nodes this range can be materially realized, unlike the 100-node
representative scenario.

Block inventory propagation iterates over peer addresses, so high miner degree
can increase:

- TCP/socket state;
- ns-3 packet events;
- cross-rank MPI event traffic;
- inventory propagation fanout.

The actual realized edge count and rank-crossing distribution must be captured
in diagnostics rather than inferred.

### 7. Metrics are enabled in the approved portable build

The Phase-4 portable image is compiled with:

`GHOSTDAGSIM_METRICS=ON`.

The event logger:

- builds `nlohmann::json` objects;
- serializes them with `dump()`;
- appends JSONL output;
- flushes its application buffer at 8 KiB.

Block receipt/coloring/snapshot and related events can therefore contribute CPU
and I/O cost at scale.

Metrics cannot simply be disabled for a canonical result because that would
change the evidence surface. Diagnostic comparison may measure their cost.

## Gate A conclusions

The static source supports four primary profiling buckets:

1. **per-node transaction/event scheduling**;
2. **blockchain/GHOSTDAG processing**, especially `AddBlock()`;
3. **network/MPI fanout and rank imbalance**;
4. **metrics/output serialization and snapshot scanning**.

No one bucket is declared the dominant bottleneck yet.

## Diagnostic profiling strategy

The first profiling iteration must avoid infrastructure mutation and avoid a
full heavy canonical rerun.

### Stage A1 — structural counters

Introduce diagnostic-only counters with low expected overhead for:

- `GenerateTransaction()` callbacks;
- successful locally generated transactions;
- snapshot callbacks;
- total block entries scanned by snapshots;
- `AddBlock()` calls;
- total block entries scanned by the `is_blue` refresh loop;
- GHOSTDAG merge-set candidate count;
- block INV fanout count;
- transaction INV fanout count;
- message/frame enqueue count and modeled bytes;
- local node count per MPI rank;
- cross-rank topology-link count if it can be observed without changing ns-3
  semantics.

Counters must be gated behind an explicit diagnostic build/flag and must not
alter canonical behavior when disabled.

### Stage A2 — short scale-preserving diagnostics

Use diagnostic scenarios that preserve the node-scale distinction but shorten
the block horizon enough to complete cheaply.

At minimum compare:

- 100 nodes / same core runtime parameters / reduced blocks;
- 1000 nodes / same core runtime parameters / reduced blocks.

These runs are diagnostic identities, not modified canonical scenarios.

The goal is to measure scaling ratios for the counters above before any
optimization.

### Stage A3 — low-overhead CPU sampling

After counters identify the likely expensive regions, add a diagnostic-only CPU
sampling profiler that does not require host privilege or host mutation.

Preferred first design:

- userspace sampling inside a diagnostic container;
- per-MPI-rank profile artifacts;
- symbolized function-level output;
- optimized build kept as close as practical to canonical;
- profiling packages/tools contained in the diagnostic image only.

Do not assume `perf` availability or request host kernel changes merely for
profiling. A host-dependent profiler may be reconsidered only if the
userspace path proves insufficient, in which case the requirement is handed to
`infra-context`.

## Optimization admission rule

An optimization branch is admitted only when Gate-B profiling identifies a
specific measured cost and the proposed change has a mechanism that addresses
that cost.

For each candidate record:

- bottleneck evidence;
- correctness invariant;
- expected complexity/mechanism improvement;
- cheap-run before/after measurement;
- whether canonical output semantics are unchanged.

Do not combine multiple independent optimizations in the first measurement.

## High-value hypotheses to test first

Priority order for measurement, not implementation:

1. full `is_blue` refresh in `Blockchain::AddBlock()`;
2. transaction-generation scheduler load after mempool saturation;
3. snapshot full-DAG scans;
4. block/network fanout caused by high-degree miners;
5. JSON metrics serialization/output;
6. GHOSTDAG merge-set/topological/anticone work;
7. MPI imbalance/communication overhead.

## Gate-B entry criteria

Gate B may begin after review confirms:

- diagnostic identities cannot be mistaken for canonical evidence;
- counters are bounded and removable/disabled by default;
- diagnostic runs do not require infrastructure mutation;
- expected artifacts are defined;
- no optimization has been preselected merely from static inspection.

## Gate B execution lane — D100 / D1000

The first real Gate-B measurements use a repository-local diagnostic execution
lane that is deliberately incompatible with canonical Phase-4 benchmark
evidence. Stage A2 now has measured D100 and D1000 evidence; the results below
remain diagnostic-only and do not change Phase-4 runtime classification.

Execution identities:

- `diagnostic-d100`: 100 nodes, 10 miners, `blocks_per_miner=20`;
- `diagnostic-d1000`: 1000 nodes, 10 miners, `blocks_per_miner=20`.

Both preserve the applicable representative/heavy simulator parameters other
than the explicitly reduced block horizon. RNG identity is harness-owned and
fixed to `RngSeed=1`, `RngRun=1`. Both execute at MPI4 only.

The diagnostic image is built once from `experiments/portable.Dockerfile` with:

- ns-3 `3.46.1`;
- optimized build profile;
- `GHOSTDAGSIM_METRICS=ON`;
- `GHOSTDAGSIM_DIAGNOSTICS=ON`;
- `NS3_NATIVE_OPTIMIZATIONS=OFF`;
- the existing MPI buffer repair.

The image is not published. The workflow records and reuses the exact local
Docker image ID for both cells and verifies that its OCI revision equals the
explicitly authorized source SHA.

Operational limits are diagnostic guardrails, not Phase-4 runtime thresholds:

| Cell | Simulation timeout | Harness deadline |
| --- | ---: | ---: |
| D100 | 1200 s | 1800 s |
| D1000 | 3600 s | 4500 s |

The workflow has an explicit, fail-closed authorization scope.

- `D100_ONLY` requires confirmation `RUN_PHASE5_GATEB_D100` and may execute
  only D100. A successful D100 records D1000 as `not_authorized` and exits.
- `D100_THEN_D1000` requires the distinct confirmation
  `RUN_PHASE5_GATEB_D100_THEN_D1000`. It is a later, separate authorization:
  D100 is rerun under the newly built immutable local image, and D1000 may start
  only if that D100 completes with exit code zero and
  `output_integrity=complete`.

There is no automatic retry or timeout increase. A `D100_ONLY` dispatch can
never authorize D1000 implicitly.

Each completed cell preserves its diagnostic scenario definition, manifest,
run log, timing, `config.json`, and exactly four rank directories containing
`events.jsonl` and bounded `diagnostics.json`. The workflow additionally
preserves execution context, runner evidence, image inspection, build
provenance, build log and cell exit codes.

Diagnostic artifacts are never input to `scripts/summarize-experiment.py`,
Phase-4 summaries, `experiments/phase4-gatec-complete.json`, or
`docs/experiments/PHASE4_DECISION.md`. They cannot change canonical runtime
classification.

The approved Phase-4 runner `ghostdagsim-phase4-kvm` is reused without host,
VM, hypervisor, CPU, memory, storage, package, pinning or governor changes.
Current infrastructure decision: `NO_INFRA_CHANGE_REQUIRED`.

## Gate B Stage A2 measured result

Two independent D100 executions completed with output integrity and reproduced
the structural counters exactly. The confirmation D100 took about 326.5 seconds
wall time for roughly 400 seconds of simulated time.

The D1000 cell used the same immutable local image, MPI4 and RNG 1/1 but hit the
explicit 3600-second diagnostic timeout after advancing only to about 27.47
seconds of simulated time. It was not OOM-killed and cleanup succeeded.

At the same simulated-time cutoff, both D100 and D1000 had mined exactly 14
unique blocks. Relative to D100, D1000 produced approximately:

- 8.99x total logged events;
- 9.10x received-message events;
- 9.42x sent-message events;
- 8.75x block-received events;
- 7.86x block-colored events;
- 252x block-orphaned events;
- 155x block-unorphaned events.

D1000 never reached the first 30-second snapshot boundary and had only 14 mined
blocks when it timed out. Snapshot scanning and late large-DAG GHOSTDAG costs
therefore cannot explain the initial 1000-node collapse, although they can still
matter later.

The evidence prioritizes the early transaction/network/event path, including
transaction scheduling and propagation, CBOR/frame processing, ns-3 event and
network-stack work, and propagation-order orphan consequences. Counters do not
yet isolate one function-level CPU cost, so the optimization admission rule is
not satisfied.

## Gate B Stage A3 userspace CPU sampling lane

Stage A3 uses gperftools entirely inside a diagnostic container. It requires no
host kernel profiler, privilege, package or infrastructure mutation.

The profiling image is parameterized by
`GHOSTDAGSIM_CPU_PROFILER=ON`; the default remains `OFF`. When profiling is
enabled, each MPI rank loads `libprofiler.so.0` and exposes a signal-controlled
profile session. The normal simulator entrypoint remains unchanged when the
profiling flag is absent.

The first Stage A3 identity is intentionally narrow:

- scenario: `diagnostic-d1000`;
- MPI4;
- RNG seed/run 1/1;
- optimized build, metrics ON, diagnostics ON, native optimizations OFF;
- 300 seconds wall-clock warmup;
- 600 seconds wall-clock CPU sampling;
- 100 Hz gperftools sampling;
- SIGUSR2 (signal 12) start/stop control;
- 1200-second harness deadline;
- simulation completion is explicitly not expected.

After the stop signal, the harness requires one non-empty raw gperftools profile
per rank before terminating the simulator container. It then symbolizes every
rank using `google-pprof --text` from the same immutable local image and
preserves raw profiles, symbolized text, partial events, config and a profile
manifest.

This lane is diagnostic-only. A profile run is not evidence that D1000 completed
and cannot change canonical benchmark classification.


## Stage A3 first execution and symbolization repair

The first Stage A3 run was executed as workflow run `37930486240` on canonical
SHA `9ba6078e6b8555a43f605292e48ee74be723d512`.

That run completed the intended 300-second warmup and 600-second CPU sampling
window and produced one non-empty raw gperftools profile for each MPI rank.
Infrastructure, Docker, MPI4 and profiler capture all functioned as intended.

The run failed only after sampling, while the host attempted to create
`pprof.txt` inside per-rank directories created by the root-running diagnostic
container. The exact failure was a permission error on
`cpu-profile/rank0/pprof.txt`.

PR #26 repaired that harness-only artifact-path defect by:

- preserving raw profiles under the container-owned `cpu-profile/rankN/` tree;
- writing symbolized output to runner-owned `symbolized/rankN/pprof.txt`;
- retaining fail-closed exact MPI4 rank validation;
- replacing the hosted-CI signal-flush smoke with a deterministic symbolization
  regression that reproduces the root-owned raw-profile boundary.

PR #26 merged as:

`1eec9d5181f49fe89c17b695753fbf3105c0cad2`

Post-merge validation on that SHA:

- Build run `37959976171`: SUCCESS;
- Test run `37959976139`: SUCCESS;
- diagnostics OFF: SUCCESS;
- diagnostics ON: SUCCESS;
- Stage A3 deterministic CPU profile symbolization smoke: SUCCESS.

## Post-Phase-5 upstream handoff

After Gate D and the final Phase-5 heavy-viability decision are complete, the
project will perform an explicit upstream-handoff preparation before beginning
campaign-scale orchestration.

The handoff does not mean pushing this fork's entire operational history or
infrastructure-specific state to upstream.

The closeout must classify Phase-0-through-5 changes into:

1. **upstreamable simulator/runtime improvements**, such as correctness fixes,
   measured performance optimizations, portable build fixes, MPI robustness,
   reusable diagnostics and generally useful tests;
2. **optionally upstreamable experiment tooling**, such as benchmark harnesses,
   profiling helpers, reproducibility metadata and generic workflow support;
3. **fork-specific operational state that must remain local**, including
   `devserver`, the Phase-4 VM, runner registrations, infra-context request
   identifiers, host attestations and environment-specific governance.

The preferred delivery form is a small reviewable series of upstream PRs rather
than one monolithic fork-to-upstream merge.

This handoff is a Phase-5 closeout activity. It does not alter the profiling,
optimization-admission or canonical-validation gates and it does not imply that
upstream acceptance is required for Phase 5 to be complete.

## Current stop point

No simulator optimization is authorized yet.

The canonical repository state for continuing Phase 5 is:

`1eec9d5181f49fe89c17b695753fbf3105c0cad2`

The next project action is exactly one rerun of the Stage A3 D1000 userspace CPU
profile on that canonical SHA, after a fresh reuse of infra-context#38 confirms:

- physical host idle/low;
- approved VM healthy;
- a fresh ephemeral runner under `gh-ghostdagsim`;
- Docker and native MPI4 passing under that same Unix context;
- no competing GhostDagSim workflow.

Only the resulting symbolized per-rank function-level evidence can admit the
first Gate-C optimization candidate.

The candidate must still document the measured bottleneck, correctness
invariant, mechanism/complexity improvement, cheap before/after measurement and
unchanged canonical output semantics.

After Gate C, Gate D performs the minimum canonical validation needed to decide
whether heavy is viable on the fixed infrastructure. Phase 5 then closes with a
durable heavy-viability/limitation decision and the upstream-handoff preparation
described above.
