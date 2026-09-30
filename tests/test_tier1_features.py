"""Tier 1: Category-Partition Feature Coverage E2E Tests (F1-F15, 75 test cases).

Covers primary happy-path behavior, configuration manifests, XML instruction
structure, persona/guardrails, callback initialization, all 6 custom tools,
and evaluation suite structure across all 15 features in PROJECT.md.
"""

import inspect
import re
from typing import Any

from tests.conftest import (
    AGENTS_DIR,
    APP_DIR,
    EVALS_DIR,
    EXPECTED_AGENTS,
    EXPECTED_TOOLS,
    EXPECTED_VARIABLES,
    PROJECT_ROOT,
    TOOLS_DIR,
    DummyCallbackContext,
    load_before_agent_callback,
    load_json_file,
    load_tool_function,
    load_yaml_file,
)


# ==============================================================================
# F1: Fictional Persona & Self-Introduction (5 test cases)
# ==============================================================================
class TestF1PersonaAndIdentity:
  """Tests F1: Totto, Mercedes F1 Fan Agent identity & fictional AI framing."""

  def test_f1_root_instruction_introduces_totto_mercedes_f1_fan_agent(self) -> None:
    content = (AGENTS_DIR / "totto_root_agent" / "instruction.txt").read_text(encoding="utf-8")
    assert "Totto, Mercedes F1 Fan Agent" in content
    assert "<role>" in content and "</role>" in content

  def test_f1_root_instruction_explicitly_states_fictional_ai_concierge(self) -> None:
    content = (AGENTS_DIR / "totto_root_agent" / "instruction.txt").read_text(encoding="utf-8").lower()
    assert "fictional" in content
    assert "toto wolff" in content

  def test_f1_all_subagents_maintain_totto_fictional_identity(self) -> None:
    for agent_name in EXPECTED_AGENTS:
      content = (AGENTS_DIR / agent_name / "instruction.txt").read_text(encoding="utf-8")
      assert "Totto, Mercedes F1 Fan Agent" in content, f"{agent_name} missing canonical name"

  def test_f1_prd_and_tdd_document_fictional_totto_identity(self) -> None:
    prd_text = (PROJECT_ROOT / "prd.md").read_text(encoding="utf-8")
    tdd_text = (PROJECT_ROOT / "tdd.md").read_text(encoding="utf-8")
    assert "Totto, Mercedes F1 Fan Agent" in prd_text
    assert "Totto, Mercedes F1 Fan Agent" in tdd_text
    assert "fictional" in prd_text.lower()

  def test_f1_golden_eval_covers_welcome_and_totto_identity(self) -> None:
    goldens = load_yaml_file(EVALS_DIR / "goldens" / "goldens.yaml")
    convs = goldens.get("conversations", [])
    assert any(
        "Totto, Mercedes F1 Fan Agent" in str(turn.get("agent", ""))
        and "fictional" in str(turn.get("agent", "")).lower()
        for c in convs
        for turn in c.get("turns", [])
    ), "Golden evaluations must include a turn introducing Totto as a fictional AI fan agent"


# ==============================================================================
# F2: Voice-First Concise Delivery (5 test cases)
# ==============================================================================
class TestF2VoiceFirstDelivery:
  """Tests F2: Voice-first, concise 2-3 sentence spoken delivery across agents."""

  def test_f2_all_agents_specify_voice_first_concise_persona(self) -> None:
    for agent_name in EXPECTED_AGENTS:
      content = (AGENTS_DIR / agent_name / "instruction.txt").read_text(encoding="utf-8").lower()
      assert "voice-first" in content or "spoken" in content, f"{agent_name} missing voice-first persona"
      assert (
          "two to three" in content
          or "two-to-three" in content
          or "2-3" in content
          or "concise" in content
      )

  def test_f2_app_json_uses_live_voice_model_settings(self) -> None:
    app_data = load_json_file(APP_DIR / "app.json")
    assert "modelSettings" in app_data
    assert "model" in app_data["modelSettings"]
    assert app_data.get("languageSettings", {}).get("defaultLanguageCode") == "en-US"

  def test_f2_root_instruction_forbids_markdown_clutter_in_voice_output(self) -> None:
    content = (AGENTS_DIR / "totto_root_agent" / "instruction.txt").read_text(encoding="utf-8").lower()
    assert "markdown" in content or "spoken" in content

  def test_f2_instructions_offer_follow_up_detail_after_concise_answer(self) -> None:
    root_text = (AGENTS_DIR / "totto_root_agent" / "instruction.txt").read_text(encoding="utf-8").lower()
    race_text = (AGENTS_DIR / "race_info_agent" / "instruction.txt").read_text(encoding="utf-8").lower()
    assert "more detail" in root_text or "deeper" in root_text
    assert "deeper" in race_text or "more" in race_text

  def test_f2_instructions_require_clarifying_questions_when_context_missing(self) -> None:
    race_text = (AGENTS_DIR / "race_info_agent" / "instruction.txt").read_text(encoding="utf-8").lower()
    merch_text = (AGENTS_DIR / "merch_support_agent" / "instruction.txt").read_text(encoding="utf-8").lower()
    assert "ask" in race_text and ("location" in race_text or "timezone" in race_text)
    assert "ask" in merch_text and "order number" in merch_text


