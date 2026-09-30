"""Tier 3: Pairwise Combinatorial & Cross-Feature E2E Tests (18 test cases).

Verifies multi-component interactions across callbacks, custom tools, agent
configurations, XML instructions, session variables, and evaluation suites.
"""

import re
from typing import Any
from jsonpath_ng import parse as jsonpath_parse

from tests.conftest import (
    AGENTS_DIR,
    APP_DIR,
    EVALS_DIR,
    EXPECTED_AGENTS,
    EXPECTED_TOOLS,
    EXPECTED_VARIABLES,
    DummyCallbackContext,
    load_before_agent_callback,
    load_json_file,
    load_tool_function,
    load_yaml_file,
)


def _eval_jsonpath(data: dict[str, Any], expr: str) -> Any:
  matches = jsonpath_parse(expr).find(data)
  return matches[0].value if matches else None


def test_comb_01_callback_state_to_schedule_missing_location_then_localized() -> None:
  """Pairwise: before_agent_callback init -> get_race_schedule empty location -> localized."""
  cb = load_before_agent_callback()
  get_race_schedule = load_tool_function("get_race_schedule")

  ctx = DummyCallbackContext({})
  cb(ctx)
  assert ctx.state["user_location"] == ""
  assert ctx.state["favorite_team"] == "Mercedes"

  # Turn 1: user_location is empty -> needs_user_location is True
  res1 = get_race_schedule(race_name="next", user_location=ctx.state["user_location"])
  assert res1["status"] == "success"
  assert res1["needs_user_location"] is True
  assert "agent_action" in res1

  # Turn 2: user provides location "London" -> callback preserves it -> localized BST times
  ctx.state["user_location"] = "London"
  cb(ctx)
  assert ctx.state["user_location"] == "London"

  res2 = get_race_schedule(race_name="next", user_location=ctx.state["user_location"])
  assert res2["status"] == "success"
  assert res2["needs_user_location"] is False
  assert "BST" in res2["localized_sessions"]["Race"]


def test_comb_02_merch_order_lookup_to_damaged_request_to_availability_check() -> None:
  """Pairwise: lookup_mock_merch_order -> submit_mock_merch_request -> check_merch_availability."""
  cb = load_before_agent_callback()
  lookup_order = load_tool_function("lookup_mock_merch_order")
  submit_request = load_tool_function("submit_mock_merch_request")
  check_avail = load_tool_function("check_merch_availability")

  ctx = DummyCallbackContext({})
  cb(ctx)
  assert ctx.state["is_mock_mode"] == "true"

  # Step 1: Lookup MERC-1002
  ctx.state["order_number"] = "MERC-1002"
  cb(ctx)
  assert ctx.state["order_number"] == "MERC-1002"
  order_res = lookup_order(order_number=ctx.state["order_number"])
  assert order_res["status"] == "success"
  assert order_res["is_mock"] is True
  assert order_res["order"]["return_eligible"] is True
  first_item = order_res["order"]["items"][0]
  item_name = first_item.get("name", str(first_item)) if isinstance(first_item, dict) else str(first_item)

  # Step 2: Submit exchange/damaged_item claim for that item
  req_res = submit_request(
      order_number=order_res["order_number"],
      request_type="exchange",
      item_name=item_name,
      reason="Exchange size L for XL",
  )
  assert req_res["status"] == "success"
  assert req_res["is_mock"] is True
  assert "MOCK-REQ" in req_res["reference_id"] and "1002" in req_res["reference_id"]

  # Step 3: Check replacement size XL availability
  avail_res = check_avail(item_query="polo", size="XL")
  assert avail_res["status"] == "success"
  assert avail_res["in_stock"] is True
  assert "XL" in avail_res["available_sizes"]


def test_comb_03_merch_out_of_stock_to_official_store_link_redirect() -> None:
  """Pairwise: check_merch_availability (XXL error) -> get_official_links(category='merch')."""
  check_avail = load_tool_function("check_merch_availability")
  get_links = load_tool_function("get_official_links")

  avail_res = check_avail(item_query="polo", size="XXL")
  assert avail_res["status"] == "error"
  assert avail_res["in_stock"] is False
  assert avail_res["official_store_url"] == "https://shop.mercedesamgf1.com/"

  link_res = get_links(category="merch")
  assert link_res["status"] == "success"
  assert avail_res["official_store_url"] in str(link_res)


