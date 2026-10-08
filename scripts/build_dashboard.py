"""Build the FabricOps reconciliation view from the live reports.

Reads the sanitized JSON reports written by the *-live commands (hashed IDs only) and
renders one HTML page. By default it captures a PNG with a headless browser; with
--serve it serves the page locally and refreshes it while the demo runs.

    python scripts/build_dashboard.py artifacts/real            # write docs/images/dashboard.png
    python scripts/build_dashboard.py artifacts/real --serve    # http://127.0.0.1:8765
"""

from __future__ import annotations

import argparse
import html
import json
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

_ap = argparse.ArgumentParser()
_ap.add_argument("reports", nargs="?", default="artifacts/real")
_ap.add_argument("--serve", action="store_true", help="serve a live, auto-refreshing dashboard")
_ap.add_argument("--port", type=int, default=8765)
_ap.add_argument("--interval", type=int, default=2, help="browser refresh interval in seconds")
ARGS = _ap.parse_args()

REPORTS = Path(ARGS.reports)
OUT = Path("docs/images")
REPORT_FILES = [
    "live-provision.json", "live-deploy.json", "live-operate.json",
    "live-govern.json", "live-accelerate.json",
]
ENVS = ["dev", "test", "prod"]

CSS = """
:root{
  --bg:#fff;--ink:#16212b;--ink2:#3f4e5b;--mute:#6b7885;--rule:#e2e7ec;--rule2:#c9d1d9;--tint:#f5f7f9;
  --ok:#0d7a5f;--warn:#b25e09;--bar:#5b7a8c;
  --ui:'Segoe UI Variable Text','Segoe UI',system-ui,sans-serif;
  --display:'Segoe UI Variable Display','Segoe UI',system-ui,sans-serif;
  --mono:'Cascadia Mono','Consolas',monospace;
}
*{box-sizing:border-box}
body{margin:0;width:1440px;background:var(--bg);color:var(--ink);font:13px/1.45 var(--ui);
  -webkit-font-smoothing:antialiased;font-variant-numeric:tabular-nums}
.top{height:44px;border-bottom:1px solid var(--rule);display:flex;align-items:center;padding:0 40px;gap:14px}
.top .name{font:600 14px var(--display)}
.top .scope{color:var(--mute)}
.top .end{margin-left:auto;display:flex;gap:20px;align-items:center;color:var(--mute)}
.livedot{display:inline-flex;align-items:center;gap:7px;color:var(--ink2)}
.livedot i{width:7px;height:7px;border-radius:50%;background:var(--ok);display:block}
.page{padding:32px 40px 24px}
.head{display:grid;grid-template-columns:minmax(0,1fr) 430px;gap:64px;align-items:start;margin-bottom:30px}
h1{margin:0 0 8px;font:600 28px/1.2 var(--display);letter-spacing:-.4px}
.lead{margin:0;color:var(--ink2);font-size:14px;line-height:1.55;max-width:600px}
.cmds th{padding-top:0}
.layout{display:grid;grid-template-columns:minmax(0,1fr) 430px;gap:64px;align-items:start}
.layout>div>section+section{margin-top:30px}
h2{margin:0;font:600 15px var(--display)}
.sechead{display:flex;align-items:baseline;justify-content:space-between;margin-bottom:8px}
.sechead code{font:11.5px var(--mono);color:var(--mute)}
table{width:100%;border-collapse:collapse}
th{text-align:left;font-weight:600;font-size:12px;color:var(--mute);padding:7px 14px 7px 0;border-bottom:1px solid var(--rule2);white-space:nowrap}
td{padding:7px 14px 7px 0;border-bottom:1px solid var(--rule);white-space:nowrap;vertical-align:middle}
th:last-child,td:last-child{padding-right:0}
th.r,td.r{text-align:right}
td.w{white-space:normal}
.grid th.env{color:var(--ink);font-size:13px}
.grid th.env span{display:block;font-weight:400;color:var(--mute);font-size:12px}
.grid td{padding-top:6px;padding-bottom:6px}
.grid tr.g td{border-bottom:0;padding:16px 0 4px;font-weight:600;font-size:12px;color:var(--mute)}
.grid tr.g:first-of-type td{padding-top:8px}
.grid td.k{color:var(--ink2);width:30%}
.grid td.k small{display:block;color:var(--mute);font-size:11.5px}
.cell{display:inline-flex;align-items:center;gap:7px;color:var(--ink2)}
.cell svg{flex:none;color:var(--ok)}
.cell.change{color:var(--warn);font-weight:600}.cell.change svg{color:var(--warn)}
.cell.na{color:#a4afb9}
.hash{font:11px var(--mono);color:var(--mute);margin-left:4px}
.mono{font:12px var(--mono);color:var(--ink2)}
.sub{display:block;color:var(--mute);font-size:12px}
.nm{font-weight:600}
.state{display:inline-flex;align-items:center;gap:7px}
.state i{width:8px;height:8px;border-radius:50%;background:var(--ok);display:block}
.state.none i{background:none;border:1.5px solid #8b97a3}
.bar{display:block;height:6px;background:var(--bar);opacity:.85}
td.bw{width:48%;padding-right:14px}
.note{margin:8px 0 0;color:var(--mute);font-size:12px;line-height:1.5}
.foot{margin-top:34px;padding-top:10px;border-top:1px solid var(--rule);display:flex;justify-content:space-between;color:var(--mute);font-size:12px}
"""

