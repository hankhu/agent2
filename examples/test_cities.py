"""Test script: Fetch population and area for Tokyo, London, and New York using
get_city_population and get_city_area.

Data flow:
  1. Nominatim (OpenStreetMap) search → Wikidata QID (from extratags.wikidata)
  2. Wikidata wbgetentities → P1082 (population) / P2046 (area km²)

No API key required. Run with:
    uv run examples/test_cities.py
"""

import asyncio
import httpx

from agent2.tools import tool

NOMINATIM_URL  = "https://nominatim.openstreetmap.org/search"
WIKIDATA_API   = "https://www.wikidata.org/w/api.php"
NOMINATIM_HEADERS = {"User-Agent": "agent2-test/1.0"}
WIKIDATA_HEADERS  = {"User-Agent": "agent2-test/1.0"}


async def _get_wikidata_qid(client: httpx.AsyncClient, city: str) -> str | None:
    """Look up a city on Nominatim and return its Wikidata QID from extratags."""
    r = await client.get(NOMINATIM_URL, params={
        "q": city, "format": "json", "limit": 1,
        "addressdetails": 0, "extratags": 1,
    }, headers=NOMINATIM_HEADERS)
    results = r.json()
    if results:
        return results[0].get("extratags", {}).get("wikidata")
    return None


async def _wikidata_claims(client: httpx.AsyncClient, qid: str) -> dict:
    """Fetch property claims for a Wikidata entity via wbgetentities (no SPARQL)."""
    r = await client.get(WIKIDATA_API, params={
        "action": "wbgetentities", "ids": qid, "format": "json",
        "props": "claims", "languages": "en",
    }, headers=WIKIDATA_HEADERS)
    data = r.json()
    return data.get("entities", {}).get(qid, {}).get("claims", {})


@tool
async def get_city_population(city: str) -> str:
    """Get the population of a city: Nominatim → Wikidata QID → P1082 (population)."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            qid = await _get_wikidata_qid(client, city)
            if not qid:
                return f"Could not find a Wikidata QID for {city} via Nominatim."

            claims = await _wikidata_claims(client, qid)
            pop_claims = claims.get("P1082", [])
            if not pop_claims:
                return f"Population data (P1082) not found for {city} on Wikidata ({qid})."

            # Use the last (most recent) population claim
            last = pop_claims[-1]["mainsnak"]["datavalue"]["value"]
            pop = int(float(last["amount"]))
            return f"The population of {city} is {pop:,} (Wikidata {qid})."
        except Exception as e:
            return f"Error fetching population for {city}: {str(e)}"


@tool
async def get_city_area(city: str) -> str:
    """Get the area of a city in sq km: Nominatim → Wikidata QID → P2046 (area km²)."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            qid = await _get_wikidata_qid(client, city)
            if not qid:
                return f"Could not find a Wikidata QID for {city} via Nominatim."

            claims = await _wikidata_claims(client, qid)
            area_claims = claims.get("P2046", [])
            if not area_claims:
                return f"Area data (P2046) not found for {city} on Wikidata ({qid})."

            # First area claim (km²)
            val = area_claims[0]["mainsnak"]["datavalue"]["value"]
            area_km2 = round(float(val["amount"]), 2)
            return f"The area of {city} is approximately {area_km2:,} sq km (Wikidata {qid})."
        except Exception as e:
            return f"Error fetching area for {city}: {str(e)}"


async def main():
    cities = ["Tokyo", "London", "New York City"]
    for city in cities:
        print(f"=== {city} ===")
        pop_result  = await get_city_population(city=city)
        area_result = await get_city_area(city=city)
        print(f"  Population: {pop_result}")
        print(f"  Area:       {area_result}")
        print()


if __name__ == "__main__":
    asyncio.run(main())