# ==============================================================================
# F3: Mercedes-First Priority & Brand-Safe Sportsmanship (5 test cases)
# ==============================================================================
class TestF3MercedesFirstAndSportsmanship:
  """Tests F3: Mercedes-AMG PETRONAS priority, Russell #63 / Antonelli #12, sportsmanship."""

  def test_f3_root_and_race_instructions_highlight_russell_and_antonelli(self) -> None:
    for agent_name in ("totto_root_agent", "race_info_agent"):
      text = (AGENTS_DIR / agent_name / "instruction.txt").read_text(encoding="utf-8")
      assert "George Russell" in text
      assert "Kimi Antonelli" in text
      assert "Silver Arrows" in text

  def test_f3_instructions_require_respect_toward_rivals_and_fia(self) -> None:
    for agent_name in ("totto_root_agent", "race_info_agent"):
      text = (AGENTS_DIR / agent_name / "instruction.txt").read_text(encoding="utf-8").lower()
      assert "rival" in text and "respect" in text and "fia" in text

  def test_f3_race_schedule_includes_mercedes_context_for_featured_races(self) -> None:
    get_race_schedule = load_tool_function("get_race_schedule")
    for race_key in ("miami", "monaco", "silverstone", "monza", "las_vegas"):
      res = get_race_schedule(race_name=race_key, user_location="London")
      assert res["status"] == "success"
      mercedes_ctx = res["race"].get("mercedes_context", "")
      assert len(mercedes_ctx) > 20
      assert any(tok in mercedes_ctx for tok in ("Mercedes", "Russell", "Antonelli", "Silver Arrows", "W17", "Brackley"))

  def test_f3_driver_standings_prioritizes_mercedes_drivers_and_constructor(self) -> None:
    get_driver_standings = load_tool_function("get_driver_standings")
    res = get_driver_standings(category="drivers", team_filter="Mercedes")
    assert res["status"] == "success"
    merc_drivers = res.get("mercedes_drivers", [])
    assert len(merc_drivers) >= 2
    driver_names = " ".join(str(d) for d in merc_drivers)
    assert "George Russell" in driver_names and "63" in driver_names
    assert "Kimi Antonelli" in driver_names and "12" in driver_names

  def test_f3_before_agent_callback_defaults_favorite_team_to_mercedes(self) -> None:
    cb = load_before_agent_callback()
    ctx = DummyCallbackContext({})
    ret = cb(ctx)
    assert ret is None
    assert ctx.state["favorite_team"] == "Mercedes"


# ==============================================================================
# F4: Race & Session Schedule + Weather (`get_race_schedule`) (5 test cases)
# ==============================================================================
class TestF4RaceScheduleAndWeather:
  """Tests F4: get_race_schedule happy paths across races, sessions, and weather."""

  def test_f4_get_race_schedule_next_returns_miami_sprint_weekend(self) -> None:
    get_race_schedule = load_tool_function("get_race_schedule")
    res = get_race_schedule(race_name="next", user_location="London")
    assert res["status"] == "success"
    assert res["data_freshness"] == "latest_available"
    race = res["race"]
    assert race["race_name"] == "Miami Grand Prix"
    assert race["circuit"] == "Miami International Autodrome"
    assert race["is_sprint_weekend"] is True
    assert "Sprint" in race["sessions_utc"]
    assert "Qualifying" in race["sessions_utc"]
    assert "Race" in race["sessions_utc"]

  def test_f4_get_race_schedule_returns_complete_weather_forecast(self) -> None:
    get_race_schedule = load_tool_function("get_race_schedule")
    res = get_race_schedule(race_name="silverstone", user_location="London")
    assert res["status"] == "success"
    weather = res["race"]["weather"]
    for key in ("condition", "temperature_c", "temperature_f", "rain_chance_percent", "wind"):
      assert key in weather, f"Missing weather key: {key}"

  def test_f4_get_race_schedule_supports_monaco_monza_and_las_vegas(self) -> None:
    get_race_schedule = load_tool_function("get_race_schedule")
    expected = {
        "monaco": "Monaco Grand Prix",
        "monza": "Italian Grand Prix",
        "las vegas": "Las Vegas Grand Prix",
    }
    for query, title in expected.items():
      res = get_race_schedule(race_name=query, user_location="London")
      assert res["status"] == "success"
      assert res["race"]["race_name"] == title

  def test_f4_get_race_schedule_supports_bahrain_australia_and_suzuka(self) -> None:
    get_race_schedule = load_tool_function("get_race_schedule")
    for query in ("bahrain", "australia", "suzuka"):
      res = get_race_schedule(race_name=query, user_location="London")
      assert res["status"] == "success"
      assert "race" in res and "race_name" in res["race"]

  def test_f4_get_race_schedule_calendar_overview_all(self) -> None:
    get_race_schedule = load_tool_function("get_race_schedule")
    res = get_race_schedule(race_name="all", user_location="")
    assert res["status"] == "success"
    assert res["data_freshness"] == "latest_available"
    featured = res.get("featured_races", [])
    assert isinstance(featured, list) and len(featured) >= 5


