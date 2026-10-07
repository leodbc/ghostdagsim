# Phase 4 — portable image and pinned self-hosted recalibration

Status: **COMPLETE — Gate A/B/C complete; Gate D reviewed; Phase 4 stopped**

Issue: #9

Phase 4 baseline:

`4d67fb14a539deb7e8f2749d017f497f6bdd90e1`

Canonical simulator source:

`ba001537e3be8edc18e8e8692121da5bcb451189`

ns-3:

`3.46.1`

Historical Phase 2 image:

`ghcr.io/leodbc/ghostdagsim@sha256:13480d2ddc80ac63e46651f6b25b50abef33ae93cdd5ca527ca84d1d205878b0`

## Gate A completion evidence

Gate A completed successfully with workflow run:

`37134911979`

Run head:

`9032f5d140bdbb003e22071e6b916d7cb63f18e4`

Approved portable image:

`ghcr.io/leodbc/ghostdagsim@sha256:89e37f6f28348c189df41d611fbf4fd7041fdb7af711edb77201eec13264e366`

Verified by that run:

- exact canonical simulator source `ba001537e3be8edc18e8e8692121da5bcb451189`;
- ns-3 `3.46.1`;
- `NS3_NATIVE_OPTIMIZATIONS=OFF`;
- linux/amd64 build with provenance and SBOM;
- OCI revision/source labels match the canonical simulator SHA;
- runtime linkage reports ns-3 `3.46.1`;
- decoded static disassembly contains no `zmmN` or `k0..k7` AVX-512 register use in shipped ghostdagsim/ns-3 ELF objects;
- direct small/MPI2 smoke completed successfully on a generic GitHub-hosted runner;
- cosign keyless signing completed successfully, with transparency-log entry created.

The historical Phase 2 image remains recorded in the Phase 3 decision record and is not mutated or retagged as experiment identity.

The repository trust anchor is advanced by the Gate-A evidence update to the immutable portable digest above.

## Why Phase 4 exists

Phase 3 established two independent execution-target problems:

1. the Phase 2 benchmark image was built with native CPU optimizations and
   contains AVX-512 instructions, while the generic GitHub-hosted pool does not
   guarantee AVX-512 exposure;
2. representative/heavy workloads do not have a robust execution envelope on
   the generic hosted runner.

The Phase 3 decision therefore keeps GitHub Actions as the control plane but
moves representative/heavy execution to a pinned self-hosted Linux runner.

## Phase 4 sequence

Phase 4 is deliberately sequential. A later gate must not be started merely
because the repository contains its design.

### Gate A — portable benchmark image

The first repository PR adds:

- this plan;
- `experiments/portable.Dockerfile`;
- `.github/workflows/phase4-publish-portable.yml`.

The publish workflow is manual only.

It checks out the control-plane repository separately from the simulator source.
The Docker build context is an exact checkout of
`ba001537e3be8edc18e8e8692121da5bcb451189`, so documentation/workflow changes
on later `master` commits cannot silently enter the simulator image.

The portable recipe keeps the optimized/release profile but explicitly forces
`NS3_NATIVE_OPTIMIZATIONS=OFF` after ns-3 profile configuration. This removes
`-march=native` / `-mtune=native` as an image-build-machine dependency.

A publish run is acceptable only if all of the following are true:

- exact canonical source checkout is verified;
- image is built for `linux/amd64`;
- provenance and SBOM are emitted;
- immutable digest is captured;
- cosign signing succeeds;
- OCI revision equals the canonical simulator SHA;
- runtime linkage identifies ns-3 `3.46.1`;
- static inspection finds no ZMM/opmask AVX-512 dependency in shipped ns-3
  libraries;
- direct small/MPI2 smoke succeeds on a generic hosted runner.

The existing `experiments/canonical-image.json` is **not** changed by the
bootstrap PR. It remains pointed at the historical Phase 2 image until a real
portable publish run has passed every Gate-A check.

After a successful publish, a separate evidence update must advance the
canonical image trust anchor to the new digest. That update must preserve the
historical Phase 2 digest in the Phase 3 decision record.

### Gate B — pinned runner acceptance

Gate B starts only after Gate A has an approved portable image.

The external host/VM must be provisioned or identified before repository
acceptance can complete. Phase 4 does not invent a cloud provider or host.

The runner must have a dedicated label and a stable identity. Acceptance must
record CPU/ISA, topology, memory, disk, OS/kernel, Docker, Open MPI, and the
GitHub runner name.

Native `mpirun -np 4` must succeed without `--oversubscribe`.

The calibration workflow must fail closed if it does not land on the approved
runner identity.

### Gate B repository acceptance contract

Repository-side Gate B preparation uses:

