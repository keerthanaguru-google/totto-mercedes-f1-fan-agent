"""Unit tests for totto_root_agent before_agent_callback."""

from pathlib import Path
import sys
from unittest.mock import MagicMock

_RESOLVED_PARENTS = Path(__file__).resolve().parents
_AGENTS_ROOT = (
    _RESOLVED_PARENTS[4] / "agents"
    if len(_RESOLVED_PARENTS) > 4
    else Path(__file__).resolve().parent
)
if _AGENTS_ROOT.exists() and str(_AGENTS_ROOT) not in sys.path:
  sys.path.append(str(_AGENTS_ROOT))

try:
  import python_code as callback_code  # type: ignore[import-not-found]
except ImportError:
  from totto_root_agent.before_agent_callbacks.before_agent import (  # type: ignore[import-not-found]
      python_code as callback_code,
  )


class TestBeforeAgentCallback:
  """Tests session state initialization and idempotency for before_agent_callback."""

  def _make_context(self, initial_state: dict | None = None) -> MagicMock:
    ctx = MagicMock()
    ctx.state = dict(initial_state) if initial_state is not None else {}
    return ctx

  def test_fresh_session_initializes_all_default_variables(self) -> None:
    """Verifies fresh session initializes favorite_team, is_mock_mode, user_location, order_number, initialized."""
    ctx = self._make_context({})
    result = callback_code.before_agent_callback(ctx)
    assert result is None
    assert ctx.state["favorite_team"] == "Mercedes"
    assert ctx.state["is_mock_mode"] == "true"
    assert ctx.state["user_location"] == ""
    assert ctx.state["order_number"] == ""
    assert ctx.state["initialized"] == "true"

  def test_idempotent_on_repeated_invocations(self) -> None:
    """Verifies repeated callback invocations preserve state without error."""
    ctx = self._make_context({})
    callback_code.before_agent_callback(ctx)
    ctx.state["user_location"] = "London"
    ctx.state["order_number"] = "MERC-1001"
    result = callback_code.before_agent_callback(ctx)
    assert result is None
    assert ctx.state["favorite_team"] == "Mercedes"
    assert ctx.state["is_mock_mode"] == "true"
    assert ctx.state["user_location"] == "London"
    assert ctx.state["order_number"] == "MERC-1001"
    assert ctx.state["initialized"] == "true"

  def test_preserves_existing_custom_session_values(self) -> None:
    """Verifies pre-populated user_location, order_number, and favorite_team are not overwritten."""
    ctx = self._make_context({
        "favorite_team": "Mercedes-AMG PETRONAS",
        "is_mock_mode": "true",
        "user_location": "Tokyo",
        "order_number": "MERC-1002",
    })
    result = callback_code.before_agent_callback(ctx)
    assert result is None
    assert ctx.state["favorite_team"] == "Mercedes-AMG PETRONAS"
    assert ctx.state["user_location"] == "Tokyo"
    assert ctx.state["order_number"] == "MERC-1002"
    assert ctx.state["initialized"] == "true"

  def test_recovers_from_none_or_empty_defaults(self) -> None:
    """Verifies None values for user_location/order_number and empty favorite_team are repaired."""
    ctx = self._make_context({
        "favorite_team": "",
        "is_mock_mode": "",
        "user_location": None,
        "order_number": None,
    })
    result = callback_code.before_agent_callback(ctx)
    assert result is None
    assert ctx.state["favorite_team"] == "Mercedes"
    assert ctx.state["is_mock_mode"] == "true"
    assert ctx.state["user_location"] == ""
    assert ctx.state["order_number"] == ""
    assert ctx.state["initialized"] == "true"
