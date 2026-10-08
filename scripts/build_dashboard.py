"""Build a dashboard from the live FabricOps reports and screenshot it.

Reads the sanitized JSON reports written by the *-live commands (hashed IDs only),
renders an HTML console view, and either captures a PNG with a headless browser
(default) or serves it live with --serve so it updates while the demo runs.

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
  --bg:#f5f6f8;--panel:#fff;--line:#e3e6ea;--line2:#eef0f3;--ink:#1a1f26;--ink2:#4b5563;--mute:#7b8594;
  --accent:#0b6e5f;--accent-bg:#e6f2ef;--ok:#17803d;--warn:#b45309;--bad:#b42318;
  --mono:'Cascadia Mono','Consolas',monospace;
}
*{box-sizing:border-box}
body{margin:0;width:1440px;background:var(--bg);color:var(--ink);font:13px/1.45 'Segoe UI Variable Text','Segoe UI',system-ui,sans-serif;
  -webkit-font-smoothing:antialiased;font-variant-numeric:tabular-nums}
.bar{height:52px;background:#fff;border-bottom:1px solid var(--line);display:flex;align-items:center;padding:0 32px;gap:28px}
.brand{display:flex;align-items:center;gap:10px;font-weight:600;font-size:14px;letter-spacing:-.1px}
.brand svg{display:block}
.nav{display:flex;gap:2px;height:100%;margin-left:8px}
.nav a{display:flex;align-items:center;gap:8px;padding:0 14px;color:var(--ink2);font-size:13px;border-bottom:2px solid transparent;margin-bottom:-1px}
.nav a.on{color:var(--ink);font-weight:600;border-bottom-color:var(--accent)}
.nav i{width:6px;height:6px;border-radius:50%;background:var(--ok);display:block}
.right{margin-left:auto;display:flex;align-items:center;gap:18px;color:var(--mute);font-size:12px}
.env{display:inline-flex;align-items:center;gap:6px;border:1px solid var(--line);border-radius:4px;padding:3px 9px;color:var(--ink2);font-size:12px;background:#fafbfc}
.page{padding:24px 32px 28px}
.crumb{color:var(--mute);font-size:12px;margin-bottom:6px}
.titlerow{display:flex;align-items:flex-end;justify-content:space-between;margin-bottom:18px}
h1{margin:0;font-size:22px;font-weight:600;letter-spacing:-.3px}
.sub{color:var(--ink2);margin-top:3px}
.status{display:flex;align-items:center;gap:8px;font-size:13px;color:var(--ok);font-weight:600}
.status i{width:8px;height:8px;border-radius:50%;background:var(--ok);display:block;box-shadow:0 0 0 3px #17803d22}
.kpis{display:grid;grid-template-columns:repeat(5,1fr);background:var(--panel);border:1px solid var(--line);border-radius:6px;margin-bottom:16px}
.kpi{padding:14px 18px 15px;border-right:1px solid var(--line2)}.kpi:last-child{border:0}
.kpi .l{color:var(--mute);font-size:12px}
.kpi .n{font-size:28px;font-weight:600;letter-spacing:-.6px;margin:2px 0 1px;line-height:1.15}
.kpi .d{color:var(--mute);font-size:12px}
.cols{display:grid;grid-template-columns:minmax(0,1.2fr) minmax(0,1fr);gap:16px;margin-bottom:16px;align-items:start}
.stack{display:flex;flex-direction:column;gap:16px}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:6px;overflow:hidden}
.ph{display:flex;align-items:center;gap:10px;padding:12px 18px;border-bottom:1px solid var(--line)}
.ph h2{margin:0;font-size:14px;font-weight:600}
.ph .k{font-size:11px;font-weight:600;color:var(--accent);background:var(--accent-bg);border-radius:3px;padding:1px 6px;letter-spacing:.2px}
.ph code{margin-left:auto;font:11.5px var(--mono);color:var(--mute)}
table{width:100%;border-collapse:collapse}
th{white-space:nowrap;font-weight:500;color:var(--mute);font-size:12px;text-align:left;padding:8px 18px;background:#fafbfc;border-bottom:1px solid var(--line)}
td{white-space:nowrap;padding:10px 18px;border-bottom:1px solid var(--line2);vertical-align:middle}
tr:last-child td{border-bottom:0}
th.r,td.r{text-align:right}td.w{white-space:normal}
th,td{padding-left:14px;padding-right:14px}th:first-child,td:first-child{padding-left:18px}th:last-child,td:last-child{padding-right:18px}
.mono{font-family:var(--mono);font-size:12px;color:var(--ink2)}
.dim{color:var(--mute)}
.st{display:inline-flex;align-items:center;gap:7px;white-space:nowrap}
.st i{width:8px;height:8px;border-radius:50%;display:block;background:var(--ok)}
.st.warn i{background:#d97706}.st.idle i{background:#fff;border:1.5px solid #9aa3af}
.ic{display:inline-flex;align-items:center;gap:9px;font-weight:500}
.ic svg{flex:none}
.ck{color:var(--ok);display:inline-block;vertical-align:-2px}
.note{padding:10px 18px;border-top:1px solid var(--line);background:#fafbfc;color:var(--mute);font-size:12px}
.flow{display:flex;align-items:center;gap:0;padding:16px 18px 6px}
.node{border:1px solid var(--line);border-radius:4px;padding:6px 14px;font-weight:600;font-size:12.5px;background:#fff}
.node.cur{border-color:var(--accent);color:var(--accent);background:var(--accent-bg)}
.arrow{flex:none;width:34px;height:1px;background:#b6bdc7;position:relative}
.arrow:after{content:"";position:absolute;right:0;top:-3px;width:6px;height:6px;border-top:1px solid #b6bdc7;border-right:1px solid #b6bdc7;transform:rotate(45deg)}
.gate{margin-left:auto;color:var(--mute);font-size:12px;display:flex;align-items:center;gap:6px}
.hb{display:flex;align-items:center;gap:12px}
.hb .t{width:92px;color:var(--ink2)}
.track{display:block;flex:1;height:8px;background:var(--line2);border-radius:2px;overflow:hidden}
.track i{display:block;height:100%;background:var(--accent);border-radius:2px}
.hb .v{width:62px;text-align:right}
.foot{display:flex;justify-content:space-between;color:var(--mute);font-size:12px;padding:2px 2px 0}.cols+.foot{margin-top:16px}
"""

