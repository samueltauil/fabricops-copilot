# Demo runbook

A step-by-step, educational walkthrough of the live FabricOps Copilot demo. Each step says
**what you run**, **what happens**, **what to look for**, and **why it matters** to a Fabric
administrator. Total time: about 25 minutes live, 10 if you only narrate the dashboard.

## The story

Northwind Health (fictional) needs a Fabric environment for care-operations analytics:
three workspaces (dev/test/prod), the right groups with the right roles, starter items,
monitoring, and a Real-Time Intelligence foundation. Normally that is a day of portal
clicking per team, repeated for every project. Here **one YAML file** drives all of it,
and every step is previewed, repeatable, and leaves sanitized evidence.

GitHub Copilot's role is explained in the [README](../README.md#how-github-copilot-is-used).
In short: Copilot helped build and maintain this tool; the tool, not Copilot, changes
Fabric.

## Before you start

| Need | Why |
|---|---|
| A Fabric capacity that is **running** (an F2+ SKU works) | Workspaces need a capacity for Lakehouse, Eventhouse, etc. A paused capacity makes item creation fail. |
| Entra security groups (admins, engineers, consumers) | Roles are granted to groups, never to individuals. |
| `az login` as a user who can create workspaces and use the capacity | Local demos use your Azure CLI identity. No secret is stored. |
| Python 3.11+, Java 11+ | Python runs the CLI; Java runs Synthea. |

```powershell
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -e ".[live]"
az login
Copy-Item config\examples\synthetic-healthcare\live.env.example config\examples\synthetic-healthcare\live.local.env
# edit live.local.env: tenant, app, capacity and group IDs (git-ignored, never commit)
```

Load the env file into your shell:

```powershell
Get-Content config\examples\synthetic-healthcare\live.local.env | ForEach-Object { if ($_ -match '=' -and $_ -notmatch '^#') { $k,$v = $_ -split '=',2; Set-Item "env:$k" $v } }
$cfg = "config\examples\synthetic-healthcare\project.yml"
```

> **Concept: two locks on every change.** A command is read-only unless you pass `--apply`
> (or `--run` for jobs) **and** set `FABRICOPS_ALLOW_LIVE_MUTATION=1`. Forgetting either is
> safe: you get a preview.

## Optional: run the dashboard live during the demo

The dashboard can run as a tiny local web server that re-reads the JSON reports every
2 seconds and updates in place (a pulsing **Live** chip appears in the top bar, and panels
flash when data changes). Open it on a second monitor or a second browser window.

```powershell
# Terminal A (leave running): serve the dashboard on http://127.0.0.1:8765
python scripts\build_dashboard.py artifacts\real --serve
```

Then run the demo steps below in a second terminal, always with `--output artifacts\real`.
Each `*-live` command rewrites its report, and the dashboard picks it up on the next poll.

| Tip | Detail |
|---|---|
| Start from a clean slate | Serve a fresh folder (for example `artifacts\demo`) and use `--output artifacts\demo`. Until all five reports exist the page shows a "Waiting for the first reports" checklist, then the panels appear. |
| Rehearsed or fresh | Serving `artifacts\real` shows the last full run immediately, and panels change as you rerun commands. |
| Options | `--port 9000` changes the port; `--interval 1` polls every second. |
| Safety | The server binds to `127.0.0.1` only and serves the same sanitized, hashed reports. No Fabric or Azure call is made by the dashboard. |
| Stop | `Ctrl+C` in Terminal A. |

## Step 0: Understand the configuration

Open `config/examples/synthetic-healthcare/project.yml`. It is the whole demo:

- `environments`: three workspaces and which capacity each uses.
- `access`: which group gets Admin, Contributor, Viewer.
- `deployment`: the starter package (Lakehouse, Notebook, DataPipeline).
- `monitoring`: jobs to watch, owners, freshness, and whether a failure may be retried.
- `synthea`: seed, population, location for the synthetic data.

**Teach:** to onboard another customer you copy this file and change names and refs. No
Python changes. Group and capacity IDs are *references* (`capacityRef`, `adminGroupRef`)
resolved from environment variables, so the file is safe to review in a pull request.

## Step 1: Preflight

```powershell
python -m fabricops.cli preflight --output artifacts\real
python -m fabricops.cli discover --config $cfg --output artifacts\real
```

**What happens:** checks that the required settings exist (never printing their values),
then lists existing workspaces read-only.
**Look for:** all prerequisites present; the target workspaces absent on a first run.
**Why:** catching a missing capacity or group mapping *before* any API mutation.

## Step 2: Provision, "landing zone in a box"

```powershell
python -m fabricops.cli provision-live --config $cfg --output artifacts\real            # preview
$env:FABRICOPS_ALLOW_LIVE_MUTATION = "1"
python -m fabricops.cli provision-live --config $cfg --output artifacts\real --apply    # do it
```

**What happens:** for each environment the engine discovers actual state, diffs it against
the YAML, and plans `create`, `update` or `no-op` for the workspace, the capacity
assignment and each role assignment. Only missing pieces are created.
**Look for:** the preview lists creates; after apply, open the Fabric portal and see
`fab-northwind-care-dev/test/prod` with the groups assigned.
**Run it again.** Everything becomes `no-op`. That is the *idempotency* proof: reruns never
create duplicate workspaces or role assignments.

## Step 3: Deploy, governed promotion

```powershell
python -m fabricops.cli deploy-live --config $cfg --output artifacts\real --apply
```

