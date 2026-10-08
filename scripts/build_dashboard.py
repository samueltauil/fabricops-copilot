"""Build the FabricOps run ledger from the live reports.

Reads the sanitized JSON reports written by the *-live commands (hashed IDs only) and
renders an HTML ledger. By default it captures a PNG with a headless browser; with
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

CSS = """
:root{
  --paper:#f3f0e8;--ink:#1b1d22;--ink2:#4a4d55;--dim:#807b6f;--rule:#d9d4c7;
  --accent:#b8431a;--ok:#2e6b43;--term:#15181d;
  --head:'Bahnschrift SemiCondensed','Bahnschrift','Arial Narrow',sans-serif;
  --serif:Georgia,'Times New Roman',serif;
  --mono:'Cascadia Mono','Consolas',monospace;
  --body:'Segoe UI Variable Text','Segoe UI',system-ui,sans-serif;
}
*{box-sizing:border-box}
body{margin:0;width:1440px;background:var(--paper);color:var(--ink);font:13px/1.45 var(--body);
  -webkit-font-smoothing:antialiased;font-variant-numeric:tabular-nums}
.mast{background:var(--ink);color:#e9e5da;height:40px;display:flex;align-items:center;padding:0 48px;gap:18px;font:12px var(--mono)}
.mast .wm{font:600 15px var(--head);letter-spacing:.16em;color:#fff}
.mast .path{color:#9a968a}
.mast .sp{margin-left:auto;display:flex;gap:22px;align-items:center;color:#b9b5a8}
.livechip{display:inline-flex;align-items:center;gap:7px;color:#f08a5d;letter-spacing:.08em}
.livechip i{width:7px;height:7px;border-radius:50%;background:#f08a5d;display:block}
.page{padding:36px 48px 30px}
.hero{display:grid;grid-template-columns:minmax(0,1fr) 600px;gap:56px;align-items:end;padding-bottom:30px}
.eyebrow{font:600 11px var(--head);letter-spacing:.18em;text-transform:uppercase;color:var(--accent);margin-bottom:12px}
.lede{font:400 31px/1.28 var(--serif);letter-spacing:-.4px;margin:0;color:var(--ink)}
.lede b{font-weight:700;border-bottom:2px solid var(--accent);padding-bottom:0}
.lede2{margin-top:14px;color:var(--ink2);font-size:14px;max-width:640px}
.term{background:var(--term);color:#d8d4c8;border-radius:2px;padding:14px 18px 16px;font:12px/1.9 var(--mono)}
.term .t{color:#6f7480;margin-bottom:4px}
.term .r{display:grid;grid-template-columns:150px 1fr auto;gap:14px;white-space:nowrap}
.term .c{color:#8b909b}.term .g{color:#6fbf8a}.term .a{color:#f08a5d}.term .w{color:#fff}
.sec{border-top:2px solid var(--ink);padding-top:10px;margin-bottom:34px}
.sh{display:flex;align-items:baseline;gap:12px;margin-bottom:6px}
.sh .no{font:600 12px var(--mono);color:var(--accent)}
.sh h2{margin:0;font:600 15px var(--head);letter-spacing:.1em;text-transform:uppercase}
.sh code{margin-left:auto;font:11px var(--mono);color:var(--dim)}
.cols{display:grid;grid-template-columns:minmax(0,1.18fr) minmax(0,1fr);gap:56px;align-items:start}
table{width:100%;border-collapse:collapse}
th{font:600 10.5px var(--head);letter-spacing:.12em;text-transform:uppercase;color:var(--dim);text-align:left;
  padding:6px 12px 6px 0;border-bottom:1px solid var(--ink)}
td{padding:9px 12px 9px 0;border-bottom:1px solid var(--rule);vertical-align:baseline;white-space:nowrap}
tr:last-child td{border-bottom:0}
th.r,td.r{text-align:right;padding-right:0}
td.w{white-space:normal}
.nm{font-weight:600;letter-spacing:-.1px}
.mono{font:11.5px var(--mono);color:var(--ink2)}
.dim{color:var(--dim)}
.sub2{display:block;color:var(--dim);font-size:12px;font-weight:400}
.st{display:inline-flex;align-items:center;gap:7px;font:600 10.5px var(--mono);letter-spacing:.08em;text-transform:uppercase;color:var(--ok)}
.st i,.sq{display:inline-block;width:8px;height:8px;background:var(--ok);flex:none}
.st.idle{color:var(--dim)}.st.idle i{background:none;border:1.5px solid var(--dim)}
.sq{vertical-align:0}
.route{display:flex;align-items:center;gap:10px;font:12px var(--mono);margin:8px 0 10px;color:var(--ink2)}
.route b{color:var(--ink);border:1px solid var(--ink);padding:1px 8px;font-weight:600}
.route span.gate{margin-left:auto;font-family:var(--serif);font-style:italic;color:var(--dim);font-size:12.5px}
.margin{margin:10px 0 0;font:italic 12.5px/1.5 var(--serif);color:var(--dim);max-width:560px}
.bar{display:block;height:4px;background:var(--ink)}
td.bw{width:42%;padding-right:18px;vertical-align:middle}
.foot{border-top:1px solid var(--ink);padding-top:9px;display:flex;justify-content:space-between;font:11px var(--mono);color:var(--dim)}
"""

LIVE_CHIP = '<span class="livechip"><i></i>LIVE</span>'
LIVE_CSS = """<style>
body{width:auto;min-width:1200px}
.livechip i{animation:blink 1.6s steps(2,start) infinite}
@keyframes blink{50%{opacity:.25}}
.sec.flash{animation:flash 1.6s ease-out}
@keyframes flash{0%{background:#f0dccf}100%{background:transparent}}
</style>"""
LIVE_JS = """<script>
(async function poll(){
  try{
    const r=await fetch('/body',{cache:'no-store'});
    if(r.ok){const t=await r.text();
      if(t!==window.__last){const first=window.__last===undefined;window.__last=t;
        document.body.innerHTML=t;
        if(!first)document.querySelectorAll('.sec').forEach(p=>p.classList.add('flash'));}}
  }catch(e){}
  setTimeout(poll,__INTERVAL__);
})();
</script>"""


def load(name: str) -> dict:
    return json.loads((REPORTS / name).read_text(encoding="utf-8"))


def esc(value: object) -> str:
    return html.escape(str(value))


def status(text: str, kind: str = "") -> str:
    return f'<span class="st {kind}"><i></i>{esc(text)}</span>'


def duration(job: dict) -> str:
    if not job.get("latestJobStartUtc") or not job.get("latestJobEndUtc"):
        return "-"
    parse = lambda s: datetime.fromisoformat(s.rstrip("Z")[:26])  # noqa: E731
    secs = (parse(job["latestJobEndUtc"]) - parse(job["latestJobStartUtc"])).total_seconds()
    return f"{secs:.0f} s"


def latest_report_time() -> datetime:
    stamps = [(REPORTS / n).stat().st_mtime for n in REPORT_FILES if (REPORTS / n).exists()]
    return datetime.fromtimestamp(max(stamps), timezone.utc) if stamps else datetime.now(timezone.utc)


def count_actions(report: dict) -> tuple[int, int]:
    """Return (unchanged, changed) over every action in a report."""
    unchanged = changed = 0

    def walk(node: object) -> None:
        nonlocal unchanged, changed
        if isinstance(node, dict):
            if "action" in node:
                if node["action"] == "no-op" or str(node["action"]).startswith("present"):
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


def masthead(live: bool, stamp: str = "") -> str:
    right = (LIVE_CHIP if live else "") + (f"<span>reconciled {stamp}</span>" if stamp else "")
    return (
        '<div class="mast"><span class="wm">FABRICOPS</span>'
        '<span class="path">northwind-health / care-operations</span>'
        f'<div class="sp"><span>SANDBOX</span>{right}</div></div>'
    )


def waiting_page(live: bool) -> str:
    rows = "".join(
        f'<tr><td class="mono">{n}</td><td class="r">'
        + (status("Received") if (REPORTS / n).exists() else status("Waiting", "idle"))
        + "</td></tr>"
        for n in REPORT_FILES
    )
    return f"""<html><head><meta charset="utf-8"><style>{CSS}</style></head><body>
{masthead(live)}
<div class="page"><div class="eyebrow">Run ledger</div>
<p class="lede">Waiting for the first reports.</p>
<p class="lede2">Run the demo commands with <code>--output {esc(REPORTS)}</code>. The ledger fills in when all five reports exist.</p>
<div class="sec" style="margin-top:28px;max-width:560px"><table><tr><th>Report</th><th class="r">State</th></tr>{rows}</table></div></div></body></html>"""


def build(live: bool = False) -> str:
    if not all((REPORTS / n).exists() for n in REPORT_FILES):
        return waiting_page(live)
    prov, dep = load("live-provision.json"), load("live-deploy.json")
    op, gov, acc = load("live-operate.json"), load("live-govern.json"), load("live-accelerate.json")
    stamp = latest_report_time().strftime("%Y-%m-%d %H:%M:%SZ")

    starter = sum(len(e["actions"]) for e in dep["environments"])
    rti_n = len(acc["realTimeIntelligence"])
    roles = sum(e["roleAssignments"]["actual"] for e in gov["environments"])
    rows_total = sum(acc["dataset"]["tableRowCounts"].values())
    gov_by_env = {e["environment"]: e for e in gov["environments"]}
    counts = {n: count_actions(r) for n, r in [("provision", prov), ("deploy", dep), ("accelerate", acc)]}
    total = sum(a + b for a, b in counts.values())
    changed = sum(b for _, b in counts.values())
    drift = gov["driftCount"]
    healthy = sum(1 for i in op["items"] if i["health"] == "healthy")
    unknown = len(op["items"]) - healthy

    def plan_row(cmd: str, detail: str, verdict: str, ok: bool = True) -> str:
        cls = "g" if ok else "a"
        return f'<div class="r"><span class="w">{cmd}</span><span class="c">{detail}</span><span class="{cls}">{verdict}</span></div>'

    plan = "".join([
        plan_row("provision-live", f'{counts["provision"][0]} unchanged, {counts["provision"][1]} to change', "no-op" if not counts["provision"][1] else "changed", not counts["provision"][1]),
        plan_row("deploy-live", f'{counts["deploy"][0]} unchanged, {counts["deploy"][1]} to change', "no-op" if not counts["deploy"][1] else "changed", not counts["deploy"][1]),
        plan_row("accelerate-live", f'{counts["accelerate"][0]} unchanged, {counts["accelerate"][1]} to change', "no-op" if not counts["accelerate"][1] else "changed", not counts["accelerate"][1]),
        plan_row("operate-live", f"{healthy} healthy, {unknown} unknown", "read-only", unknown == 0),
        plan_row("govern-live", f"{drift} drift findings", "clean" if drift == 0 else "drift", drift == 0),
    ])

    env_rows = ""
    for e in prov["environments"]:
        g = gov_by_env[e["environment"]]
        ra, si = g["roleAssignments"], g["starterItems"]
        env_rows += (
            f'<tr><td class="nm">{esc(e["workspaceName"])}</td>'
            f'<td><span class="sq"></span></td>'
            f'<td>{ra["desired"] - ra["missing"]}/{ra["desired"]}</td>'
            f'<td>{si["expected"] - si["missing"]}/{si["expected"]}</td>'
            f'<td>{g["devReferences"]}</td><td class="mono">{esc(g["workspaceIdHash"])}</td>'
            f'<td class="r">{status("In sync")}</td></tr>'
        )

    types = [a["type"] for a in dep["environments"][0]["actions"]]
    mat_rows = ""
    for t in types:
        cells = "".join(
            '<td class="r"><span class="sq"></span></td>'
            if any(a["type"] == t and a["action"] == "no-op" for a in e["actions"])
            else '<td class="r dim">-</td>'
            for e in dep["environments"]
        )
        name = next(a["item"] for a in dep["environments"][0]["actions"] if a["type"] == t)
        mat_rows += f'<tr><td class="nm">{esc(name)}</td><td class="mono">{esc(t)}</td>{cells}</tr>'

    jobs = ""
    for i in op["items"]:
        ok = i["health"] == "healthy"
        jobs += (
            f'<tr><td class="w"><span class="nm">{esc(i["name"])}</span><span class="sub2">{esc(i["owner"])}</span></td>'
            f'<td>{status(i["health"], "" if ok else "idle")}</td>'
            f'<td>{esc((i["latestJobStatus"] or "no runs").lower())}</td><td class="r">{duration(i)}</td></tr>'
        )

    rti = "".join(
        f'<tr><td class="nm">{esc(r["item"])}</td><td class="mono">{esc(r["type"])}</td>'
        f'<td class="r">{status("Present")}</td></tr>'
        for r in acc["realTimeIntelligence"]
    )

    table_counts = acc["dataset"]["tableRowCounts"]
    top = max(table_counts.values())
    bars = "".join(
        f'<tr><td>{esc(k)}</td><td class="bw"><span class="bar" style="width:{max(1.0, v * 100 / top):.1f}%"></span></td>'
        f'<td class="r mono" style="color:var(--ink)">{v:,}</td></tr>'
        for k, v in sorted(table_counts.items(), key=lambda kv: -kv[1])
    )
    uploads = "".join(
        f'<tr><td class="mono" style="color:var(--ink)">{esc(r["table"])}.csv</td><td class="r mono">{r["bytes"] / 1024:,.0f} KB</td>'
        f'<td class="mono dim" style="padding-left:28px">{esc(r["sha256"])}</td><td class="r">{status("Uploaded")}</td></tr>'
        for r in acc["syntheaUpload"]
    )

    return f"""<html><head><meta charset="utf-8"><style>{CSS}</style></head><body>
{masthead(live, stamp)}
<div class="page">
<div class="hero"><div>
<div class="eyebrow">Run ledger &middot; {"all checks passing" if drift == 0 else "drift detected"}</div>
<p class="lede"><b>{len(prov["environments"])}</b> workspaces, <b>{starter + rti_n}</b> Fabric items and <b>{roles}</b> role assignments match the configuration. A full rerun changed <b>{changed}</b> of {total} resources.</p>
<div class="lede2">Everything below was created and verified by the FabricOps commands against a real Fabric capacity, seeded with {rows_total:,} rows of Synthea synthetic patient data.</div>
</div>
<div class="term"><div class="t">$ fabricops &lt;command&gt;-live --config project.yml</div>{plan}</div></div>

<div class="cols">
<div>
<div class="sec"><div class="sh"><span class="no">01</span><h2>Provision &amp; Govern</h2><code>provision-live &middot; govern-live</code></div>
<table><tr><th>Workspace</th><th>Capacity</th><th>Roles</th><th>Items</th><th>Dev refs</th><th>Id (hash)</th><th class="r">State</th></tr>{env_rows}</table>
<p class="margin">Desired and actual state are compared for capacity, roles and items. Remediation is report-only and the owner principal is allow-listed.</p></div>
<div class="sec"><div class="sh"><span class="no">02</span><h2>Deploy</h2><code>deploy-live</code></div>
<div class="route"><b>dev</b>&rarr;<b>test</b>&rarr;<b>prod</b><span class="gate">production waits for a reviewer</span></div>
<table><tr><th>Item</th><th>Type</th><th class="r">dev</th><th class="r" style="width:54px">test</th><th class="r" style="width:54px">prod</th></tr>{mat_rows}</table>
<p class="margin">On rerun every item is a no-op, so no duplicates are created.</p></div>
</div>
<div>
<div class="sec"><div class="sh"><span class="no">03</span><h2>Operate</h2><code>operate-live</code></div>
<table><tr><th>Monitored job</th><th>Health</th><th>Last run</th><th class="r">Took</th></tr>{jobs}</table>
<p class="margin">Retries are denied unless a job is declared retryable with an attempt limit. A job with no matching item stays unknown.</p></div>
<div class="sec"><div class="sh"><span class="no">04</span><h2>Real-Time Intelligence</h2><code>accelerate-live</code></div>
<table><tr><th>Item</th><th>Type</th><th class="r">State</th></tr>{rti}</table>
<p class="margin">Dev workspace. Fabric IQ, ontology and agent templates are capability probes against preview APIs.</p></div>
</div></div>

<div class="cols">
<div class="sec"><div class="sh"><span class="no">05</span><h2>Synthea dataset</h2><code>sha {esc(acc["dataset"]["datasetHash"])}</code></div>
<table><tr><th>Table</th><th>Rows, to scale</th><th class="r">Count</th></tr>{bars}</table>
<p class="margin">Seeded synthetic patients. Only counts and a hash leave the sandbox.</p></div>
<div class="sec"><div class="sh"><span class="no">06</span><h2>Lakehouse upload</h2><code>Files/synthea</code></div>
<table><tr><th>File</th><th class="r">Size</th><th style="padding-left:28px">SHA-256</th><th class="r">State</th></tr>{uploads}</table>
<p class="margin">Dev workspace Lakehouse. A rerun leaves identical files untouched.</p></div>
</div>

<div class="foot"><span>Generated from sanitized live reports. Workspace and item identifiers are hashed.</span><span>github.com/samueltauil/fabricops-copilot</span></div>
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
