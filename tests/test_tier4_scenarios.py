"""Tier 4: Real-World Workload & End-to-End Application Scenarios (12 test cases).

Simulates complete multi-step fan journeys and verifies end-to-end compliance
across goldens.yaml, simulations.yaml, tool_tests.yaml, callback_tests/, and
cxas lint (0 errors, 0 deterministic warnings).
"""

from pathlib import Path
import subprocess
import sys
import time
from unittest.mock import patch
import urllib.error

from tests.conftest import (
    APP_DIR,
    EVALS_DIR,
    PROJECT_ROOT,
    DummyCallbackContext,
    load_before_agent_callback,
    load_tool_function,
    load_yaml_file,
)


def test_scenario_01_race_weekend_planning_and_timezone_clarification_journey() -> None:
  """E2E Journey 1: Fan plans race weekend -> prompted for timezone -> localized schedule & weather."""
  cb = load_before_agent_callback()
  get_race_schedule = load_tool_function("get_race_schedule")

  # Step 1: Session starts with empty state
  ctx = DummyCallbackContext({})
  assert cb(ctx) is None
  assert ctx.state["favorite_team"] == "Mercedes"
  assert ctx.state["user_location"] == ""

  # Step 2: Fan asks "What time is qualifying and the race this weekend?" without location
  step1_res = get_race_schedule(race_name="next", user_location=ctx.state["user_location"])
  assert step1_res["status"] == "success"
  assert step1_res["needs_user_location"] is True
  assert step1_res["data_freshness"] == "latest_available"
  assert "ask" in step1_res["agent_action"].lower()
  assert step1_res["race"]["race_name"] == "Miami Grand Prix"

  # Step 3: Fan replies "I'm in New York" -> state updated -> callback preserves -> localized EDT times
  ctx.state["user_location"] = "New York"
  assert cb(ctx) is None
  step2_res = get_race_schedule(race_name="next", user_location=ctx.state["user_location"])
  assert step2_res["status"] == "success"
  assert step2_res["needs_user_location"] is False
  assert "EDT" in step2_res["localized_sessions"]["Qualifying"]
  assert "EDT" in step2_res["localized_sessions"]["Race"]
  assert step2_res["race"]["weather"]["temperature_c"] == 29
  assert "Russell" in step2_res["race"]["mercedes_context"]


def test_scenario_02_silver_arrows_championship_and_recent_results_debrief() -> None:
  """E2E Journey 2: Fan asks for Drivers' & Constructors' standings and recent Mercedes results."""
  cb = load_before_agent_callback()
  get_driver_standings = load_tool_function("get_driver_standings")

  ctx = DummyCallbackContext({})
  cb(ctx)

  # Step 1: Driver standings focusing on Mercedes
  drv_res = get_driver_standings(category="drivers", team_filter=ctx.state["favorite_team"])
  assert drv_res["status"] == "success"
  assert drv_res["data_freshness"] == "latest_available"
  assert "latest" in drv_res["freshness_disclosure"].lower()
  merc_drivers = drv_res["mercedes_drivers"]
  assert len(merc_drivers) == 2
  assert any("George Russell" in str(d) and "63" in str(d) for d in merc_drivers)
  assert any("Kimi Antonelli" in str(d) and "12" in str(d) for d in merc_drivers)

  # Step 2: Constructor standings & recent race results
  con_res = get_driver_standings(category="constructors", team_filter="Mercedes")
  assert con_res["status"] == "success"
  assert "Mercedes" in str(con_res["mercedes_constructor"])
  assert "recent_results" in con_res and len(con_res["recent_results"]) > 0


