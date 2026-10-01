"""Tool for looking up Mercedes-AMG PETRONAS F1 merchandise orders."""

from typing import Any


def lookup_merch_order(order_number: str) -> dict[str, Any]:
  """Looks up a Mercedes F1 merchandise order using only an order number.

  Requires only the order_number parameter (e.g., "MERC-1001", "MERC-1002", or
  "MERC-1003") and returns shipment status, ordered items, carrier, and
  tracking details without requesting personal payment or billing data.

  Args:
    order_number: The merchandise order identifier (e.g., "MERC-1001" or "1001").

  Returns:
    A dictionary containing the order details, order_note, and agent_action
    guidance on errors.
  """
  order_note = (
      "Order lookup requires only your order number and never collects "
      "personal payment, billing, or credit card details."
  )
  sample_orders = ["MERC-1001", "MERC-1002", "MERC-1003"]

  orders_db: dict[str, dict[str, Any]] = {
      "MERC-1001": {
          "order_number": "MERC-1001",
          "status": "Delivered",
          "items": [
              {
                  "name": "George Russell #63 Official Driver Cap",
                  "size": "One Size",
                  "quantity": 1,
              }
          ],
          "carrier": "DHL Express",
          "tracking_number": "MERC-DHL-63001001",
          "delivery_note": "Delivered to front porch on April 14, 2026.",
          "return_eligible": True,
          "exchange_eligible": True,
      },
      "MERC-1002": {
          "order_number": "MERC-1002",
          "status": "In Transit",
          "items": [
              {
                  "name": "Mercedes-AMG PETRONAS W17 Team Polo Shirt",
                  "size": "L",
                  "quantity": 1,
              },
              {
                  "name": "Kimi Antonelli #12 Silver Arrows Graphic Tee",
                  "size": "M",
                  "quantity": 1,
              },
          ],
          "carrier": "UPS Worldwide",
          "tracking_number": "MERC-UPS-12001002",
          "delivery_note": "In transit — estimated delivery within 2 business days.",
          "return_eligible": True,
          "exchange_eligible": True,
      },
      "MERC-1003": {
          "order_number": "MERC-1003",
          "status": "Return Approved - Awaiting Drop-off",
          "items": [
              {
                  "name": "Mercedes-AMG PETRONAS Team Softshell Jacket",
                  "size": "XL",
                  "quantity": 1,
              }
          ],
          "carrier": "FedEx Ground",
          "tracking_number": "MERC-FDX-44001003",
          "delivery_note": (
              "Prepaid return label issued; awaiting carrier drop-off."
          ),
          "return_eligible": True,
          "exchange_eligible": True,
      },
  }

  raw = (order_number or "").strip().upper()
  if not raw:
    return _with_envelope({
        "status": "error",
        "error": "An order number is required to look up a merchandise order.",
        "order_note": order_note,
        "sample_order_numbers": sample_orders,
        "agent_action": (
            "Ask the user for their merchandise order number only (for example "
            "MERC-1001, MERC-1002, or MERC-1003) without requesting payment or "
            "billing information."
        ),
    })

  normalized = f"MERC-{raw}" if raw.isdigit() else raw
  if normalized not in orders_db:
    return _with_envelope({
        "status": "error",
        "error": (
            f"Order '{order_number}' was not found in the merchandise order "
            "records."
        ),
        "order_note": order_note,
        "sample_order_numbers": sample_orders,
        "agent_action": (
            "Explain that the order number was not found in the merchandise "
            "order records, share valid sample order numbers (MERC-1001, "
            "MERC-1002, MERC-1003), and never request personal payment or "
            "billing information."
        ),
    })

  order_record = dict(orders_db[normalized])
  return _with_envelope({
      "status": "success",
      "order_note": order_note,
      "order_number": normalized,
      "order": order_record,
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
