
def _get_flight_price_metrics(origin: str, destination: str, departure_date: str, currency: str = "USD") -> Dict:
    """Helper to fetch price metrics from Amadeus or return mock data."""
    try:
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
        print(f"  [Warning] Price analysis failed: {e}")

    # Fallback / Mock
    return {
        "source": "Mock",
        "metrics": [{
             "departureDate": departure_date,
             "priceMetrics": [
                {"quartileRanking": "MINIMUM", "amount": "120", "currencyCode": currency},
                {"quartileRanking": "FIRST", "amount": "180", "currencyCode": currency},
                {"quartileRanking": "MEDIUM", "amount": "250", "currencyCode": currency},
                {"quartileRanking": "THIRD", "amount": "350", "currencyCode": currency},
                {"quartileRanking": "MAXIMUM", "amount": "600", "currencyCode": currency},
            ]
        }]
    }