# ==============================================================================
# F5: Time & Location Localization (5 test cases)
# ==============================================================================
class TestF5TimeAndLocationLocalization:
  """Tests F5: Timezone localization and missing user_location handling."""

  def test_f5_missing_user_location_flags_needs_user_location_and_agent_action(self) -> None:
    get_race_schedule = load_tool_function("get_race_schedule")
    res = get_race_schedule(race_name="miami", user_location="")
    assert res["status"] == "success"
    assert res["needs_user_location"] is True
    assert isinstance(res.get("agent_action"), str) and len(res["agent_action"]) > 10
    assert "sessions_utc" in res["race"]
    assert "sessions_venue" in res["race"]

  def test_f5_london_location_converts_miami_sessions_to_bst(self) -> None:
    get_race_schedule = load_tool_function("get_race_schedule")
    res = get_race_schedule(race_name="miami", user_location="London")
    assert res["status"] == "success"
    assert res["needs_user_location"] is False
    assert "BST" in res["localized_sessions"]["Race"]
    assert "21:00" in res["localized_sessions"]["Race"]

  def test_f5_new_york_location_converts_silverstone_sessions_to_edt(self) -> None:
    get_race_schedule = load_tool_function("get_race_schedule")
    res = get_race_schedule(race_name="silverstone", user_location="New York")
    assert res["status"] == "success"
    assert res["needs_user_location"] is False
    assert "EDT" in res["localized_sessions"]["Race"]
    assert "10:00" in res["localized_sessions"]["Race"]

  def test_f5_tokyo_location_converts_sessions_to_jst_with_day_rollover(self) -> None:
    get_race_schedule = load_tool_function("get_race_schedule")
    res = get_race_schedule(race_name="miami", user_location="Tokyo")
    assert res["status"] == "success"
    assert res["needs_user_location"] is False
    assert "JST" in res["localized_sessions"]["Race"]
    assert "Monday 05:00" in res["localized_sessions"]["Race"]

  def test_f5_european_cities_convert_sessions_to_cest(self) -> None:
    get_race_schedule = load_tool_function("get_race_schedule")
    for city in ("Berlin", "Paris", "Milan"):
      res = get_race_schedule(race_name="monaco", user_location=city)
      assert res["status"] == "success"
      assert res["needs_user_location"] is False
      assert "CEST" in res["localized_sessions"]["Qualifying"]


