"""Settings for the dual-LLM title/abstract screening pipeline."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # project root (scripts/ lives one level down)
PROTOCOL = ROOT / "protocol"
RAW = ROOT / "data" / "raw"
DEDUP = ROOT / "data" / "deduplicated"
INPUT = ROOT / "data" / "screening_input"
PILOT = ROOT / "results" / "pilot"
FULL = ROOT / "results" / "full_run"
FINAL = ROOT / "results" / "final"

PROMPT_FILE = PROTOCOL / "bacteria_screening_instructions.txt"
TO_SCREEN = INPUT / "to_screen.csv"
EXCLUDED = INPUT / "excluded_records.csv"
ENV_FILE = ROOT / ".env"  # holds GEMINI_API_KEY and MISTRAL_API_KEY (git-ignored)

# Lisa flips this to True herself after checking the 100 pilot papers by hand.
# While False, `screen` refuses to run on anything beyond the 300 pilot records.
PILOT_APPROVED = True

PROMPT_VERSION = "tiab-v2"
BATCH_SIZE = 20
ABSTRACT_MAX_CHARS = 2500
SEED = 42
PILOT_SIZE = 300
PILOT_MANUAL_SIZE = 100
AUDIT_FRACTION = 0.05
AUDIT_MIN = 150

# Conservative defaults. Replace with ~70% of the real limits of Lisa's account tier
# once they are known (provider dashboards): rpm = requests/min, tpm = tokens/min.
MODELS = {
    "gemini": {
        "id": "gemini-3.1-pro-preview",
        "key_env": "GEMINI_API_KEY",
        "max_concurrent": 4,
        "rpm": 30,
        "tpm": 200_000,
        "thinking_budget": 512,
    },
    "mistral": {
        "id": "mistral-large-4",  # confirmed by check-models
        "key_env": "MISTRAL_API_KEY",
        "max_concurrent": 4,
        "rpm": 30,
        "tpm": 200_000,
    },
}

# USD per 1M tokens (input, output). Fill in from the provider price pages to get cost estimates.
PRICE_PER_M = {"gemini": None, "mistral": None}

MAX_RETRIES = 3
BACKOFF_START = 2.0
BACKOFF_MAX = 60.0
