"""Before-agent callback for initializing Totto Mercedes F1 Fan Agent session state."""

from typing import Optional
from typing import Any

try:
  from cxas_scrapi.utils.callback_libs import CallbackContext, Content
except ImportError:
  CallbackContext = Any  # type: ignore[misc,assignment]
  Content = Any  # type: ignore[misc,assignment]


def before_agent_callback(
    callback_context: CallbackContext,
) -> Optional[Content]:
  """Initializes default session state variables before the root agent runs.

  Sets default values for favorite_team, merch_support_enabled, user_location,
  order_number, and initialized on the session state dictionary while preserving
  any values already populated earlier in the conversation.

  Args:
    callback_context: The ADK callback context containing session state.

  Returns:
    None so that normal agent execution proceeds uninterrupted.
  """
  state = callback_context.state

  if not state.get("favorite_team"):
    state["favorite_team"] = "Mercedes"

  if not state.get("merch_support_enabled"):
    state["merch_support_enabled"] = "true"

  if "user_location" not in state or state.get("user_location") is None:
    state["user_location"] = ""

  if "order_number" not in state or state.get("order_number") is None:
    state["order_number"] = ""

  state["initialized"] = "true"
  return None
