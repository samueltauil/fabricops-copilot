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
*{box-sizing:border-box}
body{margin:0;font-family:'Segoe UI Variable','Segoe UI',system-ui,sans-serif;color:#1b2430;background:#f3f5f9;width:1320px}
.hero{background:linear-gradient(120deg,#0b3d3a 0,#0f6e63 45%,#1a8f7a 100%);color:#fff;padding:36px 44px 74px;position:relative}
.hero h1{margin:0;font-size:36px;font-weight:700;letter-spacing:-.6px}.hero h1 span{font-weight:300;opacity:.85}
.hero .sub{margin-top:8px;font-size:15px;opacity:.82}
.live{position:absolute;right:44px;top:40px;background:#ffffff22;border:1px solid #ffffff55;border-radius:99px;padding:6px 14px;font-size:13px;font-weight:600}
.live:before{content:"";display:inline-block;width:8px;height:8px;border-radius:50%;background:#5ef2a0;margin-right:8px;box-shadow:0 0 8px #5ef2a0}
.wrap{padding:0 44px 36px;margin-top:-52px;position:relative;z-index:3}
.flow{display:grid;grid-template-columns:repeat(5,1fr);background:#fff;border-radius:14px;box-shadow:0 6px 24px #0b1e3a1f;margin-bottom:22px}
.step{padding:16px 18px;border-right:1px solid #e6eaf1;position:relative}.step:last-child{border:0}
.step .n{font-size:11px;letter-spacing:1.2px;color:#6b7a90}
.step .t{font-size:18px;font-weight:700;margin:3px 0}.step .s{font-size:12.5px;color:#0f7b4b;font-weight:600}
.step:after{content:"";position:absolute;right:-6px;top:50%;margin-top:-6px;width:10px;height:10px;background:#fff;border-top:2px solid #9aa7ba;border-right:2px solid #9aa7ba;transform:rotate(45deg);z-index:2}.step:last-child:after{display:none}
.grid{display:grid;grid-template-columns:repeat(5,1fr);gap:14px;margin-bottom:22px}
.pill{background:#fff;border-radius:12px;padding:16px 18px;border-left:4px solid #0f7b6c;box-shadow:0 1px 3px #0b1e3a14}
.pill .k{font-size:11.5px;color:#6b7a90;text-transform:uppercase;letter-spacing:1px}
.pill .v{font-size:32px;font-weight:700;margin-top:4px;color:#0b3d3a}
.pill .v.ok{color:#0f7b4b}.pill .v.warn{color:#b26a00}
.row{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-bottom:18px}
.card{background:#fff;border-radius:14px;padding:22px;box-shadow:0 1px 3px #0b1e3a14}
.card h2{margin:0 0 14px;font-size:17px;display:flex;align-items:center;gap:10px;color:#0b3d3a}
.tag{font-size:11px;font-weight:600;padding:3px 10px;border-radius:99px;background:#e3f4f0;color:#0f6e63}
table{width:100%;border-collapse:collapse;font-size:13.5px}
th{color:#6b7a90;text-align:left;font-weight:600;font-size:11.5px;text-transform:uppercase;letter-spacing:.6px;padding:6px 8px;border-bottom:2px solid #e6eaf1}
td{padding:9px 8px;border-bottom:1px solid #eef1f6}
.b{display:inline-block;padding:2px 10px;border-radius:99px;font-size:12px;font-weight:600}
.b.ok{background:#dff5e8;color:#0f7b4b}.b.warn{background:#fff1d6;color:#9a5b00}.b.info{background:#e3f4f0;color:#0f6e63}
.env{display:flex;gap:10px;align-items:center;margin-bottom:10px}
.dot{width:10px;height:10px;border-radius:50%;background:#18b26b}.mono{font-family:Consolas,monospace;color:#6b7a90;font-size:12.5px}
.bar{height:8px;border-radius:99px;background:#e6eaf1;overflow:hidden;margin-top:6px}
.bar i{display:block;height:100%;background:linear-gradient(90deg,#0f7b6c,#18b26b)}
.foot{color:#6b7a90;font-size:12px;margin-top:12px}
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

    flow = "".join(
        f'<div class="step"><div class="n">{n}</div><div class="t">{t}</div><div class="s">&#10003; {st}</div></div>'
        for n, t, st in [
            ("01", "Provision", f"{len(prov['environments'])} workspaces"),
            ("02", "Deploy", f"{items} items, idempotent"),
            ("03", "Operate", f"{health.get('healthy', 0)} healthy job"),
            ("04", "Govern", f"{gov['driftCount']} drift findings"),
            ("05", "Accelerate", "RTI + Synthea"),
        ]
    )

    return f"""<html><head><meta charset="utf-8"><style>{CSS}</style></head><body>
<div class="hero"><div class="live">LIVE SANDBOX</div><h1>FabricOps <span>Copilot</span></h1>
<div class="sub">Governed Microsoft Fabric administration &middot; synthetic healthcare (Synthea) &middot; generated {now} from live reports</div></div>
<div class="wrap">
<div class="flow">{flow}</div>
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
        page = browser.new_page(viewport={"width": 1320, "height": 900}, device_scale_factor=2)
        page.set_content(page_html)
        page.screenshot(path=str(OUT / "dashboard.png"), full_page=True)
        browser.close()


if __name__ == "__main__":
    main()
