"""Run adapter tests in Isaac Sim Python without starting Kit."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.aspire.bootstrap import setup_paths
setup_paths()
import pytest
if __name__ == "__main__":
    raise SystemExit(pytest.main(["tests/test_aspire.py", "tests/test_full_aspire.py", "tests/test_full_aspire_recovery.py", "-q", *sys.argv[1:]]))
