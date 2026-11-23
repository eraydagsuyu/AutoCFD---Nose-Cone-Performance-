"""ISA troposfer (0–11 km) ve serbest akış koşulları."""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass

T0, P0, LAPSE, G0 = 288.15, 101325.0, 0.0065, 9.80665


@dataclass
class Freestream:
    velocity: float      # m/s
    altitude: float      # m
    T: float             # K
    p: float             # Pa (mutlak statik)
    rho: float           # kg/m³
    a: float             # m/s
    mach: float
    mu: float            # Pa·s (Sutherland)
    re_per_m: float

    def as_dict(self) -> dict:
        return asdict(self)


def isa(h: float, R: float = 287.05) -> tuple[float, float, float]:
    if not 0 <= h <= 11000:
        raise ValueError(f"ISA troposfer aralığı dışında: h = {h} m")
    T = T0 - LAPSE * h
    p = P0 * (T / T0) ** (G0 / (R * LAPSE))
    return T, p, p / (R * T)


def freestream(velocity: float, altitude: float, phys: dict) -> Freestream:
    air = phys["air"]
    T, p, rho = isa(altitude, air["R_specific"])
    a = math.sqrt(air["gamma"] * air["R_specific"] * T)
    s = air["sutherland"]
    mu = s["mu0"] * (T / s["T0"]) ** 1.5 * (s["T0"] + s["S"]) / (T + s["S"])
    return Freestream(velocity, altitude, T, p, rho, a, velocity / a, mu, rho * velocity / mu)