def test_scenario_03_trackside_attendance_and_non_transactional_ticketing_journey() -> None:
  """E2E Journey 3: Fan asks to buy/price British GP tickets and check Silverstone dates."""
  get_official_links = load_tool_function("get_official_links")
  get_race_schedule = load_tool_function("get_race_schedule")

  # Step 1: Fetch official F1 ticketing link (non-transactional)
  tickets_res = get_official_links(category="tickets")
  assert tickets_res["status"] == "success"
  assert "https://www.formula1.com/en/tickets" in str(tickets_res)
  assert (
      "cannot sell" in str(tickets_res).lower()
      or "not sell" in str(tickets_res).lower()
      or "official" in str(tickets_res).lower()
  )

  # Step 2: Provide Silverstone race weekend schedule context
  sched_res = get_race_schedule(race_name="silverstone", user_location="London")
  assert sched_res["status"] == "success"
  assert sched_res["race"]["race_name"] == "British Grand Prix"
  assert sched_res["race"]["circuit"] == "Silverstone Circuit"
  assert "July" in sched_res["race"]["dates"]


def test_scenario_04_merch_full_post_purchase_support_journey() -> None:
  """E2E Journey 4: Fan tracks order MERC-1001, files damaged-item claim, checks stock & store link."""
  cb = load_before_agent_callback()
  lookup_order = load_tool_function("lookup_merch_order")
  submit_request = load_tool_function("submit_merch_request")
  check_avail = load_tool_function("check_merch_availability")
  get_links = load_tool_function("get_official_links")

  ctx = DummyCallbackContext({})
  cb(ctx)
  assert ctx.state["is_mock_mode"] == "true"

  # Step 1: Track order MERC-1001 using only order number
  ctx.state["order_number"] = "MERC-1001"
  cb(ctx)
  lookup_res = lookup_order(order_number=ctx.state["order_number"])
  assert lookup_res["status"] == "success"
  assert "order_note" in lookup_res
  assert lookup_res["order"]["status"] == "Delivered"

  # Step 2: Submit damaged item claim for the cap
  claim_res = submit_request(
      order_number=ctx.state["order_number"],
      request_type="damaged_item",
      item_name="George Russell #63 Driver Cap",
      reason="Visor stitching arrived damaged",
  )
  assert claim_res["status"] == "success"
  assert "request_note" in claim_res
  assert "MERC-REQ" in claim_res["reference_id"] and "1001" in claim_res["reference_id"]

  # Step 3: Check stock for replacement cap and team polo
  cap_avail = check_avail(item_query="George Russell cap", size="One Size")
  assert cap_avail["status"] == "success"
  assert cap_avail["in_stock"] is True

  # Step 4: Direct new purchases to official Mercedes F1 store
  store_link = get_links(category="merch")
  assert store_link["status"] == "success"
  assert "https://shop.mercedesamgf1.com/" in str(store_link)


def test_scenario_05_multi_domain_error_recovery_journey() -> None:
  """E2E Journey 5: Fan hits MERC-9999, XXL out-of-stock, signed race suit, and Narnia GP errors."""
  lookup_order = load_tool_function("lookup_merch_order")
  submit_request = load_tool_function("submit_merch_request")
  check_avail = load_tool_function("check_merch_availability")
  get_schedule = load_tool_function("get_race_schedule")
  get_standings = load_tool_function("get_driver_standings")
  get_links = load_tool_function("get_official_links")

  err_lookup = lookup_order(order_number="MERC-9999")
  assert err_lookup["status"] == "error" and "MERC-1001" in err_lookup["agent_action"]

  err_submit = submit_request(order_number="MERC-9999", request_type="return")
  assert err_submit["status"] == "error" and len(err_submit["agent_action"]) > 15

  err_size = check_avail(item_query="polo", size="XXL")
  assert err_size["status"] == "error" and err_size["in_stock"] is False
  assert "shop.mercedesamgf1.com" in err_size["agent_action"]

  err_item = check_avail(item_query="signed race suit", size="")
  assert err_item["status"] == "error" and err_item["in_stock"] is False

  err_race = get_schedule(race_name="Narnia Grand Prix", user_location="London")
  assert err_race["status"] == "error" and len(err_race["supported_races"]) >= 5

  err_stand = get_standings(category="invalid_category", team_filter="Mercedes")
  assert err_stand["status"] == "error" and len(err_stand["agent_action"]) > 15

  err_links = get_links(category="betting")
  assert err_links["status"] == "error" and len(err_links["agent_action"]) > 15