# ==============================================================================
# F6: Driver & Constructor Standings + Recent Results (`get_driver_standings`) (5 test cases)
# ==============================================================================
class TestF6DriverAndConstructorStandings:
  """Tests F6: get_driver_standings happy paths for drivers, constructors, results."""

  def test_f6_drivers_category_returns_standings_and_mercedes_drivers(self) -> None:
    get_driver_standings = load_tool_function("get_driver_standings")
    res = get_driver_standings(category="drivers", team_filter="Mercedes")
    assert res["status"] == "success"
    assert res["data_freshness"] == "latest_available"
    assert isinstance(res.get("driver_standings"), list) and len(res["driver_standings"]) >= 5
    assert isinstance(res.get("mercedes_drivers"), list) and len(res["mercedes_drivers"]) == 2

  def test_f6_constructors_category_returns_constructor_standings_and_mercedes_summary(self) -> None:
    get_driver_standings = load_tool_function("get_driver_standings")
    res = get_driver_standings(category="constructors", team_filter="Mercedes")
    assert res["status"] == "success"
    assert isinstance(res.get("constructor_standings"), list) and len(res["constructor_standings"]) >= 4
    assert isinstance(res.get("mercedes_constructor"), dict)
    assert "Mercedes" in str(res["mercedes_constructor"])

  def test_f6_both_and_all_categories_return_full_championship_context(self) -> None:
    get_driver_standings = load_tool_function("get_driver_standings")
    for cat in ("both", "all", "results"):
      res = get_driver_standings(category=cat, team_filter="Mercedes")
      assert res["status"] == "success"
      assert "driver_standings" in res
      assert "constructor_standings" in res
      assert "recent_results" in res

  def test_f6_recent_results_highlights_mercedes_finishers(self) -> None:
    get_driver_standings = load_tool_function("get_driver_standings")
    res = get_driver_standings(category="results", team_filter="Mercedes")
    assert res["status"] == "success"
    recent = res.get("recent_results", {})
    assert isinstance(recent, dict) and len(recent) > 0
    recent_str = str(recent)
    assert "Russell" in recent_str or "Antonelli" in recent_str or "Mercedes" in recent_str

  def test_f6_dual_jsonpath_result_mirror_present_on_standings(self) -> None:
    get_driver_standings = load_tool_function("get_driver_standings")
    res = get_driver_standings(category="drivers", team_filter="Mercedes")
    assert res["status"] == "success"
    assert "result" in res and isinstance(res["result"], dict)
    assert res["result"]["status"] == "success"
    assert res["result"]["data_freshness"] == "latest_available"


# ==============================================================================
# F7: Latest-Available Data Freshness Disclosure & Strategy/Prediction Guardrails (5 test cases)
# ==============================================================================
class TestF7FreshnessAndStrategyGuardrails:
  """Tests F7: Data freshness disclosures & confidential strategy/prediction refusals."""

  def test_f7_get_race_schedule_always_includes_latest_available_freshness(self) -> None:
    get_race_schedule = load_tool_function("get_race_schedule")
    res = get_race_schedule(race_name="next", user_location="London")
    assert res.get("data_freshness") == "latest_available"

  def test_f7_get_driver_standings_includes_freshness_disclosure(self) -> None:
    get_driver_standings = load_tool_function("get_driver_standings")
    res = get_driver_standings(category="drivers", team_filter="Mercedes")
    assert res.get("data_freshness") == "latest_available"
    assert "latest" in res.get("freshness_disclosure", "").lower()

  def test_f7_race_info_agent_instruction_requires_latest_available_disclosure(self) -> None:
    text = (AGENTS_DIR / "race_info_agent" / "instruction.txt").read_text(encoding="utf-8").lower()
    assert "latest available" in text
    assert "telemetry" in text

  def test_f7_root_and_race_instructions_forbid_strategy_leaks_and_guaranteed_predictions(self) -> None:
    for agent_name in ("totto_root_agent", "race_info_agent"):
      text = (AGENTS_DIR / agent_name / "instruction.txt").read_text(encoding="utf-8").lower()
      assert "telemetry" in text
      assert "guaranteed" in text and "prediction" in text

  def test_f7_goldens_and_simulations_test_strategy_and_prediction_refusal(self) -> None:
    goldens_text = (EVALS_DIR / "goldens" / "goldens.yaml").read_text(encoding="utf-8").lower()
    sims_text = (EVALS_DIR / "simulations" / "simulations.yaml").read_text(encoding="utf-8").lower()
    assert "strategy" in goldens_text or "telemetry" in goldens_text
    assert "guarantee" in goldens_text or "prediction" in goldens_text
    assert "telemetry" in sims_text or "strategy" in sims_text