def test_comb_04_ticketing_agent_official_links_and_race_schedule_integration() -> None:
  """Pairwise: ticketing_agent combining get_official_links('tickets') + get_race_schedule."""
  get_links = load_tool_function("get_official_links")
  get_schedule = load_tool_function("get_race_schedule")

  ticket_cfg = load_json_file(AGENTS_DIR / "ticketing_agent" / "ticketing_agent.json")
  assert "get_official_links" in ticket_cfg["tools"]
  assert "get_race_schedule" in ticket_cfg["tools"]

  sched_res = get_schedule(race_name="silverstone", user_location="London")
  link_res = get_links(category="tickets")

  assert sched_res["status"] == "success"
  assert sched_res["race"]["race_name"] == "British Grand Prix"
  assert link_res["status"] == "success"
  assert "https://www.formula1.com/en/tickets" in str(link_res)


def test_comb_05_race_info_agent_schedule_and_standings_mercedes_consistency() -> None:
  """Pairwise: race_info_agent combining get_race_schedule + get_driver_standings."""
  get_schedule = load_tool_function("get_race_schedule")
  get_standings = load_tool_function("get_driver_standings")

  sched = get_schedule(race_name="monza", user_location="Milan")
  standings = get_standings(category="both", team_filter="Mercedes")

  assert sched["status"] == "success"
  assert standings["status"] == "success"
  assert sched["data_freshness"] == standings["data_freshness"] == "latest_available"
  assert "Antonelli" in sched["race"]["mercedes_context"]
  merc_names = " ".join(str(d) for d in standings["mercedes_drivers"])
  assert "George Russell" in merc_names and "Kimi Antonelli" in merc_names


def test_comb_06_app_variable_declarations_match_callback_state_keys() -> None:
  """Pairwise: app.json variableDeclarations <-> before_agent_callback state keys (V100/V101)."""
  app_data = load_json_file(APP_DIR / "app.json")
  declared_vars = {
      v["name"]: v["schema"]["type"] for v in app_data.get("variableDeclarations", [])
  }
  assert set(declared_vars.keys()) == set(EXPECTED_VARIABLES)

  cb = load_before_agent_callback()
  ctx = DummyCallbackContext({})
  cb(ctx)

  for key, val in ctx.state.items():
    assert key in declared_vars, f"Callback wrote undeclared variable {key} (V100)"
    assert isinstance(val, str), f"Callback variable {key} must be str for STRING schema (V101)"


def test_comb_07_app_variable_declarations_match_instruction_placeholders() -> None:
  """Pairwise: app.json variableDeclarations <-> instruction.txt {var} placeholders (V104)."""
  app_data = load_json_file(APP_DIR / "app.json")
  declared_vars = {v["name"] for v in app_data.get("variableDeclarations", [])}
  allowed_vars = declared_vars | {"current_date"}

  var_re = re.compile(r"(?<!\{)\{([a-zA-Z_][a-zA-Z0-9_]*)\}(?!\})")
  used_across_instructions: set[str] = set()
  for agent_name in EXPECTED_AGENTS:
    text = (AGENTS_DIR / agent_name / "instruction.txt").read_text(encoding="utf-8")
    for match in var_re.findall(text):
      assert match in allowed_vars, (
          f"{agent_name}/instruction.txt references undeclared variable {{{match}}} (V104)"
      )
      used_across_instructions.add(match)

  # Ensure core session variables are actively referenced in instructions
  for core_var in ("favorite_team", "is_mock_mode", "user_location", "order_number", "current_date"):
    assert core_var in used_across_instructions, f"Variable {{{core_var}}} not referenced in any instruction.txt"


