#!/usr/bin/env bash
# =============================================================================
# scripts/setup_github_repo.sh
#
# Idempotent bootstrap for publishing the Totto Mercedes F1 Fan Agent to GitHub
# with governance that matches .github/workflows/cxas-eval-deploy.yml:
#
#   (a) install the `gh` CLI into ~/.local/bin if missing and authenticate
#   (b) `git init -b main`, configure identity, commit the working tree
#   (c) create the GitHub repository (or reuse it) and push `main`
#   (d) substitute __GITHUB_OWNER__ in .github/CODEOWNERS
#   (e) set Actions repository variables and (optional) secrets
#   (f) create the `staging` and `production` environments
#       (production = required reviewer + deployments restricted to `main`)
#   (g) apply the `main` branch ruleset from
#       .github/rulesets/main-branch-protection.json (create or update)
#   (h) print a summary with next steps
#
# Every step is safe to re-run. Use --dry-run to print every command without
# executing anything (no network, no git mutations, no gh install).
#
# Usage:
#   GITHUB_OWNER=me GITHUB_REPO=my_cxas_agent GITHUB_TOKEN=ghp_xxx \
#     scripts/setup_github_repo.sh [--dry-run]
#
# Run `scripts/setup_github_repo.sh --help` for all inputs.
# =============================================================================
set -euo pipefail

# -----------------------------------------------------------------------------
# Constants
# -----------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
RULESET_FILE="${PROJECT_ROOT}/.github/rulesets/main-branch-protection.json"
CODEOWNERS_FILE="${PROJECT_ROOT}/.github/CODEOWNERS"
CODEOWNERS_PLACEHOLDER="__GITHUB_OWNER__"
INITIAL_COMMIT_MSG="feat: Totto Mercedes F1 Fan Agent with CXAS >90% eval gate CI/CD"
GH_INSTALL_DIR="${HOME}/.local/bin"
# Pinned gh release used when the GitHub "latest" lookup is unavailable.
GH_FALLBACK_VERSION="2.63.2"

# -----------------------------------------------------------------------------
# Inputs (env vars, overridable by flags)
# -----------------------------------------------------------------------------
GITHUB_OWNER="${GITHUB_OWNER:-}"
GITHUB_REPO="${GITHUB_REPO:-}"
GITHUB_TOKEN="${GITHUB_TOKEN:-}"
VISIBILITY="${VISIBILITY:-private}"
GIT_USER_NAME="${GIT_USER_NAME:-}"
GIT_USER_EMAIL="${GIT_USER_EMAIL:-}"

# Optional secrets (only set on GitHub when non-empty).
GCP_WORKLOAD_IDENTITY_PROVIDER="${GCP_WORKLOAD_IDENTITY_PROVIDER:-}"
GCP_SERVICE_ACCOUNT="${GCP_SERVICE_ACCOUNT:-}"

# Actions repository variables consumed by cxas-eval-deploy.yml (vars.*).
GCP_PROJECT_ID="${GCP_PROJECT_ID:-gcp-ces-chirp-dev}"
GCP_LOCATION="${GCP_LOCATION:-us-central1}"
CES_STAGING_APP_ID="${CES_STAGING_APP_ID:-keerthanaguru-totto-mercedes-f1-agent-staging}"
CES_PROD_APP_ID="${CES_PROD_APP_ID:-keerthanaguru-totto-mercedes-f1-agent}"
EVAL_THRESHOLD="${EVAL_THRESHOLD:-0.90}"
EVAL_RUNS="${EVAL_RUNS:-5}"

