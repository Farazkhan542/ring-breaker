"""Runtime settings, all overridable with environment variables."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("RB_DATA_DIR", ROOT / "data"))
CACHE_DIR = Path(os.environ.get("RB_CACHE_DIR", ROOT / "cache"))
STATE_DIR = Path(os.environ.get("RB_STATE_DIR", ROOT / "state"))
POLICY_FILE = Path(os.environ.get("RB_POLICY_FILE", ROOT / "ringbreaker" / "policy.yaml"))

# Gemini. Vertex AI is used when GOOGLE_GENAI_USE_VERTEXAI=true (plus GOOGLE_CLOUD_PROJECT/LOCATION);
# otherwise GOOGLE_API_KEY. With neither, or RB_LLM=off, cached/template text is used so the demo always completes.
MODEL_ID = os.environ.get("RB_MODEL_ID", "gemini-3.8-flash")
FALLBACK_MODELS = [m for m in os.environ.get("RB_FALLBACK_MODELS", "gemini-3.7-flash,gemini-2.5-flash").split(",") if m]
LLM_MODE = os.environ.get("RB_LLM", "auto")  # auto | off
LLM_TIMEOUT_S = float(os.environ.get("RB_LLM_TIMEOUT_S", "20"))  # per model attempt
LLM_BUDGET_S = float(os.environ.get("RB_LLM_BUDGET_S", "35"))  # all attempts; then cache, then template
CACHE_FIRST = os.environ.get("RB_CACHE_FIRST", "false").lower() == "true"  # true: instant demo from cache

# Consortium masking key: Secret Manager in production (mounted as env var on Cloud Run).
CONSORTIUM_KEY = os.environ.get("RB_CONSORTIUM_KEY", "local-dev-consortium-key").encode()

# Base URL the orchestrator uses to reach the bank agents' A2A endpoints (same container on Cloud Run).
PORT = int(os.environ.get("PORT", "8080"))
A2A_BASE_URL = os.environ.get("RB_A2A_BASE_URL", f"http://127.0.0.1:{PORT}")

BANKS = ["BANK_A", "BANK_B", "BANK_C"]
LARGE = 3000  # transfers at or above this amount are "large" for red flags and sharing
