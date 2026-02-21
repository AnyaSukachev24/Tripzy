from typing import List, Dict, Any, Optional
import json
import os
from langchain_core.tools import tool
from langchain_community.tools import DuckDuckGoSearchRun
from dotenv import load_dotenv

load_dotenv()


# --- Shared: Pinecone Vector Store for RAG ---
_pinecone_index = None
_pinecone_client = None


def _get_pinecone_client_and_index():
    """Lazy-load Pinecone client and index for Integrated Inference."""
    global _pinecone_index, _pinecone_client
    if _pinecone_index is None:
        try:
            from pinecone import Pinecone

            api_key = os.getenv("PINECONE_API_KEY")
            if not api_key:
                return None, None

            _pinecone_client = Pinecone(api_key=api_key)
            index_name = os.getenv("PINECONE_INDEX_NAME", "tripzy")
            _pinecone_index = _pinecone_client.Index(index_name)
        except Exception as e:
            print(f"  [Warning] Failed to init Pinecone: {e}")
            return None, None
    return _pinecone_client, _pinecone_index


def _query_pinecone_inference(
    query: str, k: int = 5, namespace: str = "wikivoyage"
) -> List[Any]:
    """
    Queries Pinecone using the Inference API to generate the query embedding.
    """
    pc, index = _get_pinecone_client_and_index()
    if not pc or not index:
        return []

    try:
        # 1. Generate Query Embedding via Pinecone Inference
        embedding_response = pc.inference.embed(
            model="llama-text-embed-v2",
            inputs=[query],
            parameters={"input_type": "query", "truncate": "END"},
        )
        query_values = embedding_response[0]["values"]

        # 2. Query Index
        results = index.query(
            vector=query_values, top_k=k, include_metadata=True, namespace=namespace
        )
        return results["matches"]
    except Exception as e:
        print(f"  [Warning] Pinecone Inference Query failed: {e}")
        return []


# =====================================================================
# SHARED: Amadeus Client Helper (Rate Limited)
# =====================================================================
def _get_amadeus_client():
    """Get an authenticated, rate-limited Amadeus client."""
    try:
        from app.amadeus_rate_limiter import get_amadeus_client

        return get_amadeus_client()
    except Exception as e:
        print(f"  [Warning] Rate limiter module error: {e}")
        return None


# =====================================================================
# 1. WEB SEARCH (The Researcher's Eyes)
# =====================================================================
@tool
def web_search_tool(query: str) -> str:
    """
    Performs a web search using DuckDuckGo.
    Optimized for Wikivoyage if 'destination' is mentioned.
    """
    print(f"  [Tool] Searching Web: {query}")

    # Research Insight: Prefer Wikivoyage for travel data
    if "wikivoyage" not in query.lower() and "site:" not in query.lower():
        pass

    try:
        search = DuckDuckGoSearchRun()
        return search.invoke(query)
    except Exception as e:
        return f"Search failed: {str(e)}"


# =====================================================================
# 2. FLIGHT SEARCH — Multi-Source Aggregator
#    Sources: Amadeus API → Google Flights → Kiwi.com
# =====================================================================


def _search_amadeus_flights(
    origin: str, destination: str, departure_date: str, return_date: str, adults: int
) -> List[Dict]:
    """Source 1: Amadeus Self-Service API — structured, reliable, sandbox or prod."""
    from app.amadeus_rate_limiter import get_amadeus_client, amadeus_call

    amadeus = get_amadeus_client()
    if not amadeus:
        return []
    try:
        from amadeus import ResponseError

        params = {
            "originLocationCode": origin.upper()[:3],
            "destinationLocationCode": destination.upper()[:3],
            "departureDate": departure_date,
            "adults": adults,
            "max": 5,
        }
        if return_date:
            params["returnDate"] = return_date

        response = amadeus_call(amadeus.shopping.flight_offers_search.get, **params)
        results = []
        for offer in response.data[:5]:
            flight = {
                "source": "Amadeus",
                "type": "flight-offer",
                "id": offer.get("id"),
                "price": offer.get("price", {}),
                "itineraries": [],
                "validatingAirlineCodes": offer.get("validatingAirlineCodes", []),
            }
            for itin in offer.get("itineraries", []):
                segments = []
                for seg in itin.get("segments", []):
                    segments.append(
                        {
                            "departure": seg.get("departure", {}),
                            "arrival": seg.get("arrival", {}),
                            "carrierCode": seg.get("carrierCode", ""),
                            "number": seg.get("number", ""),
                            "duration": seg.get("duration", ""),
                        }
                    )
                flight["itineraries"].append(
                    {
                        "duration": itin.get("duration", ""),
                        "segments": segments,
                    }
                )
            results.append(flight)
        print(f"  [Amadeus] Returned {len(results)} flights")
        return results
    except Exception as e:
        print(f"  [Amadeus] Failed: {e}")
        try:
            print(f"  [Amadeus] Failed Params: {params}")
            if hasattr(e, "response"):
                if hasattr(e.response, "parsed") and isinstance(
                    e.response.parsed, dict
                ):
                    import json

                    print(
                        f"  [Amadeus] Error Details: {json.dumps(e.response.parsed, indent=2)}"
                    )
                elif hasattr(e.response, "body"):
                    print(f"  [Amadeus] Error Body: {e.response.body}")
        except:
            pass
        return []


def _search_google_flights(
    origin: str, destination: str, departure_date: str, return_date: str, adults: int
) -> List[Dict]:
    """Source 2: Google Flights via fast_flights library (scraper)."""
    try:
        from fast_flights import FlightData, Passengers, get_flights

        flight_data_list = [
            FlightData(
                date=departure_date,
                from_airport=origin.upper()[:3],
                to_airport=destination.upper()[:3],
            )
        ]
        if return_date:
            flight_data_list.append(
                FlightData(
                    date=return_date,
                    from_airport=destination.upper()[:3],
                    to_airport=origin.upper()[:3],
                )
            )

        passengers = Passengers(adults=adults)
        trip_type = "round-trip" if return_date else "one-way"
        raw = get_flights(
            flight_data=flight_data_list,
            trip=trip_type,
            passengers=passengers,
            seat="economy",
        )

        results = []
        flights_list = (
            raw.flights
            if hasattr(raw, "flights")
            else (raw if isinstance(raw, list) else [])
        )

        for i, f in enumerate(flights_list[:5]):
            # Normalize to our standard format
            price_str = ""
            if hasattr(f, "price"):
                price_str = str(f.price).replace("$", "").replace(",", "").strip()
            elif isinstance(f, dict) and "price" in f:
                price_str = str(f["price"]).replace("$", "").replace(",", "").strip()

            price_val = 0.0
            try:
                price_val = float(price_str) if price_str else 0.0
            except ValueError:
                pass

            # Build segments from flight legs
            segments = []
            departure_info = {
                "iataCode": origin.upper()[:3],
                "at": f"{departure_date}T08:00:00",
            }
            arrival_info = {
                "iataCode": destination.upper()[:3],
                "at": f"{departure_date}T12:00:00",
            }

            if hasattr(f, "departure") and f.departure:
                departure_info["at"] = str(f.departure)
            if hasattr(f, "arrival") and f.arrival:
                arrival_info["at"] = str(f.arrival)

            duration_str = ""
            if hasattr(f, "duration"):
                duration_str = str(f.duration)
            elif isinstance(f, dict) and "duration" in f:
                duration_str = str(f["duration"])

            airline = ""
            if hasattr(f, "airline"):
                airline = str(f.airline)
            elif isinstance(f, dict) and "airline" in f:
                airline = str(f["airline"])

            segments.append(
                {
                    "departure": departure_info,
                    "arrival": arrival_info,
                    "carrierCode": airline[:2].upper() if airline else "GF",
                    "number": "",
                    "duration": duration_str,
                }
            )

            flight_info = {
                "source": "Google Flights",
                "type": "flight-offer",
                "id": f"gf-{i+1}",
                "price": {
                    "currency": "USD",
                    "total": f"{price_val:.2f}",
                    "grandTotal": f"{price_val:.2f}",
                },
                "itineraries": [{"duration": duration_str, "segments": segments}],
                "validatingAirlineCodes": [airline[:2].upper()] if airline else [],
                "airline_name": airline,
            }
            results.append(flight_info)

        print(f"  [Google Flights] Returned {len(results)} flights")
        return results
    except Exception as e:
        print(f"  [Google Flights] Failed: {e}")
        return []