DRY_RUN=0

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
usage() {
  cat <<'EOF'
Usage: scripts/setup_github_repo.sh [options]

Idempotently create/configure the GitHub repository for the Totto Mercedes F1
Fan Agent: repo, main branch, Actions variables/secrets, staging/production
environments, and the main-branch ruleset (required Stage 1 + Stage 2 checks).

Options (each may also be provided as the environment variable in brackets):
  --owner NAME            GitHub user/org that owns the repo       [GITHUB_OWNER]  (required)
  --repo NAME             Repository name                          [GITHUB_REPO]   (required)
  --token TOKEN           PAT with repo, workflow, admin:repo_hook [GITHUB_TOKEN]  (required unless --dry-run)
  --visibility VIS        private | public | internal              [VISIBILITY]    (default: private)
  --git-user-name NAME    Local git user.name for commits          [GIT_USER_NAME]
  --git-user-email EMAIL  Local git user.email for commits         [GIT_USER_EMAIL]
  --dry-run               Print every git/gh/API command without executing
  -h, --help              Show this help and exit

Optional secrets (set on GitHub only when non-empty):
  GCP_WORKLOAD_IDENTITY_PROVIDER, GCP_SERVICE_ACCOUNT

Actions repository variables (defaults in parentheses):
  GCP_PROJECT_ID (gcp-ces-chirp-dev)   GCP_LOCATION (us-central1)
  CES_STAGING_APP_ID (keerthanaguru-totto-mercedes-f1-agent-staging)
  CES_PROD_APP_ID (keerthanaguru-totto-mercedes-f1-agent)
  EVAL_THRESHOLD (0.90)                EVAL_RUNS (5)

Example:
  GITHUB_OWNER=octocat GITHUB_REPO=my_cxas_agent GITHUB_TOKEN=ghp_... \
    scripts/setup_github_repo.sh --dry-run
EOF
}

log()  { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
info() { printf '    %s\n' "$*"; }
warn() { printf '\033[1;33m    WARNING: %s\033[0m\n' "$*" >&2; }
die()  { printf '\033[1;31mERROR: %s\033[0m\n' "$*" >&2; exit 1; }

# run CMD...: print the command; execute it unless --dry-run.
run() {
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    printf '    [dry-run] $ %s\n' "$(printf '%q ' "$@")"
    return 0
  fi
  printf '    $ %s\n' "$(printf '%q ' "$@")"
  "$@"
}

# run_secret DESCRIPTION CMD...: like run(), but never echoes the arguments
# (used for anything that carries a token or secret value).
run_secret() {
  local description="$1"; shift
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    printf '    [dry-run] $ %s\n' "${description}"
    return 0
  fi
  printf '    $ %s\n' "${description}"
  "$@"
}

# capture CMD...: run a command whose stdout we need. In --dry-run the command
# is printed and an empty string is returned (callers substitute placeholders).
capture() {
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    printf '    [dry-run] $ %s\n' "$(printf '%q ' "$@")" >&2
    printf ''
    return 0
  fi
  "$@"
}

# gh_api_soft DESCRIPTION gh-api-args...
# Runs `gh api ...`, but downgrades HTTP 403/422 (typical for GitHub Free
# private repos that cannot use rulesets / environment protection rules) to a
# warning so the rest of the bootstrap continues. Any other failure is fatal.
# Returns 0 on success, 2 on a tolerated plan/validation error.
gh_api_soft() {
  local description="$1"; shift
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    printf '    [dry-run] $ gh api %s\n' "$(printf '%q ' "$@")"
    return 0
  fi
  printf '    $ gh api %s\n' "$(printf '%q ' "$@")"
  local err_file rc=0
  err_file="$(mktemp)"
  if gh api "$@" >/dev/null 2>"${err_file}"; then
    rm -f "${err_file}"
    return 0
  fi
  rc=$?
  if grep -qE 'HTTP (403|422)' "${err_file}"; then
    warn "${description} was rejected by GitHub ($(tr '\n' ' ' <"${err_file}"))"
    warn "This usually means the repository is PRIVATE on a GitHub Free plan."
    warn "Make the repository public (gh repo edit ${GITHUB_OWNER}/${GITHUB_REPO} --visibility public) or upgrade to GitHub Pro/Team, then re-run this script."
    rm -f "${err_file}"
    return 2
  fi
  cat "${err_file}" >&2
  rm -f "${err_file}"
  return "${rc}"
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "Required command not found: $1"
}

# -----------------------------------------------------------------------------
# Argument parsing
# -----------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
  case "$1" in
    --owner)           GITHUB_OWNER="$2"; shift 2 ;;
    --repo)            GITHUB_REPO="$2"; shift 2 ;;
    --token)           GITHUB_TOKEN="$2"; shift 2 ;;
    --visibility)      VISIBILITY="$2"; shift 2 ;;
    --git-user-name)   GIT_USER_NAME="$2"; shift 2 ;;
    --git-user-email)  GIT_USER_EMAIL="$2"; shift 2 ;;
    --dry-run)         DRY_RUN=1; shift ;;
    -h|--help)         usage; exit 0 ;;
    *) usage >&2; die "Unknown argument: $1" ;;
  esac
