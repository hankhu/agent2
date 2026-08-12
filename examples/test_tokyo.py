"""Test script: Fetch Tokyo's population and area using get_city_population and get_city_area.

Both tools query the Wikidata SPARQL endpoint (P1082=population, P2046=area in km²).
"""

import asyncio
import httpx

from agent2.tools import tool

WIKIDATA_SPARQL_URL = "https://query.wikidata.org/sparql"
HEADERS = {"User-Agent": "agent2-test/1.0 (https://github.com/agent2)", "Accept": "application/sparql-results+json"}


@tool
async def get_city_population(city: str) -> str:
    """Get the population of a city from Wikidata (property P1082)."""
    sparql = f"""
    SELECT ?population WHERE {{
      ?entity rdfs:label "{city}"@en.
      ?entity wdt:P1082 ?population.
    }} ORDER BY DESC(?population) LIMIT 1
    """
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            response = await client.get(
                WIKIDATA_SPARQL_URL,
                params={"query": sparql, "format": "json"},
                headers=HEADERS,
            )
            response.raise_for_status()
            data = response.json()
            bindings = data.get("results", {}).get("bindings", [])
            if bindings:
                pop = int(float(bindings[0]["population"]["value"]))
                return f"The population of {city} is {pop:,}."
            return f"Population data for {city} was not found on Wikidata."
        except Exception as e:
            return f"Error fetching population for {city}: {str(e)}"


@tool
async def get_city_area(city: str) -> str:
    """Get the area of a city in sq km from Wikidata (property P2046)."""
    sparql = f"""
    SELECT ?area WHERE {{
      ?entity rdfs:label "{city}"@en.
      ?entity wdt:P2046 ?area.
    }} ORDER BY DESC(?area) LIMIT 1
    """
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            response = await client.get(
                WIKIDATA_SPARQL_URL,
                params={"query": sparql, "format": "json"},
                headers=HEADERS,
            )
            response.raise_for_status()
            data = response.json()
            bindings = data.get("results", {}).get("bindings", [])
            if bindings:
                area_km2 = round(float(bindings[0]["area"]["value"]), 2)
                return f"The area of {city} is approximately {area_km2:,} sq km."
            return f"Area data for {city} was not found on Wikidata."
        except Exception as e:
            return f"Error fetching area for {city}: {str(e)}"


async def main():
    city = "Tokyo"
    print(f"=== Fetching data for {city} ===\n")

    print("▶ Calling get_city_population...")
    pop_result = await get_city_population(city=city)
    print(f"  Population: {pop_result}\n")

    print("▶ Calling get_city_area...")
    area_result = await get_city_area(city=city)
    print(f"  Area:       {area_result}\n")

    print("=== Done ===")


if __name__ == "__main__":
    asyncio.run(main())