- dedicated runner label: `ghostdagsim-phase4`;
- pending approval anchor: `experiments/runner-approval.json`;
- manual acceptance workflow: `.github/workflows/phase4-runner-acceptance.yml`.

Because this is a self-hosted runner attached to a public repository, the host
must be an isolated benchmark VM/host with no unrelated production workloads or
long-lived sensitive credentials. Untrusted pull-request code must not target
this runner. Gate-B workflows remain manual-only, run from canonical `master`,
and use minimum repository permissions.

The acceptance workflow runs only on a Linux x64 self-hosted runner carrying
the dedicated label. It records the GitHub runner name, CPU model and flags
fingerprint, core topology, memory, root-disk capacity, kernel, Docker server
version, and Open MPI version.

It then proves native `mpirun -np 4` capacity without `--oversubscribe` and
runs a small MPI4 smoke using the approved immutable portable image.

The workflow also requires an explicit host-lifetime policy statement explaining
why the host can run materially beyond the Phase 2 320-minute timeout.

A successful acceptance run only produces a **candidate** evidence record.
`experiments/runner-approval.json` remains `pending` until that exact
candidate is reviewed and committed. The later calibration workflow must match
the approved runner name and environment fingerprint fail-closed.

### Gate B completion evidence

Infrastructure dependency `leodbc/infra-context#38` completed and returned the accepted isolated KVM runner capability under Project Request ID:

`prq_6ee8c5ec-90c0-4b77-b07f-3f5d4e74d466`

Official project-side acceptance workflow run:

`37343161444`

Acceptance run head:

`71899b6cd181779adf3acd666e2c4df11e67844a`

Approved candidate:

- runner name: `ghostdagsim-phase4-kvm`;
- dedicated label: `ghostdagsim-phase4`;
- Linux / X64;
- Intel Core i5-4590 @ 3.30 GHz;
- 4 physical cores / 4 logical CPUs / one hardware thread per core;
- memory: `8326946816` bytes;
- root disk total: `82086711296` bytes;
- Docker `29.1.3`;
- Open MPI `4.1.6`;
- native `mpirun -np 4` without oversubscription: PASS;
- approved portable-image MPI4 smoke: PASS;
- CPU-flags SHA256: `a5514403b06cfe10655d650239085bef61c431350afa94c37572a5e093ab0ea6`;
- persistent isolated KVM VM with no provider active-time limit;
- out-of-pocket cost: zero.

Acceptance artifact:

- artifact ID: `11358858622`;
- digest: `sha256:3b25b3f3a2bfecc9dbfbcc46d15c2a46680435618460269a0b956fb331143bff`.

The accepted runner identity is persisted fail-closed in
`experiments/runner-approval.json`.

Infrastructure completion does not itself mean project integration is complete.
Gate C must still revalidate the exact runner identity at execution time and
complete the canonical 3×3 recalibration.

The VM is persistent, but its GitHub runner registration is intentionally
ephemeral because the repository is public. Gate C therefore uses one
self-hosted job that performs all nine cells sequentially after one fresh
ephemeral registration, preserving a single accepted runner identity for the
complete run.

The physical host is not CPU-exclusive/pinned. Before dispatch, unrelated host
workload must be confirmed idle/low. That attestation is an explicit manual Gate
C workflow input and is preserved in the evidence bundle.

### Gate C — canonical 3×3 recalibration

Only after both image and runner are approved:

- scenarios: small / representative / heavy;
- MPI: 1 / 2 / 4;
- RNG seed/run: 1 / 1;
- no oversubscription;
- immutable portable digest;
- artifacts/manifests retained on failure;
- no automatic retry-until-compatible-runner logic.

Repository preparation is materialized in
`.github/workflows/phase4-calibration.yml`.

Gate C is manual-only and must run from canonical `master`. Dispatch requires
two explicit review inputs:

- `RUN_PHASE4_GATE_C`;
- `HOST_IDLE_LOW_CONFIRMED`.

The workflow first validates the live runner against the exact approved
`experiments/runner-approval.json` identity, including runner name, CPU model
and flags fingerprint, topology, memory, disk total, kernel, Docker and Open MPI.
It also repeats a native MPI4 rank probe without oversubscription. A mismatch
fails closed before any simulation starts.

All nine cells execute sequentially in one self-hosted job. This is deliberate:
the accepted registration is ephemeral, and a single job preserves one runner
registration and one stable VM identity across the complete matrix while
avoiding nine separate privileged registrations.

The declared Phase-4 execution envelope is:

- per-simulation timeout: **390 minutes / 23,400 seconds**;
- per-cell harness deadline: **420 minutes / 25,200 seconds**;
- workflow job envelope: **24 hours**.