done

[[ -n "${GITHUB_OWNER}" ]] || { usage >&2; die "GITHUB_OWNER / --owner is required"; }
[[ -n "${GITHUB_REPO}"  ]] || { usage >&2; die "GITHUB_REPO / --repo is required"; }
if [[ -z "${GITHUB_TOKEN}" && "${DRY_RUN}" -eq 0 ]]; then
  die "GITHUB_TOKEN / --token is required (PAT with repo, workflow, admin:repo_hook)"
fi
case "${VISIBILITY}" in
  private|public|internal) ;;
  *) die "VISIBILITY must be private, public, or internal (got '${VISIBILITY}')" ;;
esac
[[ -f "${RULESET_FILE}" ]] || die "Ruleset file not found: ${RULESET_FILE}"

require_cmd git
require_cmd curl
require_cmd tar
require_cmd python3

FULL_REPO="${GITHUB_OWNER}/${GITHUB_REPO}"
REPO_URL="https://github.com/${FULL_REPO}"

cd "${PROJECT_ROOT}"

log "Configuration"
info "Project root : ${PROJECT_ROOT}"
info "Repository   : ${FULL_REPO} (${VISIBILITY})"
info "Token        : $([[ -n "${GITHUB_TOKEN}" ]] && echo '<provided>' || echo '<missing>')"
info "Dry run      : $([[ "${DRY_RUN}" -eq 1 ]] && echo yes || echo no)"

# =============================================================================
# (a) Install gh if missing, then authenticate
# =============================================================================
log "(a) GitHub CLI"
if command -v gh >/dev/null 2>&1; then
  info "gh already installed: $(gh --version | head -n1)"
else
  info "gh not found; installing to ${GH_INSTALL_DIR}"
  arch_raw="$(uname -m)"
  case "${arch_raw}" in
    x86_64|amd64)  gh_arch="amd64" ;;
    aarch64|arm64) gh_arch="arm64" ;;
    armv6l|armv7l) gh_arch="armv6" ;;
    i386|i686)     gh_arch="386" ;;
    *) die "Unsupported architecture for gh: ${arch_raw}" ;;
  esac
  os_raw="$(uname -s | tr '[:upper:]' '[:lower:]')"
  [[ "${os_raw}" == "linux" ]] || die "Automatic gh install only supports Linux (got ${os_raw}); install gh manually: https://cli.github.com"

  if [[ "${DRY_RUN}" -eq 1 ]]; then
    gh_version="${GH_FALLBACK_VERSION}"
    info "[dry-run] would resolve latest gh version via https://api.github.com/repos/cli/cli/releases/latest (fallback ${GH_FALLBACK_VERSION})"
  else
    gh_version="$(curl -fsSL https://api.github.com/repos/cli/cli/releases/latest \
      | python3 -c 'import json,sys; print(json.load(sys.stdin)["tag_name"].lstrip("v"))' \
      2>/dev/null || true)"
    [[ -n "${gh_version}" ]] || gh_version="${GH_FALLBACK_VERSION}"
  fi
  gh_tarball="gh_${gh_version}_linux_${gh_arch}.tar.gz"
  gh_url="https://github.com/cli/cli/releases/download/v${gh_version}/${gh_tarball}"
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    tmp_dir="/tmp/gh-install.XXXXXX"
  else
    tmp_dir="$(mktemp -d)"
  fi
  run mkdir -p "${GH_INSTALL_DIR}"
  run curl -fsSL -o "${tmp_dir}/${gh_tarball}" "${gh_url}"
  run tar -xzf "${tmp_dir}/${gh_tarball}" -C "${tmp_dir}"
  run install -m 0755 "${tmp_dir}/gh_${gh_version}_linux_${gh_arch}/bin/gh" "${GH_INSTALL_DIR}/gh"
  run rm -rf "${tmp_dir}"
  export PATH="${GH_INSTALL_DIR}:${PATH}"
  if [[ "${DRY_RUN}" -eq 0 ]]; then
    command -v gh >/dev/null 2>&1 || die "gh install failed (not on PATH after install)"
    info "Installed: $(gh --version | head -n1)"
  else
    info "[dry-run] would verify: gh --version"
  fi
  case ":${PATH}:" in
    *":${GH_INSTALL_DIR}:"*) ;;
    *) warn "Add ${GH_INSTALL_DIR} to your PATH permanently (e.g. in ~/.bashrc)." ;;
  esac