CHECK = (
    '<svg width="13" height="13" viewBox="0 0 16 16"><path d="m3 8.5 3.2 3.2L13 4.6" fill="none" '
    'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>'
)

LIVE_CSS = """<style>
body{width:auto;min-width:1200px}
tr.hit td,tr.hit{animation:hit 2.4s ease-out}
@keyframes hit{0%{background:#fff4d6}100%{background:transparent}}
@media (prefers-reduced-motion:reduce){tr.hit td,tr.hit{animation:none}}
</style>"""
LIVE_JS = """<script>
(async function poll(){
  try{
    const r=await fetch('/body',{cache:'no-store'});
    if(r.ok){const t=await r.text();
      if(t!==window.__last){
        const before={};document.querySelectorAll('tr[data-k]').forEach(e=>before[e.dataset.k]=e.innerHTML);
        const first=window.__last===undefined;window.__last=t;document.body.innerHTML=t;
        if(!first)document.querySelectorAll('tr[data-k]').forEach(e=>{if(before[e.dataset.k]!==e.innerHTML)e.classList.add('hit')});}}
  }catch(e){}
  setTimeout(poll,__INTERVAL__);
})();
</script>"""


def load(name: str) -> dict:
    return json.loads((REPORTS / name).read_text(encoding="utf-8"))


def esc(value: object) -> str:
    return html.escape(str(value))


def duration(job: dict) -> str:
    if not job.get("latestJobStartUtc") or not job.get("latestJobEndUtc"):
        return ""
    parse = lambda s: datetime.fromisoformat(s.rstrip("Z")[:26])  # noqa: E731
    secs = (parse(job["latestJobEndUtc"]) - parse(job["latestJobStartUtc"])).total_seconds()
    return f"{secs:.0f} s"


def latest_report_time() -> datetime:
    stamps = [(REPORTS / n).stat().st_mtime for n in REPORT_FILES if (REPORTS / n).exists()]
    return datetime.fromtimestamp(max(stamps), timezone.utc) if stamps else datetime.now(timezone.utc)


def is_unchanged(action: str) -> bool:
    return action == "no-op" or action.startswith("present")


def count_actions(report: dict) -> tuple[int, int]:
    """Return (unchanged, changed) over every action in a report."""
    unchanged = changed = 0

    def walk(node: object) -> None:
        nonlocal unchanged, changed
        if isinstance(node, dict):
            if "action" in node:
                if is_unchanged(str(node["action"])):
                    unchanged += 1
                else:
                    changed += 1
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(report)
    return unchanged, changed


def cell(action: str | None, ok_text: str = "Unchanged") -> str:
    if action is None:
        return '<span class="cell na">Not in scope</span>'
    if is_unchanged(action):
        return f'<span class="cell">{CHECK}{esc(ok_text)}</span>'
    return f'<span class="cell change">{CHECK}{esc(action.capitalize())}</span>'


def topbar(live: bool, stamp: str = "") -> str:
    end = ""
    if live:
        end += '<span class="livedot"><i></i>Live</span>'
    if stamp:
        end += f"<span>Reports updated {stamp}</span>"
    return (
        '<div class="top"><span class="name">FabricOps Copilot</span>'
        f'<span class="scope">northwind-health / care-operations</span><div class="end">{end}</div></div>'
    )


def waiting_page(live: bool) -> str:
    rows = "".join(
        f'<tr><td class="mono">{n}</td><td class="r">'
        + (f'<span class="state"><i></i>Received</span>' if (REPORTS / n).exists() else '<span class="state none"><i></i>Waiting</span>')
        + "</td></tr>"
        for n in REPORT_FILES
    )
    return f"""<html><head><meta charset="utf-8"><style>{CSS}</style></head><body>
{topbar(live)}
<div class="page"><h1>Waiting for the first reports</h1>
<p class="lead">Run the demo commands with <code>--output {esc(REPORTS)}</code>. This page fills in when all five reports exist.</p>
<table style="max-width:520px;margin-top:22px"><tr><th>Report</th><th class="r">State</th></tr>{rows}</table></div></body></html>"""