def test_comb_08_app_variable_declarations_match_all_eval_session_parameters() -> None:
  """Pairwise: app.json variableDeclarations <-> goldens, simulations, tool_tests variables (V100/V101)."""
  app_data = load_json_file(APP_DIR / "app.json")
  declared_vars = {v["name"] for v in app_data.get("variableDeclarations", [])}

  goldens = load_yaml_file(EVALS_DIR / "goldens" / "goldens.yaml")
  for k, v in goldens.get("common_session_parameters", {}).items():
    assert k in declared_vars, f"Undeclared common_session_parameter {k} in goldens.yaml"
    assert isinstance(v, str), f"common_session_parameter {k} must be str"
  for conv in goldens.get("conversations", []):
    for k, v in conv.get("session_parameters", {}).items():
      assert k in declared_vars, f"Undeclared session_parameter {k} in golden {conv.get('conversation')}"
      assert isinstance(v, str), f"session_parameter {k} must be str"

  sims = load_yaml_file(EVALS_DIR / "simulations" / "simulations.yaml")
  for sim in sims.get("evals", []):
    for k, v in sim.get("session_parameters", {}).items():
      assert k in declared_vars, f"Undeclared session_parameter {k} in simulation {sim.get('name')}"
      assert isinstance(v, str), f"session_parameter {k} must be str"

  tool_tests = load_yaml_file(EVALS_DIR / "tool_tests" / "tool_tests.yaml")
  for tt in tool_tests.get("tests", []):
    for k, v in (tt.get("variables") or {}).items():
      assert k in declared_vars, f"Undeclared variable {k} in tool_test {tt.get('name')}"
      assert isinstance(v, str)


def test_comb_09_agent_json_tools_match_instruction_tool_refs_1_to_1() -> None:
  """Pairwise: <agent>.json tools array <-> instruction.txt {@TOOL: ...} refs (I012/I013/S002)."""
  tool_ref_re = re.compile(r"\{@TOOL:\s*([^}]+)\}")
  for agent_name in EXPECTED_AGENTS:
    cfg = load_json_file(AGENTS_DIR / agent_name / f"{agent_name}.json")
    declared_tools = {t.strip() for t in cfg.get("tools", [])}
    instr = (AGENTS_DIR / agent_name / "instruction.txt").read_text(encoding="utf-8")
    referenced_tools = {m.strip() for m in tool_ref_re.findall(instr)}
    assert declared_tools == referenced_tools, (
        f"Tool mismatch in {agent_name}: json={declared_tools} vs instruction={referenced_tools}"
    )


def test_comb_10_root_agent_child_agents_match_instruction_agent_refs_1_to_1() -> None:
  """Pairwise: totto_root_agent.json childAgents <-> instruction.txt {@AGENT: ...} refs (I008/S004)."""
  root_cfg = load_json_file(AGENTS_DIR / "totto_root_agent" / "totto_root_agent.json")
  child_agents = set(root_cfg.get("childAgents", []))
  assert child_agents == {"race_info_agent", "merch_support_agent", "ticketing_agent"}

  root_instr = (AGENTS_DIR / "totto_root_agent" / "instruction.txt").read_text(encoding="utf-8")
  agent_ref_re = re.compile(r"\{@AGENT:\s*([^}]+)\}")
  referenced_agents = {m.strip() for m in agent_ref_re.findall(root_instr)}
  assert child_agents == referenced_agents

  # Sub-agents must have no childAgents (S007 single-parent hierarchy)
  for sub_agent in child_agents:
    sub_cfg = load_json_file(AGENTS_DIR / sub_agent / f"{sub_agent}.json")
    assert not sub_cfg.get("childAgents"), f"Sub-agent {sub_agent} must not declare childAgents"


