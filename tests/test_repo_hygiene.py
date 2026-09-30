"""Repository hygiene tests: ignore rules, vendored CI scripts, governance files.

These tests guard the properties that make the repository safe to publish to
GitHub and runnable on a clean `ubuntu-latest` runner:

* `.gitignore` excludes virtualenvs, caches, secrets, and internal-only notes.
* The `cxas-agent-foundry` skill scripts the workflows depend on are vendored.
* `scripts/setup_github_repo.sh` is executable and syntactically valid bash.
* The `main` branch ruleset requires the Stage 1 and Stage 2 status checks.
* No tracked file references a Google-internal workspace path.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
GITIGNORE = PROJECT_ROOT / ".gitignore"
RULESET = PROJECT_ROOT / ".github" / "rulesets" / "main-branch-protection.json"
CODEOWNERS = PROJECT_ROOT / ".github" / "CODEOWNERS"
SETUP_SCRIPT = PROJECT_ROOT / "scripts" / "setup_github_repo.sh"
VENDORED_SCRIPTS_DIR = (
    PROJECT_ROOT / ".agents" / "skills" / "cxas-agent-foundry" / "scripts"
)

REQUIRED_IGNORE_PATTERNS = (
    ".venv/",
    ".pytest_cache/",
    "__pycache__/",
    "*.pyc",
    "eval-reports/",
    ".active-project",
    "*.egg-info",
    ".env",
    ".env.*",
    "*.tar",
    ".agents/teamwork/",
    "ORIGINAL_REQUEST.md",
    "PROJECT.md",
    "TEST_INFRA.md",
    "TEST_READY.md",
)

REQUIRED_STATUS_CHECKS = (
    "Stage 1: CXAS Lint & Local Unit Tests",
    "Stage 2: CES Evaluation Suite & >90% Pass-Rate Gate",
)

VENDORED_SCRIPTS = ("run-and-report.py", "lint-harness.py", "gate-check.py")

INTERNAL_PATH_MARKERS = ("/google/src/cloud",)

# Internal-only notes that must never be tracked even if present on disk.
FORBIDDEN_TRACKED_PATTERNS = (
    ".agents/teamwork/",
    "ORIGINAL_REQUEST.md",
    "PROJECT.md",
    "TEST_INFRA.md",
    "TEST_READY.md",
    ".venv/",
    "__pycache__/",
    ".pyc",
)


def _gitignore_lines() -> list[str]:
  assert GITIGNORE.is_file(), f"Missing .gitignore at {GITIGNORE}"
  return [
      line.strip()
      for line in GITIGNORE.read_text(encoding="utf-8").splitlines()
      if line.strip() and not line.strip().startswith("#")
  ]


def _tracked_files() -> list[Path]:
  """Returns files that would be committed.

  Uses `git ls-files` when the repository is initialised; otherwise falls back
  to a manual walk that honours the top-level ignore list.
  """
  git = shutil.which("git")
  if git and (PROJECT_ROOT / ".git").exists():
    proc = subprocess.run(
        [git, "ls-files", "-z"],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        check=False,
    )
    if proc.returncode == 0:
      return [
          PROJECT_ROOT / p.decode("utf-8")
          for p in proc.stdout.split(b"\0")
          if p
      ]

  ignored = set(_gitignore_lines())
  ignored_dirs = {p.rstrip("/") for p in ignored if p.endswith("/")}
  ignored_names = {p for p in ignored if not p.endswith("/") and "*" not in p}
  ignored_suffixes = {p[1:] for p in ignored if p.startswith("*.")}
  files: list[Path] = []
  for root, dirs, names in os.walk(PROJECT_ROOT):
    rel_root = Path(root).relative_to(PROJECT_ROOT)
    dirs[:] = [
        d
        for d in dirs
        if d != ".git"
        and d not in ignored_dirs
        and str(rel_root / d) not in ignored_dirs
    ]
    for name in names:
      rel = rel_root / name
      if name in ignored_names or str(rel) in ignored_names:
        continue
      if any(name.endswith(s) for s in ignored_suffixes):
        continue
      files.append(PROJECT_ROOT / rel)
  return files


class TestGitignore:
  """The ignore file must exclude every required artifact class."""

  @pytest.mark.parametrize("pattern", REQUIRED_IGNORE_PATTERNS)
  def test_required_pattern_present(self, pattern: str) -> None:
    lines = _gitignore_lines()
    assert pattern in lines, f".gitignore is missing required pattern {pattern!r}"

  def test_vendored_skill_is_not_ignored(self) -> None:
    """`.agents/teamwork/` is ignored but `.agents/skills/` must stay tracked."""
    lines = _gitignore_lines()
    assert ".agents/" not in lines and ".agents" not in lines, (
        ".gitignore must not ignore the whole .agents/ tree; the vendored"
        " cxas-agent-foundry skill under .agents/skills/ is required by CI"
    )


class TestVendoredSkill:
  """CI workflows call these scripts from the repo root on ubuntu-latest."""

  @pytest.mark.parametrize("script", VENDORED_SCRIPTS)
  def test_vendored_script_exists(self, script: str) -> None:
    path = VENDORED_SCRIPTS_DIR / script
    assert path.is_file(), f"Vendored CI script missing: {path}"
    assert path.stat().st_size > 0, f"Vendored CI script is empty: {path}"

  @pytest.mark.parametrize("script", VENDORED_SCRIPTS)
  def test_vendored_script_has_portable_shebang(self, script: str) -> None:
    first_line = (VENDORED_SCRIPTS_DIR / script).read_text(
        encoding="utf-8"
    ).splitlines()[0]
    assert first_line.startswith("#!/usr/bin/env python"), (
        f"{script} shebang must be portable (#!/usr/bin/env python3), got"
        f" {first_line!r}"
    )

  def test_no_pycache_vendored(self) -> None:
    skill_root = VENDORED_SCRIPTS_DIR.parent
    caches = [p for p in skill_root.rglob("__pycache__") if p.is_dir()]
    tracked = {p for p in _tracked_files() if skill_root in p.parents}
    tracked_caches = [p for p in tracked if "__pycache__" in p.parts]
    assert not tracked_caches, f"Tracked bytecode caches: {tracked_caches}"
    del caches  # On-disk caches are tolerated; only tracked ones matter.


class TestSetupScript:
  """The GitHub bootstrap script must be executable and parse cleanly."""

  def test_setup_script_is_executable(self) -> None:
    assert SETUP_SCRIPT.is_file(), f"Missing {SETUP_SCRIPT}"
    assert os.access(SETUP_SCRIPT, os.X_OK), f"{SETUP_SCRIPT} is not executable"

  def test_setup_script_parses_with_bash(self) -> None:
    proc = subprocess.run(
        ["bash", "-n", str(SETUP_SCRIPT)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, f"bash -n failed:\n{proc.stderr}"

  def test_setup_script_uses_strict_mode(self) -> None:
    text = SETUP_SCRIPT.read_text(encoding="utf-8")
    assert "set -euo pipefail" in text


class TestBranchRuleset:
  """The main-branch ruleset must gate merges on Stage 1 and Stage 2."""

  def _ruleset(self) -> dict:
    assert RULESET.is_file(), f"Missing ruleset file: {RULESET}"
    data = json.loads(RULESET.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data

  def test_ruleset_is_valid_json_targeting_main(self) -> None:
    data = self._ruleset()
    assert data.get("target") == "branch"
    assert data.get("enforcement") == "active"
    includes = data["conditions"]["ref_name"]["include"]
    assert "refs/heads/main" in includes or "~DEFAULT_BRANCH" in includes

  def test_ruleset_requires_stage1_and_stage2_checks(self) -> None:
    data = self._ruleset()
    checks = [r for r in data["rules"] if r.get("type") == "required_status_checks"]
    assert len(checks) == 1, "Expected exactly one required_status_checks rule"
    params = checks[0]["parameters"]
    contexts = {c["context"] for c in params["required_status_checks"]}
    for required in REQUIRED_STATUS_CHECKS:
      assert required in contexts, f"Ruleset missing status check {required!r}"
    assert params.get("strict_required_status_checks_policy") is True

  def test_ruleset_requires_pull_request_review(self) -> None:
    data = self._ruleset()
    pr_rules = [r for r in data["rules"] if r.get("type") == "pull_request"]
    assert pr_rules, "Ruleset must include a pull_request rule"
    assert pr_rules[0]["parameters"]["required_approving_review_count"] >= 1

  def test_ruleset_blocks_deletion_and_force_push(self) -> None:
    data = self._ruleset()
    types = {r.get("type") for r in data["rules"]}
    assert {"deletion", "non_fast_forward", "required_linear_history"} <= types


class TestCodeowners:

  def test_codeowners_has_concrete_owner(self) -> None:
    assert CODEOWNERS.is_file(), f"Missing {CODEOWNERS}"
    text = CODEOWNERS.read_text(encoding="utf-8")
    assert "__GITHUB_OWNER__" not in text, "CODEOWNERS placeholder not substituted"
    rules = [l for l in text.splitlines() if l.strip() and not l.startswith("#")]
    assert any(r.split()[0] == "*" and "@" in r for r in rules), (
        "CODEOWNERS must contain a catch-all `* @owner` rule"
    )


class TestNoInternalArtifacts:
  """Nothing that would be committed may leak internal paths or scratch notes."""

  def test_no_forbidden_files_tracked(self) -> None:
    offenders = []
    for path in _tracked_files():
      rel = path.relative_to(PROJECT_ROOT).as_posix()
      if any(
          (pat.endswith("/") and pat in rel + "/")
          or (not pat.endswith("/") and (rel == pat or rel.endswith(pat)))
          for pat in FORBIDDEN_TRACKED_PATTERNS
      ):
        offenders.append(rel)
    assert not offenders, f"Internal-only files would be committed: {offenders}"

  def test_no_tracked_file_contains_internal_workspace_path(self) -> None:
    offenders: list[str] = []
    for path in _tracked_files():
      if path.resolve() == Path(__file__).resolve():
        continue  # This file names the marker in order to search for it.
      try:
        text = path.read_text(encoding="utf-8")
      except (UnicodeDecodeError, OSError):
        continue
      for marker in INTERNAL_PATH_MARKERS:
        if marker in text:
          offenders.append(f"{path.relative_to(PROJECT_ROOT)} ({marker})")
    assert not offenders, f"Internal workspace paths found: {offenders}"
