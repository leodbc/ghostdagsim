# Experiment harness

This directory contains the infrastructure-calibration scenarios used to decide
whether `ghostdagsim` fits GitHub-hosted Actions. These are **not** presented as
the scientific design of a particular study.

## Canonical identities

- simulator source SHA: `ba001537e3be8edc18e8e8692121da5bcb451189`
- ns-3: `3.46.1`
- benchmark image: must be `ghcr.io/leodbc/ghostdagsim@sha256:<digest>`
- calibration RNG: `RngSeed=1`, `RngRun=1`
- MPI candidates: `1`, `2`, `4`

The image digest is intentionally not specified in source yet. Publishing and
pinning the image built from the canonical simulator SHA is a prerequisite for
the later calibration execution.

## Scenario provenance

| Scenario | Core workload | Basis |
| --- | --- | --- |
| `small` | 20 nodes, 10 miners, 50 blocks/miner | Exact v1.0.0 quick-start example |
| `representative` | 100 nodes, 10 miners, 1000 blocks/miner | 100-node upstream entrypoint example + current defaults |
| `heavy` | 1000 nodes, 10 miners, 1000 blocks/miner | v1.0.0 says MPI tested up to 1000 nodes + current defaults |

Every other relevant simulator default is repeated explicitly in each scenario
file. That is deliberate: future changes to C++ defaults must not silently
change a benchmark revision.

`representative` means *representative infrastructure calibration workload* in
this repository. It is not evidence that the upstream author uses that exact
configuration for a specific research campaign.

## Runner

The runner uses only the Python standard library and Docker CLI. The host
`results` directory is mounted at `/results/results` because the production
image already uses `/results` as its working directory while the simulator
itself writes to relative `results/<run_name>/`. This preserves the
repository-level `results/<run_name>/` contract.

Example dry-run validation:

```bash
python3 scripts/run-experiment.py \
  --scenario experiments/scenarios/small.json \
  --image-ref ghcr.io/leodbc/ghostdagsim@sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef \
  --mpi-threads 1 \
  --rng-seed 1 \
  --rng-run 1 \
  --results-root /tmp/ghostdagsim-results \
  --dry-run
```

A real run uses the same command without `--dry-run` and with the actual
canonical image digest.

The runner deliberately refuses mutable image tags, MPI values outside the
initial calibration set, invalid scenarios, non-positive RNG values, and reuse
of a non-empty `results/<run_name>/` directory.

## Manifest

Every invocation creates:

```text
results/<scenario>-mpi<threads>-rng<run>/manifest.json
```

The manifest contains the canonical source and container identities, scenario
revision and provenance, full simulator arguments, RNG/MPI settings, GitHub
runner metadata, wall time, disk snapshots, simulator result bytes, exit code,
and Docker OOM state when available.

The manifest is written before Docker starts and finalized after execution, so a
harness-visible failure still leaves an auditable record whenever the host
filesystem remains writable.

## Summary

One or more manifests can be summarized as CSV:

```bash
python3 scripts/summarize-experiment.py results/*/manifest.json
```

Runtime classifications follow the Phase 0 protocol:

- `green`: < 270 minutes and no execution/resource failure;
- `caution`: 270–330 minutes;
- `no-go`: >= 330 minutes or an observed execution/OOM failure;
- `dry-run`: command/manifest validation only.

The 9-job calibration workflow itself belongs to the next phase and is not
implemented here.
