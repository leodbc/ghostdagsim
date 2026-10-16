# GhostDagSim handoff

## Recovery rule

Do not trust this file alone.

A fresh orchestrator must first follow `AGENTS.md`, re-observe canonical `master`, open issues/PRs, and any externally referenced upstream PR/checks.

## Completed

- Phases 0–5: complete.
- Final Phase-5 decision: `HEAVY_LIMITATION_RECORDED`.
- Degree-balanced placement: accepted as a material MPI work-balance improvement.
- Author-facing Phase 0–5 package: complete.
- Original author: explicitly requested the narrow upstream degree-balanced PR.
- Clean upstream port: prepared.
- Fork exact-head Test: SUCCESS.
- Upstream PR #1: created.

## Current external dependency

Tracker:

Issue #35 — `Upstream degree-balanced MPI PR #1 — maintainer review`

At checkpoint creation, upstream PR #1 was:

- OPEN;
- DRAFT;
- mergeable;
- head `53a014525d8efe4d8d31cef1d4edf45f8b27458c`.

Its upstream workflows were:

- Test `38512118016`: `action_required`;
- Build `38512118014`: `action_required`.

Re-observe all of this before acting.

## Authorization

`NEXT_CANDIDATE_ACTION = AUDIT_UPSTREAM_PR1_AFTER_MAINTAINER_ACTIONS`

`AUTHORIZED_WORK_ITEM = NONE`

Therefore the orchestrator currently waits.

If the maintainer approves/runs Actions, the next candidate work is to audit the resulting checks and report them to the human.

That does not authorize:

- undrafting;
- merging;
- code changes;
- Phase 6;
- a second optimization;
- a new heavy run;
- PR B/C.

## Independent GhostDagSim-Evolution project

`leodbc/ghostdagsim-evolution` is intentionally separate and has its own orchestrator.

Do not track or manage its live internal state here.

When it is completed, its results return to this GhostDagSim project for independent review by the GhostDagSim orchestrator and the externally maintained Persona before any potential simulator/upstream implication is accepted.

See `docs/GHOSTDAGSIM_EVOLUTION_RELATION.md`.
