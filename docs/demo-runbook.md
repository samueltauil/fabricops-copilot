# Demo runbook

## Purpose

Show that a single approved configuration can drive provisioning, governed promotion,
operations, drift controls, and workload accelerator readiness without customer-specific
Python code.

## Mock demo

```powershell
fabricops capabilities
fabricops demo --config config\examples\synthetic-healthcare\project.yml
fabricops demo --config config\examples\synthetic-healthcare\project.yml
```

`fabricops demo` first generates a seeded Synthea dataset (Java 11+ required; the jar is
downloaded once to `.fabricops\tools`). Only aggregate row counts and a dataset hash are
written to `artifacts\synthea-dataset.json`; patient-level rows stay in
`.fabricops\synthea` (ignored by Git) and are never logged or sent to prompts. Use
`--skip-synthea` when Java is unavailable.

The first run creates mock resources. Every use-case rerun is verified as a no-op.
Inspect `artifacts\demo-summary.json` and the per-use-case plan/evidence files.

For a guided presentation:

```powershell
fabricops tui --config config\examples\synthetic-healthcare\project.yml
```

Live mode is intentionally blocked until tenant identity, capacities, Entra groups,
permissions, and supported item types have passed capability preflight.

