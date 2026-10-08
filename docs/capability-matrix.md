# Capability matrix

Last reviewed: 2026-10-07. Revalidate before relying on any row; Fabric changes quickly.

Status legend: **Live** = ran against a real Fabric sandbox; **Probe** = reports readiness
only; **Untested** = code exists, not yet exercised end to end.

| Capability | Implementation | Status | Notes |
|---|---|---|---|
| Workspace discovery | `discover`, `live.py` | Live | Paginated read-only listing. |
| Workspace create | `provision-live` | Live | 3 workspaces; rerun is `no-op`. |
| Capacity assignment | `provision-live` | Live | Capacity must be running. |
| Workspace roles | `provision-live` | Live | Groups only; Admin/Contributor/Viewer. |
| Item deployment | `deploy-live` | Live | Lakehouse, Notebook, DataPipeline in dev, test, prod. Other item types are reported unsupported. |
| Job health and history | `operate-live` | Live | Job Scheduler API; a pipeline run completed and shows `healthy`. |
| Safe recovery | `operate-live --retry` | Policy path | Denied unless `retryable: true` with `maxAttempts`. No failure was injected live; covered by tests. |
| Governance drift | `govern-live` | Live | Capacity, roles, starter items, dev references. Zero findings on a clean run. |
| Drift injection demo | `--inject-demo-drift` | Untested | Verified only against a test double. |
| RTI accelerator | `accelerate-live` | Live | Eventhouse, KQL database, Eventstream. |
| Synthea data load | `accelerate-live` | Live | CSVs uploaded to `Files/synthea`; the notebook has not been run, so no Delta tables yet. |
| Fabric IQ | Capability probe | Probe | Preview APIs. |
| Ontology | Capability probe | Probe | Preview APIs. |
| Agents | Capability probe | Probe | Preview APIs. |
| Metadata scanner / activity events | Not implemented | n/a | Needs tenant-admin setup; governance uses workspace and item APIs only. |
| GitHub Actions workflows | `.github/workflows` | Untested | OIDC and environments configured; tenant service-principal setting unconfirmed. |

Official baseline:

- Fabric identity support: https://learn.microsoft.com/en-us/rest/api/fabric/articles/identity-support
- Fabric REST scopes: https://learn.microsoft.com/en-us/rest/api/fabric/articles/scopes
- Fabric CI/CD practices: https://learn.microsoft.com/en-us/fabric/fundamentals/understand-best-practices-fabric-cicd
- `fabric-cicd` item notes: https://github.com/microsoft/fabric-cicd/blob/main/docs/reference/item_types.md
- Job Scheduler API: https://learn.microsoft.com/en-us/rest/api/fabric/core/job-scheduler/run-on-demand-item-job
- Workspace monitoring: https://learn.microsoft.com/en-us/fabric/get-started/workspace-monitoring-overview
- Metadata scanning: https://learn.microsoft.com/power-bi/enterprise/service-admin-metadata-scanning