def build(live: bool = False) -> str:
    if not all((REPORTS / n).exists() for n in REPORT_FILES):
        return waiting_page(live)
    prov, dep = load("live-provision.json"), load("live-deploy.json")
    op, gov, acc = load("live-operate.json"), load("live-govern.json"), load("live-accelerate.json")
    stamp = latest_report_time().strftime("%H:%M:%S UTC")

    envs = {e["environment"]: e for e in prov["environments"]}
    dep_env = {e["environment"]: e for e in dep["environments"]}
    gov_env = {e["environment"]: e for e in gov["environments"]}
    counts = {n: count_actions(r) for n, r in [("provision", prov), ("deploy", dep), ("accelerate", acc)]}
    total = sum(a + b for a, b in counts.values())
    changed = sum(b for _, b in counts.values())
    drift = gov["driftCount"]
    healthy = sum(1 for i in op["items"] if i["health"] == "healthy")
    unknown = len(op["items"]) - healthy
    starter = sum(len(e["actions"]) for e in dep["environments"])
    roles = sum(e["roleAssignments"]["actual"] for e in gov["environments"])
    items_total = starter + len(acc["realTimeIntelligence"])
    rows_total = sum(acc["dataset"]["tableRowCounts"].values())

    headline = "The rerun changed nothing" if changed == 0 else f"The rerun changed {changed} of {total} resources"
    lead = (
        f"{total - changed} of {total} resources across dev, test and prod already matched the configuration. "
        f"That covers {len(envs)} workspaces, {items_total} Fabric items and {roles} role assignments. "
        f"{'No drift was found.' if drift == 0 else f'{drift} drift findings need review.'}"
    )

    def cmd_row(cmd: str, result: str) -> str:
        return f'<tr><td class="mono">{cmd}</td><td>{result}</td></tr>'

    cmds = "".join([
        cmd_row("provision-live", f'{counts["provision"][0]} unchanged, {counts["provision"][1]} changed'),
        cmd_row("deploy-live", f'{counts["deploy"][0]} unchanged, {counts["deploy"][1]} changed'),
        cmd_row("accelerate-live", f'{counts["accelerate"][0]} unchanged, {counts["accelerate"][1]} changed'),
        cmd_row("operate-live", f"{healthy} healthy, {unknown} unknown"),
        cmd_row("govern-live", f"{drift} drift findings"),
    ])

    def act(env: str, resource: str) -> str | None:
        for a in envs[env]["actions"]:
            if a["resource"] == resource:
                return a["action"]
        return None

    def item_act(env: str, typ: str) -> str | None:
        for a in dep_env[env]["actions"]:
            if a["type"] == typ:
                return a["action"]
        return None

    def row(key: str, label: str, cells: list[str], sub: str = "") -> str:
        s = f"<small>{esc(sub)}</small>" if sub else ""
        return f'<tr data-k="{key}"><td class="k">{esc(label)}{s}</td>' + "".join(f"<td>{c}</td>" for c in cells) + "</tr>"

    head = "".join(
        f'<th class="env">{e}<span>{esc(envs[e]["workspaceName"])}</span></th>' for e in ENVS
    )
    g = lambda title: f'<tr class="g"><td colspan="4">{title}</td></tr>'  # noqa: E731
    rows = g("Workspace")
    rows += row(
        "ws", "Workspace exists",
        [cell(act(e, "workspace")) + f'<span class="hash">{esc(gov_env[e]["workspaceIdHash"])}</span>' for e in ENVS],
        "Id shown as a hash",
    )
    rows += row(
        "cap", "Capacity assignment",
        [cell("no-op" if gov_env[e]["capacityMatches"] else "drifted", "Matches") for e in ENVS],
    )
    for role in ("Admin", "Contributor", "Viewer"):
        rows += row(f"role-{role}", f"{role} group", [cell(act(e, f"role/{role}"), "In place") for e in ENVS])
    rows += row(
        "devref", "References to dev",
        [cell("no-op" if gov_env[e]["devReferences"] == 0 else f'{gov_env[e]["devReferences"]} found', "None") for e in ENVS],
    )
    rows += g("Starter items")
    for a in dep["environments"][0]["actions"]:
        rows += row(f"item-{a['type']}", a["item"], [cell(item_act(e, a["type"])) for e in ENVS], a["type"])
    rows += g("Real-time intelligence")
    for r in acc["realTimeIntelligence"]:
        rows += row(
            f"rti-{r['type']}", r["item"],
            [cell(r["action"], "Present")] + [cell(None)] * 2,
            r["type"],
        )

    jobs = ""
    for i in op["items"]:
        ok = i["health"] == "healthy"
        last = (i["latestJobStatus"] or "No runs").lower()
        took = duration(i)
        jobs += (
            f'<tr data-k="job-{esc(i["name"])}"><td class="w"><span class="nm">{esc(i["name"])}</span>'
            f'<span class="sub">{esc(i["owner"])}</span></td>'
            f'<td><span class="state{"" if ok else " none"}"><i></i>{esc(i["health"].capitalize())}</span></td>'
            f'<td class="r">{esc(last)}{", " + took if took else ""}</td></tr>'
        )

    tc = acc["dataset"]["tableRowCounts"]
    top = max(tc.values())
    bars = "".join(
        f'<tr data-k="tbl-{esc(k)}"><td>{esc(k)}</td><td class="bw"><span class="bar" style="width:{max(1.0, v * 100 / top):.1f}%"></span></td>'
        f'<td class="r">{v:,}</td></tr>'
        for k, v in sorted(tc.items(), key=lambda kv: -kv[1])
    )
    uploads = "".join(
        f'<tr data-k="up-{esc(r["table"])}"><td class="mono">{esc(r["table"])}.csv</td><td class="r">{r["bytes"] / 1024:,.0f} KB</td>'
        f'<td class="r mono">{esc(r["sha256"])}</td></tr>'
        for r in acc["syntheaUpload"]
    )

    return f"""<html><head><meta charset="utf-8"><style>{CSS}</style></head><body>
{topbar(live, stamp)}
<div class="page">
<div class="layout">
<div>
<h1>{headline}</h1><p class="lead" style="margin-bottom:30px">{esc(lead)}</p>
<section><div class="sechead"><h2>Desired and actual state</h2><code>provision-live, deploy-live, govern-live</code></div>
<table class="grid"><tr><th>Resource</th>{head}</tr>{rows}</table>
<p class="note">Production waits for a reviewer before any change is applied. Remediation is report only, and the owner principal is allow-listed.</p></section>
</div>
<div>
<section><div class="sechead"><h2>Commands run</h2><code>--config project.yml</code></div>
<table class="cmds"><tr><th>Command</th><th>Result</th></tr>{cmds}</table></section>
<section><div class="sechead"><h2>Scheduled jobs</h2><code>operate-live</code></div>
<table><tr><th>Job</th><th>Health</th><th class="r">Last run</th></tr>{jobs}</table>
<p class="note">Retries are denied unless a job is declared retryable with an attempt limit. A job with no matching item stays unknown.</p></section>
<section><div class="sechead"><h2>Synthea rows by table</h2><code>{rows_total:,} total</code></div>
<table>{bars}</table>
<p class="note">Seeded synthetic patients. Only counts and the dataset hash {esc(acc["dataset"]["datasetHash"])} leave the sandbox.</p></section>
<section><div class="sechead"><h2>Files in the dev Lakehouse</h2><code>Files/synthea</code></div>
<table><tr><th>File</th><th class="r">Size</th><th class="r">SHA-256</th></tr>{uploads}</table>
<p class="note">All three files already matched on rerun, so nothing was uploaded again.</p></section>
</div></div>

<div class="foot"><span>Built from sanitized live reports. Workspace and item identifiers are hashed.</span><span>github.com/samueltauil/fabricops-copilot</span></div>
</div></body></html>"""


