import os
from dotenv import load_dotenv

# Load .env file
load_dotenv()

# Read API Token
WAQI_API_TOKEN = os.getenv("WAQI_API_TOKEN")

if WAQI_API_TOKEN is None:
    raise ValueError("WAQI_API_TOKEN not found in .env file")