"""
app.py — Phase 1: Basic Satellite Tracker (CLI)

Run this to confirm Phase 1 works before moving on to Phase 2
(orbital analysis + 3D visualization).

USAGE
-----
    python app.py                     # prints the first satellite using sample TLEs
    python app.py --norad 25544       # fetch ISS live from Celestrak
    python app.py --file path.txt --name "ISS (ZARYA)"

WHAT PHASE 1 DEMONSTRATES
--------------------------
- Loading a TLE (manual / file / live)
- Propagating it with SGP4 via Skyfield
- Reporting: position (ECI), latitude/longitude, altitude, velocity
- Reporting basic orbital elements (semi-major axis, eccentricity,
  inclination, period, apogee, perigee)
"""

import argparse
from datetime import datetime, timezone
from pathlib import Path

from satellite_tracking.orbit.propagator import SatelliteTracker
from satellite_tracking.orbit.orbital_parameters import extract_orbital_elements

SAMPLE_FILE = Path(__file__).with_name("sample_tles.txt")


def print_report(tracker: SatelliteTracker, when: datetime) -> None:
    state = tracker.state_at(when)
    elements = extract_orbital_elements(tracker.satellite)

    print("\n" + "=" * 60)
    print(f" SATELLITE: {tracker.name}")
    print("=" * 60)
    print(f" Time (UTC):            {state.timestamp_utc.isoformat()}")
    print(f" Latitude:              {state.latitude_deg:.4f} deg")
    print(f" Longitude:             {state.longitude_deg:.4f} deg")
    print(f" Altitude:              {state.altitude_km:.2f} km")
    print(f" Velocity:              {state.velocity_kms:.4f} km/s")
    print(f" ECI position (x,y,z):  {tuple(round(float(v), 1) for v in state.position_eci_km)} km")
    print(f" ECI velocity (vx,vy,vz): {tuple(round(float(v), 4) for v in state.velocity_eci_kms)} km/s")
    print(f" Distance from center:  {state.distance_from_earth_center_km:.2f} km")
    print("-" * 60)
    print(" ORBITAL ELEMENTS")
    print("-" * 60)
    print(f" Semi-major axis:       {elements.semi_major_axis_km:.2f} km")
    print(f" Eccentricity:          {elements.eccentricity:.6f}")
    print(f" Inclination:           {elements.inclination_deg:.4f} deg")
    print(f" RAAN:                  {elements.raan_deg:.4f} deg")
    print(f" Argument of perigee:   {elements.arg_perigee_deg:.4f} deg")
    print(f" Mean anomaly:          {elements.mean_anomaly_deg:.4f} deg")
    print(f" Mean motion:           {elements.mean_motion_rev_per_day:.6f} rev/day")
    print(f" Orbital period:        {elements.orbital_period_minutes:.2f} minutes")
    print(f" Apogee altitude:       {elements.apogee_altitude_km:.2f} km")
    print(f" Perigee altitude:      {elements.perigee_altitude_km:.2f} km")
    print("=" * 60)
    print(" NOTE: This is orbital-state data derived from a TLE via SGP4.")
    print(" It does NOT represent spacecraft health/telemetry.")
    print("=" * 60 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Phase 1 Satellite Tracker")
    parser.add_argument("--norad", type=int, help="Fetch live TLE by NORAD ID (needs internet)")
    parser.add_argument("--file", type=str, help="Path to a TLE file")
    parser.add_argument("--name", type=str, help="Satellite name to select from file")
    parser.add_argument("--at", default="auto", help="auto (default), now, epoch, or ISO-8601 date/time")
    args = parser.parse_args()

    if args.norad:
        print(f"Fetching live TLE for NORAD ID {args.norad} from Celestrak...")
        tracker = SatelliteTracker.from_celestrak(args.norad)
    elif args.file:
        tracker = SatelliteTracker.from_file(args.file, satellite_name=args.name)
    else:
        print(f"No source specified — using sample data: {SAMPLE_FILE}")
        tracker = SatelliteTracker.from_file(str(SAMPLE_FILE), satellite_name=args.name)

    epoch = tracker.satellite.epoch.utc_datetime()
    now = datetime.now(timezone.utc)
    age_days = abs((now - epoch).total_seconds()) / 86400
    if args.at == "auto":
        when = epoch if age_days > 14 else now
    elif args.at == "now":
        when = now
    elif args.at == "epoch":
        when = epoch
    else:
        try:
            when = datetime.fromisoformat(args.at.replace("Z", "+00:00"))
        except ValueError as exc:
            parser.error(f"Invalid --at time: {exc}")
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        when = when.astimezone(timezone.utc)

    if abs((when - epoch).total_seconds()) / 86400 > 14:
        print("WARNING: The TLE is over 14 days from the requested time. "
              "For an accurate current position, fetch a fresh TLE using --norad.")
    elif args.at == "auto" and age_days > 14:
        print("NOTE: The bundled TLE is old; using its February 2024 epoch for a meaningful demonstration.")

    print_report(tracker, when)
