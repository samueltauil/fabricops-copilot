from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from fabricops.capabilities import capabilities_dict
from fabricops.config import ConfigurationError, load_configuration
from fabricops.engine import Executor, PlanError, Planner, load_plan, write_plan
from fabricops.insights import drift_snapshot, health_snapshot
from fabricops.live import (
    FabricApiError,
    FabricRestClient,
    LiveConfigurationError,
    default_token_provider,
    discover_configured_workspaces,
)
from fabricops.live_accelerate import OneLakeFiles, accelerate_live, storage_token_provider
from fabricops.live_deploy import DeploymentError, deploy_live
from fabricops.live_govern import (
    govern_live,
    inject_demo_drift,
    render_markdown,
    revert_demo_drift,
)
from fabricops.live_operate import OperateError, operate_live, write_operate_report
from fabricops.live_provision import provision_live, resolve_references
from fabricops.preflight import live_preflight
from fabricops.reports import write_evidence
from fabricops.state import StateStore
from fabricops.synthea import SyntheaError, synthea_settings
from fabricops.synthea import generate as generate_synthea

DEFAULT_CONFIG = Path("config/examples/synthetic-healthcare/project.yml")
DEFAULT_STATE = Path(".fabricops/state.json")
DEFAULT_OUTPUT = Path("artifacts")
USE_CASES = ("provision", "deploy", "operate", "govern", "accelerate", "all")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fabricops")
    subparsers = parser.add_subparsers(dest="command", required=True)

    capabilities = subparsers.add_parser("capabilities", help="Show capability preflight")
    capabilities.add_argument("--mode", choices=("mock", "live"), default="mock")

    preflight = subparsers.add_parser("preflight", help="Validate live-mode prerequisites")
    preflight.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)

    discover = subparsers.add_parser("discover", help="Run read-only live workspace discovery")
    discover.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    discover.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)

    provision = subparsers.add_parser(
        "provision-live", help="Preview or apply live landing-zone provisioning"
    )
    provision.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    provision.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    provision.add_argument("--apply", action="store_true")

    deploy_live_parser = subparsers.add_parser(
        "deploy-live", help="Preview or apply live starter-item deployment"
    )
    deploy_live_parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    deploy_live_parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    deploy_live_parser.add_argument("--apply", action="store_true")

    accelerate_parser = subparsers.add_parser(
        "accelerate-live", help="Preview or apply live RTI items and Synthea data load"
    )
    accelerate_parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    accelerate_parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    accelerate_parser.add_argument("--apply", action="store_true")
    accelerate_parser.add_argument("--data-dir", type=Path, default=Path(".fabricops/synthea"))
    accelerate_parser.add_argument("--tools-dir", type=Path, default=Path(".fabricops/tools"))

    operate = subparsers.add_parser(
        "operate-live", help="Read live job health; optionally run or safely retry jobs"
    )
    operate.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    operate.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    operate.add_argument("--run", action="store_true", help="Trigger on-demand jobs")
    operate.add_argument("--retry", action="store_true", help="Retry policy-eligible failed jobs")

    govern_parser = subparsers.add_parser(
        "govern-live", help="Read-only live drift report (desired vs actual)"
    )
    govern_parser.add_argument("mode", nargs="?", choices=("live",), default="live")
    govern_parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    govern_parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    govern_parser.add_argument("--inject-demo-drift", action="store_true")
    govern_parser.add_argument("--revert-demo-drift", action="store_true")

    plan = subparsers.add_parser("plan", help="Create a desired-state change plan")
    _common(plan)
    plan.add_argument("--use-case", choices=USE_CASES, default="all")

    apply = subparsers.add_parser("apply", help="Apply an approved plan")
    _common(apply)
    apply.add_argument("--plan", required=True, type=Path)

    demo = subparsers.add_parser("demo", help="Run all mock demos and prove safe reruns")
    _common(demo)
    demo.add_argument("--skip-synthea", action="store_true")
    demo.add_argument("--data-dir", type=Path, default=Path(".fabricops/synthea"))
    demo.add_argument("--tools-dir", type=Path, default=Path(".fabricops/tools"))

    health = subparsers.add_parser("health", help="Build the operational health report")
    _common(health)

    synthea = subparsers.add_parser("synthea", help="Generate seeded synthetic patient data")
    synthea.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    synthea.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    synthea.add_argument("--data-dir", type=Path, default=Path(".fabricops/synthea"))
    synthea.add_argument("--tools-dir", type=Path, default=Path(".fabricops/tools"))

    drift = subparsers.add_parser("drift", help="Build the governance drift report")
    _common(drift)

    tui = subparsers.add_parser("tui", help="Open the guided terminal interface")
    _common(tui)
    return parser


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--mode", choices=("mock", "live"), default="mock")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "capabilities":
            print(json.dumps(capabilities_dict(args.mode), indent=2))
            return 0
        if args.command == "preflight":
            report = live_preflight()
            args.output.mkdir(parents=True, exist_ok=True)
            path = args.output / "live-preflight.json"
            path.write_text(json.dumps(report, indent=2), encoding="utf-8")
            print(json.dumps({"report": str(path), **report}))
            return 0 if report["readyForLiveDiscovery"] else 2
        if args.command == "discover":
            preflight = live_preflight()
            if not preflight["readyForLiveDiscovery"]:
                raise LiveConfigurationError(
                    "Live discovery prerequisites are incomplete; run fabricops preflight"
                )
            config = load_configuration(args.config)
            client = FabricRestClient(default_token_provider)
            report = discover_configured_workspaces(
                config.spec["environments"],
                client.list_workspaces(),
                {
                    "shared-nonprod": os.environ["FABRIC_CAPACITY_NONPROD"],
                    "production": os.environ["FABRIC_CAPACITY_PROD"],
                },
            )
            path = _write_report(args.output, "live-workspace-discovery", report)
            print(json.dumps({"report": str(path), **report}))
            return 0
        if args.command == "provision-live":
            if not live_preflight()["readyForLiveDiscovery"]:
                raise LiveConfigurationError("Run fabricops preflight; prerequisites are missing")
            if args.apply and os.getenv("FABRICOPS_ALLOW_LIVE_MUTATION") != "1":
                raise LiveConfigurationError(
                    "Live mutation requires FABRICOPS_ALLOW_LIVE_MUTATION=1 and --apply"
                )
            config = load_configuration(args.config)
            groups, capacities = resolve_references(config)
            report = provision_live(
                FabricRestClient(default_token_provider), config, groups, capacities, args.apply
            )
            path = _write_report(args.output, "live-provision", report)
            print(json.dumps({"report": str(path), **report}))
            return 0
        if args.command == "deploy-live":
            if not live_preflight()["readyForLiveDiscovery"]:
                raise LiveConfigurationError("Run fabricops preflight; prerequisites are missing")
            if args.apply and os.getenv("FABRICOPS_ALLOW_LIVE_MUTATION") != "1":
                raise LiveConfigurationError(
                    "Live mutation requires FABRICOPS_ALLOW_LIVE_MUTATION=1 and --apply"
                )
            config = load_configuration(args.config)
            report = deploy_live(FabricRestClient(default_token_provider), config, args.apply)
            path = _write_report(args.output, "live-deploy", report)
            print(json.dumps({"report": str(path), **report}))
            return 0
        if args.command == "govern-live":
            if not live_preflight()["readyForLiveDiscovery"]:
                raise LiveConfigurationError("Run fabricops preflight; prerequisites are missing")
            config = load_configuration(args.config)
            client = FabricRestClient(default_token_provider)
            actions = []
            if args.inject_demo_drift:
                actions.append(inject_demo_drift(client, config))
            if args.revert_demo_drift:
                actions.append(revert_demo_drift(client, config))
            groups, capacities = resolve_references(config)
            report = govern_live(client, config, groups, capacities)
            if actions:
                report["demoActions"] = actions
            path = _write_report(args.output, "live-govern", report)
            path.with_suffix(".md").write_text(render_markdown(report), encoding="utf-8")
            print(json.dumps({"report": str(path), "status": report["status"],
                              "driftCount": report["driftCount"],
                              "severityCounts": report["severityCounts"],
                              "demoActions": actions}))
            return 0
        if args.command == "operate-live":
            if not live_preflight()["readyForLiveDiscovery"]:
                raise LiveConfigurationError("Run fabricops preflight; prerequisites are missing")
            if (args.run or args.retry) and os.getenv("FABRICOPS_ALLOW_LIVE_MUTATION") != "1":
                raise LiveConfigurationError(
                    "Running jobs requires FABRICOPS_ALLOW_LIVE_MUTATION=1 and --run/--retry"
                )
            config = load_configuration(args.config)
            report = operate_live(
                FabricRestClient(default_token_provider), config, args.run, args.retry
            )
            paths = write_operate_report(args.output, report)
            print(json.dumps({"reports": [str(p) for p in paths], "summary": report["summary"]}))
            return 0
        if args.command == "accelerate-live":
            if not live_preflight()["readyForLiveDiscovery"]:
                raise LiveConfigurationError("Run fabricops preflight; prerequisites are missing")
            if args.apply and os.getenv("FABRICOPS_ALLOW_LIVE_MUTATION") != "1":
                raise LiveConfigurationError(
                    "Live mutation requires FABRICOPS_ALLOW_LIVE_MUTATION=1 and --apply"
                )
            config = load_configuration(args.config)
            report = accelerate_live(
                FabricRestClient(default_token_provider),
                OneLakeFiles(storage_token_provider),
                config,
                args.data_dir,
                args.tools_dir,
                args.apply,
            )
            path = _write_report(args.output, "live-accelerate", report)
            print(json.dumps({"report": str(path), **report}))
            return 0
        if args.command == "synthea":
            config = load_configuration(args.config)
            report = generate_synthea(
                synthea_settings(config.spec), args.data_dir, args.tools_dir
            )
            path = _write_report(args.output, "synthea-dataset", report)
            print(json.dumps({"report": str(path), **report}))
            return 0
        if args.command == "tui":
            from fabricops.tui import run_tui

            return run_tui(args.config, args.state, args.output, args.mode)
        config = load_configuration(args.config)
        store = StateStore(args.state)
        if args.command == "plan":
            plan = Planner(store).create(config, args.use_case, args.mode)
            paths = write_plan(plan, args.output)
            print(json.dumps({"summary": plan.summary(), "artifacts": [str(p) for p in paths]}))
            return 2 if plan.policy_findings else 0
        if args.command == "apply":
            plan = load_plan(args.plan)
            result = Executor(store).apply(config, plan)
            result.update({"useCase": plan.use_case, "outcome": "succeeded"})
            paths = write_evidence(args.output, f"{plan.use_case}-evidence", result)
            print(json.dumps({"result": result, "artifacts": [str(p) for p in paths]}))
            return 0
        if args.command == "demo":
            if not args.skip_synthea:
                dataset = generate_synthea(
                    synthea_settings(config.spec), args.data_dir, args.tools_dir
                )
                _write_report(args.output, "synthea-dataset", dataset)
            return _run_demo(config, store, args.output, args.mode)
        if args.command == "health":
            report = health_snapshot(config, store)
            path = _write_report(args.output, "morning-health", report)
            print(json.dumps({"report": str(path), **report}))
            return 0
        if args.command == "drift":
            report = drift_snapshot(config, store)
            path = _write_report(args.output, "governance-drift", report)
            print(json.dumps({"report": str(path), **report}))
            return 0
    except (
        ConfigurationError,
        FabricApiError,
        DeploymentError,
        OperateError,
        LiveConfigurationError,
        PlanError,
        SyntheaError,
        OSError,
    ) as error:
        print(f"fabricops: {error}", file=sys.stderr)
        return 1
    return 1


def _run_demo(config, store: StateStore, output: Path, mode: str) -> int:
    if mode != "mock":
        raise PlanError("The cohesive demo requires configured live adapters or --mode mock")
    executor = Executor(store)
    results = []
    for use_case in USE_CASES[:-1]:
        plan = Planner(store).create(config, use_case, mode)
        write_plan(plan, output / use_case)
        result = executor.apply(config, plan)
        second_plan = Planner(store).create(config, use_case, mode)
        if any(change.action != "no-op" for change in second_plan.changes):
            raise PlanError(f"Idempotency validation failed for {use_case}")
        event = {
            "operationId": plan.operation_id,
            "useCase": use_case,
            "outcome": "succeeded",
            **result,
        }
        write_evidence(output / use_case, f"{use_case}-evidence", event)
        results.append({"useCase": use_case, "firstRun": plan.summary(), "rerun": second_plan.summary()})
    summary_path = output / "demo-summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps({"outcome": "succeeded", "summary": str(summary_path)}))
    return 0


def _write_report(output: Path, name: str, report: dict) -> Path:
    output.mkdir(parents=True, exist_ok=True)
    path = output / f"{name}.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return path


if __name__ == "__main__":
    raise SystemExit(main())
