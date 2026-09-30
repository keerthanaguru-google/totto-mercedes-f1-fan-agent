#!/usr/bin/env python3
"""CXAS Agent Foundry Lint Harness.

Runs the full cxas_scrapi linter suite against a CXAS project directory and
exits 0 only when there are 0 errors and 0 deterministic warnings.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from cxas_scrapi.utils.linter import (
    Discovery,
    LintConfig,
    LintReport,
    Severity,
    build_context,
    build_registry,
    run_rules,
)


def _resolve_paths(target: Path) -> tuple[Path, Path, Path, LintConfig]:
  """Resolves project_root, app_dir, evals_dir, and LintConfig for target."""
  resolved = target.resolve()
  if (resolved / "app.json").exists() or (resolved / "app.yaml").exists():
    project_root = resolved.parent.parent if resolved.parent.name == "cxas_app" else resolved.parent
    config = LintConfig.load(project_root)
    app_dir = resolved
    evals_dir = project_root / config.evals_dir
    return project_root, app_dir, evals_dir, config

  project_root = resolved
  config = LintConfig.load(project_root)
  app_dir = project_root / config.app_dir
  evals_dir = project_root / config.evals_dir
  return project_root, app_dir, evals_dir, config


def main(argv: list[str] | None = None) -> int:
  parser = argparse.ArgumentParser(
      description="Run CXAS deterministic lint checks on a project."
  )
  parser.add_argument(
      "project",
      nargs="?",
      default=".",
      help="Path to the CXAS project root or app directory.",
  )
  parser.add_argument(
      "--app-dir",
      dest="app_dir",
      default=None,
      help="Optional override path to project root or app directory.",
  )
  parser.add_argument(
      "--json",
      action="store_true",
      dest="json_output",
      help="Emit JSON lint report.",
  )
  parser.add_argument(
      "--fix",
      action="store_true",
      dest="show_fixes",
      help="Show fix hints.",
  )
  args = parser.parse_args(argv)

  target_str = args.app_dir if args.app_dir else args.project
  project_root, app_dir, evals_dir, config = _resolve_paths(Path(target_str))

  discovery = Discovery(app_dir, evals_dir)
  if not discovery.app_root:
    print(f"ERROR: No app directory found under {app_dir}")
    return 1

  registry = build_registry()
  context = build_context(project_root, config, discovery)

  if not args.json_output:
    print(f"Linting app: {discovery.app_root.name}")
    print("=" * 60)
    print(f"  Agents: {len(discovery.discover_agents())}")
    print(f"  Tools: {len(discovery.discover_tools())}")
    print(f"  Callbacks: {len(discovery.discover_callbacks())}")
    print(f"  Evals: {len(discovery.discover_evals())}")

  report = LintReport()
  run_rules(registry, config, context, discovery, report)

  if args.json_output:
    print(report.to_json())
  else:
    print("\n" + "=" * 60)
    print("LINT RESULTS")
    print("=" * 60)
    report.print_summary(show_fixes=args.show_fixes)

  errors = [r for r in report.results if r.severity == Severity.ERROR]
  deterministic_warnings = [
      r
      for r in report.results
      if r.severity == Severity.WARNING and not r.rule_id.startswith("LLM")
  ]
  if errors or deterministic_warnings:
    if not args.json_output:
      print(
          f"\nLint FAILED with {len(errors)} error(s) and"
          f" {len(deterministic_warnings)} deterministic warning(s)."
      )
    return 1
  if not args.json_output:
    print("\nLint PASSED (0 errors, 0 deterministic warnings).")
  return 0


if __name__ == "__main__":
  sys.exit(main())
