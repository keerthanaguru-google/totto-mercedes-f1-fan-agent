"""Tool for submitting Mercedes-AMG PETRONAS F1 merchandise support requests."""

from typing import Any


def submit_merch_request(
    order_number: str,
    request_type: str,
    item_name: str = "",
    reason: str = "",
) -> dict[str, Any]:
  """Submits a return, exchange, or damaged-item merchandise request.

  Requires only the order_number and request_type ("return", "exchange", or
  "damaged_item"). Never collects or processes payment details, credit card
  numbers, or billing information.

  Args:
    order_number: The merchandise order identifier (e.g., "MERC-1001" or "1001").
    request_type: Support action type ("return", "exchange", or "damaged_item").
    item_name: Optional name or description of the item in the order.
      Defaults to "".
    reason: Optional reason for the return, exchange, or damage report.
      Defaults to "".

  Returns:
    A dictionary containing the request reference_id, resolution_steps,
    request_note, and agent_action guidance on errors.
  """
  request_note = (
      "Merchandise support requests require only your order number and "
      "request type and never collect payment or billing details."
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
            "merchandise order records."
        ),
        "request_note": request_note,
        "supported_request_types": supported_types,
        "sample_order_numbers": sample_orders,
        "agent_action": (
            "Ask the user for a valid merchandise order number only (such as "
            "MERC-1001, MERC-1002, or MERC-1003) and never ask for payment or "
            "personal billing details."
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
        "request_note": request_note,
        "supported_request_types": supported_types,
        "sample_order_numbers": sample_orders,
        "agent_action": (
            "Clarify whether the user would like to submit a 'return', "
            "'exchange', or 'damaged_item' claim for their order."
        ),
    })

  numeric_suffix = normalized_order.split("-")[-1]
  reference_id = f"MERC-REQ-{numeric_suffix}-{canonical_type.upper()}"
  resolved_item = (item_name or "").strip() or valid_orders[normalized_order]
  resolved_reason = (reason or "").strip() or f"Customer requested {canonical_type}"

  steps_by_type = {
      "return": (
          f"Prepaid return authorization logged under {reference_id} for "
          f"'{resolved_item}'. No payment or billing details are required."
      ),
      "exchange": (
          f"Size/item exchange request logged under {reference_id} for "
          f"'{resolved_item}'. No payment or billing details are required."
      ),
      "damaged_item": (
          f"Priority damaged-item replacement claim logged under "
          f"{reference_id} for '{resolved_item}' without requiring photo "
          "uploads or payment details."
      ),
  }

  return _with_envelope({
      "status": "success",
      "request_note": request_note,
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
