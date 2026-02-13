#!/usr/bin/env python3
"""
AI Repo Co-Pilot — CLI Interface

Usage:
    python cli.py /path/to/repo "What are the security risks?"
    python cli.py /path/to/repo  (defaults to general analysis)
    python cli.py /path/to/repo --json  (raw JSON output)
    python cli.py /path/to/repo -o report.json  (save to file)
"""

import argparse
import json
import os
import sys
import time

from agent.langgraph_workflow import run_langgraph_agent


def format_report(state) -> str:
    """Format agent output as a human-readable report."""
    output = state.output
    lines = []

    lines.append("=" * 60)
    lines.append("  AI REPO CO-PILOT — ANALYSIS REPORT")
    lines.append("=" * 60)
    lines.append("")

    # Summary
    summary = output.get("summary", "No summary available.")
    lines.append("SUMMARY")
    lines.append("-" * 40)
    lines.append(summary)
    lines.append("")

    # Confidence
    confidence = output.get("confidence", "unknown")
    emoji = {"high": "●", "medium": "◐", "low": "○"}.get(confidence, "?")
    lines.append(f"CONFIDENCE: {emoji} {confidence.upper()}")
    lines.append("")

    # High risk areas
    hra = output.get("high_risk_areas", [])
    if hra:
        lines.append(f"HIGH RISK AREAS ({len(hra)} found)")
        lines.append("-" * 40)
        for i, area in enumerate(hra, 1):
            fp = area.get("file_path", "?")
            ls = area.get("line_start", "?")
            le = area.get("line_end", "?")
            desc = area.get("description", "")
            if ls == le:
                loc = f"{fp}:{ls}"
            else:
                loc = f"{fp}:{ls}-{le}"
            lines.append(f"  {i}. {loc}")
            lines.append(f"     {desc}")
            lines.append("")
    else:
        lines.append("HIGH RISK AREAS: None found.")
        lines.append("")

    # Validation status
    lines.append("VALIDATION")
    lines.append("-" * 40)
    schema_ok = "PASS" if state.schema_valid else "FAIL"
    cite_ok = "PASS" if state.citations_valid else "FAIL"
    lines.append(f"  Schema:    [{schema_ok}]")
    lines.append(f"  Citations: [{cite_ok}]")

    if state.schema_errors:
        for err in state.schema_errors:
            lines.append(f"    ! {err}")
    if state.citation_errors:
        for err in state.citation_errors:
            lines.append(f"    ! {err}")

    lines.append("")
    lines.append("=" * 60)

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        prog="ai-repo-copilot",
        description="Analyze a code repository with AI-powered static analysis.",
        epilog="Example: python cli.py ./my-project \"Find SQL injection vulnerabilities\"",
    )
    parser.add_argument(
        "repo",
        help="Path to the repository to analyze",
    )
    parser.add_argument(
        "task",
        nargs="?",
        default="Identify high-risk areas, potential bugs, and security concerns in this codebase.",
        help="Analysis task / question (default: general analysis)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output raw JSON instead of formatted report",
    )
    parser.add_argument(
        "-o", "--output",
        metavar="FILE",
        help="Save JSON output to a file",
    )
    parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Suppress agent progress logs (only show report)",
    )

    args = parser.parse_args()

    # Validate repo path
    repo_path = os.path.abspath(args.repo)
    if not os.path.isdir(repo_path):
        print(f"Error: '{args.repo}' is not a directory.", file=sys.stderr)
        sys.exit(1)

    # Suppress logs if quiet mode
    if args.quiet:
        sys.stdout = open(os.devnull, "w")

    # Run the agent
    start = time.time()

    try:
        state = run_langgraph_agent(task=args.task, repo_path=repo_path)
    except Exception as e:
        if args.quiet:
            sys.stdout = sys.__stdout__
        print(f"Error: Agent failed — {e}", file=sys.stderr)
        sys.exit(1)

    elapsed = time.time() - start

    # Restore stdout if suppressed
    if args.quiet:
        sys.stdout = sys.__stdout__

    # Build JSON result
    result = {
        "task": args.task,
        "repo": repo_path,
        "output": state.output,
        "validation": {
            "schema_valid": state.schema_valid,
            "citations_valid": state.citations_valid,
            "schema_errors": state.schema_errors,
            "citation_errors": state.citation_errors,
        },
        "meta": {
            "elapsed_seconds": round(elapsed, 2),
            "llm_attempts": state.llm_attempts,
        },
    }

    # Save to file if requested
    if args.output:
        with open(args.output, "w") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        print(f"Report saved to {args.output}")

    # Print output
    if args.json_output:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print()
        print(format_report(state))
        print(f"  Completed in {elapsed:.1f}s ({state.llm_attempts} LLM call{'s' if state.llm_attempts != 1 else ''})")
        print()


if __name__ == "__main__":
    main()