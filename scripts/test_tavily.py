from __future__ import annotations

from pathlib import Path
import sys

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from services.tavily_service import TavilyConfigurationError, TavilyEvidenceService, TavilySearchError  # noqa: E402


if __name__ == "__main__":
    service = TavilyEvidenceService()
    try:
        result = service.test_connection()
    except (TavilyConfigurationError, TavilySearchError) as exc:
        print(f"Tavily test failed: {exc}")
        raise SystemExit(1)

    print(f"Authenticated + search: {'YES' if result['ok'] else 'NO RESULTS'}")
    print(f"Latency: {result['latency_seconds']}s")
    print(f"Result count: {result['result_count']}")
    print(f"First title: {result['first_title'] or 'n/a'}")
    print(f"First URL: {result['first_url'] or 'n/a'}")
