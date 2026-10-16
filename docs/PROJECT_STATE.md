# GhostDagSim project state

Status: **Phase 0–5 complete / upstream handoff pending external maintainer action**

This file is the global project-state checkpoint above individual phase documents.

The exact current `master` HEAD must always be re-observed from GitHub during fresh-chat recovery.

Checkpoint base at creation:

`65dd5ef5b9b3e4b4e3307623cbb36fc7a9a582b4`

## 1. Completed project arc

Phases 0 through 5 are complete.

The project established:

- canonical workloads and benchmark protocol;
- reproducible execution/evidence handling;
- diagnosis of hosted-runner portability and slot limitations;
- a portable execution image;
- a fixed accepted 4-CPU KVM execution target;
- small / representative / heavy execution evidence;
- a bounded profiling sequence for the 1000-node degradation;
- one evidence-backed MPI-placement optimization;
- final heavy validation under the unchanged runtime contract.

The authoritative Phase-5 conclusion remains:

`HEAVY_LIMITATION_RECORDED`

See:

- `docs/experiments/PHASE5_DECISION.md`
- `docs/experiments/PHASE5_CHECKPOINT.md`

## 2. Accepted Phase-5 optimization

Accepted simulator source:

`e89e959f0fd3a908bb46227df9e45f29a8918a08`

Accepted opt-in placement mode:

`--mpi_partition=degree-balanced`

The measured conclusion is deliberately narrow:

> topology-degree-aware placement produced a material MPI work-balance improvement under the controlled Gate-C comparison.

It must not be generalized into a proven end-to-end wall-clock speedup.

Key profiling evidence:

- mean flat `mca_pml_ob1_progress`: 37.95% → 17.28%;
- MPI-progress rank range: 55.8 pp → 13.2 pp;
- mean cumulative `DistributedSimulatorImpl::ProcessOneEvent`: 47.73% → 73.53%;
- event-loop rank range: 78.1 pp → 16.5 pp;
- `Ipv4EndPointDemux::Lookup` rank range: 20.4 pp → 5.6 pp.

Round-robin placement is treated as a major contributor implicated by profiling, not as the sole proven cause of the heavy limitation.

## 3. Final heavy result

The canonical heavy validation kept the accepted fixed runtime contract:

- 1000 nodes;
- 10 miners;
- 1000 blocks/miner;
- MPI4;
- RNG 1/1;
- degree-balanced placement;
- fixed accepted 4-CPU target;
- simulator timeout 23,400 s;
- no oversubscription.

Result:

`HEAVY_LIMITATION_RECORDED`

The simulator timed out at approximately 23,400 s.

The retained output demonstrated substantial progress, but the degree-balanced optimization alone was insufficient to make the canonical heavy workload finish on that fixed target within the unchanged ceiling.

This does **not** establish that GhostDagSim cannot scale to 1000 nodes or that stronger hardware/future optimization cannot improve the result.

## 4. Author-facing package

Issue #34 — `Author presentation package: curate Phase 0–5 findings for review` — is complete and closed.

The package reconciled the Phase 0–5 evidence into an author-facing narrative and technical appendix without treating LEODBC governance/infra as the main result.

The original author subsequently reviewed the material and explicitly requested an upstream pull request containing the degree-balanced MPI placement improvement.

That later request is a separate upstream-handoff task, not part of the original presentation-package scope.

## 5. Upstream handoff

The prepared upstream contribution is intentionally narrow.

Fork branch:

`upstream/degree-balanced-mpi`

Exact candidate head:

`53a014525d8efe4d8d31cef1d4edf45f8b27458c`

Base observed for the upstream PR:

`lechinskie/ghostdagsim@1a22d006e476db720fd16cca8df0158204bcc1b8`

Exact candidate files:

- `helpers/node-topology-helper.cc`
- `helpers/node-topology-helper.h`
- `main.cc`
- `tests/ghostdagtest.cc`

The port preserves upstream `--seed` and `--drain_seconds` behavior and excludes LEODBC governance, infrastructure, benchmark harness, and Phase-5 state.

Fork exact-head CI:

- `Test` run `38511515291`: **SUCCESS**

Upstream pull request:

- repository: `lechinskie/ghostdagsim`
- PR: #1 — `perf: add degree-balanced MPI node placement`
- observed state at checkpoint creation: **OPEN / DRAFT / mergeable**
- observed head: `53a014525d8efe4d8d31cef1d4edf45f8b27458c`

Observed upstream workflow state at checkpoint creation:

- Test `38512118016`: `action_required`
- Build `38512118014`: `action_required`

Those workflows started no jobs. This is an external maintainer approval gate, not a code/test failure.

The live PR state must be re-observed before any future action.

Current fork tracker:

Issue #35 — `Upstream degree-balanced MPI PR #1 — maintainer review`

## 6. Current authorization

`NEXT_CANDIDATE_ACTION = AUDIT_UPSTREAM_PR1_AFTER_MAINTAINER_ACTIONS`

`AUTHORIZED_WORK_ITEM = NONE`

The current dependency is external: the upstream maintainer must approve/run the pending Actions.

After that external change, the candidate next action is only to:

1. re-observe PR state/head/base;
2. audit Build/Test;
3. verify the tested SHA;
4. report the result to the human.

Do not automatically take the PR out of draft or merge it.

## 7. Explicitly not authorized

- Phase 6;
- a second Phase-5 optimization candidate;
- a new canonical heavy run;
- longer heavy timeout;
- stronger hardware as a Phase-5 continuation;
- PR B diagnostic instrumentation;
- PR C experiment/reproducibility tooling;
- automatic upstream merge/draft transition.

## 8. Related independent project

`leodbc/ghostdagsim-evolution` exists as an **independent experiment** motivated by the real performance/scaling evidence produced by this GhostDagSim project.

Its internal roadmap, implementation state, gates, and authority belong exclusively to its own repository/orchestrator.

It is **not Phase 6** of this project and has no automatic authority to modify this fork or upstream.

When that independent project reaches its own completion state, its results are expected to return here for an independent review before any implication is adopted by GhostDagSim.

See:

`docs/GHOSTDAGSIM_EVOLUTION_RELATION.md`
