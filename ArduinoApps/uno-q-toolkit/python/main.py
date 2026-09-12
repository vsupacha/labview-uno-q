"""Arduino App Lab entry point for the UNO Q toolkit app."""

from __future__ import annotations

import sys
from pathlib import Path

# App Lab launches this file from the python directory; include the app root
# so the gateway module can be shared with local unit tests.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from arduino.app_utils import App
from gateway.app import web_ui


if __name__ == "__main__":
    App.run()
