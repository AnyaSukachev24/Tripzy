"""
Amadeus Rate Limiter & Shared Client
=====================================
Provides a singleton, rate-limited Amadeus client for all API calls.

Rate limits (Amadeus Self-Service):
  - Test:       10 req/sec, min 100ms between requests
  - Production: 40 req/sec
"""
import os
import time
import threading
from typing import Optional


class AmadeusRateLimiter:
    """Thread-safe rate limiter for Amadeus API calls."""

    _instance: Optional["AmadeusRateLimiter"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "AmadeusRateLimiter":
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._initialized = True
        self._request_lock = threading.Lock()
        self._last_request_time: float = 0.0

        # Detect environment (test vs production)
        self._is_production = os.getenv("AMADEUS_PRODUCTION", "false").lower() == "true"
        self._min_interval = 0.1 if not self._is_production else 0.025  # 100ms test, 25ms prod
        self._max_rps = 10 if not self._is_production else 40

        # Sliding window for per-second tracking
        self._request_times: list[float] = []

    def wait(self) -> None:
        """Block until it's safe to make the next API request."""
        with self._request_lock:
            now = time.monotonic()

            # 1. Enforce minimum interval between requests
            elapsed = now - self._last_request_time
            if elapsed < self._min_interval:
                sleep_time = self._min_interval - elapsed
                time.sleep(sleep_time)
                now = time.monotonic()

            # 2. Enforce max requests per second (sliding window)
            cutoff = now - 1.0
            self._request_times = [t for t in self._request_times if t > cutoff]
            if len(self._request_times) >= self._max_rps:
                oldest = self._request_times[0]
                sleep_time = 1.0 - (now - oldest) + 0.01  # small buffer
                if sleep_time > 0:
                    time.sleep(sleep_time)
                    now = time.monotonic()

            self._last_request_time = now
            self._request_times.append(now)


# Singleton accessor
_rate_limiter = AmadeusRateLimiter()


def get_rate_limiter() -> AmadeusRateLimiter:
    """Get the singleton rate limiter instance."""
    return _rate_limiter


# --- Shared Amadeus Client ---
_amadeus_client = None
_client_lock = threading.Lock()


def get_amadeus_client():
    """
    Returns a shared, rate-limited Amadeus client.
    Returns None if API keys are not configured.
    """
    global _amadeus_client
    api_key = os.getenv("AMADEUS_API_KEY")
    api_secret = os.getenv("AMADEUS_API_SECRET")

    if not api_key or not api_secret:
        return None

    with _client_lock:
        if _amadeus_client is None:
            try:
                from amadeus import Client
                hostname = "production" if os.getenv("AMADEUS_PRODUCTION", "false").lower() == "true" else "test"
                _amadeus_client = Client(
                    client_id=api_key,
                    client_secret=api_secret,
                    hostname=hostname,
                )
                print(f"  [Amadeus] Client initialized ({hostname} environment)")
            except Exception as e:
                print(f"  [Amadeus] Failed to initialize client: {e}")
                return None
    return _amadeus_client


def amadeus_call(func, *args, **kwargs):
    """
    Execute an Amadeus API call with rate limiting.
    
    Usage:
        result = amadeus_call(client.shopping.flight_offers_search.get, **params)
    """
    _rate_limiter.wait()
    return func(*args, **kwargs)
