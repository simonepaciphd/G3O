import os
from dotenv import load_dotenv

# Load .env explicitly if present
load_dotenv()

def get_env_var(key, default=None, required=False):
    """
    Retrieves an environment variable with optional default value.
    Raises ValueError if a required variable is missing.
    """
    val = os.getenv(key, default)
    if required and val is None:
        raise ValueError(f"Missing required environment variable: {key}")
    return val

# API Keys
# Note: SERPER_API_KEY is required for search operations but not at import time
# The system will use mock data if this key is not provided
SERPER_API_KEY = get_env_var("SERPER_API_KEY", default=None)
OPENAI_API_KEY = get_env_var("OPENAI_API_KEY", default=None)

# Configuration
# Serper.dev endpoint for Google search API
SERPER_ENDPOINT = get_env_var("SERPER_ENDPOINT", default="https://google.serper.dev/search")

# Request timeout in seconds for all HTTP requests
REQUEST_TIMEOUT = int(get_env_var("REQUEST_TIMEOUT", default=30))

# User agent string for web scraping requests
USER_AGENT = get_env_var("USER_AGENT", default="G3O-Observatory/1.0")

# Paths
# Base directory is the parent of the directory containing this config file
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Cache directory for storing downloaded pages and search results
CACHE_DIR = os.path.join(BASE_DIR, "cache")

# Output directory for collected data files
OUTPUTS_DIR = os.path.join(BASE_DIR, "data")