The 390-minute simulation timeout provides 70 minutes of headroom beyond the
Phase-2 heavy 320-minute timeout while retaining the existing runtime
classification thresholds: green below 270 minutes, caution from 270 to below
330 minutes, and no-go at 330 minutes or above. The increased timeout is
measurement headroom, not a relaxation of the no-go threshold.

If the complete 3×3 cannot finish within the 24-hour Gate-C job envelope, that
is itself operational evidence and must trigger review rather than an automatic
retry chain, checkpoint implementation, or security-posture change.

Every manifest embeds the verified runner evidence used for that execution.
The workflow requires exactly nine manifests and the canonical scenario/MPI/RNG
matrix before its evidence set is considered complete.

### Gate C attempt 1 outcome and continuation contract

Official Gate-C attempt 1:

`37410277338`

Attempt-1 canonical master:

`1f8ee4314e03d57d31c17a0bcbce82693d8bc81c`

Final workflow conclusion:

`cancelled`

The cancellation occurred because the single sequential self-hosted job exhausted
its declared 24-hour envelope while `heavy / MPI2` was still running. The
runner-identity gates passed and the cancellation is not classified as a runner
or infrastructure-identity failure.

Attempt-1 evidence is durably indexed in:

`experiments/phase4-gatec-attempt1.json`

The preserved source artifact is:

- artifact ID: `11459436890`;
- name: `phase4-gatec-37410277338-1`;
- digest: `sha256:dd381f25e8b162488db2b284e881194a2914d40726789bb40a90013e1fde5a03`.

Seven cells produced valid terminal evidence and are not rerun:

- small / MPI1: green;
- small / MPI2: green;
- small / MPI4: green;
- representative / MPI1: no-go / 390-minute timeout;
- representative / MPI2: caution;
- representative / MPI4: green;
- heavy / MPI1: no-go / 390-minute timeout.

`heavy / MPI2` was left in `status: starting` by global job cancellation and
is not valid terminal evidence. `heavy / MPI4` was not reached.

The original one-job 3×3 workflow must not be blindly repeated because doing so
would duplicate already-valid cells and reproduce the same global-envelope
failure mode.

Continuation is materialized separately in:

`.github/workflows/phase4-calibration-completion.yml`

The continuation runs exactly the two missing cells, sequentially, on a fresh
ephemeral registration of the same approved persistent KVM VM:

- heavy / MPI2;
- heavy / MPI4.

All canonical controls remain unchanged:

- same immutable portable image;
- same heavy scenario identity;
- RNG seed/run 1/1;
- same 390-minute simulation timeout;
- same 420-minute harness deadline;
- no oversubscription;
- same fail-closed approved runner identity.

The continuation job envelope is **15 hours**. Two cells can consume at most
14 hours of harness time, leaving explicit overhead while staying below the
24-hour boundary that cancelled attempt 1.

Before execution, the continuation verifies that the exact attempt-1 artifact
still exists, is unexpired, has the expected digest, belongs to workflow run
`37410277338`, and was produced from the expected canonical master. It also
revalidates the heavy scenario definition hash.

After both missing cells produce terminal manifests, the continuation builds a
combined nine-cell evidence index that references the seven preserved attempt-1
cells and the two new continuation cells. This is evidence composition, not a
rerun of the valid attempt-1 measurements.

Gate C remains incomplete until that combined matrix exists. No continuation
workflow is dispatched merely by merging its preparation.

### Gate C completion outcome

Continuation workflow run:

`37573460831`

Continuation result:

`SUCCESS`

The continuation executed exactly:

- heavy / MPI2;
- heavy / MPI4.

Both cells reached terminal `no-go / timeout` at the unchanged 390-minute
simulation timeout.

The continuation workflow then verified the composed nine-cell matrix as:

`status = complete_matrix_evidence`

Durable combined evidence index:

`experiments/phase4-gatec-complete.json`

Continuation artifact:

- artifact ID: `11501836680`;
- name: `phase4-gatec-completion-37573460831-1`;
- digest: `sha256:2736db39a1d75664ed7230642ac38824a67af58643474b22a5da5de0a7d46d76`.

The complete matrix is therefore terminal and auditable. Gate C must not be
rerun merely to seek a green heavy result without a separately approved change
to the experiment/runtime contract.

### Gate D — review and stop

Gate D is complete.

The final review and decision are recorded in:

`docs/experiments/PHASE4_DECISION.md`

The review compares only valid Phase 2 measurements with valid Phase 4
measurements and excludes Phase 2 MPI2/MPI4 failure durations as performance
baselines.

Phase 4 stops here before campaign orchestration, checkpointing, external
storage design, scheduler/queue work, Kubernetes, or broad simulator
optimization.

## Bootstrap stop condition

The bootstrap PR stops after the manual portable-image pipeline is reviewable.

Merging the bootstrap PR does not authorize or automatically execute the image
publish, runner provisioning, or recalibration.
