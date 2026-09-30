"""Tool for submitting mocked Mercedes-AMG PETRONAS F1 merch support requests."""

from typing import Any


def submit_mock_merch_request(
    order_number: str,
    request_type: str,
    item_name: str = "",
    reason: str = "",
) -> dict[str, Any]:
  """Submits a mocked return, exchange, or damaged-item merchandise request.

  Requires only the order_number and request_type ("return", "exchange", or
  "damaged_item"). Never collects or processes real payment details, refunds,
  or personal customer data, and always returns an explicit mock disclosure.

  Args:
    order_number: The merchandise order identifier (e.g., "MERC-1001" or "1001").
    request_type: Support action type ("return", "exchange", or "damaged_item").
    item_name: Optional name or description of the item in the order.
      Defaults to "".
    reason: Optional reason for the return, exchange, or damage report.
      Defaults to "".

  Returns:
    A dictionary containing the mocked request reference_id, resolution_steps,
    is_mock flag, mock_disclaimer, and agent_action guidance on errors.
  """
  mock_disclaimer = (
      "MOCK DEMONSTRATION ONLY: This return, exchange, or damaged-item request "
      "is simulated for demo purposes and does not initiate a real refund, "
      "shipment, or account change."
  )
  valid_orders = {
      "MERC-1001": "George Russell #63 Official Driver Cap",
      "MERC-1002": "Mercedes-AMG PETRONAS W17 Team Polo Shirt",
      "MERC-1003": "Mercedes-AMG PETRONAS Team Softshell Jacket",
  }
  request_aliases = {
      "return": "return",
      "returns": "return",
      "refund": "return",
      "exchange": "exchange",
      "exchanges": "exchange",
      "size_exchange": "exchange",
      "swap": "exchange",
      "damaged_item": "damaged_item",
      "damaged": "damaged_item",
      "damage": "damaged_item",
      "defective": "damaged_item",
      "replace": "damaged_item",
      "replacement": "damaged_item",
  }
  supported_types = ["return", "exchange", "damaged_item"]
  sample_orders = ["MERC-1001", "MERC-1002", "MERC-1003"]

  raw_order = (order_number or "").strip().upper()
  normalized_order = f"MERC-{raw_order}" if raw_order.isdigit() else raw_order

  if not normalized_order or normalized_order not in valid_orders:
    return _with_envelope({
        "status": "error",
        "error": (
            f"Order number '{order_number}' is missing or not found in the "
            "mocked merchandise catalog."
        ),
        "is_mock": True,
        "mock_disclaimer": mock_disclaimer,
        "supported_request_types": supported_types,
        "sample_order_numbers": sample_orders,
        "agent_action": (
            "Ask the user for a valid demo order number only (such as "
            "MERC-1001, MERC-1002, or MERC-1003), remind them this is a mock "
            "demonstration, and never ask for payment or personal details."
        ),
    })

  raw_type = (request_type or "").strip().lower().replace(" ", "_")
  canonical_type = request_aliases.get(raw_type, "")
  if not canonical_type:
    return _with_envelope({
        "status": "error",
        "error": (
            f"Unsupported request_type '{request_type}'. Supported types are "
            "'return', 'exchange', or 'damaged_item'."
        ),
        "is_mock": True,
        "mock_disclaimer": mock_disclaimer,
        "supported_request_types": supported_types,
        "sample_order_numbers": sample_orders,
        "agent_action": (
            "Clarify whether the user would like to submit a mocked 'return', "
            "'exchange', or 'damaged_item' claim for their order."
        ),
    })

  numeric_suffix = normalized_order.split("-")[-1]
  reference_id = f"MOCK-REQ-{numeric_suffix}-{canonical_type.upper()}"
  resolved_item = (item_name or "").strip() or valid_orders[normalized_order]
  resolved_reason = (reason or "").strip() or f"Customer requested {canonical_type}"

  steps_by_type = {
      "return": (
          f"Simulated prepaid return label generated under {reference_id}. In "
          "this mock demo, no physical package drop-off or real refund occurs."
      ),
      "exchange": (
          f"Simulated size/item exchange logged under {reference_id} for "
          f"'{resolved_item}'. In this mock demo, no live inventory is "
          "dispatched."
      ),
      "damaged_item": (
          f"Simulated priority damaged-item replacement logged under "
          f"{reference_id} for '{resolved_item}' without requiring photo "
          "uploads or payment details. This is a mock demonstration."
      ),
  }

  return _with_envelope({
      "status": "success",
      "is_mock": True,
      "mock_disclaimer": mock_disclaimer,
      "reference_id": reference_id,
      "order_number": normalized_order,
      "request_type": canonical_type,
      "item_name": resolved_item,
      "reason": resolved_reason,
      "resolution_steps": steps_by_type[canonical_type],
  })


def _with_envelope(payload: dict[str, Any]) -> dict[str, Any]:
  """Attaches result and response mirrors for JSONPath compatibility."""
  base = dict(payload)
  inner_result = dict(base)
  if isinstance(base.get("result"), dict):
    inner_result.update(base["result"])
  out = dict(base)
  out["result"] = inner_result
  response_copy = dict(base)
  response_copy["result"] = dict(inner_result)
  out["response"] = response_copy
  return out