def _search_kiwi_flights(
    origin: str, destination: str, departure_date: str, return_date: str, adults: int
) -> List[Dict]:
    """Source 3: Kiwi.com via Tequila public search API."""
    try:
        import httpx

        # Kiwi Tequila API — requires apikey header
        kiwi_api_key = os.getenv("KIWI_API_KEY", "")
        if not kiwi_api_key:
            print("  [Kiwi.com] KIWI_API_KEY not set, skipping")
            return []

        parts = departure_date.split("-")
        date_from = (
            f"{parts[2]}/{parts[1]}/{parts[0]}" if len(parts) == 3 else departure_date
        )

        params = {
            "fly_from": origin.upper()[:3],
            "fly_to": destination.upper()[:3],
            "date_from": date_from,
            "date_to": date_from,
            "adults": adults,
            "curr": "USD",
            "limit": 5,
        }
        if return_date:
            rparts = return_date.split("-")
            ret_fmt = (
                f"{rparts[2]}/{rparts[1]}/{rparts[0]}"
                if len(rparts) == 3
                else return_date
            )
            params["return_from"] = ret_fmt
            params["return_to"] = ret_fmt
            params["flight_type"] = "round"
        else:
            params["flight_type"] = "oneway"

        response = httpx.get(
            "https://api.tequila.kiwi.com/v2/search",
            params=params,
            timeout=15.0,
            headers={"Accept": "application/json", "apikey": kiwi_api_key},
        )

        if response.status_code != 200:
            print(f"  [Kiwi.com] HTTP {response.status_code}: {response.text[:200]}")
            return []

        data = response.json()
        kiwi_flights = data.get("data", [])
        if not kiwi_flights:
            print("  [Kiwi.com] No results")
            return []

        results = []
        for i, kf in enumerate(kiwi_flights[:5]):
            price_val = float(kf.get("price", 0))
            airlines = kf.get("airlines", [])
            airline_code = airlines[0] if airlines else ""

            # Build segments from route
            segments = []
            for route in kf.get("route", []):
                segments.append(
                    {
                        "departure": {
                            "iataCode": route.get("flyFrom", ""),
                            "at": route.get("local_departure", ""),
                        },
                        "arrival": {
                            "iataCode": route.get("flyTo", ""),
                            "at": route.get("local_arrival", ""),
                        },
                        "carrierCode": route.get("airline", ""),
                        "number": str(route.get("flight_no", "")),
                        "duration": "",
                    }
                )

            # Duration in hours/mins
            dur_secs = (
                kf.get("duration", {}).get("total", 0)
                if isinstance(kf.get("duration"), dict)
                else 0
            )
            dur_h = dur_secs // 3600
            dur_m = (dur_secs % 3600) // 60
            duration_str = f"PT{dur_h}H{dur_m}M" if dur_secs else ""

            flight_info = {
                "source": "Kiwi.com",
                "type": "flight-offer",
                "id": f"kiwi-{i+1}",
                "price": {
                    "currency": kf.get("currency", "USD"),
                    "total": f"{price_val:.2f}",
                    "grandTotal": f"{price_val:.2f}",
                },
                "itineraries": [{"duration": duration_str, "segments": segments}],
                "validatingAirlineCodes": airlines,
                "airline_name": ", ".join(airlines),
                "booking_link": kf.get("deep_link", ""),
            }
            results.append(flight_info)

        print(f"  [Kiwi.com] Returned {len(results)} flights")
        return results
    except Exception as e:
        print(f"  [Kiwi.com] Failed: {e}")
        return []


def _generate_mock_flights(
    origin: str, destination: str, departure_date: str, return_date: str, adults: int
) -> List[Dict]:
    """Fallback: realistic mock flight data when all APIs fail."""
    import random

    airlines = [
        {"name": "British Airways", "code": "BA"},
        {"name": "Air France", "code": "AF"},
        {"name": "EasyJet", "code": "U2"},
        {"name": "Ryanair", "code": "FR"},
        {"name": "Lufthansa", "code": "LH"},
        {"name": "KLM", "code": "KL"},
        {"name": "Emirates", "code": "EK"},
        {"name": "Turkish Airlines", "code": "TK"},
    ]
    base_price = random.randint(150, 600)

    mock_results = []
    for i in range(3):
        airline = random.choice(airlines)
        price = base_price + random.randint(-50, 100) * (i + 1)
        dep_hour = random.randint(6, 20)
        dur_h = random.randint(1, 12)
        dur_m = random.randint(0, 59)

        flight = {
            "source": "Mock",
            "type": "flight-offer",
            "id": f"mock-{i+1}",
            "itineraries": [
                {
                    "duration": f"PT{dur_h}H{dur_m}M",
                    "segments": [
                        {
                            "departure": {
                                "iataCode": origin.upper()[:3],
                                "at": f"{departure_date}T{dep_hour:02d}:00:00",
                            },
                            "arrival": {
                                "iataCode": destination.upper()[:3],
                                "at": f"{departure_date}T{(dep_hour + dur_h) % 24:02d}:{dur_m:02d}:00",
                            },
                            "carrierCode": airline["code"],
                            "number": str(random.randint(100, 9999)),
                            "duration": f"PT{dur_h}H{dur_m}M",
                        }
                    ],
                }
            ],
            "price": {
                "currency": "USD",
                "total": f"{price:.2f}",
                "base": f"{price * 0.85:.2f}",
                "grandTotal": f"{price:.2f}",
            },
            "validatingAirlineCodes": [airline["code"]],
            "airline_name": airline["name"],
        }
        if return_date:
            ret_h = random.randint(8, 21)
            flight["itineraries"].append(
                {
                    "duration": f"PT{dur_h}H{dur_m + 10}M",
                    "segments": [
                        {
                            "departure": {
                                "iataCode": destination.upper()[:3],
                                "at": f"{return_date}T{ret_h:02d}:00:00",
                            },
                            "arrival": {
                                "iataCode": origin.upper()[:3],
                                "at": f"{return_date}T{(ret_h + dur_h) % 24:02d}:{(dur_m + 10) % 60:02d}:00",
                            },
                            "carrierCode": airline["code"],
                            "number": str(random.randint(100, 9999)),
                            "duration": f"PT{dur_h}H{dur_m + 10}M",
                        }
                    ],
                }
            )
        mock_results.append(flight)
    return mock_results


def _get_flight_price_metrics(
    origin: str, destination: str, departure_date: str, currency: str = "USD"
) -> Dict:
    """Helper to fetch price metrics from Amadeus or return mock data."""
    try:
        # Try using the rate-limited client from shared module
        from app.amadeus_rate_limiter import get_amadeus_client, amadeus_call

        client = get_amadeus_client()
        if client:
            response = amadeus_call(
                client.analytics.itinerary_price_metrics.get,
                originIataCode=origin.upper()[:3],
                destinationIataCode=destination.upper()[:3],
                departureDate=departure_date,
                currencyCode=currency,
            )
            data = response.data
            if data:
                return {"source": "Amadeus", "metrics": data}
    except Exception as e:
        # If rate limiter module fails or other issue, try falling back or just log
        print(f"  [Warning] Price analysis failed: {e}")

    # Fallback / Mock
    return {
        "source": "Mock",
        "metrics": [
            {
                "departureDate": departure_date,
                "priceMetrics": [
                    {
                        "quartileRanking": "MINIMUM",
                        "amount": "120",
                        "currencyCode": currency,
                    },
                    {
                        "quartileRanking": "FIRST",
                        "amount": "180",
                        "currencyCode": currency,
                    },
                    {
                        "quartileRanking": "MEDIUM",
                        "amount": "250",
                        "currencyCode": currency,
                    },
                    {
                        "quartileRanking": "THIRD",
                        "amount": "350",
                        "currencyCode": currency,
                    },
                    {
                        "quartileRanking": "MAXIMUM",
                        "amount": "600",
                        "currencyCode": currency,
                    },
                ],
            }
        ],
    }


@tool
def search_flights_tool(
    origin: str,
    destination: str,
    departure_date: str,
    return_date: Optional[str] = None,
    adults: int = 1,
) -> str:
    """
    Searches for flights across multiple sources: Amadeus, Google Flights, and Kiwi.com.
    Returns aggregated results sorted by price from the best available sources.
    Inputs:
    - origin: IATA code or city name (e.g., "LON", "London")
    - destination: IATA code or city name (e.g., "PAR", "Paris")
    - departure_date: YYYY-MM-DD format
    - return_date: YYYY-MM-DD format (optional, for round trips)
    - adults: Number of adult passengers (default 1)
    """
    print(
        f"  [Tool] Multi-Source Flight Search: {origin} -> {destination} on {departure_date}"
        f" (Return: {return_date}, Adults: {adults})"
    )

    all_results = []

    # Query all sources (each handles its own errors)
    amadeus_flights = _search_amadeus_flights(
        origin, destination, departure_date, return_date, adults
    )
    all_results.extend(amadeus_flights)

    google_flights = _search_google_flights(
        origin, destination, departure_date, return_date, adults
    )
    all_results.extend(google_flights)

    kiwi_flights = _search_kiwi_flights(
        origin, destination, departure_date, return_date, adults
    )
    all_results.extend(kiwi_flights)

    # If no real data from any source, use mock fallback
    if not all_results:
        print("  [Tool] All flight sources failed, using mock data")
        all_results = _generate_mock_flights(
            origin, destination, departure_date, return_date, adults
        )

    # Sort by price (lowest first)
    def get_price(f):
        try:
            return float(f.get("price", {}).get("total", "99999"))
        except (ValueError, TypeError):
            return 99999

    all_results.sort(key=get_price)

    # Enrich with Price Analysis (Phase B1)
    try:
        price_analysis = _get_flight_price_metrics(origin, destination, departure_date)
        metrics = price_analysis.get("metrics", [])

        # Find metrics for the departure date
        relevant_metrics = next(
            (m for m in metrics if m.get("departureDate") == departure_date), None
        )

        if relevant_metrics:
            quartiles = {
                pm["quartileRanking"]: float(pm["amount"])
                for pm in relevant_metrics.get("priceMetrics", [])
            }
            min_price = quartiles.get("MINIMUM", 0)
            med_price = quartiles.get("MEDIUM", 0)
            max_price = quartiles.get("MAXIMUM", 0)

            for flight in all_results:
                try:
                    p_val = float(flight.get("price", {}).get("total", 0))
                    if p_val <= min_price * 1.05:
                        flight["deal_status"] = "GREAT DEAL"
                    elif p_val <= med_price:
                        flight["deal_status"] = "GOOD DEAL"
                    elif p_val <= max_price:
                        flight["deal_status"] = "FAIR"
                    else:
                        flight["deal_status"] = "PRICEY"

                    flight["price_context"] = f"Median is ${med_price}"
                except:
                    pass
    except Exception as e:
        print(f"  [Warning] Enrichment failed: {e}")

    # Summary
    sources = set(f.get("source", "Unknown") for f in all_results)
    print(f"  [Tool] Aggregated {len(all_results)} flights from: {', '.join(sources)}")
    return json.dumps(all_results, indent=2)


# =====================================================================
# 3. HOTEL SEARCH (Amadeus Integration + Smart Mock Fallback)
# =====================================================================


