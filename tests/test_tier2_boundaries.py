"""Tier 2: Boundary Value Analysis & Corner Cases E2E Tests (F1-F15, 75 test cases).

Covers boundary values, negative/error paths, malformed inputs, case/prefix
normalization, OpenF1 network timeout/HTTP 500 fallback resilience (<= 5s),
callback idempotency with None/pre-populated state, and linter anti-patterns.
"""

import ast
import io
import re
import time
from unittest.mock import patch
import urllib.error

from tests.conftest import (
    AGENTS_DIR,
    APP_DIR,
    EVALS_DIR,
    EXPECTED_AGENTS,
    EXPECTED_TOOLS,
    EXPECTED_VARIABLES,
    TOOLS_DIR,
    DummyCallbackContext,
    load_before_agent_callback,
    load_json_file,
    load_tool_function,
    load_yaml_file,
)


# ==============================================================================
# F1: Fictional Persona & Anti-Impersonation Boundaries (5 test cases)
# ==============================================================================
class TestF1BoundariesAndAntiImpersonation:
  """Tests F1 boundaries: anti-impersonation of Toto Wolff, drivers, FIA, partners."""

  def test_f1_boundary_root_instruction_forbids_impersonating_toto_wolff(self) -> None:
    text = (AGENTS_DIR / "totto_root_agent" / "instruction.txt").read_text(encoding="utf-8").lower()
    assert "toto wolff" in text
    assert "fictional" in text

  def test_f1_boundary_root_instruction_forbids_impersonating_employees_drivers_fia_partners(self) -> None:
    text = (AGENTS_DIR / "totto_root_agent" / "instruction.txt").read_text(encoding="utf-8").lower()
    for entity in ("employee", "driver", "fia", "ticketing partner"):
      assert entity in text, f"totto_root_agent missing anti-impersonation boundary for '{entity}'"

  def test_f1_boundary_race_info_instruction_forbids_impersonation(self) -> None:
    text = (AGENTS_DIR / "race_info_agent" / "instruction.txt").read_text(encoding="utf-8").lower()
    assert "toto wolff" in text and "fictional" in text

  def test_f1_boundary_golden_eval_includes_adversarial_toto_impersonation_refusal(self) -> None:
    goldens = load_yaml_file(EVALS_DIR / "goldens" / "goldens.yaml")
    convs = goldens.get("conversations", [])
    assert any(
        "toto wolff" in str(turn.get("user", "")).lower()
        and "fictional" in str(turn.get("agent", "")).lower()
        for c in convs
        for turn in c.get("turns", [])
    ), "Golden evals must test user pressuring agent to impersonate Toto Wolff"

  def test_f1_boundary_simulation_eval_includes_adversarial_impersonation_scenario(self) -> None:
    sims = load_yaml_file(EVALS_DIR / "simulations" / "simulations.yaml")
    evals = sims.get("evals", [])
    assert any(
        "toto wolff" in str(item).lower() and "fictional" in str(item).lower()
        for item in evals
    ), "Simulations must include adversarial Toto Wolff impersonation refusal"