# ==============================================================================
# F8: Historical & Educational F1 Q&A with General-Knowledge Disclosure (5 test cases)
# ==============================================================================
class TestF8HistoricalAndEducationalQA:
  """Tests F8: Mercedes/F1 history & rules Q&A with general-knowledge disclosure."""

  def test_f8_root_instruction_has_history_and_education_subtask(self) -> None:
    text = (AGENTS_DIR / "totto_root_agent" / "instruction.txt").read_text(encoding="utf-8")
    assert "f1_and_mercedes_history_and_education" in text or "history" in text.lower()
    assert "DRS" in text or "rules" in text.lower()

  def test_f8_root_instruction_mandates_general_knowledge_disclosure(self) -> None:
    text = (AGENTS_DIR / "totto_root_agent" / "instruction.txt").read_text(encoding="utf-8").lower()
    assert "general formula 1 knowledge" in text or "general f1 knowledge" in text
    assert "uncertain" in text or "verified" in text

  def test_f8_race_info_instruction_also_discloses_general_knowledge_for_history(self) -> None:
    text = (AGENTS_DIR / "race_info_agent" / "instruction.txt").read_text(encoding="utf-8").lower()
    assert "general formula 1 knowledge" in text or "general f1 knowledge" in text

  def test_f8_golden_eval_verifies_historical_general_knowledge_disclosure(self) -> None:
    goldens = load_yaml_file(EVALS_DIR / "goldens" / "goldens.yaml")
    convs = goldens.get("conversations", [])
    assert any(
        "general" in str(turn.get("agent", "")).lower()
        and "knowledge" in str(turn.get("agent", "")).lower()
        for c in convs
        for turn in c.get("turns", [])
    ), "Golden evals must include a turn disclosing reliance on general Formula 1 knowledge"

  def test_f8_simulation_eval_verifies_historical_and_rules_uncertainty_disclosure(self) -> None:
    sims = load_yaml_file(EVALS_DIR / "simulations" / "simulations.yaml")
    eval_list = sims.get("evals", [])
    assert any(
        "history" in str(item).lower() and "general" in str(item).lower()
        for item in eval_list
    ), "Simulation evals must include an F1/Mercedes history general-knowledge disclosure scenario"


# ==============================================================================
# F9: Non-Transactional Official F1 Ticketing Guidance (`ticketing_agent`) (5 test cases)
# ==============================================================================
class TestF9OfficialTicketingGuidance:
  """Tests F9: Non-transactional F1 ticketing redirection and schedule context."""

  def test_f9_ticketing_agent_json_declares_required_tools(self) -> None:
    cfg = load_json_file(AGENTS_DIR / "ticketing_agent" / "ticketing_agent.json")
    tools = cfg.get("tools", [])
    assert "get_official_links" in tools
    assert "get_race_schedule" in tools
    assert "end_session" in tools

  def test_f9_ticketing_agent_instruction_prohibits_direct_sales_pricing_and_inventory(self) -> None:
    text = (AGENTS_DIR / "ticketing_agent" / "instruction.txt").read_text(encoding="utf-8").lower()
    for term in ("sell", "reserve", "book", "price", "inventory"):
      assert term in text, f"ticketing_agent instruction missing prohibition on '{term}'"

  def test_f9_ticketing_agent_instruction_references_both_tools_and_end_session(self) -> None:
    text = (AGENTS_DIR / "ticketing_agent" / "instruction.txt").read_text(encoding="utf-8")
    assert "{@TOOL: get_official_links}" in text
    assert "{@TOOL: get_race_schedule}" in text
    assert "{@TOOL: end_session}" in text

  def test_f9_get_official_links_tickets_returns_canonical_formula1_tickets_url(self) -> None:
    get_official_links = load_tool_function("get_official_links")
    res = get_official_links(category="tickets")
    assert res["status"] == "success"
    assert "https://www.formula1.com/en/tickets" in str(res)

  def test_f9_goldens_and_simulations_cover_ticket_booking_refusal_and_redirect(self) -> None:
    goldens_text = (EVALS_DIR / "goldens" / "goldens.yaml").read_text(encoding="utf-8")
    sims_text = (EVALS_DIR / "simulations" / "simulations.yaml").read_text(encoding="utf-8")
    assert "https://www.formula1.com/en/tickets" in goldens_text
    assert "https://www.formula1.com/en/tickets" in sims_text


# ==============================================================================
# F10: Official Mercedes Store, Team, Fan & Social Links (`get_official_links`) (5 test cases)
# ==============================================================================
class TestF10OfficialLinksTool:
  """Tests F10: get_official_links across merch, tickets, team, social, fan, and all."""

  def test_f10_get_official_links_merch_returns_official_store_url(self) -> None:
    get_official_links = load_tool_function("get_official_links")
    for alias in ("merch", "store", "shop"):
      res = get_official_links(category=alias)
      assert res["status"] == "success"
      assert "https://shop.mercedesamgf1.com/" in str(res)

  def test_f10_get_official_links_team_returns_official_mercedes_website(self) -> None:
    get_official_links = load_tool_function("get_official_links")
    for alias in ("team", "website", "mercedes"):
      res = get_official_links(category=alias)
      assert res["status"] == "success"
      assert "https://www.mercedesamgf1.com/" in str(res)

  def test_f10_get_official_links_social_returns_official_social_channels(self) -> None:
    get_official_links = load_tool_function("get_official_links")
    res = get_official_links(category="social")
    assert res["status"] == "success"
    text = str(res).lower()
    assert "instagram" in text and "youtube" in text

  def test_f10_get_official_links_fan_returns_fan_resources(self) -> None:
    get_official_links = load_tool_function("get_official_links")
    res = get_official_links(category="fan")
    assert res["status"] == "success"
    assert "mercedesamgf1.com" in str(res).lower()

  def test_f10_get_official_links_all_returns_comprehensive_directory(self) -> None:
    get_official_links = load_tool_function("get_official_links")
    res = get_official_links(category="all")
    assert res["status"] == "success"
    full_str = str(res)
    assert "https://www.formula1.com/en/tickets" in full_str
    assert "https://shop.mercedesamgf1.com/" in full_str
    assert "https://www.mercedesamgf1.com/" in full_str


