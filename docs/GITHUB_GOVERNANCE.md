# GitHub Governance for the Totto Mercedes F1 Fan Agent

This document lists the gates enforced on the GitHub repository, how to apply
them with `scripts/setup_github_repo.sh`, and how to create the Personal
Access Token (PAT) the script needs. For the pipeline itself see
[`CI_CD_SETUP.md`](CI_CD_SETUP.md).

## 1. Gates and criteria

### 1.1 `main` branch ruleset (`.github/rulesets/main-branch-protection.json`)

Applied via `POST /repos/{owner}/{repo}/rulesets` (or `PUT .../rulesets/{id}`
when a ruleset named `main-branch-protection` already exists). Target:
`refs/heads/main`, enforcement `active`.

| Rule | Effect |
|------|--------|
| `deletion` | `main` cannot be deleted. |
| `non_fast_forward` | No force-pushes / history rewrites on `main`. |
| `required_linear_history` | Merge commits are rejected; use squash or rebase merges. |
| `pull_request` | Changes land only via PR with **1 approving review**; stale approvals are dismissed on new pushes (`dismiss_stale_reviews_on_push: true`, `require_last_push_approval: false`). |
| `required_status_checks` | Both checks below must be green and the branch must be **up to date with `main`** (`strict_required_status_checks_policy: true`): <br>• `Stage 1: CXAS Lint & Local Unit Tests` <br>• `Stage 2: CES Evaluation Suite & >90% Pass-Rate Gate` |

`bypass_actors` grants repository **admins** (`actor_id: 5`,
`actor_type: RepositoryRole`, `bypass_mode: always`) an emergency bypass. If
GitHub rejects that actor type for the account, the script retries the ruleset
without `bypass_actors`.

The status-check contexts are the GitHub Actions **job display names** from
`.github/workflows/cxas-eval-deploy.yml`; renaming a job requires updating the
ruleset JSON and re-running the script.

### 1.2 The `>90%` evaluation gate (Stage 2)

`scripts/check_eval_threshold.py --threshold 0.90 --comparison gt` fails the
Stage 2 job unless the aggregated CES evaluation `pass_rate` across the golden,
simulation, tool, and callback suites is **strictly greater than 0.90**
(exactly 90.0% fails). Because Stage 2 is a required status check, a PR that
regresses agent quality cannot be merged, and because Stage 3 is conditioned on
`needs.evaluate-and-gate.outputs.gate_passed == 'true'`, nothing reaches the
production CES app without passing it.

### 1.3 Environments

| Environment | Used by | Protection |
|-------------|---------|------------|
| `staging` | Stage 2 (`evaluate-and-gate`) | None; evaluations must be able to run on every PR. |
| `production` | Stage 3 (`push-to-project`) | **Required reviewer** = repository owner; **deployment branch policy** limited to `main`. The Actions run pauses until the reviewer approves the deployment. |

### 1.4 Code review hygiene

- `.github/CODEOWNERS`: `* @<owner>` — the owner is requested on every PR.
- `.github/pull_request_template.md`: checklist for lint 0/0, green pytest,
  evals (incl. failure/adversarial scenarios) for new CUJs, and no secrets.

## 2. Applying the governance: `scripts/setup_github_repo.sh`

The script is idempotent and safe to re-run. It:

1. installs `gh` into `~/.local/bin` if missing and logs in with the PAT;
2. runs `git init -b main`, sets a local git identity, and commits;
3. creates the repository (or reuses it), sets `origin`, pushes `main`;
4. substitutes `__GITHUB_OWNER__` in `.github/CODEOWNERS` and pushes;
5. sets the Actions variables (`GCP_PROJECT_ID`, `GCP_LOCATION`,
   `CES_STAGING_APP_ID`, `CES_PROD_APP_ID`, `EVAL_THRESHOLD`, `EVAL_RUNS`) and
   the secrets `GCP_WORKLOAD_IDENTITY_PROVIDER` / `GCP_SERVICE_ACCOUNT` when
   those env vars are non-empty;
