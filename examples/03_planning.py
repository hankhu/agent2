"""Example 03: Planning — Plan-and-Execute pattern.

Demonstrates:
- PlannerAgent that separates planning from execution
- Dynamic re-planning based on intermediate results
- Multi-step task decomposition

Usage:
    export AGENT2_OPENAI_API_KEY=sk-...
    uv run examples/03_planning.py
"""

import asyncio

from agent2.llm import create_llm
from agent2.agent import PlannerAgent
from agent2.tools.builtin import web_search, python_exec

from agent2.tools import tool
import httpx

NOMINATIM_URL    = "https://nominatim.openstreetmap.org/search"
WIKIDATA_API     = "https://www.wikidata.org/w/api.php"
NOMINATIM_HEADERS = {"User-Agent": "agent2-example/1.0"}
WIKIDATA_HEADERS  = {"User-Agent": "agent2-example/1.0"}


_QID_CACHE: dict[str, str | None] = {}
_CLAIMS_CACHE: dict[str, dict] = {}


async def _get_wikidata_qid(client: httpx.AsyncClient, city: str) -> str | None:
    """Look up a city on Nominatim and return its Wikidata QID from extratags (cached)."""
    if city in _QID_CACHE:
        return _QID_CACHE[city]

    r = await client.get(NOMINATIM_URL, params={
        "q": city, "format": "json", "limit": 1,
        "addressdetails": 0, "extratags": 1,
    }, headers=NOMINATIM_HEADERS)
    results = r.json()
    qid = results[0].get("extratags", {}).get("wikidata") if results else None
    _QID_CACHE[city] = qid
    return qid


async def _wikidata_claims(client: httpx.AsyncClient, qid: str) -> dict:
    """Fetch property claims for a Wikidata entity via wbgetentities (cached)."""
    if qid in _CLAIMS_CACHE:
        return _CLAIMS_CACHE[qid]

    r = await client.get(WIKIDATA_API, params={
        "action": "wbgetentities", "ids": qid, "format": "json",
        "props": "claims", "languages": "en",
    }, headers=WIKIDATA_HEADERS)
    data = r.json()
    claims = data.get("entities", {}).get(qid, {}).get("claims", {})
    _CLAIMS_CACHE[qid] = claims
    return claims


@tool
async def get_city_population(city: str) -> str:
    """Get the population of a city: Nominatim → Wikidata QID → P1082 (population)."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            qid = await _get_wikidata_qid(client, city)
            if not qid:
                return f"Could not find a Wikidata QID for {city} via Nominatim."

            claims = await _wikidata_claims(client, qid)
            pop_claims = claims.get("P1082", [])   # population
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
            area_claims = claims.get("P2046", [])  # area in km²
            if not area_claims:
                return f"Area data (P2046) not found for {city} on Wikidata ({qid})."

            # First area claim (km²)
            val = area_claims[0]["mainsnak"]["datavalue"]["value"]
            area_km2 = round(float(val["amount"]), 2)
            return f"The area of {city} is approximately {area_km2:,} sq km (Wikidata {qid})."
        except Exception as e:
            return f"Error fetching area for {city}: {str(e)}"

async def main():
    llm = create_llm("deepseek")

    agent = PlannerAgent(
        "Researcher",
        llm=llm,
        tools=[get_city_population, get_city_area],
        system_prompt=(
            "You are a helpful planning assistant. "
            "IMPORTANT: Before calling any tool, check the previous step results carefully. "
            "If the data for a city (population or area) was already retrieved in a previous step, "
            "reuse that value directly — do NOT call the tool again for the same city. "
            "Each city's population and area should be fetched at most once."
        ),
        enable_replan=True,
        max_step_iterations=3,
    )

    result = await agent.run(
        "Compare the population of Tokyo, New York, and London. "
        "Which city is the most densely populated? "
        "Show the calculations."
    )

    print("\n" + "=" * 60)
    print("RESULT:", result)


if __name__ == "__main__":
    asyncio.run(main())
