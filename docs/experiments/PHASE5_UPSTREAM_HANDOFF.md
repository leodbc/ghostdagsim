# Phase 5 upstream handoff

Status: **PREPARED — separate from Phase-5 completion**

Upstream:

`lechinskie/ghostdagsim`

Fork:

`leodbc/ghostdagsim`

Phase-5 decision-point fork SHA:

`07ccfa0576d1fe5db73f308d13d3263641f9d04b`

Current upstream master observed during handoff preparation:

`1a22d006e476db720fd16cca8df0158204bcc1b8`

Common merge base:

`ba001537e3be8edc18e8e8692121da5bcb451189`

At preparation time the fork is 44 commits ahead and 1 commit behind upstream.

## Purpose

The fork contains both generally useful simulator/runtime work and a large
amount of evidence/governance/infrastructure state that exists only to support
the LEODBC experiment program.

The correct handoff is therefore **not** a fork-master-to-upstream-master pull
request.

The handoff must be a small reviewable series built fresh on current upstream
master.

## Upstream divergence that must be preserved

Upstream commit:

`1a22d006e476db720fd16cca8df0158204bcc1b8`
(`seeds and drain`)

adds, among other changes:

- `--seed` replication support;
- `--drain_seconds`;
- seed propagation into topology/node generators;
- miner drain/mining-duration behavior.

It modifies:

- `main.cc`;
- `helpers/node-topology-helper.{h,cc}`;
- `node.{h,cc}`;
- `miner.{h,cc}`;
- `README.md`.

The accepted Phase-5 degree-balanced placement also modifies
`main.cc` and `helpers/node-topology-helper.{h,cc}`.

Therefore the runtime optimization should be **ported/rebased manually onto
current upstream master**, not blindly cherry-picked and not delivered by
merging the fork.

The upstream seed/drain behavior is authoritative for the upstream branch and
must remain intact.

## Recommended upstream series

### PR A — core/runtime: topology-degree-aware MPI placement

Priority: **recommended first upstream PR**

Source evidence in the fork:

- accepted implementation commit:
  `e89e959f0fd3a908bb46227df9e45f29a8918a08`;
- Gate-C comparison run:
  `38306442092`;
- Gate-C artifact:
  `11774462184`.

Intended upstream files:

- `helpers/node-topology-helper.h`;
- `helpers/node-topology-helper.cc`;
- `main.cc`;
- `tests/ghostdagtest.cc`.

Required upstream behavior:

- preserve upstream `--seed` and `--drain_seconds` semantics;
- keep round-robin as the default;
- expose `--mpi_partition=degree-balanced` only as an explicit opt-in;
- build placement only after topology construction;
- change only SystemId assignment;
- preserve node IDs, miners, topology, links, regions, latency, bandwidth,
  protocol behavior and RNG identity;
- preserve deterministic tie-breaking and rank-capacity constraints;
- retain tests for determinism and exact MPI4/D1000 rank capacity.

Evidence worth including in the upstream PR description:

- mean MPI-progress attribution fell from 37.95% to 17.28%;
- MPI-progress rank range fell from 55.8 pp to 13.2 pp;
- mean useful event-loop attribution rose from 47.73% to 73.53%;
- event-loop rank range fell from 78.1 pp to 16.5 pp.

Gate D should also be disclosed honestly: the optimization materially improves
balance but does not make the fixed 4-core canonical heavy run complete inside
23,400 seconds.

### PR B — optional diagnostic instrumentation

Priority: **optional; only if upstream wants a built-in profiling surface**

Primary fork source:

`2dfc876ff827358f926a7810e84cdf8b4e6c4d9b`

Candidate pieces:

- `diagnostics.h`;
- compile-time diagnostics switch in `CMakeLists.txt`;
- bounded counters in `dag.cc`, `node.cc`, `metrics.h` and `main.cc`;
- diagnostics-disabled behavior remaining the default.

This should be rebased independently onto current upstream.

Do not make upstream depend on LEODBC workflows or runner state merely to obtain
the instrumentation.

### PR C — optional experiment/reproducibility tooling

Priority: **optional and likely split further**

Potential reusable pieces:

- portable Docker build pattern;
- generic scenario identity files;
- `scripts/run-experiment.py`;
- `scripts/run-diagnostic.py`;
- `scripts/run-cpu-profile.py`;
- `scripts/profile-rank.sh`;
- generic evidence-manifest concepts.

Before upstreaming, remove or parameterize fork-specific assumptions such as:

- `ghcr.io/leodbc/ghostdagsim`;
- LEODBC issue/run IDs;
- accepted local runner identities;
- local trust-anchor state;
- devserver/VM assumptions.

This tooling should not be bundled into PR A.

## State that remains local to the fork

The following are evidence/governance or infrastructure state, not upstream
simulator features:

- `leodbc/infra-context#38`;
- Project Request
  `prq_6ee8c5ec-90c0-4b77-b07f-3f5d4e74d466`;
- physical `devserver` details;
- VM `ghostdagsim-phase4` identity and UUID;
- runner registration/ephemeral-listener state;
- `experiments/runner-approval.json`;
- `experiments/canonical-image.json`;
- `experiments/phase5-gated-image.json`;
- Phase-4/Phase-5 authorization and evidence workflows tied to LEODBC
  governance;
- host-load attestations;
- artifact IDs and local benchmark classification records;
- Phase-3/4/5 decision documents as governance authority.

These can be cited as supporting evidence in an upstream PR, but should not be
made prerequisites for upstream operation.

## Delivery rules

1. Start each upstream candidate from **fresh current upstream master**.
2. Revalidate upstream master immediately before implementation.
3. Never merge the entire LEODBC fork into upstream.
4. Do not force upstream to adopt LEODBC infrastructure/governance.
5. Keep each PR reviewable and independently useful.
6. Run upstream's own tests in addition to any imported focused tests.
7. For PR A, explicitly test both:
   - default round-robin behavior;
   - opt-in degree-balanced behavior.
8. Verify `--seed=0` compatibility and nonzero seed behavior after the
   placement port.
9. Re-check constructor/API conflicts caused by the upstream seed change.
10. Upstream acceptance is independent of Phase-5 completion.

## Recommended next action

The first upstream action, if/when approved, is to create a fresh branch from
upstream master `1a22d006e476db720fd16cca8df0158204bcc1b8` (or whatever
upstream master has become at execution time) and port **only PR A**.

Do not start PR B or PR C until PR A has an independent review outcome.
