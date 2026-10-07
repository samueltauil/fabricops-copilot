# Capability matrix

Last reviewed: 2026-10-07. Revalidate before enabling live mutation.

| Capability | POC path | Live status |
|---|---|---|
| Workspace discovery | Live read-only adapter with pagination | Fabric REST API; GitHub OIDC and workspace visibility required |
| Workspace create | Mock resource handler | Fabric REST API; tenant preflight required; mutation intentionally blocked |
| Capacity assignment | Mock resource handler | Fabric REST API; capacity and caller permissions required |
| Workspace roles | Mock resource handler | Fabric REST API; Entra group mappings required |
| Item promotion | Package resources and plan | `fabric-cicd`/definition API support varies by item type |
| Job health/history | Normalized mock health report | Job Scheduler API adapter required |
| Safe recovery | Policy and eligibility report | Mutation remains disabled pending API/job validation |
| Governance drift | Desired/actual mock comparison | Scanner/activity adapters need admin setup |
| RTI accelerator | Automated template contract | Validate Eventhouse/Eventstream support and capacity |
| Fabric IQ | Capability probe | Preview/assisted path may be required |
| Ontology | Capability probe | Preview/assisted path may be required |
| Agents | Capability probe | Preview/assisted path may be required |

Official baseline:

- Fabric identity support: https://learn.microsoft.com/en-us/rest/api/fabric/articles/identity-support
- Fabric REST scopes: https://learn.microsoft.com/en-us/rest/api/fabric/articles/scopes
- Fabric CI/CD practices: https://learn.microsoft.com/en-us/fabric/fundamentals/understand-best-practices-fabric-cicd
- `fabric-cicd` item notes: https://github.com/microsoft/fabric-cicd/blob/main/docs/reference/item_types.md
- Job Scheduler API: https://learn.microsoft.com/en-us/rest/api/fabric/core/job-scheduler/run-on-demand-item-job
- Workspace monitoring: https://learn.microsoft.com/en-us/fabric/get-started/workspace-monitoring-overview
- Metadata scanning: https://learn.microsoft.com/power-bi/enterprise/service-admin-metadata-scanning
