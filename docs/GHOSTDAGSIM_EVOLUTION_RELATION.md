# Relationship to GhostDagSim-Evolution

Status: **independent related project / future result-review dependency**

Related repository:

`leodbc/ghostdagsim-evolution`

This document records only the existence, motivation, authority boundary, and future review relationship.

It intentionally does **not** mirror that project's live implementation state.

## 1. Why GhostDagSim-Evolution exists

The GhostDagSim Phase-5 program produced a real, bounded optimization problem with durable evidence:

- a 1000-node performance/scaling limitation on the accepted fixed target;
- per-rank profiling that implicated severe MPI work imbalance as a major contributor;
- a human-designed degree-balanced placement that materially improved work balance;
- a final heavy result showing that this single optimization was not sufficient to make the canonical heavy workload complete under the unchanged fixed-target ceiling.

This created a useful real-world domain for a separate question:

> Can a bounded mutation-selection system propose computational-efficiency improvements to scientific simulator code while preserving experimentally relevant semantics?

GhostDagSim-Evolution exists to investigate that question independently.

The known human degree-balanced solution provides useful retrospective calibration/reference evidence. It does not turn GhostDagSim-Evolution into another Phase of the GhostDagSim project.

## 2. Authority boundary

GhostDagSim-Evolution is **not**:

- Phase 6 of `leodbc/ghostdagsim`;
- a replacement for this repository;
- an upstream authority;
- automatically authorized to modify GhostDagSim;
- automatically authorized to convert generated candidates into upstream PRs.

Its:

- roadmap;
- implementation;
- experimental gates;
- mutation campaigns;
- internal evidence;
- authorization state

belong exclusively to its own repository and orchestrator.

The GhostDagSim orchestrator must not operate that project.

Conversely, conclusions produced there do not become GhostDagSim conclusions merely because the project uses GhostDagSim as a domain.

## 3. What GhostDagSim provides

This project may serve as a stable source of:

- historical performance/scaling evidence;
- frozen baseline/reference commits explicitly selected by the independent experiment;
- known human optimization evidence;
- domain semantics and scientific caveats;
- later independent review expertise.

Any exact baseline or protocol authority used by GhostDagSim-Evolution must still be defined in that project's own canonical state.

## 4. Future return-review gate

When GhostDagSim-Evolution reaches its own declared completion state, its results should be brought back to this project for an **independent review**.

The review should involve:

1. the GhostDagSim orchestrator;
2. the externally maintained author Persona as a reviewer proxy;
3. the human owner as final decision authority.

The Persona does not have factual authority. Its role is to challenge relevance, clarity, likely author concerns, and practical usefulness.

The independent project should supply its own canonical evidence rather than relying on chat summaries.

## 5. Questions for the future review

The review should ask:

1. Did GhostDagSim-Evolution actually answer the question it was created to test?
2. Was the methodology scientifically and operationally defensible?
3. Were mutation authority, evaluator authority, and hidden evaluation kept sufficiently separated?
4. Is there evidence of contamination, benchmark overfitting, semantic shortcutting, or hardware overfitting?
5. Did any candidate produce a real end-to-end efficiency improvement rather than only a proxy/diagnostic improvement?
6. Did the improvement persist on unseen workloads under the project's preregistered decision rules?
7. Were experimentally relevant GhostDagSim semantics preserved?
8. How does the result compare with the frozen baseline?
9. How does it compare with the known human degree-balanced reference, where comparison is valid?
10. Is any discovered implementation genuinely useful to GhostDagSim?
11. Would that implementation be understandable, maintainable, and reviewable by the original author?
12. Does anything merit a new local experiment or upstream discussion?
13. Is the correct outcome simply **no action**?

## 6. Possible outcomes

The return review may conclude:

- **NO ACTION** — useful experiment, no simulator change warranted;
- **LOCAL INVESTIGATION** — evidence is interesting but requires a separate GhostDagSim-authorized validation;
- **UPSTREAM DISCUSSION CANDIDATE** — a result appears sufficiently useful and defensible to discuss with the original author;
- **REJECT RESULT** — evidence/semantics/generalization are insufficient.

No outcome automatically creates a code change or upstream PR.

Any implementation imported back into GhostDagSim requires a new explicit authorization and normal review/validation.

## 7. Why this relationship is canonized here

This relationship is recorded so that a future fresh-chat GhostDagSim orchestrator does not forget:

- why the independent Evolution project was created;
- why it remains separate;
- why its final result is expected to return here;
- why the GhostDagSim orchestrator and Persona must review that result independently before any implication is accepted.

The live state of GhostDagSim-Evolution should not be duplicated here. Reconstruct it from its own repository only when the human explicitly initiates the future review.