# ==============================================================================
# F11: Mocked Merch Order Lookup (`lookup_mock_merch_order`) (5 test cases)
# ==============================================================================
class TestF11MockMerchOrderLookup:
  """Tests F11: lookup_mock_merch_order happy paths and mock disclaimers."""

  def test_f11_lookup_order_merc_1001_delivered_russell_cap(self) -> None:
    lookup_mock_merch_order = load_tool_function("lookup_mock_merch_order")
    res = lookup_mock_merch_order(order_number="MERC-1001")
    assert res["status"] == "success"
    assert res["is_mock"] is True
    assert "mock" in res.get("mock_disclaimer", "").lower()
    assert res["order"]["status"] == "Delivered"
    assert "Russell" in str(res["order"]["items"])

  def test_f11_lookup_order_merc_1002_in_transit_polo_and_antonelli_tee(self) -> None:
    lookup_mock_merch_order = load_tool_function("lookup_mock_merch_order")
    res = lookup_mock_merch_order(order_number="MERC-1002")
    assert res["status"] == "success"
    assert res["is_mock"] is True
    assert res["order"]["status"] == "In Transit"
    assert "Polo" in str(res["order"]["items"])

  def test_f11_lookup_order_merc_1003_return_approved_softshell_jacket(self) -> None:
    lookup_mock_merch_order = load_tool_function("lookup_mock_merch_order")
    res = lookup_mock_merch_order(order_number="MERC-1003")
    assert res["status"] == "success"
    assert res["is_mock"] is True
    assert "Return Approved" in res["order"]["status"]
    assert "Softshell" in str(res["order"]["items"])

  def test_f11_lookup_order_requires_only_order_number_parameter(self) -> None:
    lookup_mock_merch_order = load_tool_function("lookup_mock_merch_order")
    sig = inspect.signature(lookup_mock_merch_order)
    params = list(sig.parameters.keys())
    assert params == ["order_number"], f"Expected only ['order_number'], got {params}"

  def test_f11_merch_agent_instruction_requires_only_order_number_and_mock_disclosure(self) -> None:
    text = (AGENTS_DIR / "merch_support_agent" / "instruction.txt").read_text(encoding="utf-8").lower()
    assert "only an order number" in text or "only the order number" in text
    assert "mock" in text and "demonstration" in text


# ==============================================================================
# F12: Mocked Merch Returns, Exchanges & Damaged-Item Claims (`submit_mock_merch_request`) (5 test cases)
# ==============================================================================
class TestF12MockMerchSubmitRequest:
  """Tests F12: submit_mock_merch_request for return, exchange, and damaged_item."""

  def test_f12_submit_return_request_for_merc_1001(self) -> None:
    submit_mock_merch_request = load_tool_function("submit_mock_merch_request")
    res = submit_mock_merch_request(order_number="MERC-1001", request_type="return")
    assert res["status"] == "success"
    assert res["is_mock"] is True
    assert "MOCK-REQ" in res["reference_id"]
    assert res["request_type"] == "return"
    assert len(res.get("resolution_steps", "")) > 10

  def test_f12_submit_exchange_request_for_merc_1002(self) -> None:
    submit_mock_merch_request = load_tool_function("submit_mock_merch_request")
    res = submit_mock_merch_request(
        order_number="MERC-1002",
        request_type="exchange",
        item_name="W17 Team Polo Shirt",
        reason="Need size XL instead of L",
    )
    assert res["status"] == "success"
    assert res["is_mock"] is True
    assert "MOCK-REQ" in res["reference_id"]
    assert res["request_type"] == "exchange"

  def test_f12_submit_damaged_item_request_for_merc_1001(self) -> None:
    submit_mock_merch_request = load_tool_function("submit_mock_merch_request")
    res = submit_mock_merch_request(
        order_number="MERC-1001",
        request_type="damaged_item",
        item_name="Driver Cap",
        reason="Stitched logo frayed on arrival",
    )
    assert res["status"] == "success"
    assert res["is_mock"] is True
    assert "MOCK-REQ" in res["reference_id"]
    assert res["request_type"] == "damaged_item"

  def test_f12_submit_request_works_with_only_order_number_and_request_type(self) -> None:
    submit_mock_merch_request = load_tool_function("submit_mock_merch_request")
    res = submit_mock_merch_request("MERC-1003", "return")
    assert res["status"] == "success"
    assert res["order_number"] == "MERC-1003"
    assert res["is_mock"] is True

  def test_f12_submit_request_includes_explicit_no_real_refund_disclaimer(self) -> None:
    submit_mock_merch_request = load_tool_function("submit_mock_merch_request")
    res = submit_mock_merch_request("MERC-1001", "damaged_item")
    disclaimer = res.get("mock_disclaimer", "").lower()
    assert "mock" in disclaimer


