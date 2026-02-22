"""CLI entrypoint for the Dark Factory Orchestrator."""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from factory.models import ParseError, GenerationError, ValidationError
from factory.spec_parser import parse
from factory.spec_validator import validate
from factory.handoff_generator import generate
from factory.prompt_generator import generate_prompts
from factory.agent_dispatcher import dispatch_pipeline
from factory.holdout_runner import run_holdouts
from factory.report_generator import generate_report, write_report


def cmd_validate(args: argparse.Namespace) -> int:
    """Validate a spec directory."""
    try:
        spec = parse(args.spec_dir)
    except ParseError as e:
        print(json.dumps({"status": "FAIL", "error": str(e)}), file=sys.stdout)
        return 1

    result = validate(spec)
    print(json.dumps(result.to_dict(), indent=2))
    return 0 if result.status == "PASS" else 1


def cmd_generate(args: argparse.Namespace) -> int:
    """Generate handoff documents."""
    try:
        spec = parse(args.spec_dir)
    except ParseError as e:
        print(json.dumps({"status": "FAIL", "error": str(e)}), file=sys.stderr)
        return 1

    result = validate(spec)
    if result.status != "PASS":
        print(json.dumps({"status": "FAIL", "error": "Spec validation failed",
                          "checks": result.to_dict()["checks"]}), file=sys.stderr)
        return 1

    try:
        handoffs = generate(spec, args.output_dir)
    except GenerationError as e:
        print(json.dumps({"status": "FAIL", "error": str(e)}), file=sys.stderr)
        return 1

    print(json.dumps({
        "status": "OK",
        "handoffs": len(handoffs),
        "output_dir": str(args.output_dir),
    }, indent=2))
    return 0


def cmd_prompts(args: argparse.Namespace) -> int:
    """Generate agent prompts from handoffs."""
    try:
        spec = parse(args.spec_dir)
    except ParseError as e:
        print(json.dumps({"status": "FAIL", "error": str(e)}), file=sys.stderr)
        return 1

    # Re-generate handoffs to get Handoff objects
    try:
        handoffs = generate(spec, args.handoffs_dir)
    except GenerationError as e:
        print(json.dumps({"status": "FAIL", "error": str(e)}), file=sys.stderr)
        return 1

    prompts = generate_prompts(handoffs, spec, args.handoffs_dir)
    print(json.dumps({
        "status": "OK",
        "prompts": len(prompts),
        "output_dir": str(args.handoffs_dir),
    }, indent=2))
    return 0


def cmd_holdout(args: argparse.Namespace) -> int:
    """Run holdout scenarios."""
    try:
        spec = parse(args.spec_dir)
    except ParseError as e:
        print(json.dumps({"status": "FAIL", "error": str(e)}), file=sys.stderr)
        return 1

    results = run_holdouts(spec, args.install_root)
    output = {
        "holdouts": [r.to_dict() for r in results],
        "p0_total": sum(1 for r in results if r.priority == "P0"),
        "p0_passed": sum(1 for r in results if r.priority == "P0" and r.status == "PASS"),
    }
    p0_all_pass = all(r.status == "PASS" for r in results if r.priority == "P0")
    output["verdict"] = "PASS" if p0_all_pass else "FAIL"
    print(json.dumps(output, indent=2))
    return 0 if p0_all_pass else 1


def cmd_run(args: argparse.Namespace) -> int:
    """Full pipeline run."""
    start = time.monotonic()

    try:
        spec = parse(args.spec_dir)
    except ParseError as e:
        print(json.dumps({"status": "FAIL", "error": str(e)}), file=sys.stderr)
        return 1

    # Validate
    validation = validate(spec)
    if validation.status != "PASS":
        print(json.dumps({"status": "FAIL", "error": "Validation failed",
                          "validation": validation.to_dict()}), file=sys.stderr)
        return 1

    # Generate
    output_dir = Path(args.output_dir)
    try:
        handoffs = generate(spec, output_dir)
        prompts = generate_prompts(handoffs, spec, output_dir)
    except GenerationError as e:
        print(json.dumps({"status": "FAIL", "error": str(e)}), file=sys.stderr)
        return 1

    # Dispatch
    ledger_path = output_dir / "dispatch_ledger.jsonl"
    dispatches = dispatch_pipeline(
        prompts, spec, str(output_dir), str(ledger_path),
        claude_path=getattr(args, "claude_path", None),
    )

    # Holdout
    holdouts = run_holdouts(spec, str(output_dir))

    # Report
    duration = int((time.monotonic() - start) * 1000)
    report = generate_report(spec, validation, dispatches, holdouts, duration)
    report_path = write_report(report, output_dir)

    print(json.dumps(report.to_dict(), indent=2))
    return 0 if report.verdict == "ACCEPT" else 1


def main(argv: list[str] | None = None) -> None:
    """Main CLI entrypoint."""
    parser = argparse.ArgumentParser(
        prog="factory",
        description="Dark Factory Orchestrator — spec-to-delivery pipeline",
    )
    subparsers = parser.add_subparsers(dest="command")

    # validate
    p_validate = subparsers.add_parser("validate", help="Validate a spec directory")
    p_validate.add_argument("--spec-dir", required=True, help="Path to D1-D10 spec directory")

    # generate
    p_generate = subparsers.add_parser("generate", help="Generate handoff documents")
    p_generate.add_argument("--spec-dir", required=True)
    p_generate.add_argument("--output-dir", required=True)

    # prompts
    p_prompts = subparsers.add_parser("prompts", help="Generate agent prompts")
    p_prompts.add_argument("--handoffs-dir", required=True)
    p_prompts.add_argument("--spec-dir", required=True)

    # holdout
    p_holdout = subparsers.add_parser("holdout", help="Run holdout scenarios")
    p_holdout.add_argument("--spec-dir", required=True)
    p_holdout.add_argument("--install-root", required=True)

    # run
    p_run = subparsers.add_parser("run", help="Full pipeline run")
    p_run.add_argument("--spec-dir", required=True)
    p_run.add_argument("--output-dir", required=True)

    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        sys.exit(2)

    dispatch = {
        "validate": cmd_validate,
        "generate": cmd_generate,
        "prompts": cmd_prompts,
        "holdout": cmd_holdout,
        "run": cmd_run,
    }
    exit_code = dispatch[args.command](args)
    sys.exit(exit_code)
