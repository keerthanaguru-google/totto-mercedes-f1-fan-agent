"""Shared pytest fixtures and module loaders for the 4-tier E2E test suite."""

import builtins
import importlib.util
import json
from pathlib import Path
from typing import Any, Callable
import pytest
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
APP_DIR = PROJECT_ROOT / "cxas_app" / "totto_mercedes_f1_agent"
AGENTS_DIR = APP_DIR / "agents"
TOOLS_DIR = APP_DIR / "tools"
EVALS_DIR = PROJECT_ROOT / "evals"

EXPECTED_AGENTS = (
    "totto_root_agent",
    "race_info_agent",
    "merch_support_agent",
    "ticketing_agent",
)

EXPECTED_TOOLS = (
    "get_race_schedule",
    "get_driver_standings",
    "lookup_merch_order",
    "submit_merch_request",
    "check_merch_availability",
    "get_official_links",
)

EXPECTED_VARIABLES = (
    "favorite_team",
    "is_mock_mode",
    "user_location",
    "order_number",
    "initialized",
)


_TOOL_MODULE_CACHE: dict[str, Callable[..., dict[str, Any]]] = {}


def load_tool_function(tool_name: str) -> Callable[..., dict[str, Any]]:
  """Dynamically loads and returns the Python function for a custom CXAS tool."""
  if tool_name in _TOOL_MODULE_CACHE:
    return _TOOL_MODULE_CACHE[tool_name]
  code_path = TOOLS_DIR / tool_name / "python_function" / "python_code.py"
  assert code_path.is_file(), f"Tool source file missing: {code_path}"
  spec = importlib.util.spec_from_file_location(f"cxas_tool_{tool_name}", code_path)
  assert spec is not None and spec.loader is not None
  module = importlib.util.module_from_spec(spec)
  spec.loader.exec_module(module)
  fn = getattr(module, tool_name, None)
  assert callable(fn), f"Function '{tool_name}' not found in {code_path}"
  _TOOL_MODULE_CACHE[tool_name] = fn
  return fn


def load_before_agent_callback() -> Callable[..., Any]:
  """Dynamically loads and returns before_agent_callback with GECX sandbox globals."""
  try:
    from cxas_scrapi.utils.callback_libs import CallbackContext, Content
    builtins.CallbackContext = CallbackContext
    builtins.Content = Content
  except ImportError:
    pass

  cb_path = (
      AGENTS_DIR
      / "totto_root_agent"
      / "before_agent_callbacks"
      / "before_agent_callbacks_01"
      / "python_code.py"
  )
  assert cb_path.is_file(), f"Callback source file missing: {cb_path}"
  spec = importlib.util.spec_from_file_location("totto_before_agent_cb", cb_path)
  assert spec is not None and spec.loader is not None
  module = importlib.util.module_from_spec(spec)
  spec.loader.exec_module(module)
  fn = getattr(module, "before_agent_callback", None)
  assert callable(fn), f"before_agent_callback not found in {cb_path}"
  return fn


class DummyCallbackContext:
  """Lightweight GECX CallbackContext stand-in for isolated unit/E2E testing."""

  def __init__(self, initial_state: dict[str, Any] | None = None) -> None:
    self.state: dict[str, Any] = dict(initial_state) if initial_state is not None else {}


class _FastOpenF1Response:
  """Deterministic 200 OK response stand-in for OpenF1 HTTP probes."""

  status_code = 200

  def json(self) -> list[dict[str, Any]]:
    return [{"meeting_key": 1280, "driver_number": 63, "full_name": "George RUSSELL"}]


@pytest.fixture(autouse=True)
def _fast_openf1_default_mock(monkeypatch: pytest.MonkeyPatch) -> None:
  """Prevents slow live network calls during bulk test runs while allowing per-test overrides."""
  try:
    import requests
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: _FastOpenF1Response())
  except ImportError:
    pass


def load_json_file(path: Path) -> dict[str, Any]:
  """Loads and parses a JSON file."""
  assert path.is_file(), f"Expected JSON file does not exist: {path}"
  return json.loads(path.read_text(encoding="utf-8"))


def load_yaml_file(path: Path) -> Any:
  """Loads and parses a YAML file."""
  assert path.is_file(), f"Expected YAML file does not exist: {path}"
  return yaml.safe_load(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def project_root() -> Path:
  return PROJECT_ROOT


@pytest.fixture(scope="session")
def app_dir() -> Path:
  return APP_DIR