6. creates the `staging` and `production` environments;
7. creates or updates the `main-branch-protection` ruleset;
8. prints the repo/Actions URLs and next steps.

```bash
cd /path/to/my_cxas_agent

# Preview every git/gh/API call without executing anything
GITHUB_OWNER=<owner> GITHUB_REPO=<repo> GITHUB_TOKEN=<pat> \
  scripts/setup_github_repo.sh --dry-run

# Apply (add WIF secrets inline if you already have them)
GITHUB_OWNER=<owner> GITHUB_REPO=<repo> GITHUB_TOKEN=<pat> \
GIT_USER_NAME="Your Name" GIT_USER_EMAIL="you@example.com" \
GCP_WORKLOAD_IDENTITY_PROVIDER="projects/123/locations/global/workloadIdentityPools/github-pool/providers/github-provider" \
GCP_SERVICE_ACCOUNT="cxas-ci-deployer@gcp-ces-chirp-dev.iam.gserviceaccount.com" \
  scripts/setup_github_repo.sh
```

All inputs can also be passed as flags (`--owner`, `--repo`, `--token`,
`--visibility`, `--git-user-name`, `--git-user-email`); run
`scripts/setup_github_repo.sh --help` for the full list and defaults.

> **GitHub Free plan and private repositories.** Rulesets and environment
> protection rules (required reviewers, deployment branch policies) are only
> available for **public** repositories or on GitHub Pro/Team/Enterprise. On a
> Free personal account with `VISIBILITY=private`, GitHub returns HTTP 403/422
> for those calls. The script prints a warning and continues (the repository,
> variables, secrets, and plain environments are still created). To get the
> full gate set either run with `VISIBILITY=public`, make the repo public
> later (`gh repo edit <owner>/<repo> --visibility public`) and re-run the
> script, or upgrade the plan.

## 3. Creating the Personal Access Token

The script authenticates `gh` with `GITHUB_TOKEN`. Never commit the token; pass
it via the environment for the duration of the run.

### Option A — Fine-grained PAT (recommended)

1. GitHub → **Settings → Developer settings → Personal access tokens →
   Fine-grained tokens → Generate new token**.
2. **Resource owner**: the user/org that will own the repository.
3. **Repository access**: *All repositories* (required so the token can
   **create** the repo), or switch to *Only select repositories* after the
   first run.
4. **Repository permissions** (Read and write unless noted):
   - **Administration** — create repo, environments, rulesets
   - **Contents** — push commits
   - **Workflows** — push files under `.github/workflows/`
   - **Secrets** and **Variables** — Actions secrets/variables
   - **Environments** — environment protection rules
   - **Metadata** — Read-only (added automatically)
5. Set an expiry (e.g. 7 days; the token is only needed for bootstrap),
   generate, and copy it.

### Option B — Classic PAT

Scopes: `repo`, `workflow`, `admin:repo_hook`. Classic tokens are broader than
needed; prefer Option A where possible.

Export the token only in the shell that runs the script:

```bash
read -rs GITHUB_TOKEN && export GITHUB_TOKEN
```

## 4. Verifying the gates

After the script runs:

- **Rulesets**: `https://github.com/<owner>/<repo>/settings/rules` should show
  `main-branch-protection` as *Active*, or
  `gh api repos/<owner>/<repo>/rulesets --jq '.[].name'`.
- **Environments**: `https://github.com/<owner>/<repo>/settings/environments`
  should list `staging` and `production` (the latter with a required reviewer
  and `main` as the only allowed branch).
- **Required checks**: open a PR; the *Checks* section should list both Stage 1
  and Stage 2 as *Required*, and *Merge* stays disabled until they pass and a
  review is approved.
- **Production approval**: after merging to `main`, the Actions run for Stage 3
  waits in *Review deployments* until the owner approves.
