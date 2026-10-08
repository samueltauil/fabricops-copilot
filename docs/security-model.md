# Security model

## Trust boundaries

- GitHub stores source, approved configuration, workflows, and sanitized artifacts.
- Customer-controlled Entra identities authorize Fabric access.
- Fabric remains the source of actual workspace, item, job, and governance state.
- The local mock state is test evidence only and is never treated as production state.

## Identity

The preferred GitHub Actions path is OpenID Connect federation with short-lived tokens.
Separate identities should be used for provisioning/deployment and read-only
monitoring/governance. Recovery execution requires an additional explicitly approved
permission set.

`fabricops preflight` checks that tenant, client, capacity mappings, and a supported
credential signal exist. It never emits configured values.

Live adapters authenticate through `DefaultAzureCredential` (your `az login` locally,
OIDC in GitHub Actions). Live mutation is double-locked: the `--apply` (or `--run`) flag
and `FABRICOPS_ALLOW_LIVE_MUTATION=1`. Reports emit hashes rather than raw workspace IDs,
and API failures are sanitized to status, Fabric error code, and correlation ID.
Governance is read-only; unexpected principals are judged against
`FABRICOPS_GOVERN_ALLOWED_PRINCIPALS`.

Local files that hold real identifiers (`*.local.env`, `.env*`, `artifacts/`,
`.fabricops/`) are git-ignored. Published screenshots are cropped to exclude URLs, account
and capacity details.

### GitHub OIDC prerequisites

- The Entra app has federated credentials for `environment:dev`, `environment:test`, and
  `environment:prod` of this repository. Client and tenant identifiers live in GitHub
  Actions variables (`AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `FABRIC_*`), never in files.
- The `prod` GitHub environment requires a reviewer before any job runs.
- Live workflows run only on `workflow_dispatch`, preview by default, and mutate only when
  the `apply` input is true.
- **Tenant prerequisite (not verified automatically):** a Fabric admin must enable
  "Service principals can use Fabric APIs" in the Fabric admin portal (tenant settings),
  scoped to a security group containing the app's service principal, and the principal
  must be a member of the target capacity/workspaces. No client secret exists to test this
  from the CLI; confirm via the first `live-preflight` workflow run.

## Data handling

Logs and portable evidence are allowlisted. They may include operation identifiers,
logical resource aliases, action/outcome, timing, and Fabric correlation identifiers.
They must not include tokens, authorization headers, source definitions, connection
strings, query results, data samples, PHI, or raw customer data.

## Change control

- Plan artifacts are immutable inputs to apply.
- A configuration hash prevents stale apply.
- Production uses protected GitHub environments and reviewers.
- Deletes and access removal are outside the initial automatic remediation allowlist.
- Retry is denied unless an owner declares idempotency, eligible failures, and limits.
