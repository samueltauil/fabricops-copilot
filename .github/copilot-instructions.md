# FabricOps Copilot engineering instructions

- Keep customer and environment differences in validated configuration, not Python branches.
- All resource handlers must be idempotent and implement discover, diff, apply, and verify.
- Preserve plan-before-apply, configuration hashes, policy checks, and production approvals.
- Never log tokens, authorization headers, item definition bodies, source data, PHI, secrets,
  connection strings, or unsanitized API errors.
- Unknown capabilities must become `blocked` or `manual`; do not silently degrade.
- Add tests for reruns, stale plans, error handling, and sanitized evidence.
- Use the Fabric MCP server (see docs/fabric-mcp.md) for item schemas, API specs and best
  practices when adding Fabric support; it never replaces the plan/apply CLI for mutations.
- Update the capability registry and documentation when Fabric item support changes.