def test_scenario_06_goldens_yaml_covers_all_required_cujs_and_failure_adversarial_scenarios() -> None:
  """E2E Journey 6: Verify goldens.yaml covers all required happy-path CUJs and failure/adversarial cases."""
  goldens = load_yaml_file(EVALS_DIR / "goldens" / "goldens.yaml")
  assert "common_session_parameters" in goldens
  assert goldens["common_session_parameters"].get("favorite_team") == "Mercedes"
  assert goldens["common_session_parameters"].get("initialized") == "true"

  convs = goldens.get("conversations", [])
  assert len(convs) >= 12
  full_text = str(convs).lower()

  # Verify required happy-path and failure/negative/adversarial scenarios
  assert "totto, mercedes f1 fan agent" in full_text and "fictional" in full_text
  assert "merc-1001" in full_text
  assert "merc-9999" in full_text  # Invalid order ID
  assert "xxl" in full_text  # Out-of-stock merch size
  assert "general formula 1 knowledge" in full_text or "general f1 knowledge" in full_text  # Historical disclosure
  assert "toto wolff" in full_text  # Impersonation refusal
  assert "strategy" in full_text or "telemetry" in full_text  # Insider strategy refusal
  assert "guarantee" in full_text or "prediction" in full_text  # Guaranteed prediction refusal
  assert "https://www.formula1.com/en/tickets" in full_text  # Direct ticket sales refusal & redirect
  assert "credit card" in full_text or "4111" in full_text or "payment" in full_text  # Real payment refusal
  assert "red bull" in full_text or "rival" in full_text or "fia" in full_text  # Rival trash-talk refusal
  assert "hola" in full_text or "español" in full_text or "pilotos" in full_text  # Multilingual


def test_scenario_07_simulations_yaml_covers_all_required_cujs_and_failure_adversarial_scenarios() -> None:
  """E2E Journey 7: Verify simulations.yaml covers all required happy-path CUJs and failure/adversarial cases."""
  sims = load_yaml_file(EVALS_DIR / "simulations" / "simulations.yaml")
  evals = sims.get("evals", [])
  assert len(evals) >= 8

  for item in evals:
    assert item.get("name")
    assert isinstance(item.get("tags"), list) and len(item["tags"]) >= 1
    assert isinstance(item.get("steps"), list) and len(item["steps"]) >= 1
    assert isinstance(item.get("expectations"), list) and len(item["expectations"]) >= 1
    for step in item["steps"]:
      assert step.get("goal")
      assert step.get("success_criteria")

  full_text = str(evals).lower()
  assert "timezone" in full_text or "location" in full_text
  assert "merc-9999" in full_text
  assert "xxl" in full_text
  assert "general" in full_text and "knowledge" in full_text
  assert "toto wolff" in full_text
  assert "telemetry" in full_text or "strategy" in full_text
  assert "formula1.com/en/tickets" in full_text
  assert "shop.mercedesamgf1.com" in full_text
  assert "red bull" in full_text or "rival" in full_text
  assert "credit card" in full_text or "payment" in full_text


def test_scenario_08_openf1_total_outage_resilience_across_race_and_standings_journey() -> None:
  """E2E Journey 8: Complete race schedule & standings journey during total OpenF1 outage (<= 5s)."""
  get_race_schedule = load_tool_function("get_race_schedule")
  get_driver_standings = load_tool_function("get_driver_standings")

  with (
      patch("requests.get", side_effect=OSError("Total network blackout")),
      patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Total network blackout")),
  ):
    t0 = time.monotonic()
    sched = get_race_schedule(race_name="next", user_location="London")
    standings = get_driver_standings(category="both", team_filter="Mercedes")
    elapsed = time.monotonic() - t0

  assert elapsed <= 5.0
  assert sched["status"] == "success"
  assert sched["data_freshness"] == "latest_available"
  assert sched["race"]["race_name"] == "Miami Grand Prix"
  assert standings["status"] == "success"
  assert standings["data_freshness"] == "latest_available"
  assert len(standings["mercedes_drivers"]) == 2


