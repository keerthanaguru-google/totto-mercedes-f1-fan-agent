"""Tool for retrieving verified official Formula 1 ticketing and Mercedes F1 links."""

from typing import Any


def get_official_links(category: str = "all") -> dict[str, Any]:
  """Retrieves verified official links for F1 tickets and Mercedes-AMG PETRONAS F1.

  Provides canonical official URLs and spoken-friendly guidance for Formula 1
  ticketing, the official Mercedes-AMG PETRONAS F1 store, the official team
  website, fan club resources, and official social media channels.

  Args:
    category: Link category to retrieve ("tickets", "merch", "team", "social",
      "fan", or "all"). Defaults to "all".

  Returns:
    A dictionary containing the requested official link(s), spoken guidance,
    and agent_action instructions on unrecognized categories.
  """
  links_catalog: dict[str, dict[str, Any]] = {
      "tickets": {
          "title": "Official Formula 1 Ticketing Destination",
          "url": "https://www.formula1.com/en/tickets",
          "spoken_domain": "formula1.com/en/tickets",
          "non_transactional_notice": (
              "Totto cannot sell, reserve, price, or check live seat inventory "
              "for Formula 1 tickets directly."
          ),
          "guidance": (
              "Direct the user to https://www.formula1.com/en/tickets for "
              "verified Grand Prix grandstand and hospitality packages without "
              "quoting prices or claiming seat availability."
          ),
      },
      "merch": {
          "title": "Official Mercedes-AMG PETRONAS F1 Team Store",
          "url": "https://shop.mercedesamgf1.com/",
          "spoken_domain": "shop.mercedesamgf1.com",
          "guidance": (
              "Direct the user to https://shop.mercedesamgf1.com/ to browse "
              "and purchase authentic Mercedes-AMG PETRONAS F1 teamwear, "
              "George Russell #63 gear, and Kimi Antonelli #12 merchandise."
          ),
      },
      "team": {
          "title": "Official Mercedes-AMG PETRONAS Formula One Team Website",
          "url": "https://www.mercedesamgf1.com/",
          "spoken_domain": "mercedesamgf1.com",
          "guidance": (
              "Share https://www.mercedesamgf1.com/ for official team news, "
              "W17 technical features, driver profiles, and Brackley updates."
          ),
      },
      "social": {
          "title": "Official Mercedes-AMG PETRONAS F1 Social Channels",
          "url": "https://www.mercedesamgf1.com/",
          "channels": {
              "instagram": "https://www.instagram.com/mercedesamgf1/",
              "x_twitter": "https://x.com/MercedesAMGF1",
              "youtube": "https://www.youtube.com/@MercedesAMGF1",
          },
          "guidance": (
              "Share the official @MercedesAMGF1 channels on Instagram, X, and "
              "YouTube for behind-the-scenes Silver Arrows race weekend content."
          ),
      },
      "fan": {
          "title": "Official Mercedes-AMG PETRONAS F1 Fan Club & Community",
          "url": "https://www.mercedesamgf1.com/fans",
          "spoken_domain": "mercedesamgf1.com/fans",
          "guidance": (
              "Direct fans to https://www.mercedesamgf1.com/fans for official "
              "Silver Arrows fan experiences, wallpapers, and community updates."
          ),
      },
  }

  aliases: dict[str, str] = {
      "tickets": "tickets",
      "ticket": "tickets",
      "ticketing": "tickets",
      "f1_tickets": "tickets",
      "grandstand": "tickets",
      "hospitality": "tickets",
      "merch": "merch",
      "merchandise": "merch",
      "store": "merch",
      "shop": "merch",
      "gear": "merch",
      "team": "team",
      "website": "team",
      "mercedes": "team",
      "official": "team",
      "social": "social",
      "socials": "social",
      "instagram": "social",
      "youtube": "social",
      "twitter": "social",
      "fan": "fan",
      "fans": "fan",
      "community": "fan",
      "all": "all",
  }

  valid_categories = ["tickets", "merch", "team", "social", "fan", "all"]
  raw_cat = ((category or "").strip() or "all").lower().replace(" ", "_")
  canonical = aliases.get(raw_cat, "")

  if not canonical:
    return _with_envelope({
        "status": "error",
        "error": (
            f"Unsupported link category '{category}'. Valid categories are "
            "'tickets', 'merch', 'team', 'social', 'fan', or 'all'."
        ),
        "valid_categories": valid_categories,
        "agent_action": (
            "Inform the user that only official Formula 1 ticketing, Mercedes "
            "F1 merch store, team website, fan club, and social media links "
            "are available, and offer to share any of those verified URLs."
        ),
    })

  if canonical == "all":
    primary = {
        "title": "All Official Mercedes-AMG PETRONAS F1 & F1 Ticketing Links",
        "url": "https://www.mercedesamgf1.com/",
        "tickets_url": "https://www.formula1.com/en/tickets",
        "merch_url": "https://shop.mercedesamgf1.com/",
        "team_url": "https://www.mercedesamgf1.com/",
        "fan_url": "https://www.mercedesamgf1.com/fans",
        "guidance": (
            "Use https://www.formula1.com/en/tickets for official F1 race "
            "tickets, https://shop.mercedesamgf1.com/ for official Mercedes "
            "merch, and https://www.mercedesamgf1.com/ for team news."
        ),
    }
    return _with_envelope({
        "status": "success",
        "category": "all",
        "url": primary["url"],
        "tickets_url": primary["tickets_url"],
        "merch_url": primary["merch_url"],
        "team_url": primary["team_url"],
        "guidance": primary["guidance"],
        "links": links_catalog,
        "result": primary,
    })

  selected = dict(links_catalog[canonical])
  return _with_envelope({
      "status": "success",
      "category": canonical,
      "title": selected["title"],
      "url": selected["url"],
      "guidance": selected["guidance"],
      "links": {canonical: selected},
      "result": selected,
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
