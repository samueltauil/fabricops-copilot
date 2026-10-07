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
credential signal exist. It never emits configured values. Live mutation stays disabled
until API-specific identity support and least-privilege permissions are verified in the
sandbox.

The first live adapter is read-only workspace discovery through
`DefaultAzureCredential`. It emits hashes rather than raw workspace IDs in portable
reports and sanitizes API failures to status, Fabric error code, and correlation ID.

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
