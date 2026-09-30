## Summary

<!-- What does this change do, and why? Link the related issue if any. -->

## Type of change

- [ ] Agent instruction / persona change
- [ ] Tool implementation or schema change
- [ ] New or updated evaluations (goldens / simulations / tool tests / callbacks)
- [ ] CI/CD, tooling, or docs

## Pre-merge checklist

- [ ] `uv run cxas lint --app-dir cxas_app/totto_mercedes_f1_agent` reports **0 errors / 0 warnings**
- [ ] `uv run pytest tests -v` is green locally
- [ ] Every new or changed CUJ has evaluations added under `evals/`
  (golden **and** simulation where applicable)
- [ ] New evaluations include **failure / boundary / adversarial** scenarios
  (e.g. unknown order IDs, out-of-stock sizes, prompt-injection, rival trash-talk bait)
- [ ] Tools still return `agent_action` on every error path and keep the `<= 5s` timeout
- [ ] No secrets, tokens, service-account keys, or PII committed
  (`GCP_WORKLOAD_IDENTITY_PROVIDER` / `GCP_SERVICE_ACCOUNT` live in GitHub Secrets only)
- [ ] `docs/CI_CD_SETUP.md` / `README.md` updated if variables, gates, or workflow behaviour changed

## Evaluation impact

<!-- Expected effect on the Stage 2 pass rate (must remain strictly > 90%).
     Paste the CI scorecard or a local run of scripts/check_eval_threshold.py if relevant. -->