fi

# Authenticate with the PAT (idempotent: re-login simply refreshes the token).
# GH_TOKEN must NOT be exported, otherwise `gh auth login` refuses to run.
unset GH_TOKEN GITHUB_TOKEN_ENV 2>/dev/null || true
run_secret 'gh auth login --hostname github.com --with-token <<< "$GITHUB_TOKEN"' \
  bash -c 'gh auth login --hostname github.com --with-token <<< "$0"' "${GITHUB_TOKEN}"
# Let git use gh as the HTTPS credential helper so `git push` works with the PAT.
run gh auth setup-git --hostname github.com
if [[ "${DRY_RUN}" -eq 0 ]]; then
  gh auth status --hostname github.com >/dev/null 2>&1 || die "gh authentication failed; check GITHUB_TOKEN scopes"
fi

# =============================================================================
# (b) Local git repository and initial commit
# =============================================================================
log "(b) Local git repository"
if [[ -d .git ]]; then
  info "Existing git repository detected"
  if [[ "${DRY_RUN}" -eq 0 ]]; then
    current_branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo main)"
    if [[ "${current_branch}" != "main" ]]; then
      warn "Current branch is '${current_branch}', expected 'main'. The ruleset targets refs/heads/main."
    fi
  fi
else
  run git init -b main
fi

# Resolve git identity: flag/env > existing config > owner-based no-reply.
if [[ -z "${GIT_USER_NAME}" ]]; then
  GIT_USER_NAME="$(git config user.name 2>/dev/null || true)"
  [[ -n "${GIT_USER_NAME}" ]] || GIT_USER_NAME="${GITHUB_OWNER}"
fi
if [[ -z "${GIT_USER_EMAIL}" ]]; then
  GIT_USER_EMAIL="$(git config user.email 2>/dev/null || true)"
  [[ -n "${GIT_USER_EMAIL}" ]] || GIT_USER_EMAIL="${GITHUB_OWNER}@users.noreply.github.com"
fi
run git config user.name "${GIT_USER_NAME}"
run git config user.email "${GIT_USER_EMAIL}"

run git add -A
if [[ "${DRY_RUN}" -eq 1 ]]; then
  info "[dry-run] would commit if 'git status --porcelain' is non-empty:"
  run git commit -m "${INITIAL_COMMIT_MSG}"
elif [[ -n "$(git status --porcelain)" ]]; then
  run git commit -m "${INITIAL_COMMIT_MSG}"
else
  info "Working tree clean; nothing to commit"
fi

# =============================================================================
# (c) Create the GitHub repository (or reuse) and push main
# =============================================================================
log "(c) GitHub repository ${FULL_REPO}"
repo_exists=0
if [[ "${DRY_RUN}" -eq 1 ]]; then
  info "[dry-run] would check: gh repo view ${FULL_REPO}"
elif gh repo view "${FULL_REPO}" >/dev/null 2>&1; then
  repo_exists=1
fi

if [[ "${repo_exists}" -eq 1 ]]; then
  info "Repository already exists: ${REPO_URL}"
else
  info "Creating repository (if it does not already exist)"
  run gh repo create "${FULL_REPO}" "--${VISIBILITY}" --source . --remote origin \
    --description "Totto Mercedes F1 Fan Agent (CXAS/CES) with >90% eval-gated CI/CD"
fi

# Ensure `origin` points at the repo regardless of how it was created.
if [[ "${DRY_RUN}" -eq 1 ]]; then
  info "[dry-run] would ensure remote origin -> ${REPO_URL}.git"
  run git remote add origin "${REPO_URL}.git"
elif git remote get-url origin >/dev/null 2>&1; then
  current_origin="$(git remote get-url origin)"
  if [[ "${current_origin}" != *"${FULL_REPO}"* ]]; then
    warn "origin currently points to ${current_origin}; updating to ${REPO_URL}.git"
    run git remote set-url origin "${REPO_URL}.git"
  else
    info "origin already set: ${current_origin}"
  fi
else
  run git remote add origin "${REPO_URL}.git"
fi

run git push -u origin main

