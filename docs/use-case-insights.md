# FabricOps use-case insights

## Synthetic data (Synthea)

The demo data comes from [Synthea](https://github.com/synthetichealth/synthea): seeded,
reproducible synthetic patients, encounters, conditions and observations. The seed,
population and location are configured under `spec.synthea`. Synthea output looks
realistic, so it is still treated as sensitive-shaped: reports contain counts and a hash
only, and Copilot prompts must not include patient-level rows.

## Core insight

The highest-value Copilot opportunity is not to replace Fabric administration with
free-form AI decisions. It is to help engineers create and maintain a governed
automation product that turns repeated administrative choices into reviewed
configuration, deterministic plans, verified execution, and reusable evidence.

This distinction matters because Fabric capabilities evolve at different speeds.
Workspace operations are broadly automatable, while item deployment, identity support,
monitoring coverage, and preview workloads vary. A credible demo makes those boundaries
visible instead of hiding them.

## Provision

The repetitive unit is not just workspace creation. It is the complete landing-zone
contract: name, environment boundary, capacity, group-based access, starter content,
monitoring enrollment, and evidence that the result matches policy. The compelling
moment is the second run: a no-op proves the workflow is a reconciler rather than a
one-time script.

## Deploy

Promotion risk comes from hidden environment coupling. The package and its configuration
must be separate, supported item types must be detected before deployment, and any
remaining development reference must block production. A release record is as important
as the deployment because it explains the package, substitutions, approval, tests, and
target state.

## Operate

Centralizing status is useful, but automatic retry is the dangerous boundary. Retry must
be a declared property of a job, not a reaction to any failure. The operational demo
should emphasize ownership, affected data products, freshness, telemetry gaps, attempt
limits, and verification after recovery.

## Govern

Governance becomes actionable when approved desired state can be compared with actual
state. Start with report-only drift and a narrow remediation allowlist. Removing access,
changing production capacity, deleting items, or resolving unknown principals should
remain approval-gated.

## Accelerate

RTI, Fabric IQ, ontology, and agents benefit from a paved administrative road. An
accelerator template should declare prerequisites, deployment support, environment
parameters, verification, monitoring, governance metadata, and manual limitations.
This allows preview workloads to participate honestly even when their lifecycle cannot
yet be fully automated.

## GitHub Copilot

Copilot should accelerate bounded engineering work: add a resource handler from official
documentation, generate tests and sanitized fixtures, maintain the capability matrix,
create a policy rule, or diagnose a sanitized run. Pull-request review, tests, policy,
and approval gates remain authoritative.