ICONS = {
    "Lakehouse": ("#0f6cbd", '<path d="M3 8.5 8 4l5 4.5V13H3z" fill="none" stroke="#fff" stroke-width="1.3" stroke-linejoin="round"/>'),
    "Notebook": ("#5b6b7c", '<path d="M5 3.5h6v9H5zM7 6.5h2M7 9h2" fill="none" stroke="#fff" stroke-width="1.3" stroke-linecap="round"/>'),
    "DataPipeline": ("#107c41", '<path d="M3.5 5.5h3v5h-3zM9.5 5.5h3v5h-3zM6.5 8h3" fill="none" stroke="#fff" stroke-width="1.3" stroke-linejoin="round"/>'),
    "Eventhouse": ("#0f6cbd", '<path d="M3 13V8l5-4 5 4v5M6.5 13V9.5h3V13" fill="none" stroke="#fff" stroke-width="1.3" stroke-linejoin="round"/>'),
    "KQLDatabase": ("#3a7bd5", '<ellipse cx="8" cy="5" rx="4" ry="1.7" fill="none" stroke="#fff" stroke-width="1.3"/><path d="M4 5v6c0 .9 1.8 1.7 4 1.7s4-.8 4-1.7V5" fill="none" stroke="#fff" stroke-width="1.3"/>'),
    "Eventstream": ("#c239b3", '<path d="M2.5 8c1.2-3 2.3-3 3.5 0s2.3 3 3.5 0 2.3-3 4 0" fill="none" stroke="#fff" stroke-width="1.3" stroke-linecap="round"/>'),
}
CHECK = '<svg class="ck" width="14" height="14" viewBox="0 0 16 16"><path d="m3.5 8.5 3 3 6-7" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>'
LOGO = (
    '<svg width="24" height="24" viewBox="0 0 24 24"><rect width="24" height="24" rx="5" fill="#0b6e5f"/>'
    '<path d="M7 7h10M7 12h7M7 17h4" stroke="#fff" stroke-width="2" stroke-linecap="round"/></svg>'
)
LIVE_CHIP = '<span class="livechip"><i></i>Live</span>'
LIVE_CSS = """<style>
body{width:auto;min-width:1200px}
.livechip{display:inline-flex;align-items:center;gap:6px;font-weight:600;color:var(--ok);font-size:12px}
.livechip i{width:7px;height:7px;border-radius:50%;background:var(--ok);display:block;animation:pulse 1.6s ease-out infinite}
@keyframes pulse{0%{box-shadow:0 0 0 0 #17803d66}100%{box-shadow:0 0 0 8px #17803d00}}
.flash{animation:flash 1.4s ease-out}
@keyframes flash{0%{background:#e6f2ef}100%{background:transparent}}
</style>"""
LIVE_JS = """<script>
(async function poll(){
  try{
    const r=await fetch('/body',{cache:'no-store'});
    if(r.ok){const t=await r.text();
      if(t!==window.__last){const first=window.__last===undefined;window.__last=t;
        document.body.innerHTML=t;
        if(!first)document.querySelectorAll('.panel').forEach(p=>p.classList.add('flash'));}}
  }catch(e){}
  setTimeout(poll,__INTERVAL__);
})();
</script>"""


