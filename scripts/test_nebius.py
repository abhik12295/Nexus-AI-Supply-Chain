from __future__ import annotations

from pathlib import Path
import sys

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from services.nemotron_service import NemotronConfigurationError, NemotronService  # noqa: E402


def main() -> None:
    service = NemotronService()
    print(f"Model: {service.model}")
    print(f"Endpoint: {service.base_url}")

    try:
        result = service.test_connection()
    except NemotronConfigurationError as exc:
        print(f"CONFIG ERROR: {exc}")
        raise SystemExit(2) from exc
    except Exception as exc:
        print(f"RUNTIME ERROR: {type(exc).__name__}: {exc}")
        raise SystemExit(1) from exc

    print(f"Authenticated + inference: {'YES' if result['ok'] else 'UNEXPECTED RESPONSE'}")
    print(f"Response: {result['response']}")
    print(f"Latency: {result['latency_seconds']}s")
    print(f"Total tokens: {result['total_tokens']}")


if __name__ == "__main__":
    main()
