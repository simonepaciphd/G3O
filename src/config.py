import os
from dotenv import load_dotenv

# Load .env explicitly if present
load_dotenv()

def get_env_var(key, default=None, required=False):
    val = os.getenv(key, default)
    if required and val is None:
        raise ValueError(f"Missing required environment variable: {key}")
    return val

# API Keys
# The assistant will need to provide their own Serper key or use the one in Github Secrets
SERPER_API_KEY = get_env_var("SERPER_API_KEY", required=True)

# Configuration
SERPER_ENDPOINT = get_env_var("SERPER_ENDPOINT", default="https://google.serper.dev/search")
REQUEST_TIMEOUT = int(get_env_var("REQUEST_TIMEOUT", default=30))
USER_AGENT = get_env_var("USER_AGENT", default="G3O-Observatory/1.0")

# Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(BASE_DIR, "cache")
OUTPUTS_DIR = os.path.join(BASE_DIR, "data")
