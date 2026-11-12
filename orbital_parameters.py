"""
orbital_parameters.py — Phase 1 (basic set) / extended in Phase 2

Extracts the classical Keplerian orbital elements directly from the
TLE's mean-element fields. These are the raw inputs SGP4 propagates
from, so reading them is fast and doesn't require calling the propagator.

KEPLERIAN ELEMENTS EXPLAINED
-----------------------------
- Semi-major axis (a): half the longest diameter of the orbital ellipse.
  Determines orbital period via Kepler's Third Law: T = 2π√(a³/μ),
  where μ (mu) = GM_earth = 398,600.4418 km³/s².
- Eccentricity (e): 0 = perfect circle, closer to 1 = more elongated ellipse.
- Inclination (i): angle between the orbital plane and Earth's equatorial
  plane. 0° = equatorial orbit, 90° = polar orbit.
- RAAN (Ω): Right Ascension of the Ascending Node — where the orbit
  crosses the equatorial plane going north, measured from the vernal
  equinox direction.
- Argument of perigee (ω): angle from the ascending node to perigee,
  measured in the direction of motion.
- Mean anomaly (M): a time-like angle describing where the satellite is
  along its orbit at the TLE epoch (0° = at perigee).
- Mean motion (n): revolutions per day.
"""

from __future__ import annotations
from dataclasses import dataclass

MU_EARTH_KM3_S2 = 398600.4418  # standard gravitational parameter of Earth
EARTH_RADIUS_KM = 6378.137     # WGS-84 equatorial radius


@dataclass
class OrbitalElements:
    semi_major_axis_km: float
    eccentricity: float
    inclination_deg: float
    raan_deg: float
    arg_perigee_deg: float
    mean_anomaly_deg: float
    mean_motion_rev_per_day: float
    orbital_period_minutes: float
    apogee_altitude_km: float
    perigee_altitude_km: float


def extract_orbital_elements(satellite) -> OrbitalElements:
    """
    Given a Skyfield EarthSatellite object, extract and derive the
    classical orbital elements from its underlying SGP4 model.
    """
    model = satellite.model  # the underlying sgp4 satrec object

    eccentricity = model.ecco
    inclination_deg = model.inclo * 180.0 / 3.141592653589793
    raan_deg = model.nodeo * 180.0 / 3.141592653589793
    arg_perigee_deg = model.argpo * 180.0 / 3.141592653589793
    mean_anomaly_deg = model.mo * 180.0 / 3.141592653589793

    # Mean motion from the model is in radians/minute; convert to rev/day
    mean_motion_rad_per_min = model.no_kozai
    mean_motion_rev_per_day = mean_motion_rad_per_min * (1440.0 / (2 * 3.141592653589793))

    # Kepler's Third Law, rearranged to solve for semi-major axis from
    # mean motion (n in rad/s): a = (mu / n^2)^(1/3)
    n_rad_per_sec = mean_motion_rad_per_min / 60.0
    semi_major_axis_km = (MU_EARTH_KM3_S2 / (n_rad_per_sec ** 2)) ** (1.0 / 3.0)

    orbital_period_minutes = 1440.0 / mean_motion_rev_per_day

    apogee_radius_km = semi_major_axis_km * (1 + eccentricity)
    perigee_radius_km = semi_major_axis_km * (1 - eccentricity)
    apogee_altitude_km = apogee_radius_km - EARTH_RADIUS_KM
    perigee_altitude_km = perigee_radius_km - EARTH_RADIUS_KM

    return OrbitalElements(
        semi_major_axis_km=semi_major_axis_km,
        eccentricity=eccentricity,
        inclination_deg=inclination_deg,
        raan_deg=raan_deg,
        arg_perigee_deg=arg_perigee_deg,
        mean_anomaly_deg=mean_anomaly_deg,
        mean_motion_rev_per_day=mean_motion_rev_per_day,
        orbital_period_minutes=orbital_period_minutes,
        apogee_altitude_km=apogee_altitude_km,
        perigee_altitude_km=perigee_altitude_km,
    )
