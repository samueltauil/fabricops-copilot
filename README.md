# FabricOps Copilot

Configuration-driven automation for the repetitive administration of Microsoft Fabric, so teams can spend their time on RTI, Fabric IQ, ontologies and agents instead of setup checklists. GitHub Copilot is used as a **developer accelerator**; deterministic code and approval gates do the execution.

> Demo/POC. All data is synthetic (generated with [Synthea](https://github.com/synthetichealth/synthea)). No PHI, no customer data.

```
FabricOps Copilot
├── Provision   Fabric landing zones (workspaces, capacity, roles, starter items)
├── Deploy      Governed dev -> test -> prod promotion
├── Operate     Health monitoring + safe, policy-gated recovery
├── Govern      Access and configuration drift
└── Accelerate  RTI, Fabric IQ, ontology, agents
```

## Principles

- **Configuration, not customer code**: one YAML describes the project; the engine is stable.
- **Safe reruns**: deterministic logical keys; a second run is a no-op.
- **Preview before change**: `plan` first, stale-plan detection, no deletes, production behind approval.
- **Least privilege, customer-owned credentials**: OIDC / `az login`, no secrets in the repo.
- **Audit without sensitive data**: allowlisted evidence, hashed IDs, row counts only.

## Screenshots (mock mode)

Preview before change:

![plan preview](docs/images/01-plan-preview.png)

Idempotent reruns across all five pillars:

![idempotent demo](docs/images/02-idempotent-demo.png)

Optional administrator TUI (health and drift):

![admin tui](docs/images/03-admin-tui.png)

Synthea synthetic dataset (aggregate counts and hash only):

![synthea](docs/images/04-synthea-dataset.png)

Tests:

![tests](docs/images/06-tests.png)

## Screenshots (live Fabric sandbox, IDs hashed)

Operate: job status from the Job Scheduler APIs:

![live operate](docs/images/09-live-operate.png)

Govern: desired vs. actual, zero drift:

![live govern](docs/images/07-live-govern.png)

Accelerate: RTI items plus Synthea data in the dev Lakehouse:

![live accelerate](docs/images/08-live-accelerate.png)

## Quick start (mock mode, no tenant needed)

```powershell
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
python -m fabricops.cli capabilities
python -m fabricops.cli plan --config config/examples/synthetic-healthcare/project.yml --use-case all
python -m fabricops.cli demo --config config/examples/synthetic-healthcare/project.yml
python -m fabricops.cli tui --config config/examples/synthetic-healthcare/project.yml
```

`demo` runs Synthea first (needs Java 11+; use `--skip-synthea` to opt out), then each use case twice to prove idempotency.

## Live mode (your own Fabric tenant)

1. `pip install -e ".[live]"` and sign in with `az login` (or use GitHub OIDC).
2. Copy `config/examples/synthetic-healthcare/live.env.example` to `live.local.env` (git-ignored) and fill in your tenant, app, capacity and group IDs.
3. Run `preflight`, then `provision-live`, `deploy-live`, `accelerate-live`, `operate-live` and `govern-live`. All preview or read only by default; mutation needs `--apply` (or `--run` for jobs) **and** `FABRICOPS_ALLOW_LIVE_MUTATION=1`.
4. GitHub Actions: workflows run on `workflow_dispatch` with OIDC. Set `AZURE_CLIENT_ID`, `AZURE_TENANT_ID` and the `FABRIC_*` repo variables; prod needs environment approval. The tenant must allow service principals to call Fabric APIs.

Never commit tenant, subscription, group or capacity IDs. `.gitignore` excludes `*.local.env`, `.env*`, `artifacts/` and `.fabricops/`.

## Fabric MCP

`.vscode/mcp.json` and `.mcp.json` register the [Fabric MCP server](docs/fabric-mcp.md), used by Copilot for API docs and item-definition contracts.

## Docs

[Architecture](docs/architecture.md) · [Security model](docs/security-model.md) · [Capability matrix](docs/capability-matrix.md) · [Demo runbook](docs/demo-runbook.md) · [Use-case insights](docs/use-case-insights.md)

## Status

All five pillars run in mock mode and live against a Fabric sandbox. Fabric IQ, ontology and agent templates remain capability probes (preview APIs). The GitHub Actions workflows are untested end to end.