def _get_hotel_sentiments(hotel_ids: List[str]) -> Dict:
    """Helper to fetch hotel sentiments from Amadeus."""
    if not hotel_ids:
        return {"source": "None", "data": []}

    try:
        from app.amadeus_rate_limiter import get_amadeus_client, amadeus_call

        client = get_amadeus_client()
        if client:
            # Amadeus Sentiment API takes comma-separated IDs
            response = amadeus_call(
                client.e_reputation.hotel_sentiments.get,
                hotelIds=",".join(hotel_ids)[:2000],
            )
            data = response.data
            if data:
                return {"source": "Amadeus", "data": data}
    except Exception as e:
        print(f"  [Warning] Hotel sentiment analysis failed: {e}")

    # Fallback / Mock
    mock_data = []
    for h_id in hotel_ids:
        mock_data.append(
            {
                "hotelId": h_id,
                "overallRating": 85,
                "numberOfRatings": 120,
                "sentiments": {
                    "sleepQuality": 85,
                    "service": 80,
                    "facilities": 78,
                    "location": 90,
                    "valueForMoney": 75,
                },
                "source": "Mock",
            }
        )
    return {"source": "Mock", "data": mock_data}


@tool
def search_hotels_tool(
    city: str,
    check_in: str,
    check_out: str,
    budget: str = "medium",
    adults: int = 1,
    amenities: Optional[List[str]] = None,
    sort_by: str = "price",
) -> str:
    """
    Searches for hotels with real prices and availability for specific dates.
    Returns list of hotels with name, rating, price per night, amenities, and availability.
    Inputs:
    - city: City name or IATA code (e.g., "PAR", "Paris")
    - check_in: Check-in date in YYYY-MM-DD format
    - check_out: Check-out date in YYYY-MM-DD format
    - budget: Budget tier - "budget", "medium", or "luxury"
    - adults: Number of adult guests (default 1)
    - amenities: Optional list of required amenities (e.g., ["WIFI", "SPA", "PARKING"])
    - sort_by: Sort order - "price" (Cheapest first) or "rating" (Best rated first)
    """
    print(
        f"  [Tool] Searching Hotels: {city} ({check_in} to {check_out}) Budget={budget}, Sort={sort_by}"
    )

    from app.amadeus_rate_limiter import get_amadeus_client, amadeus_call

    amadeus = get_amadeus_client()

    # --- Real Amadeus API ---
    if amadeus:
        try:
            from amadeus import ResponseError

            budget_map = {"budget": "0-150", "medium": "150-400", "luxury": "400-2000"}
            price_range = budget_map.get(budget.lower(), "0-1000")

            # STEP 1: Find Hotel IDs with amenities filtering
            list_params = {"cityCode": city.upper()[-3:]}
            if amenities:
                list_params["amenities"] = ",".join(amenities).upper()

            hotel_list = amadeus_call(
                amadeus.reference_data.locations.hotels.by_city.get, **list_params
            )

            if not hotel_list.data:
                return json.dumps(
                    {
                        "error": f"No hotels found in {city} matching amenities: {amenities}",
                        "results": [],
                    }
                )

            # Step 1.5: Store hotel details for later enrichment
            hotel_details = {}
            for h in hotel_list.data:
                hotel_details[h["hotelId"]] = {
                    "geoCode": h.get("geoCode", {}),
                    "address": h.get("address", {}),
                    "rating": h.get(
                        "rating", None
                    ),  # Some endpoints might return it here
                }

            # Get top 20 IDs (Amadeus allows up to 20-50 depending on endpoint, limit to 20 to be safe)
            hotel_ids = [h["hotelId"] for h in hotel_list.data[:20]]

            # STEP 2: Get offers/prices for those IDs
            offers_response = amadeus_call(
                amadeus.shopping.hotel_offers_search.get,
                hotelIds=",".join(hotel_ids),
                adults=adults,
                checkInDate=check_in,
                checkOutDate=check_out,
                priceRange=price_range,
                currency="USD",
            )

            # STEP 3: Clean results
            results = []
            for offer in offers_response.data[:15]:  # Process more to allow sorting
                hid = offer["hotel"]["hotelId"]
                details = hotel_details.get(hid, {})

                # Try to get rating from offer or details
                rating = offer["hotel"].get("rating") or details.get("rating") or "N/A"

                # Format address
                addr_obj = details.get("address", {})
                address_str = ", ".join(
                    [line for line in addr_obj.get("lines", []) if line]
                    + [addr_obj.get("cityName", ""), addr_obj.get("countryCode", "")]
                )

                hotel_info = {
                    "name": offer["hotel"]["name"],
                    "hotelId": hid,
                    "rating": rating,
                    "location": {
                        "latitude": details.get("geoCode", {}).get("latitude"),
                        "longitude": details.get("geoCode", {}).get("longitude"),
                        "address": address_str.strip(", "),
                    },
                    "check_in": check_in,
                    "check_out": check_out,
                    "total_price": f"{offer['offers'][0]['price']['total']} {offer['offers'][0]['price']['currency']}",
                    "price_per_night": "N/A",
                    "description": offer["offers"][0]["room"]
                    .get("description", {})
                    .get("text", "No description"),
                    "amenities": offer["hotel"].get("amenities", []),
                    "available": True,
                }
                # Calculate per-night price
                try:
                    from datetime import datetime

                    d1 = datetime.strptime(check_in, "%Y-%m-%d")
                    d2 = datetime.strptime(check_out, "%Y-%m-%d")
                    nights = (d2 - d1).days
                    total = float(offer["offers"][0]["price"]["total"])
                    if nights > 0:
                        hotel_info["price_per_night"] = f"{total / nights:.2f} USD"
                        hotel_info["nights"] = nights
                except Exception:
                    pass
                results.append(hotel_info)

            # Enrich with Sentiments (Phase B2)
            try:
                found_ids = [h["hotelId"] for h in results if "hotelId" in h]
                if found_ids:
                    sentiments_data = _get_hotel_sentiments(found_ids)
                    sentiments_map = {
                        item["hotelId"]: item
                        for item in sentiments_data.get("data", [])
                    }

                    for h in results:
                        h_id = h.get("hotelId")
                        if h_id and h_id in sentiments_map:
                            s_info = sentiments_map[h_id]
                            h["sentiment_rating"] = s_info.get("overallRating", "N/A")
                            h["review_count"] = s_info.get("numberOfRatings", 0)
                            h["sentiment_summary"] = s_info.get("sentiments", {})
            except Exception as e:
                print(f"  [Warning] Sentiment enrichment failed: {e}")

            # Sorting behavior
            if sort_by == "rating":

                def get_rating_safe(h):
                    r = h.get("sentiment_rating", "N/A")
                    if isinstance(r, (int, float)):
                        return float(r)
                    return 0

                results.sort(key=get_rating_safe, reverse=True)
                print("  [Tool] Sorted results by Rating")
            else:
                # Default: Price ascending (usually default from API)
                # But ensures numeric sort if prices are strings
                def get_price_safe(h):
                    try:
                        return float(h["total_price"].split()[0])
                    except:
                        return float("inf")

                results.sort(key=get_price_safe)
                print("  [Tool] Sorted results by Price")

            # Limit to top 5 after sorting
            final_results = results[:5]

            print(f"  [Tool] Amadeus returned {len(final_results)} hotel offers")
            return json.dumps(final_results, indent=2)

        except Exception as e:
            print(f"  [Warning] Amadeus hotel API failed, using mock: {e}")

    # --- Fallback: Realistic Mock Data ---
    import random
    from datetime import datetime

    hotel_names = {
        "budget": [
            "Backpackers Inn",
            "City Hostel",
            "Budget Lodge",
            "Traveler's Rest",
            "Economy Stay",
        ],
        "medium": [
            "Grand Hotel",
            "City Suites",
            "Park View Hotel",
            "Harbor Inn",
            "Central Plaza Hotel",
        ],
        "luxury": [
            "The Ritz",
            "Four Seasons",
            "Waldorf Astoria",
            "Mandarin Oriental",
            "St. Regis",
        ],
    }

    budget_key = "medium"
    if budget.lower() in ["cheap", "low", "budget"]:
        budget_key = "budget"
    elif budget.lower() in ["luxury", "high", "premium", "5-star"]:
        budget_key = "luxury"

    base_prices = {"budget": 50, "medium": 150, "luxury": 400}

    # Calculate nights
    try:
        d1 = datetime.strptime(check_in, "%Y-%m-%d")
        d2 = datetime.strptime(check_out, "%Y-%m-%d")
        nights = max((d2 - d1).days, 1)
    except Exception:
        nights = 1

    mock_hotels = []
    names = hotel_names.get(budget_key, hotel_names["medium"])
    for i in range(3):
        name = f"{city.title()} {names[i % len(names)]}"
        price_per_night = base_prices[budget_key] + random.randint(-20, 80)
        rating = round(random.uniform(3.5, 5.0), 1)
        total_price = price_per_night * nights

        available_amenities = [
            "WiFi",
            "Breakfast",
            "Air Conditioning",
            "Pool",
            "Gym",
            "Spa",
            "Parking",
            "Restaurant",
        ]
        hotel_amenities = random.sample(available_amenities, k=random.randint(2, 5))

        mock_hotels.append(
            {
                "name": name,
                "rating": rating,
                "check_in": check_in,
                "check_out": check_out,
                "nights": nights,
                "price_per_night": f"{price_per_night:.2f} USD",
                "total_price": f"{total_price:.2f} USD",
                "currency": "USD",
                "amenities": hotel_amenities,
                "available": True,
                "booking_link": f"https://example.com/book/{name.replace(' ', '-').lower()}",
            }
        )

    print(f"  [Tool] Mock returned {len(mock_hotels)} hotel offers")
    return json.dumps(mock_hotels, indent=2)


# =====================================================================
# 4. SUGGEST DESTINATION (Wikivoyage RAG + Amadeus Logic)
# =====================================================================


