from __future__ import annotations

import json
from pathlib import Path

from fabricops.capabilities import capabilities_dict
from fabricops.config import load_configuration
from fabricops.engine import Executor, Planner, write_plan
from fabricops.insights import drift_snapshot, health_snapshot
from fabricops.state import StateStore


def run_tui(config_path: Path, state_path: Path, output_path: Path, mode: str) -> int:
    config = load_configuration(config_path)
    store = StateStore(state_path)
    while True:
        _header(config.customer, config.project, mode)
        print("1. Capability preflight")
        print("2. Preview all changes")
        print("3. Apply mock plan")
        print("4. Operations health")
        print("5. Governance drift")
        print("6. Inspect current state")
        print("7. Exit")
        choice = input("\nSelect an action: ").strip()
        if choice == "1":
            for capability in capabilities_dict(mode):
                print(f"{capability['status']:11} {capability['name']:25} {capability['note']}")
            _pause()
        elif choice == "2":
            plan = Planner(store).create(config, "all", mode)
            paths = write_plan(plan, output_path / "tui")
            print(f"\nPlan summary: {plan.summary()}")
            print(f"Artifacts: {paths[0]}, {paths[1]}")
            _pause()
        elif choice == "3":
            if mode != "mock":
                print("\nLive apply is disabled until tenant adapters are configured.")
                _pause()
                continue
            plan = Planner(store).create(config, "all", mode)
            print(f"\nPlanned changes: {plan.summary()}")
            confirmation = input("Type APPLY to continue: ").strip()
            if confirmation == "APPLY":
                print(json.dumps(Executor(store).apply(config, plan), indent=2))
            else:
                print("Apply cancelled.")
            _pause()
        elif choice == "4":
            report = health_snapshot(config, store)
            print(f"\nHealth summary: {report['summary']}")
            for item in report["items"]:
                retry = "retry eligible" if item["retry_eligible"] else item["retry_reason"]
                print(f"- {item['name']}: {item['status']} ({retry})")
            _pause()
        elif choice == "5":
            report = drift_snapshot(config, store)
            print(f"\nDrift summary: {report['summary']}")
            for category in ("missing", "changed", "unexpected"):
                for key in report[category]:
                    print(f"- {category}: {key}")
            _pause()
        elif choice == "6":
            state = store.load()
            print(f"\nTracked resources: {len(state.get('resources', {}))}")
            for key in sorted(state.get("resources", {})):
                print(f"- {key}")
            _pause()
        elif choice == "7":
            return 0
        else:
            print("Unknown selection.")


def _header(customer: str, project: str, mode: str) -> None:
    print("\n" + "=" * 72)
    print("FabricOps Copilot - Administrator Console")
    print(f"Project: {customer} / {project} | Mode: {mode}")
    print("=" * 72)


def _pause() -> None:
    input("\nPress Enter to return to the menu...")
