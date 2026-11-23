"""Cd(v) -> Cd(t) dönüşümü ve kayıp katsayısı K_kayıp = ∫ Cd(t) dt (trapez)."""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.interpolate import PchipInterpolator

from .config import CONFIG_DIR


def flight_profile() -> pd.DataFrame:
    return pd.read_csv(CONFIG_DIR / "flight_profile.csv").sort_values("time_s").reset_index(drop=True)


def cd_of_t(cd_by_vel: dict[float, float], fp: pd.DataFrame | None = None, method: str = "pchip") -> pd.DataFrame:
    """cd_by_vel: {hız [m/s]: Cd}. Hız aralığı dışında uç değerler sabit tutulur (extrapolasyon yok)."""
    fp = flight_profile() if fp is None else fp
    v = np.array(sorted(cd_by_vel))
    c = np.array([cd_by_vel[k] for k in v])
    vq = np.clip(fp["velocity_ms"].to_numpy(), v.min(), v.max())
    if method == "pchip" and len(v) >= 3:
        cd = PchipInterpolator(v, c)(vq)
    else:
        cd = np.interp(vq, v, c)
    out = fp.copy()
    out["cd"] = cd
    return out


def k_loss(cd_by_vel: dict[float, float], fp: pd.DataFrame | None = None, method: str = "pchip") -> dict:
    d = cd_of_t(cd_by_vel, fp, method)
    t, cd, v = d["time_s"].to_numpy(), d["cd"].to_numpy(), d["velocity_ms"].to_numpy()
    return {
        "K_kayip": float(np.trapezoid(cd, t)),
        "K_v2": float(np.trapezoid(v ** 2 * cd, t)),          # dinamik basınç ağırlıklı yardımcı gösterge
        "t0": float(t[0]), "t1": float(t[-1]),
    }