def _resolve_city_to_iata(city_name: str) -> Optional[str]:
    """Resolves a city name to its IATA code using Amadeus."""
    try:
        amadeus = _get_amadeus_client()
        if not amadeus:
            return None
        from app.amadeus_rate_limiter import amadeus_call

        response = amadeus_call(
            amadeus.reference_data.locations.get, keyword=city_name, subType="CITY"
        )
        if response.data:
            return response.data[0].get("iataCode")
    except Exception:
        pass
    return None


def _get_similar_destinations(city_code: str) -> List[Dict]:
    """Get Amadeus travel recommendations based on a city code."""
    try:
        amadeus = _get_amadeus_client()
        if not amadeus:
            return []
        from app.amadeus_rate_limiter import amadeus_call

        response = amadeus_call(
            amadeus.reference_data.recommended_locations.get,
            cityCodes=city_code,
            travelerCountryCode="US",
        )
        data = []
        for rec in response.data[:5]:
            data.append(
                {
                    "destination": rec.get("name"),
                    "summary": f"Recommended by Amadeus as similar to {city_code}. Type: {rec.get('subType')}",
                    "source": "Amadeus (AI Recommendation)",
                    "score": rec.get("relevance", 0.5),
                }
            )
        return data
    except Exception:
        return []


@tool
def suggest_destination_tool(
    preferences: str,
    budget_tier: str = "medium",
    trip_type: str = "",
    climate: str = "",
    duration_days: int = 0,
) -> str:
    """
    Suggests travel destinations based on user preferences using the Wikivoyage knowledge base.
    Uses semantic search over curated travel articles to find matching destinations.
    Inputs:
    - preferences: Natural language description of what the user wants (e.g., "beach, relaxation, good food")
    - budget_tier: "budget", "medium", or "luxury"
    - trip_type: Type of trip (e.g., "honeymoon", "family", "adventure", "solo")
    - climate: Preferred climate (e.g., "tropical", "cold", "temperate")
    - duration_days: Trip duration to help filter appropriate destinations
    """
    print(f"  [Tool] Suggesting destinations for: {preferences}")

    # Build rich query
    parts = [preferences]
    if trip_type:
        parts.append(f"{trip_type} trip")
    if climate:
        parts.append(f"{climate} climate weather")
    if budget_tier:
        parts.append(f"{budget_tier} budget travel")
    if duration_days:
        parts.append(f"{duration_days} days")
    query = " ".join(parts)

    # Try RAG first
    # Try RAG first
    try:
        matches = _query_pinecone_inference(query, k=5, namespace="wikivoyage")
        if matches:
            destinations = []
            for match in matches:
                metadata = match.get("metadata", {})
                title = metadata.get("title", "Unknown")
                snippet = metadata.get("text", "")[:300]
                destinations.append(
                    {
                        "destination": title,
                        "summary": snippet,
                        "source": "Wikivoyage",
                        "score": match.get("score", 0),
                    }
                )
            # Enrich with Amadeus Recommendations (Phase B3)
            try:
                if destinations and len(destinations) > 0:
                    top_dest = destinations[0].get("destination", "")
                    iata = _resolve_city_to_iata(top_dest)
                    if iata:
                        similar = _get_similar_destinations(iata)
                        if similar:
                            print(
                                f"  [Tool] Amadeus enriched with {len(similar)} similar destinations to {top_dest}"
                            )
                            destinations.extend(similar)
            except Exception as e:
                print(f"  [Warning] Amadeus enrich failed: {e}")

            print(
                f"  [Tool] Returned {len(destinations)} destination suggestions (RAG + Amadeus)"
            )
            return json.dumps(destinations, indent=2)
    except Exception as e:
        print(f"  [Warning] Wikivoyage RAG failed: {e}")

    # Fallback: Use DuckDuckGo search targeting Wikivoyage
    print("  [Tool] Falling back to DuckDuckGo for destination suggestions")
    try:
        search = DuckDuckGoSearchRun()
        search_query = f"site:wikivoyage.org best destinations {preferences}"
        if trip_type:
            search_query += f" {trip_type}"
        if climate:
            search_query += f" {climate}"
        results = search.invoke(search_query)
        return json.dumps(
            {
                "suggestions": results,
                "source": "Wikivoyage (web search)",
                "note": "For better results, ingest Wikivoyage data into the RAG system.",
            },
            indent=2,
        )
    except Exception as e:
        return json.dumps({"error": f"Destination suggestion failed: {str(e)}"})


# =====================================================================
# 5. SUGGEST ATTRACTIONS (Wikivoyage RAG)
# =====================================================================
@tool
def suggest_attractions_tool(
    destination: str,
    interests: Optional[List[str]] = None,
    trip_type: str = "",
) -> str:
    """
    Finds attractions, activities, and things to do at a destination using the Wikivoyage knowledge base.
    Returns curated recommendations from travel articles including museums, landmarks, tours, and local experiences.
    Inputs:
    - destination: City or region name (e.g., "Paris", "Bali", "Tokyo")
    - interests: Optional list of interests to filter by (e.g., ["history", "food", "nature"])
    - trip_type: Type of trip for activity matching (e.g., "family", "romantic", "adventure")
    """
    print(f"  [Tool] Finding attractions in: {destination}")

    # Build rich query
    parts = [destination, "things to do", "attractions", "activities", "see"]
    if interests:
        parts.extend(interests)
    if trip_type:
        parts.append(f"{trip_type} activities")
    query = " ".join(parts)

    # Try RAG first
    try:
        matches = _query_pinecone_inference(query, k=8, namespace="wikivoyage")
        if matches:
            attractions = []
            seen = set()
            for match in matches:
                metadata = match.get("metadata", {})
                title = metadata.get("title", "Unknown")

                # Filter by relevance: Title must match destination (fuzzy)
                # This prevents "Paris" results showing up for "Tokyo" when index is small
                if (
                    destination.lower() not in title.lower()
                    and title.lower() not in destination.lower()
                ):
                    continue

                section = metadata.get("section", "")
                snippet = metadata.get("text", "")[:400]
                # Deduplicate
                key = f"{title}:{section}"
                if key not in seen:
                    seen.add(key)
                    attractions.append(
                        {
                            "name": title,
                            "section": section,
                            "description": snippet,
                            "source": "Wikivoyage",
                            "score": match.get("score", 0),
                        }
                    )

            if attractions:
                print(f"  [Tool] RAG returned {len(attractions)} attractions")
                return json.dumps(attractions, indent=2)

    except Exception as e:
        print(f"  [Warning] Wikivoyage RAG failed: {e}")

    # Fallback: DuckDuckGo targeting Wikivoyage
    print("  [Tool] Falling back to DuckDuckGo for attraction suggestions")
    try:
        search = DuckDuckGoSearchRun()
        search_query = f"site:wikivoyage.org {destination} things to do attractions"
        if interests:
            search_query += " " + " ".join(interests)
        results = search.invoke(search_query)
        return json.dumps(
            {
                "attractions": results,
                "destination": destination,
                "source": "Wikivoyage (web search)",
            },
            indent=2,
        )
    except Exception as e:
        return json.dumps({"error": f"Attraction search failed: {str(e)}"})


# =====================================================================
# 6. CREATE USER PROFILE (Pinecone RAG)
# =====================================================================
@tool
def create_user_profile_tool(
    name: str,
    email: str,
    preferences: Optional[List[str]] = None,
    dietary_needs: Optional[List[str]] = None,
    accessibility_needs: Optional[List[str]] = None,
    past_destinations: Optional[List[str]] = None,
    loyalty_programs: Optional[List[str]] = None,
    travel_style: str = "",
) -> str:
    """
    Creates or updates a user travel profile for personalized trip recommendations.
    Stores preferences, dietary/accessibility needs, past destinations, and loyalty programs.
    The profile is used to personalize future trip planning and hotel/flight selections.
    Inputs:
    - name: User's full name
    - email: User's email (used as unique identifier)
    - preferences: List of travel preferences (e.g., ["beach", "history", "nightlife"])
    - dietary_needs: List of dietary requirements (e.g., ["vegan", "kosher", "gluten-free"])
    - accessibility_needs: List of accessibility requirements (e.g., ["wheelchair", "ground floor"])
    - past_destinations: List of previously visited destinations
    - loyalty_programs: List of loyalty program memberships (e.g., ["Marriott Bonvoy", "BA Executive Club"])
    - travel_style: General travel style (e.g., "luxury", "backpacker", "family")
    """
    print(f"  [Tool] Creating/updating profile for: {name} ({email})")

    # Build a rich summary for semantic search
    summary_parts = [f"Travel profile for {name}."]
    if preferences:
        summary_parts.append(f"Preferences: {', '.join(preferences)}.")
    if dietary_needs:
        summary_parts.append(f"Dietary needs: {', '.join(dietary_needs)}.")
    if accessibility_needs:
        summary_parts.append(f"Accessibility: {', '.join(accessibility_needs)}.")
    if past_destinations:
        summary_parts.append(f"Past trips: {', '.join(past_destinations)}.")
    if loyalty_programs:
        summary_parts.append(f"Loyalty programs: {', '.join(loyalty_programs)}.")
    if travel_style:
        summary_parts.append(f"Travel style: {travel_style}.")

    summary = " ".join(summary_parts)

    # Build metadata dict
    profile_data = {
        "name": name,
        "email": email,
        "preferences": preferences or [],
        "dietary_needs": dietary_needs or [],
        "accessibility_needs": accessibility_needs or [],
        "past_destinations": past_destinations or [],
        "loyalty_programs": loyalty_programs or [],
        "travel_style": travel_style,
    }

    # Try to store in Pinecone
    # Try to store in Pinecone
    pc, index = _get_pinecone_client_and_index()
    if pc and index:
        try:
            # 1. Generate Embedding
            embedding_response = pc.inference.embed(
                model="llama-text-embed-v2",
                inputs=[summary],
                parameters={"input_type": "passage", "truncate": "END"},
            )
            vector_values = embedding_response[0]["values"]

            # 2. Prepare Metadata
            metadata = {
                "name": name,
                "email": email,
                "travel_style": travel_style or "general",
                "preferences": ", ".join(preferences) if preferences else "",
                "dietary_needs": ", ".join(dietary_needs) if dietary_needs else "",
                "accessibility_needs": (
                    ", ".join(accessibility_needs) if accessibility_needs else ""
                ),
                "text": summary,  # Store text for retrieval
            }

            # 3. Upsert
            vector_id = f"profile_{email.replace('@', '_').replace('.', '_')}"
            index.upsert(
                vectors=[
                    {"id": vector_id, "values": vector_values, "metadata": metadata}
                ],
                namespace="user_profiles",
            )

            print(f"  [Tool] Profile stored in Pinecone")
            return json.dumps(
                {
                    "status": "saved",
                    "message": f"Profile created/updated for {name}",
                    "profile": profile_data,
                    "storage": "Pinecone (user_profiles namespace)",
                },
                indent=2,
            )
        except Exception as e:
            print(f"  [Warning] Pinecone storage failed: {e}")

    # Fallback: return profile as JSON (in-memory only)
    return json.dumps(
        {
            "status": "created_in_memory",
            "message": f"Profile created for {name} (not persisted — Pinecone unavailable)",
            "profile": profile_data,
        },
        indent=2,
    )


