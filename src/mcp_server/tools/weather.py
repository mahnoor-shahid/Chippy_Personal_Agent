"""Weather tool via Open-Meteo (free, no API key).

Geocodes a city name, then fetches current conditions + a short forecast.
"""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

# WMO weather interpretation codes -> human-readable conditions.
_WMO = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Rime fog",
    51: "Light drizzle",
    53: "Drizzle",
    55: "Heavy drizzle",
    61: "Light rain",
    63: "Rain",
    65: "Heavy rain",
    71: "Light snow",
    73: "Snow",
    75: "Heavy snow",
    80: "Rain showers",
    81: "Rain showers",
    82: "Violent rain showers",
    95: "Thunderstorm",
    96: "Thunderstorm w/ hail",
    99: "Thunderstorm w/ heavy hail",
}


def _conditions(code) -> str:
    return _WMO.get(code, f"Code {code}")


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    def get_weather(city: str) -> dict:
        """Get current weather and a 3-day forecast for a city.

        Args:
            city: City name, optionally "City, Country" to disambiguate.
        """
        import httpx

        geo = httpx.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": city, "count": 1},
            timeout=20,
        ).json()
        if not geo.get("results"):
            return {"error": f"Couldn't find a place called {city!r}."}
        loc = geo["results"][0]

        fc = httpx.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": loc["latitude"],
                "longitude": loc["longitude"],
                "current": "temperature_2m,weather_code,wind_speed_10m",
                "daily": "temperature_2m_max,temperature_2m_min,weather_code",
                "forecast_days": 3,
                "timezone": "auto",
            },
            timeout=20,
        ).json()

        cur = fc.get("current", {})
        daily = fc.get("daily", {})
        forecast = [
            {
                "date": d,
                "min_c": daily["temperature_2m_min"][i],
                "max_c": daily["temperature_2m_max"][i],
                "conditions": _conditions(daily["weather_code"][i]),
            }
            for i, d in enumerate(daily.get("time", []))
        ]

        return {
            "location": f"{loc['name']}, {loc.get('country', '')}".strip(", "),
            "current": {
                "temp_c": cur.get("temperature_2m"),
                "conditions": _conditions(cur.get("weather_code")),
                "wind_kmh": cur.get("wind_speed_10m"),
            },
            "forecast": forecast,
        }
