"""Build a visual dashboard from the live FabricOps reports and screenshot it.

Reads the sanitized JSON reports written by the *-live commands (hashed IDs only),
renders an HTML page, and captures PNGs with a headless browser.
"""

from __future__ import annotations

import html
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

REPORTS = Path(sys.argv[1] if len(sys.argv) > 1 else "artifacts/real")
OUT = Path("docs/images")

CSS = """
*{box-sizing:border-box}body{margin:0;font-family:'Segoe UI',system-ui,sans-serif;color:#e6edf3;
background:radial-gradient(1200px 600px at 10% -10%,#1b3a6b 0,transparent 60%),
radial-gradient(900px 500px at 100% 0,#0f5f4f 0,transparent 55%),#0b1220;padding:40px;width:1280px}
h1{margin:0;font-size:34px;letter-spacing:-.5px}h1 span{color:#4fc3f7}
.sub{color:#8b98a9;margin:6px 0 28px;font-size:15px}
.grid{display:grid;grid-template-columns:repeat(5,1fr);gap:14px;margin-bottom:22px}
.pill{background:#121c30cc;border:1px solid #243452;border-radius:14px;padding:16px}
.pill .k{font-size:12px;color:#8b98a9;text-transform:uppercase;letter-spacing:1px}
.pill .v{font-size:30px;font-weight:700;margin-top:6px}.ok{color:#3fb950}.warn{color:#f0b429}.info{color:#4fc3f7}
.row{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-bottom:18px}
.card{background:#121c30cc;border:1px solid #243452;border-radius:16px;padding:20px}
.card h2{margin:0 0 14px;font-size:16px;display:flex;align-items:center;gap:10px}
.tag{font-size:11px;padding:3px 9px;border-radius:99px;background:#1f6feb33;color:#79c0ff;border:1px solid #1f6feb66}
table{width:100%;border-collapse:collapse;font-size:14px}th{color:#8b98a9;text-align:left;font-weight:500;padding:6px 8px;
border-bottom:1px solid #243452}td{padding:8px;border-bottom:1px solid #1a2740}
.b{display:inline-block;padding:2px 10px;border-radius:99px;font-size:12px;font-weight:600}
.b.ok{background:#23863633;color:#3fb950}.b.warn{background:#9e6a0333;color:#f0b429}.b.info{background:#1f6feb33;color:#79c0ff}
.env{display:flex;gap:10px;align-items:center;margin-bottom:10px}.dot{width:10px;height:10px;border-radius:50%;background:#3fb950;
box-shadow:0 0 10px #3fb950}.mono{font-family:Consolas,monospace;color:#8b98a9}
.bar{height:8px;border-radius:99px;background:#1a2740;overflow:hidden;margin-top:6px}.bar i{display:block;height:100%;
background:linear-gradient(90deg,#4fc3f7,#3fb950)}
.foot{color:#6b7a90;font-size:12px;margin-top:10px}
"""


def load(name: str) -> dict:
    return json.loads((REPORTS / name).read_text(encoding="utf-8"))


def badge(text: str, kind: str = "ok") -> str:
    return f'<span class="b {kind}">{html.escape(text)}</span>'


def kind_for(action: str) -> str:
    return "ok" if action in {"no-op", "healthy", "present (default database)"} else "warn"