# =====================================================================
# 7. CREATE PLAN (Structured Plan Builder)
# =====================================================================
@tool
def create_plan_tool(
    destination: str,
    origin: str,
    duration_days: int,
    budget: float,
    currency: str = "USD",
    trip_type: str = "general",
    travelers: int = 1,
    flights_data: str = "",
    hotels_data: str = "",
    attractions_data: str = "",
) -> str:
    """
    Assembles a structured trip plan from gathered travel data.
    Takes flight, hotel, and attraction data and builds a complete day-by-day itinerary.
    Inputs:
    - destination: Trip destination (e.g., "Paris, France")
    - origin: Departure city (e.g., "London")
    - duration_days: Number of trip days
    - budget: Total budget amount
    - currency: Budget currency (default "USD")
    - trip_type: Type of trip (e.g., "honeymoon", "family", "adventure")
    - travelers: Number of travelers
    - flights_data: JSON string of flight search results (from search_flights_tool)
    - hotels_data: JSON string of hotel search results (from search_hotels_tool)
    - attractions_data: JSON string of attraction results (from suggest_attractions_tool)
    """
    print(
        f"  [Tool] Creating plan: {origin} -> {destination}, {duration_days} days, ${budget} {currency}"
    )

    # Parse JSON inputs safely
    def safe_parse(data_str):
        if not data_str:
            return []
        try:
            parsed = json.loads(data_str)
            return parsed if isinstance(parsed, list) else [parsed]
        except (json.JSONDecodeError, TypeError):
            return []

    flights = safe_parse(flights_data)
    hotels = safe_parse(hotels_data)
    attractions = safe_parse(attractions_data)

    # Budget allocation by trip type
    allocation = {
        "honeymoon": {
            "accommodation": 0.45,
            "activities": 0.25,
            "dining": 0.20,
            "transport": 0.10,
        },
        "family": {
            "accommodation": 0.40,
            "activities": 0.35,
            "dining": 0.15,
            "transport": 0.10,
        },
        "business": {
            "accommodation": 0.50,
            "activities": 0.05,
            "dining": 0.20,
            "transport": 0.25,
        },
        "adventure": {
            "accommodation": 0.25,
            "activities": 0.50,
            "dining": 0.10,
            "transport": 0.15,
        },
        "solo": {
            "accommodation": 0.35,
            "activities": 0.40,
            "dining": 0.15,
            "transport": 0.10,
        },
        "general": {
            "accommodation": 0.40,
            "activities": 0.30,
            "dining": 0.15,
            "transport": 0.15,
        },
    }

    alloc = allocation.get(trip_type.lower(), allocation["general"])
    daily_budget = budget / max(duration_days, 1)

    # Build itinerary skeleton
    itinerary = []
    for day in range(1, duration_days + 1):
        day_plan = {
            "day": day,
            "theme": "",
            "activities": [],
            "estimated_cost": round(daily_budget, 2),
        }

        # First day: arrival
        if day == 1:
            day_plan["theme"] = "Arrival & Settling In"
            day_plan["activities"].append("Arrive at destination, transfer to hotel")
            day_plan["activities"].append("Check in and explore neighborhood")

        # Last day: departure
        elif day == duration_days:
            day_plan["theme"] = "Departure Day"
            day_plan["activities"].append("Check out, last-minute shopping/sightseeing")
            day_plan["activities"].append("Transfer to airport, departure")

        # Middle days: activities
        else:
            day_plan["theme"] = f"Exploration Day {day - 1}"
            # Add attractions if available
            if attractions and day - 2 < len(attractions):
                attr = attractions[day - 2]
                if isinstance(attr, dict):
                    name = attr.get("name", attr.get("destination", "Local attraction"))
                    day_plan["activities"].append(f"Visit: {name}")
                else:
                    day_plan["activities"].append(f"Visit: {attr}")
            day_plan["activities"].append("Lunch at local restaurant")
            day_plan["activities"].append("Afternoon exploration")

        itinerary.append(day_plan)

    # Calculate budget breakdown
    flight_cost = 0
    if flights:
        try:
            first_flight = flights[0]
            if isinstance(first_flight, dict):
                price_data = first_flight.get("price", {})
                flight_cost = float(
                    price_data.get("total", price_data.get("grandTotal", 0))
                )
        except (ValueError, TypeError, IndexError):
            flight_cost = 0

    hotel_cost = 0
    if hotels:
        try:
            first_hotel = hotels[0]
            if isinstance(first_hotel, dict):
                total_str = first_hotel.get("total_price", "0")
                # Extract numeric value
                hotel_cost = float(
                    "".join(c for c in str(total_str) if c.isdigit() or c == ".") or "0"
                )
        except (ValueError, TypeError, IndexError):
            hotel_cost = 0

    plan = {
        "destination": destination,
        "origin": origin,
        "duration_days": duration_days,
        "trip_type": trip_type,
        "travelers": travelers,
        "budget": {
            "total": budget,
            "currency": currency,
            "allocation": {k: round(budget * v, 2) for k, v in alloc.items()},
            "estimated_flight_cost": flight_cost * travelers,
            "estimated_hotel_cost": hotel_cost,
            "estimated_daily_budget": round(daily_budget, 2),
        },
        "flights": flights[:3] if flights else [],
        "hotels": hotels[:3] if hotels else [],
        "itinerary": itinerary,
        "status": "draft",
    }

    print(
        f"  [Tool] Plan created: {duration_days} days, {len(itinerary)} itinerary items"
    )
    return json.dumps(plan, indent=2)


# =====================================================================
# 8. SEARCH ACTIVITIES — Tours & Activities (Amadeus Shopping Activities)
# =====================================================================
@tool
def search_activities_tool(
    latitude: float,
    longitude: float,
    radius: int = 20,
) -> str:
    """
    Find bookable tours and activities near a destination using Amadeus.
    Requires latitude and longitude of the destination.
    Returns a list of activities with names, descriptions, prices, and ratings.
    """
    print(
        f"  [Tool] Searching Activities: lat={latitude}, lng={longitude}, radius={radius}"
    )

    amadeus = _get_amadeus_client()
    if amadeus:
        try:
            response = amadeus.shopping.activities.get(
                latitude=latitude,
                longitude=longitude,
                radius=radius,
            )
            activities = []
            for act in response.data[:10]:
                activities.append(
                    {
                        "name": act.get("name", "Unknown Activity"),
                        "description": act.get("shortDescription", ""),
                        "rating": act.get("rating", "N/A"),
                        "price": act.get("price", {}).get("amount", "N/A"),
                        "currency": act.get("price", {}).get("currencyCode", "USD"),
                        "booking_link": act.get("bookingLink", ""),
                        "pictures": [p for p in act.get("pictures", [])[:2]],
                        "source": "Amadeus",
                    }
                )
            if activities:
                print(f"  [Amadeus] Found {len(activities)} activities")
                return json.dumps(activities, indent=2)
        except Exception as e:
            print(f"  [Amadeus Activities] Failed: {e}")

    # Mock fallback
    mock = [
        {
            "name": "City Walking Tour",
            "description": "Guided walking tour of historic center",
            "rating": "4.5",
            "price": "35",
            "currency": "USD",
            "source": "mock",
        },
        {
            "name": "Local Food Tasting",
            "description": "Sample local cuisine with a guide",
            "rating": "4.7",
            "price": "55",
            "currency": "USD",
            "source": "mock",
        },
        {
            "name": "Sunset Boat Cruise",
            "description": "Evening cruise with panoramic views",
            "rating": "4.3",
            "price": "70",
            "currency": "USD",
            "source": "mock",
        },
    ]
    return json.dumps(mock, indent=2)


# =====================================================================
# 9. FLIGHT PRICE ANALYSIS — Is This a Good Deal?
# =====================================================================
@tool
def flight_price_analysis_tool(
    origin: str,
    destination: str,
    departure_date: str,
    currency: str = "USD",
) -> str:
    """
    Analyze flight prices for a route to determine if current prices are
    cheap, typical, or expensive. Uses Amadeus Flight Price Analysis API.
    Origin and destination should be IATA airport/city codes (e.g., 'LON', 'PAR').
    """
    print(
        f"  [Tool] Flight Price Analysis: {origin} -> {destination} on {departure_date}"
    )

    print(
        f"  [Tool] Flight Price Analysis: {origin} -> {destination} on {departure_date}"
    )

    data = _get_flight_price_metrics(origin, destination, departure_date, currency)
    metrics = data.get("metrics", [])

    if data.get("source") == "Mock":
        # Add a note that it's mock data if needed, or just return as is
        pass

    if metrics:
        print(f"  [Amadeus] Returned price metrics for {origin}->{destination}")
        return json.dumps(metrics, indent=2)

    return json.dumps({"error": "No price metrics found"}, indent=2)


