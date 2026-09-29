"""The real app with the PricedFake odds provider, for serving over HTTP on 8140.

    bash run.sh -m uvicorn ... does not work with run.sh; use run_api.sh instead.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
sys.argv = [sys.argv[0], "serve"]
from measure_api import app  # noqa: E402,F401  (installs the PricedFake overrides)