def test_scenario_09_cxas_linter_zero_errors_and_zero_warnings_gate() -> None:
  """E2E Journey 9: Run cxas_scrapi linter rules directly and assert 0 errors and 0 warnings."""
  from cxas_scrapi.utils.linter import (
      Discovery,
      LintConfig,
      LintReport,
      build_context,
      build_registry,
      run_rules,
  )

  cfg = LintConfig.load(PROJECT_ROOT)
  discovery = Discovery(PROJECT_ROOT / cfg.app_dir, PROJECT_ROOT / cfg.evals_dir)
  registry = build_registry()
  context = build_context(PROJECT_ROOT, cfg, discovery)
  report = LintReport()
  run_rules(registry, cfg, context, discovery, report)
  assert len(report.errors) == 0, f"Expected 0 lint errors, got {len(report.errors)}: {report.errors}"
  assert len(report.warnings) == 0, f"Expected 0 lint warnings, got {len(report.warnings)}: {report.warnings}"


def test_scenario_10_lint_harness_script_exits_zero() -> None:
  """E2E Journey 10: Verify lint-harness.py executes cleanly with exit code 0."""
  harness_path = PROJECT_ROOT / ".agents" / "skills" / "cxas-agent-foundry" / "scripts" / "lint-harness.py"
  if not harness_path.is_file():
    harness_path = Path.home() / ".agents" / "skills" / "cxas-agent-foundry" / "scripts" / "lint-harness.py"
  assert harness_path.is_file(), f"Missing lint-harness.py at {harness_path}"
  proc = subprocess.run(
      [sys.executable, "-B", str(harness_path), str(PROJECT_ROOT)],
      cwd=str(PROJECT_ROOT),
      capture_output=True,
      text=True,
      timeout=30,
      check=False,
  )
  assert proc.returncode == 0, f"lint-harness.py failed:\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"


def test_scenario_11_callback_evals_suite_passes_100_percent() -> None:
  """E2E Journey 11: Run pytest on evals/callback_tests and verify 100% pass rate."""
  proc = subprocess.run(
      [sys.executable, "-m", "pytest", str(EVALS_DIR / "callback_tests"), "-q"],
      cwd=str(PROJECT_ROOT),
      capture_output=True,
      text=True,
      timeout=30,
      check=False,
  )
  assert proc.returncode == 0, f"callback_tests failed:\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"


def test_scenario_12_tool_evals_pydantic_schema_validation_passes() -> None:
  """E2E Journey 12: Validate goldens.yaml, simulations.yaml, and tool_tests.yaml against cxas_scrapi Pydantic schemas."""
  from cxas_scrapi.evals.simulation_evals import LLMUserConversation, Step
  from cxas_scrapi.evals.tool_evals import ToolTestCase
  from cxas_scrapi.utils.eval_utils import Conversations

  goldens_raw = load_yaml_file(EVALS_DIR / "goldens" / "goldens.yaml")
  parsed_goldens = Conversations.model_validate(goldens_raw)
  assert len(parsed_goldens.conversations) >= 12

  sims_raw = load_yaml_file(EVALS_DIR / "simulations" / "simulations.yaml")
  for sim_entry in sims_raw.get("evals", []):
    if hasattr(LLMUserConversation, "model_validate"):
      parsed_steps = LLMUserConversation.model_validate(sim_entry).steps
    else:
      parsed_steps = [Step.model_validate(s) for s in sim_entry.get("steps", [])]
    assert len(parsed_steps) >= 1

  tool_tests_raw = load_yaml_file(EVALS_DIR / "tool_tests" / "tool_tests.yaml")
  for tt_entry in tool_tests_raw.get("tests", []):
    parsed_tt = ToolTestCase.model_validate(tt_entry)
    assert parsed_tt.tool
