"""Pytest setup: required environment variables and the src path."""

import os
import sys
from pathlib import Path

from cryptography.fernet import Fernet

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"

# cleankoda.core.config reads these when it is imported
os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode())
os.environ.setdefault("WORKSPACE", str(PROJECT_ROOT / "workspace"))
os.environ.setdefault("DEPLOYMENT_MODE", "ON_PREMISE")

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