def test_comb_11_execute_all_tool_tests_yaml_cases_against_live_python_tools() -> None:
  """Pairwise: Execute every test case in evals/tool_tests/tool_tests.yaml against actual Python tools."""
  tool_tests_data = load_yaml_file(EVALS_DIR / "tool_tests" / "tool_tests.yaml")
  tests = tool_tests_data.get("tests", [])
  assert len(tests) >= 15

  loaded_tools = {name: load_tool_function(name) for name in EXPECTED_TOOLS}

  for tc in tests:
    tc_name = tc["name"]
    tool_name = tc["tool"]
    assert tool_name in loaded_tools, f"Unknown tool '{tool_name}' in tool_tests.yaml case '{tc_name}'"
    fn = loaded_tools[tool_name]
    args = tc.get("args", {})
    response = fn(**args)
    assert isinstance(response, dict), f"Tool {tool_name} did not return a dict in {tc_name}"

    for exp in tc.get("expectations", {}).get("response", []):
      path = exp["path"]
      op = exp["operator"]
      expected_val = exp.get("value")
      actual_val = _eval_jsonpath(response, path)

      if op in ("equals", "=="):
        assert actual_val == expected_val, (
            f"[{tc_name}] {path} expected == {expected_val!r}, got {actual_val!r}"
        )
      elif op in ("not_equals", "!="):
        assert actual_val != expected_val, (
            f"[{tc_name}] {path} expected != {expected_val!r}, got {actual_val!r}"
        )
      elif op == "contains":
        assert expected_val in str(actual_val), (
            f"[{tc_name}] {path} expected to contain {expected_val!r}, got {actual_val!r}"
        )
      elif op == "in":
        assert actual_val in expected_val, (
            f"[{tc_name}] {path} expected in {expected_val!r}, got {actual_val!r}"
        )
      elif op == "not in":
        assert actual_val not in expected_val, (
            f"[{tc_name}] {path} expected not in {expected_val!r}, got {actual_val!r}"
        )
      elif op in ("is_not_null", "not_null"):
        assert actual_val is not None, f"[{tc_name}] {path} expected is_not_null, got None"
      elif op in ("is_null", "null"):
        assert actual_val is None, f"[{tc_name}] {path} expected is_null, got {actual_val!r}"
      elif op in ("greater_than", ">"):
        assert actual_val > expected_val
      elif op in ("less_than", "<"):
        assert actual_val < expected_val
      elif op == "length_equals":
        assert len(actual_val) == expected_val
      elif op == "length_greater_than":
        assert len(actual_val) > expected_val
      elif op == "length_less_than":
        assert len(actual_val) < expected_val
      else:
        raise AssertionError(f"Unsupported operator {op} in {tc_name}")


def test_comb_12_dual_jsonpath_parity_across_all_6_tools_success_and_error() -> None:
  """Pairwise: Verify $.key == $.result.key across all 6 tools on both success and error paths."""
  cases = [
      ("get_race_schedule", {"race_name": "miami", "user_location": "London"}, {"race_name": "Narnia Grand Prix"}),
      ("get_driver_standings", {"category": "drivers", "team_filter": "Mercedes"}, {"category": "invalid_category"}),
      ("lookup_mock_merch_order", {"order_number": "MERC-1001"}, {"order_number": "MERC-9999"}),
      (
          "submit_mock_merch_request",
          {"order_number": "MERC-1001", "request_type": "return"},
          {"order_number": "MERC-9999", "request_type": "return"},
      ),
      ("check_merch_availability", {"item_query": "polo", "size": "L"}, {"item_query": "polo", "size": "XXL"}),
      ("get_official_links", {"category": "tickets"}, {"category": "betting"}),
  ]
  for tool_name, ok_args, err_args in cases:
    fn = load_tool_function(tool_name)
    ok_res = fn(**ok_args)
    assert ok_res["status"] == "success"
    assert "result" in ok_res and isinstance(ok_res["result"], dict)
    assert ok_res["result"]["status"] == "success"

    err_res = fn(**err_args)
    assert err_res["status"] == "error"
    assert isinstance(err_res.get("agent_action"), str) and len(err_res["agent_action"]) > 10
    assert "result" in err_res and isinstance(err_res["result"], dict)
    assert err_res["result"]["status"] == "error"
    assert err_res["result"]["agent_action"] == err_res["agent_action"]


def test_comb_13_goldens_tool_calls_cross_validated_against_registered_tools_and_agents() -> None:
  """Pairwise: goldens.yaml tool_calls actions and transfer targets match app tools and agents (E002/E003)."""
  goldens = load_yaml_file(EVALS_DIR / "goldens" / "goldens.yaml")
  valid_actions = set(EXPECTED_TOOLS) | {"transfer_to_agent", "end_session"}
  valid_agents = set(EXPECTED_AGENTS)

  for conv in goldens.get("conversations", []):
    for turn in conv.get("turns", []):
      for tc in turn.get("tool_calls", []) or []:
        action = tc.get("action") or tc.get("name")
        assert action in valid_actions, f"Invalid tool action {action} in golden {conv.get('conversation')}"
        if action == "transfer_to_agent":
          target_agent = tc.get("agent") or tc.get("args", {}).get("agent_name")
          assert target_agent in valid_agents, f"Invalid transfer target {target_agent}"


