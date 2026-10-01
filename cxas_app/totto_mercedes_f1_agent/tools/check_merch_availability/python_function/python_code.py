"""Tool for checking Mercedes-AMG PETRONAS F1 merchandise availability."""

from typing import Any


def check_merch_availability(
    item_query: str,
    size: str = "",
) -> dict[str, Any]:
  """Checks stock and size availability for Mercedes F1 merchandise and provides the official store URL.

  Searches the catalog of Mercedes-AMG PETRONAS Formula One Team gear (driver
  caps, team polos, hoodies, jackets, and scale model cars), verifies size
  availability when requested, and includes the official Mercedes F1 store URL.

  Args:
    item_query: Product name or keyword to search (e.g., "George Russell cap",
      "team polo", "hoodie", "softshell jacket", "model car").
    size: Optional size to check (e.g., "S", "M", "L", "XL", "One Size").
      Defaults to "".

  Returns:
    A dictionary containing stock availability, available_sizes,
    official_store_url, store_note, and agent_action guidance on errors.
  """
  official_store_url = "https://shop.mercedesamgf1.com/"
  store_note = (
      "For official store purchases and full catalog browsing, visit "
      "https://shop.mercedesamgf1.com/."
  )

  catalog: list[dict[str, Any]] = [
      {
          "keywords": ["russell", "63", "driver cap", "cap", "hat"],
          "item": "George Russell #63 Official Mercedes-AMG PETRONAS Driver Cap",
          "in_stock": True,
          "available_sizes": ["One Size"],
          "out_of_stock_sizes": ["S", "M", "L", "XL", "XXL"],
          "price_note": "Visit official store for current pricing",
      },
      {
          "keywords": ["antonelli", "kimi", "12"],
          "item": "Kimi Antonelli #12 Silver Arrows Driver Cap & Tee Collection",
          "in_stock": True,
          "available_sizes": ["One Size", "S", "M", "L", "XL"],
          "out_of_stock_sizes": ["XS", "XXL"],
          "price_note": "Visit official store for current pricing",
      },
      {
          "keywords": ["polo", "shirt", "teamwear", "jersey", "tee", "t-shirt"],
          "item": "Mercedes-AMG PETRONAS W17 Official Team Polo Shirt",
          "in_stock": True,
          "available_sizes": ["S", "M", "L", "XL"],
          "out_of_stock_sizes": ["XS", "XXL", "XXXL"],
          "price_note": "Visit official store for current pricing",
      },
      {
          "keywords": ["hoodie", "sweatshirt", "sweater", "fleece"],
          "item": "Mercedes-AMG PETRONAS Silver Arrows Team Hoodie",
          "in_stock": True,
          "available_sizes": ["M", "L", "XL"],
          "out_of_stock_sizes": ["XS", "S", "XXL"],
          "price_note": "Visit official store for current pricing",
      },
      {
          "keywords": ["jacket", "softshell", "rain", "coat"],
          "item": "Mercedes-AMG PETRONAS Team Softshell Jacket",
          "in_stock": True,
          "available_sizes": ["S", "M", "L"],
          "out_of_stock_sizes": ["XS", "XL", "XXL"],
          "price_note": "Visit official store for current pricing",
      },
      {
          "keywords": ["model", "diecast", "1:18", "w17", "car"],
          "item": "Mercedes-AMG F1 W17 1:18 Scale Collector Model Car",
          "in_stock": True,
          "available_sizes": ["1:18 Scale"],
          "out_of_stock_sizes": [],
          "price_note": "Visit official store for current pricing",
      },
      {
          "keywords": [
              "signed",
              "race suit",
              "helmet",
              "paddock pass",
              "limited edition",
          ],
          "item": "Autographed Race-Worn Collector Suit (Limited Archive)",
          "in_stock": False,
          "available_sizes": [],
          "out_of_stock_sizes": ["S", "M", "L", "XL", "One Size"],
          "price_note": "Currently out of stock in the merchandise catalog",
      },
  ]

  query_clean = (item_query or "").strip()
  if not query_clean:
    return _with_envelope({
        "status": "error",
        "error": "An item_query is required to check merchandise availability.",
        "store_note": store_note,
        "in_stock": False,
        "available_sizes": [],
        "official_store_url": official_store_url,
        "agent_action": (
            "Ask the user which Mercedes F1 merchandise item they want to "
            "check (such as a George Russell cap, team polo, hoodie, jacket, "
            "or scale model car)."
        ),
    })

  q_lower = query_clean.lower()
  matched_entry: dict[str, Any] | None = None
  for entry in catalog:
    if any(kw in q_lower for kw in entry["keywords"]):
      matched_entry = entry
      break

  if matched_entry is None:
    return _with_envelope({
        "status": "error",
        "error": (
            f"Item '{item_query}' was not found in the Mercedes F1 "
            "merchandise catalog."
        ),
        "store_note": store_note,
        "in_stock": False,
        "available_sizes": [],
        "official_store_url": official_store_url,
        "agent_action": (
            "Explain that the requested item was not found in the merchandise "
            "catalog, suggest available items (George Russell #63 cap, "
            "Kimi Antonelli #12 collection, team polo, hoodie, softshell "
            "jacket, or 1:18 model car), and direct the user to "
            "https://shop.mercedesamgf1.com/ for the full official store."
        ),
    })

  if not matched_entry["in_stock"]:
    return _with_envelope({
        "status": "error",
        "error": (
            f"'{matched_entry['item']}' is currently out of stock in the "
            "merchandise catalog."
        ),
        "store_note": store_note,
        "item": matched_entry["item"],
        "in_stock": False,
        "requested_size": (size or "").strip(),
        "available_sizes": [],
        "official_store_url": official_store_url,
        "agent_action": (
            "Inform the user that this item is currently out of stock, offer "
            "alternative in-stock gear such as driver caps or team polos, and "
            "direct them to https://shop.mercedesamgf1.com/."
        ),
    })

  req_size = (size or "").strip()
  available_sizes: list[str] = list(matched_entry["available_sizes"])
  if req_size:
    size_upper = req_size.upper()
    normalized_avail = {s.upper(): s for s in available_sizes}
    if (
        size_upper == "ONE SIZE" or req_size.lower() in ("one size", "os", "default")
    ) and "One Size" in available_sizes:
      matched_size = "One Size"
    elif size_upper in normalized_avail:
      matched_size = normalized_avail[size_upper]
    else:
      return _with_envelope({
          "status": "error",
          "error": (
              f"Size '{req_size}' for '{matched_entry['item']}' is out of "
              "stock in the merchandise catalog."
          ),
          "store_note": store_note,
          "item": matched_entry["item"],
          "in_stock": False,
          "requested_size": req_size,
          "available_sizes": available_sizes,
          "official_store_url": official_store_url,
          "agent_action": (
              f"Let the user know that size '{req_size}' is out of stock, "
              f"share the available sizes ({', '.join(available_sizes)}), and "
              "point them to https://shop.mercedesamgf1.com/ for official "
              "store purchases."
          ),
      })
  else:
    matched_size = available_sizes[0] if available_sizes else "One Size"

  return _with_envelope({
      "status": "success",
      "store_note": store_note,
      "item": matched_entry["item"],
      "in_stock": True,
      "requested_size": req_size or matched_size,
      "available_sizes": available_sizes,
      "official_store_url": official_store_url,
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