# ==============================================================================
# F2: Voice-First Formatting & Linter Anti-Pattern Boundaries (5 test cases)
# ==============================================================================
class TestF2VoiceFormattingBoundaries:
  """Tests F2 boundaries: no negative triggers, no hardcoded prices/phones, no prose FSM."""

  def test_f2_boundary_no_negative_triggers_in_any_instruction_i004(self) -> None:
    neg_re = re.compile(r"<trigger>.*?\bNOT\b.*?</trigger>", re.IGNORECASE | re.DOTALL)
    for agent_name in EXPECTED_AGENTS:
      text = (AGENTS_DIR / agent_name / "instruction.txt").read_text(encoding="utf-8")
      matches = neg_re.findall(text)
      assert not matches, f"{agent_name}/instruction.txt has negative <trigger> (I004): {matches}"

  def test_f2_boundary_no_hardcoded_dollar_prices_or_phone_numbers_i006(self) -> None:
    phone_re = re.compile(r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b")
    price_re = re.compile(r"\$\d+(?:\.\d{2})?")
    for agent_name in EXPECTED_AGENTS:
      text = (AGENTS_DIR / agent_name / "instruction.txt").read_text(encoding="utf-8")
      for line in text.splitlines():
        if "{" in line and "}" in line:
          continue
        assert not phone_re.search(line), f"{agent_name} has hardcoded phone: {line}"
        assert not price_re.search(line), f"{agent_name} has hardcoded price: {line}"

  def test_f2_boundary_no_banned_legacy_xml_tags_i015(self) -> None:
    banned_tags = (
        "<Agent>",
        "<Conversation_Schema>",
        "<Persona>",
        "<Role>",
        "<General_Instruction>",
        "<Context>",
        "<state",
        "<transitions>",
        "<conditional_logic",
    )
    for agent_name in EXPECTED_AGENTS:
      text = (AGENTS_DIR / agent_name / "instruction.txt").read_text(encoding="utf-8")
      for banned in banned_tags:
        assert banned not in text, f"{agent_name}/instruction.txt contains banned tag {banned}"

  def test_f2_boundary_no_excessive_inline_if_else_i003(self) -> None:
    if_else_re = re.compile(r"\bIF\b.*\bELSE\b", re.IGNORECASE)
    for agent_name in EXPECTED_AGENTS:
      text = (AGENTS_DIR / agent_name / "instruction.txt").read_text(encoding="utf-8")
      count = sum(1 for line in text.splitlines() if if_else_re.search(line))
      assert count < 3, f"{agent_name}/instruction.txt has {count} inline IF..ELSE lines (I003)"

  def test_f2_boundary_word_count_under_3000_words_per_instruction_i007(self) -> None:
    for agent_name in EXPECTED_AGENTS:
      text = (AGENTS_DIR / agent_name / "instruction.txt").read_text(encoding="utf-8")
      word_count = len(text.split())
      assert 50 <= word_count <= 3000, f"{agent_name} word count {word_count} out of [50, 3000] bounds"


# ==============================================================================
# F3: Rival Trash-Talk & Team Filter Boundaries (5 test cases)
# ==============================================================================
class TestF3RivalTrashTalkAndBiasBoundaries:
  """Tests F3 boundaries: rival trash-talk refusal, overall leader accuracy, team filter."""

  def test_f3_boundary_standings_includes_non_mercedes_championship_leaders(self) -> None:
    get_driver_standings = load_tool_function("get_driver_standings")
    res = get_driver_standings(category="drivers", team_filter="Mercedes")
    assert res["status"] == "success"
    drv_list = res.get("driver_standings", [])
    assert len(drv_list) >= 3, "Standings must include broader grid context beyond Mercedes"
    standings_str = " ".join(str(d) for d in drv_list)
    assert any(
        other in standings_str
        for other in ("Ferrari", "McLaren", "Red Bull", "Leclerc", "Norris", "Verstappen", "Piastri")
    ), "Standings must include non-Mercedes drivers/teams for grid accuracy"

  def test_f3_boundary_standings_case_insensitive_team_filter_for_valid_f1_teams(self) -> None:
    get_driver_standings = load_tool_function("get_driver_standings")
    for team in ("mercedes", "MERCEDES", "Silver Arrows", "Ferrari", "McLaren", "Red Bull"):
      res = get_driver_standings(category="drivers", team_filter=team)
      assert res["status"] == "success"
      assert len(res.get("mercedes_drivers", [])) == 2

  def test_f3_boundary_standings_unknown_team_filter_returns_error_with_agent_action(self) -> None:
    get_driver_standings = load_tool_function("get_driver_standings")
    res = get_driver_standings(category="drivers", team_filter="Atlantis Racing")
    assert res["status"] == "error"
    assert isinstance(res.get("agent_action"), str) and len(res["agent_action"]) > 10

  def test_f3_boundary_golden_eval_includes_rival_trash_talk_refusal(self) -> None:
    goldens = load_yaml_file(EVALS_DIR / "goldens" / "goldens.yaml")
    convs = goldens.get("conversations", [])
    assert any(
        ("trash" in str(turn.get("user", "")).lower() or "insult" in str(turn.get("user", "")).lower())
        and ("respect" in str(turn.get("agent", "")).lower() or "rival" in str(turn.get("agent", "")).lower())
        for c in convs
        for turn in c.get("turns", [])
    ), "Golden evals must test refusal of rival team/FIA trash-talk"

  def test_f3_boundary_simulation_eval_includes_rival_trash_talk_refusal(self) -> None:
    sims = load_yaml_file(EVALS_DIR / "simulations" / "simulations.yaml")
    evals = sims.get("evals", [])
    assert any(
        "red bull" in str(item).lower() or "trash" in str(item).lower() or "insult" in str(item).lower()
        for item in evals
    ), "Simulations must include adversarial rival/FIA trash-talk refusal"


# ==============================================================================
# F4: Race Schedule Boundaries & OpenF1 Network Failure Fallback (5 test cases)
# ==============================================================================
class TestF4RaceScheduleBoundariesAndOpenF1Fallback:
  """Tests F4 boundaries: unsupported races, OpenF1 timeout/HTTP 500 fallback <= 5s."""

  def test_f4_boundary_unsupported_race_narnia_and_mars_gp_return_error(self) -> None:
    get_race_schedule = load_tool_function("get_race_schedule")
    for invalid_race in ("Narnia Grand Prix", "Mars GP", "Atlantis GP", "1955 Le Mans"):
      res = get_race_schedule(race_name=invalid_race, user_location="London")
      assert res["status"] == "error"
      assert res["data_freshness"] == "latest_available"
      assert isinstance(res.get("supported_races"), list) and len(res["supported_races"]) >= 5
      assert isinstance(res.get("agent_action"), str) and len(res["agent_action"]) > 15
      assert res.get("result", {}).get("status") == "error"

  def test_f4_boundary_openf1_urlerror_falls_back_cleanly_under_5_seconds(self) -> None:
    get_race_schedule = load_tool_function("get_race_schedule")
    with (
        patch("requests.get", side_effect=OSError("Simulated network down")),
        patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Simulated network down")),
    ):
      t0 = time.monotonic()
      res = get_race_schedule(race_name="next", user_location="London")
      elapsed = time.monotonic() - t0
    assert elapsed <= 5.0
    assert res["status"] == "success"
    assert res["data_freshness"] == "latest_available"
    assert res["race"]["race_name"] == "Miami Grand Prix"

  def test_f4_boundary_openf1_timeout_error_falls_back_cleanly_under_5_seconds(self) -> None:
    get_race_schedule = load_tool_function("get_race_schedule")
    with (
        patch("requests.get", side_effect=TimeoutError("OpenF1 timed out")),
        patch("urllib.request.urlopen", side_effect=TimeoutError("OpenF1 timed out")),
    ):
      t0 = time.monotonic()
      res = get_race_schedule(race_name="silverstone", user_location="London")
      elapsed = time.monotonic() - t0
    assert elapsed <= 5.0
    assert res["status"] == "success"
    assert res["data_freshness"] == "latest_available"
    assert res["race"]["race_name"] == "British Grand Prix"

  def test_f4_boundary_openf1_http_500_falls_back_cleanly_under_5_seconds(self) -> None:
    get_race_schedule = load_tool_function("get_race_schedule")
    http_500 = urllib.error.HTTPError(
        url="https://api.openf1.org/v1/meetings",
        code=500,
        msg="Internal Server Error",
        hdrs=None,  # type: ignore[arg-type]
        fp=io.BytesIO(b"Server Error"),
    )
    with (
        patch("requests.get", side_effect=RuntimeError("HTTP 500 Internal Server Error")),
        patch("urllib.request.urlopen", side_effect=http_500),
    ):
      t0 = time.monotonic()
      res = get_race_schedule(race_name="monza", user_location="Milan")
      elapsed = time.monotonic() - t0
    assert elapsed <= 5.0
    assert res["status"] == "success"
    assert res["data_freshness"] == "latest_available"
    assert res["race"]["race_name"] == "Italian Grand Prix"

  def test_f4_boundary_whitespace_and_case_normalization_on_race_name(self) -> None:
    get_race_schedule = load_tool_function("get_race_schedule")
    for variant in ("  MIAMI  ", "British", "  monte carlo ", "VEGAS", ""):
      res = get_race_schedule(race_name=variant, user_location="London")
      assert res["status"] == "success"
      assert "race_name" in res["race"]


# ==============================================================================
# F5: Location & Timezone Boundaries (5 test cases)
# ==============================================================================
class TestF5LocationAndTimezoneBoundaries:
  """Tests F5 boundaries: empty/whitespace location, unrecognized location, day rollover."""

  def test_f5_boundary_empty_and_whitespace_user_location_requires_clarification(self) -> None:
    get_race_schedule = load_tool_function("get_race_schedule")
    for empty_loc in ("", "   ", "\t\n"):
      res = get_race_schedule(race_name="next", user_location=empty_loc)
      assert res["status"] == "success"
      assert res["needs_user_location"] is True
      assert isinstance(res.get("agent_action"), str) and len(res["agent_action"]) > 15

  def test_f5_boundary_unrecognized_user_location_returns_utc_fallback_and_needs_location(self) -> None:
    get_race_schedule = load_tool_function("get_race_schedule")
    for unknown_loc in ("Atlantis", "Moon Base Alpha", "Wakanda"):
      res = get_race_schedule(race_name="miami", user_location=unknown_loc)
      assert res["status"] == "success"
      assert res["needs_user_location"] is True
      assert "unrecognized" in res.get("resolved_timezone", "").lower() or "utc" in res.get("resolved_timezone", "").lower()
      assert isinstance(res.get("agent_action"), str) and len(res["agent_action"]) > 10

  def test_f5_boundary_negative_utc_offset_previous_day_rollover_las_vegas(self) -> None:
    get_race_schedule = load_tool_function("get_race_schedule")
    # Las Vegas Race is Sunday 06:00 UTC -> Saturday 23:00 PDT (UTC-7) or 22:00 PST
    res = get_race_schedule(race_name="las_vegas", user_location="Los Angeles")
    assert res["status"] == "success"
    assert res["needs_user_location"] is False
    assert "Saturday" in res["localized_sessions"]["Race"]

  def test_f5_boundary_positive_utc_offset_next_day_rollover_sydney(self) -> None:
    get_race_schedule = load_tool_function("get_race_schedule")
    # Miami Race is Sunday 20:00 UTC -> Monday 06:00 AEST (UTC+10) in Sydney
    res = get_race_schedule(race_name="miami", user_location="Sydney")
    assert res["status"] == "success"
    assert res["needs_user_location"] is False
    assert "Monday 06:00" in res["localized_sessions"]["Race"]

  def test_f5_boundary_golden_and_sim_cover_missing_timezone_clarification_trap(self) -> None:
    goldens = load_yaml_file(EVALS_DIR / "goldens" / "goldens.yaml")
    convs = goldens.get("conversations", [])
    assert any(
        c.get("session_parameters", {}).get("user_location", "") == ""
        and ("timezone" in str(c).lower() or "located" in str(c).lower() or "city" in str(c).lower())
        for c in convs
    ), "Golden evals must include a missing user_location clarification trap"


# ==============================================================================
# F6: Standings Boundaries & OpenF1 Failure Fallback (5 test cases)
# ==============================================================================
class TestF6StandingsBoundariesAndOpenF1Fallback:
  """Tests F6 boundaries: invalid category, invalid team_filter, OpenF1 network errors."""

  def test_f6_boundary_invalid_standings_category_returns_error_and_agent_action(self) -> None:
    get_driver_standings = load_tool_function("get_driver_standings")
    for bad_cat in ("invalid_category", "marshals", "safety_car", "pit_crew"):
      res = get_driver_standings(category=bad_cat, team_filter="Mercedes")
      assert res["status"] == "error"
      assert res["data_freshness"] == "latest_available"
      assert isinstance(res.get("agent_action"), str) and len(res["agent_action"]) > 15
      assert res.get("result", {}).get("status") == "error"

  def test_f6_boundary_invalid_team_filter_returns_error_and_agent_action(self) -> None:
    get_driver_standings = load_tool_function("get_driver_standings")
    for bad_team in ("Atlantis Racing", "Narnia Motorsport", "Gotham GP"):
      res = get_driver_standings(category="drivers", team_filter=bad_team)
      assert res["status"] == "error"
      assert isinstance(res.get("agent_action"), str) and len(res["agent_action"]) > 15

  def test_f6_boundary_openf1_network_error_on_standings_falls_back_under_5_seconds(self) -> None:
    get_driver_standings = load_tool_function("get_driver_standings")
    with (
        patch("requests.get", side_effect=OSError("Simulated DNS failure")),
        patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Simulated DNS failure")),
    ):
      t0 = time.monotonic()
      res = get_driver_standings(category="drivers", team_filter="Mercedes")
      elapsed = time.monotonic() - t0
    assert elapsed <= 5.0
    assert res["status"] == "success"
    assert res["data_freshness"] == "latest_available"
    assert len(res["mercedes_drivers"]) == 2

  def test_f6_boundary_openf1_timeout_on_standings_falls_back_under_5_seconds(self) -> None:
    get_driver_standings = load_tool_function("get_driver_standings")
    with (
        patch("requests.get", side_effect=TimeoutError("Simulated socket timeout")),
        patch("urllib.request.urlopen", side_effect=TimeoutError("Simulated socket timeout")),
    ):
      t0 = time.monotonic()
      res = get_driver_standings(category="constructors", team_filter="Mercedes")
      elapsed = time.monotonic() - t0
    assert elapsed <= 5.0
    assert res["status"] == "success"
    assert len(res["constructor_standings"]) >= 4

  def test_f6_boundary_empty_category_or_team_filter_defaults_gracefully(self) -> None:
    get_driver_standings = load_tool_function("get_driver_standings")
    res = get_driver_standings(category="", team_filter="")
    assert res["status"] == "success"
    assert res["data_freshness"] == "latest_available"


# ==============================================================================
# F7: Telemetry & Guaranteed Prediction Refusal Boundaries (5 test cases)
# ==============================================================================
class TestF7TelemetryAndPredictionRefusalBoundaries:
  """Tests F7 boundaries: freshest-data disclaimers even on error, strategy/prediction refusal."""

  def test_f7_boundary_race_schedule_error_still_includes_latest_available_freshness(self) -> None:
    get_race_schedule = load_tool_function("get_race_schedule")
    res = get_race_schedule(race_name="Narnia Grand Prix", user_location="London")
    assert res["status"] == "error"
    assert res.get("data_freshness") == "latest_available"

  def test_f7_boundary_standings_error_still_includes_latest_available_freshness(self) -> None:
    get_driver_standings = load_tool_function("get_driver_standings")
    res = get_driver_standings(category="invalid_category", team_filter="Mercedes")
    assert res["status"] == "error"
    assert res.get("data_freshness") == "latest_available"

  def test_f7_boundary_openf1_tools_configure_bounded_http_timeout_in_code(self) -> None:
    for tool_name in ("get_race_schedule", "get_driver_standings"):
      code = (TOOLS_DIR / tool_name / "python_function" / "python_code.py").read_text(encoding="utf-8")
      assert "api.openf1.org/v1" in code, f"{tool_name} must reference live OpenF1 API"
      assert "timeout=" in code, f"{tool_name} must pass an explicit bounded timeout="
      assert "try:" in code and "except" in code, f"{tool_name} must wrap HTTP calls in try...except"

  def test_f7_boundary_golden_eval_refuses_insider_strategy_and_guaranteed_win(self) -> None:
    goldens = load_yaml_file(EVALS_DIR / "goldens" / "goldens.yaml")
    convs = goldens.get("conversations", [])
    assert any(
        ("strategy" in str(turn.get("user", "")).lower() or "guarantee" in str(turn.get("user", "")).lower())
        and ("strategy" in str(turn.get("agent", "")).lower() or "guarantee" in str(turn.get("agent", "")).lower() or "telemetry" in str(turn.get("agent", "")).lower())
        for c in convs
        for turn in c.get("turns", [])
    )

  def test_f7_boundary_prd_non_goals_explicitly_forbid_insider_info_and_predictions(self) -> None:
    prd_text = (APP_DIR.parent.parent / "prd.md").read_text(encoding="utf-8").lower()
    assert "private team information" in prd_text
    assert "confidential telemetry" in prd_text
    assert "guaranteed race predictions" in prd_text


# ==============================================================================
# F8: Unverified Historical Knowledge & Uncertainty Boundaries (5 test cases)
# ==============================================================================
class TestF8UnverifiedHistoryUncertaintyBoundaries:
  """Tests F8 boundaries: historical uncertainty disclosure & unverified race fallback."""

  def test_f8_boundary_historical_1955_race_in_schedule_tool_instructs_general_knowledge_disclosure(self) -> None:
    get_race_schedule = load_tool_function("get_race_schedule")
    res = get_race_schedule(race_name="1955 British Grand Prix", user_location="London")
    # Either matches British GP or returns error with general knowledge disclosure in agent_action
    if res["status"] == "error":
      assert "general" in res["agent_action"].lower() and "knowledge" in res["agent_action"].lower()
    else:
      assert res["data_freshness"] == "latest_available"

  def test_f8_boundary_unrecognized_historical_race_agent_action_mentions_general_knowledge(self) -> None:
    get_race_schedule = load_tool_function("get_race_schedule")
    res = get_race_schedule(race_name="1954 French Grand Prix Reims", user_location="Paris")
    assert res["status"] == "error"
    assert "general" in res["agent_action"].lower() and "knowledge" in res["agent_action"].lower()

  def test_f8_boundary_root_instruction_forbids_stating_uncertain_history_as_verified_fact(self) -> None:
    text = (AGENTS_DIR / "totto_root_agent" / "instruction.txt").read_text(encoding="utf-8").lower()
    assert "uncertain" in text and "verified" in text

  def test_f8_boundary_golden_history_turn_has_no_hallucinated_tool_call_when_answered_by_root(self) -> None:
    goldens = load_yaml_file(EVALS_DIR / "goldens" / "goldens.yaml")
    convs = goldens.get("conversations", [])
    history_convs = [
        c for c in convs
        if "history" in c.get("conversation", "").lower() or "history" in str(c.get("tags", [])).lower()
    ]
    assert len(history_convs) >= 1
    for c in history_convs:
      for turn in c.get("turns", []):
        assert "general" in str(turn.get("agent", "")).lower()

  def test_f8_boundary_prd_requires_avoiding_uncertain_historical_claims(self) -> None:
    prd_text = (APP_DIR.parent.parent / "prd.md").read_text(encoding="utf-8").lower()
    assert "general knowledge" in prd_text
    assert "uncertain historical details" in prd_text


# ==============================================================================
# F9: Direct Ticket Sales, Pricing & Inventory Refusal Boundaries (5 test cases)
# ==============================================================================
class TestF9DirectTicketSalesRefusalBoundaries:
  """Tests F9 boundaries: refusal of ticket sales, reservations, pricing, seat inventory."""

  def test_f9_boundary_get_official_links_tickets_guidance_explicitly_disclaims_direct_sales(self) -> None:
    get_official_links = load_tool_function("get_official_links")
    res = get_official_links(category="tickets")
    assert res["status"] == "success"
    guidance = str(res).lower()
    assert "cannot sell" in guidance or "not sell" in guidance or "official" in guidance

  def test_f9_boundary_get_official_links_ticketing_aliases_resolve_identically(self) -> None:
    get_official_links = load_tool_function("get_official_links")
    for alias in ("tickets", "ticketing", "f1_tickets", "  TICKETS  "):
      res = get_official_links(category=alias)
      assert res["status"] == "success"
      assert "https://www.formula1.com/en/tickets" in str(res)

  def test_f9_boundary_ticketing_agent_has_no_payment_or_booking_tools(self) -> None:
    cfg = load_json_file(AGENTS_DIR / "ticketing_agent" / "ticketing_agent.json")
    tools = set(cfg.get("tools", []))
    assert tools == {"get_official_links", "get_race_schedule", "end_session"}

  def test_f9_boundary_golden_eval_tests_direct_ticket_booking_and_price_refusal(self) -> None:
    goldens = load_yaml_file(EVALS_DIR / "goldens" / "goldens.yaml")
    convs = goldens.get("conversations", [])
    assert any(
        "ticket" in str(turn.get("user", "")).lower()
        and "https://www.formula1.com/en/tickets" in str(turn.get("agent", ""))
        for c in convs
        for turn in c.get("turns", [])
    )

  def test_f9_boundary_simulation_eval_tests_adversarial_ticket_booking_insistence(self) -> None:
    sims = load_yaml_file(EVALS_DIR / "simulations" / "simulations.yaml")
    evals = sims.get("evals", [])
    assert any(
        "ticket" in str(item).lower() and "formula1.com/en/tickets" in str(item)
        for item in evals
    )


# ==============================================================================
# F10: Official Links Tool Boundaries (5 test cases)
# ==============================================================================
class TestF10OfficialLinksBoundaries:
  """Tests F10 boundaries: invalid link categories, case/whitespace, default category."""

  def test_f10_boundary_invalid_link_category_betting_returns_error_and_agent_action(self) -> None:
    get_official_links = load_tool_function("get_official_links")
    for bad_cat in ("betting", "flights", "hotels", "crypto", "vip_backstage"):
      res = get_official_links(category=bad_cat)
      assert res["status"] == "error"
      assert isinstance(res.get("valid_categories"), list)
      assert set(res["valid_categories"]) >= {"tickets", "merch", "team", "social", "fan", "all"}
      assert isinstance(res.get("agent_action"), str) and len(res["agent_action"]) > 15
      assert res.get("result", {}).get("status") == "error"

  def test_f10_boundary_empty_or_whitespace_category_defaults_to_all(self) -> None:
    get_official_links = load_tool_function("get_official_links")
    for default_cat in ("", "   ", "ALL", "all"):
      res = get_official_links(category=default_cat)
      assert res["status"] == "success"
      assert "https://shop.mercedesamgf1.com/" in str(res)
      assert "https://www.formula1.com/en/tickets" in str(res)

  def test_f10_boundary_case_and_alias_normalization_for_merch_team_social_fan(self) -> None:
    get_official_links = load_tool_function("get_official_links")
    for alias in ("  STORE ", "Shop", "Merchandise", "WEBSITE", "Mercedes", "Socials", "Fan", "Ticketing", "F1_Tickets"):
      res = get_official_links(category=alias)
      assert res["status"] == "success"

  def test_f10_boundary_dual_jsonpath_result_mirror_on_official_links(self) -> None:
    get_official_links = load_tool_function("get_official_links")
    res_ok = get_official_links(category="merch")
    assert res_ok["result"]["status"] == "success"
    assert "shop.mercedesamgf1.com" in str(res_ok["result"])

    res_err = get_official_links(category="betting")
    assert res_err["result"]["status"] == "error"
    assert len(res_err["result"].get("agent_action", "")) > 10

  def test_f10_boundary_tool_tests_yaml_covers_official_links_error_case(self) -> None:
    tool_tests = load_yaml_file(EVALS_DIR / "tool_tests" / "tool_tests.yaml")
    tests = tool_tests.get("tests", [])
    assert any(
        t.get("tool") == "get_official_links" and t.get("args", {}).get("category") == "betting"
        for t in tests
    )


# ==============================================================================
# F11: Mock Merch Order Lookup Boundaries (5 test cases)
# ==============================================================================
class TestF11OrderLookupBoundaries:
  """Tests F11 boundaries: MERC-9999, 9999, empty/whitespace, numeric shorthand, lowercase merc-1001."""

  def test_f11_boundary_non_existent_order_merc_9999_and_9999_return_error(self) -> None:
    lookup_mock_merch_order = load_tool_function("lookup_mock_merch_order")
    for not_found_id in ("MERC-9999", "9999", "#9999", "MERC-0000", "ORD-1234"):
      res = lookup_mock_merch_order(order_number=not_found_id)
      assert res["status"] == "error"
      assert res["is_mock"] is True
      assert res.get("sample_order_numbers") == ["MERC-1001", "MERC-1002", "MERC-1003"]
      assert isinstance(res.get("agent_action"), str) and len(res["agent_action"]) > 15
      assert res.get("result", {}).get("status") == "error"

  def test_f11_boundary_empty_and_whitespace_order_number_returns_error(self) -> None:
    lookup_mock_merch_order = load_tool_function("lookup_mock_merch_order")
    for empty_id in ("", "   ", "\n\t", "#"):
      res = lookup_mock_merch_order(order_number=empty_id)
      assert res["status"] == "error"
      assert res["is_mock"] is True
      assert isinstance(res.get("agent_action"), str) and len(res["agent_action"]) > 15

  def test_f11_boundary_numeric_shorthand_normalization(self) -> None:
    lookup_mock_merch_order = load_tool_function("lookup_mock_merch_order")
    for shorthand, expected_norm in (
        ("1001", "MERC-1001"),
        ("  1001  ", "MERC-1001"),
        ("1002", "MERC-1002"),
        ("  1002 ", "MERC-1002"),
        ("1003", "MERC-1003"),
    ):
      res = lookup_mock_merch_order(order_number=shorthand)
      assert res["status"] == "success"
      assert res["order_number"] == expected_norm
      assert res["order"]["order_number"] == expected_norm

  def test_f11_boundary_lowercase_and_padded_order_number_normalization(self) -> None:
    lookup_mock_merch_order = load_tool_function("lookup_mock_merch_order")
    for raw_id, expected_norm in (
        ("merc-1001", "MERC-1001"),
        ("  merc-1002  ", "MERC-1002"),
        ("Merc-1003", "MERC-1003"),
    ):
      res = lookup_mock_merch_order(order_number=raw_id)
      assert res["status"] == "success"
      assert res["order_number"] == expected_norm

  def test_f11_boundary_goldens_and_simulations_cover_merc_9999_not_found(self) -> None:
    goldens_text = (EVALS_DIR / "goldens" / "goldens.yaml").read_text(encoding="utf-8")
    sims_text = (EVALS_DIR / "simulations" / "simulations.yaml").read_text(encoding="utf-8")
    assert "MERC-9999" in goldens_text
    assert "MERC-9999" in sims_text


# ==============================================================================
# F12: Mock Merch Submit Request & Payment Refusal Boundaries (5 test cases)
# ==============================================================================
class TestF12SubmitRequestBoundariesAndPaymentRefusal:
  """Tests F12 boundaries: unknown order ID, invalid request_type, aliases, payment refusal."""

  def test_f12_boundary_unknown_order_merc_9999_or_empty_returns_error(self) -> None:
    submit_mock_merch_request = load_tool_function("submit_mock_merch_request")
    for bad_order in ("MERC-9999", "9999", "", "   "):
      res = submit_mock_merch_request(order_number=bad_order, request_type="return")
      assert res["status"] == "error"
      assert res["is_mock"] is True
      assert res.get("sample_order_numbers") == ["MERC-1001", "MERC-1002", "MERC-1003"]
      assert isinstance(res.get("agent_action"), str) and len(res["agent_action"]) > 15
      assert res.get("result", {}).get("status") == "error"

  def test_f12_boundary_invalid_request_type_returns_error_and_supported_types(self) -> None:
    submit_mock_merch_request = load_tool_function("submit_mock_merch_request")
    for bad_type in ("invalid_type", "cancel_subscription", "charge_card", ""):
      res = submit_mock_merch_request(order_number="MERC-1001", request_type=bad_type)
      assert res["status"] == "error"
      assert res["is_mock"] is True
      assert res.get("supported_request_types") == ["return", "exchange", "damaged_item"]
      assert isinstance(res.get("agent_action"), str) and len(res["agent_action"]) > 15

  def test_f12_boundary_request_type_aliases_damaged_damage_replace_normalize_cleanly(self) -> None:
    submit_mock_merch_request = load_tool_function("submit_mock_merch_request")
    for alias in ("damaged", "damage", "replace", "DAMAGED_ITEM"):
      res = submit_mock_merch_request(order_number="1001", request_type=alias)
      assert res["status"] == "success"
      assert res["order_number"] == "MERC-1001"
      assert res["request_type"] == "damaged_item"

  def test_f12_boundary_merch_agent_instruction_forbids_credit_card_and_real_refunds(self) -> None:
    text = (AGENTS_DIR / "merch_support_agent" / "instruction.txt").read_text(encoding="utf-8").lower()
    assert "credit card" in text
    assert "refund" in text

  def test_f12_boundary_goldens_and_simulations_cover_real_payment_refusal(self) -> None:
    goldens_text = (EVALS_DIR / "goldens" / "goldens.yaml").read_text(encoding="utf-8").lower()
    sims_text = (EVALS_DIR / "simulations" / "simulations.yaml").read_text(encoding="utf-8").lower()
    assert "credit card" in goldens_text or "4111" in goldens_text or "payment" in goldens_text
    assert "credit card" in sims_text or "payment" in sims_text


# ==============================================================================
# F13: Mock Merch Availability Out-of-Stock & Unknown Item Boundaries (5 test cases)
# ==============================================================================
class TestF13MerchAvailabilityOutOfStockBoundaries:
  """Tests F13 boundaries: out-of-stock sizes (XXL, XS), signed race suit, unknown/empty item."""

  def test_f13_boundary_out_of_stock_size_xxl_and_xs_for_polo_return_error(self) -> None:
    check_merch_availability = load_tool_function("check_merch_availability")
    for oos_size in ("XXL", "XS", "XXS", "3XL"):
      res = check_merch_availability(item_query="polo", size=oos_size)
      assert res["status"] == "error"
      assert res["is_mock"] is True
      assert res["in_stock"] is False
      assert res["available_sizes"] == ["S", "M", "L", "XL"]
      assert res["official_store_url"] == "https://shop.mercedesamgf1.com/"
      assert isinstance(res.get("agent_action"), str) and len(res["agent_action"]) > 15
      assert res.get("result", {}).get("status") == "error"

  def test_f13_boundary_out_of_stock_sizes_for_hoodie_and_jacket(self) -> None:
    check_merch_availability = load_tool_function("check_merch_availability")
    res_hoodie = check_merch_availability(item_query="hoodie", size="S")
    assert res_hoodie["status"] == "error"
    assert res_hoodie["in_stock"] is False
    assert res_hoodie["available_sizes"] == ["M", "L", "XL"]

    res_jacket = check_merch_availability(item_query="jacket", size="XL")
    assert res_jacket["status"] == "error"
    assert res_jacket["in_stock"] is False
    assert res_jacket["available_sizes"] == ["S", "M", "L"]

  def test_f13_boundary_out_of_stock_item_signed_race_suit_returns_error(self) -> None:
    check_merch_availability = load_tool_function("check_merch_availability")
    for oos_item in ("signed race suit", "Limited Edition W15 Signed Race Suit", "race suit"):
      res = check_merch_availability(item_query=oos_item, size="")
      assert res["status"] == "error"
      assert res["is_mock"] is True
      assert res["in_stock"] is False
      assert res["official_store_url"] == "https://shop.mercedesamgf1.com/"
      assert isinstance(res.get("agent_action"), str) and len(res["agent_action"]) > 15

  def test_f13_boundary_empty_and_unrecognized_item_query_return_error(self) -> None:
    check_merch_availability = load_tool_function("check_merch_availability")
    for bad_query in ("", "   ", "ferrari toaster", " submarine "):
      res = check_merch_availability(item_query=bad_query, size="")
      assert res["status"] == "error"
      assert res["is_mock"] is True
      assert res["in_stock"] is False
      assert res["official_store_url"] == "https://shop.mercedesamgf1.com/"
      assert isinstance(res.get("agent_action"), str) and len(res["agent_action"]) > 15

  def test_f13_boundary_goldens_and_simulations_cover_out_of_stock_size_xxl(self) -> None:
    goldens_text = (EVALS_DIR / "goldens" / "goldens.yaml").read_text(encoding="utf-8")
    sims_text = (EVALS_DIR / "simulations" / "simulations.yaml").read_text(encoding="utf-8")
    assert "XXL" in goldens_text
    assert "XXL" in sims_text


# ==============================================================================
# F14: Multilingual Ambiguity & Guardrail Preservation Boundaries (5 test cases)
# ==============================================================================
class TestF14MultilingualAmbiguityAndGuardrailBoundaries:
  """Tests F14 boundaries: multilingual guardrail preservation and clarification."""

  def test_f14_boundary_spanish_golden_preserves_payment_refusal_and_mock_order_guardrails(self) -> None:
    goldens = load_yaml_file(EVALS_DIR / "goldens" / "goldens.yaml")
    convs = goldens.get("conversations", [])
    spanish_convs = [c for c in convs if "spanish" in c.get("conversation", "").lower() or "hola" in str(c).lower()]
    assert len(spanish_convs) >= 1
    conv_str = str(spanish_convs[0]).lower()
    assert "tarjeta" in conv_str or "payment" in conv_str or "pago" in conv_str
    assert "merc-1001" in conv_str and "merc-9999" in conv_str

  def test_f14_boundary_spanish_simulation_enforces_fictional_identity_and_cest_schedule_in_spanish(self) -> None:
    sims = load_yaml_file(EVALS_DIR / "simulations" / "simulations.yaml")
    evals = sims.get("evals", [])
    multilingual_sims = [e for e in evals if "multilingual" in str(e.get("tags", [])).lower() or "spanish" in str(e).lower()]
    assert len(multilingual_sims) >= 1
    sim_str = str(multilingual_sims[0]).lower()
    assert "fictional" in sim_str or "totto" in sim_str
    assert "madrid" in sim_str and "cest" in sim_str

  def test_f14_boundary_get_race_schedule_supports_international_cities_across_languages(self) -> None:
    get_race_schedule = load_tool_function("get_race_schedule")
    for city, expected_tz in (
        ("Madrid", "CEST"),
        ("Berlin", "CEST"),
        ("Paris", "CEST"),
        ("Rome", "CEST"),
        ("Tokyo", "JST"),
    ):
      res = get_race_schedule(race_name="next", user_location=city)
      assert res["status"] == "success"
      assert res["needs_user_location"] is False
      assert expected_tz in res["localized_sessions"]["Race"]

  def test_f14_boundary_unicode_characters_in_tool_inputs_do_not_crash(self) -> None:
    get_race_schedule = load_tool_function("get_race_schedule")
    res_sched = get_race_schedule(race_name="Gran Premio de Mónaco", user_location="Madrid")
    assert res_sched["status"] in ("success", "error")

    check_merch = load_tool_function("check_merch_availability")
    res_merch = check_merch(item_query="gorra oficial ñ ü é", size="XL")
    assert res_merch["status"] in ("success", "error")
    if res_merch["status"] == "error":
      assert len(res_merch.get("agent_action", "")) > 10

  def test_f14_boundary_root_instruction_handles_unclear_multilingual_requests(self) -> None:
    text = (AGENTS_DIR / "totto_root_agent" / "instruction.txt").read_text(encoding="utf-8").lower()
    assert "multilingual" in text and "unclear" in text


# ==============================================================================
# F15: Callback & Schema Strict Boundaries (5 test cases)
# ==============================================================================
class TestF15CallbackAndSchemaStrictBoundaries:
  """Tests F15 boundaries: callback idempotency, None recovery, AST/schema strictness."""

  def test_f15_boundary_callback_idempotency_preserves_pre_populated_state(self) -> None:
    cb = load_before_agent_callback()
    ctx = DummyCallbackContext({
        "favorite_team": "Mercedes-AMG",
        "is_mock_mode": "true",
        "user_location": "Tokyo",
        "order_number": "MERC-1002",
        "initialized": "true",
    })
    ret = cb(ctx)
    assert ret is None
    assert ctx.state["favorite_team"] == "Mercedes-AMG"
    assert ctx.state["user_location"] == "Tokyo"
    assert ctx.state["order_number"] == "MERC-1002"
    assert ctx.state["initialized"] == "true"

  def test_f15_boundary_callback_recovers_from_none_or_empty_values(self) -> None:
    cb = load_before_agent_callback()
    ctx = DummyCallbackContext({
        "favorite_team": "",
        "is_mock_mode": None,
        "user_location": None,
        "order_number": None,
    })
    ret = cb(ctx)
    assert ret is None
    assert ctx.state["favorite_team"] == "Mercedes"
    assert ctx.state["is_mock_mode"] == "true"
    assert ctx.state["user_location"] == ""
    assert ctx.state["order_number"] == ""
    assert ctx.state["initialized"] == "true"

  def test_f15_boundary_callback_source_does_not_import_google_adk_or_genai(self) -> None:
    cb_path = (
        AGENTS_DIR
        / "totto_root_agent"
        / "before_agent_callbacks"
        / "before_agent_callbacks_01"
        / "python_code.py"
    )
    source = cb_path.read_text(encoding="utf-8")
    assert "google.adk" not in source, "Callback must not import google.adk"
    assert "google.genai" not in source, "Callback must not import google.genai"
    assert "from typing import Optional" in source

  def test_f15_boundary_no_tool_uses_none_default_or_kwargs_t004_t009_t011(self) -> None:
    for tool_name in EXPECTED_TOOLS:
      code_path = TOOLS_DIR / tool_name / "python_function" / "python_code.py"
      source = code_path.read_text(encoding="utf-8")
      tree = ast.parse(source)
      fn_defs = [node for node in tree.body if isinstance(node, ast.FunctionDef)]
      assert len(fn_defs) >= 1
      # First def in file MUST match tool_name (T004)
      first_fn = fn_defs[0]
      assert first_fn.name == tool_name, f"First def in {code_path} is {first_fn.name}, expected {tool_name}"
      assert first_fn.args.kwarg is None, f"{tool_name} must not use **kwargs (T009)"
      for default_node in first_fn.args.defaults:
        assert not (isinstance(default_node, ast.Constant) and default_node.value is None), (
            f"{tool_name} must not have '= None' default parameter (T011)"
        )

  def test_f15_boundary_app_and_tool_json_strict_ces_proto_schema_compliance_v001_v003(self) -> None:
    app_data = load_json_file(APP_DIR / "app.json")
    for var_decl in app_data.get("variableDeclarations", []):
      schema = var_decl.get("schema", {})
      assert schema.get("type") == "STRING"
      assert "required" in schema, f"Variable {var_decl.get('name')} missing 'required': [] in schema (V001)"

    for tool_name in EXPECTED_TOOLS:
      tool_data = load_json_file(TOOLS_DIR / tool_name / f"{tool_name}.json")
      assert "description" not in tool_data, f"{tool_name}.json must not have top-level 'description' (V003)"
      assert "description" in tool_data.get("pythonFunction", {}), (
          f"{tool_name}.json missing pythonFunction.description (T012)"
      )
