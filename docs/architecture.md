# Architecture

FabricOps separates **configuration**, **planning**, **execution** and **evidence**. The
same flow is used by the CLI, the optional TUI and the GitHub Actions workflows.

```text
project.yml  ->  config loader  ->  desired resources
                                         |
              live Fabric client  ->  discover actual state
                                         |
                                    diff (create / update / no-op / blocked)
                                         |
                                  policy checks  ->  preview (default)
                                         |
                       --apply + FABRICOPS_ALLOW_LIVE_MUTATION=1
                                         |
                                  execute + verify
                                         |
                         sanitized JSON / Markdown evidence
```

## Modules (`src/fabricops`)

| Module | Role |
|---|---|
| `config.py`, `models.py` | Load and validate the YAML; reject unknown fields. |
| `resources.py`, `engine.py`, `state.py` | Logical resource keys, planner, plan hash, stale-plan check (mock mode). |
| `capabilities.py`, `preflight.py` | What is supported and which prerequisites exist, without printing values. |
| `live.py` | Fabric REST client: auth (`DefaultAzureCredential`), pagination, long-running operations, `Retry-After`, sanitized errors. |
| `live_provision.py` | Workspaces, capacity assignment, role assignments. |
| `live_deploy.py` | Lakehouse, Notebook, DataPipeline per environment, in order. |
| `live_operate.py` | Job Scheduler health, on-demand runs, policy-gated retry. |
| `live_govern.py` | Read-only drift: capacity, roles, items, dev-reference leakage. |
| `live_accelerate.py` | Eventhouse, KQL database, Eventstream, Synthea upload, notebook update. |
| `synthea.py` | Seeded synthetic data; only counts and a hash leave the machine. |
| `reports.py` | Allowlisted evidence writer. |
| `tui.py` | Guided terminal UI, a thin client of the same services. |
| `cli.py` | The headless contract (`fabricops <command>`). |

## Key design rules

1. **Idempotent by key.** Resources are identified by a logical key (customer, project,
   environment, role), not remembered IDs. Discover first, then act.
2. **Preview by default.** Live mutation needs `--apply` and
   `FABRICOPS_ALLOW_LIVE_MUTATION=1`.
3. **No deletes.** The engine creates and reconciles; removal is out of scope.
4. **Unknown means blocked.** Unsupported capabilities are reported as `blocked`,
   `manual` or `unknown`, never silently degraded.
5. **Sanitized evidence.** Workspace IDs are hashed; errors carry status, Fabric error code
   and correlation ID only.

## Execution paths

- **Local:** your `az login` identity, for demos and development.
- **GitHub Actions:** OIDC federated credentials per environment (`dev`, `test`, `prod`);
  `prod` requires a reviewer. See the [security model](security-model.md).
- **Mock:** a local JSON-backed fake of Fabric used only by tests (`fabricops demo`).

## Where Copilot fits

Copilot helps build and extend this code and can use the Fabric MCP server for API and
item-definition knowledge. It is not part of the runtime path. See the README and
[Fabric MCP](fabric-mcp.md).