# =============================================================================
# (d) CODEOWNERS placeholder substitution
# =============================================================================
log "(d) CODEOWNERS"
if [[ -f "${CODEOWNERS_FILE}" ]] && grep -q "${CODEOWNERS_PLACEHOLDER}" "${CODEOWNERS_FILE}"; then
  run sed -i "s/${CODEOWNERS_PLACEHOLDER}/${GITHUB_OWNER}/g" "${CODEOWNERS_FILE}"
  run git add "${CODEOWNERS_FILE}"
  run git commit -m "chore: set CODEOWNERS to @${GITHUB_OWNER}"
  run git push origin main
else
  info "No ${CODEOWNERS_PLACEHOLDER} placeholder left in .github/CODEOWNERS; nothing to do"
fi

# =============================================================================
# (e) Actions variables and secrets
# =============================================================================
log "(e) Actions repository variables"
declare -A REPO_VARS=(
  [GCP_PROJECT_ID]="${GCP_PROJECT_ID}"
  [GCP_LOCATION]="${GCP_LOCATION}"
  [CES_STAGING_APP_ID]="${CES_STAGING_APP_ID}"
  [CES_PROD_APP_ID]="${CES_PROD_APP_ID}"
  [EVAL_THRESHOLD]="${EVAL_THRESHOLD}"
  [EVAL_RUNS]="${EVAL_RUNS}"
)
for var_name in GCP_PROJECT_ID GCP_LOCATION CES_STAGING_APP_ID CES_PROD_APP_ID EVAL_THRESHOLD EVAL_RUNS; do
  # `gh variable set` creates or updates, so this is naturally idempotent.
  run gh variable set "${var_name}" --repo "${FULL_REPO}" --body "${REPO_VARS[${var_name}]}"
done

log "(e) Actions repository secrets"
for secret_name in GCP_WORKLOAD_IDENTITY_PROVIDER GCP_SERVICE_ACCOUNT; do
  secret_value="${!secret_name}"
  if [[ -n "${secret_value}" ]]; then
    run_secret "gh secret set ${secret_name} --repo ${FULL_REPO} --body <redacted>" \
      gh secret set "${secret_name}" --repo "${FULL_REPO}" --body "${secret_value}"
  else
    info "Skipping ${secret_name} (env var empty). Set it later with: gh secret set ${secret_name} --repo ${FULL_REPO}"
  fi
done

# =============================================================================
# (f) Environments: staging (no gate) and production (reviewer + main only)
# =============================================================================
log "(f) Deployment environments"
ENV_PROTECTION_OK=1

# staging: plain environment, no protection rules (Stage 2 runs here).
gh_api_soft "Creating environment 'staging'" \
  -X PUT "repos/${FULL_REPO}/environments/staging" || ENV_PROTECTION_OK=0

# production: required reviewer = repo owner, deployments only from main.
owner_id="$(capture gh api "users/${GITHUB_OWNER}" --jq .id)"
[[ -n "${owner_id}" ]] || owner_id="<owner-user-id>"
info "Repository owner user id: ${owner_id}"
production_payload="$(cat <<EOF
{
  "wait_timer": 0,
  "prevent_self_review": false,
  "reviewers": [ { "type": "User", "id": ${owner_id} } ],
  "deployment_branch_policy": { "protected_branches": false, "custom_branch_policies": true }
}
EOF
)"
info "production environment payload: $(echo "${production_payload}" | tr -d '\n' | tr -s ' ')"
env_rc=0
if [[ "${DRY_RUN}" -eq 1 ]]; then
  printf '    [dry-run] $ gh api -X PUT repos/%s/environments/production --input <payload>\n' "${FULL_REPO}"
else
  gh_api_soft "Configuring environment 'production' (reviewers + branch policy)" \
    -X PUT "repos/${FULL_REPO}/environments/production" --input - <<<"${production_payload}" || env_rc=$?
fi
if [[ "${env_rc}" -ne 0 ]]; then
  ENV_PROTECTION_OK=0
  # Fall back to a plain environment so `environment: production` still resolves.
  gh_api_soft "Creating environment 'production' without protection rules" \
    -X PUT "repos/${FULL_REPO}/environments/production" || true
