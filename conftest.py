"""Root conftest.py — adds src/ to sys.path so tests can import modules directly.

e.g. ``from ingestion.ttl_policy import DataType`` works without ``src.`` prefix.
"""

import sys
import os

# Add src/ to path so test imports work without the src. prefix
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
