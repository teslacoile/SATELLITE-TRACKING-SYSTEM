"""
satellite_report.py
===================
Satellite Tracking & Health Monitoring System — standard-library-only version.

    python satellite_report.py

No pip installs. Everything is written in plain Python: the SGP4 orbit propagator,
coordinate frames, pass prediction, eclipse model, SIMULATED telemetry, limit
checks, an Isolation Forest anomaly detector, and the PDF writer itself.

Output: satellite_report.pdf (6 pages: Tracking, Passes, Telemetry & health,
Telemetry, Fleet, Orbital elements).

Options (all optional):
    --sat "NOAA 19"               satellite from the TLE set
    --station "ISTRAC Bengaluru"  SRM Kattankulathur | ISTRAC Bengaluru | Svalbard (SvalSat)
    --hours 48                    analysis window
    --minute 740                  moment shown on the tracking page
    --norad 25544 20580           live TLEs from Celestrak (needs internet)
    --tle my_tles.txt             your own 3-line TLE file
    --out report.pdf

IMPORTANT: a TLE describes only the orbit. It contains no battery, thermal or
subsystem data. All health values are SIMULATED from the orbit geometry and are
labelled as such in the report.

Requires Python 3.8+.
"""

import argparse
import base64
import json
import math
import os
import random
import subprocess
import sys
import time
import zlib
from datetime import datetime, timedelta, timezone

# Illustrative sample TLEs (epoch 14 Feb 2024); checksums are valid.
SAMPLE_TLES = """\
ISS (ZARYA)
1 25544U 98067A   24045.51782528  .00016717  00000-0  30323-3 0  9999
2 25544  51.6416 247.4627 0006703 130.5360 325.0288 15.49386731438786
HUBBLE SPACE TELESCOPE
1 20580U 90037B   24045.16815718  .00000672  00000-0  33081-4 0  9990
2 20580  28.4699 288.8102 0002785 321.7771  38.2820 15.16266097598170
NOAA 19
1 33591U 09005A   24045.50000000  .00000078  00000-0  63146-4 0  9994
2 33591  99.1932 100.3456 0013972  75.1234 285.1234 14.12345678765430
"""

# Natural Earth 1:110m coastlines, simplified (public domain), zlib + base64.
COAST_B64 = """
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
k2oSBKJkDcz8739LWA+Y
"""


# ===========================================================================
# 1. SGP4 propagator (near-Earth), written from the published algorithm
# ===========================================================================
TWOPI = 2 * math.pi
# WGS-72 constants (the ones SGP4 and TLEs are defined with)
MU72, RE72 = 398600.8, 6378.135
XKE = 60.0 / math.sqrt(RE72 ** 3 / MU72)
J2, J3, J4 = 0.001082616, -0.00000253881, -0.00000165597
J3OJ2 = J3 / J2
X2O3 = 2.0 / 3.0


def tle_checksum(line):
    return sum(int(c) if c.isdigit() else (1 if c == "-" else 0) for c in line[:68]) % 10


def _implied(field):
    """TLE 'implied decimal' fields such as ' 30323-3' -> 0.30323e-3."""
    field = field.strip()
    if not field:
        return 0.0
    sign = -1.0 if field[0] == "-" else 1.0
    field = field.lstrip("+-")
    mant, exp = field[:-2], field[-2:]
    return sign * float("0." + mant) * 10 ** int(exp)


class SGP4:
    """Near-Earth SGP4 (periods < 225 min), after Vallado et al., AIAA 2006-6753."""

    def __init__(self, name, line1, line2):
        for num, ln in (("1", line1), ("2", line2)):
            if len(ln) != 69 or not ln.startswith(num + " "):
                raise ValueError(f"TLE line {num} is malformed (need 69 characters starting '{num} ').")
            if int(ln[68]) != tle_checksum(ln):
                raise ValueError(f"TLE line {num} checksum mismatch: expected {tle_checksum(ln)}.")
        self.name, self.line1, self.line2 = name, line1, line2
        self.satnum = int(line1[2:7])
        yy = int(line1[18:20]); day = float(line1[20:32])
        year = 2000 + yy if yy < 57 else 1900 + yy
        self.epoch = datetime(year, 1, 1, tzinfo=timezone.utc) + timedelta(days=day - 1)
        self.bstar = _implied(line1[53:61])
        d2r = math.pi / 180
        self.inclo = float(line2[8:16]) * d2r
        self.nodeo = float(line2[17:25]) * d2r
        self.ecco = float("0." + line2[26:33].strip())
        self.argpo = float(line2[34:42]) * d2r
        self.mo = float(line2[43:51]) * d2r
        self.rev_per_day = float(line2[52:63])
        self.no_kozai = self.rev_per_day * TWOPI / 1440.0
        if 1440.0 / self.rev_per_day >= 225:
            raise ValueError("Deep-space orbit (period >= 225 min) is not supported by this near-Earth SGP4.")
        self._init()

    def _init(self):
        e, i = self.ecco, self.inclo
        omeosq = 1 - e * e; rteosq = math.sqrt(omeosq)
        cosio = math.cos(i); cosio2 = cosio * cosio
        ak = (XKE / self.no_kozai) ** X2O3
        d1 = 0.75 * J2 * (3 * cosio2 - 1) / (rteosq * omeosq)
        dl = d1 / (ak * ak)
        adel = ak * (1 - dl * dl - dl * (1 / 3 + 134 * dl * dl / 81))
        dl = d1 / (adel * adel)
        no = self.no_kozai / (1 + dl)
        ao = (XKE / no) ** X2O3
        sinio = math.sin(i); po = ao * omeosq
        con42 = 1 - 5 * cosio2; con41 = -con42 - cosio2 - cosio2
        posq = po * po; rp = ao * (1 - e)
        self.isimp = rp < 220 / RE72 + 1
        ss = 78 / RE72 + 1; qzms2t = ((120 - 78) / RE72) ** 4
        sfour, qzms24 = ss, qzms2t
        perige = (rp - 1) * RE72
        if perige < 156:
            sfour = perige - 78 if perige >= 98 else 20
            qzms24 = ((120 - sfour) / RE72) ** 4
            sfour = sfour / RE72 + 1
        pinvsq = 1 / posq
        tsi = 1 / (ao - sfour); eta = ao * e * tsi; etasq = eta * eta; eeta = e * eta
        psisq = abs(1 - etasq); coef = qzms24 * tsi ** 4; coef1 = coef / psisq ** 3.5
        cc2 = coef1 * no * (ao * (1 + 1.5 * etasq + eeta * (4 + etasq)) +
                            0.375 * J2 * tsi / psisq * con41 * (8 + 3 * etasq * (8 + etasq)))
        cc1 = self.bstar * cc2
        cc3 = -2 * coef * tsi * J3OJ2 * no * sinio / e if e > 1e-4 else 0.0
        x1mth2 = 1 - cosio2
        cc4 = 2 * no * coef1 * ao * omeosq * (eta * (2 + 0.5 * etasq) + e * (0.5 + 2 * etasq) -
              J2 * tsi / (ao * psisq) * (-3 * con41 * (1 - 2 * eeta + etasq * (1.5 - 0.5 * eeta)) +
              0.75 * x1mth2 * (2 * etasq - eeta * (1 + etasq)) * math.cos(2 * self.argpo)))
        cc5 = 2 * coef1 * ao * omeosq * (1 + 2.75 * (etasq + eeta) + eeta * etasq)
        cosio4 = cosio2 * cosio2
        t1 = 1.5 * J2 * pinvsq * no; t2 = 0.5 * t1 * J2 * pinvsq; t3 = -0.46875 * J4 * pinvsq * pinvsq * no
        self.mdot = no + 0.5 * t1 * rteosq * con41 + 0.0625 * t2 * rteosq * (13 - 78 * cosio2 + 137 * cosio4)
        self.argpdot = (-0.5 * t1 * con42 + 0.0625 * t2 * (7 - 114 * cosio2 + 395 * cosio4) +
                        t3 * (3 - 36 * cosio2 + 49 * cosio4))
        xhdot1 = -t1 * cosio
        self.nodedot = xhdot1 + (0.5 * t2 * (4 - 19 * cosio2) + 2 * t3 * (3 - 7 * cosio2)) * cosio
        self.omgcof = self.bstar * cc3 * math.cos(self.argpo)
        self.xmcof = -X2O3 * coef * self.bstar / eeta if e > 1e-4 else 0.0
        self.nodecf = 3.5 * omeosq * xhdot1 * cc1
        self.t2cof = 1.5 * cc1
        den = 1 + cosio if abs(cosio + 1) > 1.5e-12 else 1.5e-12
        self.xlcof = -0.25 * J3OJ2 * sinio * (3 + 5 * cosio) / den
        self.aycof = -0.5 * J3OJ2 * sinio
        self.delmo = (1 + eta * math.cos(self.mo)) ** 3
        self.sinmao = math.sin(self.mo)
        self.x7thm1 = 7 * cosio2 - 1
        if not self.isimp:
            cc1sq = cc1 * cc1
            self.d2 = 4 * ao * tsi * cc1sq
            tmp = self.d2 * tsi * cc1 / 3
            self.d3 = (17 * ao + sfour) * tmp
            self.d4 = 0.5 * tmp * ao * tsi * (221 * ao + 31 * sfour) * cc1
            self.t3cof = self.d2 + 2 * cc1sq
            self.t4cof = 0.25 * (3 * self.d3 + cc1 * (12 * self.d2 + 10 * cc1sq))
            self.t5cof = 0.2 * (3 * self.d4 + 12 * cc1 * self.d3 + 6 * self.d2 * self.d2 +
                                15 * cc1sq * (2 * self.d2 + cc1sq))
        self.no, self.ao, self.eta, self.cc1, self.cc4, self.cc5 = no, ao, eta, cc1, cc4, cc5
        self.con41, self.x1mth2 = con41, x1mth2

    def propagate(self, tsince_min):
        """Position (km) and velocity (km/s) in the TEME frame."""
        t = tsince_min
        xmdf = self.mo + self.mdot * t
        argpdf = self.argpo + self.argpdot * t
        nodedf = self.nodeo + self.nodedot * t
        argpm, mm, t2 = argpdf, xmdf, t * t
        nodem = nodedf + self.nodecf * t2
        tempa = 1 - self.cc1 * t
        tempe = self.bstar * self.cc4 * t
        templ = self.t2cof * t2
        if not self.isimp:
            delomg = self.omgcof * t
            delm = self.xmcof * ((1 + self.eta * math.cos(xmdf)) ** 3 - self.delmo)
            tmp = delomg + delm
            mm = xmdf + tmp
            argpm = argpdf - tmp
            t3 = t2 * t; t4 = t3 * t
            tempa -= self.d2 * t2 + self.d3 * t3 + self.d4 * t4
            tempe += self.bstar * self.cc5 * (math.sin(mm) - self.sinmao)
            templ += self.t3cof * t3 + t4 * (self.t4cof + t * self.t5cof)
        am = (XKE / self.no) ** X2O3 * tempa * tempa
        nm = XKE / am ** 1.5
        em = max(self.ecco - tempe, 1e-6)
        mm += self.no * templ
        xlm = mm + argpm + nodem
        nodem %= TWOPI; argpm %= TWOPI; xlm %= TWOPI
        mm = (xlm - argpm - nodem) % TWOPI
        sinip, cosip = math.sin(self.inclo), math.cos(self.inclo)
        axnl = em * math.cos(argpm)
        tmp = 1 / (am * (1 - em * em))
        aynl = em * math.sin(argpm) + tmp * self.aycof
        xl = mm + argpm + nodem + tmp * self.xlcof * axnl
        u = (xl - nodem) % TWOPI
        eo1, tem5, ktr = u, 9999.9, 1
        while abs(tem5) >= 1e-12 and ktr <= 10:          # Kepler's equation (Newton)
            s1, c1 = math.sin(eo1), math.cos(eo1)
            tem5 = (u - aynl * c1 + axnl * s1 - eo1) / (1 - c1 * axnl - s1 * aynl)
            tem5 = max(-0.95, min(0.95, tem5))
            eo1 += tem5; ktr += 1
        s1, c1 = math.sin(eo1), math.cos(eo1)
        ecose = axnl * c1 + aynl * s1; esine = axnl * s1 - aynl * c1
        el2 = axnl * axnl + aynl * aynl; pl = am * (1 - el2)
        if pl < 0:
            raise ValueError("SGP4: semi-latus rectum < 0 (orbit decayed).")
        rl = am * (1 - ecose); rdotl = math.sqrt(am) * esine / rl; rvdotl = math.sqrt(pl) / rl
        betal = math.sqrt(1 - el2); tmp = esine / (1 + betal)
        sinu = am / rl * (s1 - aynl - axnl * tmp); cosu = am / rl * (c1 - axnl + aynl * tmp)
        su = math.atan2(sinu, cosu)
        sin2u = 2 * cosu * sinu; cos2u = 1 - 2 * sinu * sinu
        tmp = 1 / pl; tmp1 = 0.5 * J2 * tmp; tmp2 = tmp1 * tmp
        mrt = rl * (1 - 1.5 * tmp2 * betal * self.con41) + 0.5 * tmp1 * self.x1mth2 * cos2u
        su -= 0.25 * tmp2 * self.x7thm1 * sin2u
        xnode = nodem + 1.5 * tmp2 * cosip * sin2u
        xinc = self.inclo + 1.5 * tmp2 * cosip * sinip * cos2u
        mvt = rdotl - nm * tmp1 * self.x1mth2 * sin2u / XKE
        rvdot = rvdotl + nm * tmp1 * (self.x1mth2 * cos2u + 1.5 * self.con41) / XKE
        ss, cs = math.sin(su), math.cos(su); sn, cn = math.sin(xnode), math.cos(xnode)
        si, ci = math.sin(xinc), math.cos(xinc)
        xmx, xmy = -sn * ci, cn * ci
        ux, uy, uz = xmx * ss + cn * cs, xmy * ss + sn * cs, si * ss
        vx, vy, vz = xmx * cs - cn * ss, xmy * cs - sn * ss, si * cs
        vkms = RE72 * XKE / 60
        r = (mrt * ux * RE72, mrt * uy * RE72, mrt * uz * RE72)
        v = ((mvt * ux + rvdot * vx) * vkms, (mvt * uy + rvdot * vy) * vkms, (mvt * uz + rvdot * vz) * vkms)
        return r, v