def load(name: str) -> dict:
    return json.loads((REPORTS / name).read_text(encoding="utf-8"))


def esc(value: object) -> str:
    return html.escape(str(value))


def icon(kind: str) -> str:
    color, glyph = ICONS[kind]
    return (
        f'<svg width="18" height="18" viewBox="0 0 16 16"><rect width="16" height="16" rx="3" fill="{color}"/>{glyph}</svg>'
    )


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


def waiting_page(live: bool) -> str:
    rows = "".join(
        f'<tr><td class="mono">{n}</td><td class="r">'
        + (status("Received", "") if (REPORTS / n).exists() else status("Waiting", "idle"))
        + "</td></tr>"
        for n in REPORT_FILES
    )
    return f"""<html><head><meta charset="utf-8"><style>{CSS}</style></head><body>
<div class="bar"><div class="brand">{LOGO}FabricOps Copilot</div><div class="nav"></div>
<div class="right"><span class="env">Sandbox</span>{LIVE_CHIP if live else ""}</div></div>
<div class="page"><div class="titlerow"><div><h1>Waiting for the first reports</h1>
<div class="sub">Run the demo commands with <code>--output {esc(REPORTS)}</code>. Panels appear when all five reports exist.</div></div></div>
<div class="panel"><table><tr><th>Report</th><th class="r">State</th></tr>{rows}</table></div></div></body></html>"""