def screenshot() -> None:
    from playwright.sync_api import sync_playwright

    OUT.mkdir(parents=True, exist_ok=True)
    page_html = build()
    Path("artifacts").mkdir(exist_ok=True)
    Path("artifacts/dashboard.html").write_text(page_html, encoding="utf-8")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="msedge")
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=2)
        page.set_content(page_html)
        page.screenshot(path=str(OUT / "dashboard.png"), full_page=True)
        browser.close()


def live_shell(page_html: str) -> str:
    js = LIVE_JS.replace("__INTERVAL__", str(ARGS.interval * 1000))
    return page_html.replace("</head>", LIVE_CSS + "</head>", 1).replace("</body>", js + "</body>", 1)


class Handler(BaseHTTPRequestHandler):
    def _send(self, body: str, code: int = 200) -> None:
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/body":
            page_html = build(live=True)
            inner = page_html.split("<body>", 1)[1].rsplit("</body>", 1)[0]
            self._send(inner)
        elif self.path in ("/", "/index.html"):
            self._send(live_shell(build(live=True)))
        else:
            self._send("not found", 404)

    def log_message(self, *_: object) -> None:
        pass


def serve() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", ARGS.port), Handler)
    print(f"Live dashboard on http://127.0.0.1:{ARGS.port}  (reading {REPORTS}, refresh {ARGS.interval}s). Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


def main() -> None:
    serve() if ARGS.serve else screenshot()


if __name__ == "__main__":
    main()
