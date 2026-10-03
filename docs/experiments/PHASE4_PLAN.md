# Phase 4 — portable image and pinned self-hosted recalibration

Status: **BOOTSTRAP — repository preparation only**

Issue: #9

Phase 4 baseline:

`4d67fb14a539deb7e8f2749d017f497f6bdd90e1`

Canonical simulator source:

`ba001537e3be8edc18e8e8692121da5bcb451189`

ns-3:

`3.46.1`

Historical Phase 2 image:

`ghcr.io/leodbc/ghostdagsim@sha256:13480d2ddc80ac63e46651f6b25b50abef33ae93cdd5ca527ca84d1d205878b0`

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

### Gate C — canonical 3×3 recalibration

Only after both image and runner are approved:

- scenarios: small / representative / heavy;
- MPI: 1 / 2 / 4;
- RNG seed/run: 1 / 1;
- no oversubscription;
- immutable portable digest;
- artifacts/manifests retained on failure;
- no automatic retry-until-compatible-runner logic.

The job envelope may be longer than Phase 2, but the new timeout/deadline must
be declared before dispatch and must provide material headroom beyond the
Phase 2 heavy 320-minute timeout.

### Gate D — review and stop

After the 3×3 recalibration, compare only valid measurements.

Phase 2 MPI2/MPI4 failure durations are not performance baselines.

Stop before campaign orchestration, checkpointing, external storage design,
scheduler/queue work, Kubernetes, or broad simulator optimization.

## Bootstrap stop condition

The bootstrap PR stops after the manual portable-image pipeline is reviewable.

Merging the bootstrap PR does not authorize or automatically execute the image
publish, runner provisioning, or recalibration.
