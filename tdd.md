# Technical Design Document: Totto, Mercedes F1 Fan Agent

## 1. Overview & Objectives

**Totto, Mercedes F1 Fan Agent** (`totto_mercedes_f1_agent`, display name `keerthanaguru-totto-mercedes-f1-agent`) is a voice-first, multi-agent Customer Engagement Suite (CES) application built for Mercedes-AMG PETRONAS Formula One Team fans and general Formula 1 audiences.

### Design Goals
- **Voice-First Delivery**: Keep initial spoken responses concise (2–3 sentences) and conversational, offering deeper breakdowns upon request.
- **Mercedes-First Perspective**: Prioritize Mercedes-AMG PETRONAS F1 context (George Russell #63 and Kimi Antonelli #12, Silver Arrows heritage, and constructor performance) while maintaining objective accuracy across the full Formula 1 grid.
- **Clear Domain Separation**: Use a hub-and-spoke multi-agent architecture with `totto_root_agent` routing specialized journeys to `race_info_agent`, `merch_support_agent`, and `ticketing_agent`.
- **Safe & Transparent Boundaries**:
  - Fictional AI concierge identity (never impersonating Toto Wolff or team executives).
  - Explicit disclosure when using general Formula 1 historical knowledge vs. structured tool data.
  - Explicit disclosure that merchandise order lookups, returns, exchanges, and damaged-item claims run in a demo/mock environment.
  - Strictly informational ticketing guidance redirecting to official Formula 1 ticketing (`https://www.formula1.com/en/tickets` / `tickets.formula1.com`) without quoting prices, seat availability, or booking tickets.

---

## 2. Multi-Agent Architecture

### 2.1 Architecture Diagram

```
+-----------------------------------------------------------------------------------+
|                                    User (Voice / Chat)                            |
+-----------------------------------------------------------------------------------+
                                           |
                                           v
+-----------------------------------------------------------------------------------+
|                          [before_agent_callback]                                  |
|  Initializes session state:                                                       |
|  - favorite_team = "Mercedes"                                                     |
|  - is_mock_mode  = "true"                                                         |
|  - user_location = "" (if unset)                                                  |
|  - order_number  = "" (if unset)                                                  |
|  - initialized   = "true"                                                         |
+-----------------------------------------------------------------------------------+
                                           |
                                           v
+-----------------------------------------------------------------------------------+
|                        totto_root_agent (Root / Concierge)                        |
|  - Introduces self as "Totto, Mercedes F1 Fan Agent"                              |
|  - Handles greetings, F1/Mercedes history & rules (with general-knowledge note)   |
|  - Handles general official team/social link requests                             |
|  - Enforces anti-impersonation & insider-info guardrails                          |
|  - Matches user's language for multilingual conversations                         |
|  Tools: get_official_links, end_session                                           |
+-----------------------------------------------------------------------------------+
            |                              |                              |
            | Race schedule, sessions,     | Merch order status,          | Race tickets,
            | weather, driver/team         | returns, exchanges,          | hospitality,
            | standings, local times       | damaged items, stock         | venue attendance
            v                              v                              v
+-------------------------+  +-----------------------------+  +-------------------------+
|     race_info_agent     |  |     merch_support_agent     |  |     ticketing_agent     |
|                         |  |                             |  |                         |
| - Checks user_location  |  | - Discloses mock/demo mode  |  | - Prohibits direct      |
|   before giving local   |  | - Requires only order_number|  |   ticket sales, pricing,|
|   session times         |  |   for order lookups/claims  |  |   or seat inventory     |
| - Highlights Mercedes   |  | - Checks item availability  |  | - Directs to official   |
|   drivers (#63, #12)    |  |   & directs purchases to    |  |   F1 ticketing portal   |
| - Discloses latest-     |  |   official Mercedes store   |  | - Shares weekend dates  |
|   available data status |  |                             |  |   for attendance context|
|                         |  |                             |  |                         |
| Tools:                  |  | Tools:                      |  | Tools:                  |
| - get_race_schedule     |  | - lookup_mock_merch_order   |  | - get_official_links    |
| - get_driver_standings  |  | - submit_mock_merch_request |  | - get_race_schedule     |
| - end_session           |  | - check_merch_availability  |  | - end_session           |
|                         |  | - get_official_links        |  |                         |
|                         |  | - end_session               |  |                         |
+-------------------------+  +-----------------------------+  +-------------------------+
```

### 2.2 Sub-Agent Routing Matrix

| Agent Name | Role | Entry Triggers | Tools Assigned | Child Agents |
| :--- | :--- | :--- | :--- | :--- |
| `totto_root_agent` | Root Concierge, Brand Ambassador, History & Rules Educator | Initial greeting, identity questions, F1/Mercedes history, rules/formats, general social/team links, off-topic/guardrail handling, session wrap-up | `get_official_links`, `end_session` | `race_info_agent`, `merch_support_agent`, `ticketing_agent` |
| `race_info_agent` | Race Weekend, Schedule, Weather & Standings Specialist | Upcoming/recent races, practice/qualifying/sprint/race start times, circuit weather, driver/constructor standings, Mercedes performance | `get_race_schedule`, `get_driver_standings`, `end_session` | None |
| `merch_support_agent` | Mock Merchandise Support & Availability Specialist | Merch order tracking, returns, exchanges, damaged items, product stock checks, where to buy official Mercedes gear | `lookup_mock_merch_order`, `submit_mock_merch_request`, `check_merch_availability`, `get_official_links`, `end_session` | None |
| `ticketing_agent` | Official Formula 1 Ticketing & Attendance Guide | Buying F1 tickets, grandstand/hospitality inquiries, race attendance guidance | `get_official_links`, `get_race_schedule`, `end_session` | None |

---

## 3. Tool Specifications

All custom tools are synchronous Python functions (`executionType: "SYNCHRONOUS"`) with full type annotations, Google-style docstrings, deterministic structured data, and actionable `"agent_action"` fields in all error responses.

### 3.1 `get_race_schedule`
- **Path**: `tools/get_race_schedule/python_function/python_code.py`
- **Signature**: `def get_race_schedule(race_name: str = "next", user_location: str = "") -> dict[str, Any]:`
- **Purpose**: Returns structured race weekend schedule (Practice 1–3, Sprint/Qualifying, Grand Prix start times in venue time, UTC, and localized time when `user_location` is provided), circuit details, weather forecast, and Mercedes-specific weekend storylines via live OpenF1 API (`https://api.openf1.org/v1/meetings`, `/v1/sessions`, `/v1/weather`) with deterministic fallback fixtures.
- **Supported Races**: `"next"` / `"miami"` (Miami Grand Prix), `"monaco"` (Monaco Grand Prix), `"silverstone"` / `"british"` (British Grand Prix), `"monza"` / `"italian"` (Italian Grand Prix), `"las vegas"` / `"vegas"` (Las Vegas Grand Prix), `"bahrain"` (Bahrain Grand Prix), `"australia"` / `"melbourne"` (Australian Grand Prix), `"japan"` / `"suzuka"` (Japanese Grand Prix), `"all"` (calendar overview).
- **Location Handling**: When `user_location` is empty, returns `needs_user_location: True` and `agent_action` instructing the agent to ask the user for their location/timezone before quoting localized session times.

### 3.2 `get_driver_standings`
- **Path**: `tools/get_driver_standings/python_function/python_code.py`
- **Signature**: `def get_driver_standings(category: str = "drivers", team_filter: str = "Mercedes") -> dict[str, Any]:`
- **Purpose**: Returns latest-available Formula 1 World Drivers' Championship (`category="drivers"`) or Constructors' Championship (`category="constructors"`) standings via live OpenF1 API (`https://api.openf1.org/v1/drivers`, `/v1/position`) with deterministic fallback fixtures, always highlighting Mercedes-AMG PETRONAS F1 (George Russell #63 and Kimi Antonelli #12) alongside top grid context, plus `"data_freshness": "latest_available"` so the agent discloses that data is latest-available rather than live telemetry.

### 3.3 `lookup_mock_merch_order`
- **Path**: `tools/lookup_mock_merch_order/python_function/python_code.py`
- **Signature**: `def lookup_mock_merch_order(order_number: str) -> dict[str, Any]:`
- **Purpose**: Looks up a mocked Mercedes F1 merchandise order using only `order_number` (e.g., `MERC-1001`, `MERC-1002`, `MERC-1003`). Always sets `"is_mock": True` and includes a `"mock_disclaimer"` reminding the agent to state clearly that order data is from a mock demonstration environment.

### 3.4 `submit_mock_merch_request`
- **Path**: `tools/submit_mock_merch_request/python_function/python_code.py`
- **Signature**: `def submit_mock_merch_request(order_number: str, request_type: str, item_name: str = "", reason: str = "") -> dict[str, Any]:`
- **Purpose**: Submits a mocked post-purchase support request (`request_type` in `{"return", "exchange", "damaged_item"}`) requiring only `order_number`. Returns a mocked reference ID, simulated resolution steps, `"is_mock": True`, and `"mock_disclaimer"`.

### 3.5 `check_merch_availability`
- **Path**: `tools/check_merch_availability/python_function/python_code.py`
- **Signature**: `def check_merch_availability(item_query: str, size: str = "") -> dict[str, Any]:`
- **Purpose**: Searches the mocked Mercedes-AMG PETRONAS F1 merchandise catalog (caps, team polo shirts, hoodies, scale model cars, driver jerseys for George Russell #63 and Kimi Antonelli #12) by product name and optional size. Returns stock status, available sizes, `"is_mock": True`, and official store link context (`https://shop.mercedesamgf1.com/`).

### 3.6 `get_official_links`
- **Path**: `tools/get_official_links/python_function/python_code.py`
- **Signature**: `def get_official_links(category: str = "all") -> dict[str, Any]:`
- **Purpose**: Returns verified official URLs for `"tickets"` (`https://www.formula1.com/en/tickets`), `"merch"` (`https://shop.mercedesamgf1.com/`), `"team"` (`https://www.mercedesamgf1.com/`), `"social"` (Instagram, X, YouTube), `"fan"` (fan club resources), or `"all"`.

### 3.7 `end_session` (System Tool)
- Declared in `app.json` and every agent's `"tools"` list, and referenced via `{@TOOL: end_session}` in every agent's `instruction.txt`.

---

## 4. Session State Variables & Callbacks

### 4.1 Declared Variables (`app.json` -> `variableDeclarations`)

| Variable Name | Schema Type | Default Initialized Value | Description |
| :--- | :--- | :--- | :--- |
| `favorite_team` | `STRING` | `"Mercedes"` | The user's prioritized Formula 1 team context, defaulting to Mercedes. |
| `is_mock_mode` | `STRING` | `"true"` | Flag indicating that merchandise order and inventory flows operate in mock demo mode. |
| `user_location` | `STRING` | `""` | The user's city, region, or timezone for localizing race session start times. |
| `order_number` | `STRING` | `""` | The user's merchandise order number for mocked order lookups and support requests. |
| `initialized` | `STRING` | `"true"` | Session initialization marker set by `before_agent_callback` on first turn. |

### 4.2 `before_agent_callback` (`totto_root_agent`)
- **Path**: `agents/totto_root_agent/before_agent_callbacks/before_agent_callbacks_01/python_code.py`
- **Behavior**:
  1. Checks `callback_context.state.get("initialized") == "true"`; if already initialized, ensures defaults remain intact and returns `None`.
  2. Sets `state["initialized"] = "true"`, `state["favorite_team"] = "Mercedes"` (if unset/empty), `state["is_mock_mode"] = "true"` (if unset/empty), `state["user_location"] = ""` (if key missing), and `state["order_number"] = ""` (if key missing).
  3. Returns `None` so normal agent execution proceeds.

---

## 5. Persona, Guardrails & Instruction Design

- **Identity**: Introduces itself as **Totto, Mercedes F1 Fan Agent**. Inspired by the passion of the Silver Arrows pit wall, but explicitly a fictional AI fan concierge.
- **Anti-Impersonation Guardrail**: Never claims to be Toto Wolff, a Mercedes employee, a driver, an FIA official, or a ticketing partner.
- **Voice-First Brevity**: Speaks in punchy, natural sentences without markdown clutter or raw URLs read character-by-character unless requested.
- **Uncertainty & Data Source Disclosures**:
  - **Race/Standings Data**: States that standings and results reflect the latest available structured data rather than live car telemetry.
  - **Historical/Educational Questions**: Explicitly states when relying on general Formula 1 knowledge for historical seasons, rules, or heritage moments.
  - **Mock Merch Support**: Explicitly reminds users that order lookups, returns, exchanges, damaged-item claims, and stock checks are part of a mock demonstration and requires only an order number for order-specific flows.
  - **Ticketing**: Never quotes ticket prices, seat inventory, or books tickets; always directs fans to Formula 1's official ticketing destination (`https://www.formula1.com/en/tickets`).
- **Multilingual Support**: Responds in the user's language (e.g., Spanish, French, German, Japanese) while preserving all persona and safety rules.

---

## 6. Evaluation Strategy

1. **Golden Evaluations (`evals/goldens/goldens.yaml`)**:
   - 12 deterministic single- and multi-turn conversations covering greeting & identity, race schedule with location clarification, driver/constructor standings with Mercedes focus, F1/Mercedes history with general-knowledge disclosure, official ticketing redirection, mock merch order lookup, mock merch return/damaged-item submission, merch stock check, anti-impersonation guardrail, and multilingual interaction.
2. **Scenario Simulations (`evals/simulations/simulations.yaml`)**:
   - 8 dynamic end-to-end persona simulations (`P0`/`P1`) testing multi-turn goal completion across race weekend planning, Mercedes performance inquiries, ticket purchase refusal + official redirection, mocked damaged merch claims, Toto Wolff impersonation attempts, and Spanish multilingual fan support.
3. **Tool Unit Tests (`evals/tool_tests/tool_tests.yaml`)**:
   - 14 YAML test cases covering happy paths, default arguments, case-insensitivity, and error/invalid-input handling (`agent_action` verification) across all 6 custom Python tools.
4. **Callback Unit Tests (`evals/callback_tests/`)**:
   - Pytest unit suite (`evals/callback_tests/tests/totto_root_agent/before_agent_callbacks/before_agent/test.py`) synced via `sync-callbacks.py --from-local`, testing fresh state initialization, idempotency on repeat calls, preservation of pre-populated `user_location` / `order_number`, and recovery from empty values.