**What happens:** the starter package (Lakehouse, Notebook, DataPipeline) is created in dev,
then test, then prod, in that order, skipping anything that already exists.
**Look for:** each item reports `create` the first time and `no-op` afterwards; the portal
shows the same item set in all three workspaces (see the README screenshots).
**Teach:** the production approval gate comes from the GitHub workflow (`deploy.yml`):
`prod` is a protected environment that needs a named reviewer. Locally the same code runs,
but the workflow is what enforces human approval in a team setting.

## Step 4: Accelerate, RTI plus Synthea data

```powershell
python -m fabricops.cli accelerate-live --config $cfg --output artifacts\real --apply
```

**What happens:**
1. Generates seeded **Synthea** patients, encounters, conditions and observations
   (identical every run because the seed is fixed). Patient-level rows stay in
   `.fabricops/synthea` (git-ignored). Reports contain only counts and a dataset hash.
2. Creates an **Eventhouse** (`rti-care-ops`) with its KQL database, and an **Eventstream**.
3. Uploads three CSVs to the dev Lakehouse `Files/synthea`.
4. Updates the starter notebook so it can load the CSVs into Delta tables.

**Look for:** Eventhouse and Eventstream in the dev workspace; three CSV files in the
Lakehouse Files view.
**Why:** this is the payoff. Once landing zone, deployment and monitoring are automated, a
team can adopt RTI in minutes instead of weeks. Fabric IQ, ontology and agents are
included as **capability probes** only because their APIs are still preview; the demo
does not claim they are automated.

## Step 5: Operate, health and safe recovery

```powershell
python -m fabricops.cli operate-live --config $cfg --output artifacts\real           # read health
python -m fabricops.cli operate-live --config $cfg --output artifacts\real --run     # trigger approved jobs
python -m fabricops.cli operate-live --config $cfg --output artifacts\real --retry   # retry eligible failures
```

**What happens:** reads job history through the Job Scheduler API and normalizes it into
`healthy`, `late`, `failed`, or `unknown`.
**Look for:** `ingest-operational-events` is `healthy` after a completed run;
`publish-care-unit-metrics` is `unknown` because no matching Fabric item exists yet. The
engine reports that gap instead of guessing.
**Teach the retry policy:** retry is **denied by default**. A job is retried only if the
YAML sets `retryable: true` *and* `maxAttempts`, it is not already running, and the
attempts are not exhausted. `--retry` on a non-retryable job does nothing.

## Step 6: Govern, drift detection

```powershell
# FABRICOPS_GOVERN_ALLOWED_PRINCIPALS is already set in live.local.env
python -m fabricops.cli govern-live --config $cfg --output artifacts\real
```

**What happens:** compares desired state with reality: workspace capacity, role
assignments (missing and unexpected), starter items, and any references that still point at
dev. The report is read-only.
**Look for:** `0` drift findings on a clean run.
**Teach least privilege:** the owner principal that holds Admin in every workspace must be
listed in `FABRICOPS_GOVERN_ALLOWED_PRINCIPALS`, otherwise it is flagged as an unexpected
principal. Nothing is assumed to be fine.
Optionally, with `FABRICOPS_DRIFT_DEMO_PRINCIPAL` set, `--inject-demo-drift` adds an
extra assignment and `--revert-demo-drift` removes it, so you can show a finding appear
and clear. (Only tested against a test double; rehearse it first.)

## Step 7: Show the evidence

If you are running the live dashboard (see above), it already shows everything. Otherwise
render the static PNG:

```powershell
python scripts\build_dashboard.py artifacts\real
```

Open `docs/images/dashboard.png`. Every number comes from the JSON reports in
`artifacts/real`. Walk the audience through the five pillars left to right, then open the
Fabric portal to show the same items exist for real.

## Step 8 (optional): GitHub Actions and Copilot

- `live-preflight.yml`, `provision.yml`, `deploy.yml`, `operate.yml`, `govern.yml`,
  `accelerate.yml` are all `workflow_dispatch`, preview by default, using GitHub OIDC (no
  stored secret). They have not yet been run end to end; the tenant must allow service
  principals to call Fabric APIs.
- Show `.github/copilot-instructions.md` and a prompt in `.github/prompts/`, then ask
  Copilot to "add support for a new Fabric item type". It follows the repo rules
  (idempotent handler, tests, capability matrix update). See the README for Copilot's
  full role.

## Talking points

| Admin pain | What the demo shows |
|---|---|
| Repeating workspace setup per team | One YAML, three workspaces, roles and items |
| Fear of duplicates on rerun | Second run is all `no-op` |
| Risky promotion to prod | Ordered deploy, approval gate, no deletes |
| Opening every run history | One normalized health view with explicit `unknown` |
| Silent access creep | Drift report with allow-listed principals |
| Slow adoption of RTI/IQ | Eventhouse and data ready right after setup |

## Mock mode (offline, for tests only)

`fabricops demo` runs against a local JSON-backed fake of Fabric so tests run without a
tenant. It is **not** the demo; use it only to develop and test.

## Reset

The engine never deletes. To start over, delete the three `fab-northwind-care-*`
workspaces in the Fabric portal. Pause the capacity when idle to save cost.

## Troubleshooting

| Symptom | Likely cause and fix |
|---|---|
| HTTP 503 or connection aborted | Transient Fabric API issue; rerun (commands are idempotent). |
| Item creation fails with capacity errors | Capacity is paused; resume it in Azure. |
| 401/403 for a service principal | Tenant setting "Service principals can use Fabric APIs" is off, or the principal is not in the allowed group. |
| Govern reports an unexpected principal | Add the owner to `FABRICOPS_GOVERN_ALLOWED_PRINCIPALS`, or remove the extra role. |
| Synthea step fails | Java 11+ is missing; install it. |
