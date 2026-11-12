"""
propagator.py — Phase 1: Satellite Data Acquisition + SGP4 Propagation

WHAT THIS FILE DOES
--------------------
1. Loads a satellite's orbital state from a Two-Line Element (TLE) set,
   either typed in manually, read from a local file, or fetched live
   from a public catalog (Celestrak) when internet access is available.
2. Wraps Skyfield's EarthSatellite object, which internally runs the
   SGP4 (Simplified General Perturbations 4) propagator.
3. Exposes a simple .state_at(time) method that returns position,
   velocity, altitude, latitude, longitude, and ground speed.

IMPORTANT CONCEPTUAL NOTE (do not skip when explaining this project):
A TLE describes a satellite's ORBITAL STATE (where it is / how it's
moving). It contains ZERO information about the spacecraft's internal
health — no battery voltage, no temperature, no subsystem status.
Any "telemetry" or "health" data elsewhere in this project is either
(a) real telemetry the operator supplies separately, or
(b) clearly-labeled SIMULATED data for demonstration purposes.
Conflating TLE orbital data with spacecraft health is a common and
incorrect assumption — this project explicitly avoids it.
"""

from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from skyfield.api import EarthSatellite, load, wgs84


def validate_tle(line1: str, line2: str) -> None:
    """Reject malformed Two-Line Elements before sending them to SGP4."""
    for prefix, line in (("1 ", line1), ("2 ", line2)):
        if len(line) != 69 or not line.startswith(prefix) or not line[68].isdigit():
            raise ValueError(f"Invalid TLE line {prefix[0]}: expected 69 characters and checksum")
        checksum = sum(int(c) if c.isdigit() else (1 if c == "-" else 0)
                       for c in line[:68]) % 10
        if checksum != int(line[68]):
            raise ValueError(f"TLE line {prefix[0]} checksum mismatch (expected {checksum})")
    if line1[2:7] != line2[2:7]:
        raise ValueError("TLE lines refer to different NORAD satellite IDs")


@dataclass
class SatelliteState:
    """A single snapshot of a satellite's orbital state at one instant."""
    timestamp_utc: datetime
    latitude_deg: float
    longitude_deg: float
    altitude_km: float
    velocity_kms: float          # speed, magnitude of ECI velocity vector
    position_eci_km: tuple       # (x, y, z) in km, Earth-Centered Inertial
    velocity_eci_kms: tuple      # (vx, vy, vz) in km/s, ECI frame
    distance_from_earth_center_km: float


class SatelliteTracker:
    """
    Loads a TLE (from string, file, or Celestrak) and provides
    position/velocity queries at any point in time via SGP4.
    """

    def __init__(self, name: str, line1: str, line2: str):
        self.name = name
        self.line1 = line1.strip()
        self.line2 = line2.strip()
        validate_tle(self.line1, self.line2)
        self.ts = load.timescale()
        self.satellite = EarthSatellite(self.line1, self.line2, self.name, self.ts)

    # ------------------------------------------------------------------
    # Constructors — the three ways a user can supply orbital data
    # ------------------------------------------------------------------

    @classmethod
    def from_manual_tle(cls, name: str, line1: str, line2: str) -> "SatelliteTracker":
        """User types in a TLE by hand."""
        return cls(name, line1, line2)

    @classmethod
    def from_file(cls, filepath: str, satellite_name: Optional[str] = None) -> "SatelliteTracker":
        """
        Load a TLE from a local text file.
        File format (standard 3-line TLE):
            SATELLITE NAME
            1 25544U 98067A   ...
            2 25544  51.6400 ...
        If the file contains multiple satellites, `satellite_name` selects one.
        """
        with open(filepath, "r") as f:
            lines = [ln.rstrip("\n") for ln in f if ln.strip()]

        # Parse groups of 3 lines: name, line1, line2
        satellites = {}
        i = 0
        while i < len(lines) - 1:
            if lines[i].startswith("1 ") and i + 1 < len(lines):
                # No name line preceding — shouldn't normally happen
                i += 1
                continue
            if i + 2 < len(lines) and lines[i + 1].startswith("1 ") and lines[i + 2].startswith("2 "):
                nm = lines[i].strip()
                satellites[nm] = (lines[i + 1], lines[i + 2])
                i += 3
            else:
                i += 1

        if not satellites:
            raise ValueError(f"No valid TLE sets found in {filepath}")

        if satellite_name:
            if satellite_name not in satellites:
                raise KeyError(
                    f"'{satellite_name}' not found in file. Available: {list(satellites.keys())}"
                )
            l1, l2 = satellites[satellite_name]
            return cls(satellite_name, l1, l2)

        # Default: first satellite in the file
        nm, (l1, l2) = next(iter(satellites.items()))
        return cls(nm, l1, l2)

    @classmethod
    def from_celestrak(cls, norad_id: int, timeout: float = 10.0) -> "SatelliteTracker":
        """
        Fetch a live, current TLE from Celestrak by NORAD catalog ID.
        Requires an internet connection. Celestrak is a long-standing,
        widely trusted public source for TLE data.
        """
        import requests  # local import: only needed for this online path

        url = (
            "https://celestrak.org/NORAD/elements/gp.php"
            f"?CATNR={norad_id}&FORMAT=TLE"
        )
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
        lines = [ln for ln in resp.text.strip().splitlines() if ln.strip()]
        if len(lines) < 3:
            raise ValueError(
                f"Could not retrieve a valid TLE for NORAD ID {norad_id}. "
                "Check the ID or your internet connection."
            )
        name, l1, l2 = lines[0].strip(), lines[1], lines[2]
        return cls(name, l1, l2)

    # ------------------------------------------------------------------
    # Core computation
    # ------------------------------------------------------------------

    def state_at(self, when: Optional[datetime] = None) -> SatelliteState:
        """
        Compute the satellite's full state at a given UTC datetime.
        If `when` is None, uses the current time.

        Explanation of the math:
        - Skyfield calls the SGP4 propagator with the TLE's mean elements
          and the elapsed time since the TLE epoch, returning an ECI
          (Earth-Centered Inertial, true-equator-mean-equinox-of-date)
          position/velocity vector.
        - `wgs84.geographic_position_of()` converts that ECI vector into
          geodetic latitude/longitude/altitude using the WGS-84 reference
          ellipsoid (accounts for Earth's equatorial bulge, unlike a
          simple spherical-Earth assumption).
        """
        if when is None:
            when = datetime.now(timezone.utc)
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)

        t = self.ts.from_datetime(when)
        geocentric = self.satellite.at(t)

        # ECI position & velocity (km, km/s)
        pos_km = geocentric.position.km
        vel_kms = geocentric.velocity.km_per_s

        # Geodetic subpoint (WGS-84)
        subpoint = wgs84.geographic_position_of(geocentric)

        speed = float((vel_kms[0] ** 2 + vel_kms[1] ** 2 + vel_kms[2] ** 2) ** 0.5)
        dist_from_center = float((pos_km[0] ** 2 + pos_km[1] ** 2 + pos_km[2] ** 2) ** 0.5)

        return SatelliteState(
            timestamp_utc=when,
            latitude_deg=subpoint.latitude.degrees,
            longitude_deg=subpoint.longitude.degrees,
            altitude_km=subpoint.elevation.km,
            velocity_kms=speed,
            position_eci_km=tuple(pos_km),
            velocity_eci_kms=tuple(vel_kms),
            distance_from_earth_center_km=dist_from_center,
        )

    def __repr__(self) -> str:
        return f"SatelliteTracker(name={self.name!r})"
