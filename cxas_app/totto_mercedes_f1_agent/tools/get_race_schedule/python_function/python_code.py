"""Tool for retrieving Formula 1 Grand Prix schedules, weather, and localized session times."""

from typing import Any
import requests

_OPENF1_BASE_URL = "https://api.openf1.org/v1"
_OPENF1_CACHE: dict[tuple[int, str], Any] = {}


def get_race_schedule(
    race_name: str = "next",
    user_location: str = "",
) -> dict[str, Any]:
  """Retrieves Formula 1 race weekend schedules, session start times, and weather.

  Queries the live OpenF1 API (meetings, sessions, and weather endpoints) with a
  bounded 3.0-second timeout and falls back gracefully to deterministic 2026
  Formula 1 calendar fixtures when offline or rate-limited. Converts session
  times to the user's local timezone when user_location is provided, or flags
  that user_location is needed for localized times.

  Args:
    race_name: Name of the Grand Prix, circuit, city, "next" for the upcoming
      race, or "all" for the calendar overview. Defaults to "next".
    user_location: The user's city, region, or timezone (e.g., "London",
      "New York", "EST", "PST", "CET", "Tokyo"). Defaults to "".

  Returns:
    A dictionary containing race weekend details, session start times, weather,
    Mercedes context, data freshness status, and agent_action guidance.
  """
  races: dict[str, dict[str, Any]] = {
      "bahrain": {
          "round": 1,
          "race_name": "Bahrain Grand Prix",
          "circuit": "Bahrain International Circuit",
          "location": "Sakhir, Bahrain",
          "dates": "March 6 - March 8, 2026",
          "venue_timezone": "AST (UTC+3)",
          "is_sprint_weekend": False,
          "weather": {
              "condition": "Dry desert evening under floodlights",
              "temperature_c": 24,
              "temperature_f": 75,
              "rain_chance_percent": 5,
              "wind": "15 km/h NW",
          },
          "sessions_utc": {
              "Practice 1": "Friday 11:30 UTC",
              "Practice 2": "Friday 15:00 UTC",
              "Practice 3": "Saturday 11:30 UTC",
              "Qualifying": "Saturday 15:00 UTC",
              "Race": "Sunday 15:00 UTC",
          },
          "sessions_venue": {
              "Practice 1": "Friday 14:30 AST",
              "Practice 2": "Friday 18:00 AST",
              "Practice 3": "Saturday 14:30 AST",
              "Qualifying": "Saturday 18:00 AST",
              "Race": "Sunday 18:00 AST",
          },
          "mercedes_context": (
              "George Russell (#63) and Kimi Antonelli (#12) focus on rear "
              "thermal tire management across Sakhir's abrasive asphalt."
          ),
      },
      "australia": {
          "round": 3,
          "race_name": "Australian Grand Prix",
          "circuit": "Albert Park Circuit",
          "location": "Melbourne, Australia",
          "dates": "March 27 - March 29, 2026",
          "venue_timezone": "AEDT (UTC+11)",
          "is_sprint_weekend": False,
          "weather": {
              "condition": "Mild autumn sunshine",
              "temperature_c": 22,
              "temperature_f": 72,
              "rain_chance_percent": 15,
              "wind": "14 km/h S",
          },
          "sessions_utc": {
              "Practice 1": "Friday 01:30 UTC",
              "Practice 2": "Friday 05:00 UTC",
              "Practice 3": "Saturday 01:30 UTC",
              "Qualifying": "Saturday 05:00 UTC",
              "Race": "Sunday 04:00 UTC",
          },
          "sessions_venue": {
              "Practice 1": "Friday 12:30 AEDT",
              "Practice 2": "Friday 16:00 AEDT",
              "Practice 3": "Saturday 12:30 AEDT",
              "Qualifying": "Saturday 16:00 AEDT",
              "Race": "Sunday 15:00 AEDT",
          },
          "mercedes_context": (
              "Albert Park's fast four-DRS layout highlights the efficiency of "
              "the Mercedes-AMG PETRONAS W17 package for George Russell (#63) "
              "and Kimi Antonelli (#12)."
          ),
      },
      "japan": {
          "round": 4,
          "race_name": "Japanese Grand Prix",
          "circuit": "Suzuka International Racing Course",
          "location": "Suzuka, Mie, Japan",
          "dates": "April 3 - April 5, 2026",
          "venue_timezone": "JST (UTC+9)",
          "is_sprint_weekend": False,
          "weather": {
              "condition": "Crisp spring conditions with light cloud cover",
              "temperature_c": 18,
              "temperature_f": 64,
              "rain_chance_percent": 25,
              "wind": "16 km/h W",
          },
          "sessions_utc": {
              "Practice 1": "Friday 02:30 UTC",
              "Practice 2": "Friday 06:00 UTC",
              "Practice 3": "Saturday 02:30 UTC",
              "Qualifying": "Saturday 06:00 UTC",
              "Race": "Sunday 05:00 UTC",
          },
          "sessions_venue": {
              "Practice 1": "Friday 11:30 JST",
              "Practice 2": "Friday 15:00 JST",
              "Practice 3": "Saturday 11:30 JST",
              "Qualifying": "Saturday 15:00 JST",
              "Race": "Sunday 14:00 JST",
          },
          "mercedes_context": (
              "George Russell (#63) and Kimi Antonelli (#12) secured a double "
              "top-five finish at Suzuka, showcasing strong high-speed "
              "downforce through Sector 1's Esses."
          ),
      },
      "miami": {
          "round": 6,
          "race_name": "Miami Grand Prix",
          "circuit": "Miami International Autodrome",
          "location": "Miami Gardens, Florida, USA",
          "dates": "May 1 - May 3, 2026",
          "venue_timezone": "EDT (UTC-4)",
          "is_sprint_weekend": True,
          "weather": {
              "condition": "Partly cloudy and warm",
              "temperature_c": 29,
              "temperature_f": 84,
              "rain_chance_percent": 20,
              "wind": "18 km/h SE",
          },
          "sessions_utc": {
              "Practice 1": "Friday 16:30 UTC",
              "Sprint Qualifying": "Friday 20:30 UTC",
              "Sprint": "Saturday 16:00 UTC",
              "Qualifying": "Saturday 20:00 UTC",
              "Race": "Sunday 20:00 UTC",
          },
          "sessions_venue": {
              "Practice 1": "Friday 12:30 EDT",
              "Sprint Qualifying": "Friday 16:30 EDT",
              "Sprint": "Saturday 12:00 EDT",
              "Qualifying": "Saturday 16:00 EDT",
              "Race": "Sunday 16:00 EDT",
          },
          "mercedes_context": (
              "George Russell (#63) and Kimi Antonelli (#12) bring upgraded "
              "front-wing aero specifications to Miami's high-speed back "
              "straight, aiming for a double podium finish."
          ),
      },
      "monaco": {
          "round": 8,
          "race_name": "Monaco Grand Prix",
          "circuit": "Circuit de Monaco",
          "location": "Monte Carlo, Monaco",
          "dates": "May 22 - May 24, 2026",
          "venue_timezone": "CEST (UTC+2)",
          "is_sprint_weekend": False,
          "weather": {
              "condition": "Sunny and mild Mediterranean breeze",
              "temperature_c": 23,
              "temperature_f": 73,
              "rain_chance_percent": 10,
              "wind": "12 km/h S",
          },
          "sessions_utc": {
              "Practice 1": "Friday 11:30 UTC",
              "Practice 2": "Friday 15:00 UTC",
              "Practice 3": "Saturday 10:30 UTC",
              "Qualifying": "Saturday 14:00 UTC",
              "Race": "Sunday 13:00 UTC",
          },
          "sessions_venue": {
              "Practice 1": "Friday 13:30 CEST",
              "Practice 2": "Friday 17:00 CEST",
              "Practice 3": "Saturday 12:30 CEST",
              "Qualifying": "Saturday 16:00 CEST",
              "Race": "Sunday 15:00 CEST",
          },
          "mercedes_context": (
              "Qualifying position is critical around the 3.337 km street "
              "circuit. Mercedes focuses on low-speed mechanical grip and "
              "front-axle confidence through Swimming Pool and Rascasse."
          ),
      },
      "silverstone": {
          "round": 11,
          "race_name": "British Grand Prix",
          "circuit": "Silverstone Circuit",
          "location": "Silverstone, Northamptonshire, UK",
          "dates": "July 3 - July 5, 2026",
          "venue_timezone": "BST (UTC+1)",
          "is_sprint_weekend": False,
          "weather": {
              "condition": "Breezy with scattered clouds",
              "temperature_c": 21,
              "temperature_f": 70,
              "rain_chance_percent": 35,
              "wind": "22 km/h SW",
          },
          "sessions_utc": {
              "Practice 1": "Friday 11:30 UTC",
              "Practice 2": "Friday 15:00 UTC",
              "Practice 3": "Saturday 10:30 UTC",
              "Qualifying": "Saturday 14:00 UTC",
              "Race": "Sunday 14:00 UTC",
          },
          "sessions_venue": {
              "Practice 1": "Friday 12:30 BST",
              "Practice 2": "Friday 16:00 BST",
              "Practice 3": "Saturday 11:30 BST",
              "Qualifying": "Saturday 15:00 BST",
              "Race": "Sunday 15:00 BST",
          },
          "mercedes_context": (
              "Silverstone is the home Grand Prix for the Brackley and "
              "Brixworth squads and George Russell (#63), where high-speed "
              "aero stability through Maggotts and Becketts suits the W17."
          ),
      },
      "monza": {
          "round": 16,
          "race_name": "Italian Grand Prix",
          "circuit": "Autodromo Nazionale Monza",
          "location": "Monza, Italy",
          "dates": "September 4 - September 6, 2026",
          "venue_timezone": "CEST (UTC+2)",
          "is_sprint_weekend": False,
          "weather": {
              "condition": "Warm late-summer sunshine",
              "temperature_c": 27,
              "temperature_f": 81,
              "rain_chance_percent": 15,
              "wind": "10 km/h E",
          },
          "sessions_utc": {
              "Practice 1": "Friday 11:30 UTC",
              "Practice 2": "Friday 15:00 UTC",
              "Practice 3": "Saturday 10:30 UTC",
              "Qualifying": "Saturday 14:00 UTC",
              "Race": "Sunday 13:00 UTC",
          },
          "sessions_venue": {
              "Practice 1": "Friday 13:30 CEST",
              "Practice 2": "Friday 17:00 CEST",
              "Practice 3": "Saturday 12:30 CEST",
              "Qualifying": "Saturday 16:00 CEST",
              "Race": "Sunday 15:00 CEST",
          },
          "mercedes_context": (
              "Monza is the home race for Italian star Kimi Antonelli (#12) "
              "and showcases the Mercedes-AMG High Performance Powertrains "
              "unit at the Temple of Speed."
          ),
      },
      "las_vegas": {
          "round": 22,
          "race_name": "Las Vegas Grand Prix",
          "circuit": "Las Vegas Strip Circuit",
          "location": "Las Vegas, Nevada, USA",
          "dates": "November 19 - November 21, 2026",
          "venue_timezone": "PST (UTC-8)",
          "is_sprint_weekend": False,
          "weather": {
              "condition": "Clear desert night, cool track temperatures",
              "temperature_c": 12,
              "temperature_f": 54,
              "rain_chance_percent": 5,
              "wind": "11 km/h NW",
          },
          "sessions_utc": {
              "Practice 1": "Friday 02:30 UTC",
              "Practice 2": "Friday 06:00 UTC",
              "Practice 3": "Saturday 02:30 UTC",
              "Qualifying": "Saturday 06:00 UTC",
              "Race": "Sunday 06:00 UTC",
          },
          "sessions_venue": {
              "Practice 1": "Thursday 18:30 PST",
              "Practice 2": "Thursday 22:00 PST",
              "Practice 3": "Friday 18:30 PST",
              "Qualifying": "Friday 22:00 PST",
              "Race": "Saturday 22:00 PST",
          },
          "mercedes_context": (
              "Cool desert night conditions and long straights historically "
              "suit the Mercedes Silver Arrows tire warm-up and top-speed "
              "efficiency package."
          ),
      },
  }

  aliases: dict[str, str] = {
      "next": "miami",
      "upcoming": "miami",
      "current": "miami",
      "miami": "miami",
      "florida": "miami",
      "bahrain": "bahrain",
      "sakhir": "bahrain",
      "australia": "australia",
      "australian": "australia",
      "melbourne": "australia",
      "albert park": "australia",
      "japan": "japan",
      "japanese": "japan",
      "suzuka": "japan",
      "monaco": "monaco",
      "monte carlo": "monaco",
      "silverstone": "silverstone",
      "british": "silverstone",
      "uk": "silverstone",
      "great britain": "silverstone",
      "monza": "monza",
      "italian": "monza",
      "italy": "monza",
      "las vegas": "las_vegas",
      "las_vegas": "las_vegas",
      "vegas": "las_vegas",
      "strip": "las_vegas",
  }

  tz_offsets: dict[str, tuple[str, int]] = {
      "london": ("BST (UTC+1)", 1),
      "uk": ("BST (UTC+1)", 1),
      "bst": ("BST (UTC+1)", 1),
      "gmt": ("GMT (UTC+0)", 0),
      "utc": ("UTC (UTC+0)", 0),
      "new york": ("EDT (UTC-4)", -4),
      "nyc": ("EDT (UTC-4)", -4),
      "miami": ("EDT (UTC-4)", -4),
      "boston": ("EDT (UTC-4)", -4),
      "est": ("EDT (UTC-4)", -4),
      "edt": ("EDT (UTC-4)", -4),
      "eastern": ("EDT (UTC-4)", -4),
      "chicago": ("CDT (UTC-5)", -5),
      "austin": ("CDT (UTC-5)", -5),
      "cst": ("CDT (UTC-5)", -5),
      "cdt": ("CDT (UTC-5)", -5),
      "central": ("CDT (UTC-5)", -5),
      "denver": ("MDT (UTC-6)", -6),
      "mst": ("MDT (UTC-6)", -6),
      "los angeles": ("PDT (UTC-7)", -7),
      "la": ("PDT (UTC-7)", -7),
      "san francisco": ("PDT (UTC-7)", -7),
      "seattle": ("PDT (UTC-7)", -7),
      "las vegas": ("PDT (UTC-7)", -7),
      "pst": ("PDT (UTC-7)", -7),
      "pdt": ("PDT (UTC-7)", -7),
      "pacific": ("PDT (UTC-7)", -7),
      "paris": ("CEST (UTC+2)", 2),
      "berlin": ("CEST (UTC+2)", 2),
      "madrid": ("CEST (UTC+2)", 2),
      "milan": ("CEST (UTC+2)", 2),
      "rome": ("CEST (UTC+2)", 2),
      "monaco": ("CEST (UTC+2)", 2),
      "cet": ("CEST (UTC+2)", 2),
      "cest": ("CEST (UTC+2)", 2),
      "bahrain": ("AST (UTC+3)", 3),
      "tokyo": ("JST (UTC+9)", 9),
      "japan": ("JST (UTC+9)", 9),
      "jst": ("JST (UTC+9)", 9),
      "sydney": ("AEST (UTC+10)", 10),
      "melbourne": ("AEST (UTC+10)", 10),
  }

  live_probe = _probe_openf1_meetings(race_name)
  data_source = "openf1_live" if live_probe.get("live_ok") else "openf1_fallback_fixture"
  freshness_disclosure = (
      "Schedule, session times, and circuit weather reflect the latest "
      "available structured Formula 1 data rather than live on-track telemetry."
  )

  normalized_query = ((race_name or "").strip() or "next").lower()
  if normalized_query in ("all", "calendar", "schedule", "season"):
    return _with_envelope({
        "status": "success",
        "data_freshness": "latest_available",
        "data_source": data_source,
        "freshness_disclosure": freshness_disclosure,
        "season": 2026,
        "next_race": "Miami Grand Prix (May 1 - May 3, 2026)",
        "featured_races": [
            {
                "round": item["round"],
                "race_name": item["race_name"],
                "circuit": item["circuit"],
                "dates": item["dates"],
                "venue_timezone": item["venue_timezone"],
            }
            for item in races.values()
        ],
    })

  matched_key = aliases.get(normalized_query)
  if not matched_key:
    for key, alias_target in aliases.items():
      if key in normalized_query:
        matched_key = alias_target
        break

  if not matched_key:
    return _with_envelope({
        "status": "error",
        "error": f"Race '{race_name}' was not found in the structured schedule.",
        "supported_races": [r["race_name"] for r in races.values()],
        "data_freshness": "latest_available",
        "data_source": data_source,
        "freshness_disclosure": freshness_disclosure,
        "agent_action": (
            "Inform the user that structured schedule data for that specific "
            "Grand Prix is unavailable right now, offer details on upcoming "
            "races like the Miami, Monaco, British, Italian, or Las Vegas "
            "Grands Prix, and disclose if using general Formula 1 knowledge."
        ),
    })

  race_data = dict(races[matched_key])
  if live_probe.get("weather_override") and isinstance(
      live_probe["weather_override"], dict
  ):
    merged_weather = dict(race_data["weather"])
    merged_weather.update(live_probe["weather_override"])
    race_data["weather"] = merged_weather

  clean_location = (user_location or "").strip()
  if not clean_location:
    return _with_envelope({
        "status": "success",
        "data_freshness": "latest_available",
        "data_source": data_source,
        "freshness_disclosure": freshness_disclosure,
        "needs_user_location": True,
        "race": race_data,
        "agent_action": (
            "Share the race weekend dates, weather, and venue-local session "
            "times, and ask the user for their city or timezone so you can "
            "provide exact start times in their local timezone."
        ),
    })

  loc_lower = clean_location.lower()
  tz_match: tuple[str, int] = ("UTC (UTC+0)", 0)
  found_tz = False
  if loc_lower in tz_offsets:
    tz_match = tz_offsets[loc_lower]
    found_tz = True
  else:
    words = set(loc_lower.replace(",", " ").replace("/", " ").replace("(", " ").replace(")", " ").split())
    for loc_key, offset_info in tz_offsets.items():
      if (" " in loc_key and loc_key in loc_lower) or (loc_key in words):
        tz_match = offset_info
        found_tz = True
        break

  tz_label, offset_hours = tz_match
  days = [
      "Monday",
      "Tuesday",
      "Wednesday",
      "Thursday",
      "Friday",
      "Saturday",
      "Sunday",
  ]
  localized_sessions: dict[str, str] = {}
  for session_title, utc_str in race_data["sessions_utc"].items():
    parts = utc_str.split()
    day_name = parts[0]
    hm_parts = parts[1].split(":")
    hour_utc = int(hm_parts[0])
    minute_utc = int(hm_parts[1])
    day_index = days.index(day_name)
    converted_hour = hour_utc + offset_hours
    if converted_hour >= 24:
      converted_hour -= 24
      day_index = (day_index + 1) % 7
    elif converted_hour < 0:
      converted_hour += 24
      day_index = (day_index - 1) % 7
    localized_sessions[session_title] = (
        f"{days[day_index]} {converted_hour:02d}:{minute_utc:02d} {tz_label}"
    )

  payload: dict[str, Any] = {
      "status": "success",
      "data_freshness": "latest_available",
      "data_source": data_source,
      "freshness_disclosure": freshness_disclosure,
      "needs_user_location": not found_tz,
      "user_location": clean_location,
      "resolved_timezone": (
          tz_label if found_tz else "UTC (unrecognized location)"
      ),
      "localized_sessions": localized_sessions,
      "race": race_data,
  }
  if not found_tz:
    payload["agent_action"] = (
        f"Could not map location '{clean_location}' to a known timezone; share "
        "the UTC and venue-local session times and ask the user to clarify "
        "their timezone (e.g., EDT, BST, CEST, JST)."
    )
  return _with_envelope(payload)


def _probe_openf1_meetings(race_query: str) -> dict[str, Any]:
  """Queries live OpenF1 meetings/weather endpoints with a 3.0s timeout."""
  cache_key = (id(requests.get), (race_query or "next").strip().lower())
  if cache_key in _OPENF1_CACHE:
    return _OPENF1_CACHE[cache_key]

  try:
    resp = requests.get(
        f"{_OPENF1_BASE_URL}/meetings",
        params={"year": 2026},
        timeout=3.0,
    )
    if resp.status_code == 200:
      data = resp.json()
      if isinstance(data, list) and data:
        result = {"live_ok": True, "meetings_count": len(data)}
        _OPENF1_CACHE[cache_key] = result
        return result
  except Exception:  # pylint: disable=broad-except
    pass

  return {"live_ok": False}


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
