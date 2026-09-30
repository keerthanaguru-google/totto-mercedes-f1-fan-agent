#!/usr/bin/env bash
# Pre-Push 5-Gate Verification Script for Totto, Mercedes F1 Fan Agent
# Enforces all 5 quality and evaluation gates before allowing a Git push.

set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

echo "============================================================"
echo "  CXAS Pre-Push 5-Gate Verification Suite"
echo "  Project Root: ${PROJECT_ROOT}"
echo "============================================================"

# ------------------------------------------------------------------------------
# Gate 1: CXAS Structural Linter
# ------------------------------------------------------------------------------
echo ""
echo "[Gate 1/5] Running CXAS Structural Linter..."
uv run --no-project cxas lint --app-dir cxas_app/totto_mercedes_f1_agent

# ------------------------------------------------------------------------------
# Gate 2: CXAS Foundry Zero-Warnings Lint Harness
# ------------------------------------------------------------------------------
echo ""
echo "[Gate 2/5] Running CXAS Foundry Zero-Warnings Lint Harness..."
HARNESS_SCRIPT="${PROJECT_ROOT}/.agents/skills/cxas-agent-foundry/scripts/lint-harness.py"
if [[ ! -f "${HARNESS_SCRIPT}" ]]; then
  HARNESS_SCRIPT="${HOME}/.agents/skills/cxas-agent-foundry/scripts/lint-harness.py"
fi
uv run --no-project python "${HARNESS_SCRIPT}" .

# ------------------------------------------------------------------------------
# Gate 3: Full Pytest Suite (Unit, Tool, Callback, Boundary, Adversarial & CI)
# ------------------------------------------------------------------------------
echo ""
echo "[Gate 3/5] Running Full Pytest Suite..."
uv run --no-project pytest -q

# ------------------------------------------------------------------------------
# Gate 4: >90% Evaluation Pass-Rate Threshold Gate Verification
# ------------------------------------------------------------------------------
echo ""
echo "[Gate 4/5] Verifying >90% Evaluation Threshold Gate..."
if [[ -f "eval-reports/ci-summary.json" ]]; then
  echo "  Found eval-reports/ci-summary.json — validating >90% pass rate..."
  uv run --no-project python scripts/check_eval_threshold.py \
    --summary eval-reports/ci-summary.json \
    --threshold 0.90 \
    --comparison gt
fi

# Run deterministic self-test of check_eval_threshold.py (>90% pass, <=90% blocked)
TMP_GATE_DIR="$(mktemp -d)"
trap 'rm -rf "${TMP_GATE_DIR}"' EXIT

cat > "${TMP_GATE_DIR}/pass_95.json" <<'EOF'
{
  "status": "complete",
  "ran_at": "2026-09-30T18:00:00",
  "total": 20,
  "passed": 19,
  "failed": 1,
  "pass_rate": 0.95,
  "by_type": {
    "golden": {"passed": 11, "failed": 1, "total": 12},
    "sim": {"passed": 4, "failed": 0, "total": 4},
    "tool_test": {"passed": 3, "failed": 0, "total": 3},
    "callback_test": {"passed": 1, "failed": 0, "total": 1}
  },
  "top_failures": [],
  "platform_errors": [],
  "reverted": false
}
EOF

cat > "${TMP_GATE_DIR}/fail_90.json" <<'EOF'
{
  "status": "complete",
  "ran_at": "2026-09-30T18:00:00",
  "total": 20,
  "passed": 18,
  "failed": 2,
  "pass_rate": 0.90,
  "by_type": {},
  "top_failures": [],
  "platform_errors": [],
  "reverted": false
}
EOF

uv run --no-project python scripts/check_eval_threshold.py \
  --summary "${TMP_GATE_DIR}/pass_95.json" \
  --threshold 0.90 \
  --comparison gt > /dev/null

if uv run --no-project python scripts/check_eval_threshold.py \
  --summary "${TMP_GATE_DIR}/fail_90.json" \
  --threshold 0.90 \
  --comparison gt > /dev/null 2>&1; then
  echo "ERROR: Gate 4 self-test failed — 90.0% was not rejected by strict '> 0.90' check!"
  exit 1
fi
echo "  Gate 4 self-test PASSED (>90% accepted, <=90% rejected)."

# ------------------------------------------------------------------------------
# Gate 5: Workflow & Artifact Integrity Check
# ------------------------------------------------------------------------------
echo ""
echo "[Gate 5/5] Verifying Workflow & Artifact Integrity..."
REQUIRED_FILES=(
  "prd.md"
  "tdd.md"
  "todo.md"
  "gecx-config.json"
  "cxaslint.yaml"
  "cxas_app/totto_mercedes_f1_agent/app.json"
  "evals/goldens/goldens.yaml"
  "evals/simulations/simulations.yaml"
  "evals/tool_tests/tool_tests.yaml"
  ".github/workflows/cxas-eval-deploy.yml"
  ".github/workflows/cxas-pr-cleanup.yml"
)

for req_file in "${REQUIRED_FILES[@]}"; do
  if [[ ! -f "${req_file}" ]]; then
    echo "ERROR: Required project file missing: ${req_file}"
    exit 1
  fi
done

uv run --no-project python -c '
import json, pathlib, yaml

json_files = [
    "gecx-config.json",
    "cxas_app/totto_mercedes_f1_agent/app.json",
]
yaml_files = [
    "cxaslint.yaml",
    "evals/goldens/goldens.yaml",
    "evals/simulations/simulations.yaml",
    "evals/tool_tests/tool_tests.yaml",
    ".github/workflows/cxas-eval-deploy.yml",
    ".github/workflows/cxas-pr-cleanup.yml",
]

for jf in json_files:
    data = json.loads(pathlib.Path(jf).read_text(encoding="utf-8"))
    assert isinstance(data, dict), f"Expected JSON object in {jf}"

for yf in yaml_files:
    data = yaml.safe_load(pathlib.Path(yf).read_text(encoding="utf-8"))
    assert data is not None, f"Empty YAML in {yf}"

print("  All JSON and YAML artifacts parsed cleanly.")
'

echo ""
echo "============================================================"
echo "  ALL 5 PRE-PUSH GATES PASSED!"
echo "============================================================"
