"""Unit and structural tests for the GitHub Actions CI/CD pipeline and >90% evaluation gate."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
from typing import Any
import pytest
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "check_eval_threshold.py"
PRE_PUSH_GATE_PATH = PROJECT_ROOT / "scripts" / "pre_push_gate.sh"
PUSH_TO_GITHUB_PATH = PROJECT_ROOT / "scripts" / "push_to_github.sh"
WORKFLOW_PATH = PROJECT_ROOT / ".github" / "workflows" / "cxas-eval-deploy.yml"


def _load_threshold_module() -> Any:
  """Dynamically loads scripts/check_eval_threshold.py."""
  assert SCRIPT_PATH.is_file(), f"Threshold gate script missing: {SCRIPT_PATH}"
  spec = importlib.util.spec_from_file_location("check_eval_threshold", SCRIPT_PATH)
  assert spec is not None and spec.loader is not None
  module = importlib.util.module_from_spec(spec)
  spec.loader.exec_module(module)
  return module


def _make_summary_payload(
    *,
    status: str = "complete",
    total: int = 20,
    passed: int = 19,
    failed: int | None = None,
    pass_rate: float | None = 0.95,
    platform_errors: list[Any] | None = None,
    top_failures: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
  """Builds a realistic `run-and-report.py --json-summary` payload."""
  actual_failed = (total - passed) if failed is None else failed
  payload: dict[str, Any] = {
      "status": status,
      "ran_at": "2026-09-30T17:55:00",
      "total": total,
      "passed": passed,
      "failed": actual_failed,
      "by_type": {
          "golden": {"passed": 11, "failed": 1 if actual_failed > 0 else 0, "total": 12},
          "sim": {"passed": 4, "failed": 0, "total": 4},
          "tool_test": {"passed": 3, "failed": 0, "total": 3},
          "callback_test": {"passed": 1, "failed": 0, "total": 1},
      },
      "top_failures": top_failures or [],
      "platform_errors": platform_errors or [],
      "reverted": False,
  }
  if pass_rate is not None:
    payload["pass_rate"] = pass_rate
  return payload


class TestCheckEvalThresholdGate:
  """Unit tests for scripts/check_eval_threshold.py."""

  def test_pass_case_above_90_percent_writes_outputs_and_exits_0(
      self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
  ) -> None:
    mod = _load_threshold_module()
    summary_file = tmp_path / "ci-summary.json"
    step_summary = tmp_path / "step_summary.md"
    github_output = tmp_path / "github_output.txt"

    payload = _make_summary_payload(
        status="complete",
        total=20,
        passed=19,
        pass_rate=0.95,
    )
    summary_file.write_text(json.dumps(payload), encoding="utf-8")

    rc = mod.main([
        "--summary",
        str(summary_file),
        "--threshold",
        "0.90",
        "--comparison",
        "gt",
        "--step-summary",
        str(step_summary),
        "--github-output",
        str(github_output),
    ])

    assert rc == 0
    stdout = capsys.readouterr().out
    assert "PASSED (> 90.0%)" in stdout
    assert "95.00%" in stdout
    assert "19/20" in stdout
    assert "Golden Conversations (`golden`)" in stdout

    assert step_summary.is_file()
    summary_md = step_summary.read_text(encoding="utf-8")
    assert "PASSED (> 90.0%)" in summary_md
    assert "### Breakdown by Evaluation Type" in summary_md

    assert github_output.is_file()
    output_lines = github_output.read_text(encoding="utf-8").strip().splitlines()
    assert "gate_passed=true" in output_lines
    assert "pass_rate=95.00%" in output_lines

  def test_boundary_exactly_90_percent_fails_gt_and_passes_ge(
      self, tmp_path: Path
  ) -> None:
    mod = _load_threshold_module()
    summary_file = tmp_path / "ci-summary-90.json"
    payload = _make_summary_payload(
        status="complete",
        total=20,
        passed=18,
        pass_rate=0.90,
    )
    summary_file.write_text(json.dumps(payload), encoding="utf-8")

    # Strict '>' (--comparison gt) must reject 90.0%
    gh_out_gt = tmp_path / "gh_output_gt.txt"
    step_gt = tmp_path / "step_gt.md"
    rc_gt = mod.main([
        "--summary",
        str(summary_file),
        "--threshold",
        "0.90",
        "--comparison",
        "gt",
        "--step-summary",
        str(step_gt),
        "--github-output",
        str(gh_out_gt),
    ])
    assert rc_gt == 1
    assert "gate_passed=false" in gh_out_gt.read_text(encoding="utf-8")
    assert "FAILED (<= 90.0%)" in step_gt.read_text(encoding="utf-8")

    # Inclusive '>=' (--comparison ge) must accept 90.0%
    gh_out_ge = tmp_path / "gh_output_ge.txt"
    step_ge = tmp_path / "step_ge.md"
    rc_ge = mod.main([
        "--summary",
        str(summary_file),
        "--threshold",
        "0.90",
        "--comparison",
        "ge",
        "--step-summary",
        str(step_ge),
        "--github-output",
        str(gh_out_ge),
    ])
    assert rc_ge == 0
    assert "gate_passed=true" in gh_out_ge.read_text(encoding="utf-8")
    assert "PASSED (>= 90.0%)" in step_ge.read_text(encoding="utf-8")

  def test_below_threshold_85_percent_exits_1_and_lists_top_failures(
      self, tmp_path: Path
  ) -> None:
    mod = _load_threshold_module()
    summary_file = tmp_path / "ci-summary-85.json"
    step_summary = tmp_path / "step_85.md"
    github_output = tmp_path / "gh_output_85.txt"

    payload = _make_summary_payload(
        status="complete",
        total=20,
        passed=17,
        pass_rate=0.85,
        top_failures=[
            {
                "eval_name": "Golden 4: Merch Return Flow",
                "eval_type": "golden",
                "category": "EXPECTATION_FAIL",
                "run_id": "run-abc123",
            },
            {
                "eval_name": "Sim 2: Timezone Clarification",
                "eval_type": "sim",
                "category": "SIM_TASK_INCOMPLETE",
                "run_id": "run-abc123",
            },
        ],
    )
    summary_file.write_text(json.dumps(payload), encoding="utf-8")

    rc = mod.main([
        "--summary",
        str(summary_file),
        "--threshold",
        "0.90",
        "--comparison",
        "gt",
        "--step-summary",
        str(step_summary),
        "--github-output",
        str(github_output),
    ])

    assert rc == 1
    assert "gate_passed=false" in github_output.read_text(encoding="utf-8")
    md = step_summary.read_text(encoding="utf-8")
    assert "FAILED (<= 90.0%)" in md
    assert "85.00%" in md
    assert "### Top Failures" in md
    assert "Golden 4: Merch Return Flow" in md
    assert "EXPECTATION_FAIL" in md
    assert "Sim 2: Timezone Clarification" in md

  def test_errored_status_fails_even_with_high_pass_rate(
      self, tmp_path: Path
  ) -> None:
    mod = _load_threshold_module()
    summary_file = tmp_path / "ci-summary-errored.json"
    github_output = tmp_path / "gh_output_err.txt"
    payload = _make_summary_payload(
        status="errored",
        total=20,
        passed=20,
        pass_rate=1.0,
    )
    summary_file.write_text(json.dumps(payload), encoding="utf-8")

    rc = mod.main([
        "--summary",
        str(summary_file),
        "--github-output",
        str(github_output),
    ])
    assert rc == 1
    assert "gate_passed=false" in github_output.read_text(encoding="utf-8")

  def test_platform_errors_fail_gate(self, tmp_path: Path) -> None:
    mod = _load_threshold_module()
    summary_file = tmp_path / "ci-summary-plat-err.json"
    step_summary = tmp_path / "step_plat_err.md"
    github_output = tmp_path / "gh_output_plat_err.txt"
    payload = _make_summary_payload(
        status="partial",
        total=20,
        passed=19,
        pass_rate=0.95,
        platform_errors=["RPC timeout"],
    )
    summary_file.write_text(json.dumps(payload), encoding="utf-8")

    rc = mod.main([
        "--summary",
        str(summary_file),
        "--step-summary",
        str(step_summary),
        "--github-output",
        str(github_output),
    ])
    assert rc == 1
    assert "gate_passed=false" in github_output.read_text(encoding="utf-8")
    assert "Platform errors detected" in step_summary.read_text(encoding="utf-8")

  def test_zero_total_and_missing_file_fail_gate(self, tmp_path: Path) -> None:
    mod = _load_threshold_module()

    # Zero total
    zero_file = tmp_path / "ci-summary-zero.json"
    gh_zero = tmp_path / "gh_zero.txt"
    payload = _make_summary_payload(
        status="complete",
        total=0,
        passed=0,
        pass_rate=0.0,
    )
    zero_file.write_text(json.dumps(payload), encoding="utf-8")
    assert mod.main(["--summary", str(zero_file), "--github-output", str(gh_zero)]) == 1
    assert "gate_passed=false" in gh_zero.read_text(encoding="utf-8")

    # Missing file
    missing_file = tmp_path / "does-not-exist.json"
    gh_missing = tmp_path / "gh_missing.txt"
    assert mod.main(["--summary", str(missing_file), "--github-output", str(gh_missing)]) == 1
    assert "gate_passed=false" in gh_missing.read_text(encoding="utf-8")

  def test_computes_pass_rate_from_passed_and_total_when_pass_rate_missing(
      self, tmp_path: Path
  ) -> None:
    mod = _load_threshold_module()
    summary_file = tmp_path / "ci-summary-no-rate.json"
    gh_out = tmp_path / "gh_no_rate.txt"
    payload = _make_summary_payload(
        status="complete",
        total=30,
        passed=28,
        pass_rate=None,
    )
    summary_file.write_text(json.dumps(payload), encoding="utf-8")

    rc = mod.main([
        "--summary",
        str(summary_file),
        "--threshold",
        "0.90",
        "--comparison",
        "gt",
        "--github-output",
        str(gh_out),
    ])
    assert rc == 0
    out_text = gh_out.read_text(encoding="utf-8")
    assert "gate_passed=true" in out_text
    assert "pass_rate=93.33%" in out_text


class TestGitHubWorkflowStructure:
  """Structural validation tests for .github/workflows/cxas-eval-deploy.yml and pre-push scripts."""

  def _load_workflow(self) -> dict[str, Any]:
    assert WORKFLOW_PATH.is_file(), f"Workflow YAML missing: {WORKFLOW_PATH}"
    data = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data

  def test_workflow_yaml_is_valid_and_has_triggers_and_env(self) -> None:
    wf = self._load_workflow()
    triggers = wf.get("on") or wf.get(True)
    assert isinstance(triggers, dict), "Workflow must define triggers under 'on:'"
    assert "push" in triggers
    assert "main" in triggers["push"].get("branches", [])
    assert "pull_request" in triggers
    assert "main" in triggers["pull_request"].get("branches", [])
    assert "workflow_dispatch" in triggers
    dispatch_inputs = triggers["workflow_dispatch"].get("inputs", {})
    for expected_input in (
        "gcp_project_id",
        "gcp_location",
        "target_app_id",
        "eval_runs",
        "threshold",
    ):
      assert expected_input in dispatch_inputs

    env = wf.get("env", {})
    assert "GCP_PROJECT_ID" in env
    assert "GCP_LOCATION" in env
    assert env.get("APP_DIR") == "cxas_app/totto_mercedes_f1_agent"
    assert "0.90" in str(env.get("EVAL_THRESHOLD"))

  def test_workflow_has_all_three_jobs_and_dependency_chain(self) -> None:
    wf = self._load_workflow()
    jobs = wf.get("jobs", {})
    assert "lint-and-unit-test" in jobs
    assert "evaluate-and-gate" in jobs
    assert "push-to-project" in jobs

    eval_job = jobs["evaluate-and-gate"]
    assert eval_job.get("needs") == "lint-and-unit-test"
    assert "gate_passed" in eval_job.get("outputs", {})
    assert "pass_rate" in eval_job.get("outputs", {})

    push_job = jobs["push-to-project"]
    assert push_job.get("needs") == "evaluate-and-gate"
    push_if = str(push_job.get("if", ""))
    assert "needs.evaluate-and-gate.outputs.gate_passed == 'true'" in push_if

  def test_workflow_steps_invoke_lint_pytest_evals_gate_and_push(self) -> None:
    raw_yaml = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "cxas lint --app-dir cxas_app/totto_mercedes_f1_agent" in raw_yaml
    assert "pytest" in raw_yaml
    assert "run-and-report.py" in raw_yaml
    assert "--json-summary eval-reports/ci-summary.json" in raw_yaml
    assert "scripts/check_eval_threshold.py" in raw_yaml
    assert "--comparison gt" in raw_yaml
    assert "cxas push" in raw_yaml
    assert "gate-check.py" in raw_yaml
    assert "--skip-push" in raw_yaml

  def test_workflow_uses_only_vendored_foundry_harness(self) -> None:
    """CI runners have no $HOME/.agents; the harness must be vendored in-repo."""
    raw_yaml = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "$HOME/.agents" not in raw_yaml
    assert "~/.agents" not in raw_yaml
    assert ".agents/skills/cxas-agent-foundry/scripts" in raw_yaml

    vendored_scripts = PROJECT_ROOT / ".agents" / "skills" / "cxas-agent-foundry" / "scripts"
    for script in ("run-and-report.py", "lint-harness.py", "gate-check.py", "config.py"):
      assert (vendored_scripts / script).is_file(), f"Vendored harness script missing: {script}"
    # The foundry scripts resolve the project via CWD gecx-config.json in CI.
    assert (PROJECT_ROOT / "gecx-config.json").is_file()

  def test_workflow_run_steps_use_strict_bash(self) -> None:
    wf = self._load_workflow()
    for job_id, job in wf["jobs"].items():
      for step in job.get("steps", []):
        script = step.get("run")
        if script is None:
          continue
        if step.get("name") == "Job summary":
          # Summary step is best-effort and must not mask the real status.
          continue
        assert "set -euo pipefail" in script, (
            f"Step '{step.get('name')}' in job '{job_id}' must start with set -euo pipefail"
        )

  def test_workflow_deployment_jobs_are_environment_protected(self) -> None:
    wf = self._load_workflow()
    jobs = wf["jobs"]
    assert jobs["push-to-project"].get("environment") == "production"
    assert jobs["evaluate-and-gate"].get("environment") == "staging"
    assert "environment" not in jobs["lint-and-unit-test"]

  def test_workflow_has_non_cancelling_concurrency_group(self) -> None:
    wf = self._load_workflow()
    concurrency = wf.get("concurrency")
    assert isinstance(concurrency, dict)
    assert "cxas-eval-deploy-" in str(concurrency.get("group"))
    assert "github.ref" in str(concurrency.get("group"))
    assert concurrency.get("cancel-in-progress") is False

  def test_workflow_installs_requirements_txt_after_ces_tarball(self) -> None:
    wf = self._load_workflow()
    assert (PROJECT_ROOT / "requirements.txt").is_file()
    assert not (PROJECT_ROOT / "pyproject.toml").exists(), (
        "pyproject.toml would route CI to `uv sync` and skip the CES tarball install"
    )
    for job_id, job in wf["jobs"].items():
      install_steps = [
          s for s in job.get("steps", [])
          if s.get("name") == "Install dependencies and cxas-scrapi CLI"
      ]
      assert len(install_steps) == 1, f"Job '{job_id}' must have exactly one install step"
      script = install_steps[0]["run"]
      tar_idx = script.index("ces-v1beta-py.tar")
      req_idx = script.index("uv pip install -r requirements.txt")
      assert tar_idx < req_idx, f"Job '{job_id}' must install the CES tarball before requirements.txt"
      # Fallback list kept for repos without requirements.txt.
      assert "uv pip install cxas-scrapi pytest pyyaml pydantic requests" in script

  def test_workflow_push_steps_retry_with_display_name_on_first_run(self) -> None:
    wf = self._load_workflow()
    jobs = wf["jobs"]
    push_steps = {
        "evaluate-and-gate": "Push candidate build to staging evaluation app",
        "push-to-project": "Push verified agent to target GCP project",
    }
    for job_id, step_name in push_steps.items():
      matching = [s for s in jobs[job_id]["steps"] if s.get("name") == step_name]
      assert len(matching) == 1, f"Missing push step '{step_name}' in '{job_id}'"
      script = matching[0]["run"]
      assert "--to " in script
      assert 'grep -q "not found"' in script
      assert "--display-name" in script
      # cxas only creates a new app when --to is omitted; the retry must not pass it.
      retry_block = script.split("--display-name", 1)[1]
      assert "--to " not in retry_block.split("else", 1)[0]
      assert "app_name=" in script and "GITHUB_OUTPUT" in script

  def test_workflow_gate_has_explicit_failure_step_and_prod_summary(self) -> None:
    wf = self._load_workflow()
    jobs = wf["jobs"]

    eval_steps = jobs["evaluate-and-gate"]["steps"]
    gate_steps = [s for s in eval_steps if s.get("id") == "eval_gate"]
    assert len(gate_steps) == 1
    assert "--threshold ${{ env.EVAL_THRESHOLD }}" in gate_steps[0]["run"]

    fail_steps = [s for s in eval_steps if "gate did not pass" in str(s.get("name", "")).lower()]
    assert len(fail_steps) == 1, "evaluate-and-gate must have an explicit gate-failure step"
    fail_script = fail_steps[0]["run"]
    assert fail_steps[0].get("if") == "always()"
    assert "steps.eval_gate.outputs.gate_passed" in fail_script
    assert '!= "true"' in fail_script
    assert "exit 1" in fail_script
    # The failure step must run after the gate step.
    assert eval_steps.index(fail_steps[0]) > eval_steps.index(gate_steps[0])

    prod_steps = jobs["push-to-project"]["steps"]
    summary_steps = [s for s in prod_steps if s.get("name") == "Job summary"]
    assert len(summary_steps) == 1
    summary_script = summary_steps[0]["run"]
    assert "needs.evaluate-and-gate.outputs.pass_rate" in summary_script
    assert "GITHUB_STEP_SUMMARY" in summary_script


class TestRepoIsSelfContainedForCI:
  """Checks that the repo carries everything the workflow needs on a clean runner."""

  def test_vendored_foundry_skill_has_no_bytecode_caches(self) -> None:
    skill_root = PROJECT_ROOT / ".agents" / "skills" / "cxas-agent-foundry"
    assert (skill_root / "SKILL.md").is_file()
    caches = [p for p in skill_root.rglob("*") if p.name in ("__pycache__", ".pytest_cache")]
    assert caches == [], f"Vendored skill should not ship caches: {caches}"

  def test_gitignore_excludes_secrets_scratch_and_build_artifacts(self) -> None:
    gitignore = PROJECT_ROOT / ".gitignore"
    assert gitignore.is_file()
    lines = {ln.strip() for ln in gitignore.read_text(encoding="utf-8").splitlines()}
    for required in (
        ".venv/",
        "__pycache__/",
        ".pytest_cache/",
        "eval-reports/",
        ".agents/teamwork/",
        "*.egg-info/",
        ".env",
        ".env.*",
        "*.log",
        ".DS_Store",
        ".active-project",
        "gh-token*",
        "*.tar",
    ):
      assert required in lines, f".gitignore missing pattern: {required}"
    assert "*.pyc" in lines or "*.py[cod]" in lines

  def test_requirements_txt_pins_core_dependencies(self) -> None:
    req = (PROJECT_ROOT / "requirements.txt").read_text(encoding="utf-8")
    for dep in ("cxas-scrapi>=1.8.0", "pytest>=8", "pyyaml>=6", "pydantic>=2", "requests>=2.31"):
      assert dep in req, f"requirements.txt missing {dep}"

  def test_pytest_ini_scopes_collection_away_from_vendored_skill(self) -> None:
    ini = (PROJECT_ROOT / "pytest.ini").read_text(encoding="utf-8")
    assert "testpaths = tests evals" in ini
    assert ".agents" in ini

  def test_pre_push_scripts_exist_are_executable_and_tests_are_path_portable(
      self,
  ) -> None:
    assert PRE_PUSH_GATE_PATH.is_file(), f"Missing {PRE_PUSH_GATE_PATH}"
    assert os.access(PRE_PUSH_GATE_PATH, os.X_OK), f"Not executable: {PRE_PUSH_GATE_PATH}"
    assert PUSH_TO_GITHUB_PATH.is_file(), f"Missing {PUSH_TO_GITHUB_PATH}"
    assert os.access(PUSH_TO_GITHUB_PATH, os.X_OK), f"Not executable: {PUSH_TO_GITHUB_PATH}"

    pre_push_text = PRE_PUSH_GATE_PATH.read_text(encoding="utf-8")
    assert "cxas lint" in pre_push_text
    assert "lint-harness.py" in pre_push_text
    assert "pytest" in pre_push_text
    assert "check_eval_threshold.py" in pre_push_text

    push_gh_text = PUSH_TO_GITHUB_PATH.read_text(encoding="utf-8")
    assert "pre_push_gate.sh" in push_gh_text
    assert "git push" in push_gh_text

    forbidden_prefix = "/usr/local/google/" + "home/keerthanaguru/my_cxas_agent"
    for py_file in (PROJECT_ROOT / "tests").rglob("*.py"):
      content = py_file.read_text(encoding="utf-8")
      assert forbidden_prefix not in content, (
          f"Hardcoded workstation path found in {py_file}"
      )
    for py_file in (PROJECT_ROOT / "evals" / "callback_tests").rglob("*.py"):
      content = py_file.read_text(encoding="utf-8")
      assert forbidden_prefix not in content, (
          f"Hardcoded workstation path found in {py_file}"
      )

  def test_defined_gates_runner_and_pre_push_hook_are_executable_and_pass(
      self,
  ) -> None:
    defined_gates_path = PROJECT_ROOT / "scripts" / "run_defined_gates.py"
    git_pre_push_hook = PROJECT_ROOT / ".githooks" / "pre-push"

    assert defined_gates_path.is_file(), f"Missing {defined_gates_path}"
    assert os.access(defined_gates_path, os.X_OK), (
        f"Not executable: {defined_gates_path}"
    )
    assert git_pre_push_hook.is_file(), f"Missing {git_pre_push_hook}"
    assert os.access(git_pre_push_hook, os.X_OK), (
        f"Not executable: {git_pre_push_hook}"
    )
    hook_text = git_pre_push_hook.read_text(encoding="utf-8")
    assert "scripts/run_defined_gates.py" in hook_text

    spec = importlib.util.spec_from_file_location(
        "run_defined_gates", defined_gates_path
    )
    assert spec is not None and spec.loader is not None
    gates_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gates_mod)

    g1_passed, g1_errors = gates_mod.gate_1_lifecycle_and_architecture(
        PROJECT_ROOT
    )
    assert g1_passed is True, f"Gate 1 failed: {g1_errors}"

    g5_passed, g5_errors = gates_mod.gate_5_eval_threshold_gate(PROJECT_ROOT)
    assert g5_passed is True, f"Gate 5 failed: {g5_errors}"

    report_json_path = (
        PROJECT_ROOT / "eval-reports" / "gate_verification_report.json"
    )
    report_md_path = (
        PROJECT_ROOT / "eval-reports" / "GATE_VERIFICATION_REPORT.md"
    )
    assert report_json_path.is_file()
    assert report_md_path.is_file()

    report_data = json.loads(report_json_path.read_text(encoding="utf-8"))
    assert report_data.get("status") == "complete"
    assert float(report_data.get("pass_rate", 0.0)) > 0.90
    assert "PASSED (> 90.0%)" in report_md_path.read_text(encoding="utf-8")

  def test_pr_cleanup_workflow_yaml_is_valid_and_has_expected_triggers(
      self,
  ) -> None:
    cleanup_path = PROJECT_ROOT / ".github" / "workflows" / "cxas-pr-cleanup.yml"
    assert cleanup_path.is_file(), f"Missing {cleanup_path}"
    wf = yaml.safe_load(cleanup_path.read_text(encoding="utf-8"))
    assert isinstance(wf, dict)
    triggers = wf.get("on") or wf.get(True)
    assert isinstance(triggers, dict)
    assert "pull_request" in triggers
    assert "closed" in triggers["pull_request"].get("types", [])
    assert "workflow_dispatch" in triggers