# ==============================================================================
# F13: Mocked Merch Product & Size Availability (`check_merch_availability`) (5 test cases)
# ==============================================================================
class TestF13MockMerchAvailability:
  """Tests F13: check_merch_availability across caps, polos, hoodies, jackets, models."""

  def test_f13_check_availability_russell_and_antonelli_caps(self) -> None:
    check_merch_availability = load_tool_function("check_merch_availability")
    for query in ("George Russell cap", "Kimi Antonelli cap", "cap"):
      res = check_merch_availability(item_query=query)
      assert res["status"] == "success"
      assert res["is_mock"] is True
      assert res["in_stock"] is True
      assert "One Size" in res["available_sizes"]
      assert res["official_store_url"] == "https://shop.mercedesamgf1.com/"

  def test_f13_check_availability_team_polo_in_valid_sizes(self) -> None:
    check_merch_availability = load_tool_function("check_merch_availability")
    for sz in ("S", "M", "L", "XL"):
      res = check_merch_availability(item_query="polo", size=sz)
      assert res["status"] == "success"
      assert res["in_stock"] is True
      assert sz in res["available_sizes"]

  def test_f13_check_availability_hoodie_in_stock(self) -> None:
    check_merch_availability = load_tool_function("check_merch_availability")
    res = check_merch_availability(item_query="hoodie", size="L")
    assert res["status"] == "success"
    assert res["in_stock"] is True
    assert "L" in res["available_sizes"]

  def test_f13_check_availability_softshell_jacket_in_stock(self) -> None:
    check_merch_availability = load_tool_function("check_merch_availability")
    res = check_merch_availability(item_query="softshell jacket", size="M")
    assert res["status"] == "success"
    assert res["in_stock"] is True
    assert "M" in res["available_sizes"]

  def test_f13_check_availability_scale_model_car(self) -> None:
    check_merch_availability = load_tool_function("check_merch_availability")
    res = check_merch_availability(item_query="model car")
    assert res["status"] == "success"
    assert res["in_stock"] is True
    assert "1:18 Scale" in res["available_sizes"]


# ==============================================================================
# F14: Multilingual Conversations (5 test cases)
# ==============================================================================
class TestF14MultilingualSupport:
  """Tests F14: Multilingual conversation matching and guardrail preservation."""

  def test_f14_root_instruction_includes_multilingual_fluency_directive(self) -> None:
    text = (AGENTS_DIR / "totto_root_agent" / "instruction.txt").read_text(encoding="utf-8").lower()
    assert "multilingual" in text
    assert "language" in text

  def test_f14_root_instruction_specifies_clarification_on_unclear_multilingual_input(self) -> None:
    text = (AGENTS_DIR / "totto_root_agent" / "instruction.txt").read_text(encoding="utf-8").lower()
    assert "clarifying question" in text or "clarification" in text

  def test_f14_prd_and_tdd_specify_multilingual_requirements(self) -> None:
    prd_text = (PROJECT_ROOT / "prd.md").read_text(encoding="utf-8").lower()
    tdd_text = (PROJECT_ROOT / "tdd.md").read_text(encoding="utf-8").lower()
    assert "multilingual" in prd_text
    assert "multilingual" in tdd_text

  def test_f14_golden_eval_includes_multilingual_spanish_conversation(self) -> None:
    goldens = load_yaml_file(EVALS_DIR / "goldens" / "goldens.yaml")
    convs = goldens.get("conversations", [])
    assert any(
        "hola" in str(c).lower() or "multilingual" in str(c.get("tags", [])).lower() or "spanish" in str(c).lower()
        for c in convs
    ), "Golden evaluations must include a multilingual (e.g., Spanish) conversation"

  def test_f14_simulation_eval_includes_multilingual_scenario(self) -> None:
    sims = load_yaml_file(EVALS_DIR / "simulations" / "simulations.yaml")
    eval_list = sims.get("evals", [])
    assert any(
        "multilingual" in str(item.get("tags", [])).lower() or "spanish" in str(item).lower()
        for item in eval_list
    ), "Simulation evaluations must include a multilingual scenario"


