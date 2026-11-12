"""Entry point that opens the optional Streamlit dashboard."""

import importlib.util
from pathlib import Path
import subprocess
import sys


def main() -> int:
    if importlib.util.find_spec("streamlit") is None:
        print('Dashboard dependencies missing. Install: python -m pip install ".[dashboard]"',
              file=sys.stderr)
        return 1
    script = Path(__file__).with_name("satellite_dashboard.py")
    return subprocess.call([sys.executable, "-m", "streamlit", "run", str(script),
                            "--theme.base", "light", "--theme.primaryColor", "#2B59C3"])


if __name__ == "__main__":
    sys.exit(main())