# =====================================================================
# 10. FLIGHT STATUS — Real-Time Flight Schedule
# =====================================================================
@tool
def flight_status_tool(
    carrier_code: str,
    flight_number: str,
    scheduled_departure_date: str,
) -> str:
    """
    Check the schedule and status of a specific flight.
    Requires the carrier code (e.g., 'BA') and flight number (e.g., '123').
    Date format: YYYY-MM-DD.
    """
    print(
        f"  [Tool] Flight Status: {carrier_code}{flight_number} on {scheduled_departure_date}"
    )

    amadeus = _get_amadeus_client()
    if amadeus:
        try:
            response = amadeus.schedule.flights.get(
                carrierCode=carrier_code.upper(),
                flightNumber=flight_number,
                scheduledDepartureDate=scheduled_departure_date,
            )
            flights = []
            for fl in response.data[:3]:
                dep = fl.get("flightPoints", [{}])[0] if fl.get("flightPoints") else {}
                arr = fl.get("flightPoints", [{}])[-1] if fl.get("flightPoints") else {}
                flights.append(
                    {
                        "carrier": carrier_code.upper(),
                        "flight_number": flight_number,
                        "departure": dep.get("iataCode", ""),
                        "departure_time": (
                            dep.get("departure", {})
                            .get("timings", [{}])[0]
                            .get("value", "")
                            if dep.get("departure")
                            else ""
                        ),
                        "arrival": arr.get("iataCode", ""),
                        "arrival_time": (
                            arr.get("arrival", {})
                            .get("timings", [{}])[0]
                            .get("value", "")
                            if arr.get("arrival")
                            else ""
                        ),
                        "source": "Amadeus",
                    }
                )
            if flights:
                print(f"  [Amadeus] Found {len(flights)} flight schedule entries")
                return json.dumps(flights, indent=2)
        except Exception as e:
            print(f"  [Amadeus Flight Status] Failed: {e}")

    # Mock fallback
    mock = {
        "carrier": carrier_code.upper(),
        "flight_number": flight_number,
        "date": scheduled_departure_date,
        "status": "SCHEDULED",
        "departure": {"airport": "N/A", "time": "08:00"},
        "arrival": {"airport": "N/A", "time": "12:00"},
        "source": "mock",
    }
    return json.dumps(mock, indent=2)


# =====================================================================
# 11. AIRPORT / CITY SEARCH — Resolve Names to IATA Codes
# =====================================================================
@tool
def airport_search_tool(
    keyword: str,
    sub_type: str = "CITY,AIRPORT",
) -> str:
    """
    Search for airports and cities by keyword and return their IATA codes.
    Use this to convert city names like 'Paris' or 'London' to IATA codes
    (e.g., 'PAR', 'LON') before calling flight/hotel tools.
    sub_type can be 'CITY', 'AIRPORT', or 'CITY,AIRPORT'.
    """
    print(f"  [Tool] Airport Search: '{keyword}' (type={sub_type})")

    amadeus = _get_amadeus_client()
    if amadeus:
        try:
            response = amadeus.reference_data.locations.get(
                keyword=keyword,
                subType=sub_type,
            )
            locations = []
            for loc in response.data[:10]:
                locations.append(
                    {
                        "name": loc.get("name", ""),
                        "iata_code": loc.get("iataCode", ""),
                        "sub_type": loc.get("subType", ""),
                        "city": loc.get("address", {}).get("cityName", ""),
                        "country": loc.get("address", {}).get("countryCode", ""),
                        "latitude": loc.get("geoCode", {}).get("latitude"),
                        "longitude": loc.get("geoCode", {}).get("longitude"),
                        "source": "Amadeus",
                    }
                )
            if locations:
                print(f"  [Amadeus] Found {len(locations)} locations for '{keyword}'")
                return json.dumps(locations, indent=2)
        except Exception as e:
            print(f"  [Amadeus Airport Search] Failed: {e}")

    # Mock fallback — common city → IATA mappings
    common_codes = {
        "paris": [
            {
                "name": "PARIS",
                "iata_code": "PAR",
                "sub_type": "CITY",
                "country": "FR",
                "source": "mock",
            }
        ],
        "london": [
            {
                "name": "LONDON",
                "iata_code": "LON",
                "sub_type": "CITY",
                "country": "GB",
                "source": "mock",
            }
        ],
        "new york": [
            {
                "name": "NEW YORK",
                "iata_code": "NYC",
                "sub_type": "CITY",
                "country": "US",
                "source": "mock",
            }
        ],
        "tokyo": [
            {
                "name": "TOKYO",
                "iata_code": "TYO",
                "sub_type": "CITY",
                "country": "JP",
                "source": "mock",
            }
        ],
        "bali": [
            {
                "name": "BALI",
                "iata_code": "DPS",
                "sub_type": "AIRPORT",
                "country": "ID",
                "source": "mock",
            }
        ],
        "rome": [
            {
                "name": "ROME",
                "iata_code": "ROM",
                "sub_type": "CITY",
                "country": "IT",
                "source": "mock",
            }
        ],
    }
    key = keyword.lower().strip()
    if key in common_codes:
        return json.dumps(common_codes[key], indent=2)
    return json.dumps(
        [
            {
                "name": keyword.upper(),
                "iata_code": keyword.upper()[:3],
                "sub_type": "CITY",
                "source": "mock_guess",
            }
        ],
        indent=2,
    )


# =====================================================================
# 12. AIRLINE LOOKUP — Resolve Airline Codes to Names
# =====================================================================
@tool
def airline_lookup_tool(
    airline_code: str,
) -> str:
    """
    Look up the full airline name from a 2-letter IATA airline code.
    Example: 'BA' -> 'BRITISH AIRWAYS', 'EK' -> 'EMIRATES'.
    """
    print(f"  [Tool] Airline Lookup: '{airline_code}'")

    amadeus = _get_amadeus_client()
    if amadeus:
        try:
            response = amadeus.reference_data.airlines.get(
                airlineCodes=airline_code.upper(),
            )
            airlines = []
            for al in response.data:
                airlines.append(
                    {
                        "code": al.get("iataCode", airline_code.upper()),
                        "name": al.get("businessName", "Unknown Airline"),
                        "common_name": al.get("commonName", ""),
                        "source": "Amadeus",
                    }
                )
            if airlines:
                print(f"  [Amadeus] Found airline: {airlines[0].get('name')}")
                return json.dumps(airlines, indent=2)
        except Exception as e:
            print(f"  [Amadeus Airline Lookup] Failed: {e}")

    # Mock fallback
    known_airlines = {
        "BA": "British Airways",
        "EK": "Emirates",
        "AA": "American Airlines",
        "UA": "United Airlines",
        "DL": "Delta Air Lines",
        "LH": "Lufthansa",
        "AF": "Air France",
        "QR": "Qatar Airways",
        "SQ": "Singapore Airlines",
        "TK": "Turkish Airlines",
        "EY": "Etihad Airways",
        "NH": "All Nippon Airways",
    }
    name = known_airlines.get(airline_code.upper(), f"Airline {airline_code.upper()}")
    return json.dumps(
        [{"code": airline_code.upper(), "name": name, "source": "mock"}], indent=2
    )


# =====================================================================
# 13. TRAVEL RECOMMENDATIONS — Destination Discovery
# =====================================================================
@tool
def travel_recommendations_tool(
    city_code: str,
    traveler_country_code: str = "US",
) -> str:
    """
    Get recommended destinations similar to a given city using Amadeus.
    Useful for discovery: 'If you like Paris, you might also like...'
    city_code: IATA city code (e.g., 'PAR' for Paris).
    """
    print(f"  [Tool] Travel Recommendations based on: {city_code}")

    amadeus = _get_amadeus_client()
    if amadeus:
        try:
            response = amadeus.reference_data.recommended_locations.get(
                cityCodes=city_code.upper(),
                travelerCountryCode=traveler_country_code.upper(),
            )
            recommendations = []
            for rec in response.data[:8]:
                recommendations.append(
                    {
                        "name": rec.get("name", ""),
                        "iata_code": rec.get("iataCode", ""),
                        "sub_type": rec.get("subType", ""),
                        "type": rec.get("type", ""),
                        "relevance": rec.get("relevance", 0),
                        "source": "Amadeus",
                    }
                )
            if recommendations:
                print(
                    f"  [Amadeus] Found {len(recommendations)} destination recommendations"
                )
                return json.dumps(recommendations, indent=2)
        except Exception as e:
            print(f"  [Amadeus Recommendations] Failed: {e}")

    # Mock fallback
    mock = [
        {"name": "Barcelona", "iata_code": "BCN", "relevance": 0.9, "source": "mock"},
        {"name": "Rome", "iata_code": "ROM", "relevance": 0.85, "source": "mock"},
        {"name": "Lisbon", "iata_code": "LIS", "relevance": 0.8, "source": "mock"},
        {"name": "Amsterdam", "iata_code": "AMS", "relevance": 0.75, "source": "mock"},
    ]
    return json.dumps(mock, indent=2)


# =====================================================================
# 14. CHEAPEST FLIGHTS — Find Best Travel Dates
# =====================================================================
@tool
def cheapest_flights_tool(
    origin: str,
    destination: str,
) -> str:
    """
    Find the cheapest flight dates for a given route using Amadeus.
    Returns a list of dates with the cheapest prices — ideal for flexible travelers.
    Origin and destination should be IATA codes (e.g., 'LON', 'PAR').
    """
    print(f"  [Tool] Cheapest Flights: {origin} -> {destination}")

    amadeus = _get_amadeus_client()
    if amadeus:
        try:
            response = amadeus.shopping.flight_dates.get(
                origin=origin.upper()[:3],
                destination=destination.upper()[:3],
            )
            dates = []
            for item in response.data[:10]:
                dates.append(
                    {
                        "departure_date": item.get("departureDate", ""),
                        "return_date": item.get("returnDate", ""),
                        "price": item.get("price", {}).get("total", "N/A"),
                        "currency": item.get("price", {}).get("currency", "USD"),
                        "source": "Amadeus",
                    }
                )
            if dates:
                print(f"  [Amadeus] Found {len(dates)} cheapest date options")
                return json.dumps(dates, indent=2)
        except Exception as e:
            print(f"  [Amadeus Cheapest Flights] Failed: {e}")

    # Mock fallback
    mock = [
        {
            "departure_date": "2026-07-15",
            "return_date": "2026-07-22",
            "price": "180",
            "currency": "USD",
            "source": "mock",
        },
        {
            "departure_date": "2026-07-20",
            "return_date": "2026-07-27",
            "price": "195",
            "currency": "USD",
            "source": "mock",
        },
        {
            "departure_date": "2026-08-01",
            "return_date": "2026-08-08",
            "price": "210",
            "currency": "USD",
            "source": "mock",
        },
    ]
    return json.dumps(mock, indent=2)


