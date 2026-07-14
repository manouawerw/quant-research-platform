from dotenv import load_dotenv
load_dotenv()

import os

# ===========================
# API Keys
# ===========================

ALPACA_API_KEY = os.getenv("ALPACA_API_KEY")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Future APIs
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY")
POLYGON_API_KEY = os.getenv("POLYGON_API_KEY")

# ===========================
# Application Settings
# ===========================

DEFAULT_LOOKBACK_DAYS = 365

DEFAULT_INTERVAL = "1Day"

TOP_STOCK_LIMIT = 500

APP_NAME = "Quant Research Platform"

MODEL_VERSION = "v1.0.0"