from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from .adapters import ADAPTERS
from .models import Result, Status
from .transport import utc_now


def write_json(data: dict, output: Path | None) -> None:
    content = json.dumps(data, indent=2, ensure_ascii=True) + "\n"
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(content, encoding="utf-8")
        print(f"Evidence written: {output}")
    else:
        print(content)


def verify(cases_path: Path, output: Path) -> int:
    cases = json.loads(cases_path.read_text(encoding="utf-8-sig"))
    adapters = {name: adapter() for name, adapter in ADAPTERS.items()}
    report = {"schema_version": 1, "data_origin": "live_http", "started_at": utc_now(), "scope": "A0 investigation only", "cases": []}
    stopped = {}
    for case in cases:
        adapter = adapters[case["supplier"]]
        if adapter.name in stopped:
            result = Result(adapter.name, case["operation"], case.get("mpn"), Status.SKIPPED, message="Supplier stopped for this run after " + stopped[adapter.name])
        elif case["operation"] == "search":
            result = adapter.search(case["mpn"], limit=case.get("limit", 2))
        elif case["operation"] == "product":
            result = adapter.product(case["url"], mpn=case.get("mpn"))
        else:
            raise ValueError("Unsupported case operation")
        if result.status in {Status.BLOCKED, Status.RATE_LIMITED, Status.ROBOTS_UNAVAILABLE} or any(e.get("http_status") in {401, 403, 429} for e in result.evidence):
            stopped[adapter.name] = str(result.status)
        entry = result.to_dict()
        entry["case_id"] = case["id"]
        entry["sample_kind"] = case.get("kind", "unspecified")
        entry["seed_url_origin"] = case.get("url_origin") if case["operation"] == "product" else None
        report["cases"].append(entry)
        print(f"{case['id']}: {result.status}; {len(result.offers)} offers", flush=True)
    report["finished_at"] = utc_now()
    report["status_counts"] = dict(Counter(case["status"] for case in report["cases"]))
    report["request_evidence"] = {name: adapter.client.evidence for name, adapter in adapters.items()}
    report["execution_completed"] = True
    report["integration_pass_claimed"] = False
    report["note"] = "Completion means all investigations ran. Supplier PASS/PARTIAL/BLOCKED and GO decisions require report review; exit 0 is not an integration PASS."
    write_json(report, output)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SONAR A0: local, robots-respecting live supplier evidence")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ["search", "product", "health"]:
        command = commands.add_parser(name)
        command.add_argument("supplier", choices=sorted(ADAPTERS))
        command.add_argument("--output", type=Path)
        if name == "search":
            command.add_argument("mpn")
            command.add_argument("--limit", type=int, default=5)
        elif name == "product":
            command.add_argument("url")
            command.add_argument("--mpn")
    command = commands.add_parser("verify")
    command.add_argument("--cases", type=Path, default=Path("examples/a0_cases.json"))
    command.add_argument("--output", type=Path, default=Path("live-output/a0-live.json"))
    args = parser.parse_args(argv)
    try:
        if args.command == "verify":
            return verify(args.cases, args.output)
        adapter = ADAPTERS[args.supplier]()
        if args.command == "search":
            result = adapter.search(args.mpn, limit=args.limit)
        elif args.command == "product":
            result = adapter.product(args.url, mpn=args.mpn)
        else:
            result = adapter.health()
        write_json(result.to_dict(), args.output)
        return 0 if result.status == Status.OK else (2 if result.status in {Status.PARTIAL, Status.NOT_FOUND} else 3)
    except (OSError, ValueError, KeyError) as error:
        print(f"Input/execution error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