def build() -> str:
    prov, dep = load("live-provision.json"), load("live-deploy.json")
    op, gov, acc = load("live-operate.json"), load("live-govern.json"), load("live-accelerate.json")
    rows = dep["environments"]
    items = sum(len(e["actions"]) for e in rows)
    roles = sum(1 for e in prov["environments"] for a in e["actions"] if a["resource"].startswith("role/"))
    rows_total = sum(acc["dataset"]["tableRowCounts"].values())
    health = op["summary"]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    def pill(k: str, v: str, cls: str) -> str:
        return f'<div class="pill"><div class="k">{k}</div><div class="v {cls}">{v}</div></div>'

    pills = "".join(
        [
            pill("Workspaces", str(len(prov["environments"])), "info"),
            pill("Starter items", str(items), "info"),
            pill("Role assignments", str(roles), "info"),
            pill("Drift findings", str(gov["driftCount"]), "ok" if gov["driftCount"] == 0 else "warn"),
            pill("Synthea rows", f"{rows_total:,}", "ok"),
        ]
    )

    envs = "".join(
        f'<div class="env"><span class="dot"></span><b>{html.escape(e["workspaceName"])}</b>'
        f'<span class="mono">{html.escape(e["environment"])}</span></div>'
        + "".join(
            f'<span style="margin-right:6px">{badge(a["resource"].replace("role/", ""), kind_for(a["action"]))}</span>'
            for a in e["actions"]
        )
        + '<div style="height:12px"></div>'
        for e in prov["environments"]
    )

    dep_rows = "".join(
        f'<tr><td>{html.escape(e["environment"])}</td>'
        + "".join(f"<td>{badge(a['action'], kind_for(a['action']))}</td>" for a in e["actions"])
        + "</tr>"
        for e in rows
    )
    head = "".join(f"<th>{html.escape(a['type'])}</th>" for a in rows[0]["actions"])

    mon = "".join(
        f'<tr><td>{html.escape(i["name"])}</td><td class="mono">{html.escape(i["owner"])}</td>'
        f'<td>{badge(i["health"], "ok" if i["health"] == "healthy" else "warn")}</td>'
        f'<td>{html.escape(str(i["latestJobStatus"] or "-"))}</td></tr>'
        for i in op["items"]
    )

    gov_rows = "".join(
        f'<tr><td>{html.escape(e["environment"])}</td><td>{badge("capacity ok" if e["capacityMatches"] else "capacity drift", "ok" if e["capacityMatches"] else "warn")}</td>'
        f'<td>{e["roleAssignments"]["missing"]}/{e["roleAssignments"]["unexpected"]}</td>'
        f'<td>{e["starterItems"]["missing"]}</td><td>{e["devReferences"]}</td>'
        f'<td class="mono">{html.escape(e["workspaceIdHash"])}</td></tr>'
        for e in gov["environments"]
    )

    rti = "".join(
        f'<tr><td>{html.escape(r["type"])}</td><td>{html.escape(r["item"])}</td><td>{badge(r["action"], kind_for(r["action"]))}</td></tr>'
        for r in acc["realTimeIntelligence"]
    )
    biggest = max(r["bytes"] for r in acc["syntheaUpload"])
    files = "".join(
        f'<div style="margin-bottom:10px"><div style="display:flex;justify-content:space-between"><span>{html.escape(r["table"])}.csv</span>'
        f'<span class="mono">{r["bytes"]:,} bytes {badge(r["action"], kind_for(r["action"]))}</span></div>'
        f'<div class="bar"><i style="width:{max(3, r["bytes"] * 100 // biggest)}%"></i></div></div>'
        for r in acc["syntheaUpload"]
    )
    counts = acc["dataset"]["tableRowCounts"]
    count_tbl = "".join(f"<tr><td>{k}</td><td>{v:,}</td></tr>" for k, v in counts.items())

    return f"""<html><head><meta charset="utf-8"><style>{CSS}</style></head><body>
<h1>FabricOps <span>Copilot</span></h1>
<div class="sub">Live Microsoft Fabric sandbox &middot; synthetic healthcare (Synthea) &middot; generated {now} from live reports</div>
<div class="grid">{pills}</div>
<div class="row">
<div class="card" id="provision"><h2>Provision <span class="tag">landing zone</span></h2>{envs}</div>
<div class="card" id="deploy"><h2>Deploy <span class="tag">dev &rarr; test &rarr; prod</span></h2>
<table><tr><th>Env</th>{head}</tr>{dep_rows}</table>
<div class="foot">Reruns are idempotent: every action is a no-op.</div></div></div>
<div class="row">
<div class="card" id="operate"><h2>Operate <span class="tag">Job Scheduler</span></h2>
<table><tr><th>Monitored item</th><th>Owner</th><th>Health</th><th>Latest job</th></tr>{mon}</table>
<div class="foot">healthy={health.get("healthy", 0)} &middot; unknown={health.get("unknown", 0)} (no matching Fabric item)</div></div>
<div class="card" id="govern"><h2>Govern <span class="tag">drift</span></h2>
<table><tr><th>Env</th><th>Capacity</th><th>Roles miss/extra</th><th>Items missing</th><th>Dev refs</th><th>Workspace</th></tr>{gov_rows}</table>
<div class="foot">Report-only. IDs are hashed.</div></div></div>
<div class="row">
<div class="card" id="accelerate"><h2>Accelerate <span class="tag">Real-Time Intelligence</span></h2>
<table><tr><th>Type</th><th>Item</th><th>State</th></tr>{rti}</table>
<div style="height:14px"></div>{files}</div>
<div class="card" id="synthea"><h2>Synthea dataset <span class="tag">synthetic</span></h2>
<table><tr><th>Table</th><th>Rows</th></tr>{count_tbl}</table>
<div class="foot">Dataset hash {html.escape(acc["dataset"]["datasetHash"])}. No patient data is committed.</div></div></div>
</body></html>"""


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    page_html = build()
    Path("artifacts/dashboard.html").write_text(page_html, encoding="utf-8")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="msedge")
        page = browser.new_page(viewport={"width": 1360, "height": 900}, device_scale_factor=2)
        page.set_content(page_html)
        page.screenshot(path=str(OUT / "dashboard.png"), full_page=True)
        for name in ("provision", "deploy", "operate", "govern", "accelerate"):
            page.locator(f"#{name}").screenshot(path=str(OUT / f"card-{name}.png"))
        browser.close()


if __name__ == "__main__":
    main()