# ===========================================================================
# 2. Time, frames and geodesy
# ===========================================================================
R_E = 6378.137                       # WGS-84 equatorial radius (km)
F_WGS84 = 1 / 298.257223563
MU = 398600.4418


def julian_date(dt):
    return (dt - datetime(2000, 1, 1, 12, tzinfo=timezone.utc)).total_seconds() / 86400 + 2451545.0


def gmst_rad(jd):
    """Greenwich mean sidereal time, IAU-82 (the rotation SGP4's TEME frame expects)."""
    t = (jd - 2451545.0) / 36525
    s = 67310.54841 + (876600 * 3600 + 8640184.812866) * t + 0.093104 * t * t - 6.2e-6 * t ** 3
    return math.radians((s % 86400) / 240.0)


def teme_to_ecef(r, jd):
    g = gmst_rad(jd)
    c, s = math.cos(g), math.sin(g)
    return (c * r[0] + s * r[1], -s * r[0] + c * r[1], r[2])


def ecef_to_geodetic(x, y, z):
    """Latitude/longitude (deg) and height (km) on the WGS-84 ellipsoid (iterative)."""
    e2 = F_WGS84 * (2 - F_WGS84)
    lon = math.atan2(y, x)
    p = math.hypot(x, y)
    lat = math.atan2(z, p * (1 - e2))
    for _ in range(6):
        n = R_E / math.sqrt(1 - e2 * math.sin(lat) ** 2)
        h = p / math.cos(lat) - n
        lat = math.atan2(z, p * (1 - e2 * n / (n + h)))
    n = R_E / math.sqrt(1 - e2 * math.sin(lat) ** 2)
    return math.degrees(lat), math.degrees(lon), p / math.cos(lat) - n


def geodetic_to_ecef(lat, lon, h_km):
    e2 = F_WGS84 * (2 - F_WGS84)
    la, lo = math.radians(lat), math.radians(lon)
    n = R_E / math.sqrt(1 - e2 * math.sin(la) ** 2)
    return ((n + h_km) * math.cos(la) * math.cos(lo), (n + h_km) * math.cos(la) * math.sin(lo),
            (n * (1 - e2) + h_km) * math.sin(la))


def look_angle(sat_ecef, st):
    """Elevation, azimuth (deg) and slant range (km) of a satellite from a station."""
    ox, oy, oz = st["ecef"]
    dx, dy, dz = sat_ecef[0] - ox, sat_ecef[1] - oy, sat_ecef[2] - oz
    la, lo = math.radians(st["lat"]), math.radians(st["lon"])
    e = -math.sin(lo) * dx + math.cos(lo) * dy
    n = -math.sin(la) * math.cos(lo) * dx - math.sin(la) * math.sin(lo) * dy + math.cos(la) * dz
    u = math.cos(la) * math.cos(lo) * dx + math.cos(la) * math.sin(lo) * dy + math.sin(la) * dz
    rng = math.sqrt(dx * dx + dy * dy + dz * dz)
    return math.degrees(math.asin(u / rng)), math.degrees(math.atan2(e, n)) % 360, rng


def sun_unit(jd):
    """Low-precision solar direction (Astronomical Almanac, ~0.01 deg)."""
    n = jd - 2451545.0
    L = math.radians((280.460 + 0.9856474 * n) % 360)
    g = math.radians((357.528 + 0.9856003 * n) % 360)
    lam = L + math.radians(1.915) * math.sin(g) + math.radians(0.020) * math.sin(2 * g)
    eps = math.radians(23.439 - 0.0000004 * n)
    return (math.cos(lam), math.cos(eps) * math.sin(lam), math.sin(eps) * math.sin(lam))


def sunlit(r, jd):
    """Cylindrical Earth-shadow model."""
    s = sun_unit(jd)
    proj = r[0] * s[0] + r[1] * s[1] + r[2] * s[2]
    perp = math.sqrt(sum((r[k] - proj * s[k]) ** 2 for k in range(3)))
    return not (proj < 0 and perp < R_E)


STATIONS = {
    "SRM Kattankulathur": (12.8230, 80.0444, 45, 10.0),
    "ISTRAC Bengaluru": (13.0346, 77.5116, 900, 10.0),
    "Svalbard (SvalSat)": (78.2298, 15.4078, 500, 5.0),
}


def make_station(name):
    lat, lon, alt_m, mask = STATIONS[name]
    return {"name": name, "lat": lat, "lon": lon, "mask": mask, "ecef": geodetic_to_ecef(lat, lon, alt_m / 1000)}


# ===========================================================================
# 3. Orbit time series, elements, passes
# ===========================================================================
def state(sat, when):
    r, v = sat.propagate((when - sat.epoch).total_seconds() / 60)
    jd = julian_date(when)
    ecef = teme_to_ecef(r, jd)
    lat, lon, alt = ecef_to_geodetic(*ecef)
    return {"time": when, "r": r, "v": v, "ecef": ecef, "lat": lat, "lon": lon, "alt": alt,
            "speed": math.sqrt(sum(c * c for c in v)), "sunlit": sunlit(r, jd)}


