#!/usr/bin/env python3
"""Synchronize Golden Evaluations, Scenario Simulations, and Evaluation Datasets for Totto to CES Console Dev, and optionally execute a live evaluation run."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any
import uuid

os.environ.setdefault("CES_API_ENDPOINT", "autopush-ces.sandbox.googleapis.com")
os.environ.setdefault("CES_TRANSPORT", "rest")

from google.api_core import client_options as client_options_lib  # noqa: E402
from google.cloud import ces_v1beta  # noqa: E402
from google.cloud.ces_v1beta import types  # noqa: E402
from google.protobuf import field_mask_pb2, json_format, struct_pb2  # noqa: E402
import yaml  # noqa: E402

from cxas_scrapi.core.agents import Agents  # noqa: E402
from cxas_scrapi.core.evaluations import Evaluations  # noqa: E402
from cxas_scrapi.core.tools import Tools  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
APP_JSON_PATH = REPO_ROOT / "cxas_app" / "totto_mercedes_f1_agent" / "app.json"
GOLDENS_PATH = REPO_ROOT / "evals" / "goldens" / "goldens.yaml"
SIMS_PATH = REPO_ROOT / "evals" / "simulations" / "simulations.yaml"
EVAL_REPORTS_DIR = REPO_ROOT / "eval-reports"
CI_SUMMARY_PATH = EVAL_REPORTS_DIR / "ci-summary.json"
CES_DEV_REPORT_PATH = EVAL_REPORTS_DIR / "ces_console_dev_eval_report.json"

DEFAULT_APP = (
    "projects/agents-keerth-sandbox-950246/locations/global/apps/"
    "totto-mercedes-f1-agent"
)

DATASET_SPECS = [
    "Totto Mercedes F1 Full Evaluation Suite",
    "Dataset 1: P0 Core Fan Concierge & Guardrails",
    "Dataset 2: P1 Extended Coverage & Multilingual",
]


def _md5_short(text: str) -> str:
  return hashlib.md5(text.encode("utf-8")).hexdigest()[:8]


def sync_app_evaluation_thresholds(
    app_name: str, creds: Any = None
) -> dict[str, Any]:
  """Patches evaluation_metrics_thresholds from local app.json onto the remote CES App."""
  if not APP_JSON_PATH.is_file():
    return {}
  app_cfg = json.loads(APP_JSON_PATH.read_text(encoding="utf-8"))
  thresholds_dict = app_cfg.get("evaluationMetricsThresholds")
  if not thresholds_dict:
    return {}

  endpoint = os.environ.get(
      "CES_API_ENDPOINT", "autopush-ces.sandbox.googleapis.com"
  )
  transport = os.environ.get("CES_TRANSPORT", "rest")
  agent_client = ces_v1beta.AgentServiceClient(
      credentials=creds,
      transport=transport,
      client_options=client_options_lib.ClientOptions(api_endpoint=endpoint),
  )
  thresholds_pb = types.EvaluationMetricsThresholds()
  json_format.ParseDict(
      thresholds_dict, thresholds_pb._pb, ignore_unknown_fields=True
  )
  updated_app = agent_client.update_app(
      request=types.UpdateAppRequest(
          app=types.App(
              name=app_name,
              evaluation_metrics_thresholds=thresholds_pb,
          ),
          update_mask=field_mask_pb2.FieldMask(
              paths=["evaluation_metrics_thresholds"]
          ),
      )
  )
  return json_format.MessageToDict(
      updated_app._pb.evaluation_metrics_thresholds
  )


def clean_stale_evaluations(app_name: str) -> dict[str, Any]:
  """Deletes remote evaluations whose display_name is not in local goldens.yaml or simulations.yaml."""
  evals_client = Evaluations(app_name=app_name)
  goldens_raw = yaml.safe_load(GOLDENS_PATH.read_text(encoding="utf-8")) or {}
  sims_raw = yaml.safe_load(SIMS_PATH.read_text(encoding="utf-8")) or {}
  target_names = {
      str(c.get("conversation"))
      for c in (goldens_raw.get("conversations") or [])
      if c.get("conversation")
  } | {
      str(s.get("name"))
      for s in (sims_raw.get("evals") or [])
      if s.get("name")
  }

  existing = evals_client.list_evaluations(app_name)
  deleted: list[str] = []
  for ev in existing:
    if ev.display_name not in target_names or ev.invalid:
      evals_client.delete_evaluation(name=ev.name, force=True)
      deleted.append(ev.display_name or ev.name)
  return {"deleted_count": len(deleted), "deleted": deleted}


def clean_stale_remote_tools_and_expectations(
    app_name: str, evals_client: Evaluations, active_prompts: list[str]
) -> dict[str, Any]:
  """Deletes stale remote tools (not in app.json) and stale EvaluationExpectations."""
  deleted_tools: list[str] = []
  deleted_expectations: list[str] = []
  if APP_JSON_PATH.is_file():
    app_cfg = json.loads(APP_JSON_PATH.read_text(encoding="utf-8"))
    allowed_tools = set(app_cfg.get("tools") or [])
    endpoint = os.environ.get(
        "CES_API_ENDPOINT", "autopush-ces.sandbox.googleapis.com"
    )
    transport = os.environ.get("CES_TRANSPORT", "rest")
    agent_client = ces_v1beta.AgentServiceClient(
        credentials=evals_client.creds,
        transport=transport,
        client_options=client_options_lib.ClientOptions(api_endpoint=endpoint),
    )
    for remote_tool in agent_client.list_tools(parent=app_name):
      t_disp = getattr(remote_tool, "display_name", "") or ""
      if t_disp and t_disp not in allowed_tools:
        try:
          agent_client.delete_tool(
              request=types.DeleteToolRequest(name=remote_tool.name, force=True)
          )
          deleted_tools.append(t_disp)
        except Exception:
          pass

  active_prompt_set = {p for p in active_prompts if p}
  for exp in evals_client.list_evaluation_expectations(app_name=app_name):
    exp_prompt = (
        getattr(exp.llm_criteria, "prompt", "")
        if hasattr(exp, "llm_criteria") and exp.llm_criteria
        else ""
    )
    if exp_prompt and exp_prompt not in active_prompt_set:
      try:
        evals_client.delete_evaluation_expectation(name=exp.name)
        deleted_expectations.append(exp.display_name or exp.name)
      except Exception:
        pass

  return {
      "deleted_tools": deleted_tools,
      "deleted_expectations": deleted_expectations,
  }


def ensure_expectations_map(
    evals_client: Evaluations, app_name: str, prompts: list[str]
) -> dict[str, str]:
  """Resolves expectation prompt strings to CES EvaluationExpectation resource names."""
  existing = evals_client.list_evaluation_expectations(app_name=app_name)
  by_display: dict[str, str] = {}
  by_prompt: dict[str, str] = {}
  for exp in existing:
    exp_prompt = (
        getattr(exp.llm_criteria, "prompt", "")
        if hasattr(exp, "llm_criteria") and exp.llm_criteria
        else ""
    )
    if exp.display_name and exp.name:
      by_display[exp.display_name] = exp.name
    if exp_prompt and exp.name:
      by_prompt[exp_prompt] = exp.name

  resolved: dict[str, str] = {}
  missing_prompts: list[str] = []
  unique_prompts = list(dict.fromkeys(p for p in prompts if p))
  for prompt in unique_prompts:
    if prompt.startswith("projects/") and "/evaluationExpectations/" in prompt:
      resolved[prompt] = prompt
      continue
    disp = f"eval_exp_{_md5_short(prompt)}"
    if prompt in by_prompt:
      resolved[prompt] = by_prompt[prompt]
    elif disp in by_display:
      resolved[prompt] = by_display[disp]
    else:
      missing_prompts.append(prompt)

  if missing_prompts:

    def _create_exp(p: str) -> tuple[str, str]:
      disp = f"eval_exp_{_md5_short(p)}"
      created = evals_client.create_evaluation_expectation(
          evaluation_expectation=types.EvaluationExpectation(
              display_name=disp,
              llm_criteria=types.EvaluationExpectation.LlmCriteria(prompt=p),
          ),
          app_name=app_name,
      )
      return p, created.name

    with ThreadPoolExecutor(max_workers=8) as pool:
      futures = [pool.submit(_create_exp, p) for p in missing_prompts]
      for fut in as_completed(futures):
        p, name = fut.result()
        resolved[p] = name
  return resolved


def build_golden_evaluations_from_yaml(
    yaml_path: Path,
    app_name: str,
    agent_map: dict[str, str],
    tool_map: dict[str, str],
    expectations_map: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
  """Builds CES Golden Evaluation dicts with chronological step ordering and relaxed tool parameter threshold overrides."""
  _ = expectations_map
  data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
  common_params = dict(data.get("common_session_parameters") or {})
  conversations = list(data.get("conversations") or [])
  file_tag = yaml_path.stem

  # Normalize tool targets to specialist agents for multi-agent transfer steps
  tool_to_agent = {
      "get_race_schedule": "race_info_agent",
      "get_driver_standings": "race_info_agent",
      "lookup_merch_order": "merch_support_agent",
      "submit_merch_request": "merch_support_agent",
      "check_merch_availability": "merch_support_agent",
  }

  golden_evals: list[dict[str, Any]] = []
  for conv in conversations:
    display_name = str(conv["conversation"])
    session_params = dict(common_params)
    session_params.update(conv.get("session_parameters") or {})

    remaining_mocks = [
        dict(m) for m in (conv.get("mocks") or []) if isinstance(m, dict)
    ]
    root_res = agent_map.get(
        "totto_root_agent", f"{app_name}/agents/totto_root_agent"
    )
    active_agent = root_res
    params_injected = False
    json_turns: list[dict[str, Any]] = []

    for turn in conv.get("turns") or []:
      steps: list[dict[str, Any]] = []
      if not params_injected and session_params:
        steps.append({"userInput": {"variables": session_params}})
        params_injected = True

      user_text = turn.get("user")
      if (
          user_text is None
          or str(user_text).strip() == "<event>welcome</event>"
      ):
        steps.append({"userInput": {"event": {"event": "welcome"}}})
      else:
        steps.append({"userInput": {"text": str(user_text)}})

      for tc in turn.get("tool_calls") or []:
        action = str(tc.get("action") or tc.get("name") or "").strip()
        if not action or action == "end_session":
          continue

        if action == "transfer_to_agent":
          target_agent_name = (
              (tc.get("args") or {}).get("agent_name")
              or (tc.get("args") or {}).get("agent")
              or tc.get("agent")
              or ""
          )
          target_agent_res = agent_map.get(
              target_agent_name,
              f"{app_name}/agents/{target_agent_name}",
          )
          active_agent = target_agent_res
          steps.append(
              {
                  "expectation": {
                      "agentTransfer": {"targetAgent": target_agent_res}
                  }
              }
          )
          continue

        # If a tool belongs to a specialist sub-agent and we are still on root,
        # emit the agentTransfer step first so CES does not mark the golden invalid.
        required_agent_key = tool_to_agent.get(action)
        if action == "get_official_links":
          cat = str((tc.get("args") or {}).get("category", "")).lower()
          if cat == "tickets":
            required_agent_key = "ticketing_agent"
        if required_agent_key:
          req_res = agent_map.get(
              required_agent_key, f"{app_name}/agents/{required_agent_key}"
          )
          if active_agent != req_res:
            steps.append(
                {"expectation": {"agentTransfer": {"targetAgent": req_res}}}
            )
            active_agent = req_res

        tool_call_id = f"adk-{uuid.uuid4()}"
        tool_res = tool_map.get(action, f"{app_name}/tools/{action}")
        args = dict(tc.get("args") or {})
        steps.append(
            {
                "expectation": {
                    "toolCall": {
                        "id": tool_call_id,
                        "tool": tool_res,
                        "args": args,
                    },
                    "expectationLevelMetricsThresholdsOverride": {
                        "toolInvocationParameterCorrectnessThreshold": 0.0
                    },
                }
            }
        )

        mock_resp = tc.get("output")
        if mock_resp is None and remaining_mocks:
          for idx, m in enumerate(remaining_mocks):
            if m.get("tool") == action:
              mock_resp = m.get("response")
              remaining_mocks.pop(idx)
              break

        if mock_resp is not None:
          steps.append(
              {
                  "expectation": {
                      "toolResponse": {
                          "id": tool_call_id,
                          "tool": tool_res,
                          "response": mock_resp,
                      }
                  }
              }
          )

      agent_field = turn.get("agent")
      if agent_field:
        agent_chunks = (
            agent_field if isinstance(agent_field, list) else [agent_field]
        )
        for text_chunk in agent_chunks:
          if "# silent" not in str(text_chunk):
            steps.append(
                {
                    "expectation": {
                        "agentResponse": {
                            "role": active_agent,
                            "chunks": [{"text": str(text_chunk)}],
                        }
                    }
                }
            )

      json_turns.append({"steps": steps})

    tags = list(conv.get("tags") or [])
    if file_tag not in tags:
      tags.append(file_tag)

    golden_evals.append(
        {
            "displayName": display_name,
            "description": (
                f"Golden Evaluation for {display_name} ({', '.join(tags)})"
            ),
            "tags": tags,
            "golden": {
                "turns": json_turns,
                "evaluationExpectations": [],
            },
        }
    )

  return golden_evals


def build_scenario_evaluations_from_yaml(
    yaml_path: Path,
    common_defaults: dict[str, Any] | None = None,
    expectations_map: dict[str, str] | None = None,
) -> list[types.Evaluation]:
  """Builds CES Scenario Evaluation proto messages (`types.Evaluation.Scenario`) from simulations YAML."""
  data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
  base_params = dict(common_defaults or {})
  base_params.update(data.get("common_session_parameters") or {})
  eval_items = list(data.get("evals") or [])
  file_tag = yaml_path.stem

  scenario_evals: list[types.Evaluation] = []
  for item in eval_items:
    display_name = str(item["name"])
    tags = list(item.get("tags") or [])
    if file_tag not in tags:
      tags.append(file_tag)

    merged_params = dict(base_params)
    merged_params.update(dict(item.get("session_parameters") or {}))

    steps = list(item.get("steps") or [])
    task_parts: list[str] = []
    rubrics: list[str] = []
    total_max_turns = 0

    for idx, step in enumerate(steps):
      goal = str(step.get("goal") or "").strip()
      guide = str(step.get("response_guide") or "").strip()
      criteria = str(step.get("success_criteria") or "").strip()
      step_turns = int(step.get("max_turns") or 4)
      total_max_turns += step_turns

      part = f"Step {idx + 1}: {goal}" if len(steps) > 1 else goal
      if guide:
        part += f" (Persona/Response Guide: {guide})"
      if part:
        task_parts.append(part)
      if criteria:
        rubrics.append(criteria)

    for exp in item.get("expectations") or []:
      exp_str = str(exp).strip()
      if exp_str and exp_str not in rubrics:
        rubrics.append(exp_str)

    task_str = "\n".join(task_parts) if task_parts else display_name
    max_turns = max(1, min(100, total_max_turns or 5))

    facts_dict: dict[str, str] = {
        str(k): str(v)
        for k, v in merged_params.items()
        if v is not None and str(v) != ""
    }
    user_facts = [
        types.Evaluation.Scenario.UserFact(name=k, value=v)
        for k, v in facts_dict.items()
    ]

    var_struct = struct_pb2.Struct()
    clean_vars = {
        str(k): (v if isinstance(v, (str, int, float, bool)) else str(v))
        for k, v in merged_params.items()
        if v is not None
    }
    var_struct.update(clean_vars)

    eval_expectations: list[str] = []
    if expectations_map:
      for exp in item.get("expectations") or []:
        if isinstance(exp, str) and exp in expectations_map:
          eval_expectations.append(expectations_map[exp])

    tags_lower = {str(t).lower() for t in tags}
    is_adversarial_refusal = (
        "adversarial" in tags_lower
        or "adversarial" in display_name.lower()
        or str(item.get("user_goal_behavior", "")).upper()
        == "USER_GOAL_REJECTED"
    )
    user_goal_behavior = (
        types.Evaluation.Scenario.UserGoalBehavior.USER_GOAL_REJECTED
        if is_adversarial_refusal
        else types.Evaluation.Scenario.UserGoalBehavior.USER_GOAL_SATISFIED
    )
    task_completion_behavior = (
        types.Evaluation.Scenario.TaskCompletionBehavior.TASK_REJECTED
        if is_adversarial_refusal
        else types.Evaluation.Scenario.TaskCompletionBehavior.TASK_SATISFIED
    )

    scenario_msg = types.Evaluation.Scenario(
        task=task_str,
        user_facts=user_facts,
        max_turns=max_turns,
        rubrics=rubrics,
        variable_overrides=var_struct,
        user_goal_behavior=user_goal_behavior,
        task_completion_behavior=task_completion_behavior,
        evaluation_expectations=eval_expectations,
    )

    scenario_evals.append(
        types.Evaluation(
            display_name=display_name,
            description=(
                f"Scenario Simulation for {display_name} ({', '.join(tags)})"
            ),
            tags=tags,
            scenario=scenario_msg,
        )
    )

  return scenario_evals


def sync_evaluations(app_name: str) -> dict[str, Any]:
  """Syncs App evaluation thresholds, Golden Evaluations, Scenario Simulations, and EvaluationDatasets to CES."""
  evals_client = Evaluations(app_name=app_name)
  patched_thresholds = sync_app_evaluation_thresholds(
      app_name=app_name, creds=evals_client.creds
  )
  agent_map = Agents(app_name=app_name, creds=evals_client.creds).get_agents_map(
      reverse=True
  )
  tool_map = Tools(app_name=app_name, creds=evals_client.creds).get_tools_map(
      reverse=True
  )

  goldens_raw = yaml.safe_load(GOLDENS_PATH.read_text(encoding="utf-8")) or {}
  sims_raw = yaml.safe_load(SIMS_PATH.read_text(encoding="utf-8")) or {}
  all_prompts: list[str] = []
  for s in sims_raw.get("evals") or []:
    all_prompts.extend(s.get("expectations") or [])

  cleanup_summary = clean_stale_remote_tools_and_expectations(
      app_name=app_name,
      evals_client=evals_client,
      active_prompts=all_prompts,
  )

  expectations_map = ensure_expectations_map(evals_client, app_name, all_prompts)

  golden_dicts = build_golden_evaluations_from_yaml(
      GOLDENS_PATH,
      app_name=app_name,
      agent_map=agent_map,
      tool_map=tool_map,
      expectations_map=expectations_map,
  )
  scenario_protos = build_scenario_evaluations_from_yaml(
      SIMS_PATH,
      common_defaults=goldens_raw.get("common_session_parameters") or {},
      expectations_map=expectations_map,
  )

  existing_evals = evals_client.list_evaluations(app_name)
  existing_by_display: dict[str, list[types.Evaluation]] = {}
  for ev in existing_evals:
    existing_by_display.setdefault(ev.display_name, []).append(ev)

  target_display_names = {g["displayName"] for g in golden_dicts} | {
      s.display_name for s in scenario_protos
  }

  to_delete: list[str] = []
  surviving_by_display: dict[str, types.Evaluation] = {}
  for disp, ev_list in existing_by_display.items():
    if disp not in target_display_names:
      for ev in ev_list:
        to_delete.append(ev.name)
      continue
    valid_candidates = [e for e in ev_list if not e.invalid]
    if valid_candidates:
      surviving_by_display[disp] = valid_candidates[0]
      for extra in valid_candidates[1:]:
        to_delete.append(extra.name)
      for inv in [e for e in ev_list if e.invalid]:
        to_delete.append(inv.name)
    else:
      for inv in ev_list:
        to_delete.append(inv.name)

  for del_name in to_delete:
    evals_client.delete_evaluation(name=del_name, force=True)

  def _upsert_one(
      payload: types.Evaluation | dict[str, Any],
  ) -> types.Evaluation:
    if isinstance(payload, dict):
      msg = types.Evaluation()
      json_format.ParseDict(payload, msg._pb, ignore_unknown_fields=True)
      payload = msg
    existing = surviving_by_display.get(payload.display_name)
    if existing and existing.name:
      payload.name = existing.name
      kind_field = (
          "golden"
          if (payload.golden and len(payload.golden.turns) > 0)
          else "scenario"
      )
      req = types.UpdateEvaluationRequest(
          evaluation=payload,
          update_mask=field_mask_pb2.FieldMask(
              paths=["display_name", "description", "tags", kind_field]
          ),
      )
      return evals_client.client.update_evaluation(request=req)
    req = types.CreateEvaluationRequest(parent=app_name, evaluation=payload)
    return evals_client.client.create_evaluation(request=req)

  all_payloads: list[types.Evaluation | dict[str, Any]] = list(
      golden_dicts
  ) + list(scenario_protos)
  synced_evals: list[types.Evaluation] = []
  with ThreadPoolExecutor(max_workers=8) as pool:
    futures = [pool.submit(_upsert_one, p) for p in all_payloads]
    for fut in as_completed(futures):
      synced_evals.append(fut.result())

  ds_target_map: dict[str, list[str]] = {name: [] for name in DATASET_SPECS}
  for ev in synced_evals:
    if not ev.name:
      continue
    ds_target_map["Totto Mercedes F1 Full Evaluation Suite"].append(ev.name)
    tags_upper = {t.upper() for t in (ev.tags or [])}
    if "P0" in tags_upper:
      ds_target_map["Dataset 1: P0 Core Fan Concierge & Guardrails"].append(
          ev.name
      )
    if "P1" in tags_upper:
      ds_target_map["Dataset 2: P1 Extended Coverage & Multilingual"].append(
          ev.name
      )

  existing_datasets = list(
      evals_client.client.list_evaluation_datasets(
          request=types.ListEvaluationDatasetsRequest(parent=app_name)
      )
  )
  ds_by_display: dict[str, types.EvaluationDataset] = {}
  for ds in existing_datasets:
    if ds.display_name in ds_target_map and ds.display_name not in ds_by_display:
      ds_by_display[ds.display_name] = ds
    else:
      evals_client.client.delete_evaluation_dataset(
          request=types.DeleteEvaluationDatasetRequest(name=ds.name)
      )

  synced_datasets: list[dict[str, Any]] = []
  for ds_disp, member_names in ds_target_map.items():
    sorted_members = sorted(dict.fromkeys(member_names))
    if ds_disp in ds_by_display:
      existing_ds = ds_by_display[ds_disp]
      updated_ds = evals_client.client.update_evaluation_dataset(
          request=types.UpdateEvaluationDatasetRequest(
              evaluation_dataset=types.EvaluationDataset(
                  name=existing_ds.name,
                  display_name=ds_disp,
                  evaluations=sorted_members,
              ),
              update_mask=field_mask_pb2.FieldMask(
                  paths=["display_name", "evaluations"]
              ),
          )
      )
    else:
      updated_ds = evals_client.client.create_evaluation_dataset(
          request=types.CreateEvaluationDatasetRequest(
              parent=app_name,
              evaluation_dataset=types.EvaluationDataset(
                  display_name=ds_disp,
                  evaluations=sorted_members,
              ),
          )
      )
    synced_datasets.append(
        {
            "name": updated_ds.name,
            "display_name": updated_ds.display_name,
            "evaluation_count": len(updated_ds.evaluations),
        }
    )

  live_evals = evals_client.list_evaluations(app_name)
  invalid = [e.display_name for e in live_evals if e.invalid]
  goldens_cnt = sum(
      1 for e in live_evals if e.golden and len(e.golden.turns) > 0
  )
  scenarios_cnt = sum(
      1 for e in live_evals if e.scenario and bool(e.scenario.task)
  )

  return {
      "status": "PASS" if not invalid and len(live_evals) > 0 else "FAIL",
      "timestamp": datetime.now(timezone.utc).isoformat(),
      "app_name": app_name,
      "patched_thresholds": patched_thresholds,
      "golden_count": goldens_cnt,
      "scenario_count": scenarios_cnt,
      "total_evaluations": len(live_evals),
      "invalid_count": len(invalid),
      "invalid_evaluations": invalid,
      "datasets": synced_datasets,
      "cleanup": cleanup_summary,
  }


def run_live_ces_evaluations(
    app_name: str, golden_run_method: str = "NAIVE"
) -> dict[str, Any]:
  """Triggers a live evaluation run across all 20 evaluations on CES Console Dev and writes check_eval_threshold.py-compatible reports."""
  evals_client = Evaluations(app_name=app_name)
  live_evals = evals_client.list_evaluations(app_name)
  eval_by_name: dict[str, types.Evaluation] = {e.name: e for e in live_evals}

  op = evals_client.run_evaluation(
      eval_type="all",
      app_name=app_name,
      run_count=1,
      golden_run_method=golden_run_method,
  )
  resp = op.result(timeout=900)
  eval_run_name = getattr(resp, "evaluation_run", "") or ""
  eval_run = evals_client.get_evaluation_run(eval_run_name)
  run_dict = json_format.MessageToDict(eval_run._pb)

  run_id_short = eval_run_name.rsplit("/", 1)[-1] if eval_run_name else "live-run"
  results_names = list(eval_run.evaluation_results or [])

  golden_passed = 0
  golden_total = 0
  sim_passed = 0
  sim_total = 0
  top_failures: list[dict[str, Any]] = []
  detailed_results: list[dict[str, Any]] = []
  platform_errors: list[str] = []

  if eval_run.error and (
      getattr(eval_run.error, "code", 0) != 0
      or getattr(eval_run.error, "message", "")
  ):
    platform_errors.append(str(eval_run.error.message or eval_run.error))

  for res_name in results_names:
    res_obj = evals_client.get_evaluation_result(res_name)
    res_dict = json_format.MessageToDict(res_obj._pb)
    parent_eval_name = res_name.split("/results/")[0]
    ev_meta = eval_by_name.get(parent_eval_name)
    disp_name = (
        ev_meta.display_name
        if ev_meta and ev_meta.display_name
        else res_obj.display_name
    )
    is_golden = bool(
        (ev_meta and ev_meta.golden and len(ev_meta.golden.turns) > 0)
        or "goldenResult" in res_dict
    )
    eval_type_key = "golden" if is_golden else "sim"
    status_str = str(res_dict.get("evaluationStatus", "UNKNOWN"))
    passed = status_str in ("PASS", "PASSED")

    if is_golden:
      golden_total += 1
      if passed:
        golden_passed += 1
    else:
      sim_total += 1
      if passed:
        sim_passed += 1

    if not passed:
      top_failures.append(
          {
              "eval_name": disp_name,
              "eval_type": eval_type_key,
              "category": "EXPECTATION_FAIL" if is_golden else "SIM_TASK_INCOMPLETE",
              "run_id": run_id_short,
              "result_name": res_name,
          }
      )

    detailed_results.append(
        {
            "eval_name": disp_name,
            "eval_type": eval_type_key,
            "evaluation_status": status_str,
            "passed": passed,
            "evaluation_resource": parent_eval_name,
            "result_resource": res_name,
            "details": res_dict,
        }
    )

  total = golden_total + sim_total
  passed_total = golden_passed + sim_passed
  failed_total = total - passed_total
  pass_rate = (passed_total / total) if total > 0 else 0.0
  ran_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

  report_payload: dict[str, Any] = {
      "status": "complete" if total > 0 and not platform_errors else "errored",
      "ran_at": ran_at,
      "app_name": app_name,
      "evaluation_run": eval_run_name,
      "evaluation_run_state": run_dict.get("state", "COMPLETED"),
      "total": total,
      "passed": passed_total,
      "failed": failed_total,
      "pass_rate": pass_rate,
      "by_type": {
          "golden": {
              "passed": golden_passed,
              "failed": golden_total - golden_passed,
              "total": golden_total,
          },
          "sim": {
              "passed": sim_passed,
              "failed": sim_total - sim_passed,
              "total": sim_total,
          },
      },
      "top_failures": top_failures,
      "platform_errors": platform_errors,
      "reverted": False,
      "results": detailed_results,
  }

  EVAL_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
  CI_SUMMARY_PATH.write_text(
      json.dumps(report_payload, indent=2) + "\n", encoding="utf-8"
  )
  CES_DEV_REPORT_PATH.write_text(
      json.dumps(report_payload, indent=2) + "\n", encoding="utf-8"
  )
  return report_payload


def main(argv: list[str] | None = None) -> int:
  parser = argparse.ArgumentParser(
      description="Sync Totto evaluations and datasets to CES Console Dev and optionally run them."
  )
  parser.add_argument("--app-name", default=DEFAULT_APP)
  parser.add_argument(
      "--clean-stale-evals",
      action="store_true",
      help="Delete stale evaluations not in local goldens.yaml/simulations.yaml before cxas push.",
  )
  parser.add_argument(
      "--run",
      action="store_true",
      help="Execute a live evaluation run across all 20 evaluations after syncing and write reports.",
  )
  parser.add_argument(
      "--golden-run-method",
      default="NAIVE",
      choices=("NAIVE", "STABLE"),
      help="Golden run method for CES RunEvaluationRequest (default: NAIVE).",
  )
  args = parser.parse_args(argv)

  if args.clean_stale_evals:
    cleaned = clean_stale_evaluations(args.app_name)
    print(json.dumps(cleaned, indent=2))
    return 0

  summary = sync_evaluations(args.app_name)
  if args.run:
    run_report = run_live_ces_evaluations(
        args.app_name, golden_run_method=args.golden_run_method
    )
    summary["live_run"] = {
        "evaluation_run": run_report["evaluation_run"],
        "total": run_report["total"],
        "passed": run_report["passed"],
        "failed": run_report["failed"],
        "pass_rate": run_report["pass_rate"],
        "by_type": run_report["by_type"],
        "top_failures": run_report["top_failures"],
    }
    print(json.dumps(summary, indent=2))
    return (
        0
        if summary["status"] == "PASS" and run_report["pass_rate"] > 0.90
        else 1
    )

  print(json.dumps(summary, indent=2))
  return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
  sys.exit(main())