# =====================================================================
# 15. HOTEL RATINGS — Traveler Sentiment & Ratings
# =====================================================================
@tool
def hotel_ratings_tool(
    hotel_ids: List[str],
) -> str:
    """
    Get traveler sentiment and ratings for specific hotels using Amadeus.
    hotel_ids: list of Amadeus hotel IDs (e.g., ['TELONMFS', 'ADNYCCTB']).
    Returns overall rating, number of reviews, and sentiment breakdown.
    """
    print(f"  [Tool] Hotel Ratings for: {hotel_ids}")

    data = _get_hotel_sentiments(hotel_ids)
    if data.get("data"):
        print(f"  [Amadeus] Found ratings for {len(data['data'])} hotels")
        return json.dumps(data["data"], indent=2)

    return json.dumps({"error": "No ratings found"}, indent=2)


# =====================================================================
# 13. RESOLVE AIRPORT CODE (Amadeus Airport & City Search)
# =====================================================================
@tool
def resolve_airport_code_tool(keyword: str) -> str:
    """
    Resolves a city name, airport name, or partial text to IATA airport/city codes.
    Use this BEFORE calling search_flights_tool or search_hotels_tool when the user
    provides a city name instead of an IATA code.
    IMPORTANT: If the known destination is a country and not a city, you MUST pass
    the capital city name of that country as the keyword, NOT the country name.
    Inputs:
    - keyword: City name or airport name (e.g., "Paris", "London Heathrow", "JFK")
    Returns: List of matching airports/cities with IATA codes, names, and types.

    """
    print(f"  [Tool] Resolving airport code for: {keyword}")
    from app.amadeus_rate_limiter import get_amadeus_client, amadeus_call

    amadeus = get_amadeus_client()
    if not amadeus:
        # Fallback: return the keyword as-is (assume it's already a code)
        return json.dumps(
            [{"iataCode": keyword.upper()[:3], "name": keyword, "type": "fallback"}]
        )

    # Inner helper to perform the actual amadeus extraction
    def _fetch_locations(search_kw):
        response = amadeus_call(
            amadeus.reference_data.locations.get,
            keyword=search_kw,
            subType="AIRPORT,CITY",
        )
        results = []
        for loc in response.data[:5]:
            results.append(
                {
                    "iataCode": loc.get("iataCode", ""),
                    "name": loc.get("name", ""),
                    "detailedName": loc.get("detailedName", ""),
                    "type": loc.get("subType", ""),
                    "cityName": loc.get("address", {}).get("cityName", ""),
                    "countryCode": loc.get("address", {}).get("countryCode", ""),
                }
            )
        return results

    try:
        # 1. Attempt initial fetch
        results = _fetch_locations(keyword)

        # 2. If 0 results, fall back to LLM resolution (in case it is a country like "Turkey")
        if len(results) == 0:
            import os
            from langchain_openai import AzureChatOpenAI
            from langchain_community.chat_models import ChatOllama
            from langchain_core.messages import SystemMessage, HumanMessage

            print(
                f"  [Tool] 0 results found for '{keyword}'. Attempting LLM resolution..."
            )

            try:
                if os.getenv("AZURE_OPENAI_API_KEY"):
                    llm = AzureChatOpenAI(
                        azure_deployment=os.environ.get(
                            "AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4.1-mini"
                        ),
                        api_version=os.environ.get(
                            "AZURE_OPENAI_API_VERSION", "2025-01-01-preview"
                        ),
                        temperature=0,
                    )
                else:
                    llm = ChatOllama(model="llama3", temperature=0)

                system_msg = SystemMessage(
                    content="You are a geographic assistant. If the user provides a country name, reply ONLY with the name of its capital city. If the user provides a city or airport name, reply EXACTLY with that city or airport name. Do not include any punctuation, conversational text, or explanation."
                )
                human_msg = HumanMessage(content=keyword)

                resolved_keyword = llm.invoke([system_msg, human_msg]).content.strip()
                print(
                    f"  [Tool] LLM resolved '{keyword}' to '{resolved_keyword}'. Retrying search..."
                )
                keyword = resolved_keyword

                # Try fetching again with the resolved keyword
                results = _fetch_locations(keyword)
            except Exception as llm_e:
                print(f"  [Tool] LLM resolution failed: {llm_e}")

        print(f"  [Tool] Found {len(results)} locations for '{keyword}'")
        if not results:
            # Final mock fallback for common cities that amadeus sandbox might miss
            common_mappings = {
                "tel aviv": "TLV",
                "paris": "PAR",
                "london": "LON",
                "new york": "NYC",
                "tokyo": "TYO",
                "bali": "DPS",
                "rome": "ROM",
                "istanbul": "IST",
                "barcelona": "BCN",
                "madrid": "MAD",
                "berlin": "BER",
                "amsterdam": "AMS",
                "bangkok": "BKK",
                "dubai": "DXB",
                "singapore": "SIN",
            }

            clean_kw = keyword.lower().strip()
            fallback_code = common_mappings.get(clean_kw, keyword.upper()[:3])

            return json.dumps(
                [{"iataCode": fallback_code, "name": keyword, "type": "fallback"}]
            )
        return json.dumps(results, indent=2)

    except Exception as e:
        print(f"  [Tool] Airport code resolution failed: {e}")
        return json.dumps(
            [{"iataCode": keyword.upper()[:3], "name": keyword, "type": "fallback"}]
        )


# =====================================================================
# 9. AIRLINE CODE LOOKUP (Amadeus Airline Code Lookup)
# =====================================================================
@tool
def get_airline_info_tool(airline_code: str) -> str:
    """
    Looks up airline information from an IATA airline code.
    Returns the airline's full name, ICAO code, and business name.
    Inputs:
    - airline_code: 2-letter IATA airline code (e.g., "BA", "LH", "AA")
    """
    print(f"  [Tool] Looking up airline: {airline_code}")
    from app.amadeus_rate_limiter import get_amadeus_client, amadeus_call

    amadeus = get_amadeus_client()
    if not amadeus:
        return json.dumps(
            {"code": airline_code, "name": airline_code, "type": "fallback"}
        )

    try:
        response = amadeus_call(
            amadeus.reference_data.airlines.get,
            airlineCodes=airline_code.upper(),
        )
        results = []
        for airline in response.data[:3]:
            results.append(
                {
                    "iataCode": airline.get("iataCode", ""),
                    "icaoCode": airline.get("icaoCode", ""),
                    "businessName": airline.get("businessName", ""),
                    "commonName": airline.get(
                        "commonName", airline.get("businessName", "")
                    ),
                }
            )
        print(f"  [Tool] Found airline info for '{airline_code}'")
        return json.dumps(results, indent=2)
    except Exception as e:
        print(f"  [Tool] Airline lookup failed: {e}")
        return json.dumps(
            [{"iataCode": airline_code, "name": airline_code, "type": "fallback"}]
        )


# =====================================================================
# 10. TOURS & ACTIVITIES (Amadeus Tours and Activities API)
# =====================================================================
@tool
def search_tours_activities_tool(
    latitude: float,
    longitude: float,
    radius: int = 5,
) -> str:
    """
    Searches for bookable tours, activities, and experiences near a location.
    Uses Amadeus Tours & Activities API which aggregates offers from Viator,
    GetYourGuide, Klook, and Musement — 300,000+ activities worldwide.
    Inputs:
    - latitude: Latitude of the location (e.g., 48.8566 for Paris)
    - longitude: Longitude of the location (e.g., 2.3522 for Paris)
    - radius: Search radius in km (default 5, max 20)
    Returns: List of activities with name, description, price, booking link, and rating.
    """
    print(
        f"  [Tool] Searching tours & activities at ({latitude}, {longitude}), radius={radius}km"
    )
    from app.amadeus_rate_limiter import get_amadeus_client, amadeus_call

    amadeus = get_amadeus_client()
    if not amadeus:
        return json.dumps({"error": "Amadeus API not configured", "results": []})

    try:
        response = amadeus_call(
            amadeus.shopping.activities.get,
            latitude=latitude,
            longitude=longitude,
            radius=min(radius, 20),
        )
        results = []
        for activity in response.data[:10]:
            act_info = {
                "name": activity.get("name", ""),
                "shortDescription": activity.get("shortDescription", ""),
                "type": activity.get("type", ""),
                "bookingLink": activity.get("bookingLink", ""),
                "price": {},
                "rating": activity.get("rating", "N/A"),
                "pictures": [],
            }
            # Price info
            price_data = activity.get("price", {})
            if price_data:
                act_info["price"] = {
                    "amount": price_data.get("amount", "N/A"),
                    "currency": price_data.get("currencyCode", "USD"),
                }
            # Pictures (first 2)
            pictures = activity.get("pictures", [])
            act_info["pictures"] = pictures[:2] if pictures else []

            results.append(act_info)

        print(f"  [Tool] Found {len(results)} tours & activities")
        return json.dumps(results, indent=2)
    except Exception as e:
        print(f"  [Tool] Tours & Activities search failed: {e}")
        return json.dumps({"error": str(e), "results": []})