def orbit_series(sat, start, hours, step_s=60):
    n = int(hours * 3600 // step_s) + 1
    out = [state(sat, start + timedelta(seconds=k * step_s)) for k in range(n)]
    for s in out:                                   # solar beta angle
        r, v = s["r"], s["v"]
        h = (r[1] * v[2] - r[2] * v[1], r[2] * v[0] - r[0] * v[2], r[0] * v[1] - r[1] * v[0])
        hn = math.sqrt(sum(c * c for c in h))
        su = sun_unit(julian_date(s["time"]))
        s["beta"] = math.degrees(math.asin(sum(h[k] * su[k] for k in range(3)) / hn))
    return out


def elements(sat):
    n = sat.no_kozai / 60
    a = (MU / n ** 2) ** (1 / 3)
    period = 1440 / sat.rev_per_day
    return [("Semi-major axis", f"{a:.2f} km"), ("Eccentricity", f"{sat.ecco:.6f}"),
            ("Inclination", f"{math.degrees(sat.inclo):.4f}°"), ("RAAN", f"{math.degrees(sat.nodeo):.4f}°"),
            ("Argument of perigee", f"{math.degrees(sat.argpo):.4f}°"),
            ("Mean anomaly", f"{math.degrees(sat.mo):.4f}°"), ("Mean motion", f"{sat.rev_per_day:.6f} rev/day"),
            ("Orbital period", f"{period:.2f} min"), ("Apogee altitude", f"{a * (1 + sat.ecco) - R_E:.2f} km"),
            ("Perigee altitude", f"{a * (1 - sat.ecco) - R_E:.2f} km")], period, math.degrees(sat.inclo)


def orbit_summary(orb):
    lit = [s["sunlit"] for s in orb]
    spans, start = [], None
    for i, l in enumerate(lit):
        if not l and start is None:
            start = i
        elif l and start is not None:
            spans.append(i - start); start = None
    step = (orb[1]["time"] - orb[0]["time"]).total_seconds() / 60
    spans.sort()
    return {"min_alt": min(s["alt"] for s in orb), "max_alt": max(s["alt"] for s in orb),
            "sunlit": sum(lit) / len(lit), "eclipses": len(spans),
            "eclipse_min": spans[len(spans) // 2] * step if spans else 0,
            "beta": sum(s["beta"] for s in orb) / len(orb)}


def elevation_at(sat, st, when):
    return look_angle(state(sat, when)["ecef"], st)


def predict_passes(sat, st, start, hours):
    """Scan elevation every 30 s, then refine rise/set by bisection and the peak by
    golden-section search."""
    step = timedelta(seconds=30)
    n = int(hours * 3600 / 30)
    el = lambda t: elevation_at(sat, st, t)[0] - st["mask"]

    def cross(a, b):
        fa = el(a)
        for _ in range(20):
            m = a + (b - a) / 2
            fm = el(m)
            if (fm > 0) == (fa > 0):
                a, fa = m, fm
            else:
                b = m
        return a + (b - a) / 2

    passes, prev_t, prev_up, rise = [], start, el(start) > 0, None
    for k in range(1, n + 1):
        t = start + k * step
        up = el(t) > 0
        if up and not prev_up:
            rise = cross(prev_t, t)
        elif prev_up and not up and rise is not None:
            set_ = cross(prev_t, t)
            a, b = rise, set_                        # golden-section for culmination
            g = (math.sqrt(5) - 1) / 2
            for _ in range(40):
                c1, c2 = b - g * (b - a), a + g * (b - a)
                if el(c1) > el(c2):
                    b = c2
                else:
                    a = c1
            culm = a + (b - a) / 2
            passes.append({"satellite": sat.name, "rise": rise, "culm": culm, "set": set_,
                           "max_el": elevation_at(sat, st, culm)[0],
                           "dur": (set_ - rise).total_seconds() / 60,
                           "az_rise": elevation_at(sat, st, rise)[1], "az_set": elevation_at(sat, st, set_)[1]})
            rise = None
        prev_t, prev_up = t, up
    return passes


# ===========================================================================
# 4. SIMULATED telemetry — orbit-driven teaching model, NOT real spacecraft data
# ===========================================================================
PROFILE = dict(v_min=24.0, v_max=29.4, battery_wh=300.0, i_solar_max=10.0, bus_v=28.0, eff=0.82,
               p_base=110.0, p_tx=35.0, eirp_dbw=3.0, freq_mhz=2250.0, rx_gain=20.0, link_mask=5.0)


def demo_faults(hours):
    """(kind, start minute, duration minutes, magnitude). Start times scale with the window;
    durations are fixed so a longer window doesn't turn a fault into a different scenario."""
    s = hours * 60
    return [("solar_array_fault", 0.18 * s, 115, 0.55), ("thermal_runaway", 0.40 * s, 86, 28.0),
            ("battery_degradation", 0.62 * s, 173, 1.6), ("sensor_glitch", 0.85 * s, 6.0, 1.0),
            ("comms_dropout", 0.0, s, 1.0)]


def simulate(sat, st, start, hours, faults=(), seed=7, step_s=60):
    P, rnd = PROFILE, random.Random(seed)
    orb = orbit_series(sat, start, hours, step_s)
    n = len(orb)
    minutes = [k * step_s / 60 for k in range(n)]
    lit = [s["sunlit"] for s in orb]
    la = [look_angle(s["ecef"], st) for s in orb]
    in_view = [a[0] > P["link_mask"] for a in la]
    link = list(in_view)
    period = 1440 / sat.rev_per_day
    i_sol = [(P["i_solar_max"] * (0.86 + 0.12 * math.cos(2 * math.pi * m / period)) + rnd.gauss(0, 0.06))
             if l else 0.0 for m, l in zip(minutes, lit)]
    truth = [""] * n
    active = lambda f, k: f[1] <= minutes[k] < f[1] + f[2]
    for f in faults:
        if f[0] == "solar_array_fault":
            for k in range(n):
                if active(f, k):
                    i_sol[k] *= 1 - f[3]
                    if lit[k]:
                        truth[k] = f[0]
        if f[0] == "comms_dropout":                  # lose the first pass after mid-window
            ks = [k for k in range(n) if in_view[k] and minutes[k] > 0.5 * hours * 60]
            if ks:
                k = ks[0]
                while k < n and in_view[k]:
                    link[k], truth[k] = False, f[0]; k += 1
    i_sol = [max(0.0, x) for x in i_sol]

    soc, s = [], 78.0                                # battery energy balance
    for k in range(n):
        p_in = P["eff"] * P["bus_v"] * i_sol[k] * (max(0.0, (100 - s) / 5) if s > 95 else 1.0)
        load = P["p_base"] + P["p_tx"] * link[k]
        s = min(100.0, max(0.0, s + (p_in - load) * (step_s / 3600) / P["battery_wh"] * 100))
        soc.append(s)
    volt = [P["v_min"] + (P["v_max"] - P["v_min"]) * x / 100 + rnd.gauss(0, 0.03) for x in soc]

    def lag(hot, cold, tau, t0, noise):              # first-order thermal response
        a, t, out = 1 - math.exp(-(step_s / 60) / tau), t0, []
        for l in lit:
            t += ((hot if l else cold) - t) * a
            out.append(t + rnd.gauss(0, noise))
        return out

    frac = sum(lit) / len(lit)                                   # start at the orbit-averaged temperature,
    start_t = lambda hot, cold: hot * frac + cold * (1 - frac)   # where the thermal cycle actually settles
    panel = lag(72, -55, 9, start_t(72, -55), 0.6)
    bus = lag(29, 14, 35, start_t(29, 14), 0.25)
    batt = lag(19, 12, 55, start_t(19, 12), 0.15)
    for f in faults:
        for k in range(n):
            if not active(f, k):
                continue
            ramp = (minutes[k] - f[1]) / max(f[2], 1e-6)
            if f[0] == "thermal_runaway":
                bus[k] += f[3] * ramp; batt[k] += 0.55 * f[3] * ramp; truth[k] = f[0]
            elif f[0] == "battery_degradation":
                volt[k] -= f[3] * ramp; truth[k] = f[0]
        if f[0] == "sensor_glitch":
            for k in [k for k in range(n) if active(f, k)][::2]:
                panel[k] += rnd.choice((-1, 1)) * 45; truth[k] = f[0]
    rssi = []
    for k in range(n):
        if link[k]:
            fspl = 20 * math.log10(la[k][2]) + 20 * math.log10(P["freq_mhz"]) + 32.44
            rssi.append(P["eirp_dbw"] + 30 + P["rx_gain"] - fspl + rnd.gauss(0, 0.8))
        else:
            rssi.append(None)
    return {"orb": orb, "time": [s["time"] for s in orb], "minutes": minutes, "sunlit": lit,
            "elev": [a[0] for a in la], "in_view": in_view, "link": link, "battery_voltage_v": volt,
            "battery_soc_pct": soc, "solar_current_a": i_sol, "panel_temp_c": panel, "bus_temp_c": bus,
            "battery_temp_c": batt, "rssi_dbm": rssi, "truth": truth}


# ===========================================================================
# 5. Limit checking
# ===========================================================================
LIMITS = {"battery_voltage_v": (25.0, 25.8, 29.6, 30.0), "battery_soc_pct": (20.0, 35.0, 101.0, 101.0),
          "panel_temp_c": (-80.0, -70.0, 85.0, 95.0), "bus_temp_c": (0.0, 8.0, 38.0, 45.0),
          "battery_temp_c": (2.0, 5.0, 25.0, 30.0)}
CHANNEL_NAMES = {"battery_voltage_v": "Battery voltage", "battery_soc_pct": "Battery charge",
                 "panel_temp_c": "Panel temperature", "bus_temp_c": "Bus temperature",
                 "battery_temp_c": "Battery temperature", "comms_loss_in_view": "No signal while in view"}


def check_limits(tel):
    status = {}
    for ch, (rl, yl, yh, rh) in LIMITS.items():
        status[ch] = [2 if (v < rl or v > rh) else 1 if (v < yl or v > yh) else 0 for v in tel[ch]]
    status["comms_loss_in_view"] = [2 if (iv and not lk) else 0 for iv, lk in zip(tel["in_view"], tel["link"])]
    return status


def limit_events(tel, status):
    ev = []
    for ch, s in status.items():
        k = 0
        while k < len(s):
            if s[k]:
                j = k
                while j + 1 < len(s) and s[j + 1]:
                    j += 1
                ev.append({"channel": CHANNEL_NAMES[ch], "severity": "alert" if max(s[k:j + 1]) == 2 else "caution",
                           "start": tel["time"][k], "end": tel["time"][j], "minutes": j - k + 1})
                k = j + 1
            else:
                k += 1
    return sorted(ev, key=lambda e: e["start"])


# ===========================================================================
# 6. Anomaly detection: Isolation Forest (written from scratch) + envelope guard
# ===========================================================================
FEATURES = ["sunlit", "solar_residual_a", "voltage_vs_charge_v", "bus_temp_c", "battery_temp_c",
            "bus_minus_battery_c", "bus_temp_rate", "panel_spike_c"]
FEATURE_SUBSYSTEM = {"solar_residual_a": "power", "voltage_vs_charge_v": "power", "bus_temp_c": "thermal",
                     "battery_temp_c": "thermal", "bus_minus_battery_c": "thermal", "bus_temp_rate": "thermal",
                     "panel_spike_c": "thermal"}


def build_features(tel):
    P, n = PROFILE, len(tel["time"])
    bus, panel = tel["bus_temp_c"], tel["panel_temp_c"]
    diffs = [0.0] + [bus[k] - bus[k - 1] for k in range(1, n)]
    rows = []
    for k in range(n):
        lit = 1.0 if tel["sunlit"][k] else 0.0
        rate = sum(diffs[max(0, k - 4):k + 1]) / len(diffs[max(0, k - 4):k + 1])
        win = sorted(panel[max(0, k - 2):k + 3])
        med = win[len(win) // 2] if len(win) % 2 else (win[len(win) // 2 - 1] + win[len(win) // 2]) / 2
        rows.append([lit, tel["solar_current_a"][k] - 0.86 * P["i_solar_max"] * lit,
                     tel["battery_voltage_v"][k] - (P["v_min"] + (P["v_max"] - P["v_min"]) * tel["battery_soc_pct"][k] / 100),
                     bus[k], tel["battery_temp_c"][k], bus[k] - tel["battery_temp_c"][k], rate, abs(panel[k] - med)])
    return rows


def _c(n):
    """Average path length of an unsuccessful binary-search-tree lookup."""
    return 2 * (math.log(n - 1) + 0.5772156649) - 2 * (n - 1) / n if n > 2 else (1.0 if n == 2 else 0.0)


class IsolationForest:
    """Liu, Ting & Zhou (2008). Anomalies are isolated by fewer random splits:
    score s(x) = 2^(-E[h(x)] / c(psi)), higher = more anomalous."""

    def __init__(self, n_trees=200, sample=256, seed=0):
        self.n_trees, self.sample, self.rnd = n_trees, sample, random.Random(seed)

    def _grow(self, X, depth, limit):
        if depth >= limit or len(X) <= 1:
            return ("leaf", len(X))
        d = len(X[0])
        feats = [f for f in range(d) if min(r[f] for r in X) < max(r[f] for r in X)]
        if not feats:
            return ("leaf", len(X))
        f = self.rnd.choice(feats)
        lo, hi = min(r[f] for r in X), max(r[f] for r in X)
        split = self.rnd.uniform(lo, hi)
        return ("node", f, split, self._grow([r for r in X if r[f] < split], depth + 1, limit),
                self._grow([r for r in X if r[f] >= split], depth + 1, limit))

    def fit(self, X):
        psi = min(self.sample, len(X))
        limit = math.ceil(math.log2(psi))
        self.trees = [self._grow(self.rnd.sample(X, psi), 0, limit) for _ in range(self.n_trees)]
        self.cn = _c(psi)
        return self

    def _path(self, x, node, depth=0):
        while node[0] == "node":
            node = node[3] if x[node[1]] < node[2] else node[4]
            depth += 1
        return depth + _c(node[1])

    def score(self, x):
        return 2 ** (-sum(self._path(x, t) for t in self.trees) / self.n_trees / self.cn)


class AnomalyDetector:
    def fit(self, nominal_rows, pct=99.9, margin=0.15):
        self.forest = IsolationForest().fit(nominal_rows)
        scores = sorted(self.forest.score(r) for r in nominal_rows)
        self.threshold = scores[min(len(scores) - 1, int(pct / 100 * len(scores)))]
        cols = list(zip(*nominal_rows))
        self.mean = [sum(c) / len(c) for c in cols]
        self.std = [max(1e-9, math.sqrt(sum((v - m) ** 2 for v in c) / len(c))) for c, m in zip(cols, self.mean)]
        self.lo = [min(c) - margin * (max(c) - min(c)) - 1e-6 for c in cols]
        self.hi = [max(c) + margin * (max(c) - min(c)) + 1e-6 for c in cols]
        return self

    def detect(self, rows):
        out = []
        for r in rows:
            if_flag = self.forest.score(r) > self.threshold
            outside = [f for f in range(1, len(r)) if r[f] < self.lo[f] or r[f] > self.hi[f]]
            if outside:
                feat = max(outside, key=lambda f: abs(r[f] - self.mean[f]) / self.std[f])
            else:
                feat = max(range(1, len(r)), key=lambda f: abs(r[f] - self.mean[f]) / self.std[f])
            flag = if_flag or bool(outside)
            out.append({"if": if_flag, "env": bool(outside), "flag": flag,
                        "feature": FEATURES[feat] if flag else "",
                        "subsystem": FEATURE_SUBSYSTEM[FEATURES[feat]] if flag else ""})
        return out


def evaluate(pred, truth):
    tp = sum(p and t != "" for p, t in zip(pred, truth))
    fp = sum(p and t == "" for p, t in zip(pred, truth))
    fn = sum((not p) and t != "" for p, t in zip(pred, truth))
    kinds = sorted(set(truth) - {""})
    caught = sum(any(p and t == k for p, t in zip(pred, truth)) for k in kinds)
    return {"precision": tp / (tp + fp) if tp + fp else 0.0, "recall": tp / (tp + fn) if tp + fn else 0.0,
            "fp": fp, "caught": f"{caught} of {len(kinds)}"}


# ===========================================================================
# 7. Health scores and the full pipeline
# ===========================================================================
SUBSYSTEMS = {"power": ["battery_voltage_v", "battery_soc_pct"],
              "thermal": ["panel_temp_c", "bus_temp_c", "battery_temp_c"], "comms": ["comms_loss_in_view"]}


def band(x):
    return "nominal" if x >= 85 else "caution" if x >= 60 else "alert"


def health_scores(tel, status, det, window=30):
    n, scores = len(tel["time"]), {}
    for sub, chans in SUBSYSTEMS.items():
        worst = [max(status[c][k] for c in chans) for k in range(n)]
        ml = [1.0 if (d["flag"] and d["subsystem"] == sub) else 0.0 for d in det]
        vals = []
        for k in range(n):
            a = max(0, k - window + 1); m = window        # samples before the window count as nominal
            red = sum(1 for w in worst[a:k + 1] if w == 2) / m
            yel = sum(1 for w in worst[a:k + 1] if w == 1) / m
            vals.append(min(100.0, max(0.0, 100 - 100 * (red + 0.4 * yel + 0.75 * sum(ml[a:k + 1]) / m))))
        scores[sub] = vals
    scores["overall"] = [min(scores[s][k] for s in SUBSYSTEMS) for k in range(n)]
    return scores


def run_health(sat, st, start, hours, faults_on=True):
    ref = simulate(sat, st, start - timedelta(hours=48), 48, seed=1007)            # fault-free reference
    tel = simulate(sat, st, start, hours, demo_faults(hours) if faults_on else (), seed=7)
    status = check_limits(tel)
    det = AnomalyDetector().fit(build_features(ref)).detect(build_features(tel))
    lim = [max(status[c][k] for c in status) > 0 for k in range(len(tel["time"]))]
    metrics = [("Limit checks only", evaluate(lim, tel["truth"])),
               ("Isolation Forest only", evaluate([d["if"] for d in det], tel["truth"])),
               ("Forest + envelope guard", evaluate([d["flag"] for d in det], tel["truth"])),
               ("Limits + ML (used)", evaluate([a or d["flag"] for a, d in zip(lim, det)], tel["truth"]))]
    return {"tel": tel, "status": status, "det": det, "events": limit_events(tel, status),
            "scores": health_scores(tel, status, det), "metrics": metrics}


# ===========================================================================
# 8. A minimal PDF writer (vector graphics + Helvetica), from the PDF 1.4 spec
# ===========================================================================
PAGE_W, PAGE_H = 842, 595          # A4 landscape, points

_HELV = {" ": 278, "!": 278, "%": 889, "(": 333, ")": 333, "+": 584, ",": 278, "-": 333, ".": 278, "/": 278,
         ":": 278, ";": 278, "°": 400, "±": 584, "·": 278, "–": 556, "—": 1000, "×": 584, "|": 260, "'": 191,
         "A": 667, "B": 667, "C": 722, "D": 722, "E": 667, "F": 611, "G": 778, "H": 722, "I": 278, "J": 500,
         "K": 667, "L": 556, "M": 833, "N": 722, "O": 778, "P": 667, "Q": 778, "R": 722, "S": 667, "T": 611,
         "U": 722, "V": 667, "W": 944, "X": 667, "Y": 667, "Z": 611, "a": 556, "b": 556, "c": 500, "d": 556,
         "e": 556, "f": 278, "g": 556, "h": 556, "i": 222, "j": 222, "k": 500, "l": 222, "m": 833, "n": 556,
         "o": 556, "p": 556, "q": 556, "r": 333, "s": 500, "t": 278, "u": 556, "v": 500, "w": 722, "x": 500,
         "y": 500, "z": 500}


def text_width(s, size, bold=False):
    return sum(_HELV.get(ch, 556) for ch in s) * size / 1000 * (1.06 if bold else 1.0)


def _rgb(hexcol):
    h = hexcol.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def mix(hexcol, t):
    """Blend a colour toward white by t (0 = colour, 1 = white) — PDF 1.4 without transparency."""
    r, g, b = _rgb(hexcol)
    return "#%02x%02x%02x" % tuple(int(255 * (c + (1 - c) * t)) for c in (r, g, b))


def _pdf_str(s):
    out = []
    for b in s.encode("cp1252", errors="replace"):
        if b in (40, 41, 92):
            out.append("\\" + chr(b))
        elif 32 <= b <= 126:
            out.append(chr(b))
        else:
            out.append("\\%03o" % b)
    return "(" + "".join(out) + ")"


class Canvas:
    """Top-left origin drawing surface for one page."""

    def __init__(self):
        self.ops = []

    def _y(self, y):
        return PAGE_H - y

    def _stroke(self, col, w, dash):
        r, g, b = _rgb(col)
        self.ops.append(f"{r:.3f} {g:.3f} {b:.3f} RG {w:.2f} w " + (f"[{dash[0]} {dash[1]}] 0 d" if dash else "[] 0 d"))

    def _fill(self, col):
        r, g, b = _rgb(col)
        self.ops.append(f"{r:.3f} {g:.3f} {b:.3f} rg")

    def polyline(self, pts, col, w=1.0, dash=None):
        """Points may contain None to break the line."""
        self._stroke(col, w, dash)
        path, pen = [], False
        for p in pts:
            if p is None:
                pen = False
                continue
            path.append(f"{p[0]:.2f} {self._y(p[1]):.2f} {'l' if pen else 'm'}")
            pen = True
        if path:
            self.ops.append(" ".join(path) + " S")

    def rect(self, x, y, w, h, fill=None, stroke=None, lw=0.6):
        if fill:
            self._fill(fill)
        if stroke:
            self._stroke(stroke, lw, None)
        op = "B" if fill and stroke else "f" if fill else "S"
        self.ops.append(f"{x:.2f} {self._y(y + h):.2f} {w:.2f} {h:.2f} re {op}")

    def circle(self, cx, cy, r, fill=None, stroke=None, lw=0.6):
        k = 0.5523 * r
        y = self._y(cy)
        if fill:
            self._fill(fill)
        if stroke:
            self._stroke(stroke, lw, None)
        self.ops.append(f"{cx + r:.2f} {y:.2f} m {cx + r:.2f} {y + k:.2f} {cx + k:.2f} {y + r:.2f} {cx:.2f} {y + r:.2f} c "
                        f"{cx - k:.2f} {y + r:.2f} {cx - r:.2f} {y + k:.2f} {cx - r:.2f} {y:.2f} c "
                        f"{cx - r:.2f} {y - k:.2f} {cx - k:.2f} {y - r:.2f} {cx:.2f} {y - r:.2f} c "
                        f"{cx + k:.2f} {y - r:.2f} {cx + r:.2f} {y - k:.2f} {cx + r:.2f} {y:.2f} c "
                        + ("B" if fill and stroke else "f" if fill else "S"))

    def diamond(self, cx, cy, r, fill):
        self._fill(fill)
        y = self._y(cy)
        self.ops.append(f"{cx:.2f} {y + r:.2f} m {cx + r:.2f} {y:.2f} l {cx:.2f} {y - r:.2f} l {cx - r:.2f} {y:.2f} l f")

    def cross(self, cx, cy, r, col, w=0.9):
        self.polyline([(cx - r, cy - r), (cx + r, cy + r), None, (cx - r, cy + r), (cx + r, cy - r)], col, w)

    def text(self, x, y, s, size=9, col="#1B2A3A", bold=False, align="left", mono=False):
        s = str(s)
        if align != "left":
            wdt = text_width(s, size, bold)
            x -= wdt if align == "right" else wdt / 2
        self._fill(col)
        self.ops.append(f"BT /{'F3' if mono else 'F2' if bold else 'F1'} {size:.1f} Tf {x:.2f} {self._y(y):.2f} Td {_pdf_str(s)} Tj ET")

    def clip(self, x, y, w, h):
        self.ops.append(f"q {x:.2f} {self._y(y + h):.2f} {w:.2f} {h:.2f} re W n")

    def unclip(self):
        self.ops.append("Q")


def write_pdf(pages, path, title):
    objs = []

    def add(body):
        objs.append(body)
        return len(objs)

    f1 = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    f2 = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")
    f3 = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier /Encoding /WinAnsiEncoding >>")
    pages_id = len(objs) + 2 * len(pages) + 1
    kids = []
    for c in pages:
        data = zlib.compress("\n".join(c.ops).encode("latin-1"))
        sid = add(b"<< /Length %d /Filter /FlateDecode >>\nstream\n" % len(data) + data + b"\nendstream")
        kids.append(add(("<< /Type /Page /Parent %d 0 R /MediaBox [0 0 %d %d] /Contents %d 0 R "
                         "/Resources << /Font << /F1 %d 0 R /F2 %d 0 R /F3 %d 0 R >> >> >>"
                         % (pages_id, PAGE_W, PAGE_H, sid, f1, f2, f3)).encode()))
    add(("<< /Type /Pages /Kids [%s] /Count %d >>" % (" ".join(f"{k} 0 R" for k in kids), len(kids))).encode())
    cat = add(b"<< /Type /Catalog /Pages %d 0 R >>" % pages_id)
    info = add(("<< /Title %s /Producer (satellite_report.py, Python standard library) >>" % _pdf_str(title)).encode())
    out, offsets = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"), []
    for i, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size %d /Root %d 0 R /Info %d 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, cat, info, xref)
    with open(path, "wb") as fh:
        fh.write(out)


# ===========================================================================
# 9. Charts and page layouts
# ===========================================================================
INK, MUTED, RULE, PAPER, PANEL = "#1B2A3A", "#5C6B7A", "#DCE1DA", "#F3F5F2", "#FFFFFF"
EARTH, LAND, ECL = "#DCE6EE", "#8FA3B5", "#E6E9EC"
NOMINAL, CAUTION, ALERT, STATION = "#2E7D4F", "#C98A12", "#C0392B", "#8A3FA0"
SAT_COLORS = ["#2B59C3", "#B5502C", "#2E7D4F", "#8A3FA0", "#C98A12"]
M = 36                                             # page margin


def coastlines():
    raw = json.loads(zlib.decompress(base64.b64decode("".join(COAST_B64.split()))))
    lines = []
    for flat in raw:
        x, y, pts = flat[0], flat[1], [(flat[0] / 5, flat[1] / 5)]
        for k in range(2, len(flat), 2):
            x += flat[k]; y += flat[k + 1]
            pts.append((x / 5, y / 5))
        lines.append(pts)
    return lines


def nice_ticks(lo, hi, n=5):
    span = hi - lo if hi > lo else 1
    raw = span / n
    mag = 10 ** math.floor(math.log10(raw))
    step = min((s * mag for s in (1, 2, 2.5, 5, 10) if s * mag >= raw), default=10 * mag)
    t, out = math.ceil(lo / step) * step, []
    while t <= hi + 1e-9:
        out.append(round(t, 10)); t += step
    return out


def fmt_num(v):
    return f"{v:.0f}" if abs(v - round(v)) < 1e-9 else f"{v:g}"


class Axes:
    def __init__(self, c, x, y, w, h, x0, x1, y0, y1, title=None, yticks=None, xlabels=True, times=None, ysuffix=""):
        self.c, self.x, self.y, self.w, self.h = c, x, y, w, h
        self.x0, self.x1, self.y0, self.y1 = x0, x1, y0, y1
        if title:
            c.text(x, y - 5, title, 8.5, MUTED)
        for t in (yticks if yticks is not None else nice_ticks(y0, y1, 4)):
            if y0 <= t <= y1:
                c.polyline([(x, self.fy(t)), (x + w, self.fy(t))], RULE, 0.4)
                c.text(x - 4, self.fy(t) + 2.8, fmt_num(t) + ysuffix, 7, MUTED, align="right")
        if times is not None and xlabels:
            self.time_labels(times)

    def fx(self, v):
        return self.x + (v - self.x0) / (self.x1 - self.x0) * self.w

    def fy(self, v):
        return self.y + self.h - (v - self.y0) / (self.y1 - self.y0) * self.h

    def time_labels(self, times):
        t0 = times[0]
        first = (t0 + timedelta(hours=3)).replace(minute=0, second=0, microsecond=0)
        first -= timedelta(hours=first.hour % 3)
        t = first
        while t <= times[-1]:
            m = (t - t0).total_seconds() / 60
            if m >= 0:
                xx = self.fx(m)
                self.c.polyline([(xx, self.y + self.h), (xx, self.y + self.h + 3)], MUTED, 0.5)
                self.c.text(xx, self.y + self.h + 11, t.strftime("%H:%M"), 7, MUTED, align="center")
                if t.hour == 0:
                    self.c.text(xx, self.y + self.h + 19, t.strftime("%d %b"), 6.5, MUTED, align="center")
            t += timedelta(hours=3)

    def shade(self, minutes, mask, col=ECL):
        start = None
        for k, v in enumerate(mask + [False]):
            if v and start is None:
                start = k
            if not v and start is not None:
                a, b = self.fx(minutes[start]), self.fx(minutes[min(k, len(minutes) - 1)])
                self.c.rect(a, self.y, max(b - a, 0.5), self.h, fill=col)
                start = None

    def line(self, xs, ys, col, w=1.0, dash=None):
        pts = [None if y is None else (self.fx(x), self.fy(y)) for x, y in zip(xs, ys)]
        self.c.clip(self.x, self.y - 1, self.w, self.h + 2)
        self.c.polyline(pts, col, w, dash)
        self.c.unclip()

    def hline(self, v, col, dash=(2, 2)):
        if self.y0 <= v <= self.y1:
            self.c.polyline([(self.x, self.fy(v)), (self.x + self.w, self.fy(v))], col, 0.6, dash)

    def frame(self):
        self.c.polyline([(self.x, self.y + self.h), (self.x + self.w, self.y + self.h)], MUTED, 0.5)


def header(c, page_no, total, sat_name, subtitle, tab):
    c.rect(0, 0, PAGE_W, PAGE_H, fill=PAPER)
    c.text(M, 44, sat_name, 22, INK, bold=True)
    c.text(M, 60, subtitle, 8.5, MUTED)
    tabs = ["Tracking", "Passes", "Telemetry & health", "Telemetry", "Fleet", "Orbital elements"]
    x = M
    for t in tabs:
        w = text_width(t, 9) + 16
        on = t == tab
        c.text(x + 8, 82, t, 9, "#2B59C3" if on else INK, bold=on)
        if on:
            c.rect(x, 87, w, 1.8, fill="#2B59C3")
        x += w
    c.polyline([(M, 89), (PAGE_W - M, 89)], RULE, 0.6)
    c.text(PAGE_W - M, PAGE_H - 16, f"Page {page_no} of {total} · generated by satellite_report.py (Python standard library only)",
           7, MUTED, align="right")


def banner(c, y, text, fill, col):
    c.rect(M, y, PAGE_W - 2 * M, 22, fill=fill)
    c.text(M + 10, y + 14.5, text, 8.5, col)


def card(c, x, y, w, h):
    c.rect(x, y, w, h, fill=PANEL, stroke=RULE, lw=0.6)


def table(c, x, y, cols, rows, row_h=15, size=8, max_rows=None):
    """cols: list of (header, width, align). Returns y after the table."""
    cx = x
    for head, w, al in cols:
        c.text(cx + (w - 6 if al == "right" else 6), y + 11, head, size, MUTED, align="right" if al == "right" else "left")
        cx += w
    total_w = sum(w for _, w, _ in cols)
    c.polyline([(x, y + row_h), (x + total_w, y + row_h)], RULE, 0.6)
    yy = y + row_h
    for r in rows[:max_rows]:
        cx = x
        for (head, w, al), val in zip(cols, r):
            if isinstance(val, tuple):           # (text, colour-dot)
                c.circle(cx + 9, yy + 7.8, 2.6, fill=val[1])
                c.text(cx + 16, yy + 11, val[0], size, INK)
            else:
                c.text(cx + (w - 6 if al == "right" else 6), yy + 11, val, size, INK, align="right" if al == "right" else "left")
            cx += w
        yy += row_h
        c.polyline([(x, yy), (x + total_w, yy)], "#ECEFEA", 0.5)
    if max_rows and len(rows) > max_rows:
        c.text(x + 6, yy + 11, f"… and {len(rows) - max_rows} more", size, MUTED)
        yy += row_h
    return yy


def draw_globe(c, cx, cy, rad, orb, idx, st, lines, col):
    lat0, lon0 = math.radians(max(-60, min(60, orb[idx]["lat"]))), math.radians(orb[idx]["lon"])
    u = (math.cos(lat0) * math.cos(lon0), math.cos(lat0) * math.sin(lon0), math.sin(lat0))  # towards viewer
    e = (-math.sin(lon0), math.cos(lon0), 0.0)
    n = (-math.sin(lat0) * math.cos(lon0), -math.sin(lat0) * math.sin(lon0), math.cos(lat0))
    s = rad / R_E

    def proj(p):
        d = p[0] * u[0] + p[1] * u[1] + p[2] * u[2]
        x, y = p[0] * e[0] + p[1] * e[1] + p[2] * e[2], p[0] * n[0] + p[1] * n[1] + p[2] * n[2]
        return (cx + x * s, cy - y * s), d > 0 or math.hypot(x, y) > R_E

    def sph(lat, lon):
        la, lo = math.radians(lat), math.radians(lon)
        return (R_E * math.cos(la) * math.cos(lo), R_E * math.cos(la) * math.sin(lo), R_E * math.sin(la))

    c.circle(cx, cy, rad, fill=EARTH, stroke=LAND, lw=0.6)
    grat = []
    for lat in range(-60, 61, 30):
        grat += [proj(sph(lat, lo)) for lo in range(-180, 181, 5)] + [(None, False)]
    for lon in range(-180, 180, 30):
        grat += [proj(sph(la, lon)) for la in range(-90, 91, 5)] + [(None, False)]
    c.polyline([p if (p and v) else None for p, v in grat], "#C8D3DC", 0.35)
    pts = []
    for line in lines:
        pts += [(lambda q: q[0] if q[1] and (sph(la, lo)[0] * u[0] + sph(la, lo)[1] * u[1] + sph(la, lo)[2] * u[2]) > 0 else None)(proj(sph(la, lo)))
                for lo, la in line] + [None]
    c.polyline(pts, LAND, 0.55)
    seg = orb[max(0, idx - 47): idx + 47]
    c.polyline([q[0] if q[1] else None for q in (proj(p["ecef"]) for p in seg)], col, 2.0)
    (sx, sy), vis = proj(orb[idx]["ecef"])
    if vis:
        c.circle(sx, sy, 3.6, fill=INK)
    (gx, gy), gvis = proj(st["ecef"])
    if gvis and (st["ecef"][0] * u[0] + st["ecef"][1] * u[1] + st["ecef"][2] * u[2]) > 0:
        c.diamond(gx, gy, 3.8, STATION)


def draw_map(c, x, y, w, h, tracks, st, lines, idx=None, single=False):
    ax = Axes(c, x, y, w, h, -180, 180, -90, 90, yticks=[-60, -30, 0, 30, 60], ysuffix="°")
    c.rect(x, y, w, h, stroke=RULE, lw=0.5)
    for lo in range(-150, 181, 30):
        c.polyline([(ax.fx(lo), y), (ax.fx(lo), y + h)], "#EEF1EC", 0.4)
        if lo % 60 == 0:
            c.text(ax.fx(lo), y + h + 10, f"{lo}°", 7, MUTED, align="center")
    pts = []
    for line in lines:
        prev = None
        for lo, la in line:
            if prev is not None and abs(lo - prev) > 180:
                pts.append(None)
            pts.append((ax.fx(lo), ax.fy(la))); prev = lo
        pts.append(None)
    c.clip(x, y, w, h)
    c.polyline(pts, LAND, 0.5)

    def track(orb, lo_i, hi_i, col, wdt):
        pts, prev = [], None
        for p in orb[lo_i:hi_i]:
            if prev is not None and abs(p["lon"] - prev) > 180:
                pts.append(None)
            pts.append((ax.fx(p["lon"]), ax.fy(p["lat"]))); prev = p["lon"]
        c.polyline(pts, col, wdt)

    for k, (name, orb, col) in enumerate(tracks):
        if single:
            track(orb, 0, len(orb), mix(col, 0.7), 0.6)
            track(orb, max(0, idx - 47), idx + 47, col, 1.8)
        else:
            track(orb, 0, len(orb), col, 1.2)
        i = idx if idx is not None else 0
        c.circle(ax.fx(orb[i]["lon"]), ax.fy(orb[i]["lat"]), 3.8, fill=col, stroke="#FFFFFF", lw=1)
    c.unclip()
    c.diamond(ax.fx(st["lon"]), ax.fy(st["lat"]), 4, STATION)
    c.text(ax.fx(st["lon"]) + 6, ax.fy(st["lat"]) - 4, st["name"], 7, STATION)


def legend(c, x, y, items, size=7.5):
    for label, col in items:
        c.polyline([(x, y - 2.5), (x + 12, y - 2.5)], col, 1.8)
        c.text(x + 16, y, label, size, INK)
        x += text_width(label, size) + 30


# ------------------------------------------------------------------ pages
def page_tracking(c, sat, orb, idx, st, lines, col, stale_note):
    y = 98
    if stale_note:
        banner(c, y, stale_note, "#DDE9F5", "#1F4E8C"); y += 30
    p = orb[idx]
    vals = [("Time (UTC)", p["time"].strftime("%H:%M")), ("Latitude", f"{p['lat']:.2f}°"),
            ("Longitude", f"{p['lon']:.2f}°"), ("Altitude", f"{p['alt']:.1f} km"),
            ("Speed", f"{p['speed']:.3f} km/s"), ("Sun", "Sunlit" if p["sunlit"] else "Eclipse")]
    w = (PAGE_W - 2 * M) / len(vals)
    for k, (lab, v) in enumerate(vals):
        c.text(M + k * w, y + 10, lab, 8, MUTED)
        c.text(M + k * w, y + 32, v, 17, INK)
    y += 46
    ch = PAGE_H - y - 70
    cw = (PAGE_W - 2 * M - 14) / 2
    card(c, M, y, cw, ch)
    draw_globe(c, M + cw / 2, y + ch / 2 + 4, min(cw, ch) / 2 - 22, orb, idx, st, lines, col)
    legend(c, M + 12, y + ch - 10, [("Track ±1 orbit", col), (sat.name, INK)])
    card(c, M + cw + 14, y, cw, ch)
    draw_map(c, M + cw + 14 + 34, y + 20, cw - 48, ch - 50, [(sat.name, orb, col)], st, lines, idx, single=True)
    s = orbit_summary(orb)
    c.text(M, PAGE_H - 44, f"Over this window the altitude ranges {s['min_alt']:.0f}–{s['max_alt']:.0f} km, the satellite is "
           f"sunlit {100 * s['sunlit']:.0f} % of the time across {s['eclipses']} eclipses (typically "
           f"{s['eclipse_min']:.0f} min), and the mean solar beta angle is {s['beta']:.1f}°.", 8.5, INK)


def page_passes(c, sat, passes, st, look):
    y = 98
    if not passes:
        banner(c, y, f"No passes above {st['mask']:.0f}° elevation in this window. Try a longer window or another station.",
               "#DDE9F5", "#1F4E8C")
        return
    tw = 470
    card(c, M, y, tw, PAGE_H - y - 40)
    rows = [(p["rise"].strftime("%d %b %H:%M:%S"), p["culm"].strftime("%H:%M:%S"), p["set"].strftime("%H:%M:%S"),
             f"{p['max_el']:.1f}°", f"{p['dur']:.1f} min", f"{p['az_rise']:.0f}° to {p['az_set']:.0f}°") for p in passes]
    c.text(M + 8, y + 18, f"Passes over {st['name']} (mask {st['mask']:.0f}°)", 10, INK, bold=True)
    table(c, M + 4, y + 28, [("Rise (UTC)", 96, "left"), ("Culmination", 70, "left"), ("Set", 64, "left"),
                             ("Max elevation", 78, "right"), ("Duration", 66, "right"), ("Azimuth", 88, "right")],
          rows, max_rows=22)
    x0 = M + tw + 14
    w = PAGE_W - M - x0
    card(c, x0, y, w, PAGE_H - y - 40)
    cx, cy, r = x0 + w / 2, y + 30 + (w - 40) / 2, (w - 60) / 2
    c.circle(cx, cy, r, fill="#FBFCFB", stroke=RULE)
    for el in (30, 60):
        c.circle(cx, cy, r * (90 - el) / 90, stroke=RULE, lw=0.5)
        c.text(cx + 3, cy - r * (90 - el) / 90 + 9, f"{el}°", 6.5, MUTED)
    for az, lab in ((0, "N"), (90, "E"), (180, "S"), (270, "W")):
        a = math.radians(az)
        c.polyline([(cx, cy), (cx + r * math.sin(a), cy - r * math.cos(a))], RULE, 0.5)
        c.text(cx + (r + 9) * math.sin(a), cy - (r + 9) * math.cos(a) + 3, lab, 8, MUTED, align="center")
    cols = SAT_COLORS + [ALERT, MUTED]
    items = []
    for k, (p, track) in enumerate(zip(passes, look)):
        pts = [(cx + r * (90 - el) / 90 * math.sin(math.radians(az)), cy - r * (90 - el) / 90 * math.cos(math.radians(az)))
               for el, az in track]
        c.polyline(pts, cols[k % len(cols)], 1.6)
        items.append((f"{p['rise']:%d %b %H:%M} · {p['max_el']:.0f}°", cols[k % len(cols)]))
    yy = cy + r + 28
    for k in range(0, len(items), 2):
        legend(c, x0 + 14, yy, items[k:k + 2]); yy += 12
    c.text(x0 + 10, y + 16, "Sky plot (zenith at centre)", 9, INK, bold=True)


def page_health(c, run, hours):
    y = 98
    banner(c, y, "SIMULATED — not real spacecraft telemetry. Values are generated from the orbit geometry to demonstrate "
                 "the monitoring pipeline; a TLE contains no spacecraft health data.", "#F6DEDB", ALERT)
    y += 30
    sc, w = run["scores"], (PAGE_W - 2 * M - 30) / 4
    for k, sub in enumerate(["overall", "power", "thermal", "comms"]):
        x = M + k * (w + 10)
        card(c, x, y, w, 50)
        c.text(x + 10, y + 14, f"{sub.title()} health, end of window", 8, MUTED)
        c.text(x + 10, y + 34, f"{sc[sub][-1]:.0f} / 100", 16, INK)
        lo = min(sc[sub])
        c.text(x + 10, y + 45, f"Lowest in window: {lo:.0f} ({band(lo)})", 7.5, {"nominal": NOMINAL, "caution": CAUTION, "alert": ALERT}[band(lo)])
    y += 60
    card(c, M, y, PAGE_W - 2 * M, 190)
    tel = run["tel"]
    ax = Axes(c, M + 40, y + 26, PAGE_W - 2 * M - 56, 140, 0, tel["minutes"][-1], -2, 102, yticks=[0, 20, 40, 60, 80, 100],
              times=tel["time"])
    for y0, y1, colr in ((85, 102, "#EEF5F0"), (60, 85, "#FBF5E8"), (-2, 60, "#FBEDEB")):
        c.rect(ax.x, ax.fy(y1), ax.w, ax.fy(y0) - ax.fy(y1), fill=colr)
    ax.shade(tel["minutes"], [not s for s in tel["sunlit"]], "#E4E7E4")
    for t in (0, 20, 40, 60, 80, 100):
        c.polyline([(ax.x, ax.fy(t)), (ax.x + ax.w, ax.fy(t))], "#FFFFFF", 0.4)
    for sub, colr in (("power", "#2B59C3"), ("thermal", "#B5502C"), ("comms", STATION)):
        ax.line(tel["minutes"], sc[sub], colr, 1.3)
    ax.frame()
    legend(c, M + 40, y + 14, [("Power", "#2B59C3"), ("Thermal", "#B5502C"), ("Comms", STATION), ("Eclipse (shaded)", "#C9CEC9")])
    c.text(M + 12, y + 100, "Score", 7.5, MUTED)
    y += 200
    half = (PAGE_W - 2 * M - 14) / 2
    card(c, M, y, half, PAGE_H - y - 30)
    c.text(M + 8, y + 16, "Limit events", 10, INK, bold=True)
    rows = [((e["channel"], ALERT if e["severity"] == "alert" else CAUTION), e["severity"], e["start"].strftime("%d %b %H:%M"),
             e["end"].strftime("%d %b %H:%M"), str(e["minutes"])) for e in run["events"]]
    table(c, M + 4, y + 22, [("Channel", 130, "left"), ("Severity", 52, "left"), ("Start (UTC)", 70, "left"),
                             ("End (UTC)", 70, "left"), ("Min", 42, "right")], rows or [("No violations", "", "", "", "")],
          max_rows=6)
    x0 = M + half + 14
    card(c, x0, y, half, PAGE_H - y - 30)
    c.text(x0 + 8, y + 16, "Detector performance vs injected faults", 10, INK, bold=True)
    rows = [(name, f"{m['precision']:.3f}", f"{m['recall']:.3f}", str(m["fp"]), m["caught"]) for name, m in run["metrics"]]
    table(c, x0 + 4, y + 22, [("Detector", 124, "left"), ("Precision", 58, "right"), ("Recall", 50, "right"),
                              ("False alarms", 70, "right"), ("Faults caught", 70, "right")], rows)


def page_telemetry(c, run):
    tel, det = run["tel"], run["det"]
    c.text(PAGE_W - M, 108, "SIMULATED — not real spacecraft telemetry", 8.5, ALERT, bold=True, align="right")
    legend(c, M, 108, [("Panel", CAUTION), ("Bus", "#B5502C"), ("Battery", NOMINAL), ("Red limit", ALERT)])
    c.cross(M + 290, 105.5, 2.6, ALERT); c.text(M + 297, 108, "Detector flag", 7.5, INK)
    c.rect(M + 370, 102, 12, 7, fill="#E4E7E4"); c.text(M + 386, 108, "Eclipse", 7.5, INK)
    card(c, M, 116, PAGE_W - 2 * M, PAGE_H - 116 - 30)
    specs = [("Battery voltage (V)", ["battery_voltage_v"], (24.5, 30.5)),
             ("Solar array current (A)", ["solar_current_a"], (-0.5, 11)),
             ("Temperatures: panel, bus, battery (°C)", ["panel_temp_c", "bus_temp_c", "battery_temp_c"], None),
             ("Downlink RSSI at station (dBm)", ["rssi_dbm"], None)]
    top, h, gap = 136, 80, 26
    where = {"voltage_vs_charge_v": (0, "battery_voltage_v"), "solar_residual_a": (1, "solar_current_a"),
             "panel_spike_c": (2, "panel_temp_c")}
    colours = {"battery_voltage_v": "#2B59C3", "solar_current_a": "#B5502C", "panel_temp_c": CAUTION,
               "bus_temp_c": "#B5502C", "battery_temp_c": NOMINAL, "rssi_dbm": STATION}
    for r, (title, chans, rng) in enumerate(specs):
        vals = [v for ch in chans for v in tel[ch] if v is not None]
        lo, hi = rng if rng else ((min(vals) - 3, max(vals) + 3) if vals else (-120, -90))
        ax = Axes(c, M + 44, top + r * (h + gap), PAGE_W - 2 * M - 60, h, 0, tel["minutes"][-1], lo, hi, title=title,
                  times=tel["time"] if r == 3 else None)
        ax.shade(tel["minutes"], [not s for s in tel["sunlit"]], "#E4E7E4")
        for ch in chans:
            if ch in LIMITS:
                ax.hline(LIMITS[ch][0], ALERT); ax.hline(LIMITS[ch][3], ALERT)
            if ch == "rssi_dbm":
                for m, v in zip(tel["minutes"], tel[ch]):
                    if v is not None:
                        c.circle(ax.fx(m), ax.fy(v), 1.3, fill=STATION)
            else:
                ax.line(tel["minutes"], tel[ch], colours[ch], 0.8 if ch == "panel_temp_c" else 1.0)
        for k, d in enumerate(det):
            if d["flag"]:
                row, ch = where.get(d["feature"], (2, "bus_temp_c"))
                if row == r:
                    c.cross(ax.fx(tel["minutes"][k]), ax.fy(tel[ch][k]), 1.8, ALERT, 0.7)
        ax.frame()


def page_fleet(c, fleet, snap, orbits, allp, st, lines):
    y = 98
    card(c, M, y, PAGE_W - 2 * M, 22 + 15 * (len(snap) + 1))
    table(c, M + 4, y + 6, [("Satellite", 170, "left"), ("NORAD", 60, "right"), ("Latitude", 70, "right"),
                            ("Longitude", 70, "right"), ("Altitude", 70, "right"), ("Inclination", 76, "right"),
                            ("Period", 70, "right"), ("TLE age", 70, "right")], snap)
    y += 32 + 15 * (len(snap) + 1)
    mw = 470
    card(c, M, y, mw, PAGE_H - y - 30)
    draw_map(c, M + 34, y + 26, mw - 48, PAGE_H - y - 88, [(n, o, col) for n, o, col in orbits], st, lines)
    legend(c, M + 34, y + 16, [(n if len(n) < 20 else n.title()[:22], col) for n, _, col in orbits])
    x0 = M + mw + 14
    card(c, x0, y, PAGE_W - M - x0, PAGE_H - y - 30)
    c.text(x0 + 8, y + 16, f"All passes over {st['name']}", 10, INK, bold=True)
    rows = [(p["satellite"].replace("HUBBLE SPACE TELESCOPE", "Hubble"), p["rise"].strftime("%d %b %H:%M"),
             f"{p['max_el']:.0f}°", f"{p['dur']:.1f}") for p in allp]
    yy = table(c, x0 + 4, y + 22, [("Satellite", 90, "left"), ("Rise (UTC)", 76, "left"), ("Max el", 50, "right"),
                                   ("Min", 40, "right")], rows, row_h=13, size=7.5, max_rows=14)
    clashes = sum(1 for i in range(len(allp)) for j in range(i + 1, len(allp))
                  if allp[i]["satellite"] != allp[j]["satellite"] and allp[j]["rise"] < allp[i]["set"])
    c.text(x0 + 8, yy + 14, "No overlapping passes: one antenna can serve the whole fleet." if not clashes
           else f"{clashes} overlapping pass pairs need antenna scheduling.", 7.5, MUTED)


def page_elements(c, sat, elems):
    y = 98
    card(c, M, y, 380, 22 + 17 * 11)
    table(c, M + 4, y + 6, [("Element", 180, "left"), ("Value", 190, "left")], elems, row_h=17, size=9)
    x0 = M + 394
    card(c, x0, y, PAGE_W - M - x0, 90)
    c.text(x0 + 10, y + 18, "Two-line element set", 10, INK, bold=True)
    for k, ln in enumerate([sat.name, sat.line1, sat.line2]):
        c.text(x0 + 10, y + 40 + 14 * k, ln, 6.9, INK, mono=True)
    c.text(x0 + 10, y + 120, "Elements are TLE mean elements; semi-major axis from Kepler's third law,", 8.5, INK)
    c.text(x0 + 10, y + 133, "a = (mu / n^2)^(1/3), with mu = 398 600.4418 km^3/s^2.", 8.5, INK)


# ===========================================================================
# 10. Main
# ===========================================================================
def load_satellites(args):
    if args.norad:
        import urllib.request
        sats = []
        for nid in args.norad:
            url = f"https://celestrak.org/NORAD/elements/gp.php?CATNR={nid}&FORMAT=TLE"
            with urllib.request.urlopen(url, timeout=15) as r:
                ln = [x.rstrip() for x in r.read().decode().splitlines() if x.strip()]
            sats.append(SGP4(ln[0].strip(), ln[1], ln[2]))
        return sats
    text = open(args.tle).read() if args.tle else SAMPLE_TLES
    ln = [x.rstrip() for x in text.splitlines() if x.strip()]
    return [SGP4(ln[i].strip(), ln[i + 1], ln[i + 2]) for i in range(0, len(ln) - 2, 3)
            if ln[i + 1].startswith("1 ") and ln[i + 2].startswith("2 ")]


def main():
    ap = argparse.ArgumentParser(description="Satellite tracking & health report (PDF), standard library only.")
    ap.add_argument("--sat", default=None, help="Satellite name (default: first in the file)")
    ap.add_argument("--station", default="SRM Kattankulathur", choices=list(STATIONS))
    ap.add_argument("--hours", type=float, default=24.0)
    ap.add_argument("--at", default="auto", help="auto | now | epoch | ISO time, e.g. 2024-02-14T12:00:00")
    ap.add_argument("--minute", type=int, default=0, help="Minute into the window shown on the tracking page")
    ap.add_argument("--tle", help="Path to a 3-line TLE file")
    ap.add_argument("--norad", type=int, nargs="*", help="Fetch live TLEs from Celestrak (needs internet)")
    ap.add_argument("--no-faults", action="store_true", help="Simulate without injected faults")
    ap.add_argument("--out", default="satellite_report.pdf")
    args = ap.parse_args()

    sats = load_satellites(args)
    if not sats:
        sys.exit("No valid TLEs found.")
    names = [s.name for s in sats]
    sat = sats[names.index(args.sat)] if args.sat in names else sats[0]
    if args.sat and args.sat not in names:
        print(f"'{args.sat}' not found; using {sat.name}. Available: {names}")
    si = sats.index(sat)
    col = SAT_COLORS[si % len(SAT_COLORS)]
    st = make_station(args.station)

    now = datetime.now(timezone.utc)
    age = (now - sat.epoch).total_seconds() / 86400
    stale_note = None
    if args.at == "now":
        start = now
    elif args.at == "epoch" or (args.at == "auto" and abs(age) > 14):
        start = sat.epoch
        if args.at == "auto":
            stale_note = (f"This TLE is {age:.0f} days old, so the view starts at its epoch "
                          f"({sat.epoch:%d %b %Y %H:%M} UTC). Use live data (--norad) for current positions.")
    elif args.at == "auto":
        start = now
    else:
        try:
            start = datetime.fromisoformat(args.at.replace("Z", "+00:00"))
        except ValueError as exc:
            ap.error(f"Invalid --at timestamp: {exc}")
        start = start.replace(tzinfo=timezone.utc) if start.tzinfo is None else start.astimezone(timezone.utc)

    if args.hours <= 0:
        ap.error("--hours must be positive")

    t_start = time.time()
    print(f"Satellite: {sat.name} (NORAD {sat.satnum}), window {start:%d %b %Y %H:%M} UTC + {args.hours:g} h")
    print("  propagating orbit (SGP4)...")
    orb = orbit_series(sat, start, args.hours)
    idx = max(0, min(args.minute, len(orb) - 1))
    print("  predicting passes...")
    passes = predict_passes(sat, st, start, args.hours)
    look = []
    for p in passes:
        n = max(2, int((p["set"] - p["rise"]).total_seconds() // 10) + 1)
        look.append([elevation_at(sat, st, p["rise"] + (p["set"] - p["rise"]) * k / (n - 1))[:2] for k in range(n)])
    print("  simulating telemetry and training the Isolation Forest...")
    run = run_health(sat, st, start, args.hours, not args.no_faults)

    print("  fleet overview...")
    all_stale = all(abs((now - s.epoch).total_seconds()) / 86400 > 14 for s in sats)
    ref = max(s.epoch for s in sats) if (all_stale and args.at != "now") else start
    snap, orbits, allp = [], [], []
    for k, s in enumerate(sats):
        p = state(s, ref)
        _, per, inc = elements(s)
        snap.append((s.name, str(s.satnum), f"{p['lat']:.2f}°", f"{p['lon']:.2f}°", f"{p['alt']:.1f} km",
                     f"{inc:.2f}°", f"{per:.2f} min", f"{(ref - s.epoch).total_seconds() / 86400:.2f} d"))
        orbits.append((s.name, orbit_series(s, ref, 3.0), SAT_COLORS[k % len(SAT_COLORS)]))
        allp += predict_passes(s, st, ref, args.hours)
    allp.sort(key=lambda p: p["rise"])
    elems, _, _ = elements(sat)

    print("  drawing PDF...")
    lines = coastlines()
    subtitle = f"NORAD {sat.satnum} · window {start:%d %b %Y %H:%M} UTC + {args.hours:g} h · ground station {st['name']}"
    builders = [("Tracking", lambda c: page_tracking(c, sat, orb, idx, st, lines, col, stale_note)),
                ("Passes", lambda c: page_passes(c, sat, passes, st, look)),
                ("Telemetry & health", lambda c: page_health(c, run, args.hours)),
                ("Telemetry", lambda c: page_telemetry(c, run)),
                ("Fleet", lambda c: page_fleet(c, sats, snap, orbits, allp, st, lines)),
                ("Orbital elements", lambda c: page_elements(c, sat, elems))]
    pages = []
    for k, (tab, build) in enumerate(builders, 1):
        c = Canvas()
        header(c, k, len(builders), sat.name, subtitle, tab)
        build(c)
        pages.append(c)
    write_pdf(pages, args.out, f"Satellite tracking & health report — {sat.name}")

    s = orbit_summary(orb)
    print(f"\nDone in {time.time() - t_start:.1f} s -> {os.path.abspath(args.out)}")
    print(f"  altitude {s['min_alt']:.0f}-{s['max_alt']:.0f} km, sunlit {100 * s['sunlit']:.0f} %, "
          f"{len(passes)} passes over {st['name']}")
    print("  detector (SIMULATED telemetry):")
    for name, m in run["metrics"]:
        print(f"    {name:<24} precision {m['precision']:.2f}  recall {m['recall']:.2f}  faults caught {m['caught']}")
    if sys.platform.startswith("win"):
        os.startfile(os.path.abspath(args.out))           # open the PDF automatically on Windows
