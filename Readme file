# Satellite Tracking & Health Monitoring System

A pip-installable Python project combining your three uploaded tools:

1. **Satellite tracker** — command-line satellite coordinates, velocity and orbital elements using Skyfield/SGP4.
2. **Interactive dashboard** — Streamlit/Plotly orbit views, ground passes, simulated telemetry, anomaly detection and fleet comparison.
3. **PDF report generator** — six-page PDF from a standalone, Python-standard-library implementation of near-Earth SGP4 and monitoring. No extra dependencies for the report itself.

**Important:** Orbital data in a TLE does **not** contain real spacecraft health telemetry. Health values and faults shown by the dashboard and report are **SIMULATED**, for educational demonstration.

## 1. Install (Windows PowerShell)

Install Python 3.10+ from [python.org](https://www.python.org/downloads/). During installation select **Add Python to PATH**. Extract this entire ZIP file, then open PowerShell inside the extracted `satellite-tracking-system` directory.

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install ".[all]"
```

If PowerShell blocks activation, use Command Prompt instead:

```bat
py -m venv .venv
.venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install ".[all]"
```

For macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install ".[all]"
```

`[all]` installs all application and testing dependencies. If you only need basic tracking and reports, `python -m pip install .` is smaller. To add the dashboard later, use `python -m pip install ".[dashboard]"` from the project directory.

## 2. Run each tool

Run these commands from the activated environment, in any working directory after installation:

| Tool | Command | Result |
|---|---|---|
| Command-line tracker | `satellite-track` | Position, velocity and orbital-element readout in terminal |
| Interactive dashboard | `satellite-dashboard` | Local web app, usually at `http://localhost:8501` |
| PDF report | `satellite-report --out my_report.pdf` | Saves a six-page PDF into the current folder |

Useful examples:

```powershell
satellite-track --name "ISS (ZARYA)"
satellite-track --norad 25544 --at now
satellite-track --file my_tles.txt --name "NOAA 19" --at epoch

satellite-dashboard

satellite-report --sat "ISS (ZARYA)" --station "SRM Kattankulathur" --hours 24 --out iss_report.pdf
satellite-report --norad 25544 --at now --out live_iss.pdf
```

You can also run the tracker with `python app.py` or `python -m satellite_tracking`, and the dashboard with `python -m satellite_tracking.launcher`. Press `Ctrl+C` to stop the dashboard server.

### TLE age and internet access

The bundled three sample satellites use an **illustrative TLE epoch of 14 February 2024**. They are appropriate for historical demonstrations, **not** for predicting their actual positions in November 2026. The tracker automatically uses the bundled TLE's historical epoch when it is stale; the dashboard and PDF generator do the same. `--at now` deliberately forces a current-time calculation, but the result is unreliable with old TLEs.

For current positions, first fetch a fresh TLE with `--norad` or supply an up-to-date local file with `--file` (tracker) / `--tle` (PDF). Live fetching needs an internet connection to [CelesTrak](https://celestrak.org).

The PDF report uses a near-Earth-specific educational SGP4 implementation. It does not support deep-space TLEs (orbital periods of 225 minutes or longer); for those, use Skyfield in the tracker instead.

## 3. Check for errors

```powershell
python -m pytest -q
python -m compileall -q satellite_tracking
satellite-track --help
satellite-report --help
```

If you want to build an installable wheel file:

```powershell
python -m pip install build
python -m build
```

The wheel is created in `dist/`. Install it on another computer with:

```powershell
python -m pip install "dist/abhay_satellite_tracking-1.0.0-py3-none-any.whl[all]"
```

Or install the ZIP folder directly after extracting it using `python -m pip install ".[all]"`.

## 4. Project organization

```text
satellite-tracking-system/
  pyproject.toml                 # pip metadata and commands
  app.py                         # legacy CLI launcher
  satellite_tracking/
    cli.py                       # satellite-track
    launcher.py                  # satellite-dashboard
    satellite_dashboard.py       # Streamlit app
    satellite_report.py          # satellite-report
    sample_tles.txt              # bundled historical examples
    orbit/
      propagator.py              # Skyfield orbit propagation
      orbital_parameters.py      # orbital elements
  tests/
    test_orbit.py
    test_applications.py
```

## Common problems

- **`satellite-track` not recognized:** Activate `.venv` or use `python -m satellite_tracking`.
- **`ModuleNotFoundError`:** Run `python -m pip install ".[all]"` in the project directory with the virtual environment activated.
- **Dashboard won't open:** Run `satellite-dashboard` and manually open `http://localhost:8501` in your browser; check firewall and the terminal for errors.
- **Wrong or suspicious orbital altitude:** Check the age of the TLE and update it. Stale TLEs become unreliable.
- **TLE checksum mismatch:** The input TLE line was mistyped or corrupted. Each line must have exactly 69 characters and a valid checksum.
- **Unable to download live TLE:** Try the offline sample without `--norad`, or provide a current TLE file.

## Tests and accuracy caveat

Tests use a fixed UTC instant close to the sample TLE epoch, so they do not degrade with the real calendar date. Plausibility checks are educational sanity tests, not precise validation against independent orbit truth data. For scientific work, compare output from the same recent TLE at the same timestamp with a separately verified SGP4 implementation and document numerical tolerances.
