# Architecture

FabricOps separates configuration, planning, execution, and evidence.

1. YAML describes approved desired state.
2. Resource builders translate that configuration into stable logical resources.
3. The planner compares desired resources with discovered adapter state.
4. Policies can block an otherwise valid plan.
5. Apply checks the configuration hash, executes changes, and verifies state.
6. Reports emit only allowlisted operational evidence.

The mock adapter persists local JSON and proves rerun behavior without a tenant. Live
Fabric clients will implement the same state and resource contracts after tenant
identity and capability preflight are configured.

The CLI is the headless contract. The TUI calls the same Python services and cannot
bypass policy or stale-plan protections.

