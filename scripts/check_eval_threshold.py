#!/usr/bin/env python3
"""CI/CD Evaluation Threshold Gate for CXAS Agent Studio.

Validates the JSON summary emitted by `run-and-report.py --json-summary`
against a configurable pass-rate threshold (default: strictly > 90%), renders
a Markdown scorecard to stdout and `$GITHUB_STEP_SUMMARY`, writes
`gate_passed` and `pass_rate` to `$GITHUB_OUTPUT`, and exits 0 on pass or 1
on failure.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any

EVAL_TYPE_ORDER: tuple[str, ...] = (
    "golden",
    "sim",
    "tool_test",
    "callback_test",
)

EVAL_TYPE_LABELS: dict[str, str] = {
    "golden": "Golden Conversations (`golden`)",
    "sim": "User Simulations (`sim`)",
    "tool_test": "Deterministic Tool Tests (`tool_test`)",
    "callback_test": "Callback Unit Tests (`callback_test`)",
}


def evaluate_summary(
    summary_data: dict[str, Any],
    threshold: float = 0.90,
    comparison: str = "gt",
) -> tuple[bool, float, list[str]]:
  """Evaluates parsed summary dictionary against gate criteria.

  Args:
    summary_data: Parsed JSON summary produced by `run-and-report.py`.
    threshold: Target pass rate ratio in [0.0, 1.0] (default 0.90).
    comparison: Either 'gt' (strictly >) or 'ge' (>=).

  Returns:
    Tuple of (gate_passed, effective_pass_rate, failure_reasons).
  """
  reasons: list[str] = []

  status = str(summary_data.get("status", "unknown"))
  if status not in ("complete", "partial"):
    reasons.append(
        f"Evaluation run status is '{status}' (expected 'complete' or 'partial')."
    )

  platform_errors = summary_data.get("platform_errors") or []
  if platform_errors:
    reasons.append(
        f"Platform errors detected ({len(platform_errors)}): {platform_errors}"
    )

  total_raw = summary_data.get("total", 0)
  passed_raw = summary_data.get("passed", 0)
  try:
    total = int(total_raw)
    passed = int(passed_raw)
  except (TypeError, ValueError):
    total = 0
    passed = 0
    reasons.append("Invalid 'total' or 'passed' count in summary JSON.")

  if total <= 0:
    reasons.append(f"Total evaluations run is {total} (must be > 0).")

  computed_rate = (passed / total) if total > 0 else 0.0
  raw_pass_rate = summary_data.get("pass_rate")
  if raw_pass_rate is None:
    pass_rate = computed_rate
  else:
    try:
      pass_rate = float(raw_pass_rate)
    except (TypeError, ValueError):
      pass_rate = computed_rate
      reasons.append(f"Invalid 'pass_rate' value: {raw_pass_rate!r}.")

  threshold_pct = threshold * 100.0
  actual_pct = pass_rate * 100.0
  if comparison == "gt":
    if not (pass_rate > threshold):
      reasons.append(
          f"Pass rate {actual_pct:.2f}% does not exceed required strict"
          f" threshold > {threshold_pct:.1f}%."
      )
  elif comparison == "ge":
    if not (pass_rate >= threshold):
      reasons.append(
          f"Pass rate {actual_pct:.2f}% is below required threshold"
          f" >= {threshold_pct:.1f}%."
      )
  else:
    raise ValueError(f"Unsupported comparison operator: {comparison!r}")

  gate_passed = len(reasons) == 0
  return gate_passed, pass_rate, reasons


def render_markdown_scorecard(
    summary_data: dict[str, Any] | None,
    gate_passed: bool,
    pass_rate: float,
    threshold: float,
    comparison: str,
    reasons: list[str],
) -> str:
  """Renders the Markdown evaluation scorecard for stdout and GitHub Step Summary."""
  threshold_pct = threshold * 100.0
  pass_rate_pct = pass_rate * 100.0

  if comparison == "gt":
    verdict_str = (
        f"PASSED (> {threshold_pct:.1f}%)"
        if gate_passed
        else f"FAILED (<= {threshold_pct:.1f}%)"
    )
    rule_str = f"`pass_rate > {threshold:.2f}` (`> {threshold_pct:.1f}%`)"
  else:
    verdict_str = (
        f"PASSED (>= {threshold_pct:.1f}%)"
        if gate_passed
        else f"FAILED (< {threshold_pct:.1f}%)"
    )
    rule_str = f"`pass_rate >= {threshold:.2f}` (`>= {threshold_pct:.1f}%`)"

  data = summary_data or {}
  total = int(data.get("total", 0) or 0)
  passed = int(data.get("passed", 0) or 0)
  failed = int(data.get("failed", max(total - passed, 0)) or 0)
  status = str(data.get("status", "errored"))
  ran_at = str(data.get("ran_at", "N/A"))

  lines: list[str] = [
      "## CXAS Agent Evaluation Gate Scorecard",
      "",
      "| Metric | Value |",
      "| :--- | :--- |",
      f"| **Overall Verdict** | **{verdict_str}** |",
      f"| **Pass Rate** | **{pass_rate_pct:.2f}%** |",
      f"| **Passed / Total** | `{passed}/{total}` (Failed: `{failed}`) |",
      f"| **Gate Rule** | {rule_str} |",
      f"| **Run Status** | `{status}` |",
      f"| **Timestamp** | `{ran_at}` |",
      "",
  ]

  by_type = data.get("by_type")
  if isinstance(by_type, dict) and by_type:
    lines.extend([
        "### Breakdown by Evaluation Type",
        "",
        "| Eval Type | Passed | Failed | Total | Type Pass Rate |",
        "| :--- | ---: | ---: | ---: | ---: |",
    ])
    seen_types: list[str] = [t for t in EVAL_TYPE_ORDER if t in by_type]
    for extra_t in sorted(by_type.keys()):
      if extra_t not in seen_types:
        seen_types.append(extra_t)

    for eval_type in seen_types:
      t_info = by_type.get(eval_type)
      if not isinstance(t_info, dict):
        continue
      t_passed = int(t_info.get("passed", 0) or 0)
      t_total = int(t_info.get("total", 0) or 0)
      t_failed = int(t_info.get("failed", max(t_total - t_passed, 0)) or 0)
      t_rate = (t_passed / t_total * 100.0) if t_total > 0 else 0.0
      label = EVAL_TYPE_LABELS.get(eval_type, f"`{eval_type}`")
      lines.append(
          f"| {label} | {t_passed} | {t_failed} | {t_total} | {t_rate:.2f}% |"
      )
    lines.append("")

  top_failures = data.get("top_failures")
  if isinstance(top_failures, list) and top_failures:
    lines.extend([
        "### Top Failures",
        "",
        "| Eval Name | Eval Type | Category | Run ID |",
        "| :--- | :--- | :--- | :--- |",
    ])
    for item in top_failures:
      if not isinstance(item, dict):
        continue
      eval_name = str(item.get("eval_name", "unknown"))
      eval_type = str(item.get("eval_type", "unknown"))
      category = str(item.get("category", "UNKNOWN"))
      run_id = str(item.get("run_id", "-"))
      lines.append(
          f"| `{eval_name}` | `{eval_type}` | `{category}` | `{run_id}` |"
      )
    lines.append("")

  if reasons:
    lines.extend([
        "### Gate Failure Reasons",
        "",
    ])
    for reason in reasons:
      lines.append(f"- {reason}")
    lines.append("")

  return "\n".join(lines)


def _write_github_outputs(
    github_output_path: str | None,
    gate_passed: bool,
    pass_rate: float,
) -> None:
  """Appends gate_passed and pass_rate to $GITHUB_OUTPUT if configured."""
  if not github_output_path:
    return
  path = Path(github_output_path)
  path.parent.mkdir(parents=True, exist_ok=True)
  with path.open("a", encoding="utf-8") as f:
    f.write(f"gate_passed={'true' if gate_passed else 'false'}\n")
    f.write(f"pass_rate={pass_rate * 100.0:.2f}%\n")


def _write_step_summary(
    step_summary_path: str | None,
    markdown: str,
) -> None:
  """Appends the Markdown scorecard to $GITHUB_STEP_SUMMARY if configured."""
  if not step_summary_path:
    return
  path = Path(step_summary_path)
  path.parent.mkdir(parents=True, exist_ok=True)
  with path.open("a", encoding="utf-8") as f:
    f.write(markdown + "\n")


def build_parser() -> argparse.ArgumentParser:
  parser = argparse.ArgumentParser(
      description=(
          "Validate CXAS evaluation summary JSON against a pass-rate threshold."
      )
  )
  parser.add_argument(
      "--summary",
      default="eval-reports/ci-summary.json",
      help="Path to the JSON summary emitted by run-and-report.py.",
  )
  parser.add_argument(
      "--threshold",
      type=float,
      default=0.90,
      help="Required pass rate ratio in [0.0, 1.0] (default: 0.90).",
  )
  parser.add_argument(
      "--comparison",
      choices=("gt", "ge"),
      default="gt",
      help=(
          "Comparison operator: 'gt' for strictly > threshold (default),"
          " or 'ge' for >= threshold."
      ),
  )
  parser.add_argument(
      "--step-summary",
      default=os.environ.get("GITHUB_STEP_SUMMARY"),
      help="Path to GitHub Actions step summary file (defaults to $GITHUB_STEP_SUMMARY).",
  )
  parser.add_argument(
      "--github-output",
      default=os.environ.get("GITHUB_OUTPUT"),
      help="Path to GitHub Actions output file (defaults to $GITHUB_OUTPUT).",
  )
  return parser


def main(argv: list[str] | None = None) -> int:
  parser = build_parser()
  args = parser.parse_args(argv)

  summary_path = Path(args.summary)
  summary_data: dict[str, Any] | None = None

  if not summary_path.is_file():
    reasons = [f"Summary file does not exist: {summary_path}"]
    gate_passed = False
    pass_rate = 0.0
  else:
    try:
      loaded = json.loads(summary_path.read_text(encoding="utf-8"))
      if not isinstance(loaded, dict):
        reasons = [f"Summary file root must be a JSON object: {summary_path}"]
        gate_passed = False
        pass_rate = 0.0
      else:
        summary_data = loaded
        gate_passed, pass_rate, reasons = evaluate_summary(
            summary_data=summary_data,
            threshold=args.threshold,
            comparison=args.comparison,
        )
    except json.JSONDecodeError as exc:
      reasons = [f"Invalid JSON in summary file {summary_path}: {exc}"]
      gate_passed = False
      pass_rate = 0.0

  markdown = render_markdown_scorecard(
      summary_data=summary_data,
      gate_passed=gate_passed,
      pass_rate=pass_rate,
      threshold=args.threshold,
      comparison=args.comparison,
      reasons=reasons,
  )

  print(markdown)
  _write_step_summary(args.step_summary, markdown)
  _write_github_outputs(args.github_output, gate_passed, pass_rate)

  return 0 if gate_passed else 1


if __name__ == "__main__":
  sys.exit(main())