# =====================================================================
# 11. POINTS OF INTEREST (Amadeus POI API)
# =====================================================================
@tool
def search_points_of_interest_tool(
    latitude: float,
    longitude: float,
    radius: int = 5,
    categories: Optional[List[str]] = None,
) -> str:
    """
    Finds popular points of interest near a location, ranked by popularity.
    Uses Amadeus Points of Interest API powered by AVUXI TopPlace data.
    Inputs:
    - latitude: Latitude of the location (e.g., 48.8566 for Paris)
    - longitude: Longitude of the location (e.g., 2.3522 for Paris)
    - radius: Search radius in km (default 5, max 20)
    - categories: Optional filter list from: SIGHTS, BEACH_PARK, HISTORICAL, NIGHTLIFE, RESTAURANT, SHOPPING
    Returns: Ranked list of POIs with name, category, tags, and coordinates.
    """
    print(
        f"  [Tool] Searching POIs at ({latitude}, {longitude}), radius={radius}km, categories={categories}"
    )
    from app.amadeus_rate_limiter import get_amadeus_client, amadeus_call

    amadeus = get_amadeus_client()
    if not amadeus:
        return json.dumps({"error": "Amadeus API not configured", "results": []})

    try:
        # Try primary SDK method
        try:
            if hasattr(amadeus.reference_data.locations, "points_of_interest"):
                response = amadeus_call(
                    amadeus.reference_data.locations.points_of_interest.get,
                    latitude=latitude,
                    longitude=longitude,
                    radius=min(radius, 20),
                    categories=",".join(categories).upper() if categories else None,
                )
            else:
                # Try raw call if SDK helper missing
                response = amadeus_call(
                    amadeus.get,
                    "/v1/reference-data/locations/pois",
                    latitude=latitude,
                    longitude=longitude,
                    radius=min(radius, 20),
                    categories=",".join(categories).upper() if categories else None,
                )
        except AttributeError:
            # Fallback to raw call
            response = amadeus_call(
                amadeus.get,
                "/v1/reference-data/locations/pois",
                latitude=latitude,
                longitude=longitude,
                radius=min(radius, 20),
                categories=",".join(categories).upper() if categories else None,
            )

        results = []
        for poi in response.data[:15]:
            results.append(
                {
                    "name": poi.get("name", ""),
                    "category": poi.get("category", ""),
                    "subCategory": poi.get("subCategory", []),
                    "tags": poi.get("tags", []),
                    "rank": poi.get("rank", 0),
                    "geoCode": poi.get("geoCode", {}),
                }
            )

        print(f"  [Tool] Found {len(results)} points of interest")
        return json.dumps(results, indent=2)

    except Exception as e:
        print(f"  [Tool] POI search failed: {e}")
        # Mock Fallback for Test Environment Reliability
        mock_pois = [
            {"name": "Mock Eiffel Tower", "category": "SIGHTS", "rank": 1},
            {"name": "Mock Louvre Museum", "category": "SIGHTS", "rank": 2},
            {"name": "Mock Notre Dame", "category": "SIGHTS", "rank": 5},
        ]
        return json.dumps(
            {
                "warning": f"Live POI search failed ({e}). Showing mock data.",
                "results": mock_pois,
            },
            indent=2,
        )


# =====================================================================
# 11.5 KIWI FLIGHT SEARCH (MCP)
# =====================================================================
@tool
def search_flights_with_kiwi_tool(
    origin: str,
    destination: str,
    departure_date: str,
    return_date: Optional[str] = None,
    passengers: int = 1,
) -> str:
    """
    Search for flights using the Kiwi.com MCP (Model Context Protocol).
    Use this for finding actual flight options, prices, and booking links.
    Inputs:
    - origin: City or Airport code (e.g. "LHR", "London")
    - destination: City or Airport code (e.g. "CDG", "Paris")
    - departure_date: Date in "DD/MM/YYYY" format (e.g. "25/12/2024")
    - return_date: Optional return date in "DD/MM/YYYY" format
    - passengers: Number of adults (default 1)
    """
    print(f"  [Tool] Searching flights with Kiwi: {origin} -> {destination}")
    from app.mcp_client import KiwiMCPClient

    # Create a fresh client for this sync call to ensure clean loop handling
    client = KiwiMCPClient()

    try:
        args = {
            "flyFrom": origin,
            "flyTo": destination,
            "departureDate": departure_date,
            "passengers": {"adults": passengers},
        }
        if return_date:
            args["returnDate"] = return_date

        result = client.call_tool_sync("search-flight", args)

        # Parse result
        # The tool returns a list of flights or a summary.
        # Based on schema description: "You should display the returned results in a markdown table format..."
        # But the raw result from call_tool will be the JSON content block

        content = result.get("content", [])
        text_response = ""
        for item in content:
            if item.get("type") == "text":
                text_response += item.get("text", "")

        return text_response or json.dumps(result)

    except Exception as e:
        print(f"  [Error] Kiwi Search failed: {e}")
        return json.dumps({"error": f"Kiwi search failed: {str(e)}"})


# =====================================================================
# 12. CHEAPEST FLIGHT DATES (Amadeus Flight Cheapest Date Search)
# =====================================================================
@tool
def search_cheapest_dates_tool(
    origin: str,
    destination: str,
    departure_date: Optional[str] = None,
    one_way: bool = False,
) -> str:
    """
    Finds the cheapest dates to fly between two cities.
    Great for flexible travelers who want to save money.
    Inputs:
    - origin: IATA code (e.g., "JFK", "LON")
    - destination: IATA code (e.g., "CDG", "BKK")
    - departure_date: Optional rough date (YYYY-MM-DD) to search around
    - one_way: If true, search one-way only (default: round trip)
    Returns: List of date combinations with the cheapest prices.
    """
    print(f"  [Tool] Searching cheapest dates: {origin} -> {destination}")
    from app.amadeus_rate_limiter import get_amadeus_client, amadeus_call

    amadeus = get_amadeus_client()
    if not amadeus:
        return json.dumps({"error": "Amadeus API not configured", "results": []})

    try:
        params = {
            "origin": origin.upper()[:3],
            "destination": destination.upper()[:3],
        }
        if departure_date:
            params["departureDate"] = departure_date
        if one_way:
            params["oneWay"] = "true"

        response = amadeus_call(
            amadeus.shopping.flight_dates.get,
            **params,
        )
        results = []
        for offer in response.data[:10]:
            results.append(
                {
                    "departureDate": offer.get("departureDate", ""),
                    "returnDate": offer.get("returnDate", ""),
                    "price": {
                        "total": offer.get("price", {}).get("total", "N/A"),
                        "currency": offer.get("price", {}).get("currency", "EUR"),
                    },
                    "links": offer.get("links", {}),
                }
            )

        print(f"  [Tool] Found {len(results)} cheapest date options")
        return json.dumps(results, indent=2)
    except Exception as e:
        print(f"  [Tool] Cheapest dates search failed: {e}")
        # Mock Fallback for Test Environment Reliability
        mock_dates = [
            {
                "departureDate": "2024-05-01",
                "returnDate": "2024-05-08",
                "price": {"total": "150.00", "currency": "EUR"},
            },
            {
                "departureDate": "2024-05-15",
                "returnDate": "2024-05-22",
                "price": {"total": "145.00", "currency": "EUR"},
            },
        ]
        return json.dumps(
            {
                "warning": f"Live date search failed ({e}). Showing mock data.",
                "results": mock_dates,
            },
            indent=2,
        )


# =====================================================================
# 6. USER PROFILE (Pinecone)
# =====================================================================
@tool
def get_user_profile(user_id: str) -> dict:
    """
    Retrieves the user's travel profile and preferences from the database.
    Inputs:
    - user_id: The unique identifier for the user (e.g., email address)
    """
    print(f"  [Tool] Fetching profile for user: {user_id}")
    try:
        # Get Pinecone index
        try:
            # Try to get it from global scope if available
            _, index = _get_pinecone_client_and_index()
        except NameError:
            # Fallback if helper is not in scope
            from pinecone import Pinecone
            import os

            api_key = os.getenv("PINECONE_API_KEY")
            index_name = os.getenv("PINECONE_INDEX_NAME")
            if not api_key or not index_name:
                return {}
            pc = Pinecone(api_key=api_key)
            index = pc.Index(index_name)

        if not index:
            return {}

        # Fetch vector by ID from 'user_profiles' namespace
        # Sanitize ID if needed (e.g. email to safe string)
        # We try multiple variations of ID to find a match
        safe_id = user_id.replace("@", "_").replace(".", "_")
        ids_to_fetch = [user_id, f"profile_{safe_id}", safe_id]

        fetch_response = index.fetch(ids=ids_to_fetch, namespace="user_profiles")

        vector_data = None
        for uid in ids_to_fetch:
            if uid in fetch_response.vectors:
                vector_data = fetch_response.vectors[uid]
                print(f"  [Tool] Found profile with ID: {uid}")
                break

        if vector_data:
            metadata = vector_data.get("metadata", {})

            def parse_list_val(val):
                if isinstance(val, list):
                    return val
                if isinstance(val, str):
                    return [x.strip() for x in val.split(",") if x.strip()]
                return []

            # Map to schema
            profile = {
                "user_id": user_id,
                "travel_style": metadata.get("travel_style")
                or metadata.get("travel style"),
                "dietary_needs": parse_list_val(
                    metadata.get("dietary_needs") or metadata.get("dietary needs")
                ),
                "accessibility_needs": parse_list_val(
                    metadata.get("accessibility_needs")
                    or metadata.get("accessibility needs")
                ),
                "interests": parse_list_val(metadata.get("interests")),
                "home_city": metadata.get("home_city") or metadata.get("home city"),
            }
            return profile
        else:
            print(f"  [Tool] User profile not found for {user_id}")
            return {}

    except Exception as e:
        print(f"  [Error] Failed to fetch user profile: {e}")
        return {}