else
  # Restrict deployments to the main branch (idempotent: skip if already present).
  existing_policy="$(capture gh api "repos/${FULL_REPO}/environments/production/deployment-branch-policies" \
    --jq '.branch_policies[]? | select(.name=="main") | .id' 2>/dev/null || true)"
  if [[ -n "${existing_policy}" ]]; then
    info "Deployment branch policy for 'main' already exists (id ${existing_policy})"
  else
    gh_api_soft "Adding deployment branch policy 'main' to production" \
      -X POST "repos/${FULL_REPO}/environments/production/deployment-branch-policies" \
      -f name=main -f type=branch || ENV_PROTECTION_OK=0
  fi
fi

# =============================================================================
# (g) Branch ruleset for main (create or update by name)
# =============================================================================
log "(g) Repository ruleset from ${RULESET_FILE#"${PROJECT_ROOT}/"}"
RULESET_OK=1
ruleset_name="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["name"])' "${RULESET_FILE}")"
info "Ruleset name: ${ruleset_name}"

existing_ruleset_id="$(capture gh api "repos/${FULL_REPO}/rulesets" \
  --jq ".[] | select(.name==\"${ruleset_name}\") | .id" 2>/dev/null || true)"

apply_ruleset() {
  # $1 = path to JSON payload
  local payload_file="$1" rc=0
  if [[ -n "${existing_ruleset_id}" ]]; then
    info "Updating existing ruleset id ${existing_ruleset_id}"
    gh_api_soft "Updating ruleset '${ruleset_name}'" \
      -X PUT "repos/${FULL_REPO}/rulesets/${existing_ruleset_id}" --input "${payload_file}" || rc=$?
  else
    info "Creating ruleset '${ruleset_name}'"
    gh_api_soft "Creating ruleset '${ruleset_name}'" \
      -X POST "repos/${FULL_REPO}/rulesets" --input "${payload_file}" || rc=$?
  fi
  return "${rc}"
}

ruleset_rc=0
apply_ruleset "${RULESET_FILE}" || ruleset_rc=$?
if [[ "${ruleset_rc}" -ne 0 && "${DRY_RUN}" -eq 0 ]]; then
  # Some account types reject RepositoryRole bypass actors; retry without them
  # before giving up (the remaining rules are far more valuable than bypass).
  stripped="$(mktemp --suffix=.json)"
  python3 - "${RULESET_FILE}" "${stripped}" <<'PY'
import json, sys
data = json.load(open(sys.argv[1]))
data.pop("bypass_actors", None)
json.dump(data, open(sys.argv[2], "w"), indent=2)
PY
  info "Retrying ruleset without bypass_actors"
  ruleset_rc=0
  apply_ruleset "${stripped}" || ruleset_rc=$?
  rm -f "${stripped}"
fi
[[ "${ruleset_rc}" -eq 0 ]] || RULESET_OK=0

# =============================================================================
# (h) Summary
# =============================================================================
log "(h) Summary"
cat <<EOF
    Repository      : ${REPO_URL}
    Actions         : ${REPO_URL}/actions
    Variables       : ${REPO_URL}/settings/variables/actions
    Secrets         : ${REPO_URL}/settings/secrets/actions
    Environments    : ${REPO_URL}/settings/environments
    Rulesets        : ${REPO_URL}/settings/rules
    Ruleset applied : $([[ "${RULESET_OK}" -eq 1 ]] && echo yes || echo 'NO (see warnings)')
    Env protection  : $([[ "${ENV_PROTECTION_OK}" -eq 1 ]] && echo yes || echo 'NO (see warnings)')

    Governance enforced on refs/heads/main:
      - no deletion, no force-push, linear history
      - pull request with >= 1 approving review (stale reviews dismissed on push)
      - required status checks (strict / up-to-date with main):
          * Stage 1: CXAS Lint & Local Unit Tests
          * Stage 2: CES Evaluation Suite & >90% Pass-Rate Gate
      - production environment: reviewer approval by @${GITHUB_OWNER}, deployments from main only

    Next steps:
      1. If not already set, add the WIF secrets (see docs/CI_CD_SETUP.md §4):
           gh secret set GCP_WORKLOAD_IDENTITY_PROVIDER --repo ${FULL_REPO}
           gh secret set GCP_SERVICE_ACCOUNT --repo ${FULL_REPO}
      2. Open a pull request and confirm both required checks appear on it.
      3. Merge to main and approve the 'production' deployment in the Actions run.
EOF
if [[ "${DRY_RUN}" -eq 1 ]]; then
  info "(dry run complete; nothing was changed)"
fi