def test_comb_14_all_merch_tools_enforce_mock_flag_and_disclaimer_invariants() -> None:
  """Pairwise: lookup_mock_merch_order, submit_mock_merch_request, check_merch_availability mock invariants."""
  lookup_fn = load_tool_function("lookup_mock_merch_order")
  submit_fn = load_tool_function("submit_mock_merch_request")
  avail_fn = load_tool_function("check_merch_availability")

  for res in (
      lookup_fn("MERC-1001"),
      lookup_fn("MERC-9999"),
      submit_fn("MERC-1001", "return"),
      submit_fn("MERC-9999", "return"),
      avail_fn("cap", "One Size"),
      avail_fn("polo", "XXL"),
  ):
    assert res.get("is_mock") is True, f"Merch tool output missing is_mock=True: {res}"
    assert "mock" in str(res).lower()


def test_comb_15_all_3_mock_orders_support_all_3_request_types_matrix() -> None:
  """Pairwise 3x3 matrix: (MERC-1001, MERC-1002, MERC-1003) x (return, exchange, damaged_item)."""
  lookup_fn = load_tool_function("lookup_mock_merch_order")
  submit_fn = load_tool_function("submit_mock_merch_request")

  for order_id in ("MERC-1001", "MERC-1002", "MERC-1003"):
    ord_res = lookup_fn(order_id)
    assert ord_res["status"] == "success"
    first_item = ord_res["order"]["items"][0]
    item_name = first_item.get("name", str(first_item)) if isinstance(first_item, dict) else str(first_item)

    for req_type in ("return", "exchange", "damaged_item"):
      req_res = submit_fn(
          order_number=order_id,
          request_type=req_type,
          item_name=item_name,
          reason=f"Testing {req_type} for {order_id}",
      )
      assert req_res["status"] == "success"
      assert req_res["order_number"] == order_id
      assert req_res["request_type"] == req_type
      assert order_id.split("-")[1] in req_res["reference_id"]


def test_comb_16_race_schedule_across_all_races_and_timezones_matrix() -> None:
  """Pairwise matrix: 8 supported races x 5 global timezones."""
  get_race_schedule = load_tool_function("get_race_schedule")
  races = ("miami", "monaco", "silverstone", "monza", "las_vegas", "bahrain", "australia", "suzuka")
  locations = ("London", "New York", "Berlin", "Tokyo", "Los Angeles")

  for race in races:
    for loc in locations:
      res = get_race_schedule(race_name=race, user_location=loc)
      assert res["status"] == "success"
      assert res["needs_user_location"] is False
      assert "Race" in res["localized_sessions"]
      assert "Qualifying" in res["localized_sessions"]


def test_comb_17_official_links_shared_across_root_merch_and_ticketing_agents() -> None:
  """Pairwise: get_official_links is declared & referenced in root, merch, and ticketing agents."""
  for agent_name in ("totto_root_agent", "merch_support_agent", "ticketing_agent"):
    cfg = load_json_file(AGENTS_DIR / agent_name / f"{agent_name}.json")
    instr = (AGENTS_DIR / agent_name / "instruction.txt").read_text(encoding="utf-8")
    assert "get_official_links" in cfg["tools"]
    assert "{@TOOL: get_official_links}" in instr


def test_comb_18_callback_sync_files_match_app_callback_code() -> None:
  """Pairwise: app callback python_code.py matches synced evals/callback_tests callback code."""
  app_cb = (
      AGENTS_DIR
      / "totto_root_agent"
      / "before_agent_callbacks"
      / "before_agent_callbacks_01"
      / "python_code.py"
  )
  synced_cb = (
      EVALS_DIR
      / "callback_tests"
      / "agents"
      / "totto_root_agent"
      / "before_agent_callbacks"
      / "before_agent"
      / "python_code.py"
  )
  assert app_cb.is_file()
  assert synced_cb.is_file()
  assert app_cb.read_text(encoding="utf-8") == synced_cb.read_text(encoding="utf-8")
