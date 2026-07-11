import sys
from pathlib import Path

# Add project root to sys.path to allow config import
sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from config.database import engine