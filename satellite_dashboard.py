"""
satellite_dashboard.py
======================
Satellite Tracking & Health Monitoring System — single-file version.

Run it with:
    pip install skyfield numpy pandas scikit-learn plotly streamlit requests
    python satellite_dashboard.py

A browser tab opens with five screens:
    1. Tracking          3D globe, ground track, live position readouts
    2. Passes            passes over a ground station + sky plot
    3. Telemetry/health  SIMULATED telemetry, limit checks, ML anomaly detection
    4. Fleet             all satellites together, merged pass schedule
    5. Orbital elements  Keplerian elements read from the TLE

IMPORTANT: a TLE describes only the ORBIT. It contains no battery, thermal or
subsystem data. All health values here are SIMULATED from the orbit geometry
and are labelled as such on screen.

Coastlines (Natural Earth 1:110m) are downloaded once from the world-atlas
package on jsDelivr and cached next to this file. Without internet the maps
still work, just without coastlines.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Self-launch: `python satellite_dashboard.py` restarts itself under Streamlit
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    try:
        from streamlit.runtime import exists as _running_in_streamlit
    except ImportError:
        sys.exit("Streamlit is not installed. Run:\n  pip install skyfield numpy pandas "
                 "scikit-learn plotly streamlit requests")
    if not _running_in_streamlit():
        sys.exit(subprocess.call([sys.executable, "-m", "streamlit", "run", __file__,
                                  "--theme.base", "light",
                                  "--theme.primaryColor", "#2B59C3",
                                  "--theme.backgroundColor", "#F3F5F2",
                                  "--theme.secondaryBackgroundColor", "#FFFFFF",
                                  "--theme.textColor", "#1B2A3A"]))

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots
from skyfield.api import EarthSatellite, load, wgs84
from skyfield.framelib import itrs
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

# ===========================================================================
# 0. Constants and sample data
# ===========================================================================
MU = 398600.4418             # km^3/s^2, Earth's gravitational parameter
R_E = 6378.137               # km, WGS-84 equatorial radius
STALE_TLE_DAYS = 14.0        # beyond this SGP4 positions are unreliable

# Illustrative sample TLEs (epoch 14 Feb 2024). Checksums are valid.
SAMPLE_TLES = """\
ISS (ZARYA)
1 25544U 98067A   26311.46585590  .00014112  00000+0  26146-3 0  9995
2 25544  51.6322 311.0744 0007266 358.6454   1.4513 15.49241650593960
HUBBLE SPACE TELESCOPE
1 20580U 90037B   26311.89641212  .00008265  00000+0  25055-3 0  9990
2 20580  28.4716 177.2871 0001867 321.5230  38.5233 15.32215546810621
NOAA 19
1 33591U 09005A   26312.10076558  .00000048  00000+0  49118-4 0  9999
2 33591  98.9383  22.9701 0013415 347.2895  12.7937 14.13492647914819
"""

# Colours
INK, MUTED, PANEL, GRID = "#1B2A3A", "#5C6B7A", "#FFFFFF", "#DCE1DA"
EARTH, LAND = "#D9E4EC", "#8FA3B5"
ECLIPSE = "rgba(27,42,58,0.09)"
NOMINAL, CAUTION, ALERT, STATION_C = "#2E7D4F", "#C98A12", "#C0392B", "#8A3FA0"
SAT_COLORS = {"ISS (ZARYA)": "#2B59C3", "HUBBLE SPACE TELESCOPE": "#B5502C", "NOAA 19": "#2E7D4F"}

_TS = load.timescale()


# ===========================================================================
# 1. TLE loading and SGP4 propagation
# ===========================================================================
def tle_checksum(line: str) -> int:
    """Modulo-10 checksum: sum of digits, '-' counts as 1."""
    return sum(int(c) if c.isdigit() else (1 if c == "-" else 0) for c in line[:68]) % 10


def validate_tle(l1: str, l2: str) -> None:
    for num, line in (("1", l1), ("2", l2)):
        if len(line) != 69 or not line.startswith(num + " "):
            raise ValueError(f"TLE line {num} is malformed.")
        if int(line[68]) != tle_checksum(line):
            raise ValueError(f"TLE line {num} checksum mismatch.")


def parse_tles(text: str) -> dict:
    lines = [ln.rstrip() for ln in text.splitlines() if ln.strip()]
    out, i = {}, 0
    while i < len(lines) - 2:
        if lines[i + 1].startswith("1 ") and lines[i + 2].startswith("2 "):
            out[lines[i].strip()] = (lines[i + 1], lines[i + 2])
            i += 3
        else:
            i += 1
    return out


def as_utc(when) -> datetime:
    if isinstance(when, pd.Timestamp):
        when = when.to_pydatetime()
    return when.replace(tzinfo=timezone.utc) if when.tzinfo is None else when.astimezone(timezone.utc)


class Satellite:
    """One satellite: TLE + SGP4 propagator (via Skyfield)."""

    def __init__(self, name: str, l1: str, l2: str):
        validate_tle(l1.strip(), l2.strip())
        self.name, self.line1, self.line2 = name, l1.strip(), l2.strip()
        self.sat = EarthSatellite(self.line1, self.line2, name, _TS)

    @classmethod
    def from_celestrak(cls, norad_id: int) -> "Satellite":
        import requests
        url = f"https://celestrak.org/NORAD/elements/gp.php?CATNR={norad_id}&FORMAT=TLE"
        lines = [ln for ln in requests.get(url, timeout=10).text.splitlines() if ln.strip()]
        if len(lines) < 3:
            raise ValueError(f"No TLE returned for NORAD {norad_id}.")
        return cls(lines[0].strip(), lines[1], lines[2])

    @property
    def epoch(self) -> datetime:
        return self.sat.epoch.utc_datetime()

    @property
    def norad(self) -> int:
        return int(self.sat.model.satnum)

    def age_days(self, when=None) -> float:
        when = as_utc(when or datetime.now(timezone.utc))
        return (when - self.epoch).total_seconds() / 86400

    def is_stale(self, when=None) -> bool:
        return abs(self.age_days(when)) > STALE_TLE_DAYS

    def times(self, start, hours, step_s):
        t0 = _TS.from_datetime(as_utc(start))
        return _TS.tt_jd(t0.tt + np.arange(0, hours * 3600 + 1e-9, step_s) / 86400)

    def elements(self) -> dict:
        m = self.sat.model
        n = m.no_kozai / 60.0                              # rad/s
        a = (MU / n ** 2) ** (1 / 3)                       # Kepler's third law
        rev_day = m.no_kozai * 1440 / (2 * np.pi)
        return {"Semi-major axis": f"{a:.2f} km", "Eccentricity": f"{m.ecco:.6f}",
                "Inclination": f"{np.degrees(m.inclo):.4f}°", "RAAN": f"{np.degrees(m.nodeo):.4f}°",
                "Argument of perigee": f"{np.degrees(m.argpo):.4f}°",
                "Mean anomaly": f"{np.degrees(m.mo):.4f}°", "Mean motion": f"{rev_day:.6f} rev/day",
                "Orbital period": f"{1440 / rev_day:.2f} min",
                "Apogee altitude": f"{a * (1 + m.ecco) - R_E:.2f} km",
                "Perigee altitude": f"{a * (1 - m.ecco) - R_E:.2f} km",
                "_period_min": 1440 / rev_day, "_inc": np.degrees(m.inclo)}


# ===========================================================================
# 2. Orbit time series, sun position and eclipse
# ===========================================================================
def sun_unit_vector(jd) -> np.ndarray:
    """Low-precision solar direction (Astronomical Almanac), shape (3, N)."""
    n = np.asarray(jd, float) - 2451545.0
    L = np.radians((280.460 + 0.9856474 * n) % 360)
    g = np.radians((357.528 + 0.9856003 * n) % 360)
    lam = L + np.radians(1.915) * np.sin(g) + np.radians(0.020) * np.sin(2 * g)
    eps = np.radians(23.439 - 0.0000004 * n)
    return np.array([np.cos(lam), np.cos(eps) * np.sin(lam), np.sin(eps) * np.sin(lam)]).reshape(3, -1)


def is_sunlit(r, jd) -> np.ndarray:
    """Cylindrical Earth-shadow test."""
    s = sun_unit_vector(jd)
    proj = np.sum(r * s, axis=0)
    perp = np.linalg.norm(r - proj * s, axis=0)
    return ~((proj < 0) & (perp < R_E))


def orbit_timeseries(sat: Satellite, start, hours=24.0, step_s=60.0) -> pd.DataFrame:
    t = sat.times(start, hours, step_s)
    geo = sat.sat.at(t)
    r, v = geo.position.km, geo.velocity.km_per_s
    ecef = geo.frame_xyz(itrs).km
    sub = wgs84.geographic_position_of(geo)
    h = np.cross(r.T, v.T).T
    h /= np.linalg.norm(h, axis=0)
    return pd.DataFrame({
        "time_utc": pd.to_datetime(t.utc_datetime()),
        "x_ecef_km": ecef[0], "y_ecef_km": ecef[1], "z_ecef_km": ecef[2],
        "lat_deg": sub.latitude.degrees, "lon_deg": sub.longitude.degrees,
        "alt_km": sub.elevation.km, "speed_kms": np.linalg.norm(v, axis=0),
        "sunlit": is_sunlit(r, t.ut1),
        "beta_deg": np.degrees(np.arcsin(np.clip(np.sum(h * sun_unit_vector(t.ut1), axis=0), -1, 1))),
    })


def orbit_summary(df: pd.DataFrame) -> dict:
    lit = df.sunlit.to_numpy()
    spans, start = [], None
    for i, s in enumerate(lit):
        if not s and start is None:
            start = i
        elif s and start is not None:
            spans.append(i - start)
            start = None
    step = (df.time_utc.iloc[1] - df.time_utc.iloc[0]).total_seconds() / 60
    return {"min_alt": df.alt_km.min(), "max_alt": df.alt_km.max(), "sunlit": lit.mean(),
            "eclipses": len(spans), "eclipse_min": np.median(spans) * step if spans else 0.0,
            "beta": df.beta_deg.mean()}


def break_antimeridian(lon, lat):
    lon, lat = np.asarray(lon, float), np.asarray(lat, float)
    j = np.where(np.abs(np.diff(lon)) > 180)[0] + 1
    return np.insert(lon, j, np.nan), np.insert(lat, j, np.nan)


# ===========================================================================
# 3. Ground stations and pass prediction
# ===========================================================================
@dataclass(frozen=True)
class GroundStation:
    name: str
    lat: float
    lon: float
    alt_m: float = 0.0
    mask_deg: float = 10.0

    @property
    def topos(self):
        return wgs84.latlon(self.lat, self.lon, elevation_m=self.alt_m)


STATIONS = {
    "SRM Kattankulathur": GroundStation("SRM Kattankulathur", 12.8230, 80.0444, 45),
    "ISTRAC Bengaluru": GroundStation("ISTRAC Bengaluru", 13.0346, 77.5116, 900),
    "Svalbard (SvalSat)": GroundStation("Svalbard (SvalSat)", 78.2298, 15.4078, 500, 5.0),
}


def predict_passes(sat: Satellite, gs: GroundStation, start, hours=24.0) -> pd.DataFrame:
    start = as_utc(start)
    t0, t1 = _TS.from_datetime(start), _TS.from_datetime(start + timedelta(hours=hours))
    times, events = sat.sat.find_events(gs.topos, t0, t1, altitude_degrees=gs.mask_deg)
    diff = sat.sat - gs.topos
    rows, rise, culm = [], None, None
    for t, ev in zip(times, events):
        if ev == 0:
            rise, culm = t, None
        elif ev == 1 and rise is not None:
            culm = t
        elif ev == 2 and rise is not None:
            culm = culm if culm is not None else rise
            rows.append({"satellite": sat.name,
                         "rise_utc": rise.utc_datetime(), "culmination_utc": culm.utc_datetime(),
                         "set_utc": t.utc_datetime(),
                         "max_elevation_deg": diff.at(culm).altaz()[0].degrees,
                         "duration_min": (t.utc_datetime() - rise.utc_datetime()).total_seconds() / 60,
                         "rise_azimuth_deg": diff.at(rise).altaz()[1].degrees,
                         "set_azimuth_deg": diff.at(t).altaz()[1].degrees})
            rise = culm = None
    return pd.DataFrame(rows)


def look_angles(sat: Satellite, gs: GroundStation, start, hours=24.0, step_s=60.0) -> pd.DataFrame:
    t = sat.times(start, hours, step_s)
    el, az, dist = (sat.sat - gs.topos).at(t).altaz()
    return pd.DataFrame({"time_utc": pd.to_datetime(t.utc_datetime()), "elevation_deg": el.degrees,
                         "azimuth_deg": az.degrees, "range_km": dist.km})


# ===========================================================================
# 4. SIMULATED telemetry (orbit-driven) with fault injection
# ===========================================================================
SIMULATED_LABEL = "SIMULATED — not real spacecraft telemetry"


@dataclass
class Profile:
    v_min: float = 24.0; v_max: float = 29.4; battery_wh: float = 300.0
    i_solar_max: float = 10.0; bus_v: float = 28.0; eff: float = 0.82
    p_base_w: float = 110.0; p_tx_w: float = 35.0
    eirp_dbw: float = 3.0; freq_mhz: float = 2250.0; rx_gain_dbi: float = 20.0; link_mask: float = 5.0


@dataclass
class Fault:
    kind: str
    start_min: float
    duration_min: float
    magnitude: float = 1.0


def demo_faults(hours: float) -> list[Fault]:
    s = hours * 60
    return [Fault("solar_array_fault", 0.18 * s, 0.08 * s, 0.55),
            Fault("thermal_runaway", 0.40 * s, 0.06 * s, 28.0),
            Fault("battery_degradation", 0.62 * s, 0.12 * s, 1.6),
            Fault("sensor_glitch", 0.85 * s, 6.0),
            Fault("comms_dropout", 0.0, s)]


def simulate_telemetry(sat: Satellite, gs: GroundStation, start, hours=24.0, step_s=60.0,
                       faults=None, seed=7, p: Profile = Profile()) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    orb = orbit_timeseries(sat, start, hours, step_s)
    la = look_angles(sat, gs, start, hours, step_s)
    n, dt_h = len(orb), step_s / 3600
    minutes = np.arange(n) * step_s / 60
    lit = orb.sunlit.to_numpy()
    in_view = la.elevation_deg.to_numpy() > p.link_mask
    link = in_view.copy()
    period = sat.elements()["_period_min"]
    i_sol = np.where(lit, p.i_solar_max * (0.86 + 0.12 * np.cos(2 * np.pi * minutes / period)), 0.0)
    i_sol = i_sol + rng.normal(0, 0.06, n) * lit
    truth = np.array([""] * n, dtype=object)
    faults = faults or []
    mask = {f.kind: (minutes >= f.start_min) & (minutes < f.start_min + f.duration_min) for f in faults}

    scale = np.ones(n)
    for f in faults:
        if f.kind == "solar_array_fault":
            scale[mask[f.kind]] = 1 - f.magnitude
            truth[mask[f.kind] & lit] = f.kind
        if f.kind == "comms_dropout":                 # lose the first pass after mid-window
            idx = np.where(in_view & (minutes > 0.5 * hours * 60))[0]
            if len(idx):
                k = idx[0]
                while k < n and in_view[k]:
                    link[k], truth[k] = False, f.kind
                    k += 1
    i_sol = np.clip(i_sol * scale, 0, None)

    soc, s = np.empty(n), 78.0                        # battery energy balance
    load = p.p_base_w + p.p_tx_w * link
    for k in range(n):
        p_in = p.eff * p.bus_v * i_sol[k] * (max(0.0, (100 - s) / 5) if s > 95 else 1.0)
        s = float(np.clip(s + (p_in - load[k]) * dt_h / p.battery_wh * 100, 0, 100))
        soc[k] = s
    v_batt = p.v_min + (p.v_max - p.v_min) * soc / 100 + rng.normal(0, 0.03, n)

    def lag(hot, cold, tau, t0):                      # first-order thermal response
        a, out, t = 1 - np.exp(-(step_s / 60) / tau), np.empty(n), t0
        for k, target in enumerate(np.where(lit, hot, cold)):
            t += (target - t) * a
            out[k] = t
        return out

    panel = lag(72, -55, 9, 20) + rng.normal(0, 0.6, n)
    bus = lag(29, 14, 35, 22) + rng.normal(0, 0.25, n)
    batt = lag(19, 12, 55, 16) + rng.normal(0, 0.15, n)

    for f in faults:
        m = mask[f.kind]
        ramp = np.clip((minutes - f.start_min) / max(f.duration_min, 1e-6), 0, 1) * m
        if f.kind == "thermal_runaway":
            bus, batt = bus + f.magnitude * ramp, batt + 0.55 * f.magnitude * ramp
            truth[m] = f.kind
        elif f.kind == "battery_degradation":
            v_batt = v_batt - f.magnitude * ramp
            truth[m] = f.kind
        elif f.kind == "sensor_glitch":
            hits = np.where(m)[0][::2]
            panel[hits] += rng.choice([-1, 1], len(hits)) * 45
            truth[hits] = f.kind

    rng_km = la.range_km.to_numpy()
    fspl = 20 * np.log10(rng_km) + 20 * np.log10(p.freq_mhz) + 32.44
    rssi = np.where(link, p.eirp_dbw + 30 + p.rx_gain_dbi - fspl + rng.normal(0, 0.8, n), np.nan)
    return pd.DataFrame({"time_utc": orb.time_utc, "minutes": minutes, "sunlit": lit,
                         "in_view": in_view, "link_up": link, "battery_voltage_v": v_batt,
                         "battery_soc_pct": soc, "solar_current_a": i_sol, "panel_temp_c": panel,
                         "bus_temp_c": bus, "battery_temp_c": batt, "rssi_dbm": rssi, "truth": truth})


# ===========================================================================
# 5. Limit checking
# ===========================================================================
LIMITS = {   # red_low, yellow_low, yellow_high, red_high
    "battery_voltage_v": (25.0, 25.8, 29.6, 30.0),
    "battery_soc_pct": (20.0, 35.0, 101.0, 101.0),
    "panel_temp_c": (-80.0, -70.0, 85.0, 95.0),
    "bus_temp_c": (0.0, 8.0, 38.0, 45.0),
    "battery_temp_c": (2.0, 5.0, 25.0, 30.0),
}
CHANNEL_NAMES = {"battery_voltage_v": "Battery voltage", "battery_soc_pct": "Battery charge",
                 "panel_temp_c": "Panel temperature", "bus_temp_c": "Bus temperature",
                 "battery_temp_c": "Battery temperature", "comms_loss_in_view": "No signal while in view"}


def check_limits(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)
    for ch, (rl, yl, yh, rh) in LIMITS.items():
        v = df[ch].to_numpy()
        s = np.zeros(len(v), int)
        s[(v < yl) | (v > yh)] = 1
        s[(v < rl) | (v > rh)] = 2
        out[ch] = s
    out["comms_loss_in_view"] = np.where(df.in_view & ~df.link_up, 2, 0)
    return out


def limit_events(df: pd.DataFrame, status: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for ch in status.columns:
        s, k = status[ch].to_numpy(), 0
        while k < len(s):
            if s[k]:
                j, worst = k, s[k]
                while j + 1 < len(s) and s[j + 1]:
                    j += 1
                    worst = max(worst, s[j])
                rows.append({"channel": CHANNEL_NAMES[ch], "severity": "alert" if worst == 2 else "caution",
                             "start_utc": df.time_utc.iloc[k], "end_utc": df.time_utc.iloc[j],
                             "minutes": j - k + 1})
                k = j + 1
            else:
                k += 1
    cols = ["channel", "severity", "start_utc", "end_utc", "minutes"]
    return pd.DataFrame(rows, columns=cols).sort_values("start_utc").reset_index(drop=True)


# ===========================================================================
# 6. ML anomaly detection: Isolation Forest + training-envelope guard
# ===========================================================================
_P = Profile()
FEATURE_SUBSYSTEM = {"solar_residual_a": "power", "voltage_vs_charge_v": "power",
                     "bus_temp_c": "thermal", "battery_temp_c": "thermal",
                     "bus_minus_battery_c": "thermal", "bus_temp_rate": "thermal", "panel_spike_c": "thermal"}


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    lit = df.sunlit.astype(float)
    return pd.DataFrame({
        "sunlit": lit,
        "solar_residual_a": df.solar_current_a - 0.86 * _P.i_solar_max * lit,
        "voltage_vs_charge_v": df.battery_voltage_v - (_P.v_min + (_P.v_max - _P.v_min) * df.battery_soc_pct / 100),
        "bus_temp_c": df.bus_temp_c, "battery_temp_c": df.battery_temp_c,
        "bus_minus_battery_c": df.bus_temp_c - df.battery_temp_c,
        "bus_temp_rate": df.bus_temp_c.diff().rolling(5, min_periods=1).mean().fillna(0),
        "panel_spike_c": (df.panel_temp_c - df.panel_temp_c.rolling(5, center=True, min_periods=1).median()).abs(),
    })


class AnomalyDetector:
    """Isolation Forest catches unusual combinations inside the normal range; the
    envelope guard catches values beyond the training range, which an Isolation
    Forest cannot isolate (its splits are drawn only inside the training range)."""

    def fit(self, nominal: pd.DataFrame, pct=99.9, margin=0.15):
        X = build_features(nominal)
        self.cols = list(X.columns)
        self.scaler = StandardScaler().fit(X)
        self.forest = IsolationForest(n_estimators=300, random_state=0).fit(self.scaler.transform(X))
        self.threshold = np.percentile(-self.forest.score_samples(self.scaler.transform(X)), pct)
        span = X.max() - X.min()
        self.lo, self.hi = X.min() - margin * span - 1e-6, X.max() + margin * span + 1e-6
        return self

    def detect(self, df: pd.DataFrame) -> pd.DataFrame:
        X = build_features(df)[self.cols]
        score = -self.forest.score_samples(self.scaler.transform(X))
        outside = ((X < self.lo) | (X > self.hi)).drop(columns="sunlit")
        z = pd.DataFrame(np.abs(self.scaler.transform(X)), columns=self.cols, index=X.index).drop(columns="sunlit")
        feature = outside.idxmax(axis=1).where(outside.any(axis=1), z.idxmax(axis=1))
        if_flag, env_flag = score > self.threshold, outside.any(axis=1).to_numpy()
        flag = if_flag | env_flag
        return pd.DataFrame({"if_flag": if_flag, "env_flag": env_flag, "flag": flag,
                             "feature": np.where(flag, feature, ""),
                             "subsystem": np.where(flag, feature.map(FEATURE_SUBSYSTEM), "")}, index=df.index)


def evaluate(pred, truth: pd.Series) -> dict:
    pred, actual = np.asarray(pred, bool), truth.to_numpy() != ""
    tp, fp, fn = int((pred & actual).sum()), int((pred & ~actual).sum()), int((~pred & actual).sum())
    kinds = sorted(set(truth) - {""})
    return {"precision": tp / (tp + fp) if tp + fp else 0.0, "recall": tp / (tp + fn) if tp + fn else 0.0,
            "false alarms": fp,
            "faults caught": f"{sum(bool((pred & (truth.to_numpy() == k)).any()) for k in kinds)} of {len(kinds)}"}


# ===========================================================================
# 7. Health scores
# ===========================================================================
SUBSYSTEMS = {"power": ["battery_voltage_v", "battery_soc_pct"],
              "thermal": ["panel_temp_c", "bus_temp_c", "battery_temp_c"],
              "comms": ["comms_loss_in_view"]}


def band(x: float) -> str:
    return "nominal" if x >= 85 else "caution" if x >= 60 else "alert"


def health_scores(df, status, det, window_min=30.0) -> pd.DataFrame:
    w = max(1, int(round(window_min / float(df.minutes.diff().median() or 1))))
    out = pd.DataFrame({"time_utc": df.time_utc})
    for sub, chans in SUBSYSTEMS.items():
        st_ = status[chans].max(axis=1)
        red = (st_ == 2).astype(float).rolling(w, min_periods=1).mean()
        yel = (st_ == 1).astype(float).rolling(w, min_periods=1).mean()
        ml = (det.flag & (det.subsystem == sub)).astype(float).rolling(w, min_periods=1).mean()
        out[sub] = np.clip(100 - 100 * (red + 0.4 * yel + 0.75 * ml), 0, 100)
    out["overall"] = out[list(SUBSYSTEMS)].min(axis=1)
    return out


def run_health(sat: Satellite, gs: GroundStation, start, hours=24.0, faults_on=True) -> dict:
    ref = simulate_telemetry(sat, gs, as_utc(start) - timedelta(hours=48), 48, seed=1007)  # fault-free
    tel = simulate_telemetry(sat, gs, start, hours, faults=demo_faults(hours) if faults_on else None)
    status = check_limits(tel)
    det = AnomalyDetector().fit(ref).detect(tel)
    lim = (status.max(axis=1) > 0).to_numpy()
    metrics = pd.DataFrame([
        {"detector": "Limit checks only", **evaluate(lim, tel.truth)},
        {"detector": "Isolation Forest only", **evaluate(det.if_flag, tel.truth)},
        {"detector": "Forest + envelope guard", **evaluate(det.flag, tel.truth)},
        {"detector": "Limits + ML (used)", **evaluate(lim | det.flag.to_numpy(), tel.truth)}])
    return {"tel": tel, "status": status, "det": det, "events": limit_events(tel, status),
            "scores": health_scores(tel, status, det), "metrics": metrics}


# ===========================================================================
# 8. Figures
# ===========================================================================
_CACHE_ROOT = Path(os.environ.get("XDG_CACHE_HOME") or os.environ.get("LOCALAPPDATA") or
                   (Path.home() / ".cache"))
LAND_CACHE = _CACHE_ROOT / "satellite_tracking" / "land_110m_cache.json"
LAND_URL = "https://cdn.jsdelivr.net/npm/world-atlas@2/land-110m.json"


@st.cache_data(show_spinner=False)
def land_lines() -> list:
    """Coastline polylines [[lon, lat], ...] decoded from Natural Earth TopoJSON."""
    try:
        if LAND_CACHE.exists():
            return json.loads(LAND_CACHE.read_text())
        import requests
        topo = requests.get(LAND_URL, timeout=10).json()
    except Exception:
        return []
    (sx, sy), (tx, ty) = topo["transform"]["scale"], topo["transform"]["translate"]
    arcs = []
    for arc in topo["arcs"]:
        x = y = 0
        pts = []
        for dx, dy in arc:
            x, y = x + dx, y + dy
            pts.append([round(x * sx + tx, 2), round(y * sy + ty, 2)])
        arcs.append(pts)
    lines = []
    for g in topo["objects"]["land"]["geometries"]:
        for poly in (g["arcs"] if g["type"] == "MultiPolygon" else [g["arcs"]]):
            for ring in poly:
                pts = []
                for i in ring:
                    a = arcs[i] if i >= 0 else arcs[~i][::-1]
                    pts.extend(a if not pts else a[1:])
                lines.append(pts)
    try:
        LAND_CACHE.parent.mkdir(parents=True, exist_ok=True)
        LAND_CACHE.write_text(json.dumps(lines, separators=(",", ":")))
    except OSError:
        pass
    return lines


def _layout(fig, height):
    fig.update_layout(template="plotly_white", height=height, paper_bgcolor=PANEL, plot_bgcolor=PANEL,
                      font=dict(family="Segoe UI, sans-serif", color=INK, size=13),
                      margin=dict(l=50, r=20, t=30, b=40))
    return fig


def _eclipse_shapes(times, sunlit):
    shapes, start, lit = [], None, sunlit.to_numpy()
    for i, s in enumerate(lit):
        if not s and start is None:
            start = i
        if (s or i == len(lit) - 1) and start is not None:
            shapes.append(dict(type="rect", xref="x", yref="paper", x0=times.iloc[start], x1=times.iloc[i],
                               y0=0, y1=1, fillcolor=ECLIPSE, line_width=0, layer="below"))
            start = None
    return shapes


def globe_figure(orbit, idx, name, gs):
    u, v = np.mgrid[0:2 * np.pi:60j, 0:np.pi:30j]
    fig = go.Figure(go.Surface(x=R_E * np.cos(u) * np.sin(v), y=R_E * np.sin(u) * np.sin(v), z=R_E * np.cos(v),
                               showscale=False, hoverinfo="skip", colorscale=[[0, EARTH], [1, EARTH]],
                               lighting=dict(ambient=0.95, diffuse=0.1, specular=0.0)))
    xs, ys, zs = [], [], []
    for line in land_lines():
        a = np.radians(np.array(line))
        xs += list(1.002 * R_E * np.cos(a[:, 1]) * np.cos(a[:, 0])) + [None]
        ys += list(1.002 * R_E * np.cos(a[:, 1]) * np.sin(a[:, 0])) + [None]
        zs += list(1.002 * R_E * np.sin(a[:, 1])) + [None]
    fig.add_scatter3d(x=xs, y=ys, z=zs, mode="lines", line=dict(color=LAND, width=2), hoverinfo="skip",
                      showlegend=False)
    seg = orbit.iloc[max(0, idx - 47): idx + 47]
    fig.add_scatter3d(x=seg.x_ecef_km, y=seg.y_ecef_km, z=seg.z_ecef_km, mode="lines",
                      line=dict(color=SAT_COLORS.get(name, "#2B59C3"), width=5), name="Track ±1 orbit")
    cur = orbit.iloc[idx]
    fig.add_scatter3d(x=[cur.x_ecef_km], y=[cur.y_ecef_km], z=[cur.z_ecef_km], mode="markers",
                      marker=dict(size=6, color=INK), name=name)
    la, lo = np.radians(gs.lat), np.radians(gs.lon)
    fig.add_scatter3d(x=[R_E * np.cos(la) * np.cos(lo)], y=[R_E * np.cos(la) * np.sin(lo)], z=[R_E * np.sin(la)],
                      mode="markers", marker=dict(size=5, color=STATION_C, symbol="diamond"), name=gs.name)
    lat0, lon0 = np.radians(np.clip(cur.lat_deg, -60, 60)), np.radians(cur.lon_deg)
    eye = dict(x=1.45 * np.cos(lat0) * np.cos(lon0), y=1.45 * np.cos(lat0) * np.sin(lon0), z=1.45 * np.sin(lat0))
    ax = dict(visible=False, showbackground=False)
    fig.update_layout(scene=dict(xaxis=ax, yaxis=ax, zaxis=ax, aspectmode="data", camera=dict(eye=eye)),
                      legend=dict(orientation="h", y=0.02))
    _layout(fig, 520).update_layout(margin=dict(l=0, r=0, t=0, b=0))
    return fig


def ground_track_figure(orbits: dict, idx, gs):
    fig = go.Figure()
    lon, lat = [], []
    for line in land_lines():
        a = np.array(line)
        x, y = break_antimeridian(a[:, 0], a[:, 1])
        lon += x.tolist() + [None]
        lat += y.tolist() + [None]
    fig.add_scatter(x=lon, y=lat, mode="lines", line=dict(color=LAND, width=1), hoverinfo="skip", showlegend=False)
    single = len(orbits) == 1
    for name, df in orbits.items():
        c = SAT_COLORS.get(name, "#2B59C3")
        x, y = break_antimeridian(df.lon_deg, df.lat_deg)
        fig.add_scatter(x=x, y=y, mode="lines", line=dict(color=c, width=1.0 if single else 1.6),
                        opacity=0.3 if single else 1, name=name, showlegend=not single)
        if single:
            seg = df.iloc[max(0, idx - 47): idx + 47]
            x, y = break_antimeridian(seg.lon_deg, seg.lat_deg)
            fig.add_scatter(x=x, y=y, mode="lines", line=dict(color=c, width=2.4), name=f"{name}, ±1 orbit")
        fig.add_scatter(x=[df.lon_deg.iloc[idx]], y=[df.lat_deg.iloc[idx]], mode="markers", showlegend=False,
                        marker=dict(size=10, color=c, line=dict(color="white", width=1.5)))
    fig.add_scatter(x=[gs.lon], y=[gs.lat], mode="markers+text", text=[gs.name], textposition="top right",
                    marker=dict(size=10, color=STATION_C, symbol="diamond"), showlegend=False)
    fig.update_xaxes(range=[-180, 180], dtick=60, title="Longitude (°)", gridcolor=GRID)
    fig.update_yaxes(range=[-90, 90], dtick=30, title="Latitude (°)", gridcolor=GRID)
    fig.update_layout(legend=dict(orientation="h", y=1.08))
    return _layout(fig, 460)


def skyplot_figure(look, passes):
    fig = go.Figure()
    for _, p in passes.iterrows():
        seg = look[(look.time_utc >= p.rise_utc) & (look.time_utc <= p.set_utc)]
        fig.add_scatterpolar(r=90 - seg.elevation_deg, theta=seg.azimuth_deg, mode="lines",
                             name=f"{pd.Timestamp(p.rise_utc):%d %b %H:%M} · {p.max_elevation_deg:.0f}°")
    fig.update_layout(polar=dict(radialaxis=dict(range=[0, 90], tickvals=[0, 30, 60, 90],
                                                 ticktext=["90°", "60°", "30°", "0°"]),
                                 angularaxis=dict(direction="clockwise", rotation=90)))
    return _layout(fig, 440)


def telemetry_figure(tel, det):
    rows = [["battery_voltage_v"], ["solar_current_a"], ["panel_temp_c", "bus_temp_c", "battery_temp_c"], ["rssi_dbm"]]
    names = {"battery_voltage_v": "Battery voltage", "solar_current_a": "Solar current",
             "panel_temp_c": "Solar panel temperature", "bus_temp_c": "Bus temperature",
             "battery_temp_c": "Battery temperature", "rssi_dbm": "RSSI"}
    fig = make_subplots(rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.05,
                        subplot_titles=["Battery voltage (V)", "Solar array current (A)", "Temperatures (°C)",
                                        "Downlink RSSI (dBm)"])
    colors = ["#2B59C3", "#B5502C", NOMINAL]
    for r, chans in enumerate(rows, 1):
        for c, ch in enumerate(chans):
            fig.add_scatter(x=tel.time_utc, y=tel[ch], mode="markers" if ch == "rssi_dbm" else "lines",
                            marker=dict(size=4), line=dict(width=1.4, color=colors[c]), name=names[ch],
                            row=r, col=1, showlegend=len(chans) > 1)
            if ch in LIMITS:
                for val in (LIMITS[ch][0], LIMITS[ch][3]):
                    if tel[ch].min() - 5 < val < tel[ch].max() + 5:
                        fig.add_hline(y=val, line=dict(color=ALERT, dash="dot", width=1), row=r, col=1)
    where = {"voltage_vs_charge_v": (1, "battery_voltage_v"), "solar_residual_a": (2, "solar_current_a"),
             "panel_spike_c": (3, "panel_temp_c")}
    first = True
    for feat, grp in det[det.flag].groupby("feature"):
        r, ch = where.get(feat, (3, "bus_temp_c"))
        fig.add_scatter(x=tel.time_utc[grp.index], y=tel[ch][grp.index], mode="markers", name="ML flag",
                        marker=dict(size=6, color=ALERT, symbol="x"), showlegend=first, row=r, col=1)
        first = False
    for s in _eclipse_shapes(tel.time_utc, tel.sunlit):
        fig.add_shape(**s)
    fig.add_annotation(text=SIMULATED_LABEL, xref="paper", yref="paper", x=1, y=1.06, showarrow=False,
                       font=dict(color=ALERT, size=12), xanchor="right")
    return _layout(fig, 820)


def health_figure(scores, sunlit):
    fig = go.Figure()
    for k, c in (("power", "#2B59C3"), ("thermal", "#B5502C"), ("comms", STATION_C)):
        fig.add_scatter(x=scores.time_utc, y=scores[k], name=k.title(), line=dict(color=c, width=1.6))
    for y0, y1, c in ((85, 101, NOMINAL), (60, 85, CAUTION), (-1, 60, ALERT)):
        fig.add_hrect(y0=y0, y1=y1, fillcolor=c, opacity=0.07, line_width=0)
    for s in _eclipse_shapes(scores.time_utc, sunlit):
        fig.add_shape(**s)
    fig.update_yaxes(range=[-2, 102], title="Health score")
    fig.update_layout(legend=dict(orientation="h", y=1.12))
    return _layout(fig, 320)


# ===========================================================================
# 9. Streamlit app
# ===========================================================================
def fmt_times(df, cols, pattern="%d %b %H:%M:%S"):
    df = df.copy()
    for c in cols:
        df[c] = pd.to_datetime(df[c]).dt.strftime(pattern)
    return df


@st.cache_resource
def load_fleet(source: str, ids: str) -> dict:
    if source == "Live (Celestrak)":
        sats = [Satellite.from_celestrak(int(i)) for i in ids.replace(",", " ").split()]
    else:
        sats = [Satellite(n, *l) for n, l in parse_tles(SAMPLE_TLES).items()]
    return {s.name: s for s in sats}


@st.cache_data(show_spinner="Propagating orbit…")
def cached_orbit(_sat, key, start, hours):
    return orbit_timeseries(_sat, start, hours)


@st.cache_data(show_spinner="Simulating telemetry and running detectors…")
def cached_health(_sat, key, start, hours, station, faults_on):
    return run_health(_sat, STATIONS[station], start, hours, faults_on)


def main():
    st.set_page_config(page_title="Satellite Tracking & Health", page_icon="🛰️", layout="wide")

    with st.sidebar:
        st.header("Setup")
        source = st.radio("Orbit data", ["Sample TLEs (offline)", "Live (Celestrak)"])
        ids = st.text_input("NORAD IDs", "25544 20580 33591", disabled=source != "Live (Celestrak)")
        try:
            fleet = load_fleet(source, ids)
        except Exception as exc:
            st.error(f"Couldn't load TLEs: {exc}. Switch to sample TLEs to work offline.")
            st.stop()
        name = st.selectbox("Satellite", list(fleet))
        sat = fleet[name]
        station_name = st.selectbox("Ground station", list(STATIONS))
        gs = STATIONS[station_name]
        hours = st.slider("Window (hours)", 3, 48, 24)
        mode = st.radio("Start time", ["Auto", "TLE epoch", "Now"],
                        help="Auto uses now, or the TLE epoch if the TLE is over 14 days old.")
        faults_on = st.toggle("Inject demo faults", value=True)

    now = datetime.now(timezone.utc)
    start = {"Now": now, "TLE epoch": sat.epoch}.get(mode, sat.epoch if sat.is_stale(now) else now)
    if sat.is_stale(now) and mode != "Now":
        st.info(f"This TLE is {sat.age_days():.0f} days old, so the view starts at its epoch "
                f"({sat.epoch:%d %b %Y %H:%M} UTC). Use live data for current positions.")
    elif sat.is_stale(start):
        st.warning("The TLE is more than 14 days from the selected time, so positions are unreliable.")

    key = f"{name}|{sat.line1}"
    orbit = cached_orbit(sat, key, start, hours)
    st.title(name)
    st.caption(f"NORAD {sat.norad} · window {start:%d %b %Y %H:%M} UTC + {hours} h · ground station {gs.name}")
    tabs = st.tabs(["Tracking", "Passes", "Telemetry & health", "Fleet", "Orbital elements"])

    with tabs[0]:  # ------------------------------------------------- tracking
        i = st.slider("Time in window (minutes)", 0, len(orbit) - 1, 0)
        row = orbit.iloc[i]
        c = st.columns(5)
        c[0].metric("Time (UTC)", f"{row.time_utc:%H:%M}")
        c[1].metric("Latitude", f"{row.lat_deg:.2f}°")
        c[2].metric("Longitude", f"{row.lon_deg:.2f}°")
        c[3].metric("Altitude", f"{row.alt_km:.1f} km")
        c[4].metric("Speed", f"{row.speed_kms:.3f} km/s", "sunlit" if row.sunlit else "eclipse", delta_color="off")
        left, right = st.columns(2)
        left.plotly_chart(globe_figure(orbit, i, name, gs), width="stretch")
        right.plotly_chart(ground_track_figure({name: orbit}, i, gs), width="stretch")
        s = orbit_summary(orbit)
        st.markdown(f"Over this window the altitude ranges **{s['min_alt']:.0f}–{s['max_alt']:.0f} km**, the "
                    f"satellite is sunlit **{100 * s['sunlit']:.0f} %** of the time across **{s['eclipses']}** "
                    f"eclipses (typically **{s['eclipse_min']:.0f} min**), and the mean solar beta angle is "
                    f"**{s['beta']:.1f}°**.")

    with tabs[1]:  # ------------------------------------------------- passes
        passes = predict_passes(sat, gs, start, hours)
        if passes.empty:
            st.info(f"No passes above {gs.mask_deg:.0f}° in this window. Try a longer window or another station.")
        else:
            show = fmt_times(passes.drop(columns="satellite"), ["rise_utc", "culmination_utc", "set_utc"])
            st.dataframe(show.round(1), width="stretch", hide_index=True)
            st.plotly_chart(skyplot_figure(look_angles(sat, gs, start, hours, 20.0), passes), width="stretch")

    with tabs[2]:  # ------------------------------------------------- health
        st.error(SIMULATED_LABEL + ". Values are generated from the orbit geometry to demonstrate the "
                 "monitoring pipeline; a TLE contains no spacecraft health data.")
        run = cached_health(sat, key, start, hours, station_name, faults_on)
        sc = run["scores"]
        cols = st.columns(4)
        for col, k in zip(cols, ["overall", "power", "thermal", "comms"]):
            col.metric(f"{k.title()} health, end of window", f"{sc[k].iloc[-1]:.0f} / 100")
            col.caption(f"Lowest in window: {sc[k].min():.0f} ({band(sc[k].min())})")
        st.plotly_chart(health_figure(sc, run["tel"].sunlit), width="stretch")
        st.plotly_chart(telemetry_figure(run["tel"], run["det"]), width="stretch")
        a, b = st.columns(2)
        a.subheader("Limit events")
        a.dataframe(fmt_times(run["events"], ["start_utc", "end_utc"], "%d %b %H:%M"), width="stretch",
                    hide_index=True)
        b.subheader("Detector performance vs injected faults")
        b.dataframe(run["metrics"].round(3), width="stretch", hide_index=True)

    with tabs[3]:  # ------------------------------------------------- fleet
        all_stale = all(s.is_stale(now) for s in fleet.values())
        ref = max(s.epoch for s in fleet.values()) if (all_stale and mode != "Now") else start
        snap = []
        for s in fleet.values():
            p = wgs84.geographic_position_of(s.sat.at(_TS.from_datetime(ref)))
            e = s.elements()
            snap.append({"satellite": s.name, "norad": s.norad, "lat_deg": p.latitude.degrees,
                         "lon_deg": p.longitude.degrees, "alt_km": p.elevation.km,
                         "inclination_deg": e["_inc"], "period_min": e["_period_min"],
                         "tle_age_days": s.age_days(ref)})
        st.dataframe(pd.DataFrame(snap).round(2), width="stretch", hide_index=True)
        orbits = {s.name: cached_orbit(s, f"{s.name}|{s.line1}", ref, 3.0) for s in fleet.values()}
        st.plotly_chart(ground_track_figure(orbits, 0, gs), width="stretch")
        st.subheader(f"All passes over {gs.name}")
        allp = pd.concat([predict_passes(s, gs, ref, hours) for s in fleet.values()], ignore_index=True)
        if not allp.empty:
            allp = allp.sort_values("rise_utc").reset_index(drop=True)
            clashes = sum(1 for i in range(len(allp)) for j in range(i + 1, len(allp))
                          if allp.satellite[i] != allp.satellite[j] and allp.rise_utc[j] < allp.set_utc[i])
            st.dataframe(fmt_times(allp[["satellite", "rise_utc", "set_utc", "max_elevation_deg", "duration_min"]],
                                   ["rise_utc", "set_utc"], "%d %b %H:%M").round(1), width="stretch", hide_index=True)
            st.caption("No overlapping passes — one antenna can serve the whole fleet." if not clashes
                       else f"{clashes} overlapping pass pairs need antenna scheduling.")

    with tabs[4]:  # ------------------------------------------------- elements
        e = {k: v for k, v in sat.elements().items() if not k.startswith("_")}
        st.dataframe(pd.DataFrame({"Element": list(e), "Value": list(e.values())}), width="stretch",
                     hide_index=True)
        st.code(f"{name}\n{sat.line1}\n{sat.line2}", language="text")


if __name__ == "__main__":
    main()
