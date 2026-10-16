# AGENTS.md — GhostDagSim orchestration contract

This repository is the canonical project for `leodbc/ghostdagsim`.

## 1. Orchestrator scope

The orchestrator for this repository is exclusive to `leodbc/ghostdagsim`.

Do not assume orchestration authority over:

- `lechinskie/ghostdagsim` (upstream);
- `leodbc/ghostdagsim-evolution`;
- `leodbc/infra-context`;
- any other repository referenced by this project.

Those repositories may be observed only when necessary to understand an explicitly referenced dependency or handoff.

In particular, `ghostdagsim-evolution` has its own independent orchestrator and canonical state. This repository records only why that project exists, its relationship to GhostDagSim, and the future return-review gate.

## 2. Stateless fresh-chat recovery

Assume zero trustworthy chat history.

Before planning or changing anything:

1. observe the repository default branch and exact `master` HEAD;
2. read, in order:
   - `AGENTS.md`
   - `docs/PROJECT_STATE.md`
   - `docs/HANDOFF.md`
   - `docs/experiments/PHASE5_DECISION.md`
   - `docs/experiments/PHASE5_CHECKPOINT.md`
   - `docs/experiments/PHASE5_UPSTREAM_HANDOFF.md`
   - `docs/GHOSTDAGSIM_EVOLUTION_RELATION.md`
3. enumerate open issues and pull requests in this fork;
4. inspect current checks/status for any active work item;
5. if the handoff references an external upstream PR, re-observe that PR and its checks;
6. reconstruct:
   - canonical integrated state;
   - completed work;
   - pending/external dependencies;
   - blocked work;
   - next candidate action;
   - currently authorized work.

Do not ask the human to repeat information that is recoverable from GitHub.

## 3. Source-of-truth precedence

Use this order:

1. phase decision documents for completed scientific/engineering conclusions;
2. code and tests on canonical `master`;
3. `docs/PROJECT_STATE.md`;
4. `docs/HANDOFF.md`;
5. open issue/PR discussion for pending work;
6. old chat transcripts, memory, or copied summaries.

An open branch or pull request is work-in-progress evidence, not canonical integrated state.

Live external state must be re-observed rather than inferred from old issue comments.

## 4. Authorization semantics

A next logical action is not authorization.

If `docs/PROJECT_STATE.md` or `docs/HANDOFF.md` says:

`AUTHORIZED_WORK_ITEM = NONE`

then the orchestrator may inspect, reconstruct, and report state, but must not begin implementation or a new experimental phase without explicit human approval.

Never infer authorization from:

- a roadmap;
- an old handoff;
- an open issue;
- a pending upstream PR;
- successful CI;
- prior-chat memory.

## 5. Current hard boundaries

Unless a later explicit human authorization changes them, do not:

- start Phase 6;
- admit a second Phase-5 optimization candidate;
- run a new canonical heavy benchmark;
- increase the heavy timeout to obtain a pass;
- change the canonical heavy workload identity;
- provision stronger hardware as a continuation of Phase 5;
- start upstream PR B/C from the prepared handoff;
- merge or undraft an upstream PR automatically;
- modify `ghostdagsim-evolution` or act as its orchestrator.

## 6. Git/PR discipline

For substantial repository changes:

- use a dedicated branch;
- validate before requesting integration;
- keep one coherent PR per atomic work item;
- never treat branch contents as integrated truth before merge;
- do not self-merge without explicit human approval;
- re-observe `master` after integration.

## 7. Checkpoint discipline

After any substantial state transition:

1. update `docs/PROJECT_STATE.md` with durable cumulative truth;
2. replace `docs/HANDOFF.md` with the current concise operational handoff;
3. update or close the relevant issue tracker;
4. preserve exact evidence references when materially useful;
5. avoid duplicating volatile live state that is safer to re-observe from GitHub.
