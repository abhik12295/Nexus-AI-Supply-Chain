# Deploy NEXUS on Streamlit Community Cloud

Repository: `abhik12295/Nexus-AI-Supply-Chain`

## App settings

- Branch: `main`
- Main file path: `streamlit_app.py`
- Python dependencies: `requirements.txt`
- NEXUS runtime: `embedded`

## Secrets

Open **Advanced settings → Secrets** and paste:

```toml
NEBIUS_API_KEY = "YOUR_NEBIUS_TOKEN_FACTORY_KEY"
NEBIUS_BASE_URL = "https://api.tokenfactory.us-central1.nebius.com/v1/"
NEBIUS_MODEL = "nvidia/nemotron-3-super-120b-a12b"

TAVILY_API_KEY = "YOUR_TAVILY_KEY"
TAVILY_BASE_URL = "https://api.tavily.com"

NEXUS_API_URL = "embedded"
```

Never commit real keys to GitHub.

## Why embedded runtime?

Streamlit Community Cloud launches the Streamlit process, not the local FastAPI command used during development. The embedded NEXUS runtime executes the existing deterministic shipment generation and incident-impact engine in-process, while the FastAPI application remains available in the repository for local/API testing.

## Expected validation

On first load:
- dashboard renders without a localhost API error,
- sidebar shows Nebius key configured,
- sidebar shows Tavily key configured,
- Run Analysis reaches Nemotron,
- Generate Recovery Plan runs the deterministic simulator,
- Challenge Leader retrieves Tavily evidence,
- Final Decision applies the deterministic policy gate.