def build(live: bool = False) -> str:
    if not all((REPORTS / n).exists() for n in REPORT_FILES):
        return waiting_page(live)
    prov, dep = load("live-provision.json"), load("live-deploy.json")
    op, gov, acc = load("live-operate.json"), load("live-govern.json"), load("live-accelerate.json")
    now = latest_report_time().strftime("%Y-%m-%d %H:%M:%S UTC")
    items = sum(len(e["actions"]) for e in dep["environments"])
    rows_total = sum(acc["dataset"]["tableRowCounts"].values())
    gov_by_env = {e["environment"]: e for e in gov["environments"]}
    clean = gov["driftCount"] == 0

    nav = "".join(
        f'<a class="{"on" if i == 0 else ""}">{n}<i></i></a>'
        for i, n in enumerate(["Provision", "Deploy", "Operate", "Govern", "Accelerate"])
    )

    kpis = "".join(
        f'<div class="kpi"><div class="l">{l}</div><div class="n">{n}</div><div class="d">{d}</div></div>'
        for l, n, d in [
            ("Workspaces", len(prov["environments"]), "dev, test, prod"),
            ("Fabric items", items + len(acc["realTimeIntelligence"]), f"{items} starter, {len(acc['realTimeIntelligence'])} real-time"),
            ("Role assignments", sum(e["roleAssignments"]["actual"] for e in gov["environments"]), "all groups, reconciled"),
            ("Drift findings", gov["driftCount"], "report-only policy"),
            ("Synthetic rows", f"{rows_total:,}", "Synthea, seeded"),
        ]
    )

    env_rows = ""
    for e in prov["environments"]:
        g = gov_by_env[e["environment"]]
        ra, si = g["roleAssignments"], g["starterItems"]
        env_rows += (
            f'<tr><td><b>{esc(e["workspaceName"])}</b></td>'
            f'<td>{CHECK}</td>'
            f'<td>{ra["desired"] - ra["missing"]} of {ra["desired"]}</td>'
            f'<td>{si["expected"] - si["missing"]} of {si["expected"]}</td>'
            f'<td>{g["devReferences"]}</td><td class="mono">{esc(g["workspaceIdHash"])}</td>'
            f'<td>{status("In sync")}</td></tr>'
        )

    types = [a["type"] for a in dep["environments"][0]["actions"]]
    mat_rows = ""
    for t in types:
        cells = "".join(
            f'<td class="r">{CHECK}</td>'
            if any(a["type"] == t and a["action"] == "no-op" for a in e["actions"])
            else '<td class="r dim">-</td>'
            for e in dep["environments"]
        )
        name = next(a["item"] for a in dep["environments"][0]["actions"] if a["type"] == t)
        mat_rows += f'<tr><td><span class="ic">{icon(t)}{esc(name)}</span></td><td class="dim">{esc(t)}</td>{cells}</tr>'

    jobs = ""
    for i in op["items"]:
        ok = i["health"] == "healthy"
        jobs += (
            f'<tr><td class="w"><b>{esc(i["name"])}</b><div class="dim">{esc(i["owner"])}</div></td>'
            f'<td>{status(i["health"].capitalize(), "" if ok else "idle")}</td>'
            f'<td>{esc(i["latestJobStatus"] or "No runs")}</td><td class="r">{duration(i)}</td></tr>'
        )

    rti = "".join(
        f'<tr><td><span class="ic">{icon(r["type"])}{esc(r["item"])}</span></td><td class="dim">{esc(r["type"])}</td>'
        f'<td class="r">{status("Present")}</td></tr>'
        for r in acc["realTimeIntelligence"]
    )

    counts = acc["dataset"]["tableRowCounts"]
    top = max(counts.values())
    uploads = "".join(
        f'<tr><td class="mono">{esc(r["table"])}.csv</td><td class="r">{r["bytes"] / 1024:,.0f} KB</td>'
        f'<td class="mono dim">{esc(r["sha256"])}</td><td class="r">{status("Uploaded")}</td></tr>'
        for r in acc["syntheaUpload"]
    )
    bars = "".join(
        f'<tr><td>{esc(k)}</td><td><span class="track"><i style="width:{max(1.5, v * 100 / top):.1f}%"></i></span></td>'
        f'<td class="r">{v:,}</td>'
        + "</tr>"
        for k, v in sorted(counts.items(), key=lambda kv: -kv[1])
    )
    return f"""<html><head><meta charset="utf-8"><style>{CSS}</style></head><body>
<div class="bar"><div class="brand">{LOGO}FabricOps Copilot</div><div class="nav">{nav}</div>
<div class="right"><span class="env">Sandbox</span>{LIVE_CHIP if live else ""}<span>Last reconciled {now}</span></div></div>
<div class="page">
<div class="crumb">Northwind Health &nbsp;/&nbsp; care-operations</div>
<div class="titlerow"><div><h1>Environment overview</h1>
<div class="sub">Three governed workspaces, starter content, job health and a real-time foundation, all driven by one configuration file.</div></div>
<div class="status"><i></i>{"All checks passing" if clean else "Drift detected"}</div></div>
<div class="kpis">{kpis}</div>
<div class="cols">
<div class="stack">
<div class="panel"><div class="ph"><span class="k">PROVISION</span><span class="k">GOVERN</span><h2>Workspaces</h2><code>provision-live &middot; govern-live</code></div>
<table><tr><th>Workspace</th><th>Capacity</th><th>Roles</th><th>Items</th><th>Dev refs</th><th>Id (hash)</th><th>State</th></tr>{env_rows}</table>
<div class="note">Desired and actual state compared for capacity, roles and items. Remediation is report-only; the owner principal is allow-listed.</div></div>
<div class="panel"><div class="ph"><span class="k">DEPLOY</span><h2>Promotion</h2><code>deploy-live</code></div>
<div class="flow"><span class="node cur">dev</span><span class="arrow"></span><span class="node">test</span><span class="arrow"></span><span class="node">prod</span>
<span class="gate">Production requires reviewer approval</span></div>
<table><tr><th>Item</th><th>Type</th><th class="r">dev</th><th class="r">test</th><th class="r">prod</th></tr>{mat_rows}</table>
<div class="note">Rerun result: every item is a no-op, so no duplicates are created.</div></div>
</div>
<div class="stack">
<div class="panel"><div class="ph"><span class="k">OPERATE</span><h2>Job health</h2><code>operate-live</code></div>
<table><tr><th>Monitored job</th><th>Health</th><th>Last run</th><th class="r">Duration</th></tr>{jobs}</table>
<div class="note">Retries are denied unless a job is declared retryable with an attempt limit. Jobs with no matching item stay unknown.</div></div>
<div class="panel"><div class="ph"><span class="k">ACCELERATE</span><h2>Real-Time Intelligence</h2><code>accelerate-live</code></div>
<table><tr><th>Item</th><th>Type</th><th class="r">State</th></tr>{rti}</table>
<div class="note">Dev workspace. Fabric IQ, ontology and agent templates are capability probes (preview APIs).</div></div>
</div></div>
<div class="cols" style="margin-bottom:0"><div class="panel"><div class="ph"><span class="k">ACCELERATE</span><h2>Synthea dataset</h2><code>dataset {esc(acc["dataset"]["datasetHash"])}</code></div>
<table><tr><th>Table</th><th style="width:36%">Share of rows</th><th class="r">Rows</th></tr>{bars}</table>
<div class="note">Seeded synthetic patients. Only counts and a hash are reported.</div></div>
<div class="panel"><div class="ph"><span class="k">ACCELERATE</span><h2>Lakehouse upload</h2><code>Files/synthea</code></div>
<table><tr><th>File</th><th class="r">Size</th><th>SHA-256</th><th class="r">State</th></tr>{uploads}</table>
<div class="note">Dev workspace Lakehouse. A rerun leaves identical files untouched.</div></div></div>
<div class="foot" style="margin-top:12px"><span>Generated from sanitized live reports. Workspace and item identifiers are hashed.</span><span>github.com/samueltauil/fabricops-copilot</span></div>
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
