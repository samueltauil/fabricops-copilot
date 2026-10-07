# Using Fabric MCP with FabricOps

The Microsoft Fabric MCP server (`@microsoft/fabric-mcp`, source: `microsoft/mcp`
`servers/Fabric.Mcp.Server`) is configured in `.vscode/mcp.json` and `.mcp.json`.

## Role: developer accelerator, not an execution path

| Use | Fabric MCP capability | FabricOps consumer |
|---|---|---|
| Add item support | Item-definition JSON schemas, OpenAPI specs | Capability registry, resource handlers, contract fixtures |
| Correct API usage | Best-practice guidance (pagination, errors, LROs) | `live.py` client conventions |
| Exploration | Operational tools under the configured identity | Read-only sandbox inspection while building |
| Data Factory | Pipeline and Dataflow Gen2 helpers | Deploy and Accelerate starter packages |

## Guardrails

- Production plan/apply stays in the deterministic CLI and GitHub Actions, never ad hoc MCP calls.
- Use the read-only `az` identity, or a least-privilege identity, for MCP operational tools.
- Do not paste MCP output containing item definitions with secrets, connection strings or data
  into prompts, issues or artifacts.
- Verify API behavior suggested by MCP against official docs before enabling live mutation.
- Record which item types were validated through MCP in `docs/capability-matrix.md`.

## Start

Requires Node.js LTS. Reload the Copilot session so it discovers the `fabric-mcp-server`
server, then ask Copilot to generate or review a resource handler using the MCP item
schemas.