# ==============================================================================
# F15: CXAS Lifecycle Artifacts, Linter & Evaluation Suite Compliance (5 test cases)
# ==============================================================================
class TestF15CXASLifecycleLinterAndEvals:
  """Tests F15: Project lifecycle files, app.json, 4 agents, 6 tools, and 4 eval suites."""

  def test_f15_lifecycle_artifacts_exist_and_non_empty(self) -> None:
    for rel_path in ("todo.md", "prd.md", "tdd.md", "gecx-config.json", "cxaslint.yaml"):
      path = PROJECT_ROOT / rel_path
      assert path.is_file(), f"Missing lifecycle artifact: {path}"
      assert path.stat().st_size > 50, f"Lifecycle artifact too small/empty: {path}"

  def test_f15_app_json_declares_root_agent_tools_and_5_variables(self) -> None:
    app_data = load_json_file(APP_DIR / "app.json")
    assert app_data["name"] == "totto_mercedes_f1_agent"
    assert app_data["rootAgent"] == "totto_root_agent"
    for tool_name in (*EXPECTED_TOOLS, "end_session"):
      assert tool_name in app_data["tools"], f"Missing tool {tool_name} in app.json"
    var_names = [v["name"] for v in app_data.get("variableDeclarations", [])]
    for expected_var in EXPECTED_VARIABLES:
      assert expected_var in var_names, f"Missing variable {expected_var} in app.json"

  def test_f15_all_4_agents_include_end_session_and_current_date_and_xml_tags(self) -> None:
    for agent_name in EXPECTED_AGENTS:
      cfg = load_json_file(AGENTS_DIR / agent_name / f"{agent_name}.json")
      instr = (AGENTS_DIR / agent_name / "instruction.txt").read_text(encoding="utf-8")
      assert "end_session" in cfg.get("tools", []), f"{agent_name}.json missing end_session"
      assert "{@TOOL: end_session}" in instr, f"{agent_name}/instruction.txt missing {{@TOOL: end_session}}"
      assert "${current_date}" in instr, f"{agent_name}/instruction.txt missing ${{current_date}}"
      for tag in ("<role>", "</role>", "<persona>", "</persona>", "<taskflow>", "</taskflow>", "<subtask", "<step", "<trigger>", "<action>"):
        assert tag in instr, f"{agent_name}/instruction.txt missing required XML tag {tag}"

  def test_f15_all_6_tools_have_valid_json_and_python_signatures(self) -> None:
    for tool_name in EXPECTED_TOOLS:
      tool_json = load_json_file(TOOLS_DIR / tool_name / f"{tool_name}.json")
      assert tool_json["displayName"] == tool_name
      assert tool_json["executionType"] == "SYNCHRONOUS"
      py_fn = tool_json.get("pythonFunction", {})
      assert py_fn.get("name") == tool_name
      assert py_fn.get("pythonCode") == f"tools/{tool_name}/python_function/python_code.py"
      assert len(py_fn.get("description", "")) > 15

      fn = load_tool_function(tool_name)
      assert fn.__doc__ is not None and "Args:" in fn.__doc__ and "Returns:" in fn.__doc__

  def test_f15_all_4_eval_suites_exist_and_parse_cleanly(self) -> None:
    goldens = load_yaml_file(EVALS_DIR / "goldens" / "goldens.yaml")
    sims = load_yaml_file(EVALS_DIR / "simulations" / "simulations.yaml")
    tool_tests = load_yaml_file(EVALS_DIR / "tool_tests" / "tool_tests.yaml")
    cb_test_file = (
        EVALS_DIR
        / "callback_tests"
        / "tests"
        / "totto_root_agent"
        / "before_agent_callbacks"
        / "before_agent"
        / "test.py"
    )
    assert "common_session_parameters" in goldens and len(goldens.get("conversations", [])) >= 10
    assert len(sims.get("evals", [])) >= 6
    assert len(tool_tests.get("tests", [])) >= 12
    assert cb_test_file.is_file()